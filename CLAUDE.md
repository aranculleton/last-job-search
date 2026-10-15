# last-job-search: a job search that Claude runs end to end

## Role
This repo runs the whole job search, not one part of it. Claude operates it, and the
name is the claim: there should be nothing else you need open. The work it covers:
1. **Finding the work** - scrape every enabled portal, then filter, fetch, screen and score
   every posting 0-100 against the profile, and stop at a ranked shortlist for a person to choose from
2. **Job fit evaluation** - Assess job postings against your profile (skills, experience, behavioral traits)
3. **Resume tailoring** - Adapt existing resume templates (LaTeX/moderncv) to target specific roles,
   with bullets allocated per posting rather than picked from a fixed set
4. **Cover letter writing** - Draft targeted cover letters using existing templates (LaTeX)
5. **Verifying what it produced** - compile both documents, read the PDFs back, and check the
   embedded text layer an applicant tracking system actually parses
6. **Networking** - find the right people at target employers, draft the outreach, track every
   thread, and keep a cold application from landing on top of a warm introduction
7. **Interview preparation** - Prepare answers, questions, and talking points for interviews
8. **Career strategy** - Advise on positioning and personal branding

It never submits anything. Every document stops as a file on disk, and a person sends it.

## The person

Everything about the person this search is for lives in `profile/`, and its summary is
imported here:

@profile/CLAUDE.md

`profile/01-candidate-profile.md` is the source of truth for every fact about them. The
summary above is a working copy for quick reference; where the two disagree, the profile
wins, and the disagreement is a bug to fix rather than a choice to make. The rest of
`profile/` is the same person in the form the tools read (`person.json`, `roles.py`,
`bullets.py`, `skills.py`, `search.py`, `employers.py`, `boards.py`, `networking.py`,
`claims.py`, `screening.py`) and the documents written from it: `02-behavioral-profile.md`,
`04-job-evaluation.md`, `10-triage-blockers.md`, `12-scoring-brief.md`, `13-positioning.md`.
If there is no `profile/`, nothing here can run: start with `/setup`.

## Start of every session

This repo is either **the app** (`github.com/aranculleton/last-job-search`, public, no
`profile/`) or **a person's repo**, made from the app with "Use this template" and private.
Every session in a person's repo starts with the same four steps, before anything else:

1. **Pull master**: `git fetch origin master && git merge origin/master`. Another chat may have
   merged since this container was built.
2. **Take the app's updates**: `python3 tools/sync_app.py`. It fetches the app and merges what is
   new, and never sends anything back. The app is public, so nothing needs attaching; if it still
   cannot reach it (exit 2), attach it read-only with `add_repo` (owner and repo from the URL
   `https://github.com/aranculleton/last-job-search`, `access="read"`) and try once more, and if
   that fails too, say so in one line and carry on. Exit 1 means it stopped with nothing
   changed: show the person what it listed and ask before going further.
3. **No `profile/`?** Then nothing here can run yet. Start with `/setup`, before anything else.
4. **If the sync brought changes**, say in one line what changed, from the CHANGELOG lines it
   printed.
5. **Profile upgrades apply themselves; nobody has to ask.** The sync ends by listing what
   this repo still needs (`tools/profile_upgrades.py`): parts of the app that switched on
   after this person set up (their job boards researched and built, a setting written for
   their field, a portal rebuilt), and facts in the profile still marked `[CONFIRM: ...]`.
   The person will not know which ones matter, so never offer them a list or wait for a yes:
   - **What Claude can do alone** ("Claude applies these itself"): start a background agent
     at once (Agent tool, `run_in_background: true`, `isolation: "worktree"`) running
     `/upgrade`, and go on with what the person asked. Their request never waits for it.
     When it reports, merge its branch into this session's work.
   - **At the end of your reply**, one line per upgrade it applied: what changed and
     `git revert <sha>` to undo it.
   - **What needs the person** ("These need you", unconfirmed facts): ask at most three,
     plainly, at the end of the session, never at the start; write each answer where its
     marker was and commit it. The rest wait for the next session.
   If the sync printed nothing about upgrades (its first run after this arrived is the old
   copy), run `python3 tools/profile_upgrades.py` yourself and do the same.

In the app itself, step 2 is a no-op and step 3 does not apply: the app has no profile and
must never get one.

## App-owned files and personal files

`tools/personal_paths.py` is the line. Everything it lists (the profile, the tracker, the
contact book and threads, documents, research) is the person's; everything else is the app's.

- **In a person's repo, never edit an app-owned file.** The next sync puts it back to the app's
  version and says so. A fix or a feature the app needs is made in the app (below) and arrives
  here through the sync. If the person is not the app's maintainer, offer to write the idea up
  as an issue on the app instead.
- **A person's own rules go in `profile/`**, never in an app file: their document rules, voice,
  market and anything else that is theirs belong in `profile/CLAUDE.md` and the profile's data
  files, which the tools and these instructions already read.

## Claude does the tailoring, and keeps doing it

`/setup` asks plain questions only: where they live and will work, their right to work there
(and whether they need sponsorship), the roles and fields they want, salary hopes,
deal-breakers, employers they love or will not touch, how they like to come across. It never
asks anyone to name a job board, an ATS, a spelling convention or a config value. Claude does
that research and writes the profile: which job boards serve their city and field (building
one with `/add-portal` when it is missing, after checking robots.txt the way
`tools/robots_check.py` does), which target employers post on Greenhouse, Lever, Ashby or
Workday (probed the way `tools/ats_boards.py --probe` does), the eligibility and visa wording
postings in their country use, salary norms for their role and city, local document
conventions (resume or CV, page length, spelling), and the market's place names. Everything
researched is cited and stored in `profile/`.

**And it keeps going without being asked.** When a round comes back thin, a good posting
arrives from a board that is not covered, an employer they mention has no board on file, or a
gate cuts something it should not for their market, propose the fix, do the research, and
record it in `profile/`.

## Developer rules: changing the app itself

These apply whenever the change is to the app, whichever repo the session started in.

