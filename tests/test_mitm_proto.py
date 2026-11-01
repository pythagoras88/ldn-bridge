import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ldn_bridge import mitm_proto as mp  # noqa: E402
from ldn_bridge.convert import from_ldn  # noqa: E402


class TestCompression(unittest.TestCase):
    def test_roundtrip(self):
        for data in [b"", b"\x00", b"abc", b"\x00" * 300, b"a\x00\x00b" + b"\x00" * 600 + b"z", bytes(range(256))]:
            self.assertEqual(mp.decompress(mp.compress(data), len(data)), data)

    def test_zero_run_format(self):
        self.assertEqual(mp.compress(b"\x00\x00\x00A"), b"\x00\x02A")
        self.assertEqual(mp.compress(b"\x00" * 257), b"\x00\xff\x00\x00")

    def test_truncated(self):
        with self.assertRaises(mp.ProtocolError):
            mp.decompress(b"A\x00")


class TestPackets(unittest.TestCase):
    def test_header_size(self):
        self.assertEqual(mp.HEADER_SIZE, 12)

    def test_scan_packet(self):
        pkt = mp.encode_packet(mp.PacketType.SCAN)
        self.assertEqual(pkt[:4], (0x11451400).to_bytes(4, "little"))
        t, payload, used = mp.decode_packet(pkt)
        self.assertEqual((t, payload, used), (mp.PacketType.SCAN, b"", 12))

    def test_compressed_roundtrip_and_stream_framing(self):
        info = mp.NetworkInfo(local_communication_id=0x0100A3D008C5C000, scene_id=3, node_count=1)
        pkt = mp.encode_packet(mp.PacketType.SYNC_NETWORK, info.pack())
        self.assertEqual(pkt[5], 1, "a mostly-zero NetworkInfo should be sent compressed")
        stream = pkt + pkt[:5]  # one full packet + a partial one
        t, payload, used = mp.decode_packet(stream)
        self.assertEqual(t, mp.PacketType.SYNC_NETWORK)
        self.assertEqual(mp.NetworkInfo.unpack(payload).scene_id, 3)
        self.assertIsNone(mp.decode_packet(stream[used:]))

    def test_bad_magic(self):
        with self.assertRaises(mp.ProtocolError):
            mp.decode_packet(b"\x00" * 12)


class TestStructs(unittest.TestCase):
    def test_sizes(self):
        self.assertEqual(len(mp.NodeInfo().pack()), 0x40)
        self.assertEqual(len(mp.NetworkInfo().pack()), 0x480)

    def test_node_ip_byte_order(self):
        raw = mp.NodeInfo(ip="169.254.1.2").pack()
        self.assertEqual(raw[:4], bytes([2, 1, 254, 169]))

    def test_network_roundtrip(self):
        info = mp.NetworkInfo(
            local_communication_id=0x0100A3D008C5C000, scene_id=7, session_id=bytes(range(16)),
            bssid=b"\x01\x02\x03\x04\x05\x06", ssid=b"ab" * 16, channel=11, security_parameter=b"S" * 16,
            station_accept_policy=0, node_count_max=4, node_count=2, advertise_data=b"\x01\x00\x02" * 100,
            authentication_id=0x1122334455667788,
        )
        info.nodes[0] = mp.NodeInfo("169.254.9.1", b"\xaa" * 6, 0, True, b"Host", 5)
        info.nodes[1] = mp.NodeInfo("169.254.9.2", b"\xbb" * 6, 1, True, b"Deck", 5)
        back = mp.NetworkInfo.unpack(info.pack())
        self.assertEqual(back, info)

    def test_field_offsets(self):
        raw = mp.NetworkInfo(scene_id=0xBEEF, channel=6, node_count=1, advertise_data=b"\x7f").pack()
        self.assertEqual(raw[0x0A:0x0C], (0xBEEF).to_bytes(2, "little"))
        self.assertEqual(raw[0x48:0x4A], (6).to_bytes(2, "little"))
        self.assertEqual(raw[0x67], 1)
        self.assertEqual(raw[0x26A:0x26C], (1).to_bytes(2, "little"))
        self.assertEqual(raw[0x26C], 0x7F)


class TestConvert(unittest.TestCase):
    def fake_ldn_info(self):
        def part(ip, mac, name, connected=True):
            return SimpleNamespace(ip_address=ip, mac_address=mac, connected=connected, name=name, app_version=5)
        parts = [part("169.254.42.1", b"\x11" * 6, b"SwitchHost"), part("169.254.42.2", b"\x22" * 6, b"Deck")]
        parts += [part("0.0.0.0", bytes(6), b"", connected=False) for _ in range(6)]
        return SimpleNamespace(
            local_communication_id=0x0100A3D008C5C000, scene_id=1, ssid=bytes(range(16)), address=b"\x11" * 6,
            channel=6, server_random=b"R" * 16, security_mode=1, accept_policy=0, max_participants=4,
            participants=parts, application_data=b"\x05" * 40,
        )

    def test_sync_info(self):
        info = from_ldn(self.fake_ldn_info())
        self.assertEqual(info.node_count, 2)
        self.assertEqual(info.nodes[0].ip, "169.254.42.1")
        self.assertEqual(info.ssid, bytes(range(16)).hex().encode())
        self.assertEqual(len(info.pack()), 0x480)

    def test_scan_override(self):
        info = from_ldn(self.fake_ldn_info(), host_ip_override="169.254.42.2")
        self.assertEqual(info.nodes[0].ip, "169.254.42.2")
        self.assertEqual(info.nodes[0].user_name, b"SwitchHost")

    def test_local_communication_id_is_the_emulators_not_the_switchs(self):
        # The game on the emulator scans for -1 and Ryujinx's Scan() compares it to the ScanResp's id,
        # so the Switch's real id would hide the session.
        for info in (from_ldn(self.fake_ldn_info()), from_ldn(self.fake_ldn_info(), host_ip_override="169.254.42.2")):
            self.assertEqual(info.local_communication_id, 0xFFFFFFFFFFFFFFFF)


if __name__ == "__main__":
    unittest.main()
