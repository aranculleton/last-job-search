# Notes for the next builder

Written at the end of 4.4.0 (2026-10-30) for the chat that builds the next version. Read
MAINTAINING.md first; this is only what 4.4 left.

## How to work (the maintainer, 2026-10-30)

- **Decide, never ask.** Every design, tooling and gate question is the builder's to settle
  (MAINTAINING.md, "The builder decides"). Make the call, do it, say it in one line.
- The push gate scans every patch and every changed file whole; a file identical to the app's
  master is not rescanned there, as the maintainer's own check already treats it.

## Left open

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

- The pre-approved writes to the page's data and comments (4.4): tested on the settings the
  app writes, never in a live chat that was asked before. A chat started before the update
  keeps its old settings, the 200,000 token cap included, until it is started again.
- Big jobs in a chat of their own (4.4) and as background agents inside it: tested on the
  messages the app sends and the cap, never with real chats or agents side by side.
- The page reading LinkedIn itself in the Claude desktop app's browser
  (host:claude_browser): proven live on 2026-10-29 for the feed and one profile's three
  pages; the whole flow (a queue read by itself, "Write my notes", a sign-out and
  LinkedIn's check) is tested with the browser simulated only.
- The daily tidy-up's calls (`list_sessions`, `get_session`, `archive_session`) and an older
  brief's move into the page's chat: tested on the shapes those tools return.
- The brief's bell opening the helper's chat from inside the Claude app (tested with
  `window.open` stubbed).
- The page store beyond the probe page, and a republish's read cost on a real page.

## Platforms

- A release's Windows suite now runs in three parts side by side (`LJS_SUITE_SHARD`, split
  by file size in `tools/platform_check.py`). 4.3's one runner took about 26 minutes; on
  4.4's last change each part took 9 to 10 minutes. The release pull request touched no path
  that starts Windows, so its one Windows fix (the quick landing check's test run under Git
  Bash, not the Windows Subsystem for Linux) was checked on Linux only: the weekly run is
  its first on Windows.
- Safari's engine leaves the space before an inline-block link out of `innerText`, though it
  lays the line out as Chrome does (measured 2026-10-30). A page test that reads words
  around a link allows for it, rather than reading the layout as wrong.
- Every suite runs in parallel workers, and the page's browser tests run in their own CI job.
  Windows runs on a release pull request, weekly and by hand, never on an ordinary change.
- Everywhere (`tools/everywhere.sh`, on releases and weekly) checks the page in Safari's
  engine, Firefox, a Mac's and Windows' type, French and German and the far time zones, and
  the rest with the clock moved on, in the far time zones, from an odd folder and on the
  newest Python.

## The maintainer's own copy

- It is on an app from before 4.0. After the update, 15 of its own tests fail, all on files
  it has not changed since 4.2 (verify_batch, record_drafts, the stage_picks audit holds,
  `referral_ask`, the cover-letter template, network state): bringing them in line is the
  copy's own step (RUNBOOK.md, "Your own tests fail after an update").
