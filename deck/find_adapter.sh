#!/usr/bin/env bash
# Run ON THE DECK: list Wi-Fi phys with driver, interface, MAC and monitor-mode support.
set -uo pipefail
printf "%-6s %-14s %-10s %-18s %s\n" PHY DRIVER IFACE MAC MONITOR
for p in /sys/class/ieee80211/*; do
  phy="$(basename "$p")"
  drv="$(basename "$(readlink -f "$p/device/driver")" 2>/dev/null || echo ?)"
  iface="$(ls "$p/device/net" 2>/dev/null | head -n1)"
  # The phy's address, not the interface's: NetworkManager randomises that one while scanning.
  mac="$(cat "$p/macaddress" 2>/dev/null)"
  mon="?"
  if command -v iw >/dev/null; then
    iw phy "$phy" info 2>/dev/null | sed -n '/Supported interface modes/,/Band/p' | grep -q '\* monitor' && mon=yes || mon=no
  fi
  printf "%-6s %-14s %-10s %-18s %s\n" "$phy" "$drv" "${iface:--}" "${mac:--}" "$mon"
done
echo
echo "The Deck's internal card is usually phy0 (ath11k_pci or rtw88). Put the USB adapter's MAC in config.toml."
command -v iw >/dev/null || echo "Note: 'iw' not found, so monitor support wasn't checked."