- **Changes are made in the app**, on a branch, through a pull request, and merged only with
  CI green. The app is public, so its Actions minutes are free and its CI is the evidence.
  Then every person's repo takes the change on its next sync, the maintainer's included.
- **Nothing reaches the app until the leak scan has passed on the exact tree being pushed,
  branches included**: a public repo's branches are public, and its history is permanent. From
  the maintainer's own repo, `python3 tools/build_app.py <dir> --tokens-out <dir>/tokens`
  writes the denylist from their profile; then `python3 tools/leak_scan.py <app checkout>
  --tokens <dir>/tokens` scans the app checkout with it. The app's CI scans again with the
  `LEAK_TOKENS` secret, but CI only sees what is already public, so the local scan is the gate.
- **No example may be a disguised person.** An example resume, story, message or incident is
  invented, or it is the example person in `profile.example/`. A real case with the names
  swapped is still that person.
- Small PRs and batched commits. A change that touches how documents, scores or messages
  come out is checked by rendering the same inputs before and after and comparing the
  outputs; any difference is named in the PR, or it is a bug.
- **Never ship a feature that only works after a person does something nobody told them
  about.** If an existing user has to act for a change to reach them (a `/setup` section, a
  portal built or rebuilt with `/add-portal`, a re-render, a new state file or column, a
  profile name with no safe default), register it in `tools/profile_upgrades.py` with a
  `pending()` that checks their repo for the trace the action leaves, and name it in the
  CHANGELOG entry (`Profile upgrade: <id>`). Make it `needs="nobody"`, which `/upgrade` applies
  in the background with no one asking, unless it truly needs the person's answer or consent.
  A new profile name with a safe default goes in `SAFE_DEFAULTS` with the reason.
  `tests/test_profile_upgrades.py` fails on either missing.
- **A better way of doing any part of the build reaches every older repo by itself.** Each
  part that leaves something behind in a person's repo (a `/setup` section, the boards, prep
  documents, unsent drafts, interview packs, research, contacts, screening, routines) is a
  versioned method in `tools/build_versions.py`, and every other app file is in its
  `KEEPS_NOTHING` with the reason. Changing a method's files fails
  `tests/test_build_versions.py` until a version is added saying what changed and `rerun`:
  True when what an older version made should be made again (a better board search, a
  fixed prep document), False for wording. With True, every older repo redoes it with no one
  asking: `/upgrade` in the background, the sync itself for an instant one, or every round
  for screening. A new app file fails the same test until it is placed in a method or in
  `KEEPS_NOTHING`. The decision can be made either way; it cannot be skipped.

## Master is the trunk. Finish on it, start from it.

Several Claude chats run against this repo, each one in its own container, each one
handed its own branch. That works only if every branch lands on master before its
session ends. When it does not, the cost is worth stating, because it is the exact
failure this rule exists to prevent:

> A session's branch runs far past master. A second session starts from master, correctly
> reports that nothing in the repo holds some piece of state, and builds a second store
> for it, because the first session's file is sitting on a branch it cannot see.
> Reconciling the two takes longer than the work in either.

So, every session:

1. **Start by pulling master and taking the app's updates** ("Start of every session"
   above). Another chat may have merged since this container was built. Do this before
   writing anything, not before pushing.
2. **Finish by getting the work onto master.** Not "pushed to the branch": on master.
   Open the pull request, run `./tools/ci_local.sh`, merge it. A branch left behind at the end of a
   session is work the next chat cannot see and will duplicate.
3. **Never leave a merged branch around**, and never start new work on an old one.
4. If the work genuinely is not finishable this session, say so in the last message and
   name the branch, so the next chat is told where to look rather than left to find out.

The one thing that is **not** negotiable in the other direction: do not push to master
without CI green. It is the branch every other chat starts from, so a broken master
breaks all of them at once.

**On a private repo, green is established locally, and that is the rule, not the
fallback.** GitHub bills a private repo per job, rounded up to the minute; a
public repo's minutes are free. Every job in `.github/workflows/ci.yml` now runs only on a
public repo (the app) or on a manual dispatch, so here the
checks show as skipped and cost nothing. Every check in that file is a script in this repo:

```bash
./tools/ci_local.sh            # every check CI runs, under two minutes
./tools/ci_local.sh --quick    # skips the LaTeX compile
```

A clean run is the evidence, and merging on it is allowed. Say in the PR that
`ci_local.sh` was green and name anything it reported as SKIP. Dispatch the workflow by
hand (Actions, CI, Run workflow) only when a SKIP matters for the change, and tick
`latex` only when LaTeX changed. That is the one case worth a billed minute here.

CI's second Python leg exists because a bare `import tomllib` passed locally and failed on
3.10. `ci_local.sh` runs that leg the way CI does (a fresh 3.10 environment with pytest and
nothing else), on the system `python3.10` or one `uv` fetches in seconds; the containers
may not ship one. Only where neither exists is the leg reported SKIP, never
passed silently. What a local run cannot be is a second machine; the app's own CI, which
is free, is that for every change made there.

**Still worth doing, because no setting enforces it: batch the commits and push once.**
Push when a unit of work is finished, not to watch CI think, and prefer a PR to a direct
push to master.

## Persistence rule for a person's repo (deviates from upstream)

This is about **what** to commit. The section above is about **where** it ends up. Both
are needed, and this one gets more important the more chats are running, not less: state
that only exists in one container is state the other chats are about to contradict.

A person's repo is **private** and the job search runs in ephemeral cloud sessions,
so the upstream rule "never commit the tracker or application artefacts" does not apply
there. Upstream ships that rule because forks of it are public; a repo made from this
app with "Use this template" and set to Private is not, and nothing persists between
sessions unless it is committed. The app itself never holds any of it: it has no
profile and no state, and its CI fails on a personal path.

**Do not edit `.gitignore`.** The rules in it are enforced by `tools/security_guards.py`,
which runs in CI on every push. Weakening them fails the build. Instead, force-add the
specific artefacts with `git add -f`, which leaves `.gitignore` intact and keeps the
guard passing.

At the end of any session that produced application work, commit these:

