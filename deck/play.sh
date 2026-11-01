#!/usr/bin/env bash
# Run ON THE LINUX COMPUTER, no sudo: start the bridge, play, and stop the bridge when the emulator closes.
# The Steam shortcut runs this, so it works in Game Mode. The bridge keeps looking for a session while the game loads.
# Paths come from [launch] in config.toml. LDN_EMULATOR and LDN_GAME override them.
set -uo pipefail
cd "$(dirname "$(readlink -f "$0")")/.."

setting() {
  .venv/bin/python3 -c 'import os, sys, tomllib
launch = tomllib.load(open("config.toml", "rb")).get("launch", {})
value = launch.get(sys.argv[1], "")
print(os.path.expanduser(value) if value else "")' "$1"
}

EMULATOR="${LDN_EMULATOR:-$(setting emulator)}"
EMULATOR="${EMULATOR:-$HOME/Applications/ryujinx-1.3.3-x64.AppImage}"
GAME="${LDN_GAME:-$(setting game)}"

bash deck/bridge.sh start
trap 'bash deck/bridge.sh stop' EXIT

# In the background so a close request from Steam runs the trap straight away.
if [ -n "$GAME" ]; then
  "$EMULATOR" --fullscreen "$GAME" &
else
  "$EMULATOR" &
fi
EMULATOR_PID=$!
trap 'kill "$EMULATOR_PID" 2>/dev/null; exit 0' HUP INT TERM
wait "$EMULATOR_PID"
