---
description: Run unit tests, then deploy the project to the Steam Deck
---
1. Run `python -m unittest discover -s tests -v`. Stop and report if anything fails.
2. Run `bash scripts/deploy.sh`.
3. If `$ARGUMENTS` is non-empty, run it on the Deck with `bash scripts/deck.sh "$ARGUMENTS"` and summarize the output.