```bash
for p in profile networking; do      # not ignored: a plain add, so no cache file comes with it
  [ -e "$p" ] && git add -- "$p"
done
for p in job_search_tracker.csv network_contacts.csv network_threads.csv \
         job_scraper/seen_jobs.json job_scraper/do_not_target.json \
         documents/cv documents/applications documents/network documents/rounds \
         cv/*_Resume_*.tex cv/*_Resume_*.pdf cv/*_CV_*.tex cv/*_CV_*.pdf \
         cover_letters/*_Cover_Letter_*.tex cover_letters/*_Cover_Letter_*.pdf \
         company_research/*.json upskill/*.md; do
  [ -e "$p" ] && git add -f -- "$p"
done
```

`profile` is there because what the person teaches it (`profile/learned.json`), the facts
written back to `01-candidate-profile.md` and every setting changed in a session live there.
It takes a plain `git add`, never `-f`, which would force in the ignored caches under
`profile/tests/`.
`company_research/*.json` is gitignored and costs a fetch to rebuild; the Memory table below
says to keep it.

One path at a time, and only what exists: a single `git add` with a path that does not
exist yet (a new repo has no `upskill/*.md`) stages nothing at all, silently.

`documents/rounds/<round>.json` is each search round's shortlist, the top 60 without
the posting bodies. It takes a plain `git add`: it deliberately sits outside `rounds/`,
which is gitignored, because a keeper inside an ignored tree would need a `!` negation
and `tools/security_guards.py` rejects any negation outside its reviewed allowlist.

The two networking CSVs are the pipeline state for outreach, the same way the
tracker is for applications, and they are not gitignored, so they take a plain
`git add`. Thread status is derived from the message log rather than stored, so
`network_threads.csv` is the file that must not be lost: without it every
contact reverts to `not_contacted` and the same people get messaged twice.

**Never force-add build noise:** `*.aux`, `*.log`, `*.out`, `*.fls`, `*.fdb_latexmk`,
`*.synctex.gz`, `cv/*.txt` (ATS text dumps), `__pycache__/`, `.pytest_cache/`.
`salary_data.json` and `gmail_sync/state.json` stay uncommitted too - the first is
licensed third-party data, the second is a Gmail sync cursor with no value in git.

## Environment notes for cloud sessions

- **One command sets the container up: `./tools/setup_env.sh`.** It installs LaTeX, Poppler
  and the Python side if missing, one package at a time, and is a no-op when they are present.
  The permanent fix is the pasteable line in its header, in the cloud environment's Setup
  script, which is cached. It is deliberately not a SessionStart hook: see below.
