# LDN Bridge — project context for Claude Code

## What this is
A tool for playing **local wireless** between an **unmodified** Switch / Switch 2 and a Linux PC running a Switch
emulator (a Ryujinx fork in **ldn_mitm** multiplayer mode). It isn't tied to one game, and each game supplies its own
passphrase. Describe it that way in user-facing docs, and keep named games to the "Tested" sections.

The bridge runs on Linux with a **USB Wi-Fi adapter** that supports monitor mode + injection. It's tested on a **Steam
Deck** (SteamOS = Arch Linux) with an Alfa AWUS036ACM (MT7612U). Other Linux computers should work but are untested. It
uses kinnay's `ldn` Python library to speak Nintendo's real over-the-air LDN protocol, and speaks the ldn_mitm LAN
protocol to the emulator, which must run on the same computer. `deck/` and the `deck` SSH alias are named after the first
test machine, and "the Deck" below means whichever Linux computer is in use.

Read `docs/DESIGN.md` before changing architecture. `docs/PLAN.md` has what's finished and what's left, in order.
`docs/MILESTONES.md` has what's been proven, and `docs/TESTING.md` has the compatibility table. The current focus is
Ryujinx on a Steam Deck only, so don't start work on other platforms or emulators until the plan reaches them.

## Current state
- Working: M0 to M5, tested with Pokémon Scarlet on a Steam Deck and Violet hosting on a Switch 2, up to a trade in Union
  Circle and a Poké Portal raid search. M6 too: the emulator hosts Union Circle and the Switch joins, trades and raids.
- Link Trade works through `bridge emulator-hosts`: the emulator's hosting turns reach the Switch, and a search takes
  about 14 s.
- Don't restart the bridge while the emulator's game is in local play: Ryujinx crashes when `ldn` goes away.
- Emulator hosting (`bridge emulator-hosts`) resets the adapter first, because a joined session leaves a key in the
  MT7612U's chip that garbles the Switch's broadcasts. Tested: hosting right after a joined session works.
- Untested: everything else, including other games, the original Switch and other Linux computers.
  `docs/TESTING.md` has what each game needs and what can stop it.
- The project is licensed GPLv3 and lives at `pythagoras88/ldn-bridge` on GitHub. Write everything here for public
  readers, and don't add notes about individuals, private arrangements or a specific person's setup.
- Keep `Co-Authored-By: Claude` in commits, but leave out any Claude session link.
- Commit as `pythagoras88` with `63681651+pythagoras88@users.noreply.github.com`, and check
  `git log --format='%an <%ae>'` before pushing.

## Helping someone new
Most users here are new to this project and may be new to the terminal, and every Deck is different. Don't assume
anything from the docs' examples: check the phy, MAC, paths and versions on their machine. Follow
`docs/SETUP.md` in order.
- **Never ask for the Deck password in chat.** Make an SSH key and a `deck` alias, then have them install the key by
  typing their password in their own terminal. The password prompt may not work through the `!` prefix.
- Ask what's physically true before planning: Deck or other Linux, adapter chip, console model, emulator version, and
  which game and update each side runs. Both sides need the same update.
- Do the non-sudo steps yourself. Give them the exact `sudo` commands to run, in one line where you can.
- Be exact with on-screen steps: name the menu, say what they should see, and say what to do if they don't see it.
- If they test something on their copy, record the result in `docs/TESTING.md` and `docs/MILESTONES.md`. Mark it as Works
  or Fails only from a real result. Keep expectations marked Untested.
- Don't print `config.toml`, logs or captures where others can see them: they can contain the passphrase, player names
  and MACs.

## How it's run
- The usual setup is **Claude Code on Windows** (Git Bash shell) with the code **running on the Deck** over SSH.
- Edit files locally, then `bash scripts/deploy.sh` copies the project to the Deck (`~/ldn-bridge`).
- Run anything on the Deck with `bash scripts/deck.sh "<command>"` (runs inside `~/ldn-bridge` with the venv active).
- Pull logs/captures back with `bash scripts/pull.sh`.
- Pure-Python unit tests (`tests/`) run on Windows too: `python -m unittest discover -s tests -v`.
- SSH settings live in `scripts/deck.env` (copy from `scripts/deck.env.example`). Default host alias: `deck`.
- Slash commands: `/milestone`, `/deploy <command>` and `/deck-logs`.

