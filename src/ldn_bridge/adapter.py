"""Find the USB adapter by its permanent MAC. Its phy number and interface name change every time it resets."""
from __future__ import annotations

import logging
import socket
import struct
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


def set_down(ifname: str) -> None:
    import fcntl  # Linux only

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        name = ifname.encode()
        flags = struct.unpack(IFREQ, fcntl.ioctl(s, SIOCGIFFLAGS, struct.pack(IFREQ, name, 0)))[1]
        fcntl.ioctl(s, SIOCSIFFLAGS, struct.pack(IFREQ, name, flags & ~IFF_UP))


def prepare(mac: str) -> str:
    """Return the adapter's current phy, with its interfaces down: a monitor can't change channel otherwise (EBUSY)."""
    phy = find_phy(mac)
    for ifname in interfaces(phy):
        log.info("bringing %s down on %s", ifname, phy)
        set_down(ifname)
    return phy
