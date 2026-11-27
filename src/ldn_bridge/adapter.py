"""Find the USB adapter by its permanent MAC. Its phy number and interface name change every time it resets."""
from __future__ import annotations

import logging
import os
import socket
import struct
import time
from collections.abc import Callable
from pathlib import Path

log = logging.getLogger(__name__)

SYS_WIPHY = Path("/sys/class/ieee80211")
SIOCGIFFLAGS = 0x8913
SIOCSIFFLAGS = 0x8914
IFF_UP = 0x1
IFREQ = "16sh14x"


def find_phy(mac: str, root: Path = SYS_WIPHY) -> str:
    for phy in sorted(root.iterdir()):
        if (phy / "macaddress").read_text().strip().lower() == mac.lower():
            return phy.name
    raise SystemExit(f"USB adapter {mac} not found. Is it plugged in? deck/find_adapter.sh lists what's there.")


def interfaces(phy: str, root: Path = SYS_WIPHY) -> list[str]:
    net = root / phy / "device" / "net"
    return sorted(p.name for p in net.iterdir()) if net.is_dir() else []


def leftovers(phy: str, names: list[str], root: Path = SYS_WIPHY) -> list[str]:
    """The bridge's own interfaces still on the adapter. A run stopped mid-scan leaves one, and every scan then fails."""
    return [ifname for ifname in interfaces(phy, root) if ifname in names]


LINK_FIELDS = {"signal": "signal", "tx packets": "tx_packets", "tx retries": "tx_retries", "tx failed": "tx_failed",
               "beacon loss": "beacon_loss"}


def link_quality(station_dump: str) -> dict[str, int]:
    """Signal (dBm) and send counters from `iw dev <ifname> station dump`. Empty when no station is connected."""
    out = {}
    for line in station_dump.splitlines():
        name, _, value = line.strip().partition(":")
        if name in LINK_FIELDS and value.split():
            try:
                out[LINK_FIELDS[name]] = int(value.split()[0])
            except ValueError:
                pass
    return out


def set_down(ifname: str) -> None:
    import fcntl  # Linux only

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        name = ifname.encode()
        flags = struct.unpack(IFREQ, fcntl.ioctl(s, SIOCGIFFLAGS, struct.pack(IFREQ, name, 0)))[1]
        fcntl.ioctl(s, SIOCSIFFLAGS, struct.pack(IFREQ, name, flags & ~IFF_UP))


USBDEVFS_RESET = 0x5514  # _IO('U', 20)
RESET_SECONDS = 15.0


def usb_node(interface: Path) -> Path:
    """The /dev/bus/usb node of the USB device whose interface (e.g. .../1-1.4/1-1.4:1.0) the phy belongs to."""
    device = interface.parent
    bus = int((device / "busnum").read_text())
    num = int((device / "devnum").read_text())
    return Path(f"/dev/bus/usb/{bus:03d}/{num:03d}")


def wait_for_return(mac: str, old_phy: str, timeout: float, root: Path = SYS_WIPHY,
                    sleep: Callable[[float], None] = time.sleep,
                    clock: Callable[[], float] = time.monotonic) -> str | None:
    """After a reset, wait for the adapter to come back as a new phy. Returns its phy (the old one if it never
    changed), or None if it's gone."""
    deadline = clock() + timeout
    phy = None
    while True:
        sleep(0.5)
        try:
            phy = find_phy(mac, root)
        except (SystemExit, OSError):  # gone, or a phy vanished while it was being read
            phy = None
        if phy is not None and phy != old_phy:
            return phy
        if clock() >= deadline:
            return phy


def reset(mac: str) -> bool:
    """Reset the adapter over USB, which reloads its firmware like a replug. A session joined with `bridge switch-hosts`
    leaves a key in the MT7612U that garbles the stations' broadcasts when hosting (docs/MILESTONES.md, M6).
    Needs write access to the adapter's USB device: deck/usb_access.sh grants it. Returns False if it couldn't reset."""
    import fcntl  # Linux only

    phy = find_phy(mac)
    node = usb_node((SYS_WIPHY / phy / "device").resolve())
    try:
        fd = os.open(node, os.O_WRONLY)
    except PermissionError:
        log.warning("no write access to %s, so the adapter wasn't reset", node)
        return False
    try:
        log.info("resetting the adapter (%s, %s)", phy, node)
        fcntl.ioctl(fd, USBDEVFS_RESET, 0)
    finally:
        os.close(fd)
    new_phy = wait_for_return(mac, phy, RESET_SECONDS)
    if new_phy is None:
        raise SystemExit(f"USB adapter {mac} didn't come back after a reset. Unplug it and plug it back in.")
    log.info("adapter back as %s", new_phy)
    return True


def prepare(mac: str) -> str:
    """Return the adapter's current phy, with its interfaces down: a monitor can't change channel otherwise (EBUSY)."""
    phy = find_phy(mac)
    for ifname in interfaces(phy):
        log.info("bringing %s down on %s", ifname, phy)
        set_down(ifname)
    return phy
