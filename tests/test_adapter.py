import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ldn_bridge.adapter import find_phy, interfaces  # noqa: E402

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


if __name__ == "__main__":
    unittest.main()
