import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ldn_bridge.config import Config  # noqa: E402
from ldn_bridge.hosting import (  # noqa: E402
    BroadcastWatch, HostSettings, is_station_broadcast, latest_capture, settings_for_game, load_sessions, pick_session, run_session, settings_from_capture,
)

try:
    import ldn  # noqa: F401
    from ldn_bridge import ldn_side
except ImportError:  # the ldn library can't import on Windows
    ldn_side = None


def session(scene_id=5, **changes):
    return {
        "protocol": 1,
        "local_communication_id": "0x0100a3d008c5c000",
        "scene_id": scene_id,
        "app_version": 21,
        "version": 4,
        "security_mode": 1,
        "band": 2,
        "channel": 6,
        "accept_policy": 0,
        "participants": "1/4",
        "application_data_hex": "aabb",
        "members": [],
    } | changes


class TestSettingsFromCapture(unittest.TestCase):
    def test_copies_the_sessions_real_details(self):
        self.assertEqual(settings_from_capture(session()), HostSettings(
            local_communication_id=0x0100A3D008C5C000,
            scene_id=5,
            app_version=21,
            version=4,
            protocol=1,
            security_mode=1,
            channel=6,
            max_participants=4,
            application_data=b"\xaa\xbb",
        ))

    def test_names_a_field_missing_from_an_old_capture(self):
        old = session()
        del old["application_data_hex"]
        with self.assertRaisesRegex(SystemExit, "application_data_hex"):
            settings_from_capture(old)


class TestPickSession(unittest.TestCase):
    def test_uses_the_only_session_without_being_told(self):
        only = session()
        self.assertIs(pick_session([only]), only)

    def test_filters_by_scene(self):
        link_trade, union_circle = session(scene_id=4), session(scene_id=5)
        self.assertIs(pick_session([link_trade, union_circle], scene_id=5), union_circle)

    def test_index_counts_within_the_matching_scene(self):
        other, first, second = session(scene_id=4), session(scene_id=5), session(scene_id=5)
        self.assertIs(pick_session([other, first, second], scene_id=5, index=1), second)

    def test_refuses_to_guess_between_sessions(self):
        with self.assertRaisesRegex(SystemExit, "--index"):
            pick_session([session(scene_id=4), session(scene_id=5)])

    def test_says_which_scenes_exist_when_none_match(self):
        with self.assertRaisesRegex(SystemExit, r"\[4\]"):
            pick_session([session(scene_id=4)], scene_id=5)

    def test_rejects_an_index_past_the_end(self):
        with self.assertRaisesRegex(SystemExit, "--index"):
            pick_session([session()], index=1)


