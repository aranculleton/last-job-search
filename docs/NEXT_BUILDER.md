# Notes for the next builder

Written at the hand-over of 9 November 2026, with no release made: the maintainer asked for a
new builder chat before releasing. Read MAINTAINING.md first; this is background, never a list
of work: a builder starts only from the maintainer's notes (MAINTAINING.md, "How a builder
works").

## Where things stand

- **Nothing released since 4.13.0.** `[Unreleased]` holds the maintainer's notes of 7, 8 and
  9 November: the helper hand-over, the Brief's room, the referral's end, a round already had,
  Help Claude do more, notes waiting on a profile read, the quiet character count, cue words in
  preps, six-second toasts, and the helper bugs below. It is a minor version (4.14.0) when they
  say "release it": it adds things a person notices.
- **The last pull request may still be open**: "Three helper bugs: a lost finish, a tweak's
  answer, unversioned page updates" on `claude/clever-wright-971fgq`, which also carries the
  calm Contacts card and computer-only reads. Merge it once `Fast checks` is green, before
  anything else.
- **The update was rehearsed** (`tools/rehearse_sync.py`) on the maintainer's copy before the
  last two rounds (47 of 47); rehearse again before the release.
- **The README pictures need remaking at the release**: the Brief and the Contacts card both
  look different now. The Brief and the tour were retaken once this version and were good, but
  that commit never left its worktree.

## What this version decided, to keep

- **Every Linux job runs on `ubuntu-24.04`.** `ubuntu-latest` became 26.04 on 9 November 2026:
  setup-python has no 3.9 there and Playwright 1.56.1 installs no browsers on it. Move back once
  both do.
- **Safari 26.0 is Playwright 1.56.1's WebKit** (what CI's Everywhere runs) and it measures
  before the page's zoom; a newer WebKit does not. Reproduce it locally by installing
  Playwright version 1.56.1 with npm in a scratch folder and pointing `NODE_PATH` at its `node_modules` with
  `LJS_PW_ENGINE=webkit`. Tests read boxes with `__drawnRect`, never `getBoundingClientRect`
  divided by the zoom.
- **`app.py done` names each batch for its item** (`page_db.batch_name`): one file shared by
  every finish lost the first of two.
- **A tweak's written answer goes to its card's own thread** (`page_db.card_thread`, the page's
  `cardThread`), with the person's words first; `done --unchanged` says a tweak left the words as
  they were. The page also works it out by itself: drawn after the finish with the rev unmoved,
  the card says the words are unchanged.
- **`view` never writes a screen with no version unless the screens were read just now**
  (`page_reads.screens_read`): screens laid from the mirror that lack a record the page holds
  make it ask for a read of `screen` first.
- **Work about a note waiting on a browser read is the computer's** (`reading.needs_browser_read`):
  routed at queue time, refused to a cloud chat in `next_item`, and put back in the queue if a
  cloud chat tries to finish it.
- **The live helper comes back half an hour after a hand-over whenever it kept the old helper,
  for any reason** (`tidy.plan`'s `recheck`).
- **A Brief panel spends only the room it has** (`fitAir`): short lists boxed and spread a step
  at a time up to 24px, the pills under sparse content, the progress chart up to 160px.
- **Toasts last six seconds** (twelve for a failure); their Undo stays on the item after.
- **A page test that builds the engine in-process puts away the modules it first loaded**
  (`test_the_page_shows_the_engines_own_data.py`): `state` and `open_actions` keep the paths of
  the copy they first loaded under, and a later test in the same worker read the wrong folder.

## Built from notes but not finished

- **The Brief's top row first** (the maintainer, 8 November): "prioritise immediate actions so
  if the top row has like enough calendar things to warrant a second row so like 4 things, or
  the today thing or next three etc that expands to the original size, rather than ALWAYS having
  a long list for jobs, people etc." Today, Coming up and Next three should get the height their
  content needs first, the second row's long lists giving way. Started by a helper and not
  finished; nothing of it was kept.
- **Your progress, polished** (same note): "make the progress dynamic expanding prettier/more
  polished, maybe the boxes slightly expand? Doesn't look great in its current form." Not built.
- **`wake` one version behind after the person answers a card**: the page raises the work's
  version when they answer, so a wake read before that pins to the old one and is refused; the
  existing `app.py version` repins it. Not changed.

## Not tested, or found and left

- **The moved-clock suite** (Everywhere's 30, 90 and 400 days) fails three tests that predate
  this version: `test_sync_app.py::test_the_app_watch_runs_once_a_day_not_on_every_sync`,
  `test_the_page_helper_stays_thin.py::test_a_save_asked_for_is_aged_on_the_clock_that_asked`
  and `test_a_search_prints_its_own_table.py::test_the_golden_round_prints_its_table_and_writes_the_same_files`.
- **Safari 26.0** fails three page tests that also fail on master before this version:
  `test_the_brief_uses_its_room.py::test_the_jobs_panel_lists_more_where_it_has_room` and two
  clock tests in `test_the_page_works_in_a_browser.py` (progress moving with the clock, work
  picked up showing its clock).
- **Windows** ran only on the Platforms runs of 7 November; nothing since.
