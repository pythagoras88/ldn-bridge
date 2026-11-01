---
description: Work on the next unchecked milestone in docs/MILESTONES.md
---
1. Read `docs/MILESTONES.md`, `docs/DESIGN.md` and whichever protocol doc applies. Find the first unchecked
   milestone (or the one named in `$ARGUMENTS`).
2. Say in two or three sentences what you'll do and what the user must do physically (open local multiplayer
   on the Switch, start the emulator, run a sudo command in their own SSH session).
3. Do the code/tooling part: edit locally, run tests, `bash scripts/deploy.sh`, run on the Deck with
   `bash scripts/deck.sh "..."`, `bash scripts/pull.sh` to fetch logs/captures.
4. When the user reports a result, record the findings under the milestone in `docs/MILESTONES.md`, update the
   protocol docs if an assumption was confirmed or disproved, and tick the box only when the milestone's visible
   result happened.

Never read or print key files or key values.
