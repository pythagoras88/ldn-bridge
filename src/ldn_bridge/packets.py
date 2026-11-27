"""Small Ethernet, ARP and IPv4 helpers for relaying an emulator's traffic (docs/WSL.md). Pure Python, unit-tested."""
from __future__ import annotations

import socket
import struct
from dataclasses import dataclass

ETH_P_IP = 0x0800
ETH_P_ARP = 0x0806
BROADCAST_MAC = b"\xff" * 6
IPPROTO_UDP = 17
IPPROTO_TCP = 6


def ethernet(dst: bytes, src: bytes, ethertype: int, payload: bytes) -> bytes:
    return dst + src + struct.pack("!H", ethertype) + payload


def parse_ethernet(frame: bytes) -> tuple[bytes, bytes, int, bytes] | None:
    """(dst, src, ethertype, payload), or None if it's too short."""
    if len(frame) < 14:
        return None
    return frame[0:6], frame[6:12], struct.unpack("!H", frame[12:14])[0], frame[14:]


@dataclass
class IPv4:
    src: str
    dst: str
    proto: int
    sport: int | None = None
    dport: int | None = None
    payload: bytes = b""  # the UDP or TCP payload, when there is one


def parse_ipv4(packet: bytes) -> IPv4 | None:
    if len(packet) < 20 or packet[0] >> 4 != 4:
        return None
    ihl = (packet[0] & 0x0F) * 4
    total = struct.unpack("!H", packet[2:4])[0]
    if ihl < 20 or len(packet) < ihl or total < ihl:
        return None
    info = IPv4(socket.inet_ntoa(packet[12:16]), socket.inet_ntoa(packet[16:20]), packet[9])
    fragment = struct.unpack("!H", packet[6:8])[0] & 0x1FFF
    body = packet[ihl:total]
    if info.proto in (IPPROTO_UDP, IPPROTO_TCP) and fragment == 0 and len(body) >= 4:
        info.sport, info.dport = struct.unpack("!HH", body[:4])
        if info.proto == IPPROTO_UDP and len(body) >= 8:
            info.payload = body[8:]
    return info


def checksum(data: bytes) -> int:
    if len(data) % 2:
        data += b"\x00"
    total = sum(struct.unpack(f"!{len(data) // 2}H", data))
    while total >> 16:
        total = (total & 0xFFFF) + (total >> 16)
    return ~total & 0xFFFF


def udp_ipv4(src: str, sport: int, dst: str, dport: int, payload: bytes, ident: int = 0) -> bytes:
    """A complete IPv4 packet carrying one UDP datagram, with both checksums."""
    s, d = socket.inet_aton(src), socket.inet_aton(dst)
    length = 8 + len(payload)
    pseudo = s + d + struct.pack("!BBH", 0, IPPROTO_UDP, length)
    udp = struct.pack("!HHHH", sport, dport, length, 0) + payload
    udp_sum = checksum(pseudo + udp) or 0xFFFF
    udp = udp[:6] + struct.pack("!H", udp_sum) + udp[8:]
    header = struct.pack("!BBHHHBBH4s4s", 0x45, 0, 20 + length, ident & 0xFFFF, 0, 64, IPPROTO_UDP, 0, s, d)
    header = header[:10] + struct.pack("!H", checksum(header)) + header[12:]
    return header + udp


def arp_reply(request: bytes, my_ip: str, my_mac: bytes) -> bytes | None:
    """The ARP reply payload if `request` asks who has my_ip, else None."""
    if len(request) < 28:
        return None
    htype, ptype, hlen, plen, op = struct.unpack("!HHBBH", request[:8])
    if (htype, ptype, hlen, plen, op) != (1, ETH_P_IP, 6, 4, 1):
        return None
    sender_mac, sender_ip, target_ip = request[8:14], request[14:18], request[24:28]
    if target_ip != socket.inet_aton(my_ip):
        return None
    return struct.pack("!HHBBH", 1, ETH_P_IP, 6, 4, 2) + my_mac + target_ip + sender_mac + sender_ip


def multicast_mac(ip: str) -> bytes:
    b = socket.inet_aton(ip)
    return bytes([0x01, 0x00, 0x5E, b[1] & 0x7F, b[2], b[3]])


def is_multicast(ip: str) -> bool:
    return 224 <= int(ip.split(".")[0]) <= 239
