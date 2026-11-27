import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ldn_bridge.adapter import find_phy, interfaces, leftovers, link_quality, usb_node, wait_for_return  # noqa: E402

ALFA = "02:00:00:00:00:02"


def fake_wiphy(root: Path, phy: str, mac: str, *ifaces: str) -> None:
    (root / phy).mkdir()
    (root / phy / "macaddress").write_text(mac + "\n")
    for iface in ifaces:
        (root / phy / "device" / "net" / iface).mkdir(parents=True)


class TestFindAdapter(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        fake_wiphy(self.root, "phy0", "02:00:00:00:00:01", "wlan0")
        fake_wiphy(self.root, "phy3", ALFA, "wlan3")

    def test_finds_phy_by_mac_whatever_its_number(self):
        self.assertEqual(find_phy(ALFA, self.root), "phy3")

    def test_mac_match_ignores_case(self):
        self.assertEqual(find_phy(ALFA.upper(), self.root), "phy3")

    def test_missing_adapter_stops_instead_of_using_another_card(self):
        with self.assertRaises(SystemExit):
            find_phy("00:11:22:33:44:55", self.root)

    def test_interfaces_are_only_the_adapters(self):
        self.assertEqual(interfaces("phy3", self.root), ["wlan3"])

    def test_phy_without_interfaces(self):
        fake_wiphy(self.root, "phy4", "00:11:22:33:44:55")
        self.assertEqual(interfaces("phy4", self.root), [])

    def test_leftovers_are_only_the_bridges_own_interfaces(self):
        fake_wiphy(self.root, "phy5", "00:11:22:33:44:66", "ldn", "wlan5")
        self.assertEqual(leftovers("phy5", ["ldn", "ldn-mon"], self.root), ["ldn"])

    def test_leftovers_ignore_other_cards(self):
        fake_wiphy(self.root, "phy5", "00:11:22:33:44:66", "ldn")
        self.assertEqual(leftovers("phy3", ["ldn", "ldn-mon"], self.root), [])



STATION_DUMP = """Station 02:00:00:00:00:09 (on ldn)
	inactive time:	56 ms
	rx packets:	375
	tx packets:	28
	tx retries:	17
	tx failed:	5
	beacon loss:	2
	signal:  	-88 [-89, -95] dBm
	tx bitrate:	39.0 MBit/s MCS 4
"""


class TestLinkQuality(unittest.TestCase):
    def test_reads_signal_and_counters(self):
        self.assertEqual(link_quality(STATION_DUMP),
                         {"signal": -88, "tx_packets": 28, "tx_retries": 17, "tx_failed": 5, "beacon_loss": 2})

    def test_no_station_gives_nothing(self):
        self.assertEqual(link_quality(""), {})


class TestUsbReset(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def test_usb_node_comes_from_the_device_above_the_interface(self):
        interface = self.root / "usb1" / "1-1" / "1-1.4" / "1-1.4_1.0"  # really "1-1.4:1.0", which Windows can't name
        interface.mkdir(parents=True)
        (interface.parent / "busnum").write_text("1\n")
        (interface.parent / "devnum").write_text("54\n")
        self.assertEqual(usb_node(interface), Path("/dev/bus/usb/001/054"))

    def test_waits_until_the_adapter_comes_back_as_a_new_phy(self):
        fake_wiphy(self.root, "phy0", "02:00:00:00:00:01")
        fake_wiphy(self.root, "phy22", ALFA)
        steps = []

        def sleep(_):
            steps.append(1)
            if len(steps) == 1:  # the reset removes the adapter
                (self.root / "phy22" / "macaddress").unlink()
                (self.root / "phy22").rmdir()
            elif len(steps) == 3:  # and it comes back with a new number
                fake_wiphy(self.root, "phy23", ALFA)
        self.assertEqual(wait_for_return(ALFA, "phy22", 10, self.root, sleep), "phy23")
        self.assertEqual(len(steps), 3)

    def test_gives_up_after_the_timeout(self):
        fake_wiphy(self.root, "phy22", ALFA)
        clock = iter(range(100))
        self.assertEqual(wait_for_return(ALFA, "phy22", 5, self.root, lambda _: None, lambda: next(clock)), "phy22")

    def test_missing_after_the_timeout(self):
        clock = iter(range(100))
        self.assertIsNone(wait_for_return(ALFA, "phy22", 5, self.root, lambda _: None, lambda: next(clock)))


if __name__ == "__main__":
    unittest.main()
