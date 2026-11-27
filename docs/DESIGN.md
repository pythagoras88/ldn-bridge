# LDN Bridge — design

The bridge lets a Ryujinx-fork emulator (ldn_mitm mode) and an unmodified Switch play local wireless together. Only
the **control plane** is translated; game traffic flows through the Linux kernel untouched.

## Goals / non-goals
- Goal: local wireless play between the emulator on a Linux computer and a stock Switch 1 or Switch 2 (running a
  Switch 1 game). The bridge isn't tied to one game: each game supplies its own passphrase and ids.
- Goal: both directions — Switch hosts / emulator joins (phase 1), emulator hosts / Switch joins (phase 2).
- Non-goal: native Switch 2 titles (protocol 3 needs `master_key_12`, see Risks), internet play, sharing keys.

## The two protocols
| Piece | What it is |
| --- | --- |
| Real LDN (Switch) | Hidden Wi-Fi network + encrypted action frames for advertisement. Members get IPs `169.254.N.x/24` (N = network id, host is `.1`). Games then talk plain UDP/TCP (Nintendo's Pia library). |
| ldn_mitm LAN protocol (emulator) | Replaces the ldn service. `Scan` is a UDP broadcast to port 11452; the host answers `ScanResp` (NetworkInfo). The joiner opens TCP to the host's IP:11452 and sends `Connect` (NodeInfo); host pushes `SyncNetwork` (NetworkInfo) on every change. Games then talk plain UDP/TCP over the LAN. |

Both sides end with "games talk plain IP to each other". So if the emulator sits on the **same IP subnet as the real
LDN network**, the only thing to bridge is discovery and membership.

## Key idea: join first, then let the emulator bind to the LDN interface
### Phase 1: Switch hosts, emulator joins
1. The Switch hosts a local multiplayer session. Bridge scans over the air with the USB adapter and finds it.
2. Bridge **joins** the network with `ldn.connect()`. This creates a real station interface `ldn` on the adapter
   with an IP like `169.254.N.k/24`. The kernel now handles encryption and IP for that interface.
3. The emulator's multiplayer **Network Interface** is set to `ldn` (one-time setting). Only now does the user open
   local multiplayer in the game: Ryujinx picks its interface when the game initialises LDN, and silently falls back to
   Wi-Fi if `ldn` doesn't exist yet.
4. The emulator broadcasts `Scan` to `169.254.N.255:11452`. Linux loops broadcasts back locally, so the bridge's UDP
   socket receives it. The bridge answers `ScanResp` with the real network converted to ldn_mitm format, sent from
   `127.0.0.1` because Ryujinx drops UDP sourced from its own IP (see `docs/LDN_MITM_PROTOCOL.md`).
5. The emulator opens TCP to "the host" (node 0's IP from ScanResp) and sends `Connect`.
   - **Trick:** in the `ScanResp` only, node 0's IP is replaced by our own IP `169.254.N.k`, so the TCP connection
     lands on the bridge locally. `SyncNetwork` then carries the **real** node list (Switch at `.1`, emulator at
     `.k`). ldn_mitm clients replace their network info wholesale on SyncNetwork. If this proves false, fall back to
     an nftables `redirect` of `tcp dport 11452` to the real host IP.
6. Bridge answers with `SyncNetwork` and keeps pushing it whenever the library reports Join/Leave/
   ApplicationDataChanged events.
7. Game traffic: emulator ⇄ Switch over the `ldn` interface. The emulator's own IP *is* our real LDN IP, so Pia's
   in-band addresses are correct and no NAT is needed.

Timing risk: between step 2 and step 5 the Switch sees a member with no game traffic. If the Switch times us out,
shorten the gap (the bridge waits for Enter before joining). The emulator can't already be on the join screen if the
game initialised LDN before `ldn` existed. The emulator log line `Initialize LanDiscovery using IP: ...` must show the
`169.254.N.k` address.

### Phase 2: emulator hosts, Switch joins
Steps 1 to 3 come from reading the library and Ryujinx 1.3.3 source. `host-test` proved the adapter side of step 1, and
the control steps have run on real interfaces against a stand-in emulator. None of this has been tried with a game.

1. Bridge creates the over-the-air network first with `ldn.create_network()` using the game's
   `local_communication_id`, `scene_id`, `app_version`, passphrase, and empty application data. These come from a `scan`
   capture, not the emulator: the interface must exist before the game starts local wireless, and the
   emulator reports its id as `-1`. The TAP interface takes the name `ldn` with IP `169.254.N.1`, and the monitor
   interface becomes `ldn-mon`, so the emulator's Network Interface setting is the same in both directions.
2. The emulator is bound to `ldn` and hosts. The bridge polls it with ldn_mitm `Scan` from `127.0.0.1` and copies its
   advertise data and host name into the AP. Stations are refused until then, and again if the emulator stops hosting.
3. When the Switch joins (`JoinEvent`), the bridge connects to the emulator's TCP 11452 on behalf of the Switch and sends
   `Connect` with the Switch's NodeInfo (its `169.254.N.x` IP and MAC). Ryujinx stores that NodeInfo unchanged. The
   connection must come from `127.0.0.1`, because Ryujinx drops TCP data as well as UDP from its own IP. If the emulator
   hangs up, the bridge kicks the Switch.
4. Both sides need the same session ID and security parameter, or the Switch's game gives up. Ryujinx leaves the
   security parameter empty, so the AP's `server_random` is all zeros, and the AP takes the emulator's session ID once
   the game hosts. The AP's host MAC still differs from the emulator's own view of itself.
5. Unlike phase 1, game traffic passes through Python here (monitor mode plus a TAP), so speed is a risk (M6b). The
   library treats a frame that fails its integrity check as fatal, so `ldn_side.py` drops those frames instead.
   The library's read of the TAP can't be cancelled, so on the way out the bridge sends one packet across it
   (`bridge.wake_tap`).
   A key left in the adapter's chip from an earlier session makes the chip decrypt the Switch's broadcasts with the
   wrong key and pass on garbage. A joined session leaves that key, so the bridge resets the adapter over USB before it
   hosts (`adapter.reset`), and warns if most broadcasts still can't be read (M6 in `docs/MILESTONES.md`).
6. The AP copies the emulator's scene, player limit, app version and session data each time the game hosts, so one
   bridge serves every mode, and the game's ID comes from `config.toml`. The Switch skips sessions whose scene or player
   limit doesn't match what it's searching for.
7. Turn-based searches (Link Trade) host for about 3 s at a time. The bridge asks the emulator every 0.2 s and closes the
   session after two unanswered scans, so each turn opens and closes within about a second of the emulator's. The
   Switch joins one of those turns, and the Switch's own turns never need to reach the emulator.

## Components
| File | Role |
| --- | --- |
| `ldn_side.py` | Builds `ConnectNetworkParam` / `CreateNetworkParam` from config; scan helpers. |
| `mitm_proto.py` | ldn_mitm packet codec and structs (pure Python, unit-tested). |
| `convert.py` | Over-the-air `ldn.NetworkInfo` → ldn_mitm `NetworkInfo`. |
| `control_plane.py` | UDP scan responder + TCP Connect/SyncNetwork server. |
| `emulator_link.py` | ldn_mitm client for phase 2: Scan and Connect, from `127.0.0.1`. |
| `hosting.py` | Hosted session settings from a capture, and tracking of the emulator's session. |
| `bridge.py` | Orchestration for both phases. |

## Hardware and environment
- A Linux computer. Tested on a Steam Deck, with its internal Wi-Fi left on NetworkManager for internet + SSH.
- USB Wi-Fi adapter with monitor mode + injection and an in-kernel driver, e.g. MediaTek MT7612U (Alfa AWUS036ACM)
  or MT7610U. NetworkManager must ignore it (`deck/nm_unmanage.sh`).
- Python venv created with `--copies`; `setcap cap_net_admin,cap_net_raw+eip` on the venv's python so the library
  can create interfaces without running everything as root.
- Keys: your own `prod.keys`. The library needs `master_key_00`, `aes_kek_generation_source`,
  `aes_key_generation_source` for protocol 1 (Switch 1 games). Protocol 3 needs `master_key_12`.

## Risks and open questions
- **Passphrases are per game.** The data-frame key is derived from server_random + the game's passphrase. Capture it
  from the emulator: the patched ldn service (`CreateNetwork` / `Connect` receive a `SecurityConfig`) records it when
  the game hosts once. See `docs/SETUP.md`, section 4.
- **Game version / emulator keys:** the stock console auto-updates games; the emulator copy must be compatible, and
  the newest update may need newer keys than an older dump.
- **Session length:** the bridge needs a session that stays open while it scans and joins. Games where both sides
  search and take turns hosting may never line up.
- **Session id:** `convert.py` always sends `-1`. A game that uses its real id on the emulator needs that changed.
- **Fast games:** the extra hop and any emulator slowdown may cause lag or disconnects.
- **Port sharing on 11452:** emulator and bridge both use it on the same host. Bridge binds UDP to the broadcast
  address only and TCP to our IP. A Linux socket simulation of Ryujinx's binds worked in either start order; confirm
  with the real emulator in M4.
- **Emulator interface selection:** Ryujinx must accept `ldn` (an interface that only exists while joined), and
  `ldn` must exist before the game initialises LDN.
- **Struct layouts** in `mitm_proto.py` come from ldn_mitm/Ryujinx sources, not captures. M3 verifies them.
- **Switch 2:** Switch 1 games on a Switch 2 advertised protocol 1 in testing. Check others with `scan`, which prints
  platform + protocol.
- **Latency:** when the Switch hosts, the data plane is in-kernel, so Python only handles control traffic. When the
  emulator hosts, every frame goes through Python.
