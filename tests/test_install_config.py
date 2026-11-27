import os
import sys
import tomllib
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ldn_bridge.install_config import protocols_for, set_value, toml_string, update_ryujinx  # noqa: E402

EXAMPLE = os.path.join(os.path.dirname(__file__), "..", "config.example.toml")


class TestSetValue(unittest.TestCase):
    def setUp(self):
        with open(EXAMPLE, encoding="utf-8") as f:
            self.text = f.read()

    def test_replaces_in_the_right_section_and_keeps_comments(self):
        text = set_value(self.text, "ldn", "adapter_mac", toml_string("00:11:22:33:44:55"))
        text = set_value(text, "launch", "emulator", toml_string("/home/deck/Applications/Ryujinx.AppImage"))
        data = tomllib.loads(text)
        self.assertEqual(data["ldn"]["adapter_mac"], "00:11:22:33:44:55")
        self.assertEqual(data["launch"]["emulator"], "/home/deck/Applications/Ryujinx.AppImage")
        self.assertEqual(text.count("# USB adapter's MAC"), 1)
        self.assertEqual(len(text.splitlines()), len(self.text.splitlines()))

    def test_lists_and_unicode_paths(self):
        text = set_value(self.text, "ldn", "protocols", "[1, 3]")
        text = set_value(text, "launch", "game", toml_string("/home/deck/Games/Pokémon™ [v0].nsp"))
        data = tomllib.loads(text)
        self.assertEqual(data["ldn"]["protocols"], [1, 3])
        self.assertEqual(data["launch"]["game"], "/home/deck/Games/Pokémon™ [v0].nsp")

    def test_adds_missing_key_and_section(self):
        text = set_value("[ldn]\nifname = \"ldn\"", "ldn", "adapter_mac", '"aa"')
        text = set_value(text, "launch", "emulator", '"x"')
        data = tomllib.loads(text)
        self.assertEqual(data, {"ldn": {"ifname": "ldn", "adapter_mac": "aa"}, "launch": {"emulator": "x"}})

    def test_does_not_touch_same_key_in_other_section(self):
        text = set_value("[a]\nk = 1\n[b]\nk = 2\n", "b", "k", "3")
        self.assertEqual(tomllib.loads(text), {"a": {"k": 1}, "b": {"k": 3}})


class TestProtocols(unittest.TestCase):
    def test_from_key_names(self):
        base = ["aes_kek_generation_source", "aes_key_generation_source"]
        self.assertEqual(protocols_for(base + ["master_key_00"]), [1])
        self.assertEqual(protocols_for(base + ["master_key_00", "master_key_12"]), [1, 3])
        self.assertEqual(protocols_for(["master_key_00"]), [])


class TestRyujinx(unittest.TestCase):
    def test_sets_ldn_mitm_interface_and_no_internet(self):
        config = {"multiplayer_mode": 0, "multiplayer_lan_interface_id": "0", "enable_internet_access": True, "x": 1}
        self.assertEqual(len(update_ryujinx(config, "ldn")), 3)
        self.assertEqual(config, {"multiplayer_mode": 2, "multiplayer_lan_interface_id": "ldn",
                                  "enable_internet_access": False, "x": 1})
        self.assertEqual(update_ryujinx(config, "ldn"), [])


if __name__ == "__main__":
    unittest.main()
