"""The station only reacts to nl80211 events for its own interface. Linux only: the ldn library can't import on Windows."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

try:
    import trio
    from netlink import nl80211

    from ldn_bridge import ldn_side
    from ldn import wlan
except (ImportError, ModuleNotFoundError):
    ldn_side = None

OWN_INDEX = 7
OTHER_INDEX = 3
HOST_MAC = bytes.fromhex("020000000001")
ROUTER_MAC = bytes.fromhex("020000000002")


class FakeMessage:
    def __init__(self, type_, attributes):
        self.type = type_
        self.attributes = attributes


class FakeNL80211:
    def __init__(self, messages):
        self._messages = list(messages)

    async def receive(self):
        if self._messages:
            return self._messages.pop(0)
        await trio.sleep_forever()


class FakeEvents:
    def __init__(self):
        self.items = []

    async def put(self, event):
        self.items.append(event)


class FakeStation:
    def __init__(self, messages):
        self._wlan = FakeNL80211(messages)
        self._events = FakeEvents()

    def index(self):
        return OWN_INDEX


def del_station(index, mac):
    return FakeMessage(nl80211.NL80211_CMD_DEL_STATION,
                       {nl80211.NL80211_ATTR_IFINDEX: index, nl80211.NL80211_ATTR_MAC: mac})


@unittest.skipIf(ldn_side is None, "needs Linux with the ldn library and trio")
class StationEventsTest(unittest.TestCase):
    def run_station(self, messages):
        station = FakeStation(messages)

        async def main():
            with trio.move_on_after(0.2):
                await ldn_side._own_messages_only(station)

        trio.run(main)
        return station._events.items

    def test_patch_is_installed(self):
        self.assertIs(wlan.Station._process_messages, ldn_side._own_messages_only)

    def test_other_interface_leaving_its_router_is_ignored(self):
        events = self.run_station([del_station(OTHER_INDEX, ROUTER_MAC)])
        self.assertEqual(events, [])

    def test_own_interface_losing_the_host_is_reported(self):
        events = self.run_station([del_station(OTHER_INDEX, ROUTER_MAC), del_station(OWN_INDEX, HOST_MAC)])
        self.assertEqual(len(events), 1)
        self.assertIsInstance(events[0], wlan.DisassociationEvent)
        self.assertEqual(bytes(events[0].address), HOST_MAC)

    def test_message_without_an_interface_is_still_handled(self):
        message = FakeMessage(nl80211.NL80211_CMD_DEL_STATION, {nl80211.NL80211_ATTR_MAC: HOST_MAC})
        self.assertEqual(len(self.run_station([message])), 1)


if __name__ == "__main__":
    unittest.main()
