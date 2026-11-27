"""ldn_mitm control plane, host side: answers Scan over UDP and serves Connect/SyncNetwork over TCP.

Used by both the real bridge and the mitm-fake-host test tool.
"""
from __future__ import annotations

import logging
import socket
from typing import Callable

import trio

from . import mitm_proto as mp

log = logging.getLogger(__name__)


class ControlPlane:
    def __init__(self, local_ip: str, broadcast_ip: str, port: int,
                 scan_info: Callable[[], mp.NetworkInfo],
                 sync_info: Callable[[], mp.NetworkInfo],
                 on_connect: Callable[[mp.NodeInfo], None] | None = None,
                 tcp_host: str | None = None, udp: bool = True):
        """tcp_host: where to listen for Connect (default local_ip). udp=False skips the Scan socket, for when scans
        arrive some other way and are answered with scan_response() (the Windows relay, docs/WSL.md)."""
        self.local_ip = local_ip
        self.tcp_host = tcp_host or local_ip
        self.udp = udp
        self.broadcast_ip = broadcast_ip
        self.port = port
        self.scan_info = scan_info
        self.sync_info = sync_info
        self.on_connect = on_connect
        self._clients: set[trio.SocketStream] = set()

    async def run(self) -> None:
        async with trio.open_nursery() as n:
            if self.udp:
                n.start_soon(self._udp_loop)
            n.start_soon(self._tcp_loop)

    def scan_response(self) -> bytes:
        """The ScanResp packet for a Scan."""
        info = self.scan_info()
        log.info("ScanResp:\n%s", info.describe())
        return mp.encode_packet(mp.PacketType.SCAN_RESP, info.pack())

    # -- UDP: Scan -> ScanResp
    async def _udp_loop(self) -> None:
        rx = trio.socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        rx.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, "SO_REUSEPORT"):
            rx.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        # Bind to the broadcast address only, so unicast replies meant for the emulator's
        # own port-11452 socket aren't stolen by us (see docs/DESIGN.md risks).
        await rx.bind((self.broadcast_ip, self.port))
        tx = trio.socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        await tx.bind((self.local_ip, 0))
        # Ryujinx drops UDP whose source is its own IP, and on the LDN interface that's our IP too.
        # Loopback still delivers locally, with a source it accepts (see docs/LDN_MITM_PROTOCOL.md).
        tx_same_ip = trio.socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        await tx_same_ip.bind(("127.0.0.1", 0))
        log.info("UDP scan responder on %s:%d", self.broadcast_ip, self.port)
        with rx, tx, tx_same_ip:
            while True:
                data, addr = await rx.recvfrom(4096)
                try:
                    pkt = mp.decode_packet(data)
                except mp.ProtocolError as e:
                    log.debug("ignoring UDP from %s: %s", addr, e)
                    continue
                if pkt is None:
                    continue
                ptype, _payload, _ = pkt
                log.info("UDP %s from %s", ptype.name, addr)
                if ptype == mp.PacketType.SCAN:
                    info = self.scan_info()
                    sock = tx_same_ip if addr[0] == self.local_ip else tx
                    await sock.sendto(mp.encode_packet(mp.PacketType.SCAN_RESP, info.pack()), addr)
                    log.info("sent ScanResp to %s:\n%s", addr, info.describe())

    # -- TCP: Connect -> SyncNetwork
    async def _tcp_loop(self) -> None:
        log.info("TCP server on %s:%d", self.tcp_host, self.port)
        await trio.serve_tcp(self._handle, self.port, host=self.tcp_host)

    async def _handle(self, stream: trio.SocketStream) -> None:
        peer = stream.socket.getpeername()
        log.info("TCP client %s connected", peer)
        buf = bytearray()
        self._clients.add(stream)
        try:
            while True:
                chunk = await stream.receive_some(8192)
                if not chunk:
                    break
                buf += chunk
                while True:
                    pkt = mp.decode_packet(buf)
                    if pkt is None:
                        break
                    ptype, payload, used = pkt
                    del buf[:used]
                    await self._on_tcp_packet(stream, ptype, payload)
        except (trio.BrokenResourceError, trio.ClosedResourceError, mp.ProtocolError) as e:
            log.warning("TCP client %s error: %s", peer, e)
        finally:
            self._clients.discard(stream)
            log.info("TCP client %s gone", peer)

    async def _on_tcp_packet(self, stream, ptype: mp.PacketType, payload: bytes) -> None:
        if ptype == mp.PacketType.CONNECT:
            node = mp.NodeInfo.unpack(payload)
            log.info("Connect from emulator: ip=%s mac=%s name=%r ver=%d", node.ip, node.mac.hex(":"),
                     node.user_name, node.local_communication_version)
            if node.ip != self.local_ip:
                log.warning("Emulator node IP %s != bridge IP %s. Is the emulator's Network Interface set "
                            "to the LDN interface?", node.ip, self.local_ip)
            if self.on_connect:
                self.on_connect(node)
            await self._send_sync(stream)
        else:
            log.info("TCP %s (%d bytes) ignored", ptype.name, len(payload))

    async def _send_sync(self, stream) -> None:
        info = self.sync_info()
        await stream.send_all(mp.encode_packet(mp.PacketType.SYNC_NETWORK, info.pack()))
        log.info("sent SyncNetwork:\n%s", info.describe())

    async def push_sync(self) -> None:
        for s in list(self._clients):
            try:
                await self._send_sync(s)
            except (trio.BrokenResourceError, trio.ClosedResourceError):
                self._clients.discard(s)
