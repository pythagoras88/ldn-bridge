"""Bridge orchestration. See docs/DESIGN.md.

switch_hosts ("join" mode): the Switch hosts and the emulator joins (docs/MILESTONES.md, M5).
emulator_hosts ("host" mode, the default): the emulator hosts and the Switch joins, including turn-based searches like
Link Trade (M6).
"""
from __future__ import annotations

import logging
import socket
from dataclasses import replace

import ldn
import trio

from . import adapter, convert, emulator_link, ldn_side
from .config import Config
from .control_plane import ControlPlane
from .hosting import BroadcastWatch, EmulatorSession, HostSettings, HostTracker

log = logging.getLogger(__name__)

# How often to ask the emulator whether it's hosting. Turn-based searches like Link Trade host for about 3 s at a time,
# so the session has to open and close within a fraction of that (docs/MILESTONES.md, M6). The emulator answers over
# loopback in milliseconds.
SCAN_SECONDS = 0.25
POLL_SECONDS = 0.2
# Unanswered scans in a row before the session closes: about 1 s.
SCAN_MISSES_ALLOWED = 2
LINK_LOG_SECONDS = 10.0
# Joins failed at about -88 dBm and worked at -72 dBm (docs/MILESTONES.md, M7).
WEAK_SIGNAL_DBM = -80
# Ryujinx never fills in the security parameter in ldn_mitm mode. Both sides need the same one, as when the Switch hosts.
EMULATOR_SECURITY_PARAMETER = bytes(16)


async def pick_network(cfg: Config, keys, index: int | None, wait: bool = False):
    """wait: keep scanning until a session shows up, for runs with nobody at the keyboard."""
    if wait:
        print("Waiting for the Switch to host a local wireless session...")
        nets = await ldn_side.wait_for_network(cfg, keys)
    else:
        nets = await ldn_side.scan(cfg, keys)
    if not nets:
        print("No matching LDN networks found. Is the Switch hosting? Check channels and game filter in config.toml.")
        return None
    for i, n in enumerate(nets):
        d = ldn_side.network_to_dict(n)
        print(f"[{i}] {d['local_communication_id']} scene={d['scene_id']} ch={d['channel']} "
              f"{d['participants']} host={d['members'][0]['name'] if d['members'] else '?'}")
    if index is None:
        index = 0 if len(nets) == 1 else int(await trio.to_thread.run_sync(input, "Pick network: "))
    return nets[index]


async def log_link(ifname: str) -> None:
    """Log the Switch's signal while joined, so a dropped session shows whether the signal fell first."""
    last = None
    while True:
        try:
            done = await trio.run_process(["iw", "dev", ifname, "station", "dump"], capture_stdout=True,
                                          capture_stderr=True, check=False)
        except OSError:
            return  # no iw on this computer
        quality = adapter.link_quality(done.stdout.decode(errors="replace"))
        if quality and quality != last:
            log.info("link: %s", " ".join(f"{k}={v}" for k, v in quality.items()))
            if quality.get("signal", 0) <= WEAK_SIGNAL_DBM and (last or {}).get("signal", 0) > WEAK_SIGNAL_DBM:
                print(f"Weak signal from the Switch ({quality['signal']} dBm). Move it closer to the adapter.")
            last = quality
        await trio.sleep(LINK_LOG_SECONDS)


async def switch_hosts(cfg: Config, keys, index: int | None = None, wait_enter: bool = True,
                       windows: bool = False) -> None:
    """windows: the emulator runs on Windows and the bridge in WSL, linked by windows/ldn_tunnel.py (docs/WSL.md)."""
    net = await pick_network(cfg, keys, index, wait=not wait_enter)
    if net is None:
        return
    if wait_enter:
        await trio.to_thread.run_sync(
            input, "Keep the emulator out of local multiplayer for now: it picks its network interface when the game "
                   "starts local wireless. Press Enter to join the Switch... ")

    async with ldn.connect(ldn_side.connect_param(cfg, keys, net)) as sta:
        me = sta.participant()
        local_ip, bcast = me.ip_address, sta.broadcast_address()
        if windows:
            print(f"Joined. Bridge IP {local_ip}. Once the Windows helper has set its adapter to that address, open "
                  "local multiplayer on the emulator and search for the session.")
        else:
            print(f"Joined. Bridge IP {local_ip} on interface '{cfg.ifname}'. Now open local multiplayer on the "
                  f"emulator (Network Interface '{cfg.ifname}') and search for the session.")

        cp = ControlPlane(
            local_ip, bcast, cfg.mitm_port,
            # ScanResp: node 0 points at us so the emulator's TCP Connect lands on the bridge. From Windows that's
            # 127.0.0.1, which WSL forwards to its own listeners.
            scan_info=lambda: convert.from_ldn(sta.info(), host_ip_override="127.0.0.1" if windows else local_ip),
            # SyncNetwork: the real member list.
            sync_info=lambda: convert.from_ldn(sta.info()),
            tcp_host="0.0.0.0" if windows else None,
            udp=not windows,
        )
        async with trio.open_nursery() as nursery:
            nursery.start_soon(cp.run)
            nursery.start_soon(log_link, cfg.ifname)
            if windows:
                from .windows_link import WindowsLink

                def node_macs() -> dict[str, bytes]:
                    return {p.ip_address: convert.mac_bytes(p.mac_address)
                            for p in sta.info().participants if p.connected}

                link = WindowsLink(cfg.ifname, local_ip, bcast, cfg.mitm_port,
                                   host_ip=lambda: sta.info().participants[0].ip_address,
                                   node_macs=node_macs, scan_response=cp.scan_response)
                nursery.start_soon(link.run)
            while True:
                ev = await sta.next_event()
                log.info("LDN event: %r", ev)
                if isinstance(ev, ldn.DisconnectEvent):
                    print(f"Disconnected from the Switch (reason {ev.reason}).")
                    nursery.cancel_scope.cancel()
                    break
                await cp.push_sync()


