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
  2026-11-07: Game Mode works. The Play with LDN Bridge shortcut joined Union Circle and stayed connected for about 40
  minutes. The Deck's built-in Wi-Fi was disconnected for that whole session. SteamOS booted on the iwd Wi-Fi backend,
  and iwd connected both radios to the home network, including the USB adapter that NetworkManager is told to ignore.
  About 15 s after boot, Steam switched the backend to wpa_supplicant. iwd stopped, and the built-in card was left with
  no network interface, so it never reconnected. The adapter kept its interface and the bridge worked. On two earlier
  boots that day, with only one Wi-Fi interface, the built-in Wi-Fi came back after the same switch. No fix has been
  tested yet.
  2026-11-07: three Union Circle sessions in Game Mode ended after about 11, 1.5 and 1 minutes. The Switch ended the
  first one (deauthentication reason 5). The other two ended within 60 ms of the Deck's built-in Wi-Fi switching
  between two routers on the same network. The `ldn` library heard that interface's station removal and treated it as
  losing the Switch. `ldn_side` now ignores events for other interfaces (see `docs/LDN_LIBRARY.md`), and
  `tests/test_station_events.py` covers it. Not yet tested in a game session.
  2026-11-08: Ryujinx 1.3.3 crashed when Scarlet on the Deck tried to host a session while the bridge was joined to
  the Switch's Union Circle. The bridge joined, and 12 s later the game called `CreateNetwork`. Ryujinx's
  `LanDiscovery.InitTcp` couldn't bind TCP 11452 on the `ldn` address, because the bridge's control plane already listens
  there (`Address already in use`). Ryujinx doesn't catch that exception, so the game froze while the crash dump was
  written. Avoiding it would need the bridge to refuse or redirect hosting while it's joined. Nothing does that yet.
  The same evening, Ryujinx closed three times after an `amdgpu` page fault from its own graphics threads, followed by a
  GPU reset. Two came about a minute after joining Union Circle, and one came before local play started. A reboot didn't
  stop them. These are emulator or driver crashes, not the bridge. Ryujinx was in Handheld mode for at least the last
  one, and had been in Docked mode for the stable 2026-11-07 session. It was switched back to Docked at about 21:20, and
  no GPU fault followed in the next 75 minutes of play.
  Ryujinx still crashed seven more times that evening. Five were segfaults inside Steam's Vulkan layers loaded into the
  emulator: three in `steamoverlayvulkanlayer.so` on its render thread, and two in `libVkLayer_steam_fossilize.so`.
  A sixth segfault left no library name, but its address matched the overlay crashes. The Deck's USB hub disconnected
  within a few seconds of four of these crashes, which ended the bridge's session. One more ended with the game itself
  aborting (2162-0001) seven minutes into a Union Circle session. `deck/play.sh` now turns both Steam layers off for
  the emulator (`LDN_STEAM_LAYERS=1` keeps them). Untested.
- [x] **M6a Can the adapter host?** — `python -m ldn_bridge host-test` hosts a copy of a session from a `scan` capture,
  with no emulator. The Switch searches from the same mode. Passing means the session appears on the Switch and the
  command logs `Joined:`. The Switch won't get any further, because nothing answers it as a game. A failure here stops M6
  on this adapter. The library has only been confirmed hosting on `mt7921e`, so the MT7612U (`mt76x2u`) is unknown.
  2026-11-01: passed on the MT7612U with the Alfa on channel 6. The Switch joined as `169.254.80.2`, left 5 s later and
  showed error 2318-0533 ("Unable to communicate with the other console(s)"), as expected with no game answering.
  Union Circle searches by a 4-digit code that changes each session. The session data held one standalone run of four
  ASCII digits, at offset 92, and searching with those digits found the session where random codes didn't. So the host's
  code is carried in that data, based on this one test. Monitor interfaces showed 0 packets sent throughout, so that
  counter doesn't show whether injection works.
