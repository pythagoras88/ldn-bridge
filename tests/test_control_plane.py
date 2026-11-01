"""ControlPlane over real sockets. Linux only: uses 127.0.0.x aliases, which also need trio installed."""
import os
import socket
import sys
import unittest

try:
    import trio
except ModuleNotFoundError:
    trio = None

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ldn_bridge import mitm_proto as mp  # noqa: E402

BRIDGE_IP = "127.0.0.2"
BROADCAST_IP = "127.0.0.255"


def free_udp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def scan_from(client_ip: str, port: int) -> tuple[str, bytes]:
    """Run a ControlPlane, send it a Scan from client_ip, return the ScanResp's (source ip, packet)."""
    from ldn_bridge.control_plane import ControlPlane

    info = mp.NetworkInfo(node_count=1)
    cp = ControlPlane(BRIDGE_IP, BROADCAST_IP, port, scan_info=lambda: info, sync_info=lambda: info)
    client = trio.socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    await client.bind((client_ip, 0))
    with trio.fail_after(2):
        async with trio.open_nursery() as n:
            n.start_soon(cp.run)
            await trio.sleep(0.05)
            await client.sendto(mp.encode_packet(mp.PacketType.SCAN), (BROADCAST_IP, port))
            data, addr = await client.recvfrom(4096)
            n.cancel_scope.cancel()
    client.close()
    return addr[0], data


@unittest.skipUnless(sys.platform == "linux" and trio, "needs Linux loopback aliases and trio")
class TestScanResponse(unittest.TestCase):
    def test_reply_to_same_ip_client_does_not_come_from_that_ip(self):
        # Ryujinx's LanProtocol.Read drops UDP whose source is its own LocalAddr, and on the LDN interface
        # the emulator's IP is the bridge's IP.
        source, data = trio.run(scan_from, BRIDGE_IP, free_udp_port())
        self.assertNotEqual(source, BRIDGE_IP)
        self.assertEqual(mp.decode_packet(data)[0], mp.PacketType.SCAN_RESP)

    def test_reply_to_other_host_comes_from_bridge_ip(self):
        source, _ = trio.run(scan_from, "127.0.0.3", free_udp_port())
        self.assertEqual(source, BRIDGE_IP)


if __name__ == "__main__":
    unittest.main()
