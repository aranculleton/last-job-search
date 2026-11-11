# Notes for the next builder

Written at the release of 4.15.0 (2026-11-11), for the chat that builds the next version. Read
MAINTAINING.md first; this is background, never a list of work: a builder starts only from the
maintainer's notes (MAINTAINING.md, "How a builder works").

## What 4.15.0 was

The maintainer asked for everything fixed and nothing left over. Two audits of 4.14.0, two
independent reviews, a UX review (U-1 to U-20), a cost audit (E-1 to E-18), an engine review
(12 items), a screen review of every page (40 findings) and the bugs the maintainer's helper
chats recorded (H-1 to H-8) were each fixed with a test that fails without the fix. Every one
of the 40 screen findings is fixed; none was set aside. The audit and review files themselves
were working notes and are not in the repo; the CHANGELOG names each fix.

## What 4.15.0 decided, to keep

- **The Brief says what the person owes.** Its Jobs line counts drafts ready, waiting on you
  and still to make in Jobs' own numbers; one Claude is making is said in Claude's work, and on
  the Brief only when nothing else is owed. On a short laptop window (660px tall or less) the
  panels keep 8px above and below, not 12. Next three keeps its three steps on any window
  600px tall or more (`fitBrief`, `held`). Coming up's week shows 5 or 7 days in a narrow
  panel (its container rules sit after the strip's own fourteen columns, which won before).
  Waiting on you puts the step under the name below 280px of panel.
- **Line breaks differ between Chromium versions.** GitHub's page tests run Playwright
  1.56.1; a cloud container has 1.63.0. A break the older one takes and the newer does not
  ("· Why" alone on a line) is fixed by leaving no plain space where no break is wanted.
- **The page's one-document cap is 1.5 MiB.** It is published in parts
  (`app_page.render_parts`, with their own size and count tests), so the cap on the one
  document only catches something embedded by mistake. The code passed 1 MiB in 4.15.0.
- **Local browser tests draw in GitHub's font.** `tests/test_the_page_works_in_a_browser.py`
  `_fonts_as_ci` points Chromium at DejaVu Sans unless `FONTCONFIG_FILE` or `LJS_SHOTS` is
  set. A cloud container has only Chromium: Safari, Firefox, a Mac's type (Inter), Windows'
  type (Liberation Sans), French, German and the far time zones run on GitHub (Everywhere).
  The Mac and Windows type can be tried locally with the fontconfig files `everywhere.sh`
  builds (`type_as`).
- **The layout probe names what sticks out anywhere**, text spilling from its box included
  (`harness.js`, `elsewhere`), and the layout scenario takes a `timezoneId`.
- **A lock is read twice before it is judged stale.** `land._live` reads an empty lock again
  for up to 0.2s: one caught between its file and its words was aged by the disk's clock, and
  on a moved clock two landings both took it.
- **No git where the app looks** is tried only where git is not in a folder the app adds to
  the PATH (`local_path.extend`: Homebrew's on a Mac). GitHub's Mac keeps git there.
- **The platform report prints on any console**, a character a Windows console has no letter
  for replaced, never crashing the report of a failing suite (`platform_check._say`).
- **A person's own set-asides with no day hold nothing until they have one** (`excluded_date`);
  the dated set-aside upgrade gives existing ones their day.
- **The interview method is at 53**: follow-ups said once a part, records on the person's day.
- **The README pictures** were taken with `LJS_SHOTS` at scale 2 (the phone at 3) from the
  sample, the tour without Claude's work open, then `tools/readme_pictures.py`.

## Not tested at this release

- **Windows and Linux computers** with the desktop app, and the cloud reading LinkedIn itself:
  as at 4.14.0, only a Mac was used for real.
- **One networking test failed twice on GitHub and never here**:
  `test_a_people_run_reaches_the_people_who_answer.py::test_a_batch_is_shown_only_what_involves_its_own_notes`
  (exit 11, "too alike"). It passed in every clock variant and 18 local runs; its message now
  prints the short list and the batch's output, so a next failure names its cause.
- **The rehearsal** on the maintainer's copy passed every step apart from their own tests: 6
  of them expect older app behaviour (2 already did before this release, 4 are set-asides with
  no day). Their copy's own-tests step brings them in line by itself.
- **Safari and Firefox** were run on GitHub only. On the release commit every check passed:
  the fast checks, Python 3.9, the page in Chrome, Safari and Firefox, a Mac's and Windows'
  type, French, German, the far time zones, the moved clock in all seven variants, and the
  person's setup on Ubuntu, a Mac and Windows (all three parts, both shells).