- [ ] **M6b Is hosting fast enough?** — measure game-sized traffic over the hosted link. Hosting sends every frame
  through Python, and the library's author measured about 20 KB/s over TCP. First confirm the Switch's data frames reach
  the interface: in M6a its receive counter stayed at 0 during the 5 s the Switch was joined. That may only mean the game
  was waiting for the host, but it doesn't yet show two-way traffic.
  2026-11-27: two-way traffic confirmed (see M6). Trades and a Tera Raid ran at normal speed with every frame going
  through Python. Nothing was measured, and a longer session is still needed.
- [x] **M6 Reverse direction** — implement `bridge.py` emulator-hosts mode; Switch joins the emulator.
  2026-11-01: built. `bridge emulator-hosts` ran on the Deck's real `ldn` interface against a stand-in emulator that
  ignores its own IP: Scan and Connect both arrived from `127.0.0.1`, and it stopped cleanly. Not yet tried with a game.
  A real test also answers M6b, so the separate speed tool wasn't built.
  2026-11-01, Scarlet hosting on the Deck, Switch joining with the emulator's code:
  - The first tries ended with error 2318-0533 after about 5 s. Sign-in succeeded, and pings from the Deck got replies
    in about 5 to 10 ms, so unicast works both ways.
  - Giving both sides the same session ID and security parameter stopped that error. The Switch stayed joined, the
    emulator showed 2 nodes, and the Switch's game started sending, but it stays on "searching for group". ARP replies
    and pings were also running in that test, so it isn't yet known that they aren't needed.
  - Remaining blocker: the Switch's game traffic is broadcast, and none of its frames to `ff:ff:ff:ff:ff:ff` can be
    read. They have the Protected bit set but no CCMP header, their sizes look like plaintext sizes, and they show no
    shared keystream. The data key doesn't open them as CCMP or as AES-CTR with SNAP plus IPv4 plaintext. The same
    station's IPv6 multicast frames decrypt normally, as does its unicast. It isn't known whether this comes from the
    MT7612U in monitor mode or from how the Switch sends them. A second radio listening on channel 6 would settle it.
  - 2026-11-27: solved. With the Switch 2 hosting Union Circle and `bridge switch-hosts` joined, a second monitor
    interface on the same adapter heard the Switch's broadcasts in two forms: as normal CCMP frames with the header
    (825 in 15 s), and already decrypted by the adapter's chip, with the CCMP header and MIC removed but the Protected
    bit still set (338). The unreadable M6 frames match the second form, decrypted with the wrong key. After the adapter
    was unplugged and plugged back in, `bridge emulator-hosts` decrypted the Switch's broadcasts normally: 17,670 frames
    over the session, with 27 unreadable ones only at the start. Scarlet on the emulator hosted Union Circle, the Switch
    2 joined with its code, both players saw each other, traded both ways at normal speed, and finished a Tera Raid that
    the emulator's player started at a den. So the cause is a key left in the MT7612U from an earlier session, not the
    Switch. Temporary ARP replies and pings were still running. Still to do: clear or detect that key in the bridge so
    no replug is needed, and test without the ARP replies and pings.
  - 2026-11-27, later: what leaves the key, and what clears it. After a fresh plug, `bridge switch-hosts` joined the
    Switch 2's Union Circle for 30 s and stopped cleanly. Hosting straight after that failed: with plain `bridge
    emulator-hosts` the Switch joined and left with error 2318-0531, and with the diagnostic run it stayed on
    "searching" while its broadcasts failed (66 failed decryption, 22 had no CCMP header, key IDs random), its unicast
    decrypted, and the bridge's new warning fired. `sudo usbreset 0e8d:7612` made the driver reload the adapter's
    firmware like a replug, and the next hosted session read the broadcasts (193 decrypted, 29 unreadable at the start
    only) and both players saw each other. Then plain `bridge emulator-hosts` hosted again with no reset in between:
    the Switch joined and stayed connected while both players walked around. So a joined session leaves the key, a
    hosted session doesn't, a USB reset clears it, and the ARP replies and pings aren't needed.
  - 2026-11-27: `bridge emulator-hosts` now resets the adapter with `USBDEVFS_RESET` before hosting. On the Deck it ran
    without sudo: the driver reloaded the firmware and the adapter came back as a new phy within 2 s. The `deck` user
    could already write to the USB device through the seat's ACL (`user:deck:rw-`), which logind grants to the
    logged-in user. `deck/usb_access.sh` adds a udev rule for when that ACL isn't there.
  - 2026-11-27: tested end to end. `bridge switch-hosts` joined the Switch 2's Union Circle for 30 s and stopped, which
    leaves the key. Plain `bridge emulator-hosts` then reset the adapter (phy23 to phy24 in 2 s), Scarlet on the
    emulator hosted Union Circle, and the Switch joined and both players saw each other. No warning about unreadable
    broadcasts, no replug and no sudo.
  - 2026-11-27: the emulator hosted a Poké Portal Tera Raid. The bridge used to advertise the capture's scene (5, Union
    Circle) whatever the game hosted, so it now copies the emulator's scene into the session (7 for the raid). Scarlet
    on the emulator hosted a raid at a den with a Link Code, the Switch 2 searched with it from the Poké Portal, and the
    raid finished on both consoles.
  - 2026-11-27: Poké Portal Link Trade works with `bridge emulator-hosts`. Ryujinx alternates hosting (about 3 s) and
    searching (about 4 s), always with the same advertise data (a Link Code sits at offset 92, like Union Circle's).
    The bridge advertised each turn, but the Switch never sent an authentication request, with or without a code. The
    emulator's session allows 2 players and the bridge advertised the capture's 4. With the emulator's player limit
    copied into the session, both consoles searching with code 12341234 found each other and traded both ways. Of 4
    joins in 26 s, 2 failed because the bridge still advertised a turn for up to 4 s after Ryujinx stopped hosting
    (TCP 11452 refused), and one stuck. The Switch's own turns are never shown to the emulator, and aren't needed.
    Restarting the bridge while Ryujinx was searching crashed Ryujinx (`Cannot assign requested address`).
  - 2026-11-27: the bridge now asks the emulator every 0.2 s (was 1 s) and closes a turn after 2 unanswered scans
    (was 3), about 1 s instead of up to 4 s. Turns then opened and closed in step with Ryujinx (one open for 3.4 s,
    the next 5 s later), the Switch joined the second turn on its first try with no refused joins, and the consoles
    found each other in about 14 s instead of 30 s.
  - 2026-11-27: host mode is the default. `bridge emulator-hosts` no longer needs a scan capture: the game's ID comes
    from `local_communication_id` in `config.toml`, and the scene, player limit, app version and session data from the
    emulator. `deck/bridge.sh` and `deck/play.sh` run the mode set in `[launch]`, and `mode = "ask"` lets the
    shortcut ask. Stopping now takes under a second and ends with "Stopped." (it used to stall until a packet
    crossed the interface, and the service's restart loop got killed after 5 s). Started from the Steam shortcut, a
    Link Trade outside Union Circle connected.
- [ ] **M7 Real use** — trade, battle, Tera Raid; 30-minute soak test.
  - 2026-11-09: a Tera Raid inside Union Circle worked. The emulator's player started it at a den, the Switch's player
    joined, and both took turns. The bridge stayed joined for over 12 minutes with 1 failed frame in about 15,500
    sent. Battles and the Poké Portal's Tera Raid Battle are still untested.
  - The same evening, joins failed while the Switch's signal at the adapter was around -88 dBm and worked at -50 to
    -72 dBm. `iw dev ldn station dump` shows it while the bridge is joined.
  - `bridge switch-hosts --no-wait` now keeps one scan open until a session shows up, with 0.3 s per channel. It used
    to listen for 0.11 s per channel, exit, and start again about every 12 s.
  - 2026-11-10: the tested game's local play is UDP only. `python -m ldn_bridge traffic` counted what crossed `ldn`
    during a trade and a Tera Raid from a den, over two sessions with the Switch 2 hosting Union Circle (the first dropped
    with reason 6): 31,783 UDP packets, no TCP, no IPv4 fragments, 29 multicast, one other IP packet, and the largest
    UDP payload was 1,454 bytes. The counter ran with the interface's address unknown, so the broadcast count isn't
    meaningful.
  - 2026-11-15: two more Tera Raids from a den inside Union Circle, with the Switch 2 hosting Union Circle and Ryujinx
    started from the Game Mode shortcut. The emulator's player started both at a den. The Switch's player joined one
    directly, and joined the other through the Poké Portal's Tera Raid Battle menu while still in the group. Both
    battles finished.
  - Reported 2026-11-15: with the Switch 2 hosting Union Circle, everything tried inside it works. Trades, Tera Raids
    and Link Battles all work whichever console starts them. A battle hasn't been played to its full 7 minutes. Each
    player met Pokémon from the other version's encounter table (tested with version-exclusive Paradox Pokémon in Area
    Zero). Picnics, sandwich making and Blueberry Quests work too. Sessions drop if the adapter is moved much, which
    fits the signal-strength note above. Still untested: the Poké Portal's raid search outside Union Circle, which may
    take turns hosting like Link Trade.
  - 2026-11-27: the Poké Portal's Tera Raid Battle search works outside Union Circle when the Switch hosts. The Switch 2
    hosted a raid at a den, which gave it a Link Code, and `bridge switch-hosts` joined its session (scene 7). Ryujinx
    searched with the code. The first try stopped with error 2203-0064, and Ryujinx's log showed `Failed to connect.`
    followed by `LdnProxyTCPClient connected!` (the join race in M4). The first lobby then timed out. With a new lobby,
    the search worked and the raid finished. The raid lobby stays open while it waits, so it doesn't take turns hosting
    like Link Trade. When the raid ended, the Switch closed its session (reason 6) and the bridge went back to scanning.
  - 2026-11-27: Ryujinx crashed while closing after the game was quit and the adapter unplugged (a .NET worker thread
    aborted while writing a core dump). The order of the two isn't known.

## Windows through WSL
- [x] **W1 Radio from WSL** — the adapter, passed through by `usbipd-win`, scans and joins a Switch's session from WSL 2.
  2026-11-06: built the MT7612U driver for WSL kernel 6.18.33.1 and loaded its firmware through `/sys/class/firmware`.
  `scan` found the Switch 2's Union Circle session on channel 6, and `join` joined it. The adapter only worked once
  Windows' own driver was kept off it with `usbipd bind --force`. Steps are in `docs/WSL.md`.
- [x] **W2 Emulator on Windows** — let Ryujinx on Windows reach the bridge in WSL. It can't see the `ldn` interface,
  and bridging the two networks would send its traffic from an address the Switch never accepted, so the bridge relays
  it instead. `windows/ldn_tunnel.py` gives Windows a Wintun adapter with the bridge's LDN address and passes its IPv4
  packets to `bridge switch-hosts --windows` over 127.0.0.1. The bridge removes that address from `ldn`, sends the
  packets out with its own MAC, answers ARP and the emulator's Scan itself, and points the ScanResp at 127.0.0.1 so
  the TCP Connect reaches it through WSL's localhost forwarding.
  2026-11-06: Ryujinx 1.3.3 for Windows, Scarlet 4.0.0, joined the Switch 2's Union Circle session this way and
  worked. Then the Switch dropped the bridge (reason 6) and it couldn't hear the Switch again: range was much shorter
  than on the Deck, with the adapter in a PC's front USB port. Transmit power was 20 dBm, as on the Deck.
