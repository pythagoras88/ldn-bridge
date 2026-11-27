#!/usr/bin/env bash
# Run ON THE LINUX COMPUTER, no sudo: run the bridge as a background service, so it doesn't need a window.
#   deck/bridge.sh start   run until stopped, and start again after a session ends or the adapter drops
#   deck/bridge.sh stop
#   deck/bridge.sh watch   start and show progress; closing the window stops the bridge
# The mode comes from [launch] mode in config.toml: "host" (default: the emulator hosts and the Switch joins) or
# "join" (the Switch hosts). LDN_MODE=host or LDN_MODE=join overrides it.
set -uo pipefail
cd "$(dirname "$(readlink -f "$0")")/.."
UNIT=ldn-bridge
LOG=logs/bridge-console.log
MATCH="ldn_bridge bridge "
MODE="${LDN_MODE:-$(.venv/bin/python3 -c 'import tomllib
print(tomllib.load(open("config.toml", "rb")).get("launch", {}).get("mode", "") or "host")' 2>/dev/null)}"
case "${MODE:-host}" in
  host|ask) MODE=host; COMMAND=emulator-hosts ;;  # only deck/play.sh asks
  join) COMMAND="switch-hosts --no-wait" ;;
  *) echo "Unknown mode '$MODE'. Use host, join or ask." >&2; exit 2 ;;
esac

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
    bash -c "exec >>$LOG 2>&1; trap 'exit 0' INT TERM; while :; do .venv/bin/python -u -m ldn_bridge bridge $COMMAND; sleep 3; done"
}

case "${1:-}" in
  start) start ;;
  stop) stop ;;
  watch)
    start
    trap 'stop; exit 0' EXIT HUP INT TERM
    echo "LDN Bridge is running in $MODE mode. Keep this window open, and close it to stop."
    if [ "$MODE" = join ]; then
      echo "Host a local multiplayer session on the Switch, then join it from the game on the emulator."
    else
      echo "Host a local multiplayer session in the game on the emulator, then join it from the Switch."
    fi
    echo
    tail -n +1 -f "$LOG" | grep --line-buffered -E       "Joined|No matching|Disconnected|Connect from|gone|Error|ready|is hosting|stopped hosting|joined|left|can't be read" &
    wait
    ;;
  *) echo "usage: deck/bridge.sh start|stop|watch" >&2; exit 2 ;;
esac
