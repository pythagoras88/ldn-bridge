"""Run ON WINDOWS as Administrator: give Ryujinx a network adapter on the bridge's LDN network (docs/WSL.md, W2).

Creates a Wintun adapter called "LDN Bridge", sets it to the address the bridge in WSL was given by the Switch, and
passes its IPv4 packets to and from the bridge over 127.0.0.1, which WSL forwards. The adapter is removed again when
this stops (Ctrl+C).

Needs wintun.dll (amd64) from wintun.net next to this file, and Python 3 for Windows. Also, once:
- adds a Windows Firewall rule allowing inbound traffic on that adapter only, so the Switch can reach Ryujinx;
- sets Ryujinx's multiplayer Mode to ldn_mitm, its Network Interface to the adapter, and Guest Internet Access off,
  in %APPDATA%\\Ryujinx\\Config.json (close Ryujinx first).

    python windows\\ldn_tunnel.py [--dll PATH] [--ryujinx-config PATH] [--port 11453]
"""
from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wt
import json
import os
import socket
import struct
import subprocess
import sys
import _thread
import threading
import time
import uuid
from pathlib import Path

ADAPTER = "LDN Bridge"
ADAPTER_GUID = uuid.UUID("6b2c8f2e-4d1a-4c3e-9b1d-1d2b3c4d5e6f")
RING_CAPACITY = 0x400000
ERROR_NO_MORE_ITEMS = 259
LDN_MITM = 2  # Ryujinx's MultiplayerMode: Disabled, LdnRyu, LdnMitm
INFINITE = 0xFFFFFFFF

# Same framing as src/ldn_bridge/tunnel_proto.py: 1-byte type, 2-byte big-endian length, payload.
CONFIG, PACKET = 1, 2
HEADER = struct.Struct("!BH")

# Windows' own chatter that shouldn't go onto the Switch's network.
NOISY_UDP_PORTS = {137, 138, 1900, 3702, 5353, 5355}


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wt.DWORD), ("Data2", wt.WORD), ("Data3", wt.WORD), ("Data4", ctypes.c_ubyte * 8)]

    @classmethod
    def from_uuid(cls, u: uuid.UUID) -> "GUID":
        g = cls()
        ctypes.memmove(ctypes.byref(g), u.bytes_le, 16)
        return g


class Wintun:
    def __init__(self, path: Path):
        self.dll = ctypes.WinDLL(str(path), use_last_error=True)
        d = self.dll
        d.WintunCreateAdapter.argtypes = [wt.LPCWSTR, wt.LPCWSTR, ctypes.POINTER(GUID)]
        d.WintunCreateAdapter.restype = ctypes.c_void_p
        d.WintunOpenAdapter.argtypes = [wt.LPCWSTR]
        d.WintunOpenAdapter.restype = ctypes.c_void_p
        d.WintunCloseAdapter.argtypes = [ctypes.c_void_p]
        d.WintunStartSession.argtypes = [ctypes.c_void_p, wt.DWORD]
        d.WintunStartSession.restype = ctypes.c_void_p
        d.WintunEndSession.argtypes = [ctypes.c_void_p]
        d.WintunGetReadWaitEvent.argtypes = [ctypes.c_void_p]
        d.WintunGetReadWaitEvent.restype = wt.HANDLE
        d.WintunReceivePacket.argtypes = [ctypes.c_void_p, ctypes.POINTER(wt.DWORD)]
        d.WintunReceivePacket.restype = ctypes.c_void_p
        d.WintunReleaseReceivePacket.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        d.WintunAllocateSendPacket.argtypes = [ctypes.c_void_p, wt.DWORD]
        d.WintunAllocateSendPacket.restype = ctypes.c_void_p
        d.WintunSendPacket.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel32.WaitForSingleObject.argtypes = [wt.HANDLE, wt.DWORD]
        self.adapter = None
        self.session = None

    def open(self) -> None:
        guid = GUID.from_uuid(ADAPTER_GUID)
        self.adapter = self.dll.WintunCreateAdapter(ADAPTER, "LDN", ctypes.byref(guid))
        if not self.adapter:
            raise OSError(ctypes.get_last_error(), "couldn't create the Wintun adapter (run as Administrator?)")
        self.session = self.dll.WintunStartSession(self.adapter, RING_CAPACITY)
        if not self.session:
            raise OSError(ctypes.get_last_error(), "couldn't start the Wintun session")
        self.read_event = self.dll.WintunGetReadWaitEvent(self.session)

    def close(self) -> None:
        if self.session:
            self.dll.WintunEndSession(self.session)
            self.session = None
        if self.adapter:
            self.dll.WintunCloseAdapter(self.adapter)
            self.adapter = None

    def receive(self) -> bytes:
        """Wait for the next packet Windows sends out of the adapter."""
        size = wt.DWORD()
        while True:
            ptr = self.dll.WintunReceivePacket(self.session, ctypes.byref(size))
            if ptr:
                data = ctypes.string_at(ptr, size.value)
                self.dll.WintunReleaseReceivePacket(self.session, ptr)
                return data
            err = ctypes.get_last_error()
            if err != ERROR_NO_MORE_ITEMS:
                raise OSError(err, "Wintun receive failed")
            self.kernel32.WaitForSingleObject(self.read_event, INFINITE)

    def send(self, packet: bytes) -> None:
        """Hand Windows a packet as if it arrived on the adapter. Dropped if the ring is full."""
        ptr = self.dll.WintunAllocateSendPacket(self.session, len(packet))
        if ptr:
            ctypes.memmove(ptr, packet, len(packet))
            self.dll.WintunSendPacket(self.session, ptr)


