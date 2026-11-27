# Windows through WSL (experimental)

The bridge can run inside WSL 2 on Windows 11, with the USB adapter passed through by `usbipd-win`, for Ryujinx
running on Windows. A small helper, `windows/ldn_tunnel.py`, gives Windows a network adapter on the Switch's network
and relays it to the bridge. This is newer and less tested than the Linux setup: see W1 and W2 in `docs/MILESTONES.md`.

Tested with an MT7612U adapter (Alfa AWUS036ACM), WSL kernel `6.18.33.1-microsoft-standard-WSL2`, Ubuntu 24.04,
usbipd-win 5.3.0, Wintun 0.14.1, Python 3.14 for Windows and Ryujinx 1.3.3 for Windows.

## Why it needs extra steps
- WSL's kernel has the Wi-Fi stack (`cfg80211`, `mac80211`) but no MT7612U driver, so the driver is built here.
- The kernel checks module versions, so the driver has to be built against the same kernel source and config.
- The kernel can't see Ubuntu's `/lib/firmware`. `wsl/load_mt76.sh` hands it the firmware through
  `/sys/class/firmware` instead, and masks Ubuntu's udev rule `50-firmware.rules`, which refuses those requests.
- Windows' own driver starts the chip when the adapter is plugged in, and the Linux driver then can't upload its
  firmware: every USB request times out with `-110`. Binding with `usbipd bind --force` keeps Windows' driver off it.

## One-time setup
1. In **Terminal (Admin)**: `winget install --exact dorssel.usbipd-win`
2. In Ubuntu: `sudo apt update && sudo apt install -y build-essential flex bison libssl-dev libelf-dev dwarves bc cpio
   kmod iw usbutils python3-venv`
3. In Ubuntu, get the kernel source for the running kernel. Check `uname -r`, then use the matching tag:
   ```bash
   git clone --depth 1 --branch linux-msft-wsl-6.18.33.1 https://github.com/microsoft/WSL2-Linux-Kernel.git ~/wsl-kernel
   ```
4. Get the two firmware files from linux-firmware:
   ```bash
   mkdir -p ~/mt76-fw && cd ~/mt76-fw
   for f in mt7662.bin mt7662_rom_patch.bin; do
     curl -fsSLO "https://git.kernel.org/pub/scm/linux/kernel/git/firmware/linux-firmware.git/plain/mediatek/$f"
   done
   ```
5. Copy this project to `~/ldn-bridge` in WSL, then build the driver: `bash ~/ldn-bridge/wsl/build_mt76.sh`. It ends
   by printing the driver's version string, which must match `uname -r`.
6. Plug in the adapter. In Terminal (Admin), find its BUSID with `usbipd list`, then
   `usbipd bind --force --busid <BUSID>`. Unplug it and plug it back in, so the chip starts without Windows' driver.
7. Set up the bridge as in `docs/SETUP.md`: `bash deck/setup.sh`, then `sudo bash deck/grant_caps.sh`, then
   `config.toml` and the keys file.
8. For Ryujinx on Windows: install Python 3 for Windows, and put `wintun.dll` from the `bin\amd64` folder of the
   Wintun zip from wintun.net next to `windows/ldn_tunnel.py`. Check it's signed by WireGuard LLC.

A Windows update can bring a new WSL kernel. If `uname -r` changes, repeat steps 3 and 5.

## Each time
1. Open Ubuntu and keep it open. Closing WSL unloads the driver.
2. In Terminal (Admin): `usbipd attach --wsl --busid <BUSID>`
3. In Ubuntu: `sudo bash ~/ldn-bridge/wsl/load_mt76.sh`. It should print `gave firmware` for both files and list a
   `phy` with a `wlan` interface.

The adapter then works as on Linux, and `python -m ldn_bridge scan` and `join` run from `~/ldn-bridge`.

## Playing with Ryujinx on Windows
**One click:** `windows/play.ps1` does all of the steps below, and the "Each time" steps above. It attaches the adapter,
loads the driver if needed, starts the bridge (minimized) and the helper, then Ryujinx, and stops them when Ryujinx
closes. It asks for Administrator rights each time. To make a launcher, save this as a `.bat` file in the Ryujinx
folder, with the path to your copy of this project:
```bat
@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "<project>\windows\play.ps1" -Ryujinx "%~dp0Ryujinx.exe"
```
Add `-Game "<path to game file>"` to open a game straight away. Before opening local multiplayer in the game, wait
until the helper window says `Adapter 'LDN Bridge' set to 169.254.x.x`.

By hand:
1. Host a local multiplayer session on the Switch, close to the adapter.
2. In Ubuntu: `bash ~/ldn-bridge/wsl/bridge_windows.sh`. It keeps looking for the session and rejoins after a
   disconnect, until Ctrl+C.
3. Close Ryujinx. In Terminal (Admin), from the project folder: `python windows\ldn_tunnel.py`. It creates the
   **LDN Bridge** adapter, adds a Windows Firewall rule for inbound traffic on that adapter only, and sets Ryujinx's
   Mode to `ldn_mitm`, Network Interface to **LDN Bridge**, and Guest Internet Access off. Ctrl+C removes the adapter.
4. Wait until it prints `Adapter 'LDN Bridge' set to 169.254.x.x`. Then start Ryujinx and join the session from the
   game. Ryujinx picks its address when the game starts local wireless, so this order matters.

## Known limits
- WSL has no country set, so 5 GHz channels 36 to 48 are receive-only. Channels 1, 6 and 11 work. Setting the country
  with `sudo iw reg set <country code>` should allow 5 GHz, but hasn't been tested.
- The quick scan gives each channel about 0.1 s, so it sometimes misses a session that's there. Scan again.
- Keep the console close to the adapter. From another room the adapter heard no advertisements at all, and range
  ended the first Ryujinx session. A USB extension cable that moves the
  adapter away from the PC may help: USB 3 ports and cables give off interference at 2.4 GHz.
- Each Windows-side packet passes through two Python processes. It was fast enough for Union Circle, but nothing
  faster has been tried.
