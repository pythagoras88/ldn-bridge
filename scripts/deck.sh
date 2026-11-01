#!/usr/bin/env bash
# Run a command on the Deck inside the project dir with the venv active.
#   bash scripts/deck.sh "python -m ldn_bridge scan"
# Interactive commands (bridge waits for Enter) need a TTY: bash scripts/deck.sh -t "python -m ldn_bridge bridge switch-hosts"
set -euo pipefail
. "$(dirname "$0")/_env.sh"
TTY=""
if [ "${1:-}" = "-t" ]; then TTY="-t"; shift; fi
[ $# -ge 1 ] || { echo "usage: deck.sh [-t] \"command\""; exit 2; }
ssh $TTY "$DECK_HOST" "cd ~/$DECK_DIR && { [ -f .venv/bin/activate ] && . .venv/bin/activate || true; } && $*"
