# Notes for the next builder

Written at the release of 4.10.0 (2026-11-05) for the chat that builds the next version. Read
MAINTAINING.md first; this is background, never a list of work: a builder starts only from the
maintainer's notes (MAINTAINING.md, "How a builder works").

## Nothing to start from here

What 4.10.0 left is said below so a note that says "carry on" can be done without guessing.

## What 4.10.0 decided, to keep

- **Contacts is one page** (DESIGN.md "Contacts"): each person's latest draft on their card, drafted
  people first; "They replied" opens a box under the person; the card carries its own work line
  (workInline, the shared work-state words, Cancel); the pencil edits in place or asks Claude.
- **Jobs is one list**, "To apply" and "Applied": a drafted job is its draft's card; the engine
  queues a stale draft's remake and its file upload by itself (app.py self_fixes, remake_drafts,
  page_db.queue_files); the job's details are their own fold; More holds only the rare.
- **To do counts cards, not people**: one card an act and a person, "Messages to send (N)" counted
  once with Contacts (app_model.to_send), "N quick answers" one at a time, Done today, snooze through
  the engine (due.snooze), put off is never done.
- **One way to ask the person**: `needs` {question, about, work, answer {kind ...}} drawn by
  answerBox/answerControl; never "Say it in Chat" for an answer a control can take.
- **Buttons**: one row of pills a card, one filled next step a screen, the card's budget (one filled,
  two soft, the pencil, the trash, the gauge); More only for the rare; nothing the app can do itself
  is a button. The gauge sits beside every control that wakes Claude (`btn(..., {wakes: kind})`,
  gaugeWakers), its minutes from this copy's own finished work (page_db.work_times).
- **The word is trash, never bin** (tests/test_the_word_is_trash_never_bin.py).
- **Held skills go into the bullets** (bullet_rewording held/related/unplaced); a skill question is
  never answered no for the person (tools/skill_answers.py, one record a skill, the later answer
  winning); the skills line never repeats a skill.
- **Chats**: a job's chat reports back with send_message and is closed at once (tidy.py close); one
  page helper, "Job search page"; the tidy never archives a chat at work (status, recent use, a task
  bound to it, a branch not on GitHub); any chat draws the page except an old helper after a
  hand-over; a newer copy is judged by its commit (base_sha), not its clock.
- **Saving**: this chat's whole file is kept when it sweeps another chat's branch, an application
  moves as one unit, plain text elsewhere line-merges, the loser kept in `.other-chat-copies`;
  a file's age is read on its own clock (tools/file_clock.py); a folder is saved file by file when
  one file is refused.
- **Your rules** in Settings and the left-out list read by the rule that cut each row
  (tools/rules_view.py); "Still right?" only on old busy rules, at most one Brief line a month.
- **The release lenses** gained the tired person (MAINTAINING.md "Releasing"): a reviewer who did not
  build a screen reads it; a button for what the app could do itself is a bug.

## How 4.10.0 was built, and what to do differently

Notes 1 to 11 of 4 November and the maintainer's evening notes were built by helpers in worktrees,
merged into a local integration branch and landed in three pull requests (169, 170, 171) and the
release. What cost time:
- **Memory**: a full page-test run at `-n 8` beside four helpers ran the container out of memory and
  restarted it, stopping every helper (their commits survived; their transcripts let them resume).
  Keep page tests at `-n 2` to `-n 4` while helpers run.
- **Merging helpers**: squash each helper's branch onto the integration branch (`git merge --squash`)
  so old patches holding a word the leak scan flags never reach "every patch since master"; have
  each helper `git merge` the integration branch just before it reports, so its conflicts are its
  own. `build_versions.py` versions clash every time: renumber the later side and refresh the
  fingerprints with `python3 tools/build_versions.py fingerprints`; then add a version yourself when
  your own fix changes a method's files (a fingerprint refreshed without a version hides a change).
- **Two independent reviews** (engine, page) found 34 real bugs after every helper's tests were green;
  run them earlier next time, on the integration branch, before the last helpers finish.

## Not tested, or left

- **Firefox**: on master after 170, two layout tests failed only in Firefox's engine:
  tests/test_the_page_keeps_its_layout_promises.py::test_16_a_jobs_cards_facts_are_one_line_on_a_wide_screen
  (a job card's facts wrap to two or three lines) and
  tests/test_jobs_and_drafts_on_the_page_say_what_is_true.py::test_a_long_title_fills_its_line_before_it_wraps
  (0.67 of the line). Chromium and Safari pass. Firefox is not installed in a cloud chat; the
  Everywhere run on the release branch says whether the page fixes changed it.
- **A live chat** has not run the new find-and-draft-all job, the job chat's send_message report and
  close, or the form-questions box end to end; their tests play Claude's side.
- **The LinkedIn reads**: a page cannot hide Claude's browser pane or open a tab out of sight (the
  pane's own documentation); reads are out of sight only while the pane is closed or showing
  something else. The least intrusive way is built: one tab, never opened by the page itself.
- **Who "needs you"** means someone with a reply, a thank-you or a call to do; follow-ups are counted
  apart ("N follow-ups you could send"), as the 2026-11-04 rule pins.
- **Practise with Claude** sits under an interview card's More on To do (the card's budget);
  it stays a button on the prep's own page.
- **The floating Chat button** stays on wide screens: it opens the chat beside the current screen,
  which the menu's Chat does not.
- A pencil for a contact's name or employer was not built: the engine has no action to correct them.
