#!/usr/bin/env bash
# Run ON THE LINUX COMPUTER, no sudo: run the bridge as a background service, so it doesn't need a window.
#   deck/bridge.sh start   keep looking for a Switch session, and rejoin after a disconnect, until stopped
#   deck/bridge.sh stop
#   deck/bridge.sh watch   start and show progress; closing the window stops the bridge
set -uo pipefail
cd "$(dirname "$(readlink -f "$0")")/.."
UNIT=ldn-bridge
LOG=logs/bridge-console.log
MATCH="ldn_bridge bridge switch-hosts"

stop() {
  # SIGINT, not SIGTERM: the ldn library removes its interface on the way out.
  systemctl --user kill --signal=SIGINT "$UNIT" 2>/dev/null
  systemctl --user stop "$UNIT" 2>/dev/null
  pkill -INT -f "$MATCH"
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    pgrep -f "$MATCH" >/dev/null || return 0
    sleep 0.5
  done
  echo "Bridge didn't stop in time; forcing it." >&2
  pkill -KILL -f "$MATCH"
}

start() {
  stop
  mkdir -p logs
  : > "$LOG"
  systemd-run --user --quiet --unit="$UNIT" --collect --working-directory="$PWD" \
    -p KillSignal=SIGINT -p TimeoutStopSec=5 \
    bash -c "exec >>$LOG 2>&1; while :; do .venv/bin/python -u -m ldn_bridge bridge switch-hosts --no-wait; sleep 3; done"
}

case "${1:-}" in
  start) start ;;
  stop) stop ;;
  watch)
    start
    trap 'stop; exit 0' EXIT HUP INT TERM
    echo "LDN Bridge is running. Keep this window open, and close it to stop."
    echo "Host a local multiplayer session on the Switch, then join it from the game on the emulator."
    echo
    tail -n +1 -f "$LOG" | grep --line-buffered -E "Joined|No matching|Disconnected|Connect from|gone|Error" &
    wait
    ;;
  *) echo "usage: deck/bridge.sh start|stop|watch" >&2; exit 2 ;;
esac
