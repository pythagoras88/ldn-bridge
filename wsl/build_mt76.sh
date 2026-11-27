#!/usr/bin/env bash
# Run IN WSL, no sudo: build the MT7612U driver (mt76x2u) as modules for the running WSL kernel, into ~/mt76-modules.
# The kernel checks module versions, so this builds the matching kernel once (about 10 minutes), then takes the modules.
# Needs the kernel source in ~/wsl-kernel, at the tag for `uname -r`: see docs/WSL.md.
set -euo pipefail
cd ~/wsl-kernel
RUNNING="$(uname -r)"
if [ ! -f .config ]; then
  zcat /proc/config.gz > .config
fi
scripts/config -k --module MT76x2U
make LOCALVERSION= olddefconfig >/dev/null
BUILT="$(make -s LOCALVERSION= kernelrelease)"
echo "running $RUNNING, building $BUILT"
[ "$BUILT" = "$RUNNING" ] || { echo "kernel release doesn't match" >&2; exit 1; }
grep -E '^CONFIG_MT76' .config
make -j"$(nproc)" LOCALVERSION= vmlinux modules 2>&1 | grep -E 'error|Error|warning: .*mt76' || true
ls -1 drivers/net/wireless/mediatek/mt76/*.ko drivers/net/wireless/mediatek/mt76/mt76x2/*.ko
modinfo -F vermagic drivers/net/wireless/mediatek/mt76/mt76x2/mt76x2u.ko
mkdir -p ~/mt76-modules
cp drivers/net/wireless/mediatek/mt76/mt76.ko drivers/net/wireless/mediatek/mt76/mt76-usb.ko \
   drivers/net/wireless/mediatek/mt76/mt76x02-lib.ko drivers/net/wireless/mediatek/mt76/mt76x02-usb.ko \
   drivers/net/wireless/mediatek/mt76/mt76x2/mt76x2-common.ko drivers/net/wireless/mediatek/mt76/mt76x2/mt76x2u.ko \
   ~/mt76-modules/
echo "Built into ~/mt76-modules"
