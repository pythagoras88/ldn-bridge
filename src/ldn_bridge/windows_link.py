"""Relay an emulator running on Windows onto the LDN network, when the bridge runs in WSL (docs/WSL.md, W2). Linux only.

The emulator's traffic arrives as IPv4 packets from windows/ldn_tunnel.py, which gives Windows an adapter with the
bridge's LDN address. This sends them out of the station interface with the bridge's MAC, and passes back what the
Switch sends to that address. The interface's own IPv4 address is removed first, so the Linux kernel doesn't also
answer for it, and this answers ARP for it instead.
"""
from __future__ import annotations

import logging
import socket
import struct
from pathlib import Path
from typing import Callable

import trio

from . import mitm_proto as mp
from . import packets, tunnel_proto

log = logging.getLogger(__name__)

ETH_P_ALL = 0x0003
PACKET_OUTGOING = 4
RTM_DELADDR = 21
IFA_ADDRESS, IFA_LOCAL = 1, 2


async def remove_ipv4(ifname: str, ip: str, prefix: int = 24) -> None:
    from netlink import route  # Linux only

    payload = struct.pack("BBBBI", socket.AF_INET, prefix, 0, 0, socket.if_nametoindex(ifname))
    for kind in (IFA_LOCAL, IFA_ADDRESS):
        addr = socket.inet_aton(ip)
        payload += struct.pack("HH", 8, kind) + addr
    async with route.connect() as router:
        await router.netlink.request(RTM_DELADDR, payload, 0)
    log.info("removed %s from %s, so only the emulator answers for it", ip, ifname)


class WindowsLink:
    def __init__(self, ifname: str, local_ip: str, broadcast_ip: str, mitm_port: int,
                 host_ip: Callable[[], str], node_macs: Callable[[], dict[str, bytes]],
                 scan_response: Callable[[], bytes], port: int = tunnel_proto.DEFAULT_PORT):
        self.ifname = ifname
        self.local_ip = local_ip
        self.broadcast_ip = broadcast_ip
        self.mitm_port = mitm_port
        self.host_ip = host_ip
        self.node_macs = node_macs
        self.scan_response = scan_response
        self.port = port
        self.my_mac = bytes.fromhex(Path(f"/sys/class/net/{ifname}/address").read_text().strip().replace(":", ""))
        self._radio: trio.socket.SocketType | None = None
        self._helper: trio.SocketStream | None = None
        self._send_lock = trio.Lock()
        self._unknown: set[str] = set()

    async def run(self) -> None:
        await remove_ipv4(self.ifname, self.local_ip)
        self._radio = trio.socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(ETH_P_ALL))
        await self._radio.bind((self.ifname, 0))
        log.info("Windows relay listening on port %d", self.port)
        with self._radio:
            async with trio.open_nursery() as n:
                n.start_soon(self._from_radio)
                n.start_soon(trio.serve_tcp, self._serve_helper, self.port)

    # -- the Windows helper
    async def _serve_helper(self, stream: trio.SocketStream) -> None:
        if self._helper is not None:
            log.info("a new Windows helper connected; dropping the old one")
            await self._helper.aclose()
        self._helper = stream
        print("The Windows helper connected.")
        await self._to_helper_raw(tunnel_proto.config(self.local_ip, 24))
        decoder = tunnel_proto.Decoder()
        try:
            while True:
                data = await stream.receive_some(65536)
                if not data:
                    break
                for kind, payload in decoder.feed(data):
                    if kind == tunnel_proto.PACKET:
                        await self._to_radio(payload)
        except (trio.BrokenResourceError, trio.ClosedResourceError):
            pass
        finally:
            if self._helper is stream:
                self._helper = None
                print("The Windows helper disconnected.")

    async def _to_helper_raw(self, message: bytes) -> None:
        helper = self._helper
        if helper is None:
            return
        async with self._send_lock:
            try:
                await helper.send_all(message)
            except (trio.BrokenResourceError, trio.ClosedResourceError):
                pass

    async def _to_helper(self, packet: bytes) -> None:
        await self._to_helper_raw(tunnel_proto.encode(tunnel_proto.PACKET, packet))

    # -- Windows -> Switch
    async def _to_radio(self, packet: bytes) -> None:
        info = packets.parse_ipv4(packet)
        if info is None:
            return
        if info.src != self.local_ip:
            log.debug("dropping a packet from %s, not the bridge's address", info.src)
            return
        if info.dst in (self.broadcast_ip, "255.255.255.255"):
            if info.proto == packets.IPPROTO_UDP and info.dport == self.mitm_port:
                await self._answer_scan(info)
                return
            dst_mac = packets.BROADCAST_MAC
        elif packets.is_multicast(info.dst):
            dst_mac = packets.multicast_mac(info.dst)
        else:
            dst_mac = self.node_macs().get(info.dst)
            if dst_mac is None:
                if info.dst not in self._unknown:
                    self._unknown.add(info.dst)
                    log.info("no LDN member at %s; dropping packets to it", info.dst)
                return
        await self._radio.send(packets.ethernet(dst_mac, self.my_mac, packets.ETH_P_IP, packet))

    async def _answer_scan(self, info: packets.IPv4) -> None:
        try:
            pkt = mp.decode_packet(info.payload)
        except mp.ProtocolError:
            return
        if pkt is None or pkt[0] != mp.PacketType.SCAN:
            return
        log.info("Scan from the emulator at %s:%s", info.src, info.sport)
        # Ryujinx ignores UDP from its own address, so answer from the host's.
        reply = packets.udp_ipv4(self.host_ip(), self.mitm_port, info.src, info.sport, self.scan_response())
        await self._to_helper(reply)

    # -- Switch -> Windows
    async def _from_radio(self) -> None:
        while True:
            frame, addr = await self._radio.recvfrom(65536)
            if addr[2] == PACKET_OUTGOING:
                continue
            eth = packets.parse_ethernet(frame)
            if eth is None:
                continue
            dst, src, ethertype, payload = eth
            if ethertype == packets.ETH_P_ARP:
                reply = packets.arp_reply(payload, self.local_ip, self.my_mac)
                if reply:
                    await self._radio.send(packets.ethernet(src, self.my_mac, packets.ETH_P_ARP, reply))
            elif ethertype == packets.ETH_P_IP:
                info = packets.parse_ipv4(payload)
                if info and (info.dst in (self.local_ip, self.broadcast_ip, "255.255.255.255")
                             or packets.is_multicast(info.dst)):
                    total = struct.unpack("!H", payload[2:4])[0]
                    await self._to_helper(payload[:total])  # Ethernet can pad short frames
