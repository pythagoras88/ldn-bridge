"""CLI: python -m ldn_bridge <command>. Run on the Steam Deck (see scripts/deck.sh)."""
from __future__ import annotations

import argparse
import logging
import socket
import sys
import time
from pathlib import Path

from . import config as config_mod
from . import mitm_proto as mp
from .config import PROJECT_ROOT

log = logging.getLogger(__name__)

HOST_TEST_STATUS_SECONDS = 15


def setup_logging(name: str, verbose: bool) -> None:
    logs = PROJECT_ROOT / "logs"
    logs.mkdir(exist_ok=True)
    fmt = "%(asctime)s %(levelname)s %(name)s: %(message)s"
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO, format=fmt, handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(logs / f"{name}-{time.strftime('%Y%m%d-%H%M%S')}.log"),
    ])


# ---------------------------------------------------------------- commands needing the ldn library

def cmd_keys_check(cfg, args):
    from . import ldn_side
    keys = ldn_side.load_keys(cfg)
    print(f"Loaded {len(keys)} keys from {cfg.keys_path} (values not shown).")
    for proto, missing in ldn_side.key_report(keys).items():
        label = "Switch 1 games" if proto == 1 else "newer protocol"
        print(f"protocol {proto} ({label}): " + ("OK" if not missing else "missing " + ", ".join(missing)))


def cmd_scan(cfg, args):
    import trio
    from . import ldn_side

    async def main():
        keys = ldn_side.load_keys(cfg)
        nets = await ldn_side.scan(cfg, keys)
        dicts = [ldn_side.network_to_dict(n) for n in nets]
        print(f"Found {len(dicts)} matching network(s)")
        for i, d in enumerate(dicts):
            print(f"\n[{i}]")
            for k, v in d.items():
                if k != "application_data_hex":
                    print(f"  {k}: {v}")
            print(f"  application_data: {len(d['application_data_hex']) // 2} bytes")
        if dicts:
            print(f"\nSaved {ldn_side.save_capture('scan', dicts)}")
    trio.run(main)


def cmd_join(cfg, args):
    import ldn
    import trio
    from . import bridge, ldn_side

    async def main():
        keys = ldn_side.load_keys(cfg)
        net = await bridge.pick_network(cfg, keys, args.index)
        if net is None:
            return
        try:
            async with ldn.connect(ldn_side.connect_param(cfg, keys, net)) as sta:
                me = sta.participant()
                print(f"Joined as {me.ip_address}. Broadcast {sta.broadcast_address()}. Ctrl-C to leave.")
                while True:
                    ev = await sta.next_event()
                    print(f"event: {ev!r}")
                    if isinstance(ev, ldn.DisconnectEvent):
                        break
        except ldn.AuthenticationError as e:
            print(f"Authentication failed: {e}. If this persists, the game probably uses a passphrase: "
                  "see milestone M2b in docs/MILESTONES.md.")
    trio.run(main)


def load_host_settings(cfg, args):
    """The details of the session to host: from --capture if given, else the game's ID in config.toml, else the newest
    scan capture. The emulator supplies the rest each time its game hosts."""
    from . import hosting

    if not cfg.password:
        raise SystemExit("password_hex is empty in config.toml, so the Switch can't authenticate. "
                         "See docs/SETUP.md, section 4.")
    if not args.capture and cfg.local_communication_id is not None:
        settings = hosting.settings_for_game(cfg.local_communication_id, cfg.protocols[0])
        print(f"Hosting for game id 0x{settings.local_communication_id:016x} from config.toml, channel "
              f"{settings.channel}.")
        return settings
    try:
        path = Path(args.capture) if args.capture else hosting.latest_capture(PROJECT_ROOT / "captures")
    except SystemExit:
        raise SystemExit("Set local_communication_id under [game] in config.toml to the game's ID, which `scan` shows "
                         "while a Switch hosts the game.") from None
    scene = cfg.scene_id if getattr(args, "scene", None) is None else args.scene
    settings = hosting.settings_from_capture(hosting.pick_session(hosting.load_sessions(path), scene, args.index))
    print(f"Using {path.name}: id 0x{settings.local_communication_id:016x}, scene {settings.scene_id}, "
          f"app version {settings.app_version}, channel {settings.channel}, up to {settings.max_participants} players, "
          f"{len(settings.application_data)} bytes of session data.")
    return settings


