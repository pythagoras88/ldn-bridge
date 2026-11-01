# Milestones

Each one ends with something visible. Tick boxes as you go and note findings under each.

This is the log of the first end-to-end test, so the notes below name the game it used. `docs/TESTING.md` has the current
compatibility notes.

- [x] **M0 Setup** — Deck SSH works from Windows; adapter detected (`deck/find_adapter.sh`); NM ignores it
  (`deck/nm_unmanage.sh`); `deck/setup.sh` done; `python -m ldn_bridge keys-check` shows required keys present.
  2026-11-01: SteamOS 3.9.5, Alfa MT7612U on `mt76x2u`, Ryujinx 1.3.3 has ldn_mitm mode, keys cover protocols 1 and 3.
- [x] **M1 See the Switch** — Switch opens Union Circle; `python -m ldn_bridge scan` lists it.
  Record: local_communication_id, scene_id, app_version, version, protocol, band/channel, application_data length.
  Repeat with Switch 2 if available.
  2026-11-01, Switch 2 hosting Violet: local_communication_id `0x0100a3d008c5c000` (Scarlet's title ID, so both
  versions share it), scene_id 5, app_version 21, version 4,
  protocol 1, band 2 channel 6, application_data 132 bytes, security_mode 1, 4 players max. Stable across two scans.
  Original Switch not tested.
- [ ] **M2a Join with empty passphrase** — `python -m ldn_bridge join` connects; Switch shows a new member.
  2026-11-01: failed. The station associated, then got no reply to its authentication frames and timed out, with no
  disassociation. That fits a wrong passphrase but doesn't prove it.
- [x] **M2b Get the passphrase (only if M2a fails auth)** — build the Ryujinx fork from source so CreateNetwork/Connect
  record the `SecurityConfig` passphrase; host Union Circle once; put the hex in `config.toml` (`password_hex`). Never
  commit it. Ryujinx's existing `NetLog` lines don't help: `SecurityConfig` has no `ToString`.
  Patch is applied in `third_party/ryujinx-1.3.3` (tag 1.3.3, needs .NET SDK 9). It appends to `~/ldn-passphrase.txt`
  (mode 600) on the Deck, not the log, along with the local_communication_id and version. Those two also answer the
  `-1` question in M3 and whether the emulator's app_version matches the Switch's 21.
  2026-11-01: passphrase captured (64 bytes, security mode 1). `join` then got node 1 on the Switch 2, `169.254.19.2`,
  and held it for 35 s until stopped.
- [x] **M3 Learn the emulator side** — with the emulator hosting in ldn_mitm mode, `python -m ldn_bridge mitm-scan`
  decodes its ScanResp. Confirms header, compression and NetworkInfo layout. Save the capture.
  2026-11-01: Ryujinx 1.3.3 hosting: decoded cleanly; id is `-1`, scene 5, version 21, 132 bytes of advertise data.
  From the emulator's own machine use `--bind 127.0.0.1 --broadcast <emulator IP>` (Ryujinx drops UDP from its own
  IP). From another machine on the LAN, `--broadcast X.X.X.255` works as is.
- [ ] **M3b Fake host** — `python -m ldn_bridge mitm-fake-host` makes a fake session appear in the emulator's join
  list, and logs the emulator's Connect NodeInfo.
- [x] **M4 Discovery bridge** — `python -m ldn_bridge bridge` (joined to the Switch); the emulator lists the
  Switch's Union Circle. Join first, then open Union Circle on the emulator, and check its log shows the `169.254.N.k`
  address (`Initialize LanDiscovery using IP`). If it shows the Wi-Fi IP, LDN started before `ldn` existed.
  2026-11-01: Scarlet on Ryujinx 1.3.3 used `169.254.19.2`, found Violet's session and sent Connect. LDN initialises
  each time Union Circle opens, not at boot. One attempt logged `Failed to connect` in `LdnProxyTCPClient.Connect` right
  after the socket connected, and the next attempt worked. It looks like a race in Ryujinx; retrying is the workaround.
- [x] **M5 Play** — emulator joins and stays connected; Pia traffic flows (watch with
  `tcpdump -i ldn -n udp`).
  2026-11-01: Scarlet on the Deck and Violet on a Switch 2 saw each other move in Union Circle and completed a trade.
  Game traffic was almost all UDP broadcast on port 12345, with very little unicast.
  The normal Ryujinx 1.3.3 AppImage also joined, from `deck/play.sh`.
  Poké Portal Link Trade doesn't work yet. The Switch's session (scene 4, 2 players) appeared in 1 of 13 scans and was
  gone or refused the join (`Connect failed with status code 1`). Meanwhile Scarlet, with no `ldn` interface yet, kept
  hosting its own session on Wi-Fi about every 8 s. It looks like both sides take short turns hosting. Union Circle
  (scene 5) stays up, so the bridge can join it. Link Trade would need faster joins and M6.
- [ ] **M6 Reverse direction** — implement `bridge.py` emulator-hosts mode; Switch joins the emulator.
- [ ] **M7 Real use** — trade, battle, Tera Raid; 30-minute soak test.
