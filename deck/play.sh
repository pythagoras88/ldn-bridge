#!/usr/bin/env bash
# Run ON THE LINUX COMPUTER, no sudo: start the bridge, play, and stop the bridge when the emulator closes.
# The Steam shortcut runs this, so it works in Game Mode. The bridge starts in [launch] mode from config.toml (host by
# default) while the game loads. mode = "ask" asks first. LDN_MODE=host or LDN_MODE=join overrides it.
# Paths come from [launch] in config.toml. LDN_EMULATOR and LDN_GAME override them.
# --no-game opens the emulator's game list instead of the game, so you pick it yourself.
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
if [ "${1:-}" = "--no-game" ]; then
  GAME=""
fi

# mode = "ask": choose who hosts in a small window, by touch or trackpad in Game Mode. No answer in 15 s means the
# emulator hosts.
if [ -z "${LDN_MODE:-}" ] && [ "$(setting mode)" = ask ]; then
  CHOICE="$(zenity --question --switch --title="LDN Bridge" --width=420 --timeout=15 \
    --text="Who hosts the local session?\n\nThis computer: Union Circle, raids and Link Trade hosted here.\nSwitch: join a session the Switch hosts." \
    --extra-button="This computer hosts" --extra-button="Switch hosts" 2>/dev/null)"
  if [ "$CHOICE" = "Switch hosts" ]; then LDN_MODE=join; else LDN_MODE=host; fi
  export LDN_MODE
  echo "Mode: $LDN_MODE"
fi

# Ryujinx picks the network interface each time the game starts local play, and uses Wi-Fi if it's set to Default.
# Its Settings window resets it to Default when saved before the bridge has joined, so set it again every time.
.venv/bin/python3 - <<'PY'
import json, os, tomllib
path = os.path.expanduser("~/.config/Ryujinx/Config.json")
ifname = tomllib.load(open("config.toml", "rb")).get("ldn", {}).get("ifname", "ldn")
if os.path.exists(path):
    with open(path, encoding="utf-8") as f:
        config = json.load(f)
    if config.get("multiplayer_lan_interface_id") != ifname:
        config["multiplayer_lan_interface_id"] = ifname
        with open(path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        print(f"Set the emulator's network interface to {ifname}.")
PY

bash deck/bridge.sh start
trap 'bash deck/bridge.sh stop' EXIT

# Steam loads its overlay and Fossilize Vulkan layers into the emulator. On the Deck in Game Mode, Ryujinx 1.3.3 has
# crashed inside both. Leave them out unless LDN_STEAM_LAYERS=1.
if [ "${LDN_STEAM_LAYERS:-0}" != "1" ]; then
  export DISABLE_VK_LAYER_VALVE_steam_overlay_1=1 DISABLE_VK_LAYER_VALVE_steam_fossilize_1=1
fi

# In the background so a close request from Steam runs the trap straight away.
if [ -n "$GAME" ]; then
  "$EMULATOR" --fullscreen "$GAME" &
else
  "$EMULATOR" &
fi
EMULATOR_PID=$!
trap 'kill "$EMULATOR_PID" 2>/dev/null; exit 0' HUP INT TERM
wait "$EMULATOR_PID"
