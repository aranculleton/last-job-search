# Notes for the next builder

Written at the release of 4.16.0 (2026-11-12) by the weekly builder. This is background, never
a list of work: a builder starts only from the maintainer's notes (MAINTAINING.md, "Builder").

## Not tested at this release
- The builder's task as `app_bug.py task` now prints it (a chat made with the app, the task
  bound to it) has not fired yet; the old task, a fresh chat each run, has to be remade by hand.
  A manual fire_trigger of a bound task starts a fresh chat (MAINTAINING.md), so a wake may
  still meet the same missing tools.
- The old brief chat archived at the next tidy-up is tested on invented chats only.
- Windows and Linux computers with the desktop app were not used for real.

## Known red
- Archiving the app's earlier chats from a chat on the computer is refused by Auto's own check
  in the desktop app; left with the maintainer (issue #243).
