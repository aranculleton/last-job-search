# Notes for the next builder

Written at the end of 4.9.0 and 4.9.1 (2026-11-04) for the chat that builds the next version. Read
MAINTAINING.md first; this is only what 4.9 left, as background, never a list of work.

## Nothing to start from here

The maintainer said on 2026-11-04 that what 4.9 left open is settled. Everything below is
background: a builder starts work only from the maintainer's notes (MAINTAINING.md, "How a
builder works").

## How to work

MAINTAINING.md now holds it for good: "How a builder works" (decide, never ask; cheap and
still certain; helpers in worktrees; the leak scan) and, under "Releasing", the lenses a
version is reviewed through instead of another whole-app audit (the stranger, real scale,
two chats at once, every engine, with Platforms started by hand early). The lessons 4.9 paid
for are rules under "Developer rules".

## What 4.9 decided, to keep

- **The page in parts** (tools/app_page.py `render_parts`, `plan`; tools/app_listen.py
  `parts_plan`): every republish lists what the page holds first and sends what it lacks; a
  page that did not load fully asks for itself whole; one built under 15 minutes ago says it is
  being updated and reloads. Never one big file again.
- **The brief stays bound to the chat that holds the copy** and sends its headline with
  PushNotification, asked from one place only (the lines tools/brief.py prints). Nothing ever
  moves a working brief to a fresh-chat task (such a run has no copy and no hook).
- **The one hook holds a turn** (reaction, page owed, improvements unstarted, unsaved work,
  brief push unsent): one hold a turn at most, each with its limit, in the form the chat's
  Claude Code version honours, never in the app, the example person or a job chat (recorded
  when `app.py start --work` runs).
- **One clock**: `person.today()` wherever a day is counted.
- **Computed once, in the engine**: counts, who is owed, who may be shown (`surface.held`, from
  the person's own rules, never names), statuses. The page renders them.
- **An employer bar applies only when the profile states one** (employer tiers or
  BAR_FRONTIER); nothing the maintainer set is applied to a stranger.
- **Merges settle themselves**: person files by `merge_state.settle` in a landing and when an
  update comes in; a document the app writes and dates keeps the later; two pages published by
  two chats keep the first; told records live outside setup_answers.json.

## Left, on purpose, with the reason

- A resume the maintainer must never send still sits in their page's file store: only a chat
  on their copy can delete it, and the app no longer offers or links it.
- Briefs already set at 7:38 in US Pacific or Mountain time keep their time: nothing changes a
  working brief. New ones there default to 5:38.
- A branch from the chat-only fix's first attempt (built on older master) is not merged; its
  third round's decisions were carried over by the stranger groups, as the notes say.

## Not tested

- The host's answer for a code file that is missing (a 404 or a page): the guard handles both
  for scripts, but it was not seen on the real host.
- A push from a real scheduled brief beyond the one recorded run ("Mobile push requested").
- The maintainer's helper said in one chat that the brief's chat had lost the files; 4.9.1
  notices that (`routines.no_copy`) and moves the brief, tested on records, not yet on a real
  task that lost its copy.
- Safari, Firefox and Windows on 4.9.0 ran on the release pull request; everything they found was
  fixed in it (a phone's Chat opening above the newest message, a long paste in Firefox, Windows
  day formats and its bash) except one Windows-only timing test that failed once and passed on
  the run before: tests/test_a_faster_round_finds_and_scores_the_same.py
  ::test_a_paced_boards_wait_does_not_hold_the_other_postings (one worker, a paced board and
  LinkedIn; it compares send times). Look at how hydrate schedules a paced board on a slow
  Windows runner before trusting it there.
