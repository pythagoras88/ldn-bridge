#!/usr/bin/env bash
# Run ON WINDOWS (Git Bash): copy the project into WSL at ~/ldn-bridge, like deploy.sh does for the Deck.
# Never sends keys, config.toml, logs, captures, the venv or wintun.dll. WSL_DISTRO picks the distro (default Ubuntu).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DISTRO="${WSL_DISTRO:-Ubuntu}"
cd "$ROOT"
tar czf - \
  --exclude='./.git' --exclude='./.venv' --exclude='./logs' --exclude='./captures' --exclude='./third_party' \
  --exclude='./config.toml' --exclude='*.keys' --exclude='./scripts/deck.env' --exclude='./windows/wintun.dll' \
  --exclude='__pycache__' --exclude='*.egg-info' \
  . | MSYS_NO_PATHCONV=1 wsl.exe -d "$DISTRO" --cd / sh -c 'mkdir -p ~/ldn-bridge && tar xzf - -C ~/ldn-bridge'
echo "Synced to WSL ($DISTRO):~/ldn-bridge"
