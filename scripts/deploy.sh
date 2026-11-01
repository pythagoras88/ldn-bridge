#!/usr/bin/env bash
# Copy the project to the Deck. Never sends keys, config.toml, logs, captures or the venv.
set -euo pipefail
. "$(dirname "$0")/_env.sh"
cd "$ROOT"

ssh "$DECK_HOST" "mkdir -p ~/$DECK_DIR"
tar czf - \
  --exclude='./.git' --exclude='./.venv' --exclude='./logs' --exclude='./captures' --exclude='./third_party' \
  --exclude='./config.toml' --exclude='*.keys' --exclude='./scripts/deck.env' \
  --exclude='__pycache__' --exclude='*.egg-info' \
  . | ssh "$DECK_HOST" "tar xzf - -C ~/$DECK_DIR"
echo "Deployed to $DECK_HOST:~/$DECK_DIR"
