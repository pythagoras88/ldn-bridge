# Setup

This project is for testing only and is provided as is, with no support. You must dump your own game and keys from your
own Switch running custom firmware. How to dump them, or where to get them or an emulator, is out of scope.

The bridge and Ryujinx run on the same Linux computer. A Steam Deck counts: it runs Linux, and it's the only computer
tested so far. The scripts live in a folder called `deck/`, but they aren't Deck-specific unless noted.

## 1. Get the project onto the Linux computer
**Working directly on it:** run `git clone https://github.com/pythagoras88/ldn-bridge.git ~/ldn-bridge` and continue to
section 2.

**Working from Windows over SSH** (the usual setup with Claude Code). On the Linux computer:
```bash
passwd                      # set a password if you haven't
sudo systemctl enable --now sshd
ip -4 addr                  # note its IP
```
On Windows, add this to `C:\Users\<you>\.ssh\config`, using your own IP and username:
```
Host deck
    HostName 192.168.x.x
    User deck
```
Then install a key so SSH doesn't prompt: in Git Bash, run `ssh-keygen -t ed25519` if you have no key, followed by
`cat ~/.ssh/id_ed25519.pub | ssh deck "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys"`. Test it with `ssh deck echo ok`.

From this folder in Git Bash, copy the project across:
```bash
cp scripts/deck.env.example scripts/deck.env   # edit if your host alias or folder differ
bash scripts/deploy.sh
```

## 2. Set up the bridge
**With the installer:** plug in the adapter, close Ryujinx, and run `bash install.sh` from the project folder, or
double-click it in Desktop Mode. If the project isn't at `~/ldn-bridge`, it copies itself there first. It then:
- finds the USB adapter, and asks which one if there's more than one
- creates the Python environment
- creates `config.toml`, or keeps yours, and fills in the adapter's MAC, the keys file, the protocols your keys allow and
  the newest Ryujinx AppImage in your home folder
- sets Ryujinx's Multiplayer mode to `ldn_mitm`, Network Interface to `ldn` and Guest Internet Access to off
- asks for your password once, for the two `sudo` steps below. If the account has no password yet, it asks you to set
  one first.
- adds the shortcuts, and adds **Play with LDN Bridge** to Steam when Steam is running
- checks your keys, showing names only

It never shows the passphrase. To keep one from an earlier setup, put your saved `config.toml` in the project folder
before running it. Run it again any time: it skips what's done. It has been tested on a freshly reset Steam Deck
(SteamOS 3.9).

**By hand:** on the Linux computer, plug in the adapter and run:
```bash
cd ~/ldn-bridge
bash deck/find_adapter.sh            # note the USB adapter's MAC
sudo bash deck/nm_unmanage.sh <MAC>  # NetworkManager ignores the adapter and ldn* interfaces
bash deck/setup.sh                   # Python environment and the ldn library, no sudo
sudo bash deck/grant_caps.sh         # lets the bridge control the adapter without sudo
sudo bash deck/usb_access.sh <MAC>   # lets the bridge reset the adapter before hosting
cp config.example.toml config.toml   # then set adapter_mac, keys_path and [launch]
```
`deck/find_keys.sh` lists likely `prod.keys` locations, showing paths only.

Re-run `deck/grant_caps.sh` after recreating `.venv`. On SteamOS, updates keep `/home` and `/etc` but may reset other
system changes.

If the adapter or a USB hub disconnects, the adapter comes back with a new phy number and interface name, with the
interface up. The bridge handles this: it finds the adapter by `adapter_mac` and takes its interface down before every
run. A disconnect during play still ends the session, so keep connections secure. On a Steam Deck, stay on charger power
for long sessions.

Without NetworkManager, stop your network manager from using the adapter yourself. If your home folder is mounted
`nosuid`, `deck/grant_caps.sh` tells you what to run instead.

## 3. Set up the emulator
- Use a Ryujinx build that has **Settings > Network > Multiplayer > Mode: ldn_mitm**. Ryubing 1.3.3 is tested.
- Use your own game and keys, dumped from your own Switch running custom firmware.
- Use a game update compatible with the one on the Switch.
- Turn **Guest Internet Access** off.
- Set **Network Interface** to `ldn`. That name only appears while the bridge is joined, so set it during your first
  session. Ryujinx remembers it, but saving Settings while the bridge isn't joined resets it to Default, which uses
  Wi-Fi. The shortcuts that run `deck/play.sh` set it back to `ldn` each time they start Ryujinx.

