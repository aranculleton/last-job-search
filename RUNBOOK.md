# Runbook: one round, portals to sent applications

Every step below is a command. Nothing spends model tokens until step 2, and step 2
spends them only on writing.

## 0. Fresh container

```bash
apt-get install -y --no-install-recommends texlive-luatex texlive-latex-extra texlive-xetex \
  texlive-fonts-recommended poppler-utils   # icon fonts are vendored in texmf/, see its README
pip3 install --upgrade cffi && pip3 install -r requirements.txt
python3 -m pytest tests -q          # over 1,200 tests; all green before anything else
./tools/ci_local.sh                 # or this: every check CI runs, under two minutes, no Actions minutes
```

Full detail, including why `cffi` comes first, is in [SETUP.md](SETUP.md).

## 1. Find jobs

```bash
python3 tools/run_round.py --out "$SCRATCH/r1" --jobage 7
```

**Point `--out` at the scratchpad, not the repo.** A round is about 55MB of raw scraped
posting text across ten stage files. It is scratch, not a deliverable, and it is thick
with third-party content. `.gitignore` is guard-enforced and is not edited, so where the
round lands is decided by where you point `--out`.

The round handles the keeping and the deleting itself. It writes the top 60 of the
shortlist, without the posting bodies, to `documents/rounds/<round>.json` at about 30KB,
then deletes the stage files and prints how much it freed. It keeps `06_shortlist.json`, cut
to the same 60 with their bodies, because drafting is staged from it; in a later session,
when `rounds/` is gone, `stage_picks.py` reads `documents/rounds/` and fetches the bodies again. That summary file is the one
to commit, and it takes a plain `git add`: it sits outside `rounds/` deliberately,
because a keeper inside an ignored tree would need a `!` negation and
`tools/security_guards.py` rejects negations outside its reviewed allowlist.

Stages, in order: scrape, prefilter, hydrate, screen, opportunity, fit, throttle. The
shortlist is ranked by fit x opportunity with a fit floor of 65; `tools/throttle.py` has
applied the company throttle and the one-role-per-employer rule and written every skip
with its reason.

The `seen_jobs.json` dedupe runs at **prefilter**, not at the throttle, so a posting this
search already ruled out never reaches `hydrate` and never costs an HTTP call. It is the
throttle's own `ruled_out()` either way, imported rather than copied, so the shortlist is
identical; a large share of everything reaching hydrate used to be in that state. A ruling
made under the person's screening rules lapses by itself when those rules change, and one
in their own words holds until `tools/exclude.py lift` takes it off; a scoring setting
lifts nothing. `--no-seen-read` skips the check at prefilter only: everything ruled out is
fetched and scored again in the stage files, and the throttle still keeps it off the
shortlist.

**Read the exit code.** 0 means the yield target was met, 2 means it was missed, 1 means
a stage actually broke. A thin market and a broken pipeline are different answers.

**`--jobage` is the window in days**, 14 by default, and nothing older is ranked; the
scheduled round uses 7. `--expand` widens it (below). If a portal is blocked by the
session's egress policy the log says `connect_rejected`; that is environment policy, not a
bug. To re-run every free stage on a scrape that already succeeded, without touching the
portals, the first run must have kept its stage files (`--keep-intermediates`), because a
normal round deletes `00_scrape/`:

```bash
python3 tools/run_round.py --out "$SCRATCH/r1" --keep-intermediates
python3 tools/run_round.py --out "$SCRATCH/r1b" --from-scraped "$SCRATCH/r1/00_scrape/kept.json"
```

### When the round misses

It exits 2 and keeps three files it otherwise deletes, with the posting bodies stripped:

| File | Answers |
|---|---|
| `01_dropped.json` | what the age and location gates removed, plus anything already ruled out in `seen_jobs.json` |
| `03_screened_all.json` | what the stated-fact knockouts removed, with the quote |
| `06_skipped.json` | what the company throttle and the one-role-per-employer rule removed |

