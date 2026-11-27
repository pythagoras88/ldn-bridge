"""ldn_mitm control plane, client side: reads a hosting emulator's session and connects stations to it.

Everything comes from 127.0.0.1. The emulator's IP is also this computer's IP on the LDN interface, and Ryujinx ignores
control traffic from its own IP, over TCP as well as UDP (LanProtocol.Read).
"""
from __future__ import annotations

import logging
import socket

import trio

from . import mitm_proto as mp

log = logging.getLogger(__name__)

LOCAL_SOURCE = ("127.0.0.1", 0)


async def scan(ip: str, port: int, timeout: float) -> mp.NetworkInfo | None:
    """Ask the emulator for its session. Returns None if it isn't hosting."""
    with trio.socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        await sock.bind(LOCAL_SOURCE)
        await sock.sendto(mp.encode_packet(mp.PacketType.SCAN), (ip, port))
        with trio.move_on_after(timeout):
            while True:
                data, _ = await sock.recvfrom(8192)
                try:
                    pkt = mp.decode_packet(data)
                except mp.ProtocolError as e:
                    log.debug("ignoring UDP from the emulator: %s", e)
                    continue
                if pkt and pkt[0] == mp.PacketType.SCAN_RESP:
                    return mp.NetworkInfo.unpack(pkt[1])
    return None


async def hold_station(ip: str, port: int, node: mp.NodeInfo) -> None:
    """Connect a station to the emulator and stay connected. Returns when the emulator hangs up."""
    with trio.socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        await sock.bind(LOCAL_SOURCE)
        await sock.connect((ip, port))
        async with trio.SocketStream(sock) as stream:
            await stream.send_all(mp.encode_packet(mp.PacketType.CONNECT, node.pack()))
            # The emulator's SyncNetwork updates must be read, but nothing here needs them: Scan shows the same session.
            while await stream.receive_some(8192):
                pass