## Hard rules
- **Never read, print, cat, log or upload `prod.keys` / `title.keys` or any key value.** Only key *names* may be
  shown (use `python -m ldn_bridge keys-check`). Claude Code's settings deny reading those files; don't work around it.
- When the user asks, copy the keys file or `config.toml` between the user's own computers (the Deck, other Linux
  computers, WSL), for example `ssh deck 'cat <file>' | wsl.exe sh -c 'cat > <dest>'` or `scp`. Pipe it from machine
  to machine and never into the output. Keep the destination's permissions private (`chmod 600`). Never copy it
  anywhere else.
- **Treat the LDN passphrase like a key.** Never print it in chat, logs or docs, and never add it to the project. Move
  it from `~/ldn-passphrase.txt` to `password_hex` with a script that doesn't echo it, and hide it when inspecting that
  file: `sed -E "s/passphrase=.*/passphrase=(hidden)/" ~/ldn-passphrase.txt`. It exists only on the user's own computers.
- Never help anyone obtain or dump games, firmware or keys, and never add those files to the project. Don't say where to
  get Ryujinx or Ryubing, and don't add links to them. The only Ryubing link is the wiki credit in `README.md`.
- The project is testing only and provided as is. Don't add wording that asks for feedback, results or contributions.
- Never commit or deploy `config.toml` values that contain secrets to anywhere other than the user's own computers.
- Commands that need root on the Deck (setcap, NetworkManager config, `ip link`) are in `deck/*.sh`. Ask the user before
  running anything with `sudo`; it prompts for the Deck password and can't run unattended over `deck.sh` unless they've
  set it up. Prefer telling them the exact command to run in an SSH session.
- Don't stop NetworkManager on the Deck: the internal Wi-Fi carries the SSH session. Use `deck/nm_unmanage.sh` so NM
  ignores only the USB adapter.
- The library's default `phyname` is `phy0`, which on the Deck is the **internal** card. Always pass the USB adapter's
  phy, which `ldn_side.scan` resolves from `adapter_mac` in `config.toml` (`deck/find_adapter.sh` shows the MAC).

## Facts learned the hard way
- `.venv/bin/python` must stay a symlink to `python3`. Only `python3` has the capabilities; `deck/setup.sh` handles this.
- A game's passphrase is required: an empty one times out at authentication. Each game has its own, and `config.toml`
  holds one at a time.
- The tested game uses session ID `-1` on the emulator and ldn_mitm mode doesn't resolve it, so `convert.py` always sends
  `-1` as `EMULATOR_LOCAL_COMMUNICATION_ID`. Another game may need its real ID, so make this per-game before relying on it.
- Steam shortcuts run `deck/play.sh` with no arguments, so keep that working. The game and the mode (`host` by
  default, or `join`) come from `[launch]` in `config.toml`; `LDN_MODE` overrides the mode. Host mode needs
  `local_communication_id` under `[game]` (or a scan capture).
- The adapter's phy number and interface name change when it reconnects, and the interface comes back up, which causes
  EBUSY on a monitor. `adapter.py` handles both. Don't go back to a fixed phy or a one-time `ip link set down`.
- Ryujinx picks its interface each time LDN starts, and silently uses Wi-Fi if `ldn` is missing. Check
  `Initialize LanDiscovery using IP` in its log. A `169.254.x.x` address is right.
- Stop the bridge with SIGINT, not SIGTERM, or `ldn` isn't cleaned up. `deck/bridge.sh` does this.
- Even SIGINT mid-scan can leave `ldn` on the adapter, and every scan after that fails with `Errno 23 Too many open
  files in system`. `ldn_side.remove_leftovers` deletes it before each scan.
- Saving Ryujinx's Settings while `ldn` is missing resets Network Interface to Default, which means Wi-Fi.
  `deck/play.sh` sets `multiplayer_lan_interface_id` back in `~/.config/Ryujinx/Config.json` before each launch.
- Ryujinx 1.3.3 can log `Failed to connect.` then `LdnProxyTCPClient connected!` when joining: its `Connect()` returns
  as soon as the socket stops "connecting", which can be before it's marked connected. That's on the emulator's side,
  and retrying the join in the game is the workaround.
- `.gitattributes` keeps every file LF, because scripts with CRLF line endings fail on Linux. Keep it.
- A key left in the MT7612U from an earlier session makes its chip decrypt the Switch's broadcasts with the wrong key
  when hosting: the frames keep the Protected bit, lose the CCMP header and MIC, and read as garbage. Replugging the
  adapter or a USB reset clears it, and `adapter.reset` does that before hosting (no sudo needed while the user is
  logged in on the Deck; `deck/usb_access.sh` adds a udev rule otherwise). A `switch-hosts` session leaves the key; a
  hosting session doesn't. The
  chip also passes correctly decrypted frames to monitor interfaces with the Protected bit set.