Those are the three places a posting can vanish. `--expand` re-runs wider automatically,
up to three rounds in all, each with more pages per search and a longer window: from the
defaults, 10 pages and 21 days, then 30 pages and 42 days. The other widenings (title
variants, places, sectors, named employers) are printed as what to try next, not run. If it
still misses, say so with the count, what was tried and the likely blocker. **Never pad a thin run with sub-60 postings, and never relax a gate or
the location filter to hit the number.**

### Then stop

Present the shortlist, highest first, with scores visible, and **ask which to take
forward and whether any have already been applied to directly.** The tracker only knows
what went through here. Do not draft anything unprompted.

## 2. Draft

**The fast path is three steps around one workflow.** Stage the picks, run the saved
`draft-applications` workflow, assemble:

```bash
python3 tools/stage_picks.py stage "$SCRATCH/r1" 3 7 "Acme::Demand Planning"
# Workflow draft-applications, args {today, round_dir: "$SCRATCH/r1", picks: <picks.json>}
python3 tools/stage_picks.py assemble "$SCRATCH/r1"          # -> drafts.json
```

The workflow researches each employer on sonnet and drafts and audits on the strongest
model, per `11-cost-model.md`. **Its concurrency is CPUs minus two**, which on a 4-CPU
container is two agents at a time, so thirty agent calls can take over an hour. For
a batch of more than three, the same three stages run faster as parallel background agents
(one drafter per posting, then one auditor per draft); the briefs they are given
are the prompts inside the workflow file.

`stage` picks each filename and never reuses one another application was sent under. The
rest of this section is what each draft object must hold, whichever way it is written.

For each chosen posting, write one draft object; the fields are in
`tools/render_application.py` `build()`. In short: `abbr`, `company`, `role`, `summary`
(40 to 48 words, identity first), `tools` (the stack the posting names that the profile
supports), `p1` / `p2` / `lead` / `p4` (200 to 250 body words between them), `cl_bullets`,
and `posting` (the full text).

**`cl_bullets` is a list of dicts**, `{"label": ..., "text": ...}`, not a list of pairs.
`build()` turns them into the `(label, text)` tuples the template wants, so the tuple
form is what comes *out* and a tuple going *in* fails with `tuple indices must be
integers`, several frames from anything that names the field.

Do **not** write `jobs`. The allocator does that, scoring every bullet in the library
against this posting on tenure, recency and relevance. Hand-picking from a fixed set is
what produces a resume that looks the same for a pricing role and a model-governance
role.

`concession` is a drafter's note for the record and is **never rendered**; if a
concession is warranted at all, the sentence itself lives in `p2`. Every company fact in
`p2` is verified from the company's own site, located independently, never from a URL
inside the posting.

Save as `$SCRATCH/r1/drafts.json` (a list), with the shortlist rows as
`$SCRATCH/r1/apps_in.json`.

## 3. Render, fit, verify

```bash
python3 tools/fit_to_page.py "$SCRATCH/r1/drafts.json"
python3 tools/check_claims.py cv/*_Resume_*.tex cv/*_CV_*.tex cover_letters/*_Cover_Letter_*.tex
tools/verify_batch.sh "$SCRATCH/r1/drafts.json"
python3 tools/outreach.py "$SCRATCH/r1/drafts.json" "$SCRATCH/r1/apps_in.json"
```

`fit_to_page` allocates bullets, renders, compiles, trims the weakest bullet for *this*
posting until one page, then grows back the strongest absent one that still fits.

`check_claims` must report **0 error-level findings**. `audit_letters`, which
`verify_batch.sh` runs, must report every letter clean. `verify_batch.sh` exits non-zero
on any finding and checks pages, chronology, section order, bullets per employer, contact
details as literal text, duplicated phrasing, em and en dashes, the document nouns the profile
bans (`person.json` `documents.banned_nouns`), and the ATS text layer. The resume's filename
noun is the profile's own word (`documents.noun`), so a profile that says "CV" writes
`cv/<Prefix>_CV_<ABBR>`; the globs here cover both.