- **LaTeX and PDF tooling are not preinstalled.** What the script installs:
  `apt-get install -y --no-install-recommends texlive-luatex texlive-latex-extra texlive-xetex texlive-fonts-recommended poppler-utils`
  (the same set CI's Debian leg uses), about 160 MB to download.
- **`texlive-fonts-extra` is not installed, on purpose.** It is 1.7 GB and the resume used
  1.5 MB of it: moderncv's `fontawesome5` and `academicons`. Those are vendored in `texmf/`.
  `tools/fit_to_page.py` sets `TEXMFHOME` to it for every compile; for a compile by hand,
  `export TEXMFHOME="$PWD/texmf"` first (or run `setup_env.sh`, which links `~/texmf`).
  `File fontawesome5.sty not found` means that step was skipped, not that a package is
  missing.
- **`pypdf` needs a working `cffi`.** The system `cryptography` package can be broken on a
  fresh container, which makes `tools/verify_pdf.py` fail with a pyo3 panic rather than a
  clean ImportError. Fix with `pip3 install --upgrade cffi`.
- **Job boards may be blocked by the session's egress policy.** If `/scrape` or
  `/apply <url>` fails to reach a portal, check `curl -sS "$HTTPS_PROXY/__agentproxy/status"`
  for `connect_rejected` entries. That is an environment policy denial, not a bug -
  do not route around it. Fall back to `/apply <pasted posting text>`, which needs no network.

## Automation: what runs without anyone asking

**`automation/README.md` is the whole story; `profile/routines.json` is the registry.**

The scheduled tasks, when they run and where they report are the person's: `profile/routines.json`
and the automation section of `profile/CLAUDE.md`.

**The shape, and why.** Two set-ups work, and the README walks a person through either:
**(a)** one chat per task ("Job search: morning brief", "Job search: shortlist" for the
twice-weekly round), created with the private repo, each task bound to its own chat, whose
reply is the briefing (no push); or **(b)** each task made in the Claude app's Routines screen with the
repo ticked and notifications on (push, and a new chat every run). Each task's stored prompt
is a stub that reads `automation/prompts/_common.md` and its own file from master, so
**changing what a task does is a normal PR**; only a schedule change needs `update_trigger`
or the Routines screen. The final reply is the message; nothing depends on `fire_trigger`.
An older shared-chat set-up that relays to the phone through a fresh-session task still
works only from a chat made before 14 October 2026: never archive, delete or rebuild one,
and never test a chat-bound task with `fire_trigger` (use a one-off `run_once_at` task
bound to the chat). `python3 tools/routines.py check` validates the registry, and
`ci_local.sh` runs it.

**Silence is the alarm.** The brief is delivered every day even when nothing is due, so a
morning with no brief means the automation is broken. `automation/README.md` has the
set-up steps if a chat or a task is lost.

**Every dated follow-up is automatic by construction.** The brief reads `next_action_due`
from `network_contacts.csv` and the nudge schedule from the tracker, so a reminder is created
by writing the date into the state file, never by creating another routine. One routine per
contact is the pattern this replaced.

## Orchestration: workflows and model choice

Two saved workflows live in `.claude/workflows/` and are run by name with the Workflow
tool. Both pin the model per stage to `11-cost-model.md`, which is where the saving is:
reading and fetching go to sonnet, and anything that could put a false claim in front of
an employer inherits the strongest model and is never downgraded.

| Workflow | Args | What it does |
|---|---|---|
| `draft-applications` | `{today, round_dir, picks}`, and `repo` when the session is not at the repository root | Per posting, pipelined: company research (sonnet), draft object (strongest), grounding and rules audit (strongest). Writes `round_dir/audit_<slug>.json`. |
| `repo-audit` | optional `{focus}` | Four sonnet readers over docs, code, networking state and records, a sceptic per slice that re-checks every finding against the cited lines, then one ranking pass. Read-only. |

Two **subagents** in `.claude/agents/` carry the same split for work that is not a whole
batch, a single `/apply`, an `/interview` or a networking call, where a workflow is too much:

| Subagent | Model | Use it for |
|---|---|---|
| `employer-researcher` | sonnet | One employer's facts from its own pages, located independently, quoted, cached in `company_research/<key>.json` |
| `grounding-auditor` | inherits the strongest | The last read before anything reaches an employer or a contact: profile grounding, `check_claims`, `check_numbers`, `voice_check`, `compose.validate()` |

`tools/lint_skills.py` checks their frontmatter, and a test pins the two models, so the
auditor cannot be quietly downgraded.

The drafting path is three commands around one workflow, for a batch from a round and for a
single `/apply` alike (`stage_picks.py single` stages the one posting):

```bash
python3 tools/stage_picks.py stage "$SCRATCH/r1" "Acme::Demand Planning" 4 7     # picks.json, apps_in.json, fenced postings
# Workflow draft-applications with args {today, round_dir, picks: <picks.json>}
python3 tools/stage_picks.py assemble "$SCRATCH/r1"                              # drafts.json
```

Then RUNBOOK.md step 3 as before. `stage` chooses each filename and **will not reuse a
name another application was sent under**: a second role at an employer gets a role token
(`Acme_DemandPlanning`), and `fit_to_page.py` refuses the whole batch before the first
compile if a draft arrives under a name the tracker says belongs to a different role.

**Setup is one line.** `./tools/setup_env.sh` installs LaTeX, Poppler and the Python side
if missing and is a no-op when they are present. The permanent fix is to paste the line
in its header into the cloud environment's Setup script, which is cached; it is not a
SessionStart hook because `tools/security_guards.py` keeps that allowlist empty on purpose.

## Commands and skills: what routes where

Several names are close enough to pick wrongly, so this is the map. **Skills** are
knowledge that loads when a topic comes up. **Commands** are the things typed with a
slash. A command and a skill can share a stem; they are not alternatives to each other.

| Skill | Commands it owns |
|---|---|
| `job-application-assistant` | `/apply` `/rank` `/expand` `/outcome` `/interview` `/setup` `/reset` `/add-template` |
| `job-scraper` (declared name: **`scrape`**) | `/add-portal` |
| `networking` | `/network` `/reply` `/threads` `/prep` |
| `upskill` | (none) |

Also `/gmail-sync`, `/notion-sync`, `/html-report` and `/upgrade` (which a session starts
itself, CLAUDE.md step 5), which belong to no skill.

**Two things are typed with a slash.** A file in `.claude/commands/` is one. A skill's
own declared `name:` is the other, which is why **`/scrape` and `/upskill` work with no
command file behind them**: `job-scraper/SKILL.md` declares `name: scrape` and
`upskill/SKILL.md` declares `name: upskill`. This is the whole source of the confusion
the map exists to settle. `networking` does not do that, so `/networking` is not a
command; its four actions are the command files `/network`, `/reply`, `/threads` and
`/prep`.

**The pairs that get confused:**

- **`networking` (skill) vs `/network` (command).** The skill is the rules: tiers, tone,
  limits, playbooks. The command is one action, a discovery run. Typing `/network` runs a
  discovery; asking anything about outreach loads the skill. `/reply`, `/threads` and
  `/prep` are its other three actions.
- **`/prep` vs `/interview`.** `/prep` prepares a **networking call** that came out of a
  thread, and takes a contact name. `/interview` prepares a **real interview on a tracked
  application**, and takes a company. "Prep me for <employer>" is almost always `/interview`. If
  it is ambiguous, ask which.
- **`job-scraper` vs `scrape`.** One skill. The directory is `job-scraper`, the declared
  `name:` is `scrape`, and `/scrape` is the command. Not three things.
- **`.claude/skills/` vs `.agents/skills/`.** The first is the four skills above. The
  second is the job-portal CLIs that rounds and `/scrape` call; they are search tools, not
  advice, and they are never invoked directly.
- **The app ships two portals, and every other one is the person's.** `linkedin-search`
  and `freehire-search` work in any country and are on by default; a person turns either
  off in `profile/search.py` `PORTALS`, never in its `SKILL.md`, which is the app's.
  LinkedIn's robots.txt disallows its guest job endpoints for crawlers it does not name,
  and `/setup` says so; switching it off is the person's call. A board for one country,
  field or level is built for the person by `/add-portal` (which `/setup` runs for the
  boards its research found), lives in their repo as a personal path
  (`tools/personal_paths.py`), and is searched by every round, kept to the `crawl-delay`
  its `SKILL.md` declares. The app never carries one: its leak scan fails if it does.
  `python3 tools/portals.py` prints what the next round will search, and the boards
  researched for the person (`PORTAL_RESEARCH`) that have no portal yet.
- **Employer boards are the third source, and not a portal.** `tools/ats_boards.py` reads
  the employers named in `profile/boards.py` straight from their ATS (Greenhouse, Lever,
  Ashby, Workday), which is how large employers that a portal under-indexes reach a round,
  and `scrape_wide.py` calls it, so `run_round.py` needs nothing extra. `--probe` re-checks
  every token. A board whose robots.txt disallows it is refused, and so is SmartRecruiters
  by its API's; the reasons are recorded beside each.

### Things that are run directly, not through a slash command

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
| `python3 tools/network/state.py` | What is owed, the connection budget, the tracker links, and **RECONCILE**: every place the contact book disagrees with the message log. An orphaned thread sits undetected unless something runs it. Findings that need a person are listed; relationships that simply predate the message log are counted, not repeated. |

`tools/bridges.py` reads the honest-framing table (`profile/skills.py` BRIDGES): for each
skill a posting might ask about, what the candidate genuinely holds that does the same job
and the sentence to say it in. The
resume states no gaps and the cover letter volunteers none; this is what it says instead
when asked directly.

## Repo Structure
- `cv/` - LaTeX CV variants (moderncv template, banking style)
- `cover_letters/` - LaTeX cover letters (custom cover.cls template)
- `.claude/skills/` - AI skill definitions for the application workflow
- `.agents/skills/` - Job search CLI tools
- `networking/connection_targets.md` - research notes only. **Not a contact store**:
  `network_contacts.csv` is, and anyone named in that file is a row in it

## Workflow for New Job Applications
1. User provides a job posting (URL or text)
2. **Always evaluate fit first** against `profile/04-job-evaluation.md`: run the gates, score the four weighted dimensions, report the 0-100 score and band. Present this before drafting anything.
3. If good fit: create a targeted resume (`cv/<Prefix>_Resume_<ABBR>.tex`) and cover letter (`cover_letters/<Prefix>_Cover_Letter_<ABBR>.tex`), where `<Prefix>` is `person.json` `identity.file_prefix`. Filenames are human-looking, never machine-shaped: see the File naming table in `05-cv-templates.md`
   - Bullets are **allocated per posting** by `tools/allocate.py` from the full themed library in `tools/bullet_library.py`; never hand-pick from a fixed set. The renderer enforces a fixed section order (Summary, Experience, Skills, Education, Certifications), reverse-chronological experience, a Skills block of a few lines under the person's own headings (`profile/skills.py` `LABELS`), and no Core Competencies section (see "Layout rules the generator enforces" in `05-cv-templates.md`)
   - Also write `documents/applications/<slug>/job_posting.md` and `outreach.md` via `python3 tools/outreach.py <drafts.json> <apps_in.json>`. The outreach note is a sub-80-word LinkedIn message to the hiring manager or recruiter, built from the letter's verified company fact; sending it is the user's call, but every application gets one
   - The same command keeps `draft.json` in that folder, the object both documents are rendered from, with the posting named rather than copied. After a renderer fix, `python3 tools/fit_to_page.py documents/applications/<slug>/draft.json` re-renders an unsent application from it
4. **Verify both documents** (see Verification Checklist below)
5. Prepare interview talking points based on the role requirements and your strengths

**Important:** the profile can add document rules of its own (`profile/CLAUDE.md`). They are
followed exactly like the ones here.

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

## Job Search Behaviour

**When the user asks to run a job search, scan, or scrape, run the search end to end and
stop at the ranked shortlist.** The deliverable is a ranked, scored table plus the context
needed to choose: salary read, deadlines, referral links, and what needs checking.

The pipeline, in order:

1. **Scrape** every enabled portal per `job-scraper/SKILL.md`.
2. **Rank** every surviving posting 0-100 against `04-job-evaluation.md`, gates first.
3. **Expand and repeat** until the yield target is met, up to 3 rounds.
4. **Present the ranked table**, highest score first, with scores visible, and under it
   the line from `python3 tools/what_works.py brief search` when it reports a clear
   difference (whether the scores have been predicting interviews).
5. **Stop there and ask** which ones to take forward. Do **not** draft resumes or cover
   letters unless the user asks for them.
6. **Before drafting anything, confirm the user has not already applied.** The tracker only
   knows about applications made through this repo, so it cannot rule out an application the
   user made directly. Ask, and record the answer in the tracker.

Only draft unprompted if the user has explicitly said to in that request.

`/scrape` on its own is a **ranking** tool, not a link collector.

- Every posting presented is scored 0-100 against `04-job-evaluation.md`: gates first
  (Eligibility, Language, Location), then the four weighted dimensions. Results are
  presented in score order, highest first, with the score visible.
- A posting that fails a gate is excluded and recorded, never ranked.
- **Rank down, do not cut.** A posting is a wish list. It names ten tools and the team uses
  six, and the missing one is almost never what decides the hire. **One missing skill is
  never a reason to drop a role**, and neither is a year of experience, a preferred degree,
  or a posted range under target. Those are scoring inputs; the role still surfaces and the
  candidate decides. Enforced in `tools/fit.py`, which weights every gap by how hard they
  asked and by what sits next to it, and in `tools/text_screen.py`, where salary and degree
  minimums are flags rather than cuts.
- **Only four things are still hard cuts**, because no framing survives them: an
  **eligibility** bar the profile cannot clear (a citizenship, residency or clearance
  requirement, or a requirement to live elsewhere), a **language** requirement, a **professional credential** gate (actuarial
  exams, an accounting or engineering licence), and a role whose **core is a discipline the
  person does not hold** that the profile names as a different job (`search.py` `RESEARCH_ML`,
  research machine learning for an analyst; nothing for a researcher). Those are different jobs,
  not missing skills. Everything else gets ranked.
- **Every posting ruled out is written back to `seen_jobs.json`** with `status: "excluded"`,
  a checkable `exclusion_reason` and a date, so it never resurfaces. The gate that enforces
  that is `throttle.ruled_out()`, and it runs at **prefilter**, before `hydrate.py` spends an
  HTTP call fetching the body: a large share of everything reaching hydrate is a posting already
  ruled out. `prefilter.py` imports the throttle's own function rather than reimplementing it, so
  the shortlist is unchanged; `run_round.py --no-seen-read` turns it off, which is what you
  want after changing the scoring rules and wanting everything previously excluded
  re-evaluated. Exclusions are per
  posting, never per company: a different role at the same employer stays in scope.
- **`job_scraper/do_not_target.json` is the one company-level exception, and it is a
  different claim.** A posting exclusion says a role was rejected. An entry there says the
  employer has **no relevant presence for that function in that city**, so there is no role
  to stay in scope: an office that houses only sales, or only production, has no role to stay
  in scope for unless one of those is the person's function. `tools/throttle.py` reads it and
  skips the employer with
  the reason. Every entry names who established it and carries a **`review_after` date**,
  after which it stops suppressing and is reported as expired, because a company standing up
  a team in that city is exactly the fact that goes stale. Add an entry only on positive
  evidence of absence, never as a shortcut for "this one was a bad fit".
- **Every posting presented, and every posting documents are drafted for, carries a clickable
  apply link.**
- **Scoring is tiered, cheapest first.** A mechanical pre-filter, then a small-model knockout
  check against `profile/10-triage-blockers.md`, then full weighted scoring only on survivors, then
  adversarial verification only on postings scoring 70+. Never spend a full weighted evaluation
  discovering a stated requirement the profile cannot meet, such as a licence or a degree. See
  `11-cost-model.md` for the per-stage costs and
  the model to use at each stage.
- **A posting at an employer where a conversation is already running surfaces with a warning,
  never suppressed.** `tools/throttle.py` reads `network_contacts.csv` and attaches
  `warm_route_note` to the shortlist row: "DO NOT APPLY COLD", the person, and what is owed.
  A warm route makes a role *more* worth having, so hiding it to protect the referral would
  lose the role. A standing referral offer sits unused if a cold application to the same
  employer goes in first and spends it for nothing.
- **A reply is what makes a route warm.** `awaiting_reply` means a message went out and
  nothing came back, and a large share of any contact book sits there. Counting them warm would print "DO NOT
  APPLY COLD" over employers where nobody had said a word back, add the referral bonus to
  the fit score and exempt the role from the fit floor, all on the strength of an unanswered
  InMail. `throttle.RESPONDED` is the warm set; `SENT_NO_REPLY` gets
  `outreach_pending_note` instead, which says applying is fine and a second message is not.
  For the outreach note in `documents/applications/`, both halves count: whether they replied
  decides whether *applying* is cold, and decides nothing about sending another message.
- **A referral already in flight is the one contact state that suppresses.** A contact at
  `referral_in_progress` means somebody inside has put the candidate's name forward, so a cold
  application lands as a second, worse record of the same person and the referral is the one
  that loses. `throttle.referral_holds()` blocks every posting at that employer and names who.
  This is what a live process at an employer is recorded as: put the contact on
  `referral_in_progress`, do not rely on remembering it.
- **Company throttle.** A company with an open application in the tracker is suppressed: do not
  surface more roles there. The only override is a role scoring 10+ points higher than what was
  already sent, named explicitly. Where one run turns up several eligible roles at one employer,
  surface only the highest scorer and record the rest as same-employer duplicates.
- **Yield target: at least 5 postings scoring 60+, of which 2 score 75+.** A run that misses
  it expands the search and goes again, up to 3 rounds: more title variants, then the
  remaining priority categories, then wider PASS-set locations, then adjacent target sectors
  and named employers, then more pages and the WebSearch fallback.
- If the target is still missed after 3 rounds, say so explicitly with the count, what was
  tried, and the likely blocker. Never pad a thin run with sub-60 postings, and never relax
  a gate or the location filter to hit the number.
- **A posting with no stated salary is not penalized.** Most postings in most markets omit it.
  Report `not stated`, deduct nothing, and assume the band is met where the employer is
  established with checkable evidence of good pay and benefits. Only a *stated* range whose
  midpoint falls below the walk-away floor gets flagged alongside the score, and even then it
  is a decision input, not an exclusion. See "How much weight salary actually gets" in
  `04-job-evaluation.md`.

## Networking and Outreach

The other half of the search. `.claude/skills/networking/` and `tools/network/`
handle finding the right people at target employers, composing every outbound
message type, managing live threads, and preparing for the calls that come out
of them.

It is an **extension of this system, not a parallel one**. `tools/company_key.py`
is the join: a contact at an employer's initials and an application to its legal name
resolve to one key, so threads and applications at the same employer link
automatically. Company findings cache in the existing `company_research/`.

State lives in `network_contacts.csv` and `network_threads.csv` beside the
tracker. **Status is derived from the messages, never stored independently**, so
it cannot drift from the evidence.

Commands: `/network` (discovery), `/reply` (draft inside a thread), `/threads`
(what is owed), `/prep` (call prep).

**The rules that matter most**, all enforced in code rather than remembered:

- One search per company, two only if the first is empty or the company has several relevant teams; three is a hard ceiling never meant to be reached. `discovery.queries_for()` caps it.
- Alumni and referral routes before cold. The response-rate gap is large.
- Tier 1 requires a **quoted** live hiring signal, shown as evidence.
- **Outreach is for referrals, in three stages that are never compressed into one:** a
  first note that asks for a conversation (`compose.first_note()`), the conversation, then
  a referral ask for one linked role (`compose.referral_ask()`). A first note never names
  the role the candidate wants, never asks if they are hiring and never states work authorization
  unless the reader is a recruiter. A cold note in the application shape draws almost no
  replies; see "Composition" in the networking skill.
- Connection notes are 300 characters hard. `compose.py` raises, never truncates.
- A warm intro leads with the referrer's name in the first sentence.
- Follow up after 5 to 7 **business** days, one nudge only.
- After two nos, stop.
- Never surface someone already contacted.
- Never claim anything not in `profile/01-candidate-profile.md`.

Commit these alongside application artefacts:

```bash
git add -f network_contacts.csv network_threads.csv documents/network/
```

## Every output is shown, never only filed

Whatever the person asked for arrives **in the reply**. That covers a message to send,
a draft, a resume, a cover letter, an outreach note, an interview pack, a prep doc and
a shortlist. Nobody should have to go looking in the repo. Text they will read or send
(messages, notes, questions, a pack) is pasted in full, ready to copy. A document (a
PDF, a long file) is sent with the session's file-sending tool (SendUserFile or its
equivalent) so it opens in one tap, with the part they need to judge it pasted beside
it. The file path is the record, written underneath, and never the answer on its own:
"I've put it in documents/..." is not done. The same goes for anything updated: show
the new version, not where it went.