class TestCaptureFiles(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def test_latest_capture_is_the_newest_scan(self):
        for name in ("scan-20261101-100000.json", "scan-20261101-120000.json", "mitm-scan-20261101-130000.json"):
            (self.root / name).write_text("[]")
        self.assertEqual(latest_capture(self.root).name, "scan-20261101-120000.json")

    def test_no_scan_capture_says_to_run_scan(self):
        with self.assertRaisesRegex(SystemExit, "ldn_bridge scan"):
            latest_capture(self.root)

    def test_no_captures_folder_says_to_run_scan(self):
        with self.assertRaisesRegex(SystemExit, "ldn_bridge scan"):
            latest_capture(self.root / "missing")

    def test_load_sessions_reads_a_capture(self):
        path = self.root / "scan.json"
        path.write_text(json.dumps([session()]))
        self.assertEqual(load_sessions(path), [session()])

    def test_load_sessions_names_a_missing_file(self):
        with self.assertRaisesRegex(SystemExit, "nope.json"):
            load_sessions(self.root / "nope.json")


def raises(error):
    def run():
        raise error
    return run


class TestRunSession(unittest.TestCase):
    def test_ctrl_c_wrapped_by_the_librarys_nurseries_is_a_normal_stop(self):
        run_session(raises(BaseExceptionGroup("", [BaseExceptionGroup("", [KeyboardInterrupt()])])))

    def test_plain_ctrl_c_is_a_normal_stop(self):
        run_session(raises(KeyboardInterrupt()))

    def test_a_failure_in_the_session_gives_a_readable_exit(self):
        with self.assertLogs("ldn_bridge.hosting", "ERROR"), self.assertRaisesRegex(SystemExit, "Hosting failed"):
            run_session(raises(ExceptionGroup("", [OSError("no such device")])))

    def test_a_missing_adapter_keeps_its_own_message(self):
        with self.assertRaisesRegex(SystemExit, "USB adapter"):
            run_session(raises(SystemExit("USB adapter not found")))


@unittest.skipIf(ldn_side is None, "needs the ldn library, which only imports on Linux")
class TestBadFrames(unittest.TestCase):
    KEY = bytes(16)
    AP_MAC = "02:00:00:00:00:01"
    SWITCH_MAC = "02:00:00:00:00:02"

    def setUp(self):
        from types import SimpleNamespace
        from ldn import queue, wlan

        self.wlan = wlan
        self.switch = wlan.MACAddress(self.SWITCH_MAC)
        self.ap = wlan.MonitorAP.__new__(wlan.MonitorAP)
        self.ap._monitor = SimpleNamespace(address=lambda: wlan.MACAddress(self.AP_MAC))
        self.ap._stations_by_address = {self.switch: 1}
        self.ap._key = self.KEY
        self.ap._data_frames = queue.create()

    def frame(self):
        snap = self.wlan.SNAPHeader()
        snap.protocol = 0x0800
        snap.payload = b"game data"
        frame = self.wlan.DataFrame()
        frame.target = self.wlan.MACAddress(self.AP_MAC)
        frame.source = self.switch
        frame.bssid = self.wlan.MACAddress(self.AP_MAC)
        frame.payload = snap.encode()
        frame.encrypt(self.KEY, 1, 0)
        return frame

    def test_a_frame_that_fails_its_check_doesnt_end_the_session(self):
        import trio

        frame = self.frame()
        frame.payload = frame.payload[:-1] + bytes([frame.payload[-1] ^ 1])
        trio.run(self.ap._process_data_frame, frame)

    def test_good_frames_still_get_through(self):
        import trio

        async def main():
            await self.ap._process_data_frame(self.frame())
            return await self.ap.receive_data()

        self.assertEqual(trio.run(main).payload, b"game data")


@unittest.skipIf(ldn_side is None, "needs the ldn library, which only imports on Linux")
class TestCreateParam(unittest.TestCase):
    def setUp(self):
        self.cfg = Config(phyname="phy2", ifname="ldn", password=b"secret", nickname="Bridge")
        self.param = ldn_side.create_param(self.cfg, {"key": b"x"}, settings_from_capture(session()))

    def test_session_details_reach_the_library(self):
        p = self.param
        self.assertEqual((p.local_communication_id, p.scene_id, p.app_version, p.version, p.protocol),
                         (0x0100A3D008C5C000, 5, 21, 4, 1))
        self.assertEqual((p.security_mode, p.channel, p.max_participants, p.application_data),
                         (1, 6, 4, b"\xaa\xbb"))

    def test_uses_the_adapters_phy_and_the_passphrase(self):
        self.assertEqual((self.param.phyname, self.param.password), ("phy2", b"secret"))

    def test_emulator_interface_keeps_the_configured_name(self):
        self.assertEqual(self.param.ifname_tap, "ldn")

    def test_interface_names_dont_collide(self):
        p = self.param
        self.assertEqual(len({p.ifname, p.ifname_active, p.ifname_tap}), 3)

    def test_library_accepts_the_param(self):
        self.param.check()


def frame(fc1=0x40, addr1=b"\xff" * 6, ftype=0x08):
    """An 802.11 header: frame control, duration, addr1, addr2, addr3, sequence, then 8 body bytes."""
    return bytes([ftype, fc1]) + bytes(2) + addr1 + bytes.fromhex("020000000005") + bytes(6) + bytes(2) + bytes(8)


class TestSettingsForGame(unittest.TestCase):
    """Hosting without a scan capture: the game's ID from config.toml, the rest from the emulator once it hosts."""

    def test_uses_the_games_id(self):
        self.assertEqual(settings_for_game(0x0100000000001000).local_communication_id, 0x0100000000001000)

    def test_no_session_data_until_the_emulator_hosts(self):
        self.assertEqual(settings_for_game(1).application_data, b"")

    def test_room_for_any_mode(self):
        self.assertEqual(settings_for_game(1).max_participants, 8)

    def test_protocol(self):
        self.assertEqual(settings_for_game(1, protocol=3).protocol, 3)


class TestStationBroadcast(unittest.TestCase):
    def test_station_broadcast(self):
        self.assertTrue(is_station_broadcast(frame()))

    def test_qos_data_counts(self):
        self.assertTrue(is_station_broadcast(frame(ftype=0x88)))

    def test_host_broadcast_has_from_ds(self):
        self.assertFalse(is_station_broadcast(frame(fc1=0x42)))

    def test_unicast_is_not_broadcast(self):
        self.assertFalse(is_station_broadcast(frame(addr1=bytes.fromhex("020000000002"))))

    def test_management_frame_is_not_data(self):
        self.assertFalse(is_station_broadcast(frame(ftype=0x80)))

    def test_short_frame(self):
        self.assertFalse(is_station_broadcast(b"\x08\x40"))


class TestBroadcastWatch(unittest.TestCase):
    def setUp(self):
        self.calls = 0
        self.watch = BroadcastWatch(self.alarm, min_unreadable=50, ratio=4)

    def alarm(self):
        self.calls += 1

    def test_all_unreadable_raises_the_alarm_once(self):
        for _ in range(200):
            self.watch.record(False)
        self.assertEqual(self.calls, 1)

    def test_a_few_unreadable_at_the_start_are_fine(self):
        for _ in range(27):
            self.watch.record(False)
        for _ in range(10000):
            self.watch.record(True)
        self.assertEqual(self.calls, 0)

    def test_needs_enough_frames(self):
        for _ in range(49):
            self.watch.record(False)
        self.assertEqual(self.calls, 0)

    def test_mostly_readable_with_damage_is_fine(self):
        for _ in range(100):
            for _ in range(10):
                self.watch.record(True)
            self.watch.record(False)
        self.assertEqual(self.calls, 0)

    def test_counts(self):
        self.watch.record(True)
        self.watch.record(False)
        self.assertEqual((self.watch.readable, self.watch.unreadable), (1, 1))


if __name__ == "__main__":
    unittest.main()
