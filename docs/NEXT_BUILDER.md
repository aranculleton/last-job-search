# Notes for the next builder

Written at the end of 4.3.0 (2026-10-29) for the chat that builds the next version. Read
MAINTAINING.md first; this is only what 4.3 left.

## Left open

- First: the release's slowest check is Windows' set-up and suite, about 26 minutes (11 of
  them the suite on four workers). Split its suite across three runners, as a matrix in
  Platforms, for about 15: free on the public app, and it does not wake a builder more
  often if each shard ends in the same summary.
- An interview with no application ("Something else" in I have an interview) opens Chat
  rather than a form.
- "Employers you follow" can be added on the page (Jobs, Change the search, Watch an
  employer) but not taken off there.
- No page door yet for the competency expansion (`/expand`), the learning plan
  (`/upskill`), adding a named job site (`/add-portal`) or a custom template
  (`/add-template`); the questions a past interview asked are told in Chat.
- The 4.2 newcomer journey findings were never closed as a list: check the apply link, the
  searching state, applied shown the same everywhere, a double paste, forms rather than chat,
  and the wording.

## Not tested against the live services

- The daily tidy-up's calls (`list_sessions`, `get_session`, `archive_session`) and an older
  brief's move into the page's chat: tested on the shapes those tools return.
- The brief's bell opening the helper's chat from inside the Claude app (tested with
  `window.open` stubbed).
- The 200,000-token history cap (`CLAUDE_CODE_AUTO_COMPACT_WINDOW` in `.claude/settings.json`):
  set as Claude Code's docs describe, not yet seen compacting a live chat.
- The page store beyond the probe page, and a republish's read cost on a real page.

## Platforms

- Windows passed the person's set-up and the whole suite on 4.3 (25 minutes in one worker).
  The chat-on-a-computer job ran past 40 minutes with no log to say where; each command in it
  is now named as it starts and gives up after ten minutes, and the copy's own check no
  longer builds a Python 3.9 environment when only personal files changed.
- Every suite runs in parallel workers, and the page's browser tests run in their own CI job.
  Windows runs on a release pull request, weekly and by hand, never on an ordinary change.
- Everywhere (`tools/everywhere.sh`, on releases and weekly) checks the page in Safari's
  engine, Firefox, a Mac's and Windows' type, French and German and the far time zones, and
  the rest with the clock moved on, in the far time zones, from an odd folder and on the
  newest Python. Before it, the page was only ever drawn in one font: the layout tests pass
  in Inter here and failed in the DejaVu Sans font on CI's Linux, 37px over on a phone.

## The maintainer's own copy

- It is on an app from before 4.0. After the update, 14 of its own tests fail, all on files
  unchanged since 4.2 (verify_batch, record_drafts, the stage_picks audit holds,
  `referral_ask`, the cover-letter template, network state): bringing them in line is the
  copy's own step (RUNBOOK.md, "Your own tests fail after an update").