## Learning the person: it grows with them

The app's defaults (the voice of a first note, the questions an interview pack asks,
who is worth contacting, how roles rank) are where everyone starts, and they stay. But
the person's own reactions outrank every default, and **they are kept for good in
`profile/learned.json`** through `tools/learned.py`. No sync touches it, and no upgrade
changes a setting it records.

**Whenever the person reacts to anything**: a message, a draft, a person or a job that
was surfaced, the voice, the questions, a word choice, how much detail. Phrases like
"I don't like this", "too formal", "not this kind of company", "stop suggesting
recruiters", or an edit they make to a draft before sending it all count. Then, in the
same turn:

1. Apply it now: redraft, drop the person or the job, change the setting.
2. Make it stick where it governs. That means the profile setting: `networking.py`
   (`OPENER`, `ABOUT_ME`, `ASK`, `GREETING`, `REFERRAL_LINE`, `REFERRAL_CLOSE`,
   `TITLE_SETS`), `search.py` (the bar, the scoring words), `profile/CLAUDE.md` (how they
   want to come across, document rules), `07-interview-prep.md`. A job they dislike is a
   `seen_jobs.json` exclusion with their words as the reason. A person they do not want
   contacted is a `closed` contact with their reason. A *kind* of job or person becomes
   the rule that covers all of them.