def powershell(command: str) -> str:
    out = subprocess.run(["powershell", "-NoProfile", "-Command", command], capture_output=True, text=True)
    return out.stdout.strip()


def netsh(*args: str) -> None:
    subprocess.run(["netsh", *args], capture_output=True, text=True)


def adapter_id() -> str:
    """The adapter's Id as .NET reports it, which is what Ryujinx stores."""
    for _ in range(20):
        guid = powershell(f"(Get-NetAdapter -Name '{ADAPTER}' -ErrorAction SilentlyContinue).InterfaceGuid")
        if guid:
            return guid
        time.sleep(0.5)
    return "{" + str(ADAPTER_GUID).upper() + "}"


def allow_inbound() -> None:
    if not powershell(f"Get-NetFirewallRule -DisplayName '{ADAPTER}' -ErrorAction SilentlyContinue"):
        powershell(f"New-NetFirewallRule -DisplayName '{ADAPTER}' -Direction Inbound -Action Allow "
                   f"-InterfaceAlias '{ADAPTER}' -Profile Any | Out-Null")
        print(f"Added a Windows Firewall rule allowing inbound traffic on the '{ADAPTER}' adapter.")


def point_ryujinx(config_path: Path, interface_id: str) -> None:
    if not config_path.exists():
        print(f"No Ryujinx config at {config_path}. In Ryujinx, set Network Interface to '{ADAPTER}' yourself.")
        return
    config = json.loads(config_path.read_text(encoding="utf-8-sig"))
    wanted_settings = {
        "multiplayer_mode": LDN_MITM,
        "multiplayer_lan_interface_id": interface_id,
        "enable_internet_access": False,  # Guest Internet Access off, as in docs/SETUP.md
    }
    changed = {k: v for k, v in wanted_settings.items() if config.get(k) != v}
    if changed:
        config.update(changed)
        config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Set Ryujinx to Mode ldn_mitm and Network Interface '{ADAPTER}'. Restart Ryujinx if it's open.")


def set_address(ip: str, prefix: int) -> None:
    mask = socket.inet_ntoa(struct.pack("!I", (0xFFFFFFFF << (32 - prefix)) & 0xFFFFFFFF))
    netsh("interface", "ipv4", "set", "address", f"name={ADAPTER}", "source=static", f"address={ip}",
          f"mask={mask}", "gateway=none", "store=active")
    netsh("interface", "ipv4", "set", "subinterface", ADAPTER, "mtu=1500", "store=active")
    print(f"Adapter '{ADAPTER}' set to {ip}/{prefix}. Open local multiplayer in the game now.")


