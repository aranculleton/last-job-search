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

`profile/01-candidate-profile.md` is the source of truth for every fact about them. A claim
is **grounded** when a file `person.json` `grounding.sources` names carries it: by default
`01-candidate-profile.md`, the summary above and `bullets.py`, the set `tools/check_numbers.py`
reads. An older resume, a tailored draft or the chat is never a source until the fact is
written into `01`. The summary is a working copy for quick reference; where the sources
disagree, `01` wins, and the disagreement is a bug to report and fix rather than a choice to
make. The rest of
`profile/` is the same person in the form the tools read (`person.json`, `roles.py`,
`bullets.py`, `skills.py`, `search.py`, `employers.py`, `boards.py`, `networking.py`,
`claims.py`, `screening.py`) and the documents written from it: `02-behavioral-profile.md`,
`04-job-evaluation.md`, `10-triage-blockers.md`, `12-scoring-brief.md`, `13-positioning.md`.
If there is no `profile/`, nothing here can run: start with `/setup`, once `python3
tools/place.py state` says there is none anywhere (start of every session, step 3).

## Start of every session

This repo is either **the app** (`github.com/aranculleton/last-job-search`, public, no
`profile/`) or **a person's repo**, made from the app with "Use this template" and private.
Every session in a person's repo starts with the same five steps, before anything else:

1. **Pull master**: `python3 tools/sync_app.py --pull`. Another chat may have merged since
   this container was built. It never merges a master whose history was rewritten (the fetch
   says "forced update"), which conflicts on hundreds of files: a branch with nothing of its
   own moves to the new master, and one with commits of its own stops, names them and gives
   the command that carries them across. Exit 1 means it stopped with nothing changed: do
   what it printed before anything else.
2. **Take the app's updates**: `python3 tools/sync_app.py --on "<this session's model>"
   --tools "<the browser tools this chat has: browser, chrome, enable, or none>"`. It
   fetches the app and merges what is new (the newest release; the maintainer's own copy takes
   master), never sends anything back, and ends with the day's model check: what this model
   suits and what wants another, which goes first in the reply when the person's request is
   one of the latter. Then the place check (`tools/place.py`), once a chat (weekly only while a computer lacks a tool): when this chat
   cannot do what the person set up (profiles read in their browser, from a chat with no
   browser of theirs; tools missing on their computer), it prints what to tell them, which
   goes at the end of the reply in its own words: two or three short sentences, and the
   dated steps only if they ask how (`place.py how`). It offers a choice and never makes it.
   The set-up it recommends to anyone with a computer is two chats: one on their computer
   for everything they do, networking included, and the brief in the cloud (`place.TWO_CHATS`).
   In the maintainer's own repo the sync also checks the public app for their names
   (`tools/app_watch.py`): an `APP LEAK` line goes first in the reply, before anything else. The app is public, so nothing needs attaching; if it still cannot reach
   it (exit 2), attach it read-only with `add_repo` (owner and repo from the URL
   `https://github.com/aranculleton/last-job-search`, `access="read"`) and try once more, and if
   that fails too, say so in one line and carry on. Exit 1 means it stopped with nothing
   changed: do what it printed yourself (commit the work it lists, carry across what it
   names) and run it again. Never put it to the person: saving and updating are always yes.
3. **No `profile/`?** First `python3 tools/place.py state`, before anything is asked: another
   chat may hold the profile on master or on a branch it has not landed (it brings it in and
   the search is set up), or still be writing it (say its one line and start nothing). Only
   with none anywhere, start `/setup`. **A profile here is never set up again** (that is
   `/reset`): in a chat on their computer it is "Your search is already set up; this computer
   is ready for it too.", and nothing is asked, least of all a resume.
4. **If the sync brought changes**, say in one plain line what changed for them, from the
   lines it printed under "What changed": never a file, a command, a version or a git word.
