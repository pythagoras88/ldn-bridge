"""Framing between the bridge in WSL and the Windows helper (windows/ldn_tunnel.py). Pure Python, unit-tested.

Each message is a 1-byte type, a 2-byte big-endian length, then the payload. The Windows helper keeps its own copy of
this, since it runs from Windows without the package installed: keep the two the same.
"""
from __future__ import annotations

import socket
import struct

CONFIG = 1  # bridge -> helper: 4-byte IPv4 address, 1-byte prefix length. Set the adapter to this address.
PACKET = 2  # either way: one IPv4 packet
HEADER = struct.Struct("!BH")
DEFAULT_PORT = 11453


def encode(kind: int, payload: bytes) -> bytes:
    return HEADER.pack(kind, len(payload)) + payload


def config(ip: str, prefix: int) -> bytes:
    return encode(CONFIG, socket.inet_aton(ip) + bytes([prefix]))


def parse_config(payload: bytes) -> tuple[str, int]:
    return socket.inet_ntoa(payload[:4]), payload[4]


class Decoder:
    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, data: bytes) -> list[tuple[int, bytes]]:
        self._buf += data
        out = []
        while len(self._buf) >= HEADER.size:
            kind, length = HEADER.unpack_from(self._buf)
            if len(self._buf) < HEADER.size + length:
                break
            out.append((kind, bytes(self._buf[HEADER.size:HEADER.size + length])))
            del self._buf[:HEADER.size + length]
        return out
