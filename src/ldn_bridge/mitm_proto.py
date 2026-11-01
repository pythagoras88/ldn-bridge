"""ldn_mitm LAN protocol codec. Pure Python: no trio, no ldn imports, so it can be unit-tested on Windows.

Layouts are reconstructed from ldn_mitm / Ryujinx sources. See docs/LDN_MITM_PROTOCOL.md and verify with captures.
"""
from __future__ import annotations

import ipaddress
import struct
from dataclasses import dataclass, field
from enum import IntEnum

MAGIC = 0x11451400
PORT = 11452

HEADER = struct.Struct("<IBBHH2x")  # magic, type, compressed, length, decompress_length, reserved[2]
HEADER_SIZE = HEADER.size  # 12

NODE_INFO_SIZE = 0x40
NETWORK_INFO_SIZE = 0x480
MAX_NODES = 8
ADVERTISE_DATA_MAX = 384

NETWORK_TYPE_LDN = 2


class PacketType(IntEnum):
    SCAN = 0
    SCAN_RESP = 1
    CONNECT = 2
    SYNC_NETWORK = 3


class ProtocolError(Exception):
    pass


# ---------------------------------------------------------------- compression

def compress(data: bytes) -> bytes:
    """Zero run-length encoding: 0x00 followed by the count of *additional* zeros (max 255)."""
    out = bytearray()
    i, n = 0, len(data)
    while i < n:
        b = data[i]
        i += 1
        if b == 0:
            count = 0
            while i < n and data[i] == 0 and count < 0xFF:
                count += 1
                i += 1
            out += bytes((0, count))
        else:
            out.append(b)
    return bytes(out)


def decompress(data: bytes, expected_size: int | None = None) -> bytes:
    out = bytearray()
    i, n = 0, len(data)
    while i < n:
        b = data[i]
        i += 1
        out.append(b)
        if b == 0:
            if i >= n:
                raise ProtocolError("truncated zero run")
            out += bytes(data[i])
            i += 1
    if expected_size is not None and len(out) != expected_size:
        raise ProtocolError(f"decompressed {len(out)} bytes, expected {expected_size}")
    return bytes(out)


# ---------------------------------------------------------------- packets

def encode_packet(ptype: PacketType, payload: bytes = b"") -> bytes:
    body, compressed = payload, 0
    if payload:
        packed = compress(payload)
        if len(packed) < len(payload):
            body, compressed = packed, 1
    return HEADER.pack(MAGIC, int(ptype), compressed, len(body), len(payload)) + body


@dataclass
class Header:
    type: PacketType
    compressed: bool
    length: int
    decompress_length: int


def decode_header(buf: bytes) -> Header:
    if len(buf) < HEADER_SIZE:
        raise ProtocolError("short header")
    magic, ptype, compressed, length, dlen = HEADER.unpack_from(buf)
    if magic != MAGIC:
        raise ProtocolError(f"bad magic 0x{magic:08x}")
    try:
        t = PacketType(ptype)
    except ValueError:
        raise ProtocolError(f"unknown packet type {ptype}") from None
    return Header(t, bool(compressed), length, dlen)


def decode_packet(buf: bytes) -> tuple[PacketType, bytes, int] | None:
    """Decode one packet from the start of buf. Returns (type, payload, bytes_consumed),
    or None if buf doesn't hold a whole packet yet (TCP framing)."""
    if len(buf) < HEADER_SIZE:
        return None
    h = decode_header(buf)
    end = HEADER_SIZE + h.length
    if len(buf) < end:
        return None
    body = bytes(buf[HEADER_SIZE:end])
    payload = decompress(body, h.decompress_length) if h.compressed else body
    return h.type, payload, end


# ---------------------------------------------------------------- structs

def _ip_to_u32(ip: str) -> int:
    return int(ipaddress.IPv4Address(ip))


def _u32_to_ip(v: int) -> str:
    return str(ipaddress.IPv4Address(v))


def _cstr(raw: bytes) -> bytes:
    return raw.split(b"\0", 1)[0]


_NODE = struct.Struct("<I6sbb33sxH16x")
assert _NODE.size == NODE_INFO_SIZE


@dataclass
class NodeInfo:
    ip: str = "0.0.0.0"
    mac: bytes = bytes(6)
    node_id: int = 0
    is_connected: bool = False
    user_name: bytes = b""
    local_communication_version: int = 0

    def pack(self) -> bytes:
        return _NODE.pack(
            _ip_to_u32(self.ip), bytes(self.mac)[:6].ljust(6, b"\0"), self.node_id,
            1 if self.is_connected else 0, self.user_name[:32], self.local_communication_version,
        )

    @classmethod
    def unpack(cls, data: bytes) -> "NodeInfo":
        if len(data) < NODE_INFO_SIZE:
            raise ProtocolError(f"NodeInfo needs {NODE_INFO_SIZE} bytes, got {len(data)}")
        ip, mac, nid, conn, name, ver = _NODE.unpack_from(data)
        return cls(_u32_to_ip(ip), mac, nid, bool(conn), _cstr(name), ver)


