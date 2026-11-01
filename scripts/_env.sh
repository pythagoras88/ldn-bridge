# Sourced by the other scripts.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ -f "$ROOT/scripts/deck.env" ]; then
  # shellcheck disable=SC1091
  . "$ROOT/scripts/deck.env"
fi
DECK_HOST="${DECK_HOST:-deck}"
DECK_DIR="${DECK_DIR:-ldn-bridge}"
