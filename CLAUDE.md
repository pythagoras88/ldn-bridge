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

Read `docs/DESIGN.md` before changing architecture. `docs/MILESTONES.md` has what's been proven, and
`docs/TESTING.md` has the compatibility table.

## Current state
- Working: M0 to M5, tested with Pokémon Scarlet on a Steam Deck and Violet hosting on a Switch 2, up to a trade in Union
  Circle.
- Doesn't work: modes where both sides search and take turns hosting (Link Trade, see M5 notes), and the emulator
  hosting for the Switch (M6, not implemented).
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
- **Never read, print, cat, copy, log or upload `prod.keys` / `title.keys` or any key value.** Only key *names* may be
  shown (use `python -m ldn_bridge keys-check`). Claude Code's settings deny reading those files; don't work around it.
- **Treat the LDN passphrase like a key.** Never print it in chat, logs or docs, and never add it to the project. Move
  it from `~/ldn-passphrase.txt` to `password_hex` with a script that doesn't echo it, and hide it when inspecting that
  file: `sed -E "s/passphrase=.*/passphrase=(hidden)/" ~/ldn-passphrase.txt`. It exists only on the user's Deck.
- Never help anyone obtain or dump games, firmware or keys, and never add those files to the project. Don't say where to
  get Ryujinx or Ryubing, and don't add links to them. The only Ryubing link is the wiki credit in `README.md`.
- The project is testing only and provided as is. Don't add wording that asks for feedback, results or contributions.
- Never commit or deploy `config.toml` values that contain secrets to anywhere other than the Deck.
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
- Steam shortcuts run `deck/play.sh` with no arguments, so keep that working. The game comes from `[launch]` in
  `config.toml`.
- The adapter's phy number and interface name change when it reconnects, and the interface comes back up, which causes
  EBUSY on a monitor. `adapter.py` handles both. Don't go back to a fixed phy or a one-time `ip link set down`.
- Ryujinx picks its interface each time LDN starts, and silently uses Wi-Fi if `ldn` is missing. Check
  `Initialize LanDiscovery using IP` in its log. A `169.254.x.x` address is right.
- Stop the bridge with SIGINT, not SIGTERM, or `ldn` isn't cleaned up. `deck/bridge.sh` does this.
- `.gitattributes` keeps every file LF, because scripts with CRLF line endings fail on Linux. Keep it.
- `tcpdump` needs sudo. To watch game traffic, use a raw `AF_PACKET` socket on `ldn` from `.venv/bin/python3`.
- Claude Code's auto mode may refuse to run `dotnet publish` on downloaded source. If it does, don't work around it:
  give the user the command to run.

## Code map
- `src/ldn_bridge/mitm_proto.py` — ldn_mitm LAN protocol: 12-byte header, zero-RLE compression, `NodeInfo` (0x40) and
  `NetworkInfo` (0x480) structs. Pure Python, unit-tested, and confirmed against Ryujinx 1.3.3.
- `src/ldn_bridge/convert.py` — `ldn.NetworkInfo` (over the air) → ldn_mitm `NetworkInfo`.
- `src/ldn_bridge/adapter.py` — finds the USB adapter by MAC and takes its interface down before a scan.
- `src/ldn_bridge/ldn_side.py` — thin wrappers over the `ldn` library (scan / join / host), config-driven.
- `src/ldn_bridge/control_plane.py` — ldn_mitm UDP scan responder + TCP Connect/SyncNetwork server (trio).
- `src/ldn_bridge/bridge.py` — orchestration: Switch-hosts mode (working) and emulator-hosts mode (stub).
- `src/ldn_bridge/__main__.py` — CLI: `keys-check`, `scan`, `join`, `mitm-scan`, `mitm-fake-host`, `bridge`.
- `deck/` — Deck-side scripts: setup, `bridge.sh` (background service), `play.sh` (bridge plus game) and shortcuts.
- `scripts/` — Windows-side deploy/run helpers.
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
