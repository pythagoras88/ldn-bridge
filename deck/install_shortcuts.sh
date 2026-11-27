#!/usr/bin/env bash
# Run ON THE LINUX COMPUTER, no sudo: add the LDN Bridge desktop shortcuts, and Play/Start/Stop to the application menu.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APPS="$HOME/.local/share/applications"
mkdir -p "$HOME/Desktop" "$APPS"

entry() { # file, name, exec, terminal comment
  cat > "$1" <<EOF
[Desktop Entry]
Type=Application
Name=$2
Comment=$4
Exec=$3
Icon=network-wireless
Terminal=false
Categories=Game;
EOF
  chmod +x "$1"
}

entry "$HOME/Desktop/LDN Bridge.desktop" "LDN Bridge" "konsole -e bash $ROOT/deck/bridge.sh watch" \
  "Connect the emulator to a Switch. Close the window to stop."
entry "$HOME/Desktop/LDN Bridge + Emulator.desktop" "LDN Bridge + Emulator" "bash $ROOT/deck/play.sh --no-game"   "Start the bridge and open the emulator's game list. Closing the emulator stops the bridge."
entry "$APPS/ldn-bridge-emulator.desktop" "LDN Bridge + Emulator" "bash $ROOT/deck/play.sh --no-game"   "Start the bridge and open the emulator's game list. Closing the emulator stops the bridge."
entry "$APPS/ldn-bridge-play.desktop" "Play with LDN Bridge" "bash $ROOT/deck/play.sh" \
  "Start the bridge and the emulator, in [launch] mode (the emulator hosts by default). Closing the emulator stops it."
entry "$APPS/ldn-bridge-play-join.desktop" "Play with LDN Bridge (Switch hosts)" "env LDN_MODE=join bash $ROOT/deck/play.sh" \
  "Start the bridge to join a session the Switch hosts, and the emulator. Closing the emulator stops the bridge."
entry "$APPS/ldn-bridge-start.desktop" "LDN Bridge Start" "bash $ROOT/deck/bridge.sh start" \
  "Start the bridge in the background, for Game Mode."
entry "$APPS/ldn-bridge-stop.desktop" "LDN Bridge Stop" "bash $ROOT/deck/bridge.sh stop" \
  "Stop the background bridge."
echo "Installed."
