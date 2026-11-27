"""Thin, config-driven wrappers over kinnay's ldn library."""
from __future__ import annotations

import logging
import socket

import ldn
from ldn import wlan
from netlink import nl80211

from . import adapter
from .captures import save_capture  # noqa: F401  (re-exported for callers)
from .config import REQUIRED_KEYS, Config
from .convert import mac_bytes
from .hosting import BroadcastWatch, HostSettings, is_station_broadcast

log = logging.getLogger(__name__)

HOST_MONITOR_IFNAME = "ldn-mon"
# Seconds per channel. The library's default is 0.11, about one advertisement, so one damaged frame hides a session.
SCAN_DWELL = 0.3

_process_data_frame = wlan.MonitorAP._process_data_frame
_parse_frame = wlan.Monitor._parse_frame
_dropped_frames = 0
BROADCAST = wlan.MACAddress("ff:ff:ff:ff:ff:ff")
# Set while hosting, to notice when the stations' broadcasts can't be read (hosting.BroadcastWatch).
broadcast_watch: BroadcastWatch | None = None


async def _drop_bad_frames(self, frame) -> None:
    """The library lets a frame that fails its integrity check end the hosted session. Radio frames can arrive damaged."""
    global _dropped_frames
    watched = (broadcast_watch is not None and frame.target == BROADCAST and not frame.tods and not frame.fromds
               and frame.source in self._stations_by_address)
    try:
        await _process_data_frame(self, frame)
    except ValueError as e:
        _dropped_frames += 1
        if _dropped_frames == 1 or _dropped_frames % 100 == 0:
            log.warning("Dropped %d data frame(s) from a station. Latest: %s", _dropped_frames, e)
        if watched:
            broadcast_watch.record(False)
        return
    if watched:
        broadcast_watch.record(True)


def _watch_unparsable(self, data: bytes, **kw):
    """The library skips frames it can't parse without a word. A protected frame without a CCMP header is one of them,
    and it's what a wrongly decrypted broadcast looks like."""
    try:
        return _parse_frame(self, data, **kw)
    except Exception:
        if broadcast_watch is not None and is_station_broadcast(data):
            broadcast_watch.record(False)
        raise


wlan.MonitorAP._process_data_frame = _drop_bad_frames
wlan.Monitor._parse_frame = _watch_unparsable


async def _own_messages_only(self) -> None:
    """The library's station hears nl80211 events from every Wi-Fi interface. Without this check, the computer's own
    Wi-Fi switching routers removes a station on that interface, and the library reports it as losing the Switch."""
    while True:
        message = await self._wlan.receive()
        attrs = message.attributes
        if nl80211.NL80211_ATTR_IFINDEX in attrs and attrs[nl80211.NL80211_ATTR_IFINDEX] != self.index():
            continue
        if message.type == nl80211.NL80211_CMD_FRAME:
            frame = wlan.ActionFrame()
            frame.decode(attrs[nl80211.NL80211_ATTR_FRAME])
            await self._events.put(wlan.ActionFrameEvent(frame, attrs[nl80211.NL80211_ATTR_WIPHY_FREQ]))
        elif message.type == nl80211.NL80211_CMD_CONTROL_PORT_FRAME:
            mac = wlan.MACAddress(attrs[nl80211.NL80211_ATTR_MAC])
            await self._events.put(wlan.CustomFrameEvent(mac, attrs[nl80211.NL80211_ATTR_FRAME]))
        elif message.type == nl80211.NL80211_CMD_DEL_STATION:
            await self._events.put(wlan.DisassociationEvent(wlan.MACAddress(attrs[nl80211.NL80211_ATTR_MAC])))


wlan.Station._process_messages = _own_messages_only

PLATFORMS = {ldn.PLATFORM_NX: "Switch", ldn.PLATFORM_OUNCE: "Switch 2"}


def load_keys(cfg: Config) -> dict[str, bytes]:
    return ldn.load_keys(cfg.keys_file)


def key_report(keys: dict[str, bytes]) -> dict[int, list[str]]:
    """Missing key *names* per protocol. Never returns values."""
    return {proto: [k for k in names if k not in keys] for proto, names in REQUIRED_KEYS.items()}


async def remove_leftovers(cfg: Config) -> None:
    """Delete interfaces an interrupted run left on the adapter. Creating a new one fails until they're gone."""
    # ldn-ack is the library's second hosting interface, left behind if host mode was killed.
    names = adapter.leftovers(cfg.phyname, [cfg.ifname, HOST_MONITOR_IFNAME, "ldn-ack"])
    if not names:
        return
    async with nl80211.connect() as nl:
        for ifname in names:
            log.info("removing leftover interface %s on %s", ifname, cfg.phyname)
            await nl.request(nl80211.NL80211_CMD_DEL_INTERFACE,
                             {nl80211.NL80211_ATTR_IFINDEX: socket.if_nametoindex(ifname)})


