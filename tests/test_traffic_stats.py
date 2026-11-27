import os
import socket
import struct
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ldn_bridge import packets  # noqa: E402
from ldn_bridge.traffic_stats import TrafficStats  # noqa: E402

MAC_A = b"\x02\x00\x00\x00\x00\x01"
MAC_B = b"\x02\x00\x00\x00\x00\x02"


def ip_packet(proto: int, dst: str = "169.254.5.2", flags_frag: int = 0, body: bytes = b"\x00" * 8) -> bytes:
    header = struct.pack("!BBHHHBBH4s4s", 0x45, 0, 20 + len(body), 0, flags_frag, 64, proto, 0,
                         socket.inet_aton("169.254.5.1"), socket.inet_aton(dst))
    return header + body


def frame(packet: bytes) -> bytes:
    return packets.ethernet(MAC_B, MAC_A, packets.ETH_P_IP, packet)


def udp_frame(dst: str, size: int) -> bytes:
    return frame(packets.udp_ipv4("169.254.5.1", 1000, dst, 2000, b"x" * size))


class TrafficStatsTests(unittest.TestCase):
    def test_counts_udp_tcp_and_other(self):
        s = TrafficStats("169.254.5.255")
        s.add(udp_frame("169.254.5.2", 10))
        s.add(frame(ip_packet(6)))
        s.add(frame(ip_packet(1)))
        r = s.summary()
        self.assertEqual((r["udp"], r["tcp"], r["other_ip"]), (1, 1, 1))

    def test_counts_fragments(self):
        s = TrafficStats("169.254.5.255")
        s.add(frame(ip_packet(17, flags_frag=0x2000)))  # MF set
        s.add(frame(ip_packet(17, flags_frag=0x00B9)))  # offset > 0
        s.add(udp_frame("169.254.5.2", 10))
        self.assertEqual(s.summary()["fragments"], 2)

    def test_counts_multicast_broadcast_and_max_size(self):
        s = TrafficStats("169.254.5.255")
        s.add(udp_frame("224.0.0.1", 10))
        s.add(udp_frame("169.254.5.255", 1400))
        r = s.summary()
        self.assertEqual((r["multicast"], r["broadcast"], r["max_udp_payload"]), (1, 1, 1400))

    def test_ignores_non_ip_and_garbage(self):
        s = TrafficStats("169.254.5.255")
        s.add(packets.ethernet(MAC_B, MAC_A, packets.ETH_P_ARP, b"\x00" * 28))
        s.add(b"\x01\x02")
        self.assertEqual(sum(s.summary().values()), 0)


if __name__ == "__main__":
    unittest.main()
