# Notes for the next builder

Written at the release of 4.15.1 (2026-11-11). This is background, never a list of work: a
builder starts only from the maintainer's notes (MAINTAINING.md, "Builder").

## Not tested at this release

- Windows and Linux computers with the desktop app, and the cloud reading LinkedIn itself:
  only a Mac was used for real. Safari and Firefox ran on GitHub only.
- [4.15.1's final test results go here, written at the release.]

## Known red

- `test_a_people_run_reaches_the_people_who_answer.py::test_a_batch_is_shown_only_what_involves_its_own_notes`
  failed twice on GitHub in 4.15.0 and never locally; its message names the cause next time.