Ryujinx reads this setting each time a game starts local wireless, and silently uses your normal network if `ldn` is
missing. So let the bridge join before you open the game's local multiplayer mode.

## 4. Capture the passphrase
Do this once for each game. Passphrases aren't included in this project, so capture yours from your own copy of the game.
A game update could change one: if `join` starts timing out at authentication, capture it again.

With the .NET 9 SDK, build the Ryubing 1.3.3 source with the patch. This can be done on the Linux computer or on Windows.
The patch records the passphrase in a private file instead of the log, and repoints the 1.3.3 package sources, which have
moved. Run this from your copy of that source, where `<project>` is the path to this project:
```bash
git apply --ignore-whitespace <project>/docs/patches/ryujinx-1.3.3-capture-passphrase.patch
dotnet publish -c Release -r linux-x64 -o publish -p:Version=1.3.3 -p:DebugType=embedded -p:SourceRevisionId=m2b -p:ExtraDefineConstants=DISABLE_UPDATER src/Ryujinx --self-contained
```
Copy `publish` to `~/ryujinx-m2b` on the Linux computer and run `Ryujinx.sh`. Set Mode to `ldn_mitm`, then host a session
in the game using local communication. `~/ldn-passphrase.txt` then contains a line ending in `passphrase=<hex>`.

Put that hex in `config.toml` as `password_hex`, delete the file, and go back to your normal emulator. Never share it.
Note the `lcid=` value on the same line, and put it in `config.toml` under `[game]` as `local_communication_id`, in
quotes, for example `"0x0100000000001000"`. Host mode needs it. See "What each game needs" in `docs/TESTING.md`.

## 5. Playing
`bash deck/install_shortcuts.sh` adds the shortcuts once.

**Play with LDN Bridge** asks who hosts (`mode = "ask"` under `[launch]`). In Game Mode, tap a button or use the
trackpad. If nothing is picked within 15 s, the game on the emulator hosts and the Switch joins. Set `mode = "host"`
or `mode = "join"` to skip the question.

1. Start the bridge and the emulator with **Play with LDN Bridge**. Closing the emulator stops the bridge.
   - It opens the game set in `[launch]` in `config.toml`, or the emulator's game list if none is set.
   - To pick the game yourself, double-click **LDN Bridge + Emulator** on the desktop instead. It opens the emulator's
     game list, and closing the emulator stops the bridge.
   - Other options: double-click **LDN Bridge** on the desktop and close its window to stop, or run
     `bash deck/bridge.sh start` and `stop` from a terminal.
2. Host a local multiplayer session in the game on the emulator.
3. Join it from the Switch, with the game's code if it shows one.

The bridge resets the adapter over USB before it hosts, which takes about 2 s. If the Switch stays on "searching" and
the bridge says the Switch's game traffic can't be read, unplug the adapter and plug it back in. Don't restart the
bridge while the game is in local play: Ryujinx 1.3.3 can crash when the `ldn` interface goes away.

**When the Switch hosts:** pick **Switch hosts** at the question, set `mode = "join"` under `[launch]`, or start with
`LDN_MODE=join bash deck/play.sh`. Host on
the Switch, then join from the game on the emulator. If it fails straight away, try again.
- Ryujinx 1.3.3 sometimes reports a failed connection to the bridge just before the connection completes, and the game
  then says it couldn't communicate. Its log shows `Failed to connect.` followed by `LdnProxyTCPClient connected!`. The
  bridge stays joined to the Switch, so search for the session again in the game.
- The bridge keeps looking until it finds a session and rejoins after a disconnect. The game has to rejoin the session
  itself.

**Steam Deck Game Mode:** the installer adds **Play with LDN Bridge** to Steam. Otherwise, in Desktop Mode, right-click
it in the application menu and choose Add to Steam. Then run it from your library, and exit with **Steam button > Exit Game**. This is untested.

## 6. Adapter choice
You need monitor mode and injection with an in-kernel driver. MediaTek **MT7612U** is tested, in an Alfa AWUS036ACM.
**MT7610U** should also work. Dual-band matters, because local wireless may use 5 GHz channels 36 to 48.