`outreach` writes `documents/applications/<slug>/job_posting.md` and `outreach.md`. The
outreach note is a sub-80-word message to the hiring manager or recruiter built from the
letter's verified company fact. Sending it is the user's call; every application gets one.

Then read every resume and letter in the batch by eye. Not the .tex, the PDF. LaTeX page-break decisions are not
predictable from source, which is the whole reason this step exists.

## 4. Record and persist

`python3 tools/record_drafts.py "$SCRATCH/r1/drafts.json" "$SCRATCH/r1/apps_in.json" --round r1`
adds a row per application at `status=drafted` (fit in `fit_rating`, never priority) and
writes each `screening_answers.md`. Then:

```bash
git add -f job_search_tracker.csv documents/applications/ job_scraper/seen_jobs.json
git add -f cv/*_Resume_*.tex cv/*_Resume_*.pdf cv/*_CV_*.tex cv/*_CV_*.pdf
git add -f cover_letters/*_Cover_Letter_*.tex cover_letters/*_Cover_Letter_*.pdf
git add documents/rounds/
git commit && git push
```

Never `*.aux *.log *.out *.fls *.fdb_latexmk *.synctex.gz cv/*.txt`. Never edit
`.gitignore`. The full list of what persists is in CLAUDE.md under the persistence rule.

Then get it onto master. A branch left behind at the end of a session is work the next
session cannot see and will duplicate.

## 5. After the user applies

- `/outcome`, or edit the tracker directly: `status=applied`.
- Send the outreach note the same day: `documents/applications/<slug>/outreach.md`.
- `python3 tools/open_actions.py --due` each morning: only what is due today or overdue,
  people and applications, with the counts on the first line. The full
  `python3 tools/open_actions.py` shows the same follow-ups beside everything else owed at
  that employer, so a nudge and a reply are not two separate checks, and
  `python3 tools/followups.py` prints the nudges alone.
- A first follow-up is due 7 days after applying and a second 7 days after the first
  actually went. **After sending one, append `followed up YYYY-MM-DD` to the row's notes**,
  the form `/outcome` Step 2b writes: the second is timed from that date, and without it
  the next run offers the first again. A week after the second, or 45 days after applying
  with no reply, the chase stops and says so once.
- A follow-up with nobody on file is listed without a draft. Put the recruiter or hiring
  manager in the row's `contact_person` column and the draft is addressed to them.
