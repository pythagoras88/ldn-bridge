"""The bridge as a client of a hosting emulator. FakeEmulator follows the Ryujinx 1.3.3 rules that matter here."""
import functools
import os
import socket
import sys
import unittest
from types import SimpleNamespace

try:
    import trio
except ModuleNotFoundError:
    trio = None

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ldn_bridge import mitm_proto as mp  # noqa: E402
from ldn_bridge.config import Config  # noqa: E402
from ldn_bridge.convert import node_from_participant  # noqa: E402
from ldn_bridge.hosting import HostSettings, HostTracker  # noqa: E402

try:
    import ldn
    from ldn_bridge import bridge
except (ImportError, ModuleNotFoundError):  # the ldn library can't import on Windows
    ldn = bridge = None

EMULATOR_IP = "127.0.0.2"
SWITCH_IP = "169.254.7.2"
SWITCH_MAC = b"\x02\x11\x22\x33\x44\x55"


SESSION_ID = bytes(range(16))


def hosted(advertise_data=b"code", name=b"Host", scene_id=5, version=21, session_id=SESSION_ID, max_players=4):
    info = mp.NetworkInfo(scene_id=scene_id, session_id=session_id, security_parameter=bytes(16), node_count=1,
                          node_count_max=max_players, advertise_data=advertise_data)
    info.nodes[0] = mp.NodeInfo(ip=EMULATOR_IP, node_id=0, is_connected=True, user_name=name,
                                local_communication_version=version)
    return info


def participant(ip=SWITCH_IP):
    return SimpleNamespace(ip_address=ip, mac_address=SWITCH_MAC, connected=True, name=b"Guest", app_version=21)


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class FakeEmulator:
    """Answers Scan while hosting and ignores control traffic from its own IP, like LanProtocol.Read."""

    def __init__(self, port, info):
        self.port = port
        self.info = info
        self.hosting = True
        self.stations = []
        self.gone = trio.Event()
        self._drop = trio.Event()

    async def run(self, task_status=trio.TASK_STATUS_IGNORED if trio else None):
        udp = trio.socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        await udp.bind((EMULATOR_IP, self.port))
        async with trio.open_nursery() as n:
            await n.start(functools.partial(trio.serve_tcp, self._handle, self.port, host=EMULATOR_IP))
            n.start_soon(self._udp, udp)
            task_status.started()

    async def _udp(self, udp):
        with udp:
            while True:
                data, addr = await udp.recvfrom(4096)
                if addr[0] != EMULATOR_IP and self.hosting and mp.decode_packet(data)[0] == mp.PacketType.SCAN:
                    await udp.sendto(mp.encode_packet(mp.PacketType.SCAN_RESP, self.info.pack()), addr)

    async def _handle(self, stream):
        ignored = stream.socket.getpeername()[0] == EMULATOR_IP
        async with trio.open_nursery() as n:
            async def drop():
                await self._drop.wait()
                await stream.aclose()
                n.cancel_scope.cancel()
            n.start_soon(drop)
            buf = bytearray()
            try:
                while chunk := await stream.receive_some(8192):
                    buf += chunk
                    pkt = mp.decode_packet(buf)
                    if pkt and not ignored and pkt[0] == mp.PacketType.CONNECT:
                        self.stations.append(mp.NodeInfo.unpack(pkt[1]))
                        del buf[:pkt[2]]
                        await stream.send_all(mp.encode_packet(mp.PacketType.SYNC_NETWORK, self.info.pack()))
            except (trio.BrokenResourceError, trio.ClosedResourceError):
                pass
            self.gone.set()
            n.cancel_scope.cancel()

    def drop_stations(self):
        self._drop.set()


class FakeAP:
    def __init__(self):
        self.host = SimpleNamespace(ip_address=EMULATOR_IP, name=b"", connected=True)
        self.network = SimpleNamespace(ssid=bytes([255]) * 16)
        self._interface = SimpleNamespace(_ssid="ff" * 16)
        self.application_data = None
        self.accept_policy = None
        self.kicked = []
        self.send, self.events = trio.open_memory_channel(10)

    def participant(self):
        return self.host

    def info(self):
        return self.network

    def set_application_data(self, data):
        self.application_data = data

    def set_accept_policy(self, policy):
        self.accept_policy = policy

    async def next_event(self):
        return await self.events.receive()

    async def kick(self, index):
        self.kicked.append(index)
        await self.send.send(ldn.LeaveEvent(index, participant()))


async def until(condition):
    with trio.fail_after(3):
        while not condition():
            await trio.sleep(0.01)


