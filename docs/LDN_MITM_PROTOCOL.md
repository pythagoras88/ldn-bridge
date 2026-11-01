# ldn_mitm LAN protocol

Status: reconstructed from ldn_mitm (`ldn_mitm/source/lan_protocol.*`, `ldn_types.hpp`,
https://github.com/spacemeowx2/ldn_mitm) and Ryujinx/yuzu's LdnMitm ports. **Verify with captures (M3)** and update
this file with what you see.

## Transport
- Port **11452**, UDP and TCP.
- Discovery: client sends `Scan` as UDP broadcast to the interface's broadcast address; any host answers `ScanResp`
  by unicast UDP.
- Membership: client opens TCP to node 0's IP (the host) and sends `Connect`; host replies and later pushes
  `SyncNetwork` whenever anything changes. The TCP connection stays open for the session.
- Game traffic: ordinary UDP/TCP between node IPs. Not part of this protocol.

## Header (12 bytes, little-endian)
| Offset | Type | Field |
| --- | --- | --- |
| 0x0 | u32 | magic `0x11451400` |
| 0x4 | u8 | type: 0 Scan, 1 ScanResp, 2 Connect, 3 SyncNetwork |
| 0x5 | u8 | compressed (0/1) |
| 0x6 | u16 | length (payload bytes on the wire) |
| 0x8 | u16 | decompress_length (payload size after decompression) |
| 0xA | u8[2] | reserved |

## Compression
Zero run-length: a `0x00` byte is followed by a count byte = how many *additional* zeros follow (0–255). Other bytes
are copied. The sender only sets `compressed=1` when the result is smaller.

## Payloads
- `Scan`: empty.
- `ScanResp`, `SyncNetwork`: `NetworkInfo` (0x480).
- `Connect`: `NodeInfo` (0x40) of the joining node.

## NetworkInfo (0x480)
| Offset | Size | Field |
| --- | --- | --- |
| 0x000 | 8 | local_communication_id (u64) |
| 0x008 | 2 | reserved |
| 0x00A | 2 | scene_id (u16) |
| 0x00C | 4 | reserved |
| 0x010 | 16 | session_id |
| 0x020 | 6 | bssid (MAC) |
| 0x026 | 1 | ssid length |
| 0x027 | 33 | ssid (32 chars + NUL) |
| 0x048 | 2 | channel (s16) |
| 0x04A | 1 | link_level (s8) |
| 0x04B | 1 | network_type (u8, 2 = LDN) |
| 0x04C | 4 | reserved |
| 0x050 | 16 | security_parameter (server random) |
| 0x060 | 2 | security_mode (u16) |
| 0x062 | 1 | station_accept_policy |
| 0x063 | 3 | reserved |
| 0x066 | 1 | node_count_max |
| 0x067 | 1 | node_count |
| 0x068 | 0x200 | nodes[8] (NodeInfo) |
| 0x268 | 2 | reserved |
| 0x26A | 2 | advertise_data_size |
| 0x26C | 384 | advertise_data |
| 0x3EC | 140 | reserved |
| 0x478 | 8 | authentication_id (u64) |

## NodeInfo (0x40)
| Offset | Size | Field |
| --- | --- | --- |
| 0x00 | 4 | ipv4 address as u32 **in host order, stored little-endian** (169.254.1.2 → `02 01 FE A9`) — verify |
| 0x04 | 6 | MAC |
| 0x0A | 1 | node_id (s8) |
| 0x0B | 1 | is_connected (s8) |
| 0x0C | 33 | user name (UTF-8, NUL-terminated) |
| 0x2D | 1 | reserved |
| 0x2E | 2 | local_communication_version (u16) |
| 0x30 | 16 | reserved |

## Ryujinx behaviour that affects the bridge
Read from Ryubing source, commit `475615f` (`src/Ryujinx.HLE/HOS/Services/Ldn/UserServiceCreator/LdnMitm/`; a local
copy lives in `third_party/ryujinx`). The fork you actually run may differ.
- **Same-IP UDP is dropped.** `LanProtocol.Read` silently ignores any datagram whose source IP equals the emulator's
  `LocalAddr`. On the `ldn` interface the emulator and bridge share an IP, so a ScanResp sent from that IP never
  arrives. `control_plane.py` answers same-IP scanners from `127.0.0.1` instead, which still delivers locally.
  Same for `mitm-scan` on the emulator's machine: use `--bind 127.0.0.1 --broadcast <emulator IP>`.
- **Interface is chosen once.** `LdnMitmClient` resolves `MultiplayerLanInterfaceId` when the game initialises LDN.
  If that interface is missing, `NetworkHelpers.GetLocalInterface` silently falls back to the first one with a gateway
  (the Deck's Wi-Fi). So `ldn` must already exist, with its IP, before the game starts local wireless.
- **Empty host name hides the session.** `Scan()` drops results whose node 0 `UserName` starts with NUL.
- **Sends are always compressed**, and receivers honour the header flag, so sending uncompressed is fine.
- Linux sockets: UDP on `LocalAddr:11452` and on `broadcast:11452`, both `SO_REUSEADDR`. TCP client only when joining.
- Connect waits 4 s (`FailureTimeout`) for the first SyncNetwork, otherwise it returns `ConnectTimeout`.

## Things to confirm in M3
Notes say what source reading and a socket-level simulation (Linux network namespace) showed. Tick a box only after
a real capture agrees.
- [x] Port 11452 for both UDP and TCP. *2026-11-01: ScanResp came from UDP 11452; the emulator's log shows its TCP
  server on 11452.*
- [x] Header layout + magic; compression flag behaviour. *2026-11-01: Ryujinx 1.3.3's ScanResp decoded correctly.*
- [x] NodeInfo IP byte order. *2026-11-01: node 0 decoded as the emulator's IP.*
- [x] Does the emulator accept a ScanResp from a different source port than 11452? *2026-11-01: yes. Scarlet found the
  session from the bridge's `127.0.0.1` reply.*
- [x] Does the emulator replace its NetworkInfo wholesale on SyncNetwork (needed for the node-0 IP trick)? *2026-11-01:
  yes in practice. It connected to the ScanResp's node 0 IP, and play worked with the real member list.*
- [x] Does Scarlet use a real local_communication_id on the emulator, or the default `-1`? *2026-11-01: `-1`.*
  ldn_mitm mode has `NeedsRealId => false`, so Ryujinx passes it through instead of resolving it, and `Scan()` compares
  it to the ScanResp's id. `mitm-scan` showed `0xffffffffffffffff` while the emulator hosted, so `convert.py` sends that
  value in place of the Switch's real id. The emulator's scene_id (5), version (21) and advertise data size (132) match
  the Switch's.
- [x] How the emulator identifies its own node in SyncNetwork (IP? MAC?). *2026-11-01: IP is enough for play. The
  emulator's Connect carried MAC `02:00:a9:fe:13:02` and the member list shows the adapter's MAC, and trading still
  worked.*
