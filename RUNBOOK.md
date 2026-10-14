# Runbook: one round, portals to sent applications

Every step below is a command. Nothing spends model tokens until step 2, and step 2
spends them only on writing.

## 0. Fresh container

```bash
apt-get install -y --no-install-recommends texlive-luatex texlive-latex-extra texlive-xetex \
  texlive-fonts-recommended poppler-utils   # icon fonts are vendored in texmf/, see its README
pip3 install --upgrade cffi pytest pypdf
python3 -m pytest tests -q          # over 450 tests; all green before anything else
./tools/ci_local.sh                 # or this: every check CI runs, ~40s, no Actions minutes
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
then deletes the stage files and prints how much it freed. That summary file is the one
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
identical; a large share of everything reaching hydrate used to be in that state. `--no-seen-read`
turns it off, which is what you want after changing the scoring rules and wanting
everything previously excluded re-evaluated.

**Read the exit code.** 0 means the yield target was met, 2 means it was missed, 1 means
a stage actually broke. A thin market and a broken pipeline are different answers.

**Anything older than 14 days is already gone** from the portals. If one is blocked by
the session's egress policy the log says `connect_rejected`; that is environment policy,
not a bug. To re-run every free stage on a scrape that already succeeded, without
touching the portals:

```bash
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
up to three rounds. If it still misses, say so with the count, what was tried and the
likely blocker. **Never pad a thin run with sub-60 postings, and never relax a gate or
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
python3 tools/check_claims.py cv/*_Resume_*.tex cover_letters/*_Cover_Letter_*.tex
tools/verify_batch.sh "$SCRATCH/r1/drafts.json"
python3 tools/outreach.py "$SCRATCH/r1/drafts.json" "$SCRATCH/r1/apps_in.json"
```

`fit_to_page` allocates bullets, renders, compiles, trims the weakest bullet for *this*
posting until one page, then grows back the strongest absent one that still fits.

`check_claims` must report **0 error-level findings**. `audit_letters`, which
`verify_batch.sh` runs, must report every letter clean. `verify_batch.sh` exits non-zero
on any finding and checks pages, chronology, section order, bullets per employer, contact
details as literal text, duplicated phrasing, em dashes, the word "CV", and the ATS text
layer.

`outreach` writes `documents/applications/<slug>/job_posting.md` and `outreach.md`. The
outreach note is a sub-80-word message to the hiring manager or recruiter built from the
letter's verified company fact. Sending it is the user's call; every application gets one.

Then read three PDFs by eye. Not the .tex, the PDF. LaTeX page-break decisions are not
predictable from source, which is the whole reason this step exists.

## 4. Record and persist

`python3 tools/record_drafts.py "$SCRATCH/r1/drafts.json" "$SCRATCH/r1/apps_in.json" --round r1`
adds a row per application at `status=drafted` (fit in `fit_rating`, never priority) and
writes each `screening_answers.md`. Then:

```bash
git add -f job_search_tracker.csv documents/applications/ job_scraper/seen_jobs.json
git add -f cv/*_Resume_*.tex cv/*_Resume_*.pdf
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
  the next run offers the first again. After two, or 45 days of silence, the chase stops
  and says so once.
- A follow-up with nobody on file is listed without a draft. Put the recruiter or hiring
  manager in the row's `contact_person` column and the draft is addressed to them.
- `DO NOT CHASE` in a row's notes holds its follow-ups, with the reason shown; `until
  YYYY-MM-DD` in the same note, or a later note saying `chase again`, lifts it. An
  interview or offer at the same employer, or a referral in flight there, holds them too.
- `/interview <company>` when one lands. Not `/prep`, which is for a networking call.

## What "done" looks like for a round

At least 5 postings scoring 60+, of which 2 at 75+, all under 14 days old. Every drafted
application has two verified one-page PDFs, a persisted posting, an outreach note, a
tracker row, and 0 claim errors. All of it committed, and on master.