class TestHostTracker(unittest.TestCase):
    def test_first_sighting_is_a_change(self):
        tracker = HostTracker()
        self.assertTrue(tracker.update(hosted()))
        self.assertEqual((tracker.session.advertise_data, tracker.session.name), (b"code", b"Host"))

    def test_same_session_is_not_a_change(self):
        tracker = HostTracker()
        tracker.update(hosted())
        self.assertFalse(tracker.update(hosted()))

    def test_new_advertise_data_is_a_change(self):
        tracker = HostTracker()
        tracker.update(hosted())
        self.assertTrue(tracker.update(hosted(b"other")))
        self.assertEqual(tracker.session.advertise_data, b"other")

    def test_keeps_the_games_player_limit(self):
        tracker = HostTracker()
        tracker.update(hosted(max_players=2))  # Link Trade is for 2, Union Circle for 4
        self.assertEqual(tracker.session.max_participants, 2)

    def test_new_player_limit_is_a_change(self):
        tracker = HostTracker()
        tracker.update(hosted())
        self.assertTrue(tracker.update(hosted(max_players=2)))

    def test_nothing_hosting_yet_is_not_a_change(self):
        self.assertFalse(HostTracker().update(None))

    def test_a_new_session_id_is_a_change(self):
        tracker = HostTracker()
        tracker.update(hosted())
        self.assertTrue(tracker.update(hosted(session_id=bytes(16))))
        self.assertEqual(tracker.session.session_id, bytes(16))

    def test_a_missed_scan_doesnt_end_the_session(self):
        tracker = HostTracker(misses_allowed=2)
        tracker.update(hosted())
        self.assertFalse(tracker.update(None))
        self.assertFalse(tracker.update(None))
        self.assertIsNotNone(tracker.session)

    def test_too_many_missed_scans_end_the_session(self):
        tracker = HostTracker(misses_allowed=2)
        tracker.update(hosted())
        tracker.update(None)
        tracker.update(None)
        self.assertTrue(tracker.update(None))
        self.assertIsNone(tracker.session)

    def test_a_reply_resets_the_missed_scans(self):
        tracker = HostTracker(misses_allowed=1)
        tracker.update(hosted())
        tracker.update(None)
        tracker.update(hosted())
        self.assertFalse(tracker.update(None))


class TestNodeFromParticipant(unittest.TestCase):
    def test_keeps_the_switchs_address_and_slot(self):
        node = node_from_participant(1, participant())
        self.assertEqual((node.ip, node.mac, node.node_id), (SWITCH_IP, SWITCH_MAC, 1))
        self.assertEqual((node.is_connected, node.user_name, node.local_communication_version),
                         (True, b"Guest", 21))


@unittest.skipUnless(sys.platform == "linux" and trio, "needs Linux loopback aliases and trio")
class TestEmulatorLink(unittest.TestCase):
    def test_scan_reads_the_emulators_session(self):
        from ldn_bridge import emulator_link

        async def main():
            port = free_port()
            async with trio.open_nursery() as n:
                await n.start(FakeEmulator(port, hosted()).run)
                info = await emulator_link.scan(EMULATOR_IP, port, timeout=1)
                n.cancel_scope.cancel()
            return info

        self.assertEqual(trio.run(main).advertise_data, b"code")

    def test_scan_returns_none_when_nothing_is_hosting(self):
        from ldn_bridge import emulator_link

        async def main():
            port = free_port()
            emulator = FakeEmulator(port, hosted())
            emulator.hosting = False
            async with trio.open_nursery() as n:
                await n.start(emulator.run)
                info = await emulator_link.scan(EMULATOR_IP, port, timeout=0.1)
                n.cancel_scope.cancel()
            return info

        self.assertIsNone(trio.run(main))

    def test_station_reaches_the_emulator_with_the_switchs_details(self):
        from ldn_bridge import emulator_link

        async def main():
            port = free_port()
            emulator = FakeEmulator(port, hosted())
            with trio.fail_after(3):
                async with trio.open_nursery() as n:
                    await n.start(emulator.run)
                    n.start_soon(emulator_link.hold_station, EMULATOR_IP, port, node_from_participant(1, participant()))
                    await until(lambda: emulator.stations)
                    n.cancel_scope.cancel()
            return emulator.stations

        stations = trio.run(main)
        self.assertEqual((stations[0].ip, stations[0].mac), (SWITCH_IP, SWITCH_MAC))

    def test_hold_station_returns_when_the_emulator_hangs_up(self):
        from ldn_bridge import emulator_link

        async def main():
            port = free_port()
            emulator = FakeEmulator(port, hosted())
            returned = trio.Event()

            async def hold():
                await emulator_link.hold_station(EMULATOR_IP, port, node_from_participant(1, participant()))
                returned.set()

            with trio.fail_after(3):
                async with trio.open_nursery() as n:
                    await n.start(emulator.run)
                    n.start_soon(hold)
                    await until(lambda: emulator.stations)
                    emulator.drop_stations()
                    await returned.wait()
                    n.cancel_scope.cancel()

        trio.run(main)


