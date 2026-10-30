# Runbook: one round, portals to sent applications

Every step below is a command. Nothing spends model tokens until step 2, and step 2
spends them only on writing.

## Start of a session: what the start command and the day's check print

Every chat starts with `python3 tools/app.py start --on "<this chat's model>" --tools "<the
browser tools this chat has: browser, chrome, enable, or none>"` (CLAUDE.md) and does what it
prints: it checks the copy, runs the day's check below when it has not run today, publishes or
refreshes the person's page and says where setup stands. This section says what each part
means, for when a line it prints is unclear.

This repo is either **the app** (`github.com/aranculleton/last-job-search`, public, no
`profile/`) or **a person's copy**, made from the app and private. In a person's copy the
day's check is five steps, before anything else:

1. **Pull master**: `python3 tools/sync_app.py --pull`. Another chat may have merged since
   this container was built. It never merges a master whose history was rewritten (the fetch
   says "forced update"), which conflicts on hundreds of files: a branch with nothing of its
   own moves to the new master, and one with commits of its own stops, names them and gives
   the command that carries them across. Exit 1 means it stopped with nothing changed: do
   what it printed before anything else.
2. **Take the app's updates**: `python3 tools/sync_app.py --on "<this chat's model>" --tools
   "<the browser tools this chat has>"`. It fetches the app and merges what is new (the newest
   release; the maintainer's own copy takes master), never sends anything back, and ends with
   the day's model check: what this model suits and what wants another, which goes first in
   the reply when the person's request is one of the latter. Then the place check
   (`tools/place.py`), once a chat (weekly only while a computer lacks a tool): when this chat
   cannot do what the person set up (tools missing on their computer, say), it prints what to
   tell them, which goes at the end of the reply in its own words: two or three short
   sentences, and the dated steps only if they ask how (`place.py how`). It offers a choice
   and never makes it. It recommends no move to a chat on a computer: the page and the chat
   that answers it do everything, the page reads LinkedIn profiles itself when it is open
   in the Claude desktop app, and a chat on a computer is optional, for files kept there
   (`place.CHATS`). In the maintainer's own copy the sync also checks the public app for
   their names (`tools/app_watch.py`): an `APP LEAK` line goes first in the reply, before
   anything else. The app is public, so nothing needs attaching; if the sync still cannot
   reach it (exit 2), attach it read-only with `add_repo` (owner and repo from the URL
   `https://github.com/aranculleton/last-job-search`, `access="read"`) and try once more,
   and if that fails too, say so in one line and carry on. Exit 1 means it stopped with
   nothing changed: do what it printed yourself (commit the work it lists, carry across what
   it names) and run it again. Never put it to the person: saving and updating are always
   yes (updating waits only where they chose that). **Updates arrive by themselves**, unless
   the person asks to choose when ("only update when I say", in any words): then write
   `"app_updates": "when_asked"` into `profile/person.json` for them and commit it (the
   page's Settings has the same switch). From then on this step only looks and changes
   nothing of the app; when a newer version is waiting it prints one line, once per version
   ("An update is waiting: ..."), which goes at the end of the reply in its words, and when
   they say "update" the same command with `--update` takes it. Never press them for it,
   and nothing waits on it. "Update" from the person, in any words ("we should have a new
   update now"), is enough on its own, whatever the setting: run `--update` and do what it
   prints, with nothing asked first.
   **Once an update is in, the page is brought up to date at once, never asked about.**
   Whichever run took it (the day's check from `app.py start`, `--if-stale`, `--update`), it
   ends with the page's steps (`app_listen.after_update`): the page's own code changed, so
   the chat that answers the page republishes it (any other chat asks that one to, with
   `app.py republish`), or only its data could have, so `app.py view`. Each command runs on
   its own, never chained. A publish that is refused is read again and tried once more; only
   a second refusal is said, in its one plain line. The person hears one line, "Your page is
   updated.", and nothing about safety checks, listeners, timers or the steps. Pinning the
   page is offered once ever, by `app.py published`, which records the offer in
   `profile/app.json`. A timer, a reminder or a background job of this chat's that ends with
   nothing new for the person is said to nobody; no step here sets one.
3. **No `profile/`?** `app.py start` has already said where setup stands, before anything is
   asked, by the one detector (`place.setup_state`): another chat may hold the profile on
   master or on a branch it has not landed (`set up elsewhere`: it brings it in and the
   search is set up), or still be writing it (`setup going in another chat`: say its one
   line and start nothing). Only with none anywhere (`setting up`) does `/setup` start, its
   questions asked on the page wherever one is published.
   **A profile here is never set up again** (that is `/reset`): in a chat on their computer
   it is "Your search is already set up; this computer is ready for it too.", and nothing is
   asked, least of all a resume.
   **One chat answers the page**: the one that published it, or the helper the person
   started from Settings ("Claude's helper, in the cloud", which works with their computer
   off). It is the only chat the app needs: the brief runs in it, long work on another model
   runs as an agent inside it, and once a day it tidies away the app's own old chats
   (tools/tidy.py; never the person's own, never unsaved work). The app never starts a chat
   by itself. Every other chat neither publishes nor watches the page, and says so once, in
   one line, the first time it starts; when the page's own code changed it asks that chat to
   republish (`app.py republish`).
   Start prints which this chat is (tools/app_listen.py).
4. **If the sync brought changes**, say in one plain line what changed for them, from the
   lines it printed under "What changed": never a file, a command, a version or a git word.
5. **Profile upgrades apply themselves; nobody has to ask.** The sync ends by listing what
   this copy still needs (`tools/profile_upgrades.py`): parts of the app that switched on
   after this person set up (their job boards researched and built, a setting written for
   their field, a portal rebuilt), and facts in the profile still marked `[CONFIRM: ...]`.
   The person will not know which ones matter, so never offer them a list or wait for a yes:
   - **What Claude can do alone** ("Claude applies these itself"): start one background agent
     at once (Agent tool, `model: "sonnet"`, `run_in_background: true`, `isolation: "worktree"`) running
     `/upgrade`, and go on with what the person asked. Their request never waits for it.
     When it reports, merge its branch into this session's work, then run `python3
     tools/network/state.py follow-ups --write`: it worked from an older copy of the
     messages. Its progress shows on the page.
   - **At the end of your reply**, one plain line per change it made for them, and nothing
     about commits or commands: if they want one undone, undo it yourself (`git revert`);
     the page offers the same Undo on each change. When it made none, say nothing about it.
   - **What needs the person** ("These need you", unconfirmed facts): ask at most three, at
     the end of the session, never at the start, **each as its short plain question first**,
     as the sync prints it (the page asks them as To do cards). Detail comes only after a yes
     (its steps) or a "why?" (one sentence), both in `profile_upgrades.py --plan`; a no gets
     one line, "No problem, I'll ask again in a month.", and `--no <id>` records it. Never
     paste a long block, an id, a version number or the word "upgrade". Write each answer
     where its marker was and commit it. The rest wait for the next session. A no to any
     question is for now, never for ever: `--no <id>` keeps it, dated, and it comes back when
     the question changes or after `REASK_DAYS`; a setting the person kept over a new way
     (`learned.py offer`) is offered again after 30 days, saying when it was kept.
   If the sync printed nothing about upgrades (its first run after this arrived is the old
   copy), run `python3 tools/profile_upgrades.py` yourself and do the same.
   - **One chat per update.** When the sync says the upgrades belong to another chat, start
     nothing and ask nothing about them, set no timer to look again (the next sync hands them
     over by itself), and follow what it prints; when the person says no
     other chat is open, `python3 tools/profile_upgrades.py --take` hands them over. The chat
     that brought an update in lands that sync on master promptly, before its other work.

**A chat that carries on for days does this every day, not once.** Most people keep one
chat going, so "the start of a session" may be days ago. Before each new piece of work (a
search, an application, outreach, a reply, interview prep), run `python3 tools/sync_app.py
--if-stale --on "<this chat's model>" --tools "<...>"`. When today's check has not run, it
does steps 1 and 2 (master, then the app) and the rest follows as above; otherwise it prints
"already checked today" and changes nothing. `run_round.py` and `stage_picks.py` print a
reminder when it was skipped, and that reminder is code, so it reaches a chat whose
instructions were loaded before this rule existed.

**Which model, and how hard it thinks.** The day's sync prints the model check (step 2,
`--on`). For one piece of work, `python3 tools/model_guide.py <command or kind of work> --on
"<this chat's model>"` prints nothing when the model fits; otherwise its one line goes first
in the reply, and the work carries on. `--all` prints the whole table for anyone who asks.

In the app itself, step 2 is a no-op and step 3 does not apply: the app has no profile and
must never get one. `app.py start` there makes the person's private copy first.

## 0. Fresh container, or a computer of your own

In a cloud container, `./tools/setup_env.sh` does all of this and is a no-op when it is done:
the one line in that script's header, the same line a person pastes into the cloud
environment's setup script, is TeX, then `cffi` before the Python packages. **`./tools/setup_env.sh` sets the container up**,
one package at a time; pasted into the cloud environment's setup script (where: `python3
tools/claude_surfaces.py say cloud-environment`), its header line is cached. It is not a
SessionStart hook, on purpose: `tools/security_guards.py` keeps that allowlist empty.
SETUP.md, "A. Fresh cloud container", says why each piece is there and what its errors mean
(`File fontawesome5.sty not found` is an unset `TEXMFHOME`; a pyo3 panic from
`verify_pdf.py` is a broken `cffi`). Then:

```bash
./tools/ci_local.sh                 # in the app, before a change: every check CI runs, under two minutes
```

A person's repo needs neither before work starts: the day's sync runs their own tests when an
update arrives, and `./tools/ci_local.sh --quick` runs before a merge.

On a computer of their own (a Mac, Windows or Linux), Claude runs one command and the person
installs nothing first: no Homebrew, no winget, no password.

```bash
python3 tools/env_check.py --fix    # TinyTeX, Bun, gh and the Python packages, in their own folders
python3 tools/env_check.py          # then: what is here, one line each
```

Nobody is asked to set up a computer: the cloud does the work, and the person's page reads
LinkedIn in the Claude desktop app. [COMPUTER.md](COMPUTER.md) is for a chat on a computer that
someone already uses.
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

**Four commands around one workflow.** Stage the picks, build the drafting pack, run the
saved `draft-applications` workflow, audit, assemble:

```bash
python3 tools/stage_picks.py stage "$SCRATCH/r1" 3 7 "Acme::Demand Planning"
# Ask the questions it prints, then record each answer:
python3 tools/stage_picks.py consent "$SCRATCH/r1" <slug> --yes <skill> ... --no <skill> ...
python3 tools/stage_picks.py consent "$SCRATCH/r1" <slug> --draft   # or --skip: a held pick
# Two roles at one employer are both held with "which one?"; stage ... --both drafts both.
python3 tools/draft_pack.py build "$SCRATCH/r1"           # pack.md and draft_args.json
# Workflow draft-applications, args: the contents of draft_args.json, plus {today}
#   (add "only": [slugs] to leave out roles the person has dropped)
python3 tools/stage_picks.py audit "$SCRATCH/r1"          # both audits, authoritative
python3 tools/stage_picks.py assemble "$SCRATCH/r1"       # -> drafts.json
# Dropping a role after the workflow: audit and assemble with --only <slug> ... too.
```

**Models, workflows and subagents.** Inside the work, models are pinned per stage to
`11-cost-model.md`: reading and fetching go to sonnet, and anything that could put a false
claim in front of an employer runs on the session's own model and is never downgraded. Two
saved workflows in `.claude/workflows/` run by name with the Workflow tool:
`draft-applications`, whose args are the contents of `draft_args.json` (`{round_dir, pack,
pack_hash, picks}`) plus `{today}`, `only` (slugs) to leave out roles the person drops, and
`repo` when the session is not at the repository root (it writes `draft_<slug>.json` and
`model_audit_<slug>.json`; `stage_picks.py audit` writes `audit_<slug>.json`); and
`repo-audit`, the maintainer's (MAINTAINING.md). Two subagents in `.claude/agents/` carry
the same split for a single `/apply`, an `/interview` or a networking call, where a workflow
is too much: `employer-researcher` (sonnet: one employer's facts from its own pages, located
independently, quoted, cached in `company_research/<key>.json`) and `grounding-auditor` (no
model set, so the session's own: the last read before anything reaches an employer or a
contact, with profile grounding, `check_claims`, `check_numbers`, `voice_check` and
`compose.validate()`). The path is the same for a batch from a round and a single `/apply`
(`stage_picks.py single` stages the one posting). Every draft that will be sent gets both
audits; a draft the code audit alone passed is never assembled.

**A skill a posting names that the profile does not hold is the person's call, every
time**: `stage` prints one short question per pick, asked as written (on the page, it was
asked when they tapped "Draft this": the work item's `answers`), `consent` records each
answer, and the workflow drafts nothing and `assemble` assembles nothing while a question
waits. `/apply` Steps 1c and 2 have the rest: a skill the question missed, what a yes puts on
the page, and a general yes written into the profile in the same turn. `stage` **never reuses
a name another application was sent under**: a second role at an employer gets a role token
(`Acme_DemandPlanning`), and `fit_to_page.py` refuses the whole batch if a draft arrives
under a name that belongs to a different role.

**The drafter reads the pack and nothing else.** `draft_pack.py` compiles what every
drafter used to read for itself (the profile's facts, each under an id a claim can cite,
the person's rules and what they have taught it, the openings and closings already sent,
the field contract) into one file of a few thousand tokens, the same bytes for every
posting, so the prompt cache serves it after the first. Build it again after any
`consent`, and whenever it says it is out of date. Each drafter is one call: the pack,
this posting, the verified research. It returns the draft object with a claim map (each
sentence and the ids it rests on), writes it to `draft_<slug>.json`, and repairs from what
the code audit prints, at most twice.

**Every draft that will be sent gets two audits: code first, then the model.**
`stage_picks.py audit` runs every check that is mechanical (`tools/draft_audit.py`:
voice_check, check_numbers with numbers written as words, check_claims, the letter checks,
the budgets, rule 9, the person's answers, each sentence's numbers, skills, verb, scope,
tense and employer facts against what it cites, every cited research quote against the
page it was fetched from, and the letter's addressee against the research) and writes
`audit_<slug>.json`. Then the model auditor reads it: one call on the strongest model per
draft, flagged or not, reading one packet and nothing else (`python3 tools/draft_audit.py
packet "$SCRATCH/r1" <slug>`, under 10k tokens: the draft, each sentence beside the
evidence it cites, the research facts and their quote checks, the flags, what changed in
the profile since the draft) and saving its verdict with `python3 tools/draft_audit.py
verdict "$SCRATCH/r1" <slug>`, which re-checks its corrected draft by code. A draft is
`needs_model` until then, and `pass` or `fixed` only once code agrees with what it
returned. Skipping it is only for the roles the person drops: `only` (slugs) in the
workflow's args, and `stage_picks.py audit --only <slug> ...` and `assemble --only <slug>
...` after it. `assemble` renders a draft both audits passed and nothing else.

`outreach_body` is optional. Without one, `tools/outreach.py` builds the note from the
letter, as it always has; `outreach` in the args (true, or a list of slugs) has a small
step write one from the paragraphs both audits passed, saved with `python3
tools/draft_audit.py note`, which stamps it with the draft it was written for, and the
code audit checks it whole. A note written for another version of the draft is left out.

**What it cost.** Save the workflow's return value as JSON and run `python3
tools/draft_cost.py "$SCRATCH/r1" --result <file> [--usage <file>]`: one record per stage
per posting, in `cost.json` beside the batch and each application. Tokens, tool calls and
seconds come only from the Workflow tool's run summary (`--usage`); the script cannot see
them.

The workflow researches each employer on sonnet and drafts and audits on the strongest
model, per `11-cost-model.md`. Research fetches only through `python3 tools/company_research.py
fetch "<employer>" --posting <pick file> --urls ...`: robots.txt first, the crawl delay kept,
a feed or sitemap behind a bot check, `FETCH_BUDGET` requests an employer a day, what each
host did noted in `company_research/_hosts.json` for the next agent, fresh facts never
fetched again, and each saved quote checked against the page. **Its concurrency is CPUs minus two**, which on a 4-CPU
container is two agents at a time. Where the Workflow tool is not available, run the same
stages as background agents: the briefs are the prompts inside the workflow file, with the
contents of `pack.md` as the drafter's first lines.

`stage` picks each filename and never reuses one another application was sent under.
When it gives a slug to a different role than the round's earlier pick under it, that
pick's files (its draft, research, audits, note) move to `old/<slug>-N/` first; a draft
still found for another role is `stale` and never assembled. The rest of this section is
what each draft object must hold, whichever way it is written.

For each chosen posting, write one draft object; the fields are in
`tools/render_application.py` `build()`. In short: `abbr`, `company`, `role`, `summary`
(36 to 52 words, identity first), `tools` (the stack the posting names that the profile
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

**A yes can be named in the work that used it, on that resume only.** `bullet_rewordings`
(optional, `[{"id", "skill", "text"}]`) rewords up to three of the bullets the allocator
chose, each the profile's own bullet with a skill the person said yes to for this
application added beside the tool the work used. The pack lists which bullets each yes may
go in; `tools/bullet_rewording.py` is the guard, run by the code audit and again by the
renderer: the same numbers, every tool still named (never "Redshift" turned into the yes),
nothing added but the yes and a linking word, and work the skill's tool family, theme or
the profile's bridge touches. The model auditor rules on whether the work plausibly used
it. A rewording lives in the draft and its kept `draft.json`, and is never written back to
`profile/bullets.py`; a refused one renders as the profile's own bullet.

`concession` is a drafter's note for the record and is **never rendered**; if a
concession is warranted at all, the sentence itself lives in `p2`. Every company fact in
`p2` is verified from the company's own site, located independently, never from a URL
inside the posting.

`assemble` writes `$SCRATCH/r1/drafts.json` (a list); `stage` wrote the shortlist rows as
`$SCRATCH/r1/apps_in.json`. Section 1 of the pack is this contract as the drafter reads it.

## 3. Render, fit, verify

```bash
python3 tools/fit_to_page.py "$SCRATCH/r1/drafts.json"
tools/verify_batch.sh "$SCRATCH/r1/drafts.json"     # runs check_claims, check_numbers and voice_check too
python3 tools/outreach.py "$SCRATCH/r1/drafts.json" "$SCRATCH/r1/apps_in.json"
```

Both audits in step 2 ran before anything was rendered: the code audit (the claim,
number, voice and letter checks on each draft object) and the model auditor's reading of
its packet. The code checks run again here on the rendered files, where the page, layout
and text-layer checks can be made too: a sign the font has no glyph for, in the resume or
the letter, is named.

`fit_to_page` allocates bullets, renders, compiles, trims the weakest bullet for *this*
posting until one page, then grows back the strongest absent one that still fits.

`check_claims` must report **0 error-level findings**, and `audit_letters` must report
every letter clean; `verify_batch.sh` runs both, and exits non-zero
on any finding and checks pages, chronology, section order, bullets per employer, contact
details as literal text, duplicated phrasing, em and en dashes, the document nouns the profile
bans (`person.json` `documents.banned_nouns`), the ATS text layer (read with pypdf, which alone
sees words run together: without it the batch exits 3 and says the spacing check was SKIPPED),
every figure in each letter against the profile (`check_numbers.py --drafts`, numbers
written as words included; the summary and the letter bullets against the profile alone,
the opening and close also against the posting and p2), and a letter bullet that repeats a
resume bullet. The resume's filename
noun is the profile's own word (`documents.noun`), so a profile that says "CV" writes
`cv/<Prefix>_CV_<ABBR>`.

`outreach` writes `documents/applications/<slug>/job_posting.md` and `outreach.md`. The
outreach note is a sub-80-word message to the hiring manager or recruiter built from the
letter's verified company fact. Sending it is the user's call; every application gets one.
It also keeps `draft.json` in that folder: the object both documents are rendered from, with
the posting named rather than copied. After a renderer fix,
`python3 tools/fit_to_page.py documents/applications/<slug>/draft.json` re-renders an unsent
application from it.

Then read every resume and letter in the batch by eye. Not the .tex, the PDF. LaTeX page-break decisions are not
predictable from source, which is the whole reason this step exists. **Verify both
documents**: go through **every** item in
`.claude/skills/job-application-assistant/verification-checklist.md` before presenting
anything (both documents compiled and read back as PDFs is mandatory, never skipped, and so
is the resume's text layer as an ATS parses it), and report it in one line (all of them
passed, or `verify_batch.sh`'s last line), plus each item that failed or needs the person's
call; never the whole list. A finding is fixed in the draft object and rendered again, never
by hand in the `.tex`. Bullets are **allocated per posting** by `tools/allocate.py`, never
hand-picked, and filenames are human-looking (`<Prefix>_Resume_<ABBR>`, the File naming table
in `05-cv-templates.md`).

Deliver the batch on the person's page first (CLAUDE.md, "Every output is shown"): the files
in the page's own store, then `python3 tools/app.py view`, so each role shows under Drafts.
Where there is no page, the one way "Delivering in the chat" below sets: per role, one
file-sending call with its resume and letter, captioned role, employer, pay, location and
apply link; then one index table in the reply, role | apply link; paths as plain text
underneath, never as markdown links, which do not open from the desktop app.

## 4. Record and persist, then land on master

`python3 tools/record_drafts.py "$SCRATCH/r1/drafts.json" "$SCRATCH/r1/apps_in.json" --round r1`
adds a row per application at `status=drafted` (fit in `fit_rating`, never priority) and
writes each `screening_answers.md`. Then:

Then `python3 tools/save_state.py` (CLAUDE.md, "Saving"), which
stages each path that exists and no build noise, in any shell, then `git commit -m "<what
changed>"` and, as a command of its own, `git push -u origin HEAD`.

**What it stages, and why it is forced.** A person's copy is **private** and the search runs
in cloud containers that are gone when the chat ends, so nothing persists unless it is
committed, and the state is committed there. (Upstream's "never commit the tracker" rule is
for public forks. The app itself holds none of it, and its CI fails on a personal path.)
**Do not edit `.gitignore`**: `tools/security_guards.py` enforces it in CI, so the ignored
files are forced in instead, path by path. `save_state.py` is the rule as code, so it works
in any shell: the loop it replaced stopped under zsh, the Mac's own shell, on the first
pattern that matched nothing, before staging anything. It stages `profile` and `networking`
with a plain `git add`, never `-f`, which would force in the caches under `profile/tests/`;
and, forced in, the tracker, `network_contacts.csv`, `network_threads.csv`,
`job_scraper/seen_jobs.json` and `do_not_target.json`, `documents/cv`, `applications`,
`network`, `rounds` and `interview`, each application's resume and letter in `cv/` and
`cover_letters/`, `company_research/*.json` (it costs a fetch to rebuild) and `upskill/*.md`
(`--list` says what, and stages nothing). `documents/rounds/<round>.json`, each round's top
60 without the posting bodies, sits outside the ignored `rounds/` on purpose.
`network_threads.csv` is the file that must never be lost: status is derived from it, and
without it every contact reverts to `not_contacted` and the same people get messaged twice.
**Build noise is never staged** (`*.aux`, `*.log`, `*.out`, `*.fls`, `*.fdb_latexmk`,
`*.synctex.gz`, `cv/*.txt`, `__pycache__/`, `.pytest_cache/`), nor `salary_data.json`
(licensed third-party data). Never force any of them in by hand.

### Landing on master

Several chats run against one copy, each in its own container and on its own branch. That
works only if every branch lands on master before its chat ends: a chat that starts from
master cannot see work sitting on another chat's branch, and builds it a second time. So:

1. **Start by pulling master and taking the app's updates** ("Start of a session", above),
   before writing anything, not before pushing.
2. **Finish by getting the work onto master.** Not "pushed to the branch": on master. Open
   the pull request and start `./tools/ci_local.sh --quick` in the background (Bash,
   `run_in_background`), so the chat stays free for the person and the page while it runs
   (in the foreground it held the chat that answers the page for minutes, 2026-10-29); when
   it ends green, merge, in the turn its ending wakes. Silently: never subscribe to it, set a
   check-in for it or wait on GitHub's checks, and never tell the person about it or its
   checks (CLAUDE.md, "Saving"). While it runs, the chat that answers the page says "Saving
   your work" there (`app.py busy`, the `app` skill, step 5), and clears it once landed. A
   branch left behind at the end of a session is work the next chat cannot see and will
   duplicate.
3. **Never leave a merged branch around**, and never start new work on an old one.
4. If the work genuinely is not finishable this session, push it, and say in one plain line
   that it is not finished and the next chat carries on. The next chat finds it itself
   (`git branch -r --no-merged origin/master`); the person is never given a branch name.

**Commit and push whenever a unit of work finishes**, not once at the end: a session that
runs out of context mid-task loses everything uncommitted. Batch the commits and push once a
unit of work is finished.

**Two chats changing the same state file is not a conflict to resolve by hand.** The
tracker, the contact book, the message log and every JSON state file the app writes (the
profile's, the page's, the networking and research records: `merge_state.JSON_FILES`) merge
row by row or key by key (`tools/merge_state.py`, which every sync wires into git): rows and
entries either side added are both kept, and notes both sides added are both kept. Where
both sides changed the same field of the same row, the later change is kept by itself (the
record's own date where it has one), and the merge says which and what the other side had:
tell the person in plain words which answer was kept and what the other said, since their
word outranks it. A line ending "nothing to tell the person" is the app's own record. Git
stops only where neither change is later. Before
merging a pull request, `git fetch origin master` and then `git merge origin/master`, each a
command of its own, so that merge happens in the container, where the driver is set, and not
on GitHub, where it is not.

The one thing that is **not** negotiable in the other direction: **never push to master
without CI green**. It is the branch every other chat starts from, so a broken master breaks
all of them at once. **On a private copy, green is established locally, and that is the
rule: `./tools/ci_local.sh --quick`** (it skips the compile of the app's example documents,
which a person's copy never edits, and a second run of their own tests on the oldest Python;
the full run is for a change to the app). A
clean run is the evidence and merging on it is allowed; say so in the pull request and name
anything it reported as SKIP. Why, what CI's Python 3.9 leg is for, and the one case worth a
billed CI run: MAINTAINING.md, "CI on a private repo".

**On a computer of your own** (no GitHub tools in the chat; `gh` is the route, and
`place.py` lists it, and `gh auth login`, which is the person's to run, when either is
missing), the first chat works in the copy itself, and a second chat open there at the same
time works in a folder of its own, made once and first, before any other work (the sync's
first line says so when another chat is working in the main folder):
`python3 tools/sync_app.py --worktree <name>` (`.claude/worktrees/<name>` inside this folder,
where Claude Code keeps its own, on a new, unique branch from master), and every command runs
there: `cd` into it once, and since it is inside the project the chat stays there. Two chats in one folder switch branches under each
other and fight over git's index. Files git does not carry (the connections export) are read
from the main folder. Then, from that folder, commit, and:

```bash
git fetch origin master
git merge origin/master        # the row-by-row driver merges state files; the sync sets it here too
./tools/ci_local.sh
git push -u origin HEAD
gh pr create --base master --fill
gh pr merge <number> --merge
gh pr view <number> --json state -q .state           # MERGED is the answer, not the exit code
git fetch origin master
git switch --detach origin/master
```

The last line keeps no local master to fall behind.

**Run each line as a command of its own, the merge above all: never chained with `;`, `&&`
or a pipe.** Every one of them is pre-approved in the app's `.claude/settings.json`, and
Claude Code approves a command only when each part of it matches a rule, before auto mode's
own check looks at it. A chain with one part that is not pre-approved (`git push ...; gh pr
edit ...; gh pr merge 164 --merge`, 2026-10-23) goes to that check whole, and it refuses a
merge as "Merge Without Review". The merge alone matches `Bash(gh pr merge:*)` and runs.
To change a pull request's text, run `gh pr edit` on its own line before it, never in the
same command.

`gh pr merge` can exit non-zero after a merge that worked: it tries to fast-forward a local
master that has fallen behind and prints "fatal: Not possible to fast-forward". Keep no
local master, and read the state, not the exit code. The rules apply once the folder is
trusted (the desktop app asks once). Where a merge is still held:

- **The approval box** (Manual or Accept edits mode): say one plain line, "Click Allow to
  save this.", and nothing about merges.
- **Auto mode refused it**: never switch to bypass permissions, and never ask the person to.
  Auto mode takes the person's own message naming the action as their approval for that one
  action, so ask once, in these words: "Your computer's safety check wants your OK to save
  this. Reply: yes, merge pull request <number>." Then run the merge again, on its own.

It never retries on its own beyond that.
When the pull request has landed, `cd` back to the main folder and `git worktree remove <the
folder>` from there (Windows will not remove a folder a chat is still working in).

## 5. After the user applies

- `/outcome`, or `python3 tools/confirm.py applied <row> --on <date> --source chat` (an
  employer, `Employer::title words`, the file's ABBR, or `all from round <name> except ...`),
  never a hand edit of the tracker: it keeps `date`, writes `applied_on` and who said so, and
  prints exactly which applications it covered, which the person is shown.
  `confirm.py check` lists what does not add up (an application nobody confirmed, a draft
  whose notes say it went).
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
  separate clock on purpose: 5 to 7 business days, and one only, unless the person's
  `FOLLOW_UP_DAYS` and `MAX_UNANSWERED` in profile/networking.py say otherwise (the
  networking skill); `state.py follow-ups --write` puts each date on its contact.
- `DO NOT CHASE` in a row's notes holds its follow-ups, with the reason shown; `until
  YYYY-MM-DD` in the same note, or a later note saying `chase again`, lifts it. An
  interview or offer at the same employer, or a referral in flight there, holds them too.
- `/interview <company>` when one lands. Not `/prep`, which is for a networking call.

## What "done" looks like for a round

At least 5 postings scoring 60+, of which 2 at 75+, all inside the round's age window. Every drafted
application has two verified one-page PDFs, a persisted posting, an outreach note, a
tracker row, and 0 claim errors. All of it committed, and on master.

## What changes, and where it goes

Sessions here run in **ephemeral cloud containers**: the conversation is gone when the session
ends, and anything that matters has to be written to a file and committed, or it did not
happen. **The standing rule: whenever something changes, write it down before replying.** Not
at the end of the session, not when asked. A session that learns a fact and only says it in
chat has lost it.

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
| A fact about the candidate: a skill, a gap, a date, a constraint | `01-candidate-profile.md`, and `profile/CLAUDE.md` if it belongs in the summary |
| They told one employer a different place from the profile's | `python3 tools/told.py "<Employer>" "<place>"` (person.json `identity.places_told`) |
| A reaction or preference: a message, a person, a job, the voice, the questions | the setting it governs, and `profile/learned.json` via `tools/learned.py record` ("Learning the person", below) |
| Company research that cost a fetch | `company_research/<key>.json` |
| Something the person did on their page (a tick, an answer, a setting) | applied by `python3 tools/app.py apply`, the `app` skill, never by hand |

`python3 tools/open_actions.py` renders all of it as one view, employers first, each
carrying its applications and its contacts together. `--company <name>` answers "what is
happening at <employer>" in one command. It is **derived, never stored**, so it cannot go
stale: if something is missing there, fix the state file, not the view. The page is built the
same way (`app.py model`), from these files and nothing else.

**The tracker only knows what was recorded.** A candidate applies to things directly, which
is why the already-applied question comes before anything is drafted (the job-scraper skill,
"The rules every search keeps"): a yes is a tracker row at `applied` with the date they give
(`/apply` Step 1c), and a no is recorded by the `drafted` row the draft writes.

## Delivering in the chat, where there is no page

Everything the person asked for goes on their page first (CLAUDE.md, "Every output is
shown"). Where no page can be published (the chat has no Artifact tool, or `python3
tools/app.py published none` was run for it), the chat is the page, and every output
arrives **in the reply**: a message to send, a draft, a resume, a cover letter, an outreach
note, an interview pack, a prep doc and a shortlist. Nobody should have to go looking in the
repo. Text they will send (messages, notes, questions) is pasted in full, ready to copy. A
document (a PDF, a pack, a prep, a long file) is sent with SendUserFile so it opens in one
tap (`display: "render"` for a pack or a prep), with the part they need to judge it pasted
beside it (a pack's one screen), under a name that says whose it is: a prep document is sent
as the copy `python3 tools/shown.py <file>` makes ("Acme Analyst interview prep.md", never
"prep.md"), which the prep tools print as `send:`. **Where the chat has no SendUserFile**
(Claude Code's tools reference lists it for a cloud chat, and for a chat on a computer only
while it is steered from claude.ai or the phone: `claude_surfaces.py show remote-control`),
paste that one screen and write the copy's full path on a line of its own: in the desktop app
a path in the chat opens when clicked. The file path is the record, written underneath, and
never the answer on its own: "I've put it in documents/..." is not done. The same goes for
anything updated: show the new version, not where it went.

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

## Learning the person: what a reaction changes

The app's defaults (the voice of a first note, the questions an interview pack asks, who is
worth contacting, how roles rank) are where everyone starts, and they stay. The person's own
reactions outrank every default, and **they are kept for good in `profile/learned.json`**
through `tools/learned.py`. No sync touches it, and no upgrade changes a setting it records.
The hook and the four steps are in CLAUDE.md ("Learning the person"); this is the detail.

- **Make it stick where it governs.** That means the profile setting: `networking.py`
  (`OPENER`, `ABOUT_ME`, `ASK`, `GREETING`, `REFERRAL_LINE`, `REFERRAL_CLOSE`,
  `TITLE_SETS`), `search.py` (the bar, the scoring words), `profile/CLAUDE.md` (how they
  want to come across, document rules), `07-interview-prep.md`, and for how a page looks
  ("bigger font", "less cramped", "centre my name") `person.json` `documents.design` through
  `python3 templates/doc_design.py adjust <change>`. A job they dislike is `python3
  tools/exclude.py add <url> --basis person --reason "<their words>"`. A person they do not
  want contacted is a `closed` contact with their reason. A *kind* of job or person becomes
  the rule that covers all of them.
- **Rulings change, and that is normal:** when they change their mind about a kind of job, a
  sector or an employer, undo the ruling in the same turn (`exclude.py lift "<words of the
  reason>"`, the sector or employer out of `search.py` `BAR_EXCLUDED` or `BAR_DECLINED`, the
  entry out of `job_scraper/do_not_target.json`). A ruling made by their screening rules
  lapses by itself when the part of the rules it rests on changes (one blocker row, one gate
  setting); when you change a screening rule, run `exclude.py lapsed` in the same turn and
  `restamp` the groups that do not rest on what changed.
- **Record it**: `python3 tools/learned.py record --area <voice|messages|questions|people|targets|jobs|documents|search|interview|other> --said "<their words>" --rule "<what is different from now on>" --applied-to "<file SETTING>"`.
  Add `--never-say "<phrase>"` for wording they never want; `tone.py` and `voice_check.py`
  then flag it in everything drafted. Where their rule and a check disagree, ask once which
  wins and add `--overrides <the check's rule name>` when theirs does. When it lists
  `CONTRADICTS`, ask which stands, with both dates, and retire the other. An edit made
  before sending records itself when the send is logged with its words.
- **Ask, lightly, and now and then a tip.** After work they will read or send (a shortlist,
  a draft, a batch of notes, an interview pack, a prep, a brief), end with the one line
  `python3 tools/tips.py <search|apply|networking|reply|interview|prep|brief>` prints, and
  nothing if it prints nothing. It decides when: the first time a kind of work is done, a
  line saying the first go may be off and how to say so; after that a short tip on using the
  app, at most one every two days. Never write one of your own, never more than one a reply,
  and never in place of the work. "No more tips" is `python3 tools/tips.py off`. **When they
  ask what it can do or how to use a part of it** ("show me around", "how do I..."), it is
  `python3 tools/tips.py tour` (or `tour <topic>`), passed on as it prints: short, never a
  manual.
- **Updates and what they have taught it.** A sync's genuine fixes apply: they change code,
  not their settings. When an update would change a setting `learned.py locked` lists,
  `/upgrade` changes nothing. It records `learned.py offer` instead, and the person is asked
  once, with the session's other questions, whether to keep theirs or try the new way.

**What works: it learns from results, not only from what they say.** `tools/what_works.py`
counts what happened, from the state files and with no model call: which messages drew a
reply, which applications reached an interview. **Before drafting**, beside the learned
brief: `brief messages` (with `--channel` and `--route`) for a networking message, `brief
documents` for an application; match the shape of what worked, never its words or another
person's facts. **When a result arrives**: `event --company "<employer>"` from `/outcome`,
`event --contact <id>` from `/reply`, one line shown in the reply. A difference is reported
only when both groups are big enough and the gap is unlikely to be chance. A resume that
reached an interview gives its bullets a small, capped lift in `tools/allocate.py`, which
decides between bullets a posting rates alike and never outranks one the posting asks for. A
message logged without its `full_text` can never be an example.

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
| `app` | (none: it loads when the person's page rings a chat) |

Also `/html-report` and `/upgrade` (which a session starts itself, "Start of a session"
step 5), which belong to no skill.

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
- **`.claude/skills/` vs `.agents/skills/`.** The first is the skills above. The second is
  the job-portal CLIs that rounds and `/scrape` call; they are search tools, not advice, and
  they are never invoked directly.
- **Portals and employer boards.** The app ships `linkedin-search` and `freehire-search`; a
  person turns either off in `profile/search.py` `PORTALS`, never in its `SKILL.md`. Every
  other board is the person's, built by `/add-portal` into their repo. Employer ATS boards
  (`tools/ats_boards.py`, named in `profile/boards.py`) are a third source;
  `ats_boards.py --find "<Employer>"` finds a board, through the vendored
  [openroles](https://github.com/aranculleton/openroles) in `tools/openroles/` (never edited
  here). `python3 tools/portals.py` prints what the next round searches; the rest is in the
  job-scraper skill.

**Where things are**: `cv/` holds the LaTeX resume variants (moderncv, banking style),
`cover_letters/` the letters (the custom `cover.cls`), `.claude/skills/` the skills,
`.agents/skills/` the job-portal CLIs, and `networking/connection_targets.md` research notes
only, never a contact store (`network_contacts.csv` is). **Tools run directly, not through a
slash command** are the table below, each with what it does, its flags and its exit codes:
`run_round.py` exits 0 when the yield target is met, 2 when it is missed (a thin market) and
1 when a stage broke.

## Tools run directly, not through a slash command

| Command | What it does |
|---|---|
| `python3 tools/run_round.py --out rounds/rN [--expand]` | The whole free pipeline, portals to ranked shortlist. It checks the yield target and prints MET or MISSED with the counts. **Exit 0 met, exit 2 missed, exit 1 a stage actually broke** - a thin market and a broken pipeline are different answers. `--expand` re-runs wider up to the 3 rounds the rule allows. It **prunes itself**: `rounds/` is gitignored and its ~55MB of stage files are deleted, except `06_shortlist.json` cut to the top 60 with their bodies, which is what drafting is staged from; the same 60 rows, minus the posting bodies, are written to `documents/rounds/<round>.json` and **are** committed, beside what it filtered out and why (`documents/rounds/filtered/<round>.json`, read by `tools/filtered.py`). `--keep-intermediates` retains the stage files for debugging a round that went wrong, and a round that **missed** keeps `00_scrape/dropped.json`, `01_dropped.json`, `03_screened_all.json` and `06_skipped.json` automatically, with the posting bodies stripped, because those are the files the MISSED message tells you to read. |
| `python3 tools/network/prep.py --all` | Rewrites every contact's prep document. Without it a fix to `prep.py` reaches whichever one somebody runs next and no others. Each document's last line says which prep wrote it: `--stale-only` rewrites only the documents an older prep wrote or written before the contact's row or thread changed (and never writes one for a contact who has none), keeping answers already rewritten to be said, and `--dry-run` lists what would be written and writes nothing. `"<contact>" --check` exits 1 while an answer is raw profile wording or reads as written. |
| `python3 tools/network/export.py` | LinkedIn's data export, read, only the files it names. **Given one, `take <zip|folder>` first** (`take --find` looks in Downloads, Desktop and Documents): it saves every file the app reads into documents/linkedin/, in the main folder on a computer, and imports the history into network_threads.csv in one step. `files` (no argument) says plainly when messages.csv or Invitations.csv was never saved; `files <zip>` says what a download holds and what is missing, `history --from <zip>` lists the messages and invitations it would add to network_threads.csv (joined by profile address, else a careful name match, else listed as not in the contact book) and `--apply` writes them, twice adding nothing; `pending` lists the invitations sent and never accepted for three weeks, oldest first, for the person to withdraw on LinkedIn, and `withdrawn <name>...` records the ones they did. Nothing is sent. |
| `python3 tools/network/own_profile.py` | The person's own LinkedIn profile, now and then. `due` prints one line when a look is worth it (never looked over, a fact it compares has changed, or a run of unanswered first notes too long to be chance) and nothing otherwise, at most once in 30 days; `check` lists red flags only, each with its evidence and one fix; `brief` is what is left for the session's model to judge, well under two thousand tokens. Kept in documents/network/own_profile_review.json. |
| `python3 tools/network/profile_facts.py` | The candidate half of a prep doc, read out of `01-candidate-profile.md` and `tools/bridges.py`. `prep.py` calls it automatically; run it directly to see what it extracts. |
| `python3 tools/network/surface.py` | The one check before anyone is shown as someone to write to: the contact book (by id, LinkedIn address in any form, or name at either employer), their whole thread on every channel, the bar, `do_not_target.json`, a hold. `"<name>" --company --url` for one person, `--file <people.json>` for a list a chat made, `--queue` for everyone waiting on a first note, `--id` for book rows. Prints SHOW or NOT with the reason. |
| `python3 tools/network/state.py follow-ups [--write]` | Each conversation waiting on a reply, with the day its follow-up falls due by the person's rule (`FOLLOW_UP_DAYS`, `MAX_UNANSWERED`), or that no more go; `--write` puts it on the contact row, never over a next action the person wrote. |
| `python3 tools/network/export.py due` | One line once the last LinkedIn download is a fortnight old (`EXPORT_EVERY_DAYS`), for the brief; nothing otherwise. |
| `python3 tools/open_actions.py` | Everything owed, employers first, derived from the three state files: live applications, contacts owed a reply, and **follow-ups due** on applications that have gone quiet. `--company <name>` for one employer. **`--due`** prints only what is due today or overdue, both halves, most urgent first, with the counts on line one and the first five lines written to stand alone: it is what the daily routine pastes into a push notification. A contact whose `next_action` opens on HOLD or FREEZE is not due until the date after "until" arrives. Requests nobody accepted are one section to withdraw together, and anything owed more than 45 days with nothing done (`state.OLD_OWED_DAYS`, most often old LinkedIn history) is counted on line one, not listed; `state.py` still lists each, and a date of the person's own on the row keeps it live. An interview booked in an application's `outcome.md` is due once it is a week away with no pack for that stage, and its thank-you for a week after it until one is on file. This is the one view; `tools/followups.py` is the nudge half of it and still runs on its own when that is all you want. |
| `python3 tools/what_works.py brief <messages\|documents\|search\|interviews>` | What has worked, counted from the state files with no model call: reply rates and the messages that drew replies, the applications that reached an interview with the resume and letter they used, the interview rate by fit band and route, and (`interviews`) how far applications get by the stages ticked in each `outcome.md`, with the questions the bank says keep coming up and the stories that landed. A difference is reported only when the groups are big enough and the gap is unlikely to be chance. `event --contact <id>` and `event --company <name>` are the one-line audit when a result arrives. |
| `python3 tools/interview_pack.py pack "<company>"` | The one living prep document `/interview` builds for a hiring process, one screen first (what they are assessing and want to hear, likely questions with the story or answer for each, hooks, the money, what not to say), then your answers to write as said, what the employer's people and papers have been told (conflicts flagged), who you are meeting and the question for each, the format, and the detail, every fact sourced. `--stage`, `--date`, `--time`, `--with`, `--format` (case, coding, behavioural, technical, presentation, screen), `--map <json>` and `--write` (beside the application, as `interview_prep.md`, keeping what the person wrote). `book "<company>" [--stage ...] [--date ...] --time HH:MM [--zone <as written>]` saves an interview's day and time on its record (its `outcome.md` line), the one place the page reads it: a time said in the chat, an invite or a message is saved this way at once, never left for the person to add. `times` saves every time a note or a logged message gives for a booked interview that has none (logging a message or a note, and every wake of the chat that answers the page, run it). `process "<company>" --contact <id> --role "<role>" [--time HH:MM] [--posting <file or link>]` registers a process with no application (a referral or a recruiter's call) and writes its document in one command; `postings` gives every process folder that has none a `job_posting.md`. `motive "<question>" --answer "<their words>" [--suits ...] [--not-for ...]` keeps the person's own reasons in `profile/07-interview-prep.md` for every later employer. `check` exits 1 while an answer is unwritten or reads as written, a question waits on the person's own reasons, or research is still to do. `campaign --yes "<chat>"\|--no` records the one-time offer of a chat for that employer. `asked` adds a question an interview asked to `documents/interview/question_bank.csv`; `rework` adds an answer to work on, which a rebuild keeps. |
| `python3 tools/profile_consistency.py` | The pay band, the walk-away floor, the notice period, the sponsorship position and the permit-disclosure rule, said the same way across the profile: names every other place that says one differently from its source (the rubric's salary table, the candidate profile's notice line, the summary's sponsorship sentence). Exit 1 when anything disagrees; the `profile-consistency` upgrade asks the person which is right. |
| `python3 tools/followups.py` | The application nudges alone, on the schedule in step 5, "After the user applies": each one due, who it goes to, the held ones with their reason, and where the chase stops (at the throttle's 45 days of silence, `throttle.SILENCE_DAYS`, or a week after the second follow-up). `--close-quiet` closes each application past the chase as `no_response` with a dated note, recorded as the search's call (`confirmed_by` "the search") and printed as "closing as no reply" with the `confirm.py applied` line that keeps one open; the brief runs it. |
| `python3 tools/confirm.py applied\|not-applied\|skip\|closed <rows...>` | What the person says happened to an application, on exactly the rows they meant: a file's ABBR, the employer, `Employer::title words`, or `all from round <name> except ...`. `--on <date>` is the day it went, `--source chat\|page` where they said it; `applied --new --company --role --url` adds one made outside the app. It never moves `date` (part of the tracker's merge key), writes `applied_on`, `confirmed_by` and `confirmed_at`, prints each row it changed, and refuses (exit 1, nothing written) a name that could be two rows, listing them. `check` lists an application nobody confirmed, a draft whose notes say it went, and a page tick the tracker disagrees with (`--ticks <file>`). |
| `python3 tools/filtered.py show\|back <round> [<pick>...]` | What a round filtered out and why, kept by every round at `documents/rounds/filtered/<round>.json` (the search's gates, what was already ruled out or first seen too long ago, the screen's cuts, the throttle's skips). `back` brings one back: lifts its ruling and adds it to the round's shortlist, printing the rank to stage it as. |
| `python3 tools/apply_link.py <url>` or `--file <rows.json>` | The link a card shows: tracking taken off with the job kept, a redirect unwrapped, what kind of page it is, and the employer's own listing found on their board where one is on file, stamped "checked <date time>" (or "closed"). LinkedIn is never fetched. `stage_picks.py` runs it on every pick. |
| `python3 tools/stage_picks.py stage <round_dir> <pick>...` | The step between a shortlist and a draft. A pick is a shortlist rank or `Company::title words`. In a later session, when `rounds/` is gone, it reads `documents/rounds/<round>.json` instead and fetches each pick's body from its board, or reads `<round_dir>/postings/<slug>.txt` when the board will not give it. `single <dir> --company --role --posting-file` stages one posting from no round, which is how `/apply` enters the same pipeline. Writes each posting fenced by `tools/untrusted.py`, `picks.json` (the `draft-applications` workflow's args) and `apps_in.json`, and picks each filename: **a name another application was sent under is never reused**, so a second role at an employer gets a role token (`Acme_DemandPlanning`). It prints what code read from each posting (contract or permanent and when it ends, the pay and whose place it is for, years, degree, where and how it is worked, a repost, what is already running at the employer) and holds a pick with a surprise in it (a fixed-term contract, pay for another place, an application already in, a referral in flight, a second role at one employer unless `--both`) in `held.json` until `consent <round_dir> <slug> --draft` or `--skip`. It prints one short question per pick about the skills the posting names that the profile does not hold (never one it covers under another name: a held part such as Azure Data Factory covers Azure, a listed synonym such as model serving covers model deployment), and `consent <round_dir> <slug> --yes ... --no ...` records the answers: nothing is drafted or assembled while one waits, a yes prints on that resume's skills line, and both answers go into the documents' header. `assemble <round_dir>` turns the audited drafts into `drafts.json` and names any pick with no draft. |
| `tools/verify_batch.sh <drafts.json>` | Every rendered application: pages, chronology, section layout, text layer, claims, letters. Exits non-zero on any finding. |
| `python3 tools/record_drafts.py <drafts.json> <apps_in.json> --round rN` | The tracker rows for a rendered batch, by `/apply` Step 6b's rules, plus `screening_answers.md` for each. It writes **fit** in `fit_rating`, never the shortlist's priority, which can exceed 100 on a 0-100 column. |
| `python3 tools/bar.py "<company>"` | The candidate's bar in code: pay, prestige, signal, or none, with the reason. The throttle applies it every round: the sectors and employers `profile/search.py` excludes are skipped with the reason recorded, every other row carries its verdict into the shortlist and `documents/rounds/`, and "none" is a flag, never a cut. An employer on none of the profile's lists says so ("not on your employer lists yet"): `bar.py unjudged` lists them in the newest shortlist, and `bar.py judge "<company>" <pay\|prestige\|signal\|none> "<why>"` records a judgement once (`profile/employers_judged.json`), which every later verdict reads; the profile's own lists and hard rules outrank it. |
| `python3 tools/network/reading.py` | What was read about one person before writing to them: `read <contact_id> <file\|->` takes their profile page (pasted, read in the person's own browser, LinkedIn's Save to PDF, or transcribed screenshots), `add` one public finding (a talk, an article, a post), `show` what a note can rest on, best first, and `queue` the waiting drafts with no fresh reading, offering a paste for the best three only. `paste <file\|->` reads several profiles pasted at once, a line of `---` between them, each matched to a waiting note by name and employer. `draft <contact_id> <file\|->` writes a first note to its `draft.md`, refused when nothing was read about them unless `--card-only` (saved under `CARD ONLY`, shown as card-only), refused past the company limit, and checked with the notes waiting for one frame, opening or close (exit 11); `drafts <file.json>` saves a batch checked together. `estimate [N]` says how long N reads take today, before they start; `meanwhile` lists the notes to write while a page waits. `people <file>` with no `--company` groups a search by title across employers by employer. `shortlist <ids>` puts the run's best ten on the day's short list, and a browser read refuses anyone not on it. `verdict <contact_id>` is KEEP or SKIP after a read, `route --tools <...>` says how this session reads profiles and the one line to tell the person, `gate` says whether a browser read may go now, and `stop "<what LinkedIn showed>"` halts browser reads for the day. Keeps only what a note could rest on, never their whole profile. |
| `python3 tools/network/sources.py ["<employer>"...]` | Where to look for people. Alone, this person's plan of source kinds, ranked by what has drawn replies; with employers, the run's exact searches inside the budget (at most four per employer and five shared by the whole run), and none for an employer the job search ruled out. `ladder --tools <...>` prints what this chat can use, from their connections export to a read in their browser, and the one line to say when it has no browser; `connections "<employer>"` lists who they already know there; `harvest <results.json> --company "<employer>"` turns a search's results into a ranked list of people, each with its evidence, profile status (verified, likely or unconfirmed) and route, nothing fetched; with no `--company`, one search by title feeds every employer it found, grouped by employer, those the search ruled out left out. |
| `python3 tools/claude_surfaces.py` | What the Claude app and Claude Code can do, and how to reach each part, dated and sourced (`tools/claude_surfaces.json`): `show <id>`, `say <id>` (the words a person sees), `check` (entries older than 60 days, as warnings), `sync-docs` (the docs' marked blocks), and `watch`, the maintainer's check of every quote against its page and of the latest release, run weekly in the app only. |
| `python3 tools/network/why.py [<contact_id>...]` | Why each person: a score from 0 to 100 and one plain line, best first, by counting, with no model call. |
| `python3 tools/network/openalex.py "<employer>"` | Researchers who put the employer on a recent paper, only when `profile/networking.py` sets `OPENALEX`. A cloud session needs `OPENALEX_API_KEY` (SETUP.md). |
| `python3 tools/exclude.py` | Rulings in `seen_jobs.json`, each with what it rests on. `add <url> --reason "<why>" [--basis person] [--rests-on "<part>"]` rules a posting out (a reason that cites "blocker N" names its part by itself), `lift "<words in the reason>"` takes rulings off when the person changes their mind, `review` groups older rulings that record no basis, `stamp "<words>" --basis rules\|person` records what a group rests on, `parts` lists the parts of the rules a ruling can rest on, `lapsed` the rulings a rules change lapsed and `restamp "<words>" --rests-on "<part>"\|all` keeps the ones that still hold; `--url` narrows lift, stamp and restamp to named postings when reasons are word for word the same; and `rules` prints the rules fingerprint. |
| `python3 tools/sync_app.py` | Takes the app's updates and never sends anything back. `--if-stale` pulls master and syncs once a day and is a no-op after that; `--on "<model>"` ends the day's sync with the model check (`tools/model_guide.py`); `--check` says how far behind, changing nothing. Where the person's profile has `"app_updates": "when_asked"` (their choice, never the default), a plain run and `--if-stale` only look and say once that an update is waiting, and `--update` takes it when they say so. Exit 1 stopped with nothing changed, 2 the app could not be reached. |
| `python3 tools/env_check.py` | Whether this session can do the whole job, one line each: LaTeX, pypdf, Node or Bun, gh and every job board's host, with what to do about anything missing. `--fix` installs what a computer lacks into the person's own folders with no password (tools/installs.py); in a cloud chat it runs `setup_env.sh`. |
| `python3 tools/network/state.py` | What is owed, the requests sent and InMail credits left, the tracker links, and **RECONCILE**: every place the contact book disagrees with the message log. An orphaned thread sits undetected unless something runs it. Findings that need a person are listed; relationships that simply predate the message log are counted, not repeated. `withdraw <contact_id>...` (or `--all-due`) records connection requests the person has withdrawn: a `request_withdrawn` row and the contact closed, so they are never surfaced again. `nudge <contact_id> --text-file <file>` logs a nudge that went, with its words, and `message <contact_id> ...` any other later message (`--texts <file.json>` for several); the BUDGET line counts the requests sent this week and today, with no cap of the app's own: LinkedIn says when its own limit is reached. |

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
not a bug in the update. **A person's own tests (`profile/tests`) use the app's public names
only**, so fewer break: a name that starts with an underscore, and anything inside
`tools/openroles/`, can change in any release; a job board is faked through
`tools/offline_boards.py`. **When they fail after an update**, bringing them in line is
Claude's job, done in the same turn and committed with the sync's work: never a question or
a to-do for the person, who hears one plain line at most.

1. `python3 tools/sync_app.py --own-tests` sorts every failing test into two kinds and says
   what to do. The sync and `ci_local.sh` print the same by themselves.
2. **It uses a part of the app the update removed** (an `AttributeError` or `ImportError`
   naming one of the app's modules, often a name starting with an underscore). What it
   checked has moved, and the app's own tests cover the app's behaviour. Rewrite the ones
   that pin the person's own data through the app's public names (a job board through
   `tools/offline_boards.py`), keeping every assertion; the rest are retired.
3. **It checks behaviour the update changed.** Read the CHANGELOG entry for the change and
   bring the test in line with it. If the new behaviour looks wrong for this person, bring the
   test in line all the same; in the maintainer's own repo, report it the way its
   `profile/CLAUDE.md` says. Anyone else is never told: a failing test would hold the whole
   update back, and the app's problems are the maintainer's, not theirs.
4. **All of it is Claude's, in the same turn, with nothing asked.** Rewrite, retire and bring
   in line, run them again, and commit with the sync's work, naming each test in the commit so
   a revert brings any back. The person hears one plain line at most (`OWN_CHECKS_SAID` in
   `tools/sync_app.py`); most have never seen a test, and a question or a to-do about one is
   one they cannot act on.
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
