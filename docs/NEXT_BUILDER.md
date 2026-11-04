# Notes for the next builder

Written at the end of 4.9.0 and 4.9.1 (2026-11-04), and brought up to date the same evening when
the builder chat for the next version handed over before its release, its chat too long. Read
MAINTAINING.md first; this is background, never a list of work: the maintainer's notes say what
to build.

## Nothing to start from here

A builder starts work only from the maintainer's notes (MAINTAINING.md, "How a builder works").
The sections below say where the unreleased version stood at the hand-over, so a note that says
"carry on" can be done in full without guessing.

## Where the unreleased version stood (4 November, evening)

Everything below is in `[Unreleased]` in CHANGELOG.md, nothing released since 4.9.1.

- **On master**: pull requests 164 to 167 (the builder waits for notes; README pictures named
  after their contents; the brief's phone notification as a setting, off by default; the page's
  walk-through fixes: Claude's work as a side panel with one pill, batched runs of four or more,
  the edit panel, drafted messages as one card, tap rev fixes, searches done only once saved).
- **Branch `claude/evening`, its own pull request**: the evening batch. Agency recruiters are not
  held to the employer bar; a past call moves the contact on in the daily check-in; nobody at
  their limit is dated or a To do (every date through `state.put_next`); a sheet's foot never
  covers its last choice; phones kept in the app; a search's `--show N` cuts with every hard
  rule (language, agency, jobs already held, unscored); a resume can be drafted alone
  (`stage_picks.py --resume-only`) and the tracker names only documents made; reply guidance
  never offers a forbidden or hand-made old resume; short thank-yous pass the message checks and
  a note naming no place is never told it named the wrong one; saving leaves week-old chat work
  and side copies alone and clears old copies; a test that wrote over
  `profile.example/CLAUDE.md` and deleted it puts it back. The old chat merges it once its fast
  checks are green; if it is still open, it is the new chat's to merge.
- **Not yet done for this version**: `tools/rehearse_sync.py` has not been run on the evening
  batch; the page's changed browser tests ran in Chromium only (Safari's and Firefox's engines
  are not installed in a cloud chat, so their CI runs are the check); the search and
  resume-only tests were not shown to fail on the old code.

## Half-built, on its own branch

Notes 5 to 8 of the maintainer's nine of 4 November (a resume drafted in another chat never
reaching the page; work asked for in a chat never in Claude's work; two chats overwriting each
other's page updates during the hand-over; the check-in trusting a stored version number) were
being built by a helper that was stopped mid-way when the usage limit ran out. Its three commits
are on `claude/page-sync-wip`, based on the evening batch, not merged and not reviewed:

- "Only explicit job work or work begun in a chat draws the page; the stamp as read kept for the
  store's version" (notes 7 and 8)
- "A queued upload names every application it covers" (note 5)
- "The scheduled brief draws the day's news wherever it runs" (note 7, the brief's side)

It changed tools/app.py, app_listen.py, app_model.py, page_db.py, the app skill and three tests.
Its last words: the scheduled brief passes `--chat brief` and can run in a chat of its own in
older copies, so it is let draw the page like a job does, guarded by the newer-copy check. No
commit title is about note 6. Nothing on it has a build version or a fixture remade yet.

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
