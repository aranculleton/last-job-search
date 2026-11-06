# Notes for the next builder

Written at the release of 4.13.0 (2026-11-06), for the chat that builds the next version. Read
MAINTAINING.md first; this is background, never a list of work: a builder starts only from the
maintainer's notes (MAINTAINING.md, "How a builder works").

## What 4.13.0 decided, to keep

- **Safari measures before the page's zoom, Chrome and Firefox after.** Anything set against the
  window (innerHeight, scrollTop) turns a measured box into the window's px first
  (`screenPerPx`, `screenY` in app.js; the tests' `__drawnRect`). Chrome can measure Safari's way
  in a test (`measureBeforeZoom` in the harness), so the ordinary run holds it.
- **A computer that reports no pointer is a computer.** Headless Firefox, a remote desktop and a
  keyboard alone report `pointer: none`; every laptop rule lists it beside `pointer: fine`.
- **Everywhere by hand takes `variants` and `tests`**, and its summary prints each failure's
  message whole (`--tb=line`, `verbosity_assertions=2`). A probe test that raises its
  measurements, run there on a branch, is the cheap way to see what Safari or Firefox draws
  (this container has neither); remove it before merging.
- **The Brief takes its compact shape whenever the whole of it does not fit**, not at a fixed
  height (`brief-short` on the root, set by `fitBrief`), and a last few px of scroll come off the
  stretched rows. Its fit is kept by the window's size and the zoom.
- **News shows the person's News items setting (3 unless chosen)**; a point written "... Use it:
  ..." is set in its two parts (`app_model._NEWS_USE`). News is never clipped: a cut point had no
  way to open (2026-10-30).
- **The Chat panel sits left or right** (`ljs:dock-side`, Settings > Look and the panel's arrow:
  one choice). Earlier messages come only by Show, never by scrolling up.
- **A job tapped keeps its place on Jobs while the person stays** (`S.jobsHeld`).
- **Toasts: two at most, "+N more" opening Claude's work, a ring round the close for the time
  left.** A redraw is never started from inside a redraw (`release` defers).
- **A draft left out as not a fit is `result.left_out`**: said as its reason, never Try again.
- **Saving**: a landing pushes the chat's branch before the check; the chat that answers the page
  batches saves asked within five minutes, but only after its work is pushed; a round's number
  counts GitHub's rounds and a clash is renamed; lost work is asked for once, then said; the
  steps unsubscribe from a save's pull request at once.
- **The page helper**: the hand-over ends on a new day in the person's zone; the listener starts
  the fresh helper with `create_session` itself (the scheduled-task route is gone, its names
  listed in docs/removed_names.json); a helper that handed over does no more work and archives
  itself once its save lands; work named at a pass's end and left holds the helper's turn once.
- **Follow-ups never ask the person to write them.** What code cannot write goes to Claude, who
  looks first (their profile as read, the employer's news and roles, the person's profile), then
  writes a plain follow-up. A "don't repeat" rule never turns plain follow-ups off.
- **Profile reading uses the page's own tab only**, checks sign-in by reading it, and a sign-out
  is one To do card. A web page cannot hide Claude's browser pane, so a read is visible if that
  tab is open.
- **A general resume is grounded like a tailored one**, and its bullets are chosen with its
  pencil (Tweak panel, Bullets).

## Built from notes but not finished

- **Small taps still take 2 to 4 minutes** (the maintainer's note 11). The code is under two
  seconds; the time is about twelve model steps in a fresh helper. Recommended, not built: the
  listener does code-only taps itself with no helper, and the late-read queries go with the last
  batch; measure with `helper_usage` before and after.
- **The suite's time is unchanged** (note 5): 4.12 added about 5%, the rest is fresh
  `tools/app.py` processes importing 96 modules and compiling about 1,745 regexes. Lazy regex
  compiling across about 20 modules would save roughly 15%; not done, being wide.
- **What's new in Settings reads as cluttered** (the maintainer, at release): every version's
  lines and "Changes made for you" in one long block. Not touched.
- **Advanced holds two settings by design** (4.12: only what can slow things or use the
  allowance); the maintainer asked about it at release.
- **To do's folds**: one card left over shown in place rather than "Show 1 more", and the folds
  as quiet lines rather than whole-width bars, were built after the release was asked for and go
  in the next version's first merge (they are on master after 4.13.0 if that merge happened).
- A record with a vanity LinkedIn address and an export in the member-id form, with no message
  to match on, can still become a second record. "Make a fresh one" on a general resume starts
  its bullets again. Undoing "Not this person" does not put them back on the reading list.

## Not tested at this release

- **Windows** ran only on 4.12's runs and this release pull request: its landing test's fix
  from 4.12 (shlex.join) and everything since are read there.
- **Safari and Firefox** were run by hand on the page's fit, Chat, review and file-name tests and
  the layout promises: all passed. The rest of the page in those engines runs on the release pull
  request's Everywhere.
- **The rehearsal** (`tools/rehearse_sync.py`) passed on the maintainer's copy at release, a cloud
  and a computer chat taking the update at once, their own tests and the quick check included.
  It needs a full clone of their copy (a filtered one cannot be copied): the push gate keeps one.
- An `app.py model` build reads the checkout's own `origin/claude/*` branches (through
  `report.stuck`), so a page test depends on the checkout it runs in.