_NET_ID = struct.Struct("<Q2xH4x16s")          # IntentId + SessionId = 0x20
_COMMON = struct.Struct("<6sB33shbB4x")       # CommonNetworkInfo = 0x30
_LDN_HEAD = struct.Struct("<16sHB3xBB")       # first 0x18 bytes of LdnNetworkInfo
_LDN_TAIL = struct.Struct("<2xH384s140xQ")    # after nodes
assert _NET_ID.size + _COMMON.size + _LDN_HEAD.size + NODE_INFO_SIZE * MAX_NODES + _LDN_TAIL.size == NETWORK_INFO_SIZE


@dataclass
class NetworkInfo:
    local_communication_id: int = 0
    scene_id: int = 0
    session_id: bytes = bytes(16)
    bssid: bytes = bytes(6)
    ssid: bytes = b""                      # up to 32 ASCII chars (hex of the 16-byte LDN SSID)
    channel: int = 0
    link_level: int = 3
    network_type: int = NETWORK_TYPE_LDN
    security_parameter: bytes = bytes(16)  # server_random
    security_mode: int = 1
    station_accept_policy: int = 0
    node_count_max: int = 8
    node_count: int = 0
    nodes: list[NodeInfo] = field(default_factory=lambda: [NodeInfo() for _ in range(MAX_NODES)])
    advertise_data: bytes = b""
    authentication_id: int = 0

    def pack(self) -> bytes:
        if len(self.advertise_data) > ADVERTISE_DATA_MAX:
            raise ProtocolError("advertise_data longer than 384 bytes")
        nodes = (list(self.nodes) + [NodeInfo() for _ in range(MAX_NODES)])[:MAX_NODES]
        ssid = self.ssid[:32]
        out = bytearray()
        out += _NET_ID.pack(self.local_communication_id, self.scene_id, bytes(self.session_id)[:16].ljust(16, b"\0"))
        out += _COMMON.pack(bytes(self.bssid)[:6].ljust(6, b"\0"), len(ssid), ssid, self.channel,
                            self.link_level, self.network_type)
        out += _LDN_HEAD.pack(bytes(self.security_parameter)[:16].ljust(16, b"\0"), self.security_mode,
                              self.station_accept_policy, self.node_count_max, self.node_count)
        for n in nodes:
            out += n.pack()
        out += _LDN_TAIL.pack(len(self.advertise_data), self.advertise_data, self.authentication_id)
        assert len(out) == NETWORK_INFO_SIZE
        return bytes(out)

    @classmethod
    def unpack(cls, data: bytes) -> "NetworkInfo":
        if len(data) < NETWORK_INFO_SIZE:
            raise ProtocolError(f"NetworkInfo needs {NETWORK_INFO_SIZE} bytes, got {len(data)}")
        off = 0
        lcid, scene, session = _NET_ID.unpack_from(data, off); off += _NET_ID.size
        bssid, ssid_len, ssid, channel, link, ntype = _COMMON.unpack_from(data, off); off += _COMMON.size
        sp, smode, policy, nmax, ncount = _LDN_HEAD.unpack_from(data, off); off += _LDN_HEAD.size
        nodes = []
        for _ in range(MAX_NODES):
            nodes.append(NodeInfo.unpack(data[off:off + NODE_INFO_SIZE])); off += NODE_INFO_SIZE
        adv_size, adv, auth = _LDN_TAIL.unpack_from(data, off)
        return cls(lcid, scene, session, bssid, ssid[:min(ssid_len, 32)], channel, link, ntype, sp, smode,
                   policy, nmax, ncount, nodes, adv[:min(adv_size, ADVERTISE_DATA_MAX)], auth)

    def describe(self) -> str:
        lines = [
            f"local_communication_id=0x{self.local_communication_id:016x} scene_id={self.scene_id}",
            f"ssid={self.ssid.decode(errors='replace')} channel={self.channel} bssid={self.bssid.hex(':')}",
            f"nodes {self.node_count}/{self.node_count_max} accept_policy={self.station_accept_policy} "
            f"security_mode={self.security_mode} advertise_data={len(self.advertise_data)} bytes",
        ]
        for n in self.nodes:
            if n.is_connected:
                lines.append(f"  node {n.node_id}: {n.ip} {n.mac.hex(':')} "
                             f"'{n.user_name.decode(errors='replace')}' v{n.local_communication_version}")
        return "\n".join(lines)