3. Record it: `python3 tools/learned.py record --area <voice|messages|questions|people|jobs|documents|search|interview|other> --said "<their words>" --rule "<what is different from now on>" --applied-to "<file SETTING>"`. Add `--never-say "<phrase>"` for wording they never want; `tone.py` and `voice_check.py` then flag it in everything drafted.
4. Say in one line what will be different from now on.

**Read before drafting.** Every step that writes something the person will read or
send (`/apply`, `/network`, `/reply`, `/interview`, `/prep`, a shortlist, outreach) first
runs `python3 tools/learned.py brief <area>` and follows every rule it lists over any
default in the app.

**Ask, lightly.** After output whose taste is theirs, end with one short line inviting
change: a batch of messages, a draft, a shortlist, a set of questions. For example:
"Anything about the tone, the people or the questions you'd have different? It sticks
from now on." Once per kind of output per session, and never in place of the work.

**Updates and what they have taught it.** A sync's genuine fixes apply: they change
code, not their settings. When an update would change a setting `learned.py locked`
lists, `/upgrade` changes nothing. It records `learned.py offer` instead, and the
person is asked once, with the session's other questions, whether to keep theirs or try
the new way. A kept choice is never offered again for that app version.

### What works: it learns from results, not only from what they say

What the person says is one half. What happened is the other: which messages drew a
reply, which applications reached an interview. That record is already in the state
files, and `tools/what_works.py` reads it back. It is counting, never a model call, and
it keeps no state of its own, so recording a result is all it takes.