def publish(ap, session: EmulatorSession | None) -> None:
    """Show the emulator's session over the air, or close ours while it isn't hosting."""
    if session is None:
        ap.set_application_data(b"")
        ap.set_accept_policy(ldn.ACCEPT_NONE)
        return
    ldn_side.set_session_id(ap, session.session_id)
    # The game mode, e.g. Union Circle or a Tera Raid. The Switch's search skips sessions of another scene.
    ap.info().scene_id = session.scene_id
    # How many players the mode takes, e.g. 2 for Link Trade and 4 for Union Circle. The Switch's search may skip a
    # session that doesn't match.
    ap.info().max_participants = session.max_participants
    ap.participant().name = session.name
    ap.participant().app_version = session.app_version
    ap.set_application_data(session.advertise_data)
    ap.set_accept_policy(ldn.ACCEPT_ALL)


def describe_session(session: EmulatorSession, settings: HostSettings) -> None:
    print(f"The emulator is hosting (scene {session.scene_id}). Search from the Switch with the code on the emulator's "
          "screen, if the game has one.")
    if settings.app_version and session.app_version != settings.app_version:
        print(f"The emulator's game is version {session.app_version}, but the capture's is {settings.app_version}. "
              "Both sides need the same update.")


def wake_tap(ip: str) -> None:
    """The library reads the emulator's interface in a thread that can't be cancelled, so stopping waits until one
    more packet crosses it. Send that packet."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.bind((ip, 0))
            s.sendto(b"", (ip.rsplit(".", 1)[0] + ".255", 9))
    except OSError as e:
        log.debug("couldn't wake the interface: %s", e)


def unreadable_broadcasts() -> None:
    log.warning("Most of the stations' broadcast frames can't be read")
    print("The Switch's game traffic can't be read, so it will wait on \"searching\". A key left in the adapter from an "
          "earlier session causes this. Stop the bridge, unplug the adapter, plug it back in and start again.")


async def emulator_hosts(cfg: Config, keys, settings: HostSettings) -> None:
    """Phase 2 (docs/DESIGN.md). The session opens only while the emulator hosts, with the emulator's own data."""
    if cfg.adapter_mac:
        print("Resetting the adapter...")
        if not await trio.to_thread.run_sync(adapter.reset, cfg.adapter_mac):
            print("Couldn't reset the adapter, because this user can't write to its USB device. Run "
                  "`sudo bash deck/usb_access.sh` once to allow it. Until then, if the Switch stays on \"searching\", "
                  "unplug the adapter and plug it back in.")
        cfg.phyname = adapter.prepare(cfg.adapter_mac)
    # The capture's application data belongs to an old session, and a game could find it by that session's code.
    param = ldn_side.create_param(cfg, keys, replace(settings, application_data=b""))
    param.server_random = EMULATOR_SECURITY_PARAMETER
    ldn_side.broadcast_watch = BroadcastWatch(unreadable_broadcasts)
    async with ldn.create_network(param) as ap:
        ip = ap.participant().ip_address
        ap.set_accept_policy(ldn.ACCEPT_NONE)
        print(f"Bridge ready on '{cfg.ifname}' at {ip}. Open the game on the emulator (Network Interface "
              f"'{cfg.ifname}') and host a local session.")
        links: dict[int, trio.CancelScope] = {}

        async def watch_emulator() -> None:
            tracker = HostTracker(misses_allowed=SCAN_MISSES_ALLOWED)
            while True:
                info = await emulator_link.scan(ip, cfg.mitm_port, SCAN_SECONDS)
                if tracker.update(info):
                    publish(ap, tracker.session)
                    s = tracker.session
                    log.info("published: %s", "nothing" if s is None else
                             f"scene {s.scene_id}, up to {s.max_participants} players, session {s.session_id.hex()[:8]}, "
                             f"{len(s.advertise_data)} bytes")
                    if tracker.session is None:
                        print("The emulator stopped hosting.")
                    else:
                        describe_session(tracker.session, settings)
                await trio.sleep(POLL_SECONDS)

        async def link_station(index: int, participant) -> None:
            with trio.CancelScope() as scope:
                links[index] = scope
                try:
                    await emulator_link.hold_station(ip, cfg.mitm_port, convert.node_from_participant(index, participant))
                except (OSError, trio.BrokenResourceError) as e:
                    log.warning("Lost the emulator connection for node %d: %s", index, e)
                print(f"The emulator dropped node {index}.")
                await ap.kick(index)

        try:
            async with trio.open_nursery() as nursery:
                nursery.start_soon(watch_emulator)
                while True:
                    ev = await ap.next_event()
                    if isinstance(ev, ldn.JoinEvent):
                        print(f"The Switch joined as node {ev.index} at {ev.participant.ip_address}.")
                        nursery.start_soon(link_station, ev.index, ev.participant)
                    elif isinstance(ev, ldn.LeaveEvent):
                        print(f"Node {ev.index} left.")
                        scope = links.pop(ev.index, None)
                        if scope:
                            scope.cancel()
        finally:
            wake_tap(ip)