- `tcpdump` needs sudo. To watch game traffic, use a raw `AF_PACKET` socket on `ldn` from `.venv/bin/python3`.
- Claude Code's auto mode may refuse to run `dotnet publish` on downloaded source. If it does, don't work around it:
  give the user the command to run.

## Code map
- `install.sh` — one-step setup: copies itself to `~/ldn-bridge`, venv, adapter, `config.toml`, Ryujinx settings, one
  `sudo` prompt, shortcuts and Steam. Settings are written by `src/ldn_bridge/install_config.py` (pure Python, tested).
- `src/ldn_bridge/mitm_proto.py` — ldn_mitm LAN protocol: 12-byte header, zero-RLE compression, `NodeInfo` (0x40) and
  `NetworkInfo` (0x480) structs. Pure Python, unit-tested, and confirmed against Ryujinx 1.3.3.
- `src/ldn_bridge/convert.py` — `ldn.NetworkInfo` (over the air) → ldn_mitm `NetworkInfo`.
- `src/ldn_bridge/adapter.py` — finds the USB adapter by MAC and takes its interface down before a scan.
- `src/ldn_bridge/ldn_side.py` — thin wrappers over the `ldn` library (scan / join / host), config-driven.
- `src/ldn_bridge/control_plane.py` — ldn_mitm UDP scan responder + TCP Connect/SyncNetwork server (trio).
- `src/ldn_bridge/bridge.py` — orchestration: emulator-hosts mode ("host", the default) and switch-hosts mode ("join").
- `src/ldn_bridge/hosting.py` — hosted session settings from a `scan` capture, and tracking of the emulator's session.
  Pure Python, unit-tested.
- `src/ldn_bridge/emulator_link.py` — ldn_mitm client: sends Scan and Connect to the emulator from `127.0.0.1` (trio).
- `src/ldn_bridge/__main__.py` — CLI: `keys-check`, `scan`, `join`, `host-test`, `mitm-scan`, `mitm-fake-host`, `bridge`.
- `deck/` — Deck-side scripts: setup, `bridge.sh` (background service), `play.sh` (bridge plus game) and shortcuts.
- `scripts/` — Windows-side deploy/run helpers.
- `wsl/` — WSL 2 on Windows: building and loading the MT7612U driver, and `bridge_windows.sh`. See `docs/WSL.md`.
- `windows/ldn_tunnel.py` — runs on Windows as Admin: a Wintun adapter for Ryujinx, relayed to the bridge in WSL.
  `windows/play.ps1` is the one-click launcher for the whole Windows setup.
  Keeps its own copy of the `tunnel_proto.py` framing.
- `src/ldn_bridge/windows_link.py` — the WSL end of that relay (`bridge switch-hosts --windows`). Linux only.
- `src/ldn_bridge/packets.py`, `tunnel_proto.py` — Ethernet/ARP/IPv4 helpers and the relay's framing. Pure Python,
  unit-tested.
- `scripts/wsl_sync.sh` — copies the project into WSL, like `deploy.sh` does for the Deck.
- `docs/patches/` — Ryujinx 1.3.3 patch: captures the passphrase and repoints moved package sources. Apply it with
  `git apply --ignore-whitespace`.
- `third_party/` — gitignored, never deployed, and may not exist: local read-only sources of `ldn_mitm`, `LDN` and
  Ryubing. Check real behaviour there when it's present.
- `tests/test_control_plane.py` needs Linux and trio, so it skips on Windows. The `ldn` library can't import on Windows
  (`fcntl`), so `ldn_side` and `bridge` can only be imported on Linux.

## Conventions
- Python ≥ 3.11, async with **trio** (the `ldn` library uses trio; don't mix in asyncio).
- Log with `logging`; every CLI command writes a log file under `logs/` on the Deck.
- Packet captures go in `captures/` (gitignored). Never put keys or passphrases in captures' filenames or logs.
- When a protocol assumption is confirmed or disproved by a real capture, update `docs/LDN_MITM_PROTOCOL.md` or
  `docs/LDN_LIBRARY.md` and tick the item in `docs/MILESTONES.md`.
