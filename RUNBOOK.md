# Runbook: one round, portals to sent applications

Every step below is a command. Nothing spends model tokens until step 2, and step 2
spends them only on writing.

## 0. Fresh container, or a computer of your own

`./tools/setup_env.sh` does all of this where it can, and is a no-op when it is done. By hand,
in a cloud container (Debian or Ubuntu), the install is the one line in that script's header,
the same line START_HERE.md has a person paste into the cloud environment's setup script:
TeX and Poppler, then `cffi` before the Python packages. Then:

```bash
python3 -m pytest tests -q          # over 1,200 tests; all green before anything else
./tools/ci_local.sh                 # or this: every check CI runs, under two minutes, no Actions minutes
```

On a Mac (Homebrew; the TeX install asks for the Mac's password once):

```bash
brew install --cask mactex-no-gui   # nothing to add to the shell: the app finds /Library/TeX/texbin
brew install poppler
brew install oven-sh/bun/bun
python3 -m pip install --user -r requirements.txt   # the Mac's own python3 (3.9) is enough
./tools/ci_local.sh
```

Full detail, including why `cffi` comes first and which Python to use, is in [SETUP.md](SETUP.md).

**`$SCRATCH` below is any folder outside the repo**: the session's scratchpad in a
cloud chat, or something like `~/ljs-scratch` on a computer (`export SCRATCH=~/ljs-scratch`).
A round run on a person's own computer is gentler by default (two pages, four at once, at
most 300 requests a portal; `profile/search.py` `SCRAPE_PAGES`, `SCRAPE_WORKERS` and
`SCRAPE_MAX_REQUESTS` change that), because it comes from the address their own LinkedIn
account uses. Its progress prints a line a portal a minute, to the screen and `round.log`.

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
shortlist is ranked by fit x opportunity. A fit under 65 (`fit.FIT_FLOOR`) is held low in that
order, unless a warm route exempts it, and never cut: the yield target counts fit, so a
posting at 60 to 64 still counts toward it. `tools/throttle.py` has
applied the company throttle and the one-role-per-employer rule and written every skip
with its reason.

The `seen_jobs.json` dedupe runs at **prefilter**, not at the throttle, so a posting this
search already ruled out never reaches `hydrate` and never costs an HTTP call. It is the
throttle's own `ruled_out()` either way, imported rather than copied, so the shortlist is
identical; a large share of everything reaching hydrate used to be in that state. A ruling
made under the person's screening rules lapses by itself when those rules change, and one
in their own words holds until `tools/exclude.py lift` takes it off; a scoring setting
lifts nothing. `--no-seen-read` skips the check at the prefilter and the throttle alike:
everything ruled out is fetched, screened and scored again and can reach the shortlist,
which is what it is for after the rules change. Postings are still aged from when they
were first seen.

**Read the exit code.** 0 means the yield target was met, 2 means it was missed, 1 means
a stage actually broke. A thin market and a broken pipeline are different answers. A scrape
where more than a quarter of the portal requests failed is neither: the round carries on
with what the rest found and prints a warning, which belongs in what you tell the person.

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

It exits 2 and keeps four files it otherwise deletes, with the posting bodies stripped:

| File | Answers |
|---|---|
| `00_scrape/dropped.json` | what the age, location and title gates removed (the scrape applies them) |
| `01_dropped.json` | what was already ruled out in `seen_jobs.json`, and relists first seen too long ago |
| `03_screened_all.json` | what the stated-fact knockouts removed, with the quote |
| `06_skipped.json` | what the company throttle and the one-role-per-employer rule removed |

