import os
import socket
import struct
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ldn_bridge import packets, tunnel_proto  # noqa: E402

MY_MAC = bytes.fromhex("020000000002")
SWITCH_MAC = bytes.fromhex("020000000001")


class TestUdpPacket(unittest.TestCase):
    def test_round_trip(self):
        pkt = packets.udp_ipv4("169.254.48.1", 11452, "169.254.48.2", 40000, b"hello")
        info = packets.parse_ipv4(pkt)
        self.assertEqual((info.src, info.dst, info.proto, info.sport, info.dport, info.payload),
                         ("169.254.48.1", "169.254.48.2", 17, 11452, 40000, b"hello"))

    def test_ip_header_checksum_verifies(self):
        pkt = packets.udp_ipv4("169.254.48.1", 1, "169.254.48.2", 2, b"x")
        self.assertEqual(packets.checksum(pkt[:20]), 0)

    def test_udp_checksum_verifies(self):
        pkt = packets.udp_ipv4("169.254.48.1", 1, "169.254.48.2", 2, b"odd")
        udp = pkt[20:]
        pseudo = pkt[12:20] + struct.pack("!BBH", 0, 17, len(udp))
        self.assertEqual(packets.checksum(pseudo + udp), 0)

    def test_rejects_short_and_non_ipv4(self):
        self.assertIsNone(packets.parse_ipv4(b"\x45" * 10))
        self.assertIsNone(packets.parse_ipv4(b"\x60" + b"\x00" * 39))

    def test_later_fragments_have_no_ports(self):
        pkt = bytearray(packets.udp_ipv4("10.0.0.1", 5, "10.0.0.2", 6, b"data"))
        pkt[6:8] = struct.pack("!H", 100)
        self.assertIsNone(packets.parse_ipv4(bytes(pkt)).dport)


class TestArp(unittest.TestCase):
    def request(self, target: str) -> bytes:
        return (struct.pack("!HHBBH", 1, 0x0800, 6, 4, 1) + SWITCH_MAC + socket.inet_aton("169.254.48.1")
                + bytes(6) + socket.inet_aton(target))

    def test_answers_for_my_ip(self):
        reply = packets.arp_reply(self.request("169.254.48.2"), "169.254.48.2", MY_MAC)
        self.assertEqual(reply[6:8], b"\x00\x02")
        self.assertEqual(reply[8:14], MY_MAC)
        self.assertEqual(reply[14:18], socket.inet_aton("169.254.48.2"))
        self.assertEqual(reply[18:24], SWITCH_MAC)

    def test_ignores_other_ips(self):
        self.assertIsNone(packets.arp_reply(self.request("169.254.48.3"), "169.254.48.2", MY_MAC))


class TestEthernet(unittest.TestCase):
    def test_round_trip(self):
        frame = packets.ethernet(SWITCH_MAC, MY_MAC, packets.ETH_P_IP, b"payload")
        self.assertEqual(packets.parse_ethernet(frame), (SWITCH_MAC, MY_MAC, 0x0800, b"payload"))

    def test_multicast(self):
        self.assertTrue(packets.is_multicast("224.0.0.251"))
        self.assertFalse(packets.is_multicast("169.254.48.255"))
        self.assertEqual(packets.multicast_mac("224.0.0.251"), bytes.fromhex("01005e0000fb"))


class TestTunnelProto(unittest.TestCase):
    def test_split_and_joined_messages(self):
        data = tunnel_proto.config("169.254.48.2", 24) + tunnel_proto.encode(tunnel_proto.PACKET, b"abc")
        d = tunnel_proto.Decoder()
        self.assertEqual(d.feed(data[:3]), [])
        msgs = d.feed(data[3:])
        self.assertEqual(msgs[0], (tunnel_proto.CONFIG, socket.inet_aton("169.254.48.2") + b"\x18"))
        self.assertEqual(tunnel_proto.parse_config(msgs[0][1]), ("169.254.48.2", 24))
        self.assertEqual(msgs[1], (tunnel_proto.PACKET, b"abc"))


if __name__ == "__main__":
    unittest.main()
