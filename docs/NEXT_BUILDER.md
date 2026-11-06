# Notes for the next builder

Written at the release of 4.12.0 (2026-11-06), for the chat that builds the next version. Read
MAINTAINING.md first; this is background, never a list of work: a builder starts only from the
maintainer's notes (MAINTAINING.md, "How a builder works").

## Nothing to start from here

What 4.12.0 left is said below so a note that says "carry on" can be done without guessing.

## What 4.12.0 decided, to keep

- **Settings folds many of one kind into one row.** Employers turned down are "Employers you've
  turned down (N)" with what they left out, each name with its own small trash. Learned rules
  have one home, "What you have taught it", grouped by area, a rule a line with its day; Your
  rules links to it. Long sections show their first few with Show all (`shortList`). Advanced
  holds only what can slow things or use the Claude allowance (where Claude works, suggestions);
  Look holds light or dark, text size and keyboard shortcuts; This device holds Check this device.
- **A search setting changed starts no search.** Its row says "Used from your next search" with
  Find jobs beside it; the Tweak panel's own Apply still searches. Writing a setting keeps the
  person's comments (`profile_set._in_place`, a dict changed one entry at a time).
- **Each job site is its own item** (`site-<name>`), with a plain name and a note from
  `portals.SITES`; a site needing a key or a paid plan says so and opens on its steps.
- **Rules the app now does by itself are retired once** (`learned.BUILT_IN`, `learned.py
  built-in`, the `built-in-rules` upgrade). A complaint about the app is never a rule
  (`learned.ABOUT_APP`, which needs an app subject; when unsure, it is the person's rule).
- **Changes made for you are plain words, each once** (`app_setup.plain_change`): never a file
  or test name.
- **The brief keeps a picked time to the minute**; only the app's default sits before the hour,
  and the page shows the time it really comes (`routines.real_time`), the scheduler's late start
  included.
- **Documents are named person, employer, document** for new files; old files keep their names
  and every reader finds both orders (`docpaths`). The File names setting renames only the copy
  that leaves (downloads and the chat's copy), never the kept file.
- **Saves queue.** One lock taken in one step with a token, handed to the detached run; a save
  asked meanwhile is taken by the running one, or a new one is started for it, whatever the
  first one's result; a check has a 30 minute deadline. In a person's copy the quick check never
  runs the app's own tests.
- **An update never blocks a save on the person's own tests it broke.** Those are set aside for
  the save and brought in line by the `own-tests` background improvement, queued at once.
- **The maintainer's app watch runs in the background**; its findings are said by the next check.
- **`run_round.py --employers`** limits a search to named employers, aimed at them from the scrape on.
- **After an update, an open chat re-reads only the skills it had read.**

## Built from notes but not finished

- **`app.app_bugs`** (the maintainer's copy only) is in the model but not drawn on the page.
- **The cost audit's next safe saving**: a `--table` on the shortlist step so the chat does not
  build the table itself (about 10k tokens a search). Not done: it changes how a search is shown.
  Also seen and left: re-fetching postings already surfaced between rounds (`hydrate.py`,
  `throttle.py`), and `/rank --all` fanning out agents that could be the code scorer. The page
  helper, the hook holds, land.py's pacing and the scrape's pacing were judged not to touch.
- **The person's own tests still run in the foreground of the day's check after an update**
  (timeout 300 s), because they decide what a save sets aside; on a big profile that is the
  slowest part of that check.
- **"No more from this industry"** in a job's trash (from 4.11) is still not built.

## Not tested at this release

- **Safari** (page everywhere) found five, none in what 4.12 changed: the laptop Brief's fit at
  1000x560, 1280x720 and 1440x900, the Chat's latest on a phone, and the 4.11 review's latest
  button. Its 4.11 run never ran, so these are older; reproduce with
  `EVERYWHERE_TESTS="<file>" tools/everywhere.sh page safari`.
- **Firefox** found the same six as at 4.11: a Jobs card's facts on one line (wide), the Brief
  scrolling at 1000x560 and 1280x720, the privacy line as one paragraph, and panels lined up.
  The container has no Firefox; text drawn wider than Chromium's is the first suspect.
- **Mac, Windows, German, far time zones and the moved clock** on the final push were still
  running when the release merged: read them on the 4.12.0 pull request's runs.
- **The rehearsal** on the maintainer's copy passed for a cloud and a computer chat; one of their
  own tests (a recorded draft's resume path) now differs by design (the new name order) and is
  brought in line by the background step. Named in the CHANGELOG.
- **The suite outgrew ten minutes on a slow runner** at this release: the Python 3.9 leg was
  stopped at 96% and 98% by its limit, so the release raised both test jobs' limits to 15
  minutes (`ci.yml`). The suite grew by about 150 tests in 4.12; watch the times.
- **README pictures** were not remade: 4.12 changed Settings, not the four pictured screens.
