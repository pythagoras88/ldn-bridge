#!/usr/bin/env bash
# Copy logs/ and captures/ back from the Deck into this folder.
set -euo pipefail
. "$(dirname "$0")/_env.sh"
cd "$ROOT"
for d in logs captures; do
  mkdir -p "$d"
  ssh "$DECK_HOST" "cd ~/$DECK_DIR && [ -d $d ] && tar czf - $d || true" | tar xzf - 2>/dev/null || true
done
echo "Pulled logs/ and captures/ from $DECK_HOST"
