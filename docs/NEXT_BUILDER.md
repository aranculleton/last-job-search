# Notes for the next builder

Written at the release of 4.17.0 (2026-11-19) by the weekly builder. This is background, never
a list of work: a builder starts only from the maintainer's notes (MAINTAINING.md, "Builder").

## Not tested at this release
- The redesigned page was looked at on screenshots of the sample and in the maintainer's own
  page; no stranger's page with a long history has been seen in the new look.
- The computer chat renaming itself on the computer has run in tests only.
- Windows and Linux computers with the desktop app were not used for real.

## Known red
- Python's zone data has Vancouver on UTC-7 all year from November 2026; a test or an issue
  that assumes UTC-8 there reads an hour wrong.