- `DO NOT CHASE` in a row's notes holds its follow-ups, with the reason shown; `until
  YYYY-MM-DD` in the same note, or a later note saying `chase again`, lifts it. An
  interview or offer at the same employer, or a referral in flight there, holds them too.
- `/interview <company>` when one lands. Not `/prep`, which is for a networking call.

## What "done" looks like for a round

At least 5 postings scoring 60+, of which 2 at 75+, all inside the round's age window. Every drafted
application has two verified one-page PDFs, a persisted posting, an outreach note, a
tracker row, and 0 claim errors. All of it committed, and on master.

## Tools run directly, not through a slash command

| Command | What it does |
|---|---|
| `python3 tools/run_round.py --out rounds/rN [--expand]` | The whole free pipeline, portals to ranked shortlist. It checks the yield target and prints MET or MISSED with the counts. **Exit 0 met, exit 2 missed, exit 1 a stage actually broke** - a thin market and a broken pipeline are different answers. `--expand` re-runs wider up to the 3 rounds the rule allows. It **prunes itself**: `rounds/` is gitignored and its ~55MB of stage files are deleted, except `06_shortlist.json` cut to the top 60 with their bodies, which is what drafting is staged from; the same 60 rows, minus the posting bodies, are written to `documents/rounds/<round>.json` and **are** committed. `--keep-intermediates` retains the stage files for debugging a round that went wrong, and a round that **missed** keeps `01_dropped.json`, `03_screened_all.json` and `06_skipped.json` automatically, with the posting bodies stripped, because those are the three files the MISSED message tells you to read. |
| `python3 tools/job_alerts.py <messages.json> --out <alerts.json>` | The person's LinkedIn job alerts, read by the session from Gmail only when `profile/search.py` `JOB_ALERT_QUERY` asks for it (`--query` prints the search). Takes the job ids alone and fills each posting from LinkedIn's own page; `run_round.py --alerts <alerts.json>` adds them to the round before the free filters. |
| `python3 tools/network/prep.py --all` | Rewrites every contact's prep document. Without it a fix to `prep.py` reaches whichever one somebody runs next and no others. |
| `python3 tools/network/profile_facts.py` | The candidate half of a prep doc, read out of `01-candidate-profile.md` and `tools/bridges.py`. `prep.py` calls it automatically; run it directly to see what it extracts. |
| `python3 tools/open_actions.py` | Everything owed, employers first, derived from the three state files: live applications, contacts owed a reply, and **follow-ups due** on applications that have gone quiet. `--company <name>` for one employer. **`--due`** prints only what is due today or overdue, both halves, most urgent first, with the counts on line one and the first five lines written to stand alone: it is what the daily routine pastes into a push notification. A contact whose `next_action` opens on HOLD or FREEZE is not due until the date after "until" arrives. This is the one view; `tools/followups.py` is the nudge half of it and still runs on its own when that is all you want. |
| `python3 tools/what_works.py brief <messages\|documents\|search>` | What has worked, counted from the state files with no model call: reply rates and the messages that drew replies, the applications that reached an interview with the resume and letter they used, and the interview rate by fit band and route. A difference is reported only when the groups are big enough and the gap is unlikely to be chance. `event --contact <id>` and `event --company <name>` are the one-line audit when a result arrives. |
| `python3 tools/followups.py` | The application nudges alone. The first is due 7 days after applying, the second 7 days after the first **actually went**, read from `followed up YYYY-MM-DD` in the row's notes (the form `/outcome` Step 2b writes), never from the application's age. Held, with the reason printed, while an interview or offer runs at that employer, a referral is in flight there, or the row's notes say `DO NOT CHASE` (`until <date>` in that note, or a later `chase again`, lifts it). A later row for the same role closes the earlier one. It names who the nudge goes to, from the row's `contact_person`, the application's `outreach.md`, or a contact there who has replied, and otherwise says nobody is on file and drafts nothing. It stops a week after the second follow-up, or at the throttle's 45 days of silence, and says so once. A separate clock from the networking nudge below, deliberately. |
| `python3 tools/stage_picks.py stage <round_dir> <pick>...` | The step between a shortlist and a draft. A pick is a shortlist rank or `Company::title words`. In a later session, when `rounds/` is gone, it reads `documents/rounds/<round>.json` instead and fetches each pick's body from its board, or reads `<round_dir>/postings/<slug>.txt` when the board will not give it. `single <dir> --company --role --posting-file` stages one posting from no round, which is how `/apply` enters the same pipeline. Writes each posting fenced by `tools/untrusted.py`, `picks.json` (the `draft-applications` workflow's args) and `apps_in.json`, and picks each filename: **a name another application was sent under is never reused**, so a second role at an employer gets a role token (`Acme_DemandPlanning`). `assemble <round_dir>` turns the audited drafts into `drafts.json` and names any pick with no draft. |
| `tools/verify_batch.sh <drafts.json>` | Every rendered application: pages, chronology, section layout, text layer, claims, letters. Exits non-zero on any finding. |
| `python3 tools/record_drafts.py <drafts.json> <apps_in.json> --round rN` | The tracker rows for a rendered batch, by `/apply` Step 6b's rules, plus `screening_answers.md` for each. It writes **fit** in `fit_rating`, never the shortlist's priority, which can exceed 100 on a 0-100 column. |
| `python3 tools/bar.py "<company>"` | The candidate's bar in code: pay, prestige, signal, or none, with the reason. The throttle applies it every round: the sectors and employers `profile/search.py` excludes are skipped with the reason recorded, every other row carries its verdict into the shortlist and `documents/rounds/`, and "none" is a flag, never a cut. |
| `python3 tools/network/reading.py` | What was read about one person before writing to them: `read <contact_id> <file\|->` takes their profile page (pasted, read in the person's own browser, LinkedIn's Save to PDF, or transcribed screenshots), `add` one public finding (a talk, an article, a post), `show` what a note can rest on, best first, and `queue` the waiting drafts with no fresh reading. `verdict <contact_id>` is KEEP or SKIP after a read, `route --tools <...>` says how this session reads profiles and the one line to tell the person, `gate` says whether a browser read may go now, and `stop "<what LinkedIn showed>"` halts browser reads for the day. Keeps only what a note could rest on, never their whole profile. |
| `python3 tools/network/sources.py ["<employer>"...]` | Where to look for people. Alone, this person's plan of source kinds, ranked by what has drawn replies; with employers, the run's exact searches inside the budget (at most four per employer and five shared by the whole run), and none for an employer the job search ruled out. |
| `python3 tools/network/why.py [<contact_id>...]` | Why each person: a score from 0 to 100 and one plain line, best first, by counting, with no model call. |
| `python3 tools/network/openalex.py "<employer>"` | Researchers who put the employer on a recent paper, only when `profile/networking.py` sets `OPENALEX`. A cloud session needs `OPENALEX_API_KEY` (SETUP.md). |
| `python3 tools/exclude.py` | Rulings in `seen_jobs.json`, each with what it rests on. `add <url> --reason "<why>" [--basis person] [--rests-on "<part>"]` rules a posting out (a reason that cites "blocker N" names its part by itself), `lift "<words in the reason>"` takes rulings off when the person changes their mind, `review` groups older rulings that record no basis, `stamp "<words>" --basis rules\|person` records what a group rests on, `parts` lists the parts of the rules a ruling can rest on, `lapsed` the rulings a rules change lapsed and `restamp "<words>" --rests-on "<part>"\|all` keeps the ones that still hold; `--url` narrows lift, stamp and restamp to named postings when reasons are word for word the same; and `rules` prints the rules fingerprint. |
| `python3 tools/sync_app.py` | Takes the app's updates and never sends anything back. `--if-stale` pulls master and syncs once a day and is a no-op after that; `--on "<model>"` ends the day's sync with the model check (`tools/model_guide.py`); `--check` says how far behind, changing nothing. Exit 1 stopped with nothing changed, 2 the app could not be reached. |
| `python3 tools/env_check.py` | Whether this session can do the whole job, one line each: LaTeX, Poppler, pypdf, Bun and every job board's host, with what to do about anything missing. |
| `python3 tools/network/state.py` | What is owed, the connection budget, the tracker links, and **RECONCILE**: every place the contact book disagrees with the message log. An orphaned thread sits undetected unless something runs it. Findings that need a person are listed; relationships that simply predate the message log are counted, not repeated. |

`tools/bridges.py` reads the honest-framing table (`profile/skills.py` BRIDGES): for each
skill a posting might ask about, what the candidate genuinely holds that does the same job
and the sentence to say it in. The
resume states no gaps and the cover letter volunteers none; this is what it says instead
when asked directly.

## Documents for someone else

The repo has no pipeline for drafting a resume for somebody other than the candidate. Its
renderer, bullet library, `verify_batch.sh` and grounding tools all assume the candidate.
When it is asked for anyway, this is what works:

- **Keep it out of the candidate's state.** Work in the session scratchpad, or in `documents/others/<name>/`
  only if asked to keep it. Never `cv/`, `cover_letters/`, the tracker, the networking CSVs or
  `profile/`.
- **One sources file first.** Their old resume verbatim, their LinkedIn, what they or the user
  confirmed (including contact details), and employer facts with URLs. Ground against that
  alone, and tell the `grounding-auditor` the document is not the candidate's so it skips
  their profile and tools.
- **Ask for real outcomes before inferring them.** One question round turns task bullets into
  results, and an inferred outcome is a claim nobody confirmed.
- **A standalone template needs the same proof as the candidate's:** one page read back visually, and
  `tools/verify_pdf.py` clean. That is what caught a font pypdf read with no spaces at all,
  which pdftotext and the eye both passed.
