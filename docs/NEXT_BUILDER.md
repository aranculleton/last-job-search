# Notes for the next builder

Written at the release of 4.16.1 (2026-11-12) by the weekly builder. This is background, never
a list of work: a builder starts only from the maintainer's notes (MAINTAINING.md, "Builder").

## Not tested at this release
- The builder's task as `app_bug.py task` prints it (its own chat with the app) has not fired.
- The computer-route fixes of this release ran on GitHub only, never on a real computer.
- An old brief chat archived at the next tidy-up is tested on invented chats only.
- Windows and Linux computers with the desktop app were not used for real.

## Known red
- Python's zone data has Vancouver on UTC-7 all year from November 2026; a test or an issue
  that assumes UTC-8 there reads an hour wrong.
- Making a no-tap computer route the default waits for the maintainer (issue #250).
