# Testing notes

This project is for testing only and is provided as is, with no support. Only one setup has been confirmed.

Dump your own game and keys from your own Switch running custom firmware. How to dump games or keys, or where to get them
or an emulator, is out of scope for this project.

## What should work

Switch 1 games that use local wireless share Nintendo's LDN system, and the bridge doesn't depend on any particular game.
It handles finding and joining a session, then passes game traffic through unchanged. Other games may work, but only the
setup under [Tested so far](#tested-so-far) has been tried.

### What each game needs

- **Its own passphrase.** Capture it once with `docs/SETUP.md`, section 4.
- **The right session ID.** The bridge always sends the emulator `-1`, which is what the tested game uses. If the `lcid=`
  value in `~/ldn-passphrase.txt` isn't `ffffffffffffffff`, the session stays hidden until
  `EMULATOR_LOCAL_COMMUNICATION_ID` in `src/ldn_bridge/convert.py` is changed to that value.
- **A compatible update.** The emulator and console need versions of the game that can play together.

`config.toml` holds one game's passphrase at a time, so back up `password_hex` before replacing it.

### What can stop a game

| Limit | Which games it affects |
| --- | --- |
| **The console must host** | Games that only let the emulator host, because emulator hosting isn't implemented |
| **Sessions must stay open** | Games where both sides search and take turns hosting. The bridge can't join in time. |
| **Timing** | Fast games: the extra hop adds delay, and emulator slowdown can cause lag or disconnects |
| **Emulator support** | Games that run poorly in Ryujinx, or whose local play has bugs there |
| **Player identity** | Games stricter about the emulator's name and MAC not matching the bridge's |
| **One player per bridge** | Each Linux computer bridges one emulator, which takes one player slot |

### What the bridge doesn't cover

- **LAN mode** in some games is a separate system that runs over wired networking, not local wireless.
- **Native Switch 2 games** can't run on the emulator.
- **Online play** isn't part of this project.

## Checking a game

A game with a lobby the console can host is the easiest case. This first check needs no code changes.

1. Open the game's local multiplayer mode on the Switch, host a session, and stay on that screen near the computer.
2. In `config.toml`, set `protocols = [1, 3]`. Protocol 3 needs `master_key_12`, and `keys-check` shows if it's present.
3. Run `python -m ldn_bridge scan` about three times.

| Result | What it probably means |
| --- | --- |
| The session stays visible in every scan | The bridge can probably join it |
| The session comes and goes | The game probably takes turns hosting, so joining may fail |
| Nothing appears | The game may not be hosting, or may need a different mode |
| `protocol: 3` | The bridge has never joined one of these |

If the session stays visible, try to play it:

1. Capture the game's passphrase and check its session ID, as described above.
2. Run `python -m ldn_bridge join`. A line starting with `Joined` means the passphrase is right.
3. Start the bridge and join from the game on the emulator.

## Privacy

Never share key files, `config.toml` or a passphrase. Raw logs and captures can contain player names, MAC addresses and
network details.

## Tested so far

**Setup:** Steam Deck on SteamOS 3.9.5, Alfa AWUS036ACM Long-Range Dual-Band AC1200 USB 3.0 adapter (MT7612U chip,
2.4 GHz and 5 GHz, 2x 5 dBi antennas), and Ryujinx 1.3.3.

**Game:** Pokémon Scarlet v4.0.0 on the Steam Deck, with Pokémon Violet hosting on a Switch 2.

| Feature | Status | Notes |
| --- | --- | --- |
| Union Circle: join and see each other move | Works | |
| Trade inside Union Circle | Works | One trade completed |
| Normal Ryujinx 1.3.3 with the shortcut | Works | Joined Union Circle. Play wasn't separately confirmed. |
| Poké Portal Link Trade search | Fails | Short sessions, and the Switch can't join the emulator |
| Violet on the emulator, Scarlet on the Switch | Untested | |
| Battles and Tera Raids | Untested | |
| Sessions over about 30 minutes | Untested | |
| Steam Deck Game Mode | Untested | Likely used once, but not confirmed |

**Everything else is untested:** any other game, the original Switch, any Linux computer other than a Steam Deck, and
any adapter other than the Alfa AWUS036ACM. Emulator hosting isn't implemented.
