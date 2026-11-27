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
- **Its ID, for host mode.** `local_communication_id` under `[game]` in `config.toml`. `scan` shows it while a Switch
  hosts the game, and the passphrase capture shows it as `lcid=`.
- **A compatible update.** The emulator and console need versions of the game that can play together.

`config.toml` holds one game's passphrase at a time, so back up `password_hex` before replacing it.

### What can stop a game

| Limit | Which games it affects |
| --- | --- |
| **One direction at a time** | Host mode (the default) shows the emulator's sessions to the Switch but not the other way round. To join a session only the console can host, pick join mode. |
| **Turn-based searches in join mode** | Games where both sides search and take turns hosting can't connect in join mode. Use host mode, where the console joins one of the emulator's turns. |
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
| Trade inside Union Circle | Works | Started from either console |
| Normal Ryujinx 1.3.3 with the shortcut | Works | Joined Union Circle in join mode. Play wasn't separately confirmed. The shortcut now starts host mode by default. |
| Play with LDN Bridge in host mode, no scan capture | Works | Steam shortcut on the Deck: the bridge hosted with the game ID from `config.toml`, reset the adapter, and a Link Trade outside Union Circle connected. |
| The shortcut's who-hosts question in Game Mode | Works | `mode = "ask"` opens a zenity window before the emulator, and an answer was picked in Game Mode (the bridge started 9 s after the shortcut, inside the 15 s timeout). With no answer the emulator hosts. |
| Poké Portal Link Trade search | Works | `bridge emulator-hosts`, both consoles searching with the same Link Code. Ryujinx takes hosting turns of about 3 s; the bridge shows them to the Switch, which joins one. Found each other after about 14 s (30 s before turns were tracked faster), and trades finished. The Switch's own hosting turns are never shown to the emulator. Without a code it wasn't tried after the fix below. |
| Restarting the bridge while the game on the emulator is in local play | Fails | Ryujinx 1.3.3 crashed (`Cannot assign requested address`) when the `ldn` interface went away during a Link Trade search. Leave local play before restarting the bridge. |
| Game on the emulator starts hosting while the bridge is joined | Fails | Ryujinx crashes with `Address already in use` on TCP 11452 and the game freezes. Join the Switch's session instead of hosting from the emulator. See M5 in `docs/MILESTONES.md`. |
| Emulator hosts, Switch joins | Works | `bridge emulator-hosts`, with Scarlet on the emulator hosting Union Circle and the Switch 2 joining with its code. Trades both ways and a Tera Raid from a den, started on the emulator, worked at normal speed. A session joined with `bridge switch-hosts` leaves a key in the adapter's chip that garbles the Switch's broadcasts, and the Switch then waits on "searching". `bridge emulator-hosts` now resets the adapter over USB before hosting, which clears it like a replug, and warns if the broadcasts still can't be read. Tested: after a joined session, hosting reset the adapter and the Switch joined and played, with no replug. See M6 in `docs/MILESTONES.md`. |
| Switch joins a session hosted by the adapter | Works | `host-test` only, with a copied Union Circle session and no emulator. Needs the code from the capture. The Switch then stops with error 2318-0533, because no game answers. |
| Violet on the emulator, Scarlet on the Switch | Untested | |
| Tera Raid from a den inside Union Circle | Works | Started from either console. Joining through the Poké Portal's Tera Raid Battle menu while in the group works too. |
| Link Battle inside Union Circle | Works | Started from either console. A battle hasn't been played to its full 7 minutes. |
| Encounters from the other version inside Union Circle | Works | Each player met the other version's exclusive Paradox Pokémon in Area Zero |
| Picnic and sandwich making inside Union Circle | Works | |
| Blueberry Quests inside Union Circle | Works | |
| Moving the adapter during a session | Fails | Moving it much can drop the session. Keep it still and in range of the Switch. |
| Local play traffic is UDP only | Works | Trade and Tera Raid in Union Circle: no TCP, no fragments, largest UDP payload 1,454 bytes. Counted with `python -m ldn_bridge traffic`. See M7 in `docs/MILESTONES.md`. |
| Tera Raid Battle search from the Poké Portal, outside Union Circle | Works | The Switch hosted a raid at a den with a Link Code, and the emulator searched with that code through `bridge switch-hosts`. The raid finished. The first try stopped with error 2203-0064 (Ryujinx's join race, see the next row); searching again worked. |
| Tera Raid Battle search from the Poké Portal, emulator hosts | Works | `bridge emulator-hosts`: the emulator's player hosted a raid at a den with a Link Code, and the Switch searched with it from the Poké Portal. The raid finished on both. The bridge copies the emulator's scene (7 for a raid, 5 for Union Circle) into the hosted session. |
| Joining from the emulator on the first try | Fails sometimes | Ryujinx 1.3.3 can log `Failed to connect.` and then `LdnProxyTCPClient connected!`, and the game stops with error 2203-0064. This is on the emulator's side. Search or join again. |
| Sessions over about 30 minutes | Untested | |
| Steam Deck Game Mode | Works | Joined Union Circle from the Play with LDN Bridge shortcut and stayed connected for about 40 minutes |
| Deck's built-in Wi-Fi while in Game Mode | Fails | With the USB adapter plugged in at boot, the built-in Wi-Fi stayed disconnected for the whole session. The bridge wasn't affected. See M5 in `docs/MILESTONES.md`. |
| Windows 11 with WSL 2: scan and join | Works | Bridge only, no emulator. Same adapter passed through by usbipd-win. See `docs/WSL.md`. |
| Windows 11 with WSL 2: emulator on Windows | Works | Ryujinx 1.3.3 for Windows joined Union Circle through `windows/ldn_tunnel.py`. Range was much shorter than on the Deck, and the session dropped. See W2 in `docs/MILESTONES.md`. |

**Everything else is untested:** any other game, the original Switch, any Linux computer other than a Steam Deck, and
any adapter other than the Alfa AWUS036ACM. Emulator hosting has only been tried with Union Circle and one Tera Raid.