def cmd_host_test(cfg, args):
    """Host a copy of a captured session, with no emulator, to see if the adapter can host and the Switch can join."""
    import ldn
    import trio
    from . import adapter, hosting, ldn_side

    settings = load_host_settings(cfg, args)
    joins = 0

    async def main():
        nonlocal joins
        keys = ldn_side.load_keys(cfg)
        if cfg.adapter_mac:
            cfg.phyname = adapter.prepare(cfg.adapter_mac)
        async with ldn.create_network(ldn_side.create_param(cfg, keys, settings)) as ap:
            print(f"Hosting on {cfg.phyname} for {args.seconds:g} s. Ctrl-C stops it sooner. "
                  "Search for the session from the same mode on the Switch.")
            with trio.move_on_after(args.seconds):
                while True:
                    with trio.move_on_after(HOST_TEST_STATUS_SECONDS) as wait:
                        ev = await ap.next_event()
                    if wait.cancelled_caught:
                        print(f"Still hosting: {ap.info().num_participants - 1} joined.")
                    elif isinstance(ev, ldn.JoinEvent):
                        joins += 1
                        log.info("Joined: node %d at %s", ev.index, ev.participant.ip_address)
                    elif isinstance(ev, ldn.LeaveEvent):
                        log.info("Left: node %d", ev.index)

    hosting.run_session(lambda: trio.run(main))
    if joins:
        print(f"RESULT: joined {joins} time(s). The adapter can host.")
    else:
        print("RESULT: nothing joined.")


def cmd_bridge(cfg, args):
    import trio
    from . import bridge, hosting, ldn_side

    mode = args.mode or config_mod.MODES[cfg.mode]
    if mode == "emulator-hosts":
        settings = load_host_settings(cfg, args)

        async def host():
            await bridge.emulator_hosts(cfg, ldn_side.load_keys(cfg), settings)
        hosting.run_session(lambda: trio.run(host))
        return

    async def main():
        keys = ldn_side.load_keys(cfg)
        await bridge.switch_hosts(cfg, keys, args.index, wait_enter=not args.no_wait, windows=args.windows)
    trio.run(main)


# ---------------------------------------------------------------- ldn_mitm tools (no ldn library needed)

def cmd_mitm_scan(cfg, args):
    """Act as an ldn_mitm client: broadcast Scan, print every ScanResp (e.g. from the emulator hosting)."""
    from .captures import save_capture

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    s.bind((args.bind, 0))
    s.settimeout(0.3)
    s.sendto(mp.encode_packet(mp.PacketType.SCAN), (args.broadcast, cfg.mitm_port))
    print(f"Sent Scan to {args.broadcast}:{cfg.mitm_port}, listening {args.wait}s...")
    results, deadline = [], time.time() + args.wait
    while time.time() < deadline:
        try:
            data, addr = s.recvfrom(8192)
        except socket.timeout:
            continue
        try:
            pkt = mp.decode_packet(data)
        except mp.ProtocolError as e:
            print(f"{addr}: undecodable ({e}); raw {data[:32].hex()}...")
            continue
        if pkt and pkt[0] == mp.PacketType.SCAN_RESP:
            info = mp.NetworkInfo.unpack(pkt[1])
            print(f"\nScanResp from {addr}:\n{info.describe()}")
            results.append({"from": f"{addr[0]}:{addr[1]}", "raw_hex": data.hex(), "describe": info.describe()})
    if results:
        print(f"\nSaved {save_capture('mitm-scan', results)}")
    else:
        print("No ScanResp received.")


def cmd_mitm_fake_host(cfg, args):
    """Pretend to be an ldn_mitm host on an interface, so the emulator's join list shows a fake session."""
    import trio
    from .control_plane import ControlPlane
    from .netutil import iface_ipv4, iface_mac

    if args.ip and args.broadcast:
        ip, bcast = args.ip, args.broadcast
    elif args.iface:
        ip, bcast = iface_ipv4(args.iface)
    else:
        raise SystemExit("give --iface, or both --ip and --broadcast")
    mac = iface_mac(args.iface) if args.iface else b"\x02\x00\x00\x00\x00\x01"
    info = mp.NetworkInfo(
        local_communication_id=cfg.local_communication_id or 0x0100A3D008C5C000,
        scene_id=cfg.scene_id or 0,
        session_id=bytes(range(16)),
        bssid=mac,
        ssid=bytes(range(16)).hex().encode(),
        channel=6,
        node_count_max=8,
        node_count=1,
    )
    info.nodes[0] = mp.NodeInfo(ip=ip, mac=mac, node_id=0, is_connected=True,
                                user_name=b"BridgeFakeHost", local_communication_version=0)

    async def main():
        cp = ControlPlane(ip, bcast, cfg.mitm_port, scan_info=lambda: info, sync_info=lambda: info)
        print(f"Fake ldn_mitm host on {args.iface or ip} ({ip}, broadcast {bcast}). Ctrl-C to stop.")
        await cp.run()
    trio.run(main)


