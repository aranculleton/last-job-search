# Notes for the next builder

Written at the end of 4.8.0 (2026-11-02) for the chat that builds the next version. Read
MAINTAINING.md first; this is only what 4.8 left.

## Do first, for [Unreleased]

1. **Read what 4.8.0's last runs found.** At the merge, every platform had passed on the
   version's final tree (Windows parts 1 to 3, Mac, Firefox, German and far time zones, the
   Mac and Windows type in French) except two still running: the Windows Git Bash set-up (its
   long step now has 45 minutes) and the moved-clock suite. The release pull request runs all
   of them again: read each summary line and fix what is real.
2. **Check the first brief after 4.8 on the maintainer's copy** (07:56 UK the next morning;
   `list_events` on their helper chat): the page republished (the FOR CLAUDE lines are no
   longer cut at 2,500 characters, which had dropped the republish and the page update on
   their real state); News has three to five items, each ending in how to use it; and a live
   process whose record ticks a stage done gets that stage on its tracker row.
3. **Safari's self-reload test**: the harness's last unprotected reads (`settle`, `goto`, the
   end of `S.engine`) now wait out a page reloading itself. Confirm Safari is green on the
   release pull request.

## How to work (the maintainer, 2026-10-30 to 2026-11-02)

- **Decide, never ask.** Make the call, do it, say it in one line, with a reason.
- **Use the app yourself, as a tired job seeker would, and let that drive the version**:
  journeys on a phone and a laptop (the morning glance, a reply, an application, an interview,
  a mistake undone, a brand-new person), dead ends, counts that disagree, things said twice.
  4.8's walk-through found more than its code review did. Helpers on separate screens, each in
  its own worktree with tests, merged by you, kept that fast.
- **Look before calling it done**: screenshots at 1280 and 1440 wide, a phone, light and dark,
  and a fuller sample when a panel's behaviour depends on how much it holds. The maintainer
  reads alignment, white space, bold and underlines closely, and sees the screenshots you read.
- **Say nothing about runs on a push you have replaced** (the maintainer, 2026-11-02: "why do
  u keep reporting on this random older push"). Speak when the latest push is green or truly
  red, when work merges, and when the release is out.
- **Keep it cheap**: few steps, no polling, the whole suite on GitHub only, one push per round.
  The push gate needs the app's master beside the maintainer's copy: copy their repo to the
  scratchpad, add the `app` remote there, fetch, and point `push_gate.sh` at the copy.

## What 4.8 decided, to keep

- **News is never empty.** The reader widens to the last week, then the last month, inside
  its one call (`brief.wider`, at most eight searches), returns three to six items each ending
  in how to use it, never a link sent in the last four weeks (`links_sent`), and no month on a
  search in a month's first week (`_dated`). Nothing found: the last items are carried with
  the day they were gathered, ending four weeks from it (`carry_news`); the page shows the
  newest earlier news with that day (`_news_fallback`, `news_date`). Points are split into
  what, use and source (`app_model.news_parts`).
- **FOR CLAUDE lines are never cut**; only the message gives way to `TEXT_MAX`.
- **Today is the one most pressing thing**: today's booked thing as itself (an interview, a
  call, a test, by kind then time), an interview tomorrow, one in the prep window with no
  prep, what rolled over (replies first), what is due today, the prepared interview, the
  brief's first step. Beside it, the likely questions or a few facts, never one the title
  says. It comes again in Next three only where there is room.
- **One count of jobs to look at** (`jobToLook`): new, a good fit, not closed, not drafted or
  in a process, not just set aside; every count and list uses it.
- **A drafted message is opened, never drafted again** ("See the draft"), and "I sent it"
  counts on every screen at once (`sentHere`).
- **A stage `outcome.md` ticks done** after the row's last note of the person's own goes onto
  the tracker row, once (`brief.stages_into_tracker`); app notes and hand-written headings
  never count.
- **The page**: one aligned dot for every Brief point; weekly bars as boxes on a baseline,
  labelled by week; the menu folds to 24px icons (`nav:mini`, kept per device); inline styles
  set sizes only, never a colour; the week labels use the page's small size (seven type
  styles a first screen).
- **Windows**: a research lock refused for a moment is waited for (`_locked`, `_write_json`).

## Left, on purpose, with the reason

- **A To do card hidden by mistake is remembered on that device only**: it can now be brought
  back from the end of To do; keeping hides across devices means recording them as actions.
- **The draft bin's own message** ("Not applying: ...") is unchanged; a test pins it.
- **"Contacts replied"** counts everyone who wrote back in a thread in the last 30 days:
  plausible on the maintainer's data, not changed.
- **The three older pages titled with the maintainer's name** stay in their Claude list; only
  the pinned one is used. Deleting is theirs to ask for.

## Not tested

- Safari's and Firefox's engines locally (not installed in the builder's container): only the
  pull requests' Everywhere runs.
- The page in the real Claude app's frame, and on a laptop waking from sleep.
- A brief rewriting the watch list, widening the news and carrying it, in a real scheduled run.
