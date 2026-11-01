"""Bridge orchestration. See docs/DESIGN.md.

Phase 1 (switch_hosts): working on hardware (docs/MILESTONES.md, M5).
Phase 2 (emulator_hosts): stub.
"""
from __future__ import annotations

import logging

import ldn
import trio

from . import convert, ldn_side
from .config import Config
from .control_plane import ControlPlane

log = logging.getLogger(__name__)


async def pick_network(cfg: Config, keys, index: int | None):
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


async def switch_hosts(cfg: Config, keys, index: int | None = None, wait_enter: bool = True) -> None:
    net = await pick_network(cfg, keys, index)
    if net is None:
        return
    if wait_enter:
        await trio.to_thread.run_sync(
            input, "Keep the emulator out of local multiplayer for now: it picks its network interface when the game "
                   "starts local wireless. Press Enter to join the Switch... ")

    async with ldn.connect(ldn_side.connect_param(cfg, keys, net)) as sta:
        me = sta.participant()
        local_ip, bcast = me.ip_address, sta.broadcast_address()
        print(f"Joined. Bridge IP {local_ip} on interface '{cfg.ifname}'. "
              f"Now open local multiplayer on the emulator (Network Interface '{cfg.ifname}') and search for the session.")

        cp = ControlPlane(
            local_ip, bcast, cfg.mitm_port,
            # ScanResp: node 0 points at us so the emulator's TCP Connect lands on the bridge.
            scan_info=lambda: convert.from_ldn(sta.info(), host_ip_override=local_ip),
            # SyncNetwork: the real member list.
            sync_info=lambda: convert.from_ldn(sta.info()),
        )
        async with trio.open_nursery() as nursery:
            nursery.start_soon(cp.run)
            while True:
                ev = await sta.next_event()
                log.info("LDN event: %r", ev)
                if isinstance(ev, ldn.DisconnectEvent):
                    print(f"Disconnected from the Switch (reason {ev.reason}).")
                    nursery.cancel_scope.cancel()
                    break
                await cp.push_sync()


async def emulator_hosts(cfg: Config, keys) -> None:
    """Phase 2 (M6). Outline:
    1. ldn_side.create_param(...) with the game's ids/app_version from config + captures (M1/M3).
    2. async with ldn.create_network(param) as ap: TAP 'ldn-tap' gets 169.254.N.1.
    3. Tell the user to bind the emulator to 'ldn-tap' and host.
    4. Poll the emulator with an ldn_mitm Scan; copy advertise_data into ap.set_application_data().
    5. On JoinEvent: open TCP to emulator:11452, send Connect with the Switch's NodeInfo
       (participant ip/mac/name/app_version); relay SyncNetwork; on LeaveEvent close it.
    """
    raise NotImplementedError("Emulator-hosts mode is milestone M6; see the docstring and docs/DESIGN.md")