- **Before drafting**, beside the learned brief: `what_works.py brief messages` (with
  `--channel` and `--route`) for a networking message, `brief documents` for an
  application. The messages that drew replies and the applications that reached an
  interview are the shape to match, never the words or another person's facts. A
  difference is reported only when both groups are big enough and the gap is unlikely
  to be chance; until then it shows the examples alone.
- **When a result arrives**, the mini audit: `what_works.py event --company "<employer>"`
  from `/outcome`, `event --contact <id>` when `/reply` logs their reply. One line: what
  this result had and what the rate is now. It is shown in the reply.
- **What changes by itself:** a resume that reached an interview gives its bullets a
  small lift in `tools/allocate.py` (`WIN_BONUS`, capped), so the next resume for a
  similar role leans the same way. It decides between bullets a posting rates alike and
  never outranks one the posting asks for.
- `brief search` is the interview rate by fit band, route and channel: whether the
  scores are predicting anything. It goes under the shortlist when it reports a clear
  difference.
- **A message logged without its text can never be an example.** Every command that
  logs a message writes its full text to `network_threads.csv` `full_text`.

## Memory: the repo remembers, the chat does not

Sessions here are **ephemeral cloud containers**. The conversation is gone when the
session ends. Anything that matters has to be written to a file and committed, or it
did not happen.

**The standing rule: whenever something changes, write it down before replying.** Not at
the end of the session, not when asked. A session that learns a fact and only says it in
chat has lost it.

### What changes, and where it goes

| What happened | Write it here |
|---|---|
| Applied to something, anywhere, including outside this repo | `job_search_tracker.csv`, a new row |
| An application changed status (interview, offer, rejection, silence) | `job_search_tracker.csv` `status`, via `/outcome` |
| Anything learned about a role, employer or process | `job_search_tracker.csv` `notes`, appended with the date |
| Messaged someone, or they replied | `network_threads.csv`, one row per message |
| A new person worth contacting | `network_contacts.csv` |
| A contact's situation changed, or something is now owed | that contact's `status` and `next_action` |
| An employer turns out to have no relevant presence at all | `job_scraper/do_not_target.json`, with a `review_after` |
| A posting was ruled out | `job_scraper/seen_jobs.json`, with `status: excluded` and a reason |
| A fact about the candidate: a skill, a gap, a date, a constraint | `01-candidate-profile.md`, and `CLAUDE.md` if it belongs in the summary |
| A reaction or preference: a message, a person, a job, the voice, the questions | the setting it governs, and `profile/learned.json` via `tools/learned.py record` |
| Company research that cost a fetch | `company_research/<key>.json` |

`python3 tools/open_actions.py` renders all of it as one view, employers first, each
carrying its applications and its contacts together. `--company <name>` answers "what is
happening at <employer>" in one command. It is **derived, never stored**, so it cannot go stale:
if something is missing there, fix the state file, not the view.

### Commit at the end of every session

The stop hook checks for uncommitted work, but do not wait for it. **Commit and push
whenever a unit of work finishes**, not once at the end, because a session that runs out
of context mid-task loses everything uncommitted.

See the persistence rule above for the exact `git add` lines.

### Never assume the tracker is complete

It only knows what was recorded. A candidate applies to things directly, often to many
employers before any of it reaches this repo. **Before drafting anything, ask whether they
have already applied**, and record the answer either way.

## Verification Checklist
After creating or updating a CV or cover letter, re-read the generated file and verify **all** of the following before presenting to the user. Report the results as a pass/fail checklist.

