import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ldn_bridge.config import load  # noqa: E402


class TestMode(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "config.toml"

    def load(self, text: str):
        self.path.write_text(text, encoding="utf-8")
        return load(self.path)

    def test_hosts_by_default(self):
        self.assertEqual(self.load("[ldn]\n").mode, "host")

    def test_join_mode(self):
        self.assertEqual(self.load('[launch]\nmode = "join"\n').mode, "join")

    def test_ask_is_a_mode(self):
        # deck/play.sh asks which side hosts; anything else that reads it hosts.
        self.assertEqual(self.load('[launch]\nmode = "ask"\n').mode, "ask")

    def test_unknown_mode_stops(self):
        with self.assertRaises(SystemExit):
            self.load('[launch]\nmode = "both"\n')

    def test_game_id(self):
        self.assertEqual(self.load('[game]\nlocal_communication_id = "0x0100000000001000"\n').local_communication_id,
                         0x0100000000001000)


if __name__ == "__main__":
    unittest.main()
