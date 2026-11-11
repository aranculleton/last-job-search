# Notes for the next builder

Written at the release of 4.14.0 (2026-11-10), for the chat that builds the next version. Read
MAINTAINING.md first; this is background, never a list of work: a builder starts only from the
maintainer's notes (MAINTAINING.md, "How a builder works").

## What 4.14.0 decided, to keep

- **LinkedIn is read on the person's computer, started from the cloud.** A cloud chat finds an
  active bridge environment (`list_environments`, kind `bridge`) and starts a chat there with
  `create_session` (`tools/computer.py route`); its results come back through the page and git,
  never `send_message`, which asks the person every time. Work that needs a LinkedIn read is
  `to: computer` once the computer is known ready (`computer.reads_there`), and a cloud chat may
  not claim, finish or fail it (`page_db.computer_only`). A route given no list of computers
  asks for one first, never judging the computer off from its last check-in alone.
- **Auto is inherited, not granted.** A chat starts in Auto only when the chat starting it is in
  Auto ("requires the parent session to be in auto mode"). Every `create_session` the app builds
  asks for it (`app_listen.SESSION_MODE`), and on that refusal the person is asked once to switch
  the right chat (`MODE_REFUSED`). A mode menu showing Auto is not proof; the refusal is.
- **Computer approval and scheduled tasks never share a chat.** `confirm_repository_trust` ties
  the approving chat to the person's devices, and a task bound to it fails. The morning brief
  fires into a chat of its own made with the copy as `source_url` ("Job search: morning brief");
  the daily check remakes it when missing, archived or trusted (`tidy.plan`), and existing copies
  move by the `brief-own-chat` upgrade. A fresh chat a run cannot work: it has no copy. A manual
  `fire_trigger` of a task bound to a chat starts a fresh chat, so it cannot test the bound run.
- **No reminders and no hourly task.** A helper sets no `send_later` (a trusted helper cannot
  run one); the computer has no scheduled task (it cost a run an hour for nothing).
- **A chat on the computer:** draws the page first, then saves in the background; its save
  ends at its push and the cloud's landing merges it (`land.on_computer`); it says nothing about
  saving. It removes a memory note that contradicts the person's settings. It cannot remove
  itself from the desktop sidebar, and archiving from the cloud does not either; the job's card
  says up front that it runs in a chat there, which the person can delete.
- **Page versions:** every read records the page's own versions: the PostToolUse hook on
  ArtifactData keeps them, and only where it did not (a chat started before the hook was
  added) does `wake` ask for `app.py versions` once the read is in. A `view` while the page's own code is behind says to republish.
- **People runs:** an employer frees after one follow-up wait from the last contact; an
  unaccepted request after 21 days; a thread with no answer in 90 days goes cold by itself
  (`threads-gone-cold`). Recruiters and founders before peers, by the person's reply rates; a
  close only counts when the person made it. Likely employers are searched first and an empty
  one rests 30 days (`candidates.py order`).
- **Documents set with no kerning**, so a text layer reads AWS whole; the final check flags any
  word split by a space. A resume made for a contact keeps the person's own file name.
- **Saves that touch only the person's files** land with a data check, no code checks.
- **Every Linux CI job names ubuntu-24.04**: ubuntu-latest became 26.04, with no Python 3.9 and
  no Playwright browsers.
- **Pre-approved tools and the read hook are the maintainer's edits.** Claude's safety check
  refuses an agent changing `.claude/settings.json`, `tools/security_guards.py`'s allowlists or
  a skill's `allowed-tools`, even when asked. The maintainer made those edits on GitHub; a
  skill's `allowed-tools` must stay on one line (`test_a_skills_allowed_tools_is_one_line`).

## Not tested at this release

- **Windows and Linux computers.** The computer side was used for real on a Mac only. Linux
  has no desktop app, so it gets the paste fallback.
- **The cloud reading LinkedIn itself** (`request_computer_folder`, a lent browser) was not
  available on the maintainer's account, so those routes are untried.
- **Firefox:** one page test (the work card's progress at 150 s into a 300 s stage) failed once
  in Firefox and passed when run again by hand on the branch: intermittent, Firefox only.
- **Safari:** `test_the_brief_uses_its_room.py::test_the_jobs_panel_lists_more_where_it_has_room`
  shows 4 jobs where more fit, in Safari only, and fails the same way on the master before this
  release (run by hand there on 2026-11-10), so this release did not cause it. Safari and
  Firefox had not run for days before (ubuntu 26.04 broke their install).
- **Windows:** the two `test_a_job_chats_lost_work_is_asked_for_once_then_said.py` failures
  in the Git Bash leg were already on master's weekly run of 2026-11-09.
- **The rehearsal** passed on the maintainer's copy, apart from two of their own tests that
  still expect older app behaviour (a referral removing a job; the old resume name order).
  Their copy's own-tests step brings them in line.
