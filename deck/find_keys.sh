#!/usr/bin/env bash
# Run ON THE DECK: list likely prod.keys locations. Prints paths only, never contents.
for f in \
  ~/.switch/prod.keys \
  ~/.config/Ryujinx/system/prod.keys \
  ~/.var/app/*/config/*/system/prod.keys \
  ~/.local/share/*/system/prod.keys \
  ~/Emulation/bios/*/keys/prod.keys \
  ~/Emulation/bios/*/prod.keys; do
  [ -f "$f" ] && echo "$f"
done
echo "(Not listed? Search: find ~ -name prod.keys 2>/dev/null)"