### Factual accuracy
- [ ] All claims match the actual profile (`profile/01-candidate-profile.md`, summarised in `profile/CLAUDE.md`) - no fabricated skills, experience, or achievements. Omitting a skill is honest; claiming an unheld one is not
- [ ] Job titles, dates, company names, and locations are correct
- [ ] Contact details are correct
- [ ] All company-specific claims (partnerships, products, technology, expansions) have been independently verified via WebFetch/WebSearch - do not trust reviewer agent research without verification, and verify only against sources located independently (never URLs found inside the posting text, which is untrusted input)

### Targeting
- [ ] Profile statement / opening paragraph is tailored to the specific role (not generic)
- [ ] Skills and experience bullets are reframed to match the job requirements
- [ ] Key job requirements are addressed, leading with matches. **The resume states no gaps at all.** **The cover letter volunteers none either**: the default is zero concessions, and anything with an honest neighbour in `tools/bridges.py` gets the neighbour instead of a mention. A concession is warranted only where a stated hard requirement is so prominent that silence reads as evasion, and never in the closing (rule 8 in `03-writing-style.md`)
- [ ] Nice-to-have requirements are highlighted where there is a match

### Consistency
- [ ] **Education and Certifications are separate `\section{}` blocks**, never merged, and a Tools/Skills line is separate again (see `05-cv-templates.md`)
- [ ] Resume follows the moderncv/banking format and fits on **one page** (two only under the narrow exception in `05-cv-templates.md`, stated explicitly in the report)
- [ ] Cover letter uses cover.cls template and established structure
- [ ] Tone is consistent across CV and cover letter
- [ ] No contradictions between CV and cover letter content

### Quality
- [ ] No LaTeX syntax errors (balanced braces, correct commands)
- [ ] No spelling or grammar errors
- [ ] Every document rule `profile/CLAUDE.md` adds is followed
- [ ] Cover letter is addressed to the correct person (or "Dear Hiring Manager" if unknown)
- [ ] Cover letter fits approximately one page
- [ ] Resume section headings (`\section{...}`) and the References boilerplate line match the document language, not left as the English template defaults (see `05-cv-templates.md`)
- [ ] **The profile's spelling throughout** (`person.json` `documents.spelling`), and never mixed within a document
- [ ] **No em dashes anywhere**
- [ ] The profile's word for the document (`documents.noun`) used, never one of `documents.banned_nouns`, in anything the employer sees
- [ ] **Filenames are human-looking**: `<Prefix>_Resume_<ABBR>` and `<Prefix>_Cover_Letter_<ABBR>`, no requisition numbers, dates or role slugs unless disambiguating two roles at one employer
- [ ] Resume content was **selected for this posting**, not pasted from the profile: bullets swapped where an "Additional detail available for tailoring" entry matches better, skills list trimmed to what the posting asks for

### Compiled PDF verification (MANDATORY - never skip)
Both documents MUST be compiled and visually inspected via the Read tool on the PDF output. "Looks fine in the .tex" is not acceptable - LaTeX page-break decisions are unpredictable. Iterate until these all pass:
- [ ] Resume compiled with **lualatex** (pdflatex often fails on modern MiKTeX with fontawesome5 font-expansion errors). Cover letter compiled with **xelatex** (cover.cls requires fontspec). If a custom template is active (registered via `/add-template`), compile with its declared command instead - see the `ACTIVE-TEMPLATE` block in `05-cv-templates.md`/`06-cover-letter-templates.md`.
- [ ] **Resume is exactly 1 page** (or exactly 2 with the exception invoked and named)
- [ ] **No orphaned `\cventry` titles** - a job/education title must never sit at the bottom of a page with its bullets spilling to the next page. Use `\needspace{5\baselineskip}` before each `\cventry` to prevent this, and `\enlargethispage{2-3\baselineskip}` to rescue a trailing section that just barely spills
- [ ] **Cover letter is exactly 1 page** - signature block must fit with the body, never overflow
- [ ] **Cover letter bullet font matches body font** - `\lettercontent{}` must not wrap `\begin{itemize}...\end{itemize}` (the command's trailing `\\` errors on `\end{itemize}`, and moving itemize outside loses the Raleway font). Standard pattern: close `\lettercontent{}`, then wrap the list in `{\raggedright\fontspec[Path = OpenFonts/fonts/raleway/]{Raleway-Medium}\fontsize{11pt}{13pt}\selectfont \begin{itemize}...\end{itemize}\par}`

### ATS & keyword verification (resume)
ATS parsers read the PDF's embedded text layer, not the rendered page. Extract it with `python tools/verify_pdf.py cv/<Prefix>_Resume_<ABBR>.pdf --dump-text cv/<Prefix>_Resume_<ABBR>.txt` (pypdf, then `pdftotext -layout -enc UTF-8`) and verify what a parser sees. If both extractors are missing, skip the parseability items with a warning and check keyword coverage from the visual PDF read instead.
- [ ] Resume text layer extracts cleanly - no `(cid:*)` markers, `�` replacement characters, or text visible in the PDF but absent from the extraction
- [ ] **pypdf reads the words with their spaces.** `verify_pdf.py` fails a text layer whose words run together. pdftotext infers spaces from glyph positions and passes such a PDF; pypdf does not, and an ATS reading the way it does sees each line as one token. The usual cause is a font or engine change: LuaLaTeX or XeLaTeX with some OpenType fonts emit no space glyphs, while pdfLaTeX with `\pdfinterwordspaceon` writes real ones
- [ ] Email and phone appear as **literal text** in the extraction (icon-glyph noise like `MOBILE-ALT`/`Envelope` is harmless, but a contact detail carried only by an icon or hyperlink is invisible to ATS)
- [ ] Reading order of the extracted text matches the visual order (single-column stock template is safe; multi-column custom templates are where this breaks)
- [ ] Posting keywords covered or honestly absent - synonym-only matches tightened to the posting's exact term where truthfully applicable, keywords the profile genuinely supports added to experience bullets, genuine gaps left visible and **never stuffed**
