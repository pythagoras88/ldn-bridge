# kinnay/LDN library notes

Source: https://github.com/kinnay/LDN (docs: https://ldn.readthedocs.io). Read from source at v0.0.21 (master,
Oct 2026). The docs page lags the source in places (e.g. `security_level` is `security_mode` in code).

Install from GitHub master, not PyPI (PyPI can lag):
`pip install https://github.com/kinnay/LDN/archive/refs/heads/master.zip` — depends on `python-netlink==0.0.15`,
`pycryptodome`, `trio`.

## API used here
- `ldn.load_keys(path) -> dict[str, bytes]` — parses `prod.keys`.
- `await ldn.scan(keys, ifname="ldn", phyname="phy0", channels=[1,6,11], dwell_time=.110, protocols=[1,3])`
  → `list[NetworkInfo]`. Creates a monitor interface on `phyname`. LDN uses 7 channels: 1, 6, 11, 36, 40, 44, 48.
- `async with ldn.connect(ConnectNetworkParam) as sta:` — creates a **station-mode** interface `ifname`, joins,
  assigns `169.254.N.k/24` (N = 3rd octet of the host's IP), adds static neighbours. `sta.info()`,
  `sta.participant()`, `sta.broadcast_address()`, `await sta.next_event()` → `JoinEvent`, `LeaveEvent`,
  `DisconnectEvent`, `ApplicationDataChanged`, `AcceptPolicyChanged`.
- `async with ldn.create_network(CreateNetworkParam) as ap:` — monitor-mode AP (`ifname` + `ifname_active`) plus
  TAP `ifname_tap` (MTU 1400) with host IP `169.254.N.1`. `ap.set_application_data()`, `ap.kick()`,
  `await ap.next_event()` → Join/Leave.

## NetworkInfo fields (source)
`protocol, address (host MAC), band, channel, local_communication_id, scene_id, ssid (16 bytes), version,
server_random, security_mode, app_version, accept_policy, max_participants, num_participants, participants[8],
application_data, challenge, nonce`.
ParticipantInfo: `ip_address, mac_address, connected, name (bytes), app_version, platform (0 NX, 1 Ounce = Switch 2)`.

## Keys needed (from `KeyDerivation`)
- Always: `aes_kek_generation_source`, `aes_key_generation_source`.
- Protocol 1 (Switch 1 games): `master_key_00` — present in every prod.keys dump, however old.
- Protocol 3: `master_key_12` — needs a dump from a newer firmware.

## Passphrase
Data-frame key = derive(server_random + passphrase). Games pick their own passphrase (Mario Kart 8 Deluxe:
`MarioKart8Delux` + 17 NUL bytes; Super Mario Maker 2: `LunchPack2DefaultPhrase` — from
https://nintendo-wiki.pretendo.network/docs/pia/ldn/passphrases). Scarlet/Violet is not listed, and joining with an
empty passphrase times out at authentication. Its 64-byte passphrase, read from the emulator (M2b), works on Violet.

## Gotchas
- Default `phyname` is `phy0` = Deck's internal Wi-Fi. Always pass the USB adapter's phy.
- Needs `CAP_NET_ADMIN` (+ raw sockets). NetworkManager must not touch the adapter or the `ldn*` interfaces.
- `ConnectNetworkParam.check()` rejects networks whose `version` isn't 2, 3 or 4.
- The station listens to nl80211 MLME events from every Wi-Fi interface and doesn't check the interface index. When
  the computer's own Wi-Fi switches routers, the station removed on that interface ends the LDN session as
  `DisconnectEvent(reason=6)`. `ldn_side._own_messages_only` replaces `Station._process_messages` and ignores events
  for other interfaces. Confirmed on a Steam Deck on 2026-11-07: two sessions ended within 60 ms of the built-in Wi-Fi
  roaming. The join loop in `Station` reads `NL80211_CMD_CONNECT` without the same check, which hasn't been seen to
  cause a failure.
