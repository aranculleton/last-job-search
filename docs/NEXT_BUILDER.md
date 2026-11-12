# Notes for the next builder

Written at the release of 4.15.1 (2026-11-11). This is background, never a list of work: a
builder starts only from the maintainer's notes (MAINTAINING.md, "Builder").

## Not tested at this release
- Windows and Linux computers with the desktop app, and the cloud reading LinkedIn itself:
  only a Mac was used for real; Safari and Firefox ran on GitHub only. The weekly builder task
  (Wednesdays 23:15 UK) is made at this release, and its first run is untried.
- Checked: the whole suite, the page in every engine and every system on GitHub; the
  maintainer's copy rehearsed (47 steps) and new copies from 4.14.0 (60) and 4.15.0 (56).

## Known red
- `test_a_people_run_reaches_the_people_who_answer.py::test_a_batch_is_shown_only_what_involves_its_own_notes`
  failed twice on GitHub in 4.15.0 and never locally; its message names the cause next time.
