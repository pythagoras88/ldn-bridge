#!/usr/bin/env bash
# Run ON THE DECK with sudo: make NetworkManager ignore the USB adapter and the ldn* interfaces,
# while it keeps managing the internal Wi-Fi (your SSH session).
#   sudo bash deck/nm_unmanage.sh aa:bb:cc:dd:ee:ff
set -euo pipefail
MAC="${1:?usage: nm_unmanage.sh <usb adapter MAC from find_adapter.sh>}"
CONF=/etc/NetworkManager/conf.d/99-ldn-bridge-unmanaged.conf
cat > "$CONF" <<EOF
[keyfile]
unmanaged-devices=mac:${MAC};interface-name:ldn*
EOF
echo "Wrote $CONF"
nmcli general reload conf 2>/dev/null || systemctl reload NetworkManager
sleep 1
# NM leaves the adapter's interface up, and the monitor can't change channel until it's down (EBUSY).
for p in /sys/class/ieee80211/*; do
  [ "$(cat "$p/macaddress")" = "$MAC" ] || continue
  for dev in "$p"/device/net/*; do ip link set "$(basename "$dev")" down; done
done
nmcli device status
