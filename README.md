<div align="center">

# LDN Bridge

**Local wireless between an unmodified Switch and a Linux PC running an emulator.**

![Testing only](https://img.shields.io/badge/testing-only-red)
![Provided as is](https://img.shields.io/badge/provided-as%20is-lightgrey)
![Platform: Linux](https://img.shields.io/badge/platform-Linux-555555)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776ab)
![License: GPLv3](https://img.shields.io/badge/license-GPLv3-blue)

[Requirements](#requirements) · [Setup](#setup) · [Playing](#playing) · [Compatibility](#compatibility) · [Troubleshooting](#troubleshooting)

</div>

> [!CAUTION]
> **This project is for testing only and is provided as is, with no support.**
>
> **You must dump your own game and keys from your own Switch running custom firmware.** This project includes no game
> files, firmware, keys, passphrases or emulator builds.
>
> **Don't ask how to dump games or keys, or where to get them or an emulator.** That is out of scope for this project,
> and those questions won't be answered.

## Overview

Nintendo's local wireless and the `ldn_mitm` multiplayer mode in Ryujinx use different protocols, so an emulator can't
normally see a nearby Switch. LDN Bridge connects the two.

A USB Wi-Fi adapter joins the Switch's session using Nintendo's over-the-air protocol, through kinnay's
[`ldn`](https://github.com/kinnay/LDN) library. The bridge presents that session to the emulator. Only discovery and
membership are translated, and game traffic passes through unchanged.

```
                         Linux PC
           ┌────────────────────────────────────────┐
 Switch ~~~│~~> USB adapter -> LDN Bridge -> Ryujinx│
 (hosts)   │                                ldn_mitm│
           └────────────────────────────────────────┘
```

## Requirements

- A Linux PC with Python 3.11 or later and a driver for your adapter. A Steam Deck works.
- A USB Wi-Fi adapter with monitor mode and injection. See [Tested with](#tested-with).
- Ryujinx with `ldn_mitm` mode. Ryubing 1.3.3 is the tested build.
- Your own game and keys, dumped from your own Switch running custom firmware.
- Compatible game updates on the emulator and the Switch.
- The .NET 9 SDK, once per game, to capture its passphrase.

## Setup

The [setup guide](docs/SETUP.md) has every command, including how to work from Windows over SSH. With
[Claude Code](https://claude.com/claude-code), `CLAUDE.md` provides the project context.

**1. Prepare the computer.** Plug in the adapter and run:

```bash
git clone https://github.com/pythagoras88/ldn-bridge.git ~/ldn-bridge
cd ~/ldn-bridge
bash deck/find_adapter.sh            # note the adapter's MAC
sudo bash deck/nm_unmanage.sh <MAC>  # NetworkManager leaves only the adapter alone
bash deck/setup.sh                   # Python environment and the ldn library
sudo bash deck/grant_caps.sh         # lets the bridge control the adapter without sudo
cp config.example.toml config.toml   # set adapter_mac, keys_path and [launch]
```

The `deck/` folder is named after the first test machine. Its scripts also work on other Linux computers, apart from the
notes in the setup guide.

**2. Check your keys.** This prints key names only, never their values:

```bash
. .venv/bin/activate && python -m ldn_bridge keys-check
```

**3. Capture the game's passphrase.** Follow [section 4 of the setup guide](docs/SETUP.md#4-capture-the-passphrase), then
put it in `config.toml` as `password_hex`.

**4. Configure Ryujinx.** Under **Settings > Network**, set Mode to `ldn_mitm` and turn Guest Internet Access off.

**5. Install the shortcuts.**

```bash
bash deck/install_shortcuts.sh
```

> [!TIP]
> Network Interface must be set to `ldn`, but that name only appears while the bridge is joined. Set it during your
> first session and Ryujinx remembers it.

## Playing

1. Plug in the adapter.
2. Host a local multiplayer session on the Switch.
3. Run **Play with LDN Bridge**. It starts the bridge and the emulator, and closing the emulator stops the bridge.
4. Join the session from the game on the emulator.

The Switch has to host. The bridge keeps looking for a session and rejoins after a disconnect, but the game has to rejoin
the session itself.

<details>
<summary><strong>Choosing the game and emulator</strong></summary>

<br>

Set these in `config.toml`. If `game` is empty, the emulator opens its game list:

```toml
[launch]
emulator = "~/Applications/ryujinx-1.3.3-x64.AppImage"
game = "~/Games/your-game.nsp"
```

</details>

<details>
<summary><strong>Steam Deck</strong></summary>

<br>

In Desktop Mode, right-click **Play with LDN Bridge** in the application menu and choose **Add to Steam**. Then run it from
your library in Game Mode, and exit with **Steam button > Exit Game**. The bridge stops by itself. Use the charger for long
sessions.

</details>

## Compatibility

The bridge isn't tied to one game. Switch 1 games that use local wireless share the same system, so others may work, but
only the setup under [Tested with](#tested-with) has been confirmed.

Each game needs its own passphrase, a compatible update on both sides, and the right session ID. The bridge sends the ID
used by the tested game, so some games need a small code change. [Testing notes](docs/TESTING.md) has the details.

| Limit | What it means |
| --- | --- |
| The Switch must host | Emulator hosting isn't implemented, so the Switch can't join the emulator |
| Sessions must stay open | Games where both sides search and take turns hosting may never connect |
| Timing | Fast games may lag or disconnect from the extra hop and emulator slowdown |
| Emulator support | The game has to run well in Ryujinx, including its local play |
| One player per bridge | Each Linux PC bridges one emulator, which takes one player slot |

**Not covered:** LAN mode, which is a separate wired system, native Switch 2 games, and online play.

## Troubleshooting

| Problem | Likely fix |
| --- | --- |
| The session doesn't appear in the game | Set Network Interface to `ldn`. If local multiplayer opened before the bridge joined, Ryujinx silently uses your normal network, so close it and reopen it. Its log should show a `169.254.x.x` address. |
| Still hidden after that | Check the game's session ID. See [what each game needs](docs/TESTING.md#what-each-game-needs). |
| A short search finds nobody | The game may take turns hosting. Use a mode where the Switch hosts and waits, if it has one. |
| `join` times out at authentication | `password_hex` is wrong or missing, or a game update changed the passphrase. Capture it again. |
| The emulator logs `Failed to connect` | Join again. This looks like a timing bug in Ryujinx, and the next attempt worked. |
| `scan` finds nothing | Keep the session open on the Switch, near the computer. Then check the adapter with `deck/find_adapter.sh`. |
| `Operation not permitted` | Run `sudo bash deck/grant_caps.sh`. Run it again after recreating `.venv`. |
| The session drops | Check the adapter and any hub are firmly connected, and that the computer has stable power. |

## Commands

<details>
<summary><strong>Command reference</strong></summary>

<br>

Run these in `~/ldn-bridge` with `.venv` active:

```bash
python -m ldn_bridge keys-check            # are the required keys present?
python -m ldn_bridge scan                  # list nearby Switch sessions
python -m ldn_bridge join                  # join a session and print events
python -m ldn_bridge mitm-scan --bind 127.0.0.1 --broadcast <emulator IP>   # decode the emulator's session
python -m ldn_bridge bridge switch-hosts   # run the bridge in the foreground

bash deck/bridge.sh start|stop|watch       # run the bridge as a background service
bash deck/play.sh                          # bridge plus emulator; stops when the emulator closes
```

Unit tests run on Windows or Linux. Two of them need Linux:

```bash
python -m unittest discover -s tests -v
```

</details>

## Project layout

```
src/ldn_bridge/   the bridge
deck/             setup and launch scripts for the Linux computer
scripts/          deploy and run helpers for working from Windows (Git Bash)
docs/             setup, testing notes, design, protocol notes and milestones
docs/patches/     Ryujinx 1.3.3 patch for capturing a game's passphrase
tests/            unit tests
CLAUDE.md         project rules and context for Claude Code
```

## Safety

- Never share `prod.keys`, `title.keys`, `config.toml` or a captured passphrase.
- Raw logs and captures can contain player names and MAC addresses.
- `scripts/deploy.sh` never copies `config.toml`, and `.gitignore` excludes it.
- Don't stop NetworkManager if you're connected over Wi-Fi. `deck/nm_unmanage.sh` only excludes the adapter.

## Credits

- [kinnay/LDN](https://github.com/kinnay/LDN), the local wireless library this project is built on
- [ldn_mitm](https://github.com/spacemeowx2/ldn_mitm), for the LAN protocol
- Ryubing, for Ryujinx and its `ldn_mitm` mode ([multiplayer wiki](https://git.ryujinx.app/projects/Ryubing/wiki/Multiplayer-%28LDN-Local-Wireless%29-Guide))
- [Nintendo wiki by Pretendo](https://nintendo-wiki.pretendo.network/), for protocol documentation

## License and legal

Copyright (C) 2026 pythagoras88. Licensed under the [GNU General Public License v3.0](LICENSE).

This project depends on `ldn` and `python-netlink`, which are GPLv3. `src/ldn_bridge/mitm_proto.py` implements a protocol
described in the `ldn_mitm` (GPLv2) and Ryujinx (MIT) sources. The patch in `docs/patches/` modifies MIT-licensed Ryujinx
code.

This is an unofficial project and isn't affiliated with or endorsed by Nintendo or any game publisher. All trademarks
belong to their owners. It's provided as is, for testing only, and only with a game and keys you dumped yourself from your
own Switch.

## Tested with

| | |
| --- | --- |
| **Game** | Pokémon Scarlet on a Steam Deck, with Pokémon Violet on a Switch 2 |
| **Result** | Joined Union Circle, saw each other move, and completed a trade |
| **Doesn't work** | Poké Portal Link Trade search: trade through Union Circle instead |
| **Computer** | Steam Deck on SteamOS 3.9.5 |
| **Adapter** | Alfa AWUS036ACM Long-Range Dual-Band AC1200 USB 3.0 (MT7612U chip) |
| **Emulator** | Ryujinx 1.3.3 |

Everything else is untested, including battles, Tera Raids, long sessions, other games, the original Switch, and other
Linux computers. [Testing notes](docs/TESTING.md#tested-so-far) has the full list.

---

<div align="center">

made with love, by claude

</div>
