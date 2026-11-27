#!/usr/bin/env bash
# Run IN WSL with sudo, after each WSL restart and after attaching the adapter with usbipd:
# load the mt76x2u driver from ~/mt76-modules and hand it the MT7612U firmware from ~/mt76-fw.
# WSL's kernel looks for firmware outside the distro, so this answers its requests through /sys/class/firmware.
# Writes what happened to ~/load_mt76.log so it can be read without sudo.
set -uo pipefail
# The user whose ~/mt76-modules and ~/mt76-fw to use: whoever ran sudo, or else whoever owns this script, so it also
# works when Windows runs it as root (windows/play.ps1).
OWNER="${SUDO_USER:-$(stat -c %U "$(readlink -f "$0")")}"
HOME_DIR="$(getent passwd "$OWNER" | cut -d: -f6)"
LOG="$HOME_DIR/load_mt76.log"
exec > >(tee "$LOG") 2>&1
FW="$HOME_DIR/mt76-fw"

feed_firmware() { # answer firmware requests for $1 seconds
  local end=$((SECONDS + $1))
  while [ $SECONDS -lt $end ]; do
    for dir in /sys/class/firmware/*/; do
      [ -f "$dir/loading" ] || continue
      name="$(basename "$dir" | tr '!' '/')"
      file="$FW/$(basename "$name")"
      [ -f "$file" ] || file="/lib/firmware/$name"
      echo 1 > "$dir/loading" 2>/dev/null || continue
      if [ -f "$file" ]; then
        cat "$file" > "$dir/data" && echo 0 > "$dir/loading" && echo "gave firmware $name"
      else
        echo -1 > "$dir/loading"; echo "no file for firmware request $name"
      fi
    done
    sleep 0.2
  done
}

# Ubuntu's udev rule answers every firmware request with "not found" straight away. Mask it.
if [ ! -f /etc/udev/rules.d/50-firmware.rules ]; then
  echo "# Masks Ubuntu's rule that refuses firmware requests, so load_mt76.sh can answer them." \
    > /etc/udev/rules.d/50-firmware.rules
  echo "masked udev 50-firmware.rules"
fi
udevadm control --reload
echo 1 > /proc/sys/kernel/firmware_config/force_sysfs_fallback
trap 'echo 0 > /proc/sys/kernel/firmware_config/force_sysfs_fallback' EXIT
modprobe usbcore; modprobe led-class; modprobe cfg80211; modprobe mac80211
for m in mt76 mt76-usb mt76x02-lib mt76x02-usb mt76x2-common; do
  if lsmod | grep -q "^${m//-/_} "; then echo "$m already loaded"; else insmod "$HOME_DIR/mt76-modules/$m.ko" && echo "loaded $m"; fi
done
rmmod mt76x2u 2>/dev/null && echo "unloaded mt76x2u to try again"
feed_firmware 40 &
FEEDER=$!
insmod "$HOME_DIR/mt76-modules/mt76x2u.ko" && echo "loaded mt76x2u"  # returns once the firmware is in
sleep 1
iw reg reload 2>/dev/null
sleep 2
kill "$FEEDER" 2>/dev/null; wait "$FEEDER" 2>/dev/null
echo 0 > /proc/sys/kernel/firmware_config/force_sysfs_fallback

echo "--- kernel messages"
dmesg | grep -v vhci_hcd | grep -i -E "mt76|mt7662|firmware|regulatory|ieee80211|phy[0-9]" | tail -15
echo "--- wireless"
ls /sys/class/ieee80211 2>&1
iw dev 2>&1
