# Notes for the next builder

Written at the release of 4.11.0 (2026-11-06), for the chat that builds the next version. Read
MAINTAINING.md first; this is background, never a list of work: a builder starts only from the
maintainer's notes (MAINTAINING.md, "How a builder works").

## Nothing to start from here

What 4.11.0 left is said below so a note that says "carry on" can be done without guessing.

## What 4.11.0 decided, to keep

- **Marks never wake Claude.** `app_actions.MARKS` is the one list of taps that need no judgement
  (applied, not applying, I sent it, set aside, bring back, snooze and the rest). They are never
  rung, never make the page say Claude is not listening, and any view, wake, start or brief keeps
  pending marks first, in one batch, before reading. A tap that needs Claude still rings.
- **One "Stop Claude"**, faint red, from one helper (`stopClaude()`), wherever Claude's running or
  queued work can be stopped, inline or in the work list. A Cancel that only closes a box before
  anything is sent stays a Cancel. Suggestion boxes say Dismiss.
- **A card's answers stay in reach.** The latest exchange shows; "Earlier (N)" opens the rest in
  place; a hidden or two-day-old one leaves "Claude answered <day> · Show". Under an answer, the
  Copy and I sent it of any message it changed (two at most), found from message versions the
  question recorded and read live, so they follow the record wherever it goes.
- **An answer waits for its change.** An answer written with its work, newer than the page's newest
  view, says it is putting the change on the page first (five minutes at most): `heldAnswer`.
- **A sent tap counts for its own version.** `msgStatus` ignores a sent or skip tap whose `rev_seen`
  is not the message's rev; every message to one person shares one id.
- **The Brief on a laptop never scrolls.** It fills the window, panels lined up to the foot, when it
  already fills `FILL_SHARE` (75%) of it; a sparser one keeps each row to what it holds. Lists grow
  into spare room and give way, one item at a time, when the window is short.
- **Applied roles leave To apply at once**; Applied opens on "Today or yesterday" as a chip with
  Clear all, only when there are some.
- **One open role per employer across all of Jobs** (`run_round.extra_roles`), the rest set aside
  with Bring back, never saved as a ruling. An employer's lift is counted before the top-of-scale
  taper (`fit.fit(lifts=...)`).
- **InMail is chosen in code** (`tools/network/inmail_pick.py`): a recruiter or hiring leader at a
  target employer whom a request reaches badly, at most two a run, never the last credit, never on
  a free plan; the card says why and what it spends, with a switch to a connection note and back. A
  weekly To do question asks the balance, with LinkedIn's own steps (`claude_surfaces`
  `linkedin-inmail-credits`).
- **A conversation needs a word from them, narrowly.** A stored in_conversation whose only logged
  rows are our own connection requests reads as the log shows (awaiting_reply, or
  connected_no_reply where Connections.csv has them), unless the row holds a call day or the
  person set it by hand; reconcile reports it as `no_word_from_them`. call_booked and any thread
  with a message we sent keep their status: the rehearsal on the maintainer's own tests showed a
  wider rule nudging people with a call booked and dropping referral holds.
- **A referral in progress keeps the role on the list**, marked not to apply cold
  (`throttle.employer_stops`, `referral_note`), rather than dropping it.
- **Dropped and closed people are never read by the page** (app_model filters the reading queue
  by the contact's stored status).
- **One person is one record.** `state.py same-person` closes a duplicate and carries its fields
  over; the export matches an existing person by a shared message or a surname in the record; the
  `one-record` profile upgrade joins certain duplicates and fills first-name rows from the
  person's own Connections.csv, everything uncertain left to reconcile.
- **Own tests an update broke come first.** Every entry point prints the bring-them-in-line step
  until they pass; land.py says so and keeps the work.
- **The page's rings are cleared every day** by the daily tidy (`app_setup.doorbells_due`), not once.

## Built from notes but not finished

- **"No more from this industry"** in a job's trash: not built, because no job row carries an
  industry. It needs a sector on each job row (app_model), a setting such as
  `BAR_SECTORS_DECLINED` with a writer and Undo in app_actions like the employer one, and bar.py
  reading it.
- **A stray "Saved." line** beside a running work line under "Resume 1 page" was reported once and
  could not be reproduced.
- **InMail's window check** still happens in a chat (`reading.py extractor --message-check`) or on
  the person's word; the page's own profile read does not do it.
- **Marks and landing:** land.py never reads the page, so it does not keep pending marks; the
  brief, wake, view and start all do.
- **Own tests in a fresh clone** are unknown until the first landing records them.
- **A save refused twice** is kept in its view folder, but nothing carries it into a later folder.
- **Duplicates the upgrade leaves:** different employers (a job move is not certain), the same
  words logged in opposite directions, and anything a name alone suggests stay for reconcile.

## Not tested at this release

- The Platforms and Everywhere runs started on the last batch's pull request: Mac found one test
  that committed in a clone with no git identity (fixed in the release). Their Windows, Safari,
  Firefox, language and moved-clock results were still running when the release merged: read
  them on that run before trusting those platforms.
- The rehearsal against the maintainer's copy (tools/try_personal_tests.py) left one of their own
  tests to bring in line: the referral hold that now keeps the role (named in the CHANGELOG).
- No independent reviewer read the whole `[Unreleased]` diff; each batch was reviewed through its
  own tests.

## Seen in the README pictures, not fixed

- The week labels under Your progress run together in the four-column Brief ("28 Sep" touching
  "5 Oct").
- The Progress screen's "Each week" panel draws as an empty box at 1600 by 1000, so Progress is
  left out of the tour.
- The floating Chat button covers the last card's tag on Contacts at 1600 by 1000.
- In the tour's 1600 by 1000 Brief frame the sample falls just under the fill share, so its rows
  keep to their content with space under them.
