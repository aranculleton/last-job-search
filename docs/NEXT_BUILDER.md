# Notes for the next builder

Written at the end of 4.9.0 (2026-11-04) for the chat that builds the next version. Read
MAINTAINING.md first; this is only what 4.9 left.

## Do first, for [Unreleased]

- **The real-page report.** After 4.9.0 reaches the maintainer's copy, their helper chat walks
  the key journeys on the real page (chat send and paste, every work state, booking offered
  days, a batch of drafts, contacts with rule-breaking candidates) and reports. That report is
  the audit's final gate: fix anything it finds first, as a patch release if it stops something
  working for anyone.
- **The first full-size page in parts.** Every page republishes once into the new shape at its
  update (a small page.html plus about 70 content-named code files, sent in batches). Only a
  small probe was published on the real host (all its checks passed); the first full-size one
  is the maintainer's. If it says "did not load fully" after its 15 minutes of "being updated",
  read tools/app_page.py `plan` and templates/app/guard.js first.
- **The maintainer's own tests.** Seven of them pinned behaviour 4.9 changed on purpose (job
  boards held to the search window, the scorer's baseline, a sample note using initials their
  own rules ban); the update tells their chat to bring them in line. Check it did.

## How to work (the maintainer, 2026-10-30 to 2026-11-04)

- **Decide, never ask.** Make the call, do it, say it in one line, with a reason.
- **Use the app yourself, as a tired job seeker would, and as a stranger would**: a copy with
  no tie to the maintainer, chat only, on a phone, weeks behind, in another country. 4.9's
  stranger audit found 85 things the maintainer's own use never showed.
- **Token-cheap, and still certain.** The maintainer runs short of tokens: no separate skeptic
  per finding (a fix's test that fails first is the check), one reviewer for what merges broke,
  scripts for coverage, the whole suite on GitHub only, one push per round.
- **Helpers in worktrees start on old master**: tell each to `git reset --hard` to the
  branch's head first. Merging many helpers is where new bugs come from: give the merge to one
  careful agent with both sides' outcome tables.
- **The container can restart mid-night** and lose every background agent: helpers commit
  early and often; a lost one is re-created from the same brief.
- **The push gate's leak scan reads every patch since master**: invented names only, never the
  maintainer's employers, contacts or handle (write the app's address as
  `aranculleton/last-job-search` in full); when an old patch holds a flagged line, fold the
  unpushed commits into one (`git reset --soft origin/<branch>`).
- **Say nothing about runs on a push you have replaced.** Speak when the latest push is green
  or truly red, when work merges, and when the release is out.

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
- Safari, Firefox and Windows on 4.9.0 ran on the release pull request; everything they found was
  fixed in it (a phone's Chat opening above the newest message, a long paste in Firefox, Windows
  day formats and its bash) except one Windows-only timing test that failed once and passed on
  the run before: tests/test_a_faster_round_finds_and_scores_the_same.py
  ::test_a_paced_boards_wait_does_not_hold_the_other_postings (one worker, a paced board and
  LinkedIn; it compares send times). Look at how hydrate schedules a paced board on a slow
  Windows runner before trusting it there.
