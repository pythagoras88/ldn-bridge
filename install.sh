#!/usr/bin/env bash
# One-step setup on a Steam Deck or other Linux computer. Run it from Desktop Mode, by double-clicking it or with
#   bash install.sh
# Safe to run again: it keeps your config.toml and skips what's already done.
# It asks for your password once, for the two system changes (NetworkManager ignoring the adapter, and network
# permissions for the bridge's Python). It never shows the passphrase or key values.
set -uo pipefail

SRC="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"

# Double-clicked: re-open in a terminal, so the password prompt and the results can be seen.
if [ ! -t 0 ] && [ -z "${LDN_INSTALL_TERMINAL:-}" ]; then
  export LDN_INSTALL_TERMINAL=1
  for term in konsole gnome-terminal xterm; do
    command -v "$term" >/dev/null || continue
    case "$term" in
      gnome-terminal) exec gnome-terminal -- bash "$SRC/install.sh" "$@" ;;
      *) exec "$term" -e bash "$SRC/install.sh" "$@" ;;
    esac
  done
  echo "Open a terminal and run: bash $SRC/install.sh" >&2
  exit 1
fi

bold() { printf '\n\033[1m%s\033[0m\n' "$*"; }
fail() {
  printf '\n\033[31mStopped: %s\033[0m\n' "$*" >&2
  [ -n "${LDN_INSTALL_TERMINAL:-}" ] && read -rp "Press Enter to close." _
  exit 1
}

DEST="$HOME/ldn-bridge"

bold "1/7  Project folder"
if [ "$SRC" != "$DEST" ]; then
  # Shortcuts point at the project folder, so keep it in one place rather than in Downloads.
  mkdir -p "$DEST"
  tar -C "$SRC" --exclude=./.venv --exclude=./config.toml --exclude=./logs --exclude=./captures -cf - . \
    | tar -C "$DEST" -xf - || fail "couldn't copy the project to $DEST"
  if [ -f "$SRC/config.toml" ] && [ ! -f "$DEST/config.toml" ]; then
    cp "$SRC/config.toml" "$DEST/config.toml"
  fi
  echo "Copied the project to $DEST."
  exec bash "$DEST/install.sh" "$@"
fi
cd "$DEST"
echo "Using $DEST."

bold "2/7  Checks"
[ "$(uname -s)" = Linux ] || fail "this runs on Linux, such as a Steam Deck in Desktop Mode."
[ "$(id -u)" != 0 ] || fail "run it as your normal user, not with sudo. It asks for the password when it needs it."
python3 - <<'EOF' || fail "Python 3.11 or later is needed."
import sys
sys.exit(sys.version_info < (3, 11))
EOF
echo "Python $(python3 -c 'import platform; print(platform.python_version())') OK"
if pgrep -i '^ryujinx' >/dev/null; then
  fail "Ryujinx is open. Close it first, so its settings can be updated."
fi

