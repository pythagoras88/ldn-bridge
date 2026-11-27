"""Counts the protocols in local-play traffic (the `traffic` command). Pure Python, unit-tested; holds counts only."""
from __future__ import annotations

import struct

from . import packets


class TrafficStats:
    def __init__(self, broadcast_ip: str):
        self.broadcast_ip = broadcast_ip
        self._counts = {"udp": 0, "tcp": 0, "other_ip": 0, "fragments": 0, "multicast": 0, "broadcast": 0,
                        "max_udp_payload": 0}

    def add(self, frame: bytes) -> None:
        eth = packets.parse_ethernet(frame)
        if eth is None or eth[2] != packets.ETH_P_IP:
            return
        packet = eth[3]
        ip = packets.parse_ipv4(packet)
        if ip is None:
            return
        c = self._counts
        if ip.proto == packets.IPPROTO_UDP:
            c["udp"] += 1
            c["max_udp_payload"] = max(c["max_udp_payload"], len(ip.payload))
        elif ip.proto == packets.IPPROTO_TCP:
            c["tcp"] += 1
        else:
            c["other_ip"] += 1
        flags_frag = struct.unpack("!H", packet[6:8])[0]
        if flags_frag & 0x2000 or flags_frag & 0x1FFF:  # More Fragments flag, or a non-zero offset
            c["fragments"] += 1
        if packets.is_multicast(ip.dst):
            c["multicast"] += 1
        elif ip.dst == self.broadcast_ip:
            c["broadcast"] += 1

    def summary(self) -> dict[str, int]:
        return dict(self._counts)
