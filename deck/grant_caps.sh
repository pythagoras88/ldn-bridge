#!/usr/bin/env bash
# Run ON THE DECK with sudo: lets the venv's python create Wi-Fi/TAP interfaces without running as root.
# Re-run after recreating .venv.
set -euo pipefail
cd "$(dirname "$0")/.."
PY="$(readlink -f .venv/bin/python3)"
case "$PY" in
  "$(pwd)"/.venv/*) ;;
  *) echo "Refusing: $PY is outside .venv (was the venv made with --copies?)"; exit 1 ;;
esac
if findmnt -no OPTIONS -T "$PY" | grep -qw nosuid; then
  echo "Warning: this filesystem is mounted nosuid, so file capabilities are ignored."
  echo "Run commands as: sudo .venv/bin/python -m ldn_bridge <command>"
fi
setcap cap_net_admin,cap_net_raw+eip "$PY"
getcap "$PY"
