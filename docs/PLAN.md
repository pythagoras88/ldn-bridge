# Plan

Where the project stands and what's left. The current focus is **Ryujinx on a Steam Deck**. Other platforms and
emulators wait until that works fully. Test results and dated notes are in `docs/MILESTONES.md`, and the compatibility
table is in `docs/TESTING.md`.

## Finished

| Milestone | What it proved |
| --- | --- |
| M0 Setup | The Deck, the adapter, the `ldn` library and the keys work together |
| M1 See the Switch | `scan` finds a Switch's Union Circle session over the air |
| M2b Get the passphrase | A patched Ryujinx captures the game's passphrase, and `join` gets a node on the Switch |
| M3 Learn the emulator side | The ldn_mitm protocol from Ryujinx 1.3.3 decodes as expected |
| M4 Discovery bridge | Ryujinx lists the Switch's session through the bridge |
| M5 Play | Ryujinx joins the Switch's Union Circle: players see each other move and can trade. Works from Game Mode too. |
| M6a Can the adapter host? | The MT7612U can host a session that a Switch joins |
| M6 Emulator hosts | Ryujinx hosts and the Switch joins: Union Circle, trades both ways, Tera Raids. The bridge resets the adapter first, which clears a key a joined session leaves in its chip. |
| Host mode by default | `deck/play.sh` asks who hosts (`mode = "ask"`), hosts with the game's ID from `config.toml`, and stops cleanly in under a second |
| Poké Portal raids | The Tera Raid search outside Union Circle works whichever console hosts |
| Link Trade | Ryujinx's short hosting turns reach the Switch, which joins one. With a code, partners find each other in about 14 s. |
| W1, W2 Windows through WSL | Ryujinx on Windows joins through the bridge in WSL 2. Paused until the Deck work is done. |

Not needed: **M2a** (an empty passphrase can't work, so M2b replaced it) and **M3b** (a fake host, made unnecessary by
M4).

## Left, in order

### 1. M7 Real use

Needed:
- A Link Battle played to its full 7 minutes.
- A 30-minute session with active play (trades, raids or battles), in host mode. This also covers M6b: every hosted
  frame goes through Python, so a long session shows whether that keeps up.
- Link Trade without a code.
- Retesting a fix that hasn't been tried in a game yet: turning off Steam's Vulkan layers for the emulator in
  `deck/play.sh`. Ignoring Wi-Fi events from the Deck's built-in card was only needed in join mode.

Done when: all of these are recorded in `docs/TESTING.md`, and the 30-minute session completes without a drop caused by
the bridge.

### 2. Hosting from the emulator while joined (join mode only)

In join mode, if the game on the emulator starts hosting while the bridge is joined, Ryujinx crashes. It can't bind TCP
11452 on the `ldn` address, because the bridge's control plane already uses it, and Ryujinx doesn't catch the error.
Host mode doesn't have this problem, and it's the default.

Needed: a way for the game to get a normal failure instead of a crash. That might come from the bridge freeing or
sharing the port, or it may need a change on the emulator's side. It needs investigating first.

Done when: starting to host while joined no longer freezes the game.

### 3. Built-in Wi-Fi in Game Mode

With the adapter plugged in at boot, SteamOS can leave the Deck's built-in Wi-Fi without a network interface after
Steam switches the Wi-Fi backend from iwd to wpa_supplicant. The bridge isn't affected, but the Deck loses its normal
network.

Needed: find a setting or boot order that keeps the built-in Wi-Fi working, then test it over several boots.

Done when: the built-in Wi-Fi reconnects after boot with the adapter plugged in.

### 4. One mode for everything (optional)

Today the bridge either hosts or joins, chosen at launch. Switching by itself would need one `ldn` interface that stays
in place while the radio changes role, because Ryujinx crashes when `ldn` disappears during local play. Each switch
also costs a few seconds for the adapter reset and channel change.

## Later

After the Deck works fully: other Linux computers, Windows through WSL (W1 and W2 work, but it isn't being developed
now), other emulators and other games.