@unittest.skipUnless(sys.platform == "linux" and ldn, "needs Linux and the ldn library")
class TestEmulatorHosts(unittest.TestCase):
    SETTINGS = HostSettings(0x0100A3D008C5C000, 5, 21, 4, 1, 1, 6, 4, b"from the capture")

    def run_bridge(self, scenario):
        """Run emulator_hosts against a FakeAP and FakeEmulator, then the scenario, then stop."""
        created = []

        def create_network(param):
            created.append(param)
            return self.ap_context

        import contextlib

        @contextlib.asynccontextmanager
        async def ap_context():
            yield self.ap

        self.ap_context = ap_context()
        self.addCleanup(setattr, bridge.ldn, "create_network", bridge.ldn.create_network)
        bridge.ldn.create_network = create_network
        self.addCleanup(setattr, bridge, "SCAN_SECONDS", bridge.SCAN_SECONDS)
        self.addCleanup(setattr, bridge, "POLL_SECONDS", bridge.POLL_SECONDS)
        bridge.SCAN_SECONDS, bridge.POLL_SECONDS = 0.05, 0.01

        async def main():
            self.ap = FakeAP()
            port = free_port()
            cfg = Config(ifname="ldn", password=b"secret", mitm_port=port)
            emulator = FakeEmulator(port, hosted())
            with trio.fail_after(5):
                async with trio.open_nursery() as n:
                    await n.start(emulator.run)
                    n.start_soon(bridge.emulator_hosts, cfg, {"key": b"x"}, self.SETTINGS)
                    await scenario(self.ap, emulator)
                    n.cancel_scope.cancel()

        trio.run(main)
        return created[0]

    def test_session_starts_closed_and_without_the_captures_data(self):
        async def scenario(ap, emulator):
            emulator.hosting = False
            await until(lambda: ap.accept_policy == ldn.ACCEPT_NONE)

        self.assertEqual(self.run_bridge(scenario).application_data, b"")

    def test_emulators_session_is_published_and_opened(self):
        async def scenario(ap, emulator):
            await until(lambda: ap.accept_policy == ldn.ACCEPT_ALL)
            self.assertEqual(ap.application_data, b"code")
            self.assertEqual(ap.host.name, b"Host")

        self.run_bridge(scenario)

    def test_switch_sees_the_emulators_session_id(self):
        async def scenario(ap, emulator):
            await until(lambda: ap.accept_policy == ldn.ACCEPT_ALL)
            self.assertEqual(ap.network.ssid, SESSION_ID)
            self.assertEqual(ap._interface._ssid, SESSION_ID.hex())

        self.run_bridge(scenario)

    def test_switch_gets_the_emulators_empty_security_parameter(self):
        async def scenario(ap, emulator):
            await until(lambda: ap.accept_policy == ldn.ACCEPT_ALL)

        self.assertEqual(self.run_bridge(scenario).server_random, bytes(16))

    def test_session_closes_when_the_emulator_stops_hosting(self):
        async def scenario(ap, emulator):
            await until(lambda: ap.accept_policy == ldn.ACCEPT_ALL)
            emulator.hosting = False
            await until(lambda: ap.accept_policy == ldn.ACCEPT_NONE)
            self.assertEqual(ap.application_data, b"")

        self.run_bridge(scenario)

    def test_a_joining_switch_is_connected_to_the_emulator(self):
        async def scenario(ap, emulator):
            await until(lambda: ap.accept_policy == ldn.ACCEPT_ALL)
            await ap.send.send(ldn.JoinEvent(1, participant()))
            await until(lambda: emulator.stations)
            self.assertEqual(emulator.stations[0].ip, SWITCH_IP)

        self.run_bridge(scenario)

    def test_a_leaving_switch_is_disconnected_from_the_emulator(self):
        async def scenario(ap, emulator):
            await until(lambda: ap.accept_policy == ldn.ACCEPT_ALL)
            await ap.send.send(ldn.JoinEvent(1, participant()))
            await until(lambda: emulator.stations)
            await ap.send.send(ldn.LeaveEvent(1, participant()))
            await emulator.gone.wait()
            self.assertEqual(ap.kicked, [])

        self.run_bridge(scenario)

    def test_switch_is_kicked_when_the_emulator_drops_it(self):
        async def scenario(ap, emulator):
            await until(lambda: ap.accept_policy == ldn.ACCEPT_ALL)
            await ap.send.send(ldn.JoinEvent(1, participant()))
            await until(lambda: emulator.stations)
            emulator.drop_stations()
            await until(lambda: ap.kicked == [1])

        self.run_bridge(scenario)


if __name__ == "__main__":
    unittest.main()
