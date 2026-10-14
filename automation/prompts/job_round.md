# Job round (schedule: `profile/routines.json`)

Follow CLAUDE.md "Job Search Behaviour": score and rank, stop at the shortlist, draft
nothing until the candidate picks. `_common.md` first.

1. No LaTeX is needed for this step. Pick `rN` as the next round number after the highest
   file in `documents/rounds/`. Run, with `$SCRATCH` a scratch directory outside the repo:
   `python3 tools/run_round.py --out "$SCRATCH/rN" --jobage 7 --expand`
   Read the exit code: 0 met the yield target, 2 missed it (report what the MISSED message
   says), 1 a stage broke (diagnose it and say so; never paper over it).
2. From the shortlist, drop anything failing the candidate's bar (`tools/bar.py`, and the
   target sectors and exclusions in `profile/CLAUDE.md`), any employer with a live interview
   process or referral hold, anything already drafted or applied to in
   `job_search_tracker.csv`, and anything posted more than 7 days ago. One role per
   employer. Keep warm-route warnings ("DO NOT APPLY COLD") visible next to the role.
3. Commit `documents/rounds/<rN>.json` and `job_scraper/seen_jobs.json` (`git add -f` for
   the latter) and land them per `_common.md`.
4. The message:

```
Round <rN>: <n> at 60+, <n> at 75+
<the top 8 after step 2, numbered: score | company | role | posted | one-line reason | apply link>
Reply in the "Job search ops" session with the numbers to draft (e.g. draft 1,3,5), and say if you have already applied to any.
```

5. **When the candidate replies with picks** (here, in this session): record any "already applied"
   answers in the tracker, then `./tools/setup_env.sh` (LaTeX this time), stage the picks
   with `tools/stage_picks.py`, run the saved `draft-applications` workflow, assemble, render
   with `tools/fit_to_page.py`, run `tools/check_claims.py` and `tools/verify_batch.sh` until
   clean, write outreach notes and kept drafts with `tools/outreach.py`, record the tracker
   rows with `tools/record_drafts.py`, and land everything per `_common.md` and CLAUDE.md's
   persistence rule. Deliver a short "drafted N, all verified, here is what to check" message
   the same way.