5. **Profile upgrades apply themselves; nobody has to ask.** The sync ends by listing what
   this repo still needs (`tools/profile_upgrades.py`): parts of the app that switched on
   after this person set up (their job boards researched and built, a setting written for
   their field, a portal rebuilt), and facts in the profile still marked `[CONFIRM: ...]`.
   The person will not know which ones matter, so never offer them a list or wait for a yes:
   - **What Claude can do alone** ("Claude applies these itself"): start a background agent
     at once (Agent tool, `run_in_background: true`, `isolation: "worktree"`) running
     `/upgrade`, and go on with what the person asked. Their request never waits for it.
     When it reports, merge its branch into this session's work, then run `python3
     tools/network/state.py follow-ups --write`: it worked from an older copy of the messages.
   - **At the end of your reply**, one plain line per change it made for them, and nothing
     about commits or commands: if they want one undone, undo it yourself (`git revert`).
   - **What needs the person** ("These need you", unconfirmed facts): ask at most three,
     at the end of the session, never at the start, **each as its short plain question
     first**, as the sync prints it. Detail comes only after a yes (its steps) or a "why?"
     (one sentence), both in `profile_upgrades.py --plan`; a no gets one line, "No problem,
     I'll ask again in a month.", and `--no <id>` records it. Never paste a long block, an
     id, a version number or the word "upgrade". Write each answer where its marker was and
     commit it. The rest wait for the next session.
   If the sync printed nothing about upgrades (its first run after this arrived is the old
   copy), run `python3 tools/profile_upgrades.py` yourself and do the same.
   - **One chat per update.** When the sync says the upgrades belong to another chat, start
     nothing and ask nothing about them, and follow what it prints; when the person says no
     other chat is open, `python3 tools/profile_upgrades.py --take` hands them over. The chat
     that brought an update in lands that sync on master promptly, before its other work.

**A chat that carries on for days does this every day, not once.** Most people keep one
chat going, so "the start of a session" may be days ago. Before each new piece of work (a
search, an application, outreach, a reply, interview prep), run
`python3 tools/sync_app.py --if-stale --on "<this session's model>" --tools "<...>"`. When today's check has
not run, it does steps 1 and 2 (master, then the app) and the rest follows as above;
otherwise it prints "already checked today" and changes nothing. `run_round.py` and `stage_picks.py` print a reminder
when it was skipped, and that reminder is code, so it reaches a chat whose instructions
were loaded before this rule existed.

In the app itself, step 2 is a no-op and step 3 does not apply: the app has no profile and
must never get one.

## App-owned files and personal files

`tools/personal_paths.py` is the line. Everything it lists (the profile, the tracker, the
contact book and threads, documents, research) is the person's; everything else is the app's.

- **In a person's repo, never edit an app-owned file.** The next sync puts it back to the app's
  version and says so. A fix or a feature the app needs is made in the app (below) and arrives
  here through the sync. If the person is not the app's maintainer, never tell them the app
  has a problem or ask them to report one: do what they asked the best honest way the app
  allows, and say plainly only what could not be done for them.
- **A person's own tests (`profile/tests`) use the app's public names only.** A name that
  starts with an underscore, and anything inside `tools/openroles/`, can change in any
  release; a job board is faked through `tools/offline_boards.py`. **When they fail after an
  update**, `python3 tools/sync_app.py --own-tests` says which, why (a part of the app the
  update removed, or behaviour it changed) and what to do; the sync and `ci_local.sh` print
  it by themselves. Bringing them in line is Claude's job, done in the same turn and committed
  with the sync's work: never a question or a to-do for the person, who hears one plain line at
  most. RUNBOOK.md, "Your own tests fail after an update", has the steps.
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
`tools/robots_check.py` does), which target employers post on a hiring system openroles
reads (Greenhouse, Lever, Ashby, Workday, Personio, Teamtailor and the rest:
`tools/ats_boards.py --find` tries them all) or on a careers site that publishes its jobs for
search engines (probed the way `tools/ats_boards.py --probe` does), the eligibility and visa wording
postings in their country use, salary norms for their role and city, local document
conventions (resume or CV, page length, spelling), and the market's place names. Everything
researched is cited and stored in `profile/`.

**And it keeps going without being asked.** When a round comes back thin, a good posting
arrives from a board that is not covered, an employer they mention has no board on file, or a
gate cuts something it should not for their market, propose the fix, do the research, and
record it in `profile/`.

## Developer rules: changing the app itself

**Before changing any app-owned file, read `MAINTAINING.md`, "Developer rules"**, whichever
repo the session started in. In short: Claude's own documentation and similar projects on
GitHub are looked at first, unasked, for every question, fix, feature and release; the
change is made in the app, on a branch, and merged
with CI green; the leak scan passes on the exact tree before anything is pushed, because the
app is public and so are its branches and history; no example is a disguised person, and a
real person a run turns up is described, never named, in code, commits or PR text
(`tools/name_guard.py`); a change
an existing user would have to act on is a profile upgrade (`tools/profile_upgrades.py`); and
a change to a part of the build that leaves something behind is a new version in
`tools/build_versions.py`. Tests fail on the last two.

## Master is the trunk. Finish on it, start from it.

Several Claude chats run against this repo, each one in its own container, each one
handed its own branch. That works only if every branch lands on master before its
session ends: a chat that starts from master cannot see work sitting on another chat's
branch, and builds it a second time.

So, every session:

1. **Start by pulling master and taking the app's updates** ("Start of every session"
   above). Another chat may have merged since this container was built. Do this before
   writing anything, not before pushing.
2. **Finish by getting the work onto master.** Not "pushed to the branch": on master.
   Open the pull request, run `./tools/ci_local.sh --quick`, merge it. A branch left behind at the end of a
   session is work the next chat cannot see and will duplicate.
3. **Never leave a merged branch around**, and never start new work on an old one.
4. If the work genuinely is not finishable this session, push it, and say in one plain line
   that it is not finished and the next chat carries on. The next chat finds it itself
   (`git branch -r --no-merged origin/master`); the person is never given a branch name.

**Two chats changing the same state file is not a conflict to resolve by hand.** The
tracker, the contact book, the message log and `seen_jobs.json` merge row by row
(`tools/merge_state.py`, which every sync wires into git): rows either side added are both
kept, and notes both sides added are both kept. Where both sides changed the same field of
the same row, the later change is kept by itself, and the merge says which and what the other
side had: tell the person in plain words which answer was kept and what the other said, since
their word outranks it. Git stops only where neither change is
later. Before
merging a pull request, `git fetch origin master` and then `git merge origin/master`, each a
command of its own, so that merge
happens in the container, where the driver is set, and not on GitHub, where it is not.

**On the person's own computer** a chat has no GitHub tools and lands its work with `gh`.
**The first chat on a computer works in the copy itself**, the folder COMPUTER.md made; **a
second chat open there at the same time works in a folder of its own, made before any other
work** (`python3 tools/sync_app.py --worktree <name>`): two chats in one folder switch
branches under each other. RUNBOOK.md step 4 has the commands, how to tell a merge worked, and what
to do when the desktop app refuses one. **Each runs as a command of its own, the merge above
all, never chained**: a chain with one part the app has not pre-approved sends the whole of
it, merge included, to auto mode's own check, which refuses the merge.

The one thing that is **not** negotiable in the other direction: do not push to master
without CI green. It is the branch every other chat starts from, so a broken master
breaks all of them at once.

**On a private repo, green is established locally, and that is the rule:
`./tools/ci_local.sh --quick`** (it skips only the compile of the app's example documents,
which a person's repo never edits; the full run is for a change to the app). A clean run is the evidence and
merging on it is allowed; say so in the PR and name anything it reported as SKIP. Why, what
CI's Python 3.9 leg is for, and the one case worth a billed CI run: `MAINTAINING.md`, "CI on
a private repo". Batch the commits and push once, when a unit of work is finished.

## Persistence rule for a person's repo (deviates from upstream)

A person's repo is **private** and the search runs in ephemeral cloud sessions, so nothing
persists unless it is committed, and the state is committed there. (Upstream's "never commit
the tracker" rule is for public forks. The app itself holds none of it, and its CI fails on a
personal path.) **Do not edit `.gitignore`**: `tools/security_guards.py` enforces it in CI.
Force-add the specific artefacts instead. At the end of any session that produced work,
`python3 tools/save_state.py` stages them (`--list` says what, and stages nothing). It is
the rule as code, so it works in any shell: the loop it replaced stopped under zsh, the
Mac's own shell, on the first pattern that matched nothing, before staging anything.

What it stages: `profile` and `networking` with a plain `git add`, never `-f`, which would
force in the caches under `profile/tests/`; and, forced in path by path because they are
ignored, the tracker, `network_contacts.csv`, `network_threads.csv`,
`job_scraper/seen_jobs.json` and `do_not_target.json`, `documents/cv`, `applications`,
`network`, `rounds` and `interview`, each application's resume and letter in `cv/` and
`cover_letters/`, `company_research/*.json` (it costs a fetch to rebuild) and
`upskill/*.md`. `documents/rounds/<round>.json`, each round's top 60 without the posting
bodies, sits outside the ignored `rounds/` on purpose. `network_threads.csv` is the file that
must never be lost: status is derived from it, and without it every contact reverts to
`not_contacted` and the same people get messaged twice. **Build noise is never staged**
(`*.aux`, `*.log`, `*.out`, `*.fls`, `*.fdb_latexmk`, `*.synctex.gz`, `cv/*.txt`,
`__pycache__/`, `.pytest_cache/`), nor `salary_data.json` (licensed third-party data).

## Environment notes for cloud sessions

- **`./tools/setup_env.sh` sets the container up**: LaTeX and the Python side, one
  package at a time, and a no-op when they are present. The line in its header, pasted into
  the cloud environment's setup script (where: `python3 tools/claude_surfaces.py say
  cloud-environment`), caches it. It is not a SessionStart hook, on purpose:
  `tools/security_guards.py` keeps that allowlist empty. SETUP.md, "A. Fresh cloud
  container", says why each piece is there and what its errors mean (`File fontawesome5.sty
  not found` is an unset `TEXMFHOME`; a pyo3 panic from `verify_pdf.py` is a broken `cffi`).
- **A job board the session cannot reach** may be blocked by the chat's cloud settings: check
  `curl -sS "$HTTPS_PROXY/__agentproxy/status"` for `connect_rejected`. That is a policy
  denial, not a bug: do not route around it. Tell the person what `python3 tools/env_check.py
  --say` prints, word for word (a round prints the same under "Tell the person"): one
  recommended fix in numbered steps, which reaches the running chat within about a minute.
  The day's sync checks it and prints the same words first. Until it is fixed, run no search:
  a web search in its place finds old, closed jobs. `/apply <pasted posting text>` still works.

## Automation: what runs without anyone asking

**`automation/README.md` is the whole story; `profile/routines.json` is the registry**, and
when the tasks run and where they report is the person's (the automation section of
`profile/CLAUDE.md`). The default is one task, **a brief twice a week** that also takes the
app's updates; a scheduled job round is optional and off by default, since "find me jobs"
runs one in any chat. Two set-ups work, and the README walks a person through either: **(a)**
one chat per task, each task bound to its own chat, whose reply is the briefing; or **(b)**
each task made as a routine with the repo ticked, every run a new chat. Each task's stored prompt is a stub
that reads `automation/prompts/_common.md` and its own file from master, so **changing what a
task does is a normal PR**; only a schedule change needs `update_trigger` or the routine's
own page. The final reply is the message; nothing depends on `fire_trigger`. An older
shared-chat set-up that relays to the phone through a fresh-session task still works only
from a chat made before 14 October 2026: never archive, delete
or rebuild one, and never test a chat-bound task with `fire_trigger` (use a one-off
`run_once_at` task bound to the chat). `python3 tools/routines.py check` validates the
registry.

**"Set up my brief" is set-up (a) in `automation/README.md`, and `/setup` does it at its end,
asking nothing.** First list the account's scheduled tasks (`list_triggers`, every page) and
run `python3 tools/routines.py brief --triggers <each page>`: a brief that exists, whatever it
is called, is attached to and never made twice, and a task that only looks like one is asked
about. The brief always runs in the cloud. **In a cloud chat** with none, `brief` prints the
calls to make, in order: `create_session` on the person's private repo, titled "Job search:
morning brief" and with no prompt; `create_trigger` bound to that chat
(`persistent_session_id`), `CRON_TZ=<their zone> 38 7 * * 1,4`, the stub as its prompt,
`connectors: []`; and a one-off `run_once_at` first brief bound to the same chat, never
`fire_trigger`. Then `routines.py record`, and land it. A chat told "Set up my brief in this
chat" binds the task to itself the same way. **On their computer**
(`python3 tools/claude_surfaces.py show <id>` for remote-trigger, routines-cloud,
routines-local and cli-cloud): with the `RemoteTrigger` tool, make it yourself as (b), on the
private repo, the stub as its prompt, notifications on, recorded as `routines_screen`;
without it, give them once the steps `claude_surfaces.py steps routines-cloud` prints. Never
start a cloud chat from your own shell (cli-cloud: the command refuses a shell that is not an
interactive terminal, which yours is not), and never make a desktop scheduled task for the
brief (it runs on the computer). The lines `routines.py brief` prints are for you: act on
them, and tell the person only the one line it gives ("Your brief is set up: Mondays and
Thursdays at 7:38, ..."), never its file, id or task name. (b) is also for someone who would
rather have each run arrive as a new chat and a notification.

**Silence is the alarm**: the brief is delivered on each of its days even when nothing is
due, so one of those mornings with no brief means the automation is broken; `automation/README.md` has the set-up
steps if a chat or a task is lost.
**Every dated follow-up is automatic by construction**: the brief reads `next_action_due` from
`network_contacts.csv` and the nudge schedule from the tracker, so a reminder is a date
written into a state file, never another routine.

## Orchestration: workflows and model choice

**Which model, and how hard it thinks.** The day's sync prints the check (step 2, `--on`).
For one piece of work, `python3 tools/model_guide.py <command or kind of work> --on "<this
session's model>"` prints nothing when the model fits; otherwise its one line goes first in
the reply, and the work carries on. `--all` prints the whole table for anyone who asks.

Inside the work, models are pinned per stage to `11-cost-model.md`: reading and fetching go
to sonnet, and anything that could put a false claim in front of an employer runs on the
session's own model and is never downgraded. Two saved workflows in `.claude/workflows/` are
run by name with the Workflow tool:

| Workflow | Args | What it does |
|---|---|---|
| `draft-applications` | the contents of `draft_args.json` (`{round_dir, pack, pack_hash, picks}`) plus `{today}`, `only` (slugs) to leave out roles the person drops, and `repo` when the session is not at the repository root | Per posting, pipelined: company research (sonnet), one drafting call from the pack, the code audit, then the model audit of one small packet for every draft that will be sent (the session's own model). Writes `draft_<slug>.json` and `model_audit_<slug>.json`; `stage_picks.py audit` writes `audit_<slug>.json`. |
| `repo-audit` | optional `{focus}` | Four sonnet readers over docs, code, networking state and records, a sceptic per slice that re-checks every finding against the cited lines, then one ranking pass. Read-only. |

Two of the **subagents** in `.claude/agents/` carry the same split for a single `/apply`, an
`/interview` or a networking call, where a workflow is too much:

| Subagent | Model | Use it for |
|---|---|---|
| `employer-researcher` | sonnet | One employer's facts from its own pages, located independently, quoted, cached in `company_research/<key>.json` |
| `grounding-auditor` | none set: the session's own | The last read before anything reaches an employer or a contact: profile grounding, `check_claims`, `check_numbers`, `voice_check`, `compose.validate()` |

`tools/lint_skills.py` checks their frontmatter, and a test pins the two models, so the
auditor cannot be quietly downgraded. The drafting path is five commands around one
workflow, for a batch from a round and a single `/apply` alike (`stage_picks.py single`
stages the one posting):

```bash
python3 tools/stage_picks.py stage "$SCRATCH/r1" "Acme::Demand Planning" 4 7     # picks.json, apps_in.json, fenced postings
python3 tools/stage_picks.py consent "$SCRATCH/r1" acme --yes Looker --no Spark   # the person's answers
python3 tools/draft_pack.py build "$SCRATCH/r1"                                  # pack.md, draft_args.json
# Workflow draft-applications, args: draft_args.json plus {today} ("only": [slugs] for roles dropped)
python3 tools/stage_picks.py audit "$SCRATCH/r1"                                 # both audits, the record that counts
python3 tools/stage_picks.py assemble "$SCRATCH/r1"                              # drafts.json
```

Every draft that will be sent gets both audits; a draft the code audit alone passed is
never assembled.

**A skill a posting names that the profile does not hold is the person's call, every time**:
`stage` prints one short question per pick, asked as written, `consent` records each answer,
and the workflow drafts nothing and `assemble` assembles nothing while a question waits.
`/apply` Steps 1c and 2 have the rest: a skill the question missed, what a yes puts on the
page, and a general yes written into the profile in the same turn.

Then RUNBOOK.md step 3. `stage` **never reuses a name another application was sent under**:
a second role at an employer gets a role token (`Acme_DemandPlanning`), and `fit_to_page.py`
refuses the whole batch if a draft arrives under a name that belongs to a different role.

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

Also `/html-report` and `/upgrade` (which a session starts itself,
CLAUDE.md step 5), which belong to no skill.

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
  thread, and takes a contact name. `/interview` prepares a **real interview**, and takes a
  company: on a tracked application, or on a process with no application at all (a referral
  that led to a recruiter's call; `interview_pack.py process` registers it). **A recruiter
  screen on a live hiring process is an interview stage**, referred or not, so it is
  `/interview`. "Prep me for <employer>" is almost always `/interview`. If it is ambiguous,
  ask which. Each process keeps one living document, `interview_prep.md` in its folder,
  updated in place and sent again on every change.
- **`job-scraper` vs `scrape`.** One skill. The directory is `job-scraper`, the declared
  `name:` is `scrape`, and `/scrape` is the command. Not three things.
- **`.claude/skills/` vs `.agents/skills/`.** The first is the four skills above. The
  second is the job-portal CLIs that rounds and `/scrape` call; they are search tools, not
  advice, and they are never invoked directly.
- **Portals and employer boards.** The app ships `linkedin-search` and `freehire-search`; a
  person turns either off in `profile/search.py` `PORTALS`, never in its `SKILL.md`. Every
  other board is the person's, built by `/add-portal` into their repo. Employer ATS boards
  (`tools/ats_boards.py`, named in `profile/boards.py`) are a third source;
  `ats_boards.py --find "<Employer>"` finds a board, through the vendored
  [openroles](https://github.com/aranculleton/openroles) in `tools/openroles/` (never edited
  here). `python3
  tools/portals.py` prints what the next round searches; the rest is in the job-scraper skill.

**Tools run directly, not through a slash command**: `run_round.py`,
`stage_picks.py`, `verify_batch.sh`, `record_drafts.py`, `open_actions.py` (`--due`,
`--company`), `followups.py` (`--close-quiet`), `what_works.py`, `interview_pack.py`, `bar.py`, `network/state.py`, `network/reading.py`,
`network/prep.py --all`, `network/profile_facts.py` and `bridges.py`. What each does, its flags and its exit
codes are in RUNBOOK.md, "Tools run directly". `run_round.py` exits 0 when the yield target is
met, 2 when it is missed (a thin market) and 1 when a stage broke.

## Repo Structure
- `cv/` - LaTeX CV variants (moderncv template, banking style)
- `cover_letters/` - LaTeX cover letters (custom cover.cls template)
- `.claude/skills/` - AI skill definitions for the application workflow
- `.agents/skills/` - Job search CLI tools
- `networking/connection_targets.md` - research notes only. **Not a contact store**:
  `network_contacts.csv` is, and anyone named in that file is a row in it

## Workflow for New Job Applications
1. User provides a job posting (URL or text): `/apply` takes it from there.
2. **Always evaluate fit first** against `profile/04-job-evaluation.md`: run the gates, score the four weighted dimensions, report the 0-100 score and band. Present this before drafting anything.
3. If good fit, and they say to: one application and a batch take the same pipeline (`/apply` Step 2; RUNBOOK.md steps 2 to 4). Bullets are **allocated per posting** by `tools/allocate.py`, never hand-picked; the renderer enforces the layout (`05-cv-templates.md`, "Layout rules the generator enforces"); filenames are human-looking (`<Prefix>_Resume_<ABBR>`, the File naming table in `05`); every application gets an outreach note and a kept `draft.json` (`tools/outreach.py`); and a finding is fixed in the draft object, never by hand in the `.tex`.
4. **Verify both documents** (the Verification Checklist, below)
5. Prepare interview talking points from the role's requirements and the person's strengths (`/interview`)

**Important:** the profile can add document rules of its own (`profile/CLAUDE.md`). They are
followed exactly like the ones here.

**A resume for somebody other than the candidate**: the repo has no pipeline for it. Read
RUNBOOK.md, "Documents for someone else", before starting.

## Job Search Behaviour

**When the user asks to run a job search, scan, or scrape, run the search end to end and
stop at the ranked shortlist.** Scrape every enabled portal; rank every surviving posting
0-100 against `04-job-evaluation.md`, gates first; expand and repeat, up to 3 rounds, until
the yield target is met (at least 5 postings at 60+, 2 of them 75+); then present the ranked
table, highest first, with the scores, the salary read, deadlines, referral links, a
clickable apply link on every row and what needs checking. **Stop there and ask** which to
take forward: draft nothing unless that request asked for it, and before drafting anything,
ask whether they have already applied and record the answer, and ask the skills question
staging prints (above).

**Rank down, do not cut.** The hard cuts are only the ones no framing survives, each cut on
a quoted sentence: an eligibility bar the profile cannot clear, a language requirement (or a
title written in another language), a location the profile's Location table fails, a
professional credential gate, a role whose core is a discipline the person does not hold, a
posting open to existing staff only, a stated pay range whose top is below the person's cut
line, and a knockout on their own triage card. The job-scraper skill says what each one
means. A missing skill, a year of experience, a preferred degree or a
posted range under target is a scoring input, and a posting with no stated
salary loses nothing. Never pad a thin run with sub-60 postings, and never relax a gate or
the location filter to hit the number; say what was tried instead. **The rules every search
keeps, and why** (exclusions written back, the do-not-target list, warm routes and referrals,
the company throttle, salary, tiered scoring): the job-scraper skill, which loads with
`/scrape`. Read that section before running or presenting a round by hand.

## Networking and Outreach

The other half of the search: finding the right people at target employers, composing every
outbound message, managing live threads and preparing for the calls that come out of them
(`.claude/skills/networking/` and `tools/network/`; commands `/network`, `/reply`, `/threads`,
`/prep`). It is an **extension of this system, not a parallel one**: `tools/company_key.py`
joins a contact at an employer's initials and an application to its legal name into one key,
and company findings cache in the existing `company_research/`.

State lives in `network_contacts.csv` and `network_threads.csv` beside the tracker, committed
by the persistence loop above. **Status is derived from the messages wherever the log can know
it**, so it cannot drift from the evidence. What the log cannot know (a call booked, a
referral in flight, a conversation gone cold, a close) is stored on the contact row by
whoever learns it, and wins over the log.

**Every networking rule is in the networking skill, and enforced in code**: the search budget
(`tools/network/sources.py`), alumni and referral routes before cold, tier 1 only on a quoted
live hiring signal, reading each person before writing to them (`reading.py`, `/network`
step 5), who reads a message and what it may say (`compose.READER_TYPES`), `compose.advise()`,
warm intros, the follow-up cadence, when to stop, and never surfacing someone already
contacted. Load the skill before any outreach. What a session needs before it does:

- **Nobody is shown as someone to write to without the one check**:
  `python3 tools/network/surface.py` (`surface.check()`; `--file` for a list made any other
  way). It reads the contact book, their whole thread on every channel and the bar, and
  prints NOT with the reason for anyone not to show. Never join files or check people by hand.

- **Outreach is for referrals, in three stages never compressed into one:** a first note that
  asks for a conversation (`compose.first_note()`), the conversation, then a referral ask for
  one linked role (`compose.referral_ask()`).
- **Who reads a first note decides what it says** (`compose.READER_TYPES`, each a setting in
  `profile/networking.py`): a recruiter may be told the role wanted and the person's work
  authorization, a decision-maker the role wanted (their work authorization once the messages
  the person approves say it), and a decision-maker gets the open ask ("anything coming
  up"); asking whether they are hiring, or for a referral, is a recruiter's alone; a peer is
  told neither unless that message asks.
- Before a draft is shown, `compose.advise()`: the draft is rewritten on its warnings first,
  and a warning the rewrite leaves standing is shown with the draft for the person to decide,
  never in place of the rewrite.
- Connection notes are the plan's limit, 200 characters on a free LinkedIn plan and 300 on
  Premium (`schema.LIMITS`, from `LINKEDIN_PLAN`), hard: `compose.py` raises, never truncates.
- No LinkedIn profile is ever fetched from a session, and LinkedIn's job search **stays on**:
  only the person switches it off, never a session.
- **A chat on the person's computer** starts with the networking skill's "On a new computer"
  step (`reading.py new-computer`): LinkedIn signed in, then its download, unprompted.
- Never claim anything not in `profile/01-candidate-profile.md`.
- **A LinkedIn download the person gives is taken first**, before anything is written from it:
  `python3 tools/network/export.py take <the ZIP or its folder>` saves it and imports its
  message history in one step. Never read its files straight from where it was downloaded.
- A resume sent to a contact is logged with its file (`state.py message <id> --attached <file>`).
  One made for them is staged with `stage_picks.py --for-contact <id>`, and RECONCILE says
  where the two disagree, because the chat that logs the ask and the chat that drafts the
  resume are often two chats at once.

## A step on another company's site is checked before it is given

Steps that name LinkedIn's, GitHub's or Claude's own screens come from
`tools/claude_surfaces.json` (`claude_surfaces.py steps <id>`). Each carries the day it was
checked and its official page, for you and never the person: `steps` and `say` print them on
stderr, and `show <id>` prints the quotes. Before giving one, check that page that day: a web search for
linkedin.com, which no session fetches, and a fetch for the rest. Where the page says
something else, give what it says and fix the entry. Where it cannot be checked, say "I could
not check this today" and keep the step short. Never pass on a step about another site from
memory: a LinkedIn path given unchecked sent a person to an option LinkedIn no longer offered.
A screen name written outside the registry fails `tests/test_claude_surfaces.py`.

## Every output is shown, never only filed

Whatever the person asked for arrives **in the reply**. That covers a message to send,
a draft, a resume, a cover letter, an outreach note, an interview pack, a prep doc and
a shortlist. Nobody should have to go looking in the repo. Text they will send
(messages, notes, questions) is pasted in full, ready to copy. A document (a PDF, a pack,
a prep, a long file) is sent with SendUserFile so it opens in one tap (`display:
"render"` for a pack or a prep), with the part they need to judge it pasted beside it (a
pack's one screen), under a name that says whose it is: a prep document is sent as the
copy `python3 tools/shown.py <file>` makes ("Acme Analyst interview prep.md", never
"prep.md"), which the prep tools print as `send:`. **Where the chat has no SendUserFile**
(Claude Code's tools reference lists it for a cloud chat, and for a chat on a computer only
while it is steered from claude.ai or the phone: `claude_surfaces.py show remote-control`), paste
that one screen and write the copy's full path on a line of its own: in the desktop app a
path in the chat opens when clicked. The file path is the record, written underneath, and
never the answer on its own: "I've put it in documents/..." is not done. The same goes
for anything updated: show the new version, not where it went.

**Applications, one or a batch, are delivered one way** (2026-10-23):

1. **Per role, one file-sending call** holding that role's resume and cover letter
   together, captioned: role, employer, pay (or "pay not stated"), location, apply link.
   With no SendUserFile in the chat, the caption's line and the two files' full paths,
   one a line, in its place.
2. **Then one index table in the reply**: role | apply link, the full web address, one row
   per role. Beside it, what they need to judge each one without opening anything (the
   outreach note, the screening answers to decide).
3. **No markdown link to a file in the repo**, in a table or anywhere: a relative link
   such as `[resume](documents/...)` does not open from the desktop app. Claude's
   desktop docs say a file's path written in the chat opens when clicked, so each path is
   written underneath as plain text, as the record.

Never one caption listing every file, never a table of file links, and never one
message per role in place of the index.

## Talking to the person: plain words, one recommendation, short

Most people using this have never used a terminal, GitHub or a cloud setting, and a message
they cannot act on is one they did not get. Everything said to them:

- **Plain English.** No word they would have to look up: not environment, repository,
  branch, worktree, proxy, domain, allowlist, CLI or config. Where a screen itself uses such
  a word, quote its button and say in a few words what it is for (the settings of the cloud
  computer this chat runs on, say).
- **One recommendation.** Where there is a choice, say which you recommend and why, in a
  sentence. The other options only if they ask.
- **Clear steps.** One action a line, numbered; for another company's screens, the steps
  `python3 tools/claude_surfaces.py steps <id>` prints.
- **Short.** A few lines. Reasons, detail and alternatives come when they ask, never before.
- **Git and GitHub are yours, done without asking and never explained.** Saving, taking
  master and the app's updates, opening and merging a pull request, settling a merge and the
  local CI are always yes: never ask, never describe them, and never show a command, an
  option, a commit, a branch, a pull request, CI, master or a merge. Say the outcome in plain
  words ("Saved.", "Updated to the newest version.") or nothing at all. Lines a tool prints
  for you (`sync_app:`, `Claude:`, file paths, counts of commits) are never repeated. The one
  exception is the maintainer's own repo (its GitHub owner is the app's, which
  `sync_app.maintainers()` checks), and only when they ask.

The tools' own messages are written this way (`tests/test_a_beginner_is_told_in_plain_words.py`
keeps them so): pass them on as they are, never reworded into jargon.

**A draft they ask for is not a claim.** When the person asks for an example, an anecdote,
metrics, a project or a way they might have used a tool, for interview prep or a call, write
a plausible one marked as a draft for them to confirm or change (`/interview` rule 2). Never
refuse and never question whether it happened. "Never claim anything not in the profile" is
about what an employer or a contact sees: a draft reaches the profile, or anything they see,
only once the person confirms it.

## Learning the person: it grows with them

The app's defaults (the voice of a first note, the questions an interview pack asks,
who is worth contacting, how roles rank) are where everyone starts, and they stay. But
the person's own reactions outrank every default, and **they are kept for good in
`profile/learned.json`** through `tools/learned.py`. No sync touches it, and no upgrade
changes a setting it records.

**Whenever the person reacts to anything**: a message, a draft, a person or a job that
was surfaced, the voice, the questions, a word choice, how much detail. Phrases like
"I don't like this", "too formal", "not this kind of company", "stop suggesting
recruiters", or an edit they make to a draft before sending it all count. **This is
enforced, not remembered**: the app's one hook (`tools/learned.py hook`) puts a reaction on
the chat's pending list, every composer refuses to draft over it, and the turn cannot end
until it is recorded or skipped with a reason (`learned.py skip`). An edit made before
sending records itself when the send is logged with its words. Then, in the same turn:

1. Apply it now: redraft, drop the person or the job, change the setting.
2. Make it stick where it governs. That means the profile setting: `networking.py`
   (`OPENER`, `ABOUT_ME`, `ASK`, `GREETING`, `REFERRAL_LINE`, `REFERRAL_CLOSE`,
   `TITLE_SETS`), `search.py` (the bar, the scoring words), `profile/CLAUDE.md` (how they
   want to come across, document rules), `07-interview-prep.md`, and for how a page looks
   ("bigger font", "less cramped", "centre my name") `person.json` `documents.design`
   through `python3 templates/doc_design.py adjust <change>`. A job they dislike is
   `python3 tools/exclude.py add <url> --basis person --reason "<their words>"`. A person
   they do not want contacted is a `closed` contact with their reason. A *kind* of job or
   person becomes the rule that covers all of them. **Rulings change, and that is
   normal:** when they change their mind about a kind of job, a sector or an employer,
   undo the ruling in the same turn (`exclude.py lift "<words of the reason>"`, the sector or
   employer out of `search.py` `BAR_EXCLUDED` or `BAR_DECLINED`, the entry out of
   `job_scraper/do_not_target.json`). A ruling made by their screening rules lapses by
   itself when the part of the rules it rests on changes (one blocker row, one gate setting);
   when you change a screening rule, run `exclude.py lapsed` in the same turn and `restamp`
   the groups that do not rest on what changed.
3. Record it: `python3 tools/learned.py record --area <voice|messages|questions|people|targets|jobs|documents|search|interview|other> --said "<their words>" --rule "<what is different from now on>" --applied-to "<file SETTING>"`. Add `--never-say "<phrase>"` for wording they never want; `tone.py` and `voice_check.py` then flag it in everything drafted. Where their rule and a check disagree, ask once which wins and add `--overrides <the check's rule name>` when theirs does. When it lists `CONTRADICTS`, ask which stands, with both dates, and retire the other.
4. Say in one line what will be different from now on.

**Read before drafting.** Every step that writes something the person will read or
send (`/apply`, `/network`, `/reply`, `/interview`, `/prep`, a shortlist, outreach) first
runs `python3 tools/learned.py brief <area>` and follows every rule it lists over any
default in the app.

**Ask, lightly, and now and then a tip.** After work they will read or send (a shortlist,
a draft, a batch of notes, an interview pack, a prep, a brief), end with the one line
`python3 tools/tips.py <search|apply|networking|reply|interview|prep|brief>` prints, and
nothing if it prints nothing. It decides when: the first time a kind of work is done, a line
saying the first go may be off and how to say so; after that a short tip on using the app,
at most one every two days. Never write one of your own, never more than one a reply, and
never in place of the work. "No more tips" is `python3 tools/tips.py off`. **When they ask
what it can do or how to use a part of it** ("show me around", "how do I..."), it is
`python3 tools/tips.py tour` (or `tour <topic>`), passed on as it prints: short, never a manual.

**Updates and what they have taught it.** A sync's genuine fixes apply: they change
code, not their settings. When an update would change a setting `learned.py locked`
lists, `/upgrade` changes nothing. It records `learned.py offer` instead, and the
person is asked once, with the session's other questions, whether to keep theirs or try
the new way. A kept choice is offered again after 30 days, saying when it was kept: a no
to any question is for now, never for ever (`profile_upgrades.py --no <id>` keeps one,
dated, and it comes back when the question changes or after `REASK_DAYS`).

### What works: it learns from results, not only from what they say

`tools/what_works.py` counts what happened, from the state files and with no model call:
which messages drew a reply, which applications reached an interview. **Before drafting**,
beside the learned brief: `brief messages` (with `--channel` and `--route`) for a networking
message, `brief documents` for an application; match the shape of what worked, never its
words or another person's facts. **When a result arrives**: `event --company "<employer>"`
from `/outcome`, `event --contact <id>` from `/reply`, one line shown in the reply. A
difference is reported only when both groups are big enough and the gap is unlikely to be
chance. A resume that reached an interview gives its bullets a small, capped lift in
`tools/allocate.py`, which decides between bullets a posting rates alike and never outranks
one the posting asks for. A message logged without its `full_text` can never be an example.

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
| An interview was booked | that application's `outcome.md`, as a scheduled stage line, via `/outcome` |
| The questions an interview asked, and which stories landed | `documents/interview/question_bank.csv`, via `/outcome` (`interview_pack.py asked`) |
| Anything learned about a role, employer or process | `job_search_tracker.csv` `notes`, appended with the date |
| Messaged someone, or they replied | `network_threads.csv`, one row per message |
| Sent a contact a resume | that message's row, with the file: `state.py message <id> --attached <file>` |
| A new person worth contacting | `network_contacts.csv` |
| A contact's situation changed, or something is now owed | that contact's `status` and `next_action`: `python3 tools/network/state.py set <contact> --status <s> --next-action "<what>" --due <date> --note "<what happened>"`, never by hand |
| An employer turns out to have no relevant presence at all | `job_scraper/do_not_target.json`, with a `review_after` |
| A posting was ruled out | `job_scraper/seen_jobs.json`, through `tools/exclude.py add` (a reason, and what it rests on) |
| A fact about the candidate: a skill, a gap, a date, a constraint | `01-candidate-profile.md`, and `CLAUDE.md` if it belongs in the summary |
| They told one employer a different place from the profile's | `python3 tools/told.py "<Employer>" "<place>"` (person.json `identity.places_told`) |
| A reaction or preference: a message, a person, a job, the voice, the questions | the setting it governs, and `profile/learned.json` via `tools/learned.py record` |
| Company research that cost a fetch | `company_research/<key>.json` |

`python3 tools/open_actions.py` renders all of it as one view, employers first, each
carrying its applications and its contacts together. `--company <name>` answers "what is
happening at <employer>" in one command. It is **derived, never stored**, so it cannot go stale:
if something is missing there, fix the state file, not the view.

**Commit and push whenever a unit of work finishes**, not once at the end (the `git add`
lines are in the persistence rule above): a session that runs out of context mid-task loses
everything uncommitted. **The tracker only knows what was recorded.** A candidate applies to
things directly, which is why the already-applied question (Job Search Behaviour, above) comes
before anything is drafted: a yes is a tracker row at `applied` with the date they give
(`/apply` Step 1c), and a no is recorded by the `drafted` row the draft writes.

## Verification Checklist

After creating or updating a CV or cover letter, go through **every** item in
`.claude/skills/job-application-assistant/verification-checklist.md` before presenting
anything: factual accuracy, targeting, consistency, quality (including every document rule
`profile/CLAUDE.md` adds), both documents compiled and read back as PDFs (mandatory, never
skipped), and the resume's text layer as an ATS parses it. Report it in one line (all of
them passed, or `verify_batch.sh`'s last line), plus each item that failed or needs the
person's call; never the whole list.