Those are the places a posting can vanish. `--expand` re-runs wider automatically,
up to three rounds in all, each with more pages per search (from the default 5, then 10,
then 30) and the same freshness window, which is a gate and never widens. Each wider round
reuses the bodies the round before it fetched. The other widenings (title
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
# Ask the questions it prints, then record each answer:
python3 tools/stage_picks.py consent "$SCRATCH/r1" <slug> --yes <skill> ... --no <skill> ...
python3 tools/stage_picks.py consent "$SCRATCH/r1" <slug> --draft   # or --skip: a held pick
# Two roles at one employer are both held with "which one?"; stage ... --both drafts both.
# Workflow draft-applications, args {today, round_dir: "$SCRATCH/r1", picks: <picks.json>}
python3 tools/stage_picks.py assemble "$SCRATCH/r1"          # -> drafts.json
```

The workflow researches each employer on sonnet and drafts and audits on the strongest
model, per `11-cost-model.md`. Research fetches only through `python3 tools/company_research.py
fetch "<employer>" --posting <pick file> --urls ...`: robots.txt first, the crawl delay kept,
a feed or sitemap behind a bot check, `FETCH_BUDGET` requests an employer a day, what each
host did noted in `company_research/_hosts.json` for the next agent, fresh facts never
fetched again, and each saved quote checked against the page. **Its concurrency is CPUs minus two**, which on a 4-CPU
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
and `posting` (the full text). `contact_person` (the recruiter or hiring manager the employer's
own page names for this role, never a name from anywhere else) addresses the letter to them,
and `req_id` reaches the tracker's notes; both stay empty when the research found none.

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
bans (`person.json` `documents.banned_nouns`), the ATS text layer (read with pypdf, which alone
sees words run together: without it the batch exits 3 and says the spacing check was SKIPPED),
every figure in each letter against the profile (`check_numbers.py --drafts`), and a letter
bullet that repeats a resume bullet. The resume's filename
noun is the profile's own word (`documents.noun`), so a profile that says "CV" writes
`cv/<Prefix>_CV_<ABBR>`; the globs here cover both.

`outreach` writes `documents/applications/<slug>/job_posting.md` and `outreach.md`. The
outreach note is a sub-80-word message to the hiring manager or recruiter built from the
letter's verified company fact. Sending it is the user's call; every application gets one.
It also keeps `draft.json` in that folder: the object both documents are rendered from, with
the posting named rather than copied. After a renderer fix,
`python3 tools/fit_to_page.py documents/applications/<slug>/draft.json` re-renders an unsent
application from it.

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

**On a computer of your own** (no GitHub tools in the chat; `gh` is the route, and
`place.py` lists it, and `gh auth login`, which is the person's to run, when either is
missing), each chat works in a folder of its own, made once and first, before any other work
(the sync's first line says so while a chat is in the main folder):
`python3 tools/sync_app.py --worktree <name>` (`../<repo>-<name>`, on a new, unique branch from
master), and every command runs there. Two chats in one folder switch branches under each
other and fight over git's index. Files git does not carry (the connections export) are read
from the main folder. Then, from that folder, commit, and:

```bash
git fetch origin master && git merge origin/master   # the row-by-row driver merges state files; the sync sets it here too
./tools/ci_local.sh
git push -u origin HEAD
gh pr create --base master --fill
gh pr merge <number> --merge
gh pr view <number> --json state -q .state           # MERGED is the answer, not the exit code
git fetch origin master && git switch --detach origin/master   # no local master to fall behind
```

`gh pr merge` can exit non-zero after a merge that worked: it tries to fast-forward a local
master that has fallen behind and prints "fatal: Not possible to fast-forward". Keep no
local master, and read the state, not the exit code. In the Claude desktop app, a merge
may be refused by the app's own permission check ("merge without review"): then the
person merges it, or approves it, and the chat says so once and stops; it never retries.
When the pull request has landed, `git worktree remove <the folder>`.

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
- Each follow-up names who it goes to: the row's `contact_person`, the application's
  `outreach.md`, or a contact there who has replied. One with nobody on file is listed
  without a draft; put the recruiter or hiring manager in `contact_person` and the draft is
  addressed to them. A later row for the same role closes the earlier one.
- This is the application clock, `tools/followups.py`. A networking contact's nudge is a
  separate clock on purpose: 5 to 7 business days, and one only (the networking skill).
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
| `python3 tools/run_round.py --out rounds/rN [--expand]` | The whole free pipeline, portals to ranked shortlist. It checks the yield target and prints MET or MISSED with the counts. **Exit 0 met, exit 2 missed, exit 1 a stage actually broke** - a thin market and a broken pipeline are different answers. `--expand` re-runs wider up to the 3 rounds the rule allows. It **prunes itself**: `rounds/` is gitignored and its ~55MB of stage files are deleted, except `06_shortlist.json` cut to the top 60 with their bodies, which is what drafting is staged from; the same 60 rows, minus the posting bodies, are written to `documents/rounds/<round>.json` and **are** committed. `--keep-intermediates` retains the stage files for debugging a round that went wrong, and a round that **missed** keeps `00_scrape/dropped.json`, `01_dropped.json`, `03_screened_all.json` and `06_skipped.json` automatically, with the posting bodies stripped, because those are the files the MISSED message tells you to read. |
| `python3 tools/job_alerts.py <messages.json> --out <alerts.json>` | The person's LinkedIn job alerts, read by the session from Gmail only when `profile/search.py` `JOB_ALERT_QUERY` asks for it (`--query` prints the search). Takes the job ids alone and fills each posting from LinkedIn's own page; `run_round.py --alerts <alerts.json>` adds them to the round before the free filters. |
| `python3 tools/network/prep.py --all` | Rewrites every contact's prep document. Without it a fix to `prep.py` reaches whichever one somebody runs next and no others. Each document's last line says which prep wrote it: `--stale-only` rewrites only the documents an older prep wrote or written before the contact's row or thread changed (and never writes one for a contact who has none), keeping answers already rewritten to be said, and `--dry-run` lists what would be written and writes nothing. `"<contact>" --check` exits 1 while an answer is raw profile wording or reads as written. |
| `python3 tools/network/export.py` | LinkedIn's data export, read, only the files it names: `files <zip>` says what it holds and what is missing, `history --from <zip>` lists the messages and invitations it would add to network_threads.csv (joined by profile address, else a careful name match, else listed as not in the contact book) and `--apply` writes them, twice adding nothing; `pending` lists the invitations sent and never accepted for three weeks, oldest first, for the person to withdraw on LinkedIn, and `withdrawn <name>...` records the ones they did. Nothing is sent. |
| `python3 tools/network/own_profile.py` | The person's own LinkedIn profile, now and then. `due` prints one line when a look is worth it (never looked over, a fact it compares has changed, or a run of unanswered first notes too long to be chance) and nothing otherwise, at most once in 30 days; `check` lists red flags only, each with its evidence and one fix; `brief` is what is left for the session's model to judge, well under two thousand tokens. Kept in documents/network/own_profile_review.json. |
| `python3 tools/network/profile_facts.py` | The candidate half of a prep doc, read out of `01-candidate-profile.md` and `tools/bridges.py`. `prep.py` calls it automatically; run it directly to see what it extracts. |
| `python3 tools/open_actions.py` | Everything owed, employers first, derived from the three state files: live applications, contacts owed a reply, and **follow-ups due** on applications that have gone quiet. `--company <name>` for one employer. **`--due`** prints only what is due today or overdue, both halves, most urgent first, with the counts on line one and the first five lines written to stand alone: it is what the daily routine pastes into a push notification. A contact whose `next_action` opens on HOLD or FREEZE is not due until the date after "until" arrives. An interview booked in an application's `outcome.md` is due once it is a week away with no pack for that stage, and its thank-you for a week after it until one is on file. This is the one view; `tools/followups.py` is the nudge half of it and still runs on its own when that is all you want. |
| `python3 tools/what_works.py brief <messages\|documents\|search\|interviews>` | What has worked, counted from the state files with no model call: reply rates and the messages that drew replies, the applications that reached an interview with the resume and letter they used, the interview rate by fit band and route, and (`interviews`) how far applications get by the stages ticked in each `outcome.md`, with the questions the bank says keep coming up and the stories that landed. A difference is reported only when the groups are big enough and the gap is unlikely to be chance. `event --contact <id>` and `event --company <name>` are the one-line audit when a result arrives. |
| `python3 tools/interview_pack.py pack "<company>"` | The one living prep document `/interview` builds for a hiring process, one screen first (what they are assessing and want to hear, likely questions with the story or answer for each, hooks, the money, what not to say), then your answers to write as said, what the employer's people and papers have been told (conflicts flagged), who you are meeting and the question for each, the format, and the detail, every fact sourced. `--stage`, `--date`, `--with`, `--format` (case, coding, behavioural, technical, presentation, screen), `--map <json>` and `--write` (beside the application, as `interview_prep.md`, keeping what the person wrote). `process "<company>" --contact <id> --role "<role>" [--posting <file or link>]` registers a process with no application (a referral or a recruiter's call) and writes its document in one command; `postings` gives every process folder that has none a `job_posting.md`. `motive "<question>" --answer "<their words>" [--suits ...] [--not-for ...]` keeps the person's own reasons in `profile/07-interview-prep.md` for every later employer. `check` exits 1 while an answer is unwritten or reads as written, a question waits on the person's own reasons, or research is still to do. `campaign --yes "<chat>"\|--no` records the one-time offer of a chat for that employer. `asked` adds a question an interview asked to `documents/interview/question_bank.csv`; `rework` adds an answer to work on, which a rebuild keeps. |
| `python3 tools/profile_consistency.py` | The pay band, the walk-away floor, the notice period, the sponsorship position and the permit-disclosure rule, said the same way across the profile: names every other place that says one differently from its source (the rubric's salary table, the candidate profile's notice line, the summary's sponsorship sentence). Exit 1 when anything disagrees; the `profile-consistency` upgrade asks the person which is right. |
| `python3 tools/followups.py` | The application nudges alone, on the schedule in step 5, "After the user applies": each one due, who it goes to, the held ones with their reason, and where the chase stops (at the throttle's 45 days of silence, `throttle.SILENCE_DAYS`, or a week after the second follow-up). `--close-quiet` closes each application past the chase as `no_response` with a dated note; the brief runs it. |
| `python3 tools/stage_picks.py stage <round_dir> <pick>...` | The step between a shortlist and a draft. A pick is a shortlist rank or `Company::title words`. In a later session, when `rounds/` is gone, it reads `documents/rounds/<round>.json` instead and fetches each pick's body from its board, or reads `<round_dir>/postings/<slug>.txt` when the board will not give it. `single <dir> --company --role --posting-file` stages one posting from no round, which is how `/apply` enters the same pipeline. Writes each posting fenced by `tools/untrusted.py`, `picks.json` (the `draft-applications` workflow's args) and `apps_in.json`, and picks each filename: **a name another application was sent under is never reused**, so a second role at an employer gets a role token (`Acme_DemandPlanning`). It prints what code read from each posting (contract or permanent and when it ends, the pay and whose place it is for, years, degree, where and how it is worked, a repost, what is already running at the employer) and holds a pick with a surprise in it (a fixed-term contract, pay for another place, an application already in, a referral in flight, a second role at one employer unless `--both`) in `held.json` until `consent <round_dir> <slug> --draft` or `--skip`. It prints one short question per pick about the skills the posting names that the profile does not hold (never one it covers under another name: a held part such as Azure Data Factory covers Azure, a listed synonym such as model serving covers model deployment), and `consent <round_dir> <slug> --yes ... --no ...` records the answers: nothing is drafted or assembled while one waits, a yes prints on that resume's skills line, and both answers go into the documents' header. `assemble <round_dir>` turns the audited drafts into `drafts.json` and names any pick with no draft. |
| `tools/verify_batch.sh <drafts.json>` | Every rendered application: pages, chronology, section layout, text layer, claims, letters. Exits non-zero on any finding. |
| `python3 tools/record_drafts.py <drafts.json> <apps_in.json> --round rN` | The tracker rows for a rendered batch, by `/apply` Step 6b's rules, plus `screening_answers.md` for each. It writes **fit** in `fit_rating`, never the shortlist's priority, which can exceed 100 on a 0-100 column. |
| `python3 tools/bar.py "<company>"` | The candidate's bar in code: pay, prestige, signal, or none, with the reason. The throttle applies it every round: the sectors and employers `profile/search.py` excludes are skipped with the reason recorded, every other row carries its verdict into the shortlist and `documents/rounds/`, and "none" is a flag, never a cut. An employer on none of the profile's lists says so ("not on your employer lists yet"): `bar.py unjudged` lists them in the newest shortlist, and `bar.py judge "<company>" <pay\|prestige\|signal\|none> "<why>"` records a judgement once (`profile/employers_judged.json`), which every later verdict reads; the profile's own lists and hard rules outrank it. |
| `python3 tools/network/reading.py` | What was read about one person before writing to them: `read <contact_id> <file\|->` takes their profile page (pasted, read in the person's own browser, LinkedIn's Save to PDF, or transcribed screenshots), `add` one public finding (a talk, an article, a post), `show` what a note can rest on, best first, and `queue` the waiting drafts with no fresh reading, offering a paste for the best three only. `paste <file\|->` reads several profiles pasted at once, a line of `---` between them, each matched to a waiting note by name and employer. `draft <contact_id> <file\|->` writes a first note to its `draft.md`, opening on `WAITS ON A READ` when nothing was read about them. `shortlist <ids>` puts the run's best ten on the day's short list, and a browser read refuses anyone not on it. `verdict <contact_id>` is KEEP or SKIP after a read, `route --tools <...>` says how this session reads profiles and the one line to tell the person, `gate` says whether a browser read may go now, and `stop "<what LinkedIn showed>"` halts browser reads for the day. Keeps only what a note could rest on, never their whole profile. |
| `python3 tools/network/sources.py ["<employer>"...]` | Where to look for people. Alone, this person's plan of source kinds, ranked by what has drawn replies; with employers, the run's exact searches inside the budget (at most four per employer and five shared by the whole run), and none for an employer the job search ruled out. `ladder --tools <...>` prints what this chat can use, from their connections export to a read in their browser, and the one line to say when it has no browser; `connections "<employer>"` lists who they already know there; `harvest <results.json> --company "<employer>"` turns a search's results into a ranked list of people, each with its evidence, profile status (verified, likely or unconfirmed) and route, nothing fetched. |
| `python3 tools/claude_surfaces.py` | What the Claude app and Claude Code can do, and how to reach each part, dated and sourced (`tools/claude_surfaces.json`): `show <id>`, `say <id>` (the words a person sees), `check` (entries older than 60 days, as warnings), `sync-docs` (the docs' marked blocks), and `watch`, the maintainer's check of every quote against its page and of the latest release, run weekly in the app only. |
| `python3 tools/network/why.py [<contact_id>...]` | Why each person: a score from 0 to 100 and one plain line, best first, by counting, with no model call. |
| `python3 tools/network/openalex.py "<employer>"` | Researchers who put the employer on a recent paper, only when `profile/networking.py` sets `OPENALEX`. A cloud session needs `OPENALEX_API_KEY` (SETUP.md). |
| `python3 tools/exclude.py` | Rulings in `seen_jobs.json`, each with what it rests on. `add <url> --reason "<why>" [--basis person] [--rests-on "<part>"]` rules a posting out (a reason that cites "blocker N" names its part by itself), `lift "<words in the reason>"` takes rulings off when the person changes their mind, `review` groups older rulings that record no basis, `stamp "<words>" --basis rules\|person` records what a group rests on, `parts` lists the parts of the rules a ruling can rest on, `lapsed` the rulings a rules change lapsed and `restamp "<words>" --rests-on "<part>"\|all` keeps the ones that still hold; `--url` narrows lift, stamp and restamp to named postings when reasons are word for word the same; and `rules` prints the rules fingerprint. |
| `python3 tools/sync_app.py` | Takes the app's updates and never sends anything back. `--if-stale` pulls master and syncs once a day and is a no-op after that; `--on "<model>"` ends the day's sync with the model check (`tools/model_guide.py`); `--check` says how far behind, changing nothing. Exit 1 stopped with nothing changed, 2 the app could not be reached. |
| `python3 tools/env_check.py` | Whether this session can do the whole job, one line each: LaTeX, Poppler, pypdf, Bun and every job board's host, with what to do about anything missing. |
| `python3 tools/network/state.py` | What is owed, the connection budget, the tracker links, and **RECONCILE**: every place the contact book disagrees with the message log. An orphaned thread sits undetected unless something runs it. Findings that need a person are listed; relationships that simply predate the message log are counted, not repeated. `withdraw <contact_id>...` (or `--all-due`) records connection requests the person has withdrawn: a `request_withdrawn` row and the contact closed, so they are never surfaced again. |

`tools/bridges.py` reads the honest-framing table (`profile/skills.py` BRIDGES): for each
skill a posting might ask about, what the candidate genuinely holds that does the same job
and the sentence to say it in. The
resume states no gaps and the cover letter volunteers none; this is what it says instead
when asked directly.

## Two chats applied the same profile upgrade

One chat owns each update's upgrades: the chat whose sync of it reached master first
(`profile_upgrades.py` checks master before it tells a chat to start, and `/upgrade` checks
it again before each one). Two chats that synced the same update within a minute can still
both apply one. Then merging master conflicts in that upgrade's files (its `Profile upgrade:
<id>` commit names them). **Take master's copy of each of those files**
(`git checkout --theirs -- <file>` while merging master in, then `git add <file>`): an
upgrade makes the same change wherever it runs, so the copy already on master is the
answer, and a person need not be asked to choose. Anything else in a conflicted file that
this chat changed itself is kept as usual.

## Your own tests fail after an update

A person's own tests (`profile/tests`) pin how the app worked when they were written, and
an update can change or remove what they pinned. CI going red after a sync is usually this,
not a bug in the update.

1. `python3 tools/sync_app.py --own-tests` sorts every failing test into two kinds and says
   what to do. The sync and `ci_local.sh` print the same by themselves.
2. **It uses a part of the app the update removed** (an `AttributeError` or `ImportError`
   naming one of the app's modules, often a name starting with an underscore). What it
   checked has moved, and the app's own tests cover the app's behaviour. Rewrite the ones
   that pin the person's own data through the app's public names (a job board through
   `tools/offline_boards.py`), keeping every assertion; the rest are retired.
3. **It checks behaviour the update changed.** Read the CHANGELOG entry for the change and
   bring the test in line with it. If the new behaviour looks wrong for this person, report
   it to the app (the way this repo's `profile/CLAUDE.md` says, or an issue on the app) and
   leave the test failing rather than weaken it.
4. **Deleting a failing test is the person's call, asked in plain words.** The sync prints
   the exact question, its two answers with "Yes (recommended)" first, what to say if they
   ask what it means, and the reply to each (`ASK_TIDY` and the lines under it in
   `tools/sync_app.py`). Ask once, in those words: most
   people have never seen a test, and "retire 57 tests?" means nothing to them. When none
   needs deleting there is no question. A permission check that stops an unexplained
   deletion is right to.
5. Run `./tools/ci_local.sh`, then land on master as usual. Until it is green, master stays
   on the old version and nothing breaks.

`python3 tools/sync_app.py --own-test-risks` names the tests that will break the next time
the app changes a private part, before it does; `ci_local.sh` prints it as a note.

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
