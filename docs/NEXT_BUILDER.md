# Notes for the next builder

Written at the end of 4.7.0 (2026-11-02) for the chat that builds the next version. Read
MAINTAINING.md first; this is only what 4.7 left.

## Do first, for [Unreleased]

Built into [Unreleased] on 2026-11-02, not released (the maintainer: release only when they say):

- **Done**: item 0, the news never empty (the reader widens to a week and a month inside its
  one call, each item ends in how to use it, nothing new carries the last items with their
  day, the page shows the newest earlier brief's news with `news_date`); the brief's FOR
  CLAUDE lines are never cut at `TEXT_MAX` (the cut dropped the republish and the page's
  update on the maintainer's real state); 4.7.0's runs read (Windows set-up step given 45
  minutes; the harness reads survive a page reloading itself in Firefox); Firefox reduced
  motion (its own Firefox with `ui.prefersReducedMotion`, and a skip saying so where the
  engine ignores it); the update line moves by transform; a quiet day fills Today ("Then",
  the next step) and Coming up (what is due next); a due item keys its person by `item`.
  Then, at the maintainer's word the same day: Today is the one most pressing thing (today's
  booked thing, an interview tomorrow, one in the prep window with no prep, rolled over,
  due today, then the prepared interview) with facts beside it, and may be in Next three;
  news points split into what, use and source (`app_model.news_parts`); the brief's upkeep
  copies a stage `outcome.md` marks done onto its tracker row (`brief.stages_into_tracker`).
- **Still to check**: the first brief after these land (07:56 UK) republishes the
  maintainer's page and fills News with three items that each say how to use them
  (`list_events` on their helper chat). The Firefox reduced-motion and reload fixes are
  untested locally (no Firefox in the container): read the next Everywhere run.
- **Looked at with real data, left as is**: "contacts replied" counts everyone who wrote back
  in a thread in the last 30 days (47 on the maintainer's data, plausible with two live
  processes); the Outlook link was not looked at.

## How to work (the maintainer, 2026-10-30 to 2026-11-02)

- **Decide, never ask.** Make the call, do it, say it in one line, with a reason.
- **Be smart about what a person sees, and look before calling it done.** Screenshots
  (`run("shots", ...)` with `LJS_SHOTS`) at 1280x760, 1440x900, a tablet and a phone, and a
  fuller sample than the standard one when a panel's behaviour depends on how much it holds.
  The maintainer reads alignment and white space closely: a ragged column, a list cut beside
  empty space, a panel left blank, all got noticed within minutes.
- **Nobody is ever told to type "update" or to refresh.** Updates reach everyone by the next
  morning's brief; the page keeps itself current; Refresh appears by itself only when data
  is older than today. Say how a change reaches existing people before building it.
- **Merge to master when green; release when the maintainer says**, and run an independent
  review of `[Unreleased]` before the release (4.7's found nine real bugs).
- **Keep it cheap**: few steps, no polling, the whole suite on GitHub only. The push gate's
  denylist needs the app's master beside the maintainer's copy: their copy is never changed,
  so copy it to the scratchpad, add the `app` remote there and fetch, and point
  `push_gate.sh` at the copy. Clear `/tmp/ljs-push-gate` if an earlier build ran without it.

## What 4.7 decided, to keep

- **What the brief's news watches is the person's own list** (person.json `brief.watch`:
  `{what, every: day|week|month}`, `"by": "you"` for their own). Claude writes it from the
  profile (`brief.py watch write`, at setup, by the `brief-watch` upgrade, and by the brief
  when `watch_needs_writing`: never written, or `watch_from` no longer matches
  `watch_basis`). Claude's rewrite keeps the person's items and never re-adds
  `watch_dropped`; 4.6's `leave_out` kinds are passed on in words (`turned_off_before`).
  Searches: the employers in play (two, placed by the last part of the person's own
  location), then due items, longest waiting first, six at most. Due by days since last
  searched (1, 7, 28); planned at the gather, noted only when `brief.py news` runs.
  No tables of banks, countries or languages anywhere; the reader gets a language code.
- **Edit the brief**: Also watch (B6) and How often (B7), Stop watching (B3), Watch again
  (B8, only when something was stopped); one shared list per Apply (`watch_state`).
- **The page keeps itself current**: on show, focus, back online and every 5 minutes it reads
  `meta/now` once and resubscribes when behind (never while the store is failing: the
  subscriptions' own backoff retries). `meta/now.page` (written by `app.py view` from the
  version recorded at publish) above the page's own `model.app.page` reloads it once per
  version, never mid-typing or with a sheet open, and only where session storage works.
  Refresh wakes a chat only for data older than today, with the cost gauge; otherwise it
  only resubscribes, free.
- **The brief republishes a page left behind** (`page_behind`, `behind_steps`), before its
  data.
- **A stage line carries what it is**: `(due DATE)` for a test, `(scheduled DATE HH:MM ZONE,
  N min, with WHO)`, ZONE a zone's own name or the invite's word; `interview_pack.py book
  --due --minutes --zone`. A zone it cannot place gives no time. Words resolve: the
  person's own zone if it uses the word, then `app_model._ZONE_WORDS`, then the standard
  library's zones; a word several zones share at different hours gives no time.
- **Settings**: `prep_days` (the next interview leads the Brief from 2, 7 or 14 days) and
  `calendar_reminder` (15, 60, 1440 minutes or none; all-day items the afternoon before).
- **The Brief**: Today leads with what is on today (a call or a test due today before a
  later interview); the strip and Coming up's day headings mark today in a clear green
  and tomorrow in gold (palettes `day-today`, `day-tomorrow`), never red, which read as a
  threat; nothing else. Compared before choosing (2026-11-02): the red circle in Apple Calendar
  is that brand's own colour, not a warning; Google Calendar marks today with its accent; Asana shows
  due today and tomorrow in green and keeps red for overdue. The colour is never the only
  sign: today is boxed on the strip, and Coming up says "Today" and "Tomorrow" in words, so a
  green and gold someone cannot tell apart lose nothing; each
  person's step and day sit in one column (subgrid). `fitBrief` takes, while the Brief runs
  past the window, the one last item whose going saves most, never one beside white space,
  with `data-fit` "fewest,start,keep" (Today's questions 2,3,0; Coming up 2,2; Jobs 2,3,2;
  People 2,3,3); News and Next three never shrink; a short window scrolls.
- **Tips**: a first-time line is never shown where the tracker or the briefs show the work
  was done before (`tips.done_before`).

## Left, on purpose, with the reason

- **The three older pages titled with the maintainer's name** stay in their Claude list;
  only the pinned one is used. Deleting is theirs to ask for.
- **Vietnamese day names** fall back to the language's short form ("Thứ 2"), wider than two
  letters; legible, not checked on a phone.
- **A watch item's frequency cannot be changed in place** on the page: stop it and add it
  again, or say it in a chat.

## Not tested

- The self-refresh and the self-reload in the real Claude app's frame (only the harness's
  fake runtime), and on a laptop waking from sleep.
- Safari's and Firefox's engines locally (not installed in the builder's container): only
  the release PR's runs, item 1 above.
- A brief rewriting the watch list from a real profile in a scheduled run.
