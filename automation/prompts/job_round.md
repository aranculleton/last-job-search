# Job round (schedule: `profile/routines.json`)

Follow CLAUDE.md "Job Search Behaviour": score and rank, stop at the shortlist, draft
nothing until the candidate picks. `_common.md` first.

1. No LaTeX is needed for this step. Pick `rN` as the next round number after the highest
   file in `documents/rounds/`. `$SCRATCH` is a scratch directory outside the repo.

   **The app's updates and the profile's upgrades, first.** `python3 tools/sync_app.py`
   (exit 1 or 2: one line in the message, carry on). If it lists upgrades Claude applies
   itself, run `/upgrade 20` now, before the round: a job board it builds is searched this
   round. Never put a question to the person mid-run; the "need you" ones go in the message.

   **Job alerts, if the person reads theirs here.** `python3 tools/job_alerts.py --query --days 8`
   prints a Gmail search, or exits 1 when they have not asked for alerts to be read: then
   skip to the run. With a query and the Gmail tools in this chat, `search_threads` with it
   (paginate), `get_thread` with `messageFormat: FULL_CONTENT` for each, and write only the
   messages in each thread from the sender the query names, as `{"id", "date", "body"}`,
   into a JSON list at `$SCRATCH/alerts_in.json`. Read nothing else in the inbox. Then
   `python3 tools/job_alerts.py "$SCRATCH/alerts_in.json" --out "$SCRATCH/alerts.json"`.
   Without the Gmail tools here, say so in one line of the message and run without.

   Run: `python3 tools/run_round.py --out "$SCRATCH/rN" --jobage 7 --expand`, adding
   `--alerts "$SCRATCH/alerts.json"` when step 1 wrote it.
   Read the exit code: 0 met the yield target, 2 missed it (report what the MISSED message
   says), 1 a stage broke (diagnose it and say so; never paper over it). A portal the
   health probe reports DOWN goes in the message's first line: a quiet board is not a
   thin market.
2. From the shortlist, drop anything failing the candidate's bar (`tools/bar.py`, and the
   target sectors and exclusions in `profile/CLAUDE.md`), any employer with a live interview
   process or referral hold, anything already drafted or applied to in
   `job_search_tracker.csv`, and anything posted more than 7 days ago. One role per
   employer. Keep warm-route warnings ("DO NOT APPLY COLD") visible next to the role.
3. Commit `documents/rounds/<rN>.json` and `job_scraper/seen_jobs.json` (`git add -f` for
   the latter) and land them per `_common.md`.
4. The message, written to be read on a phone: one role per block, the role and employer
   first, the details on one short line, the link on its own line (a link inside a sentence
   breaks on a small screen). Dates as the profile writes them, pay only where a band is
   stated, and a warm-route or pending-outreach note on its own line under the role it
   belongs to. A failed step goes in one line above everything, and only when a step failed.

```
Shortlist <rN>: <n> roles at 60+, <n> at 75+

1. <Role>, <Employer> (<score>)
   <Location> · posted <date> · <one reason: the stated band, or the strongest match>
   <apply link>

2. ...

Reply in <the chat to reply in, per _common.md> with the numbers to draft, for example
"draft 1, 3", and say if you have already applied to any.
```

   After the list: one line per upgrade `/upgrade` applied (what changed, `git revert <sha>`
   to undo), and at most three questions from what needs the person, each on its own line
   (the round's "Profile upgrades" line names them).

   When the round missed its yield target, add one line under the list: the counts, and
   the boards the MISSED message names as researched with no portal yet, with "say 'build
   <board>' and I will add it" (that is `/add-portal`, run when they ask, never here).

5. **When the candidate replies with picks** (in this chat): record any "already applied"
   answers in the tracker, then `./tools/setup_env.sh` (LaTeX this time), stage the picks
   with `tools/stage_picks.py`, run the saved `draft-applications` workflow, assemble, render
   with `tools/fit_to_page.py`, run `tools/check_claims.py` and `tools/verify_batch.sh` until
   clean, write outreach notes and kept drafts with `tools/outreach.py`, record the tracker
   rows with `tools/record_drafts.py`, and land everything per `_common.md` and CLAUDE.md's
   persistence rule. Deliver a short "drafted N, all verified, here is what to check" message
   the same way.