async def scan(cfg: Config, keys) -> list:
    if cfg.adapter_mac:
        cfg.phyname = adapter.prepare(cfg.adapter_mac)
        await remove_leftovers(cfg)
    log.info("scanning phy=%s channels=%s protocols=%s", cfg.phyname, cfg.channels, cfg.protocols)
    nets = await ldn.scan(keys, ifname=cfg.ifname, phyname=cfg.phyname,
                          channels=cfg.channels, protocols=cfg.protocols, dwell_time=SCAN_DWELL)
    return [n for n in nets if matches(cfg, n)]


async def wait_for_network(cfg: Config, keys) -> list:
    """Sweep the channels on one monitor until a matching session shows up. Starting a new scan each time spends most
    of its time setting up, and listens for under a second of it."""
    if cfg.adapter_mac:
        cfg.phyname = adapter.prepare(cfg.adapter_mac)
        await remove_leftovers(cfg)
    log.info("waiting for a session on phy=%s channels=%s protocols=%s", cfg.phyname, cfg.channels, cfg.protocols)
    key_derivations = {protocol: ldn.KeyDerivation(keys, protocol) for protocol in cfg.protocols}
    async with wlan.create_factory() as factory:
        async with factory.create_monitor(cfg.phyname, cfg.ifname) as monitor:
            scanner = ldn.Scanner(key_derivations, monitor)
            while True:
                if cfg.adapter_mac:
                    # The adapter's own interface can come back up, and the monitor can't change channel while it is.
                    for ifname in adapter.interfaces(cfg.phyname):
                        if ifname != cfg.ifname:
                            adapter.set_down(ifname)
                nets = [n for n in await scanner.scan(cfg.channels, SCAN_DWELL) if matches(cfg, n)]
                if nets:
                    return nets


def matches(cfg: Config, n) -> bool:
    if cfg.local_communication_id is not None and n.local_communication_id != cfg.local_communication_id:
        return False
    if cfg.scene_id is not None and n.scene_id != cfg.scene_id:
        return False
    return True


def network_to_dict(n) -> dict:
    return {
        "protocol": n.protocol,
        "local_communication_id": f"0x{n.local_communication_id:016x}",
        "scene_id": n.scene_id,
        "app_version": n.app_version,
        "version": n.version,
        "security_mode": n.security_mode,
        "band": n.band,
        "channel": n.channel,
        "host_mac": mac_bytes(n.address).hex(":"),
        "ssid": bytes(n.ssid).hex(),
        "accept_policy": n.accept_policy,
        "participants": f"{n.num_participants}/{n.max_participants}",
        "application_data_hex": bytes(n.application_data).hex(),
        "members": [
            {"index": i, "name": p.name.decode(errors="replace"), "ip": p.ip_address,
             "mac": mac_bytes(p.mac_address).hex(":"), "app_version": p.app_version,
             "platform": PLATFORMS.get(p.platform, p.platform)}
            for i, p in enumerate(n.participants) if p.connected
        ],
    }


def connect_param(cfg: Config, keys, network) -> "ldn.ConnectNetworkParam":
    p = ldn.ConnectNetworkParam()
    p.keys = keys
    p.network = network
    p.phyname = cfg.phyname
    p.ifname = cfg.ifname
    p.password = cfg.password
    p.name = cfg.nickname.encode()[:32]
    p.app_version = network.app_version
    p.platform = ldn.PLATFORM_NX
    return p


def set_session_id(ap, session_id: bytes) -> None:
    """Use the emulator's session ID, which it only picks when the game hosts. The library has no call for this."""
    ap.info().ssid = session_id
    ap._interface._ssid = session_id.hex()


def create_param(cfg: Config, keys, settings: HostSettings) -> "ldn.CreateNetworkParam":
    p = ldn.CreateNetworkParam()
    p.keys = keys
    p.phyname = cfg.phyname
    # The interface the emulator binds to, so its Network Interface setting is the same in both directions.
    p.ifname_tap = cfg.ifname
    p.ifname = HOST_MONITOR_IFNAME
    p.local_communication_id = settings.local_communication_id
    p.scene_id = settings.scene_id
    p.app_version = settings.app_version
    p.version = settings.version
    p.protocol = settings.protocol
    p.security_mode = settings.security_mode
    p.channel = settings.channel
    p.application_data = settings.application_data
    p.max_participants = settings.max_participants
    p.password = cfg.password
    p.name = cfg.nickname.encode()[:32]
    return p
