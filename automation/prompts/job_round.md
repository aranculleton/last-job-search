# Job round (optional; schedule: `profile/routines.json`)

Off unless a person asks for a scheduled search: the twice-weekly brief does not search,
and "find me jobs" in any chat runs one. Follow CLAUDE.md "Job Search Behaviour": score and
rank, stop at the shortlist, draft nothing until the candidate picks. `_common.md` first.

1. No LaTeX is needed for this step. Pick `rN` as the next round number after the highest
   file in `documents/rounds/`. `$SCRATCH` is a scratch directory outside the repo.

   **The app's updates and the profile's upgrades came first**, in `_common.md` step 2
   (`python3 tools/sync_app.py --if-stale --on "<the model this run is on>"`, then `/upgrade 20`): a job board an upgrade
   builds is searched this round.

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
2. Judge every employer the bar does not know yet, once each (`python3 tools/bar.py
   unjudged`, then `bar.py judge "<employer>" <verdict> "<why>"`): a "none" that says "not on
   your employer lists yet" has not failed the bar. Then, from the shortlist, drop anything
   failing the candidate's bar (`tools/bar.py`, and the target sectors and exclusions in
   `profile/CLAUDE.md`), any employer with a live interview
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
   with `tools/stage_picks.py`. When it prints questions (a pick held for a fixed-term
   contract, pay for another place or an application already in, which role to draft when
   two share an employer, and skills a posting names that the profile does not hold), ask
   them, all in one message and word for word, and wait: record each answer with
   `stage_picks.py consent` (`--draft` or `--skip` for a held pick). Then run the saved `draft-applications` workflow, assemble, render
   with `tools/fit_to_page.py`, run `tools/check_claims.py` and `tools/verify_batch.sh` until
   clean, write outreach notes and kept drafts with `tools/outreach.py`, record the tracker
   rows with `tools/record_drafts.py`, and land everything per `_common.md` and CLAUDE.md's
   persistence rule. Deliver a short "drafted N, all verified, here is what to check" message
   the same way.