bold "3/7  Wi-Fi adapter"
find_usb_adapters() {
  for p in /sys/class/ieee80211/*; do
    [ -e "$p" ] || continue
    readlink -f "$p/device" | grep -q '/usb' || continue
    if command -v iw >/dev/null; then
      iw phy "$(basename "$p")" info 2>/dev/null | sed -n '/Supported interface modes/,/Band/p' \
        | grep -q '\* monitor' || continue
    fi
    printf '%s %s\n' "$(cat "$p/macaddress")" "$(basename "$(readlink -f "$p/device/driver")")"
  done
}
while :; do
  mapfile -t ADAPTERS < <(find_usb_adapters)
  [ "${#ADAPTERS[@]}" -gt 0 ] && break
  echo "No USB Wi-Fi adapter with monitor mode found. The Deck's own Wi-Fi can't be used for this."
  read -rp "Plug in the adapter, wait a few seconds, then press Enter (or Ctrl+C to stop). " _
done
if [ "${#ADAPTERS[@]}" -gt 1 ]; then
  echo "More than one USB adapter found:"
  for i in "${!ADAPTERS[@]}"; do echo "  $((i + 1))) ${ADAPTERS[$i]}"; done
  read -rp "Which one is for the bridge? [1] " pick
  pick="${pick:-1}"
  [[ "$pick" =~ ^[0-9]+$ ]] && [ "$pick" -ge 1 ] && [ "$pick" -le "${#ADAPTERS[@]}" ] || fail "no such adapter."
  ADAPTER="${ADAPTERS[$((pick - 1))]}"
else
  ADAPTER="${ADAPTERS[0]}"
fi
MAC="${ADAPTER%% *}"
echo "Adapter: $ADAPTER"

bold "4/7  Python environment"
if .venv/bin/python3 -c 'import ldn, trio, ldn_bridge' 2>/dev/null; then
  echo "Already set up."
else
  echo "Downloading the bridge's Python packages. This takes a minute."
  # Hide packaging warnings. Real errors still show, and the import check below catches a failed setup.
  LDN_INSTALLER=1 PIP_QUIET=1 bash deck/setup.sh 2>&1 \
    | grep -vE 'Deprecat|deprecat|license|no longer be supported|\*{8}|^ *!!|^ *$|corresp|By 20|SPDX' || true
  .venv/bin/python3 -c 'import ldn, trio, ldn_bridge' 2>/dev/null || fail "the Python setup didn't finish. Check the internet connection and run this again."
fi

bold "5/7  Settings"
EMULATOR="$(find -L "$HOME" -maxdepth 3 -type f -iname '*ryujinx*.appimage' -not -path '*/.local/share/Trash/*' \
  -printf '%T@ %p\n' 2>/dev/null | sort -rn | head -n1 | cut -d' ' -f2-)"
if [ -n "$EMULATOR" ]; then
  chmod +x "$EMULATOR"
else
  echo "NOTE: no Ryujinx AppImage found in your home folder. Put it in ~/Applications and run this again."
fi
KEYS="$(bash deck/find_keys.sh | grep -v '^(' | head -n1)"
.venv/bin/python3 -m ldn_bridge.install_config --mac "$MAC" --emulator "$EMULATOR" --keys "$KEYS" \
  || fail "couldn't write the settings."

bold "6/7  System permissions (needs your password once)"
CONF=/etc/NetworkManager/conf.d/99-ldn-bridge-unmanaged.conf
PY="$(readlink -f .venv/bin/python3)"
USB_RULE=/etc/udev/rules.d/99-ldn-bridge-usb.rules
if grep -qi "mac:$MAC" "$CONF" 2>/dev/null && getcap "$PY" 2>/dev/null | grep -q cap_net_admin \
    && grep -q "OWNER=\"$USER\"" "$USB_RULE" 2>/dev/null; then
  echo "Already done."
else
  if [ "$(passwd -S "$USER" 2>/dev/null | awk '{print $2}')" != P ]; then
    echo "Your account has no password yet, and one is needed for this step."
    echo "Choose one now. Nothing appears on screen while you type it."
    passwd || fail "the password wasn't set."
  fi
  echo "Type your password when asked. Nothing appears on screen while you type it."
  sudo bash -c 'bash "$1" "$2" >/dev/null && bash "$3" && bash "$4" "$2" >/dev/null' _ "$DEST/deck/nm_unmanage.sh" "$MAC" \
    "$DEST/deck/grant_caps.sh" "$DEST/deck/usb_access.sh" \
    || fail "the system step didn't finish. Run this again and check the password."
fi

bold "7/7  Shortcuts"
bash deck/install_shortcuts.sh >/dev/null && echo "Added LDN Bridge to the desktop and the application menu."
SHORTCUTS=("$HOME"/.local/share/Steam/userdata/*/config/shortcuts.vdf)
for SHORTCUT in "Play with LDN Bridge:ldn-bridge-play"; do
  NAME="${SHORTCUT%%:*}"
  FILE="$HOME/.local/share/applications/${SHORTCUT##*:}.desktop"
  # Steam ends each name with a NUL, so the first name doesn't also match the second.
  if grep -aqsP "\Q$NAME\E\x00" "${SHORTCUTS[@]}"; then
    echo "$NAME is already in your Steam library."
  elif command -v steamos-add-to-steam >/dev/null && pgrep -x steam >/dev/null; then
    steamos-add-to-steam "$FILE" >/dev/null 2>&1 && echo "Added $NAME to your Steam library, for Game Mode."
  else
    echo "To play from Game Mode, right-click $NAME in the application menu and choose Add to Steam."
  fi
done

bold "Checking"
.venv/bin/python3 -m ldn_bridge keys-check 2>&1 | grep -E "^protocol|Loaded" || true
echo
echo "Done. Run Play with LDN Bridge, host a local multiplayer session in the game, then join it from the Switch."
grep -qE '^local_communication_id = "0x' config.toml \
  || echo "NOTE: set local_communication_id under [game] in config.toml first (docs/SETUP.md, section 4)."
echo "Anything marked NOTE above still needs doing first."
[ -n "${LDN_INSTALL_TERMINAL:-}" ] && read -rp "Press Enter to close." _
exit 0