def cmd_traffic(cfg, args):
    """Count the protocols of all traffic on the adapter's interface (counts only, no addresses or payloads)."""
    if sys.platform != "linux":
        raise SystemExit("traffic runs on Linux only")
    import select
    from .netutil import iface_ipv4
    from .traffic_stats import TrafficStats

    _, bcast = iface_ipv4(cfg.ifname)
    stats = TrafficStats(bcast)
    sock = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(0x0003))  # ETH_P_ALL
    sock.bind((cfg.ifname, 0))
    print(f"Counting traffic on {cfg.ifname}. Ctrl-C to stop.")
    last = time.monotonic()
    try:
        with sock:  # outgoing frames (from the bridge itself) are counted too
            while True:
                if select.select([sock], [], [], 1.0)[0]:
                    stats.add(sock.recv(65536))
                if time.monotonic() - last >= 10:
                    last = time.monotonic()
                    print(stats.summary(), flush=True)
    except KeyboardInterrupt:
        pass
    print("Final:", stats.summary())


def main(argv=None):
    ap = argparse.ArgumentParser(prog="ldn_bridge")
    ap.add_argument("--config", help="path to config.toml")
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("keys-check", help="check prod.keys has the needed key names (values never shown)")
    sub.add_parser("scan", help="scan for real LDN networks (M1)")
    p = sub.add_parser("join", help="join a real LDN network and print events (M2)")
    p.add_argument("--index", type=int)
    p = sub.add_parser("host-test", help="host a captured session to see if the Switch can join (M6a)")
    p.add_argument("--capture", help="scan capture to copy (default: the newest in captures/)")
    p.add_argument("--scene", type=int, help="use the capture's session with this scene")
    p.add_argument("--index", type=int, help="which session, if several match")
    p.add_argument("--seconds", type=float, default=300, help="stop after this long (default: 300)")
    p = sub.add_parser("bridge", help="run the bridge (M4+)")
    p.add_argument("mode", nargs="?", choices=["switch-hosts", "emulator-hosts"],
                   help="default: [launch] mode in config.toml (host = emulator-hosts, join = switch-hosts)")
    p.add_argument("--index", type=int)
    p.add_argument("--no-wait", action="store_true", help="join without waiting for Enter")
    p.add_argument("--windows", action="store_true",
                   help="switch-hosts: the emulator runs on Windows, linked by windows/ldn_tunnel.py (docs/WSL.md)")
    p.add_argument("--capture", help="emulator-hosts: scan capture to copy (default: the newest in captures/)")
    p.add_argument("--scene", type=int, help="emulator-hosts: use the capture's session with this scene")
    p = sub.add_parser("mitm-scan", help="send an ldn_mitm Scan and decode replies (M3)")
    p.add_argument("--broadcast", required=True, help="broadcast address, e.g. 192.168.1.255")
    p.add_argument("--bind", default="0.0.0.0")
    p.add_argument("--wait", type=float, default=2.0)
    p = sub.add_parser("mitm-fake-host", help="advertise a fake ldn_mitm session (M3b)")
    p.add_argument("--iface", help="interface to advertise on (reads its IP, broadcast and MAC)")
    p.add_argument("--ip", help="override IP (with --broadcast), e.g. for loopback tests")
    p.add_argument("--broadcast")

    sub.add_parser("traffic", help="count TCP, UDP, fragments and multicast on the adapter's interface")

    args = ap.parse_args(argv)
    setup_logging(args.cmd, args.verbose)
    cfg = config_mod.load(args.config)
    {
        "keys-check": cmd_keys_check, "scan": cmd_scan, "join": cmd_join, "host-test": cmd_host_test,
        "bridge": cmd_bridge, "mitm-scan": cmd_mitm_scan, "mitm-fake-host": cmd_mitm_fake_host,
        "traffic": cmd_traffic,
    }[args.cmd](cfg, args)


if __name__ == "__main__":
    main()