def wanted(packet: bytes) -> bool:
    """Only IPv4, and none of Windows' own discovery traffic."""
    if len(packet) < 20 or packet[0] >> 4 != 4 or packet[9] == 2:  # IGMP
        return False
    if packet[9] == 17:
        ihl = (packet[0] & 0x0F) * 4
        if len(packet) >= ihl + 4 and struct.unpack("!H", packet[ihl + 2:ihl + 4])[0] in NOISY_UDP_PORTS:
            return False
    return True


def adapter_to_bridge(tun: Wintun, sock: socket.socket, stop: threading.Event) -> None:
    while not stop.is_set():
        packet = tun.receive()
        if stop.is_set():
            break
        if wanted(packet):
            try:
                sock.sendall(HEADER.pack(PACKET, len(packet)) + packet)
            except OSError:
                break


def bridge_to_adapter(tun: Wintun, sock: socket.socket) -> None:
    buf = bytearray()
    while True:
        try:
            data = sock.recv(65536)
        except socket.timeout:
            continue  # wake up now and then, so Ctrl+C works on Windows
        if not data:
            return
        buf += data
        while len(buf) >= HEADER.size:
            kind, length = HEADER.unpack_from(buf)
            if len(buf) < HEADER.size + length:
                break
            payload = bytes(buf[HEADER.size:HEADER.size + length])
            del buf[:HEADER.size + length]
            if kind == CONFIG:
                set_address(socket.inet_ntoa(payload[:4]), payload[4])
            elif kind == PACKET:
                tun.send(payload)


def exit_with(pid: int) -> None:
    """Stop, removing the adapter, once process `pid` exits (windows/play.ps1 passes its own)."""
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = wt.HANDLE
    handle = kernel32.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
    if handle:
        kernel32.WaitForSingleObject(handle, INFINITE)
    _thread.interrupt_main()


def main() -> None:
    here = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser(description="Give Ryujinx on Windows a link to the LDN bridge in WSL.")
    ap.add_argument("--dll", type=Path, default=here / "wintun.dll", help="path to wintun.dll (amd64)")
    ap.add_argument("--ryujinx-config", type=Path,
                    default=Path(os.environ.get("APPDATA", "")) / "Ryujinx" / "Config.json")
    ap.add_argument("--port", type=int, default=11453, help="the bridge's relay port in WSL")
    ap.add_argument("--exit-with", type=int, metavar="PID", help="stop when this process exits")
    args = ap.parse_args()

    if not ctypes.windll.shell32.IsUserAnAdmin():
        sys.exit("Run this from Terminal (Admin): creating a network adapter needs Administrator rights.")
    if not args.dll.exists():
        sys.exit(f"wintun.dll not found at {args.dll}. Get it from wintun.net (bin\\amd64\\wintun.dll).")

    if args.exit_with:
        threading.Thread(target=exit_with, args=(args.exit_with,), daemon=True).start()
    tun = Wintun(args.dll)
    tun.open()
    try:
        allow_inbound()
        point_ryujinx(args.ryujinx_config, adapter_id())
        print(f"Adapter '{ADAPTER}' is up. Waiting for the bridge in WSL on 127.0.0.1:{args.port}... (Ctrl+C stops)")
        while True:
            try:
                sock = socket.create_connection(("127.0.0.1", args.port), timeout=5)
            except OSError:
                time.sleep(2)
                continue
            sock.settimeout(1.0)
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            print("Connected to the bridge.")
            stop = threading.Event()
            threading.Thread(target=adapter_to_bridge, args=(tun, sock, stop), daemon=True).start()
            try:
                bridge_to_adapter(tun, sock)
            except OSError:
                pass
            stop.set()
            sock.close()
            print("The bridge disconnected. Waiting for it to come back...")
    except KeyboardInterrupt:
        pass
    finally:
        tun.close()
        print(f"Removed adapter '{ADAPTER}'.")


if __name__ == "__main__":
    main()
