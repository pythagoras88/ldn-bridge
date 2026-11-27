#!/usr/bin/env bash
# Run IN WSL, no sudo, after wsl/load_mt76.sh: keep the bridge joined to the Switch for an emulator on Windows.
# It keeps looking for a session and rejoins after a disconnect, until Ctrl+C. Run windows/ldn_tunnel.py on Windows too.
set -uo pipefail
cd "$(dirname "$(readlink -f "$0")")/.."
trap 'exit 0' INT TERM
while :; do
  .venv/bin/python -u -m ldn_bridge bridge switch-hosts --no-wait --windows
  sleep 3
done
