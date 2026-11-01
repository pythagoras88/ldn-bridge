from __future__ import annotations

import ipaddress
import json
import subprocess
from pathlib import Path


def iface_ipv4(ifname: str) -> tuple[str, str]:
    """Return (ip, broadcast) of an interface's first IPv4 address."""
    out = subprocess.run(["ip", "-j", "-4", "addr", "show", "dev", ifname],
                         check=True, capture_output=True, text=True).stdout
    for link in json.loads(out or "[]"):
        for a in link.get("addr_info", []):
            ip = a["local"]
            bcast = a.get("broadcast") or str(
                ipaddress.IPv4Network(f"{ip}/{a['prefixlen']}", strict=False).broadcast_address)
            return ip, bcast
    raise SystemExit(f"Interface {ifname} has no IPv4 address")


def iface_mac(ifname: str) -> bytes:
    return bytes.fromhex(Path(f"/sys/class/net/{ifname}/address").read_text().strip().replace(":", ""))
