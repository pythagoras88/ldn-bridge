#!/usr/bin/env bash
# Run ON THE DECK with sudo: lets your user reset the USB adapter, so `bridge emulator-hosts` can clear a key that a
# joined session leaves in the adapter's chip (docs/MILESTONES.md, M6). Writes a udev rule for the adapter's USB ID.
#   sudo bash deck/usb_access.sh [aa:bb:cc:dd:ee:ff]
# Without a MAC it uses adapter_mac from config.toml.
set -euo pipefail
cd "$(dirname "$0")/.."
USER_NAME="${SUDO_USER:-}"
[ -n "$USER_NAME" ] && [ "$USER_NAME" != root ] || { echo "Run it with sudo from your normal user."; exit 1; }
MAC="${1:-$(sed -nE 's/^\s*adapter_mac\s*=\s*"([^"]+)".*/\1/p' config.toml 2>/dev/null | head -n1)}"
[ -n "$MAC" ] || { echo "usage: sudo bash deck/usb_access.sh <usb adapter MAC from find_adapter.sh>"; exit 1; }
DEV=""
for p in /sys/class/ieee80211/*; do
  [ "$(cat "$p/macaddress")" = "${MAC,,}" ] || continue
  DEV="$(readlink -f "$p/device")/.."
done
[ -n "$DEV" ] || { echo "No adapter with MAC $MAC. Is it plugged in?"; exit 1; }
VID="$(cat "$DEV/idVendor")"
PID="$(cat "$DEV/idProduct")"
RULE=/etc/udev/rules.d/99-ldn-bridge-usb.rules
cat > "$RULE" <<EOF
# LDN Bridge: let $USER_NAME reset the USB Wi-Fi adapter ($VID:$PID).
SUBSYSTEM=="usb", ENV{DEVTYPE}=="usb_device", ATTR{idVendor}=="$VID", ATTR{idProduct}=="$PID", OWNER="$USER_NAME", MODE="0664"
EOF
echo "Wrote $RULE"
udevadm control --reload
udevadm trigger --action=add --subsystem-match=usb --attr-match=idVendor="$VID" --attr-match=idProduct="$PID"
udevadm settle
ls -l "/dev/bus/usb/$(printf %03d "$(cat "$DEV/busnum")")/$(printf %03d "$(cat "$DEV/devnum")")"
