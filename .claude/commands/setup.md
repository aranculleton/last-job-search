# /setup - Set a person up

You are setting up a job search for the person in front of you, in their own private copy of
the app. They answer a few plain questions about themselves; you do everything else, most of
it in the background while they wait, and the proof is their first shortlist. The same flow
runs wherever this chat is (the Claude app on a phone, claude.ai/code in a browser, the
desktop app's cloud or Local chats): it never stops to send them somewhere else.

**Targets:** about six questions in all, under 400 words from you before the shortlist, and
the shortlist within about an hour. Everything about them goes into `profile/` and the state
files at the root; the code, skills, docs and templates are the app's and are never edited
here (CLAUDE.md, "App-owned files and personal files"). Speak as CLAUDE.md, "Talking to the
person", says: plain words, no file, command, git or GitHub word, ever.

How each part of the profile is written, section by section, is in
`.claude/skills/job-application-assistant/setup-sections.md`. Read the section you are about
to write before you write it; this file is the order and the questions.

**On the person's page (2026-10-25).** "Set me up" is the only thing they say in a chat. First
of all, `python3 tools/app.py start --on "<this chat's model>" --tools "<browser tools>"`, and
do what it prints: it checks the copy, takes the day's update, publishes their page and says
where setup stands. Wherever a page is published, every question below is asked **on the
page**, one at a time with "2 of 6", and never in the chat: the chat says the one line `start`
prints, then works. Each answer reaches the repo when the page rings this chat and it applies
the page's actions (the `app` skill: `python3 tools/app.py apply`), which writes them to
`profile/setup_answers.json`. **Read every answer from there, never from the chat, and never
ask one again**, here or on the page: a step already answered, or already held by the profile,
shows as done. `python3 tools/app.py start` again, at any point, says what is left.

- **The resume** arrives as a file the page holds (`resume.asset`: save it the way `start`
  prints, then `python3 tools/app.py resume-saved <file> --asset <id>`, and delete it from the
  page), as pasted words already saved to `documents/cv/resume_pasted_*.txt` (`resume.file`),
  or as "build one with me" (`resume.source: build`): then the page asks one job at a time
  from `history_interview.py ask` and keeps each answer in `history.jobs`, which you write into
  the profile as setup-sections.md, `history`, says.
- **The roles you propose**, once you have read the resume: `python3 tools/app.py propose
  "<role A>" "<role B>" "<role C>"`; the page's roles question shows them.
- **The research** shows its progress on the page: each topic in Step 2.3 is a work item
  `research~<topic>` (`boards`, `market`, `documents`, `voice`, `employers`), written at each
  stage boundary as the `app` skill says, and done once its section is recorded.
- **What only they can do** (their private copy, the cloud setting that lets this chat reach
  job sites, the chat on their computer, LinkedIn signed in there) is a card on the page with
  the registry's own steps; never type those steps into the chat.

**Where no page can be published, setup runs in the chat**, exactly as below. That is a
session the Artifact tool is not in, or refuses: one on an API key, a gateway token or a cloud
provider's own Claude service; the Agent
SDK, the GitHub Action, an MCP-server context, `claude -p`; artifacts turned off in settings,
by `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC`, or by an organisation's Owner; an organisation
with customer-managed keys, HIPAA or Zero Data Retention; a Free plan; Claude Code before
v2.1.281 or the desktop app before 1.13576.0 (code.claude.com/docs/en/artifacts,
"Availability", read 2026-10-25). The docs name the CLI and the desktop app; a cloud chat at
claude.ai/code published and woke on its page's comments on 2026-10-25, and the phone apps
read and write a page's data, but a publish from a chat started on the phone is unverified.
Then run `python3 tools/app.py published none` (the sync stops asking for a month) and carry on
here.

---

## Step 0: The right copy, and a private one (no questions)

Run `git remote get-url origin` (skip silently if it fails).

- **The app itself** (`https://github.com/aranculleton/last-job-search`, or a fork of it,
  which is public too). Stop: nothing personal ever goes here. Tell them they need their own
  private copy first, from the one link GitHub fills in for them (the app as the template,
  **Private** chosen), with the template page's own **Use this template** as the way when the
  form opens empty, as `python3 tools/claude_surfaces.py steps make-copy` prints; then a chat
  on that copy, saying "set me up". `python3 tools/app.py start` says the same.
- **Any other repo.** Check it is private, never by asking first: in a cloud chat
  `gh api repos/<owner>/<name> --jq .private` (it answers where `gh repo view` is refused), on a
  computer the same command, or the GitHub tools where the chat has them. **Public**: stop,
  and say why (setup writes their name, work history, pay and later every contact into
  tracked files, which a public repo shows to anyone) and how to make it private
  (`python3 tools/claude_surfaces.py steps make-private`). Never change it yourself.
  **Unknown** (no `gh`, no tools): ask them once to look: GitHub shows **Private** or
  **Public** beside the copy's name.

**Is it set up already?** Before anything is asked or written, `python3 tools/app.py start`
(every chat runs it first) has said, by its first line. It looks here, on master and on
every other chat's unlanded branch:

- **`set up`** (or **`set up elsewhere`**, which it brings in first, as its step says):
  the search is set up, and /setup never starts it again (that is `/reset`). Ask nothing,
  and never for a resume or anything else the copy already holds. **In a chat on their
  computer**: say only "Your search is already set up; this computer is ready for it too.",
  start the installs in the background (`python3 tools/env_check.py --fix`), write
  `PROFILE_READS = "browser"` in `profile/networking.py` if it is unset, and go straight on
  to the networking skill's "On a new computer" step: its browser, LinkedIn, the download,
  all without a question. **In a cloud chat**: say only "Your search is already set up.",
  and do what they ask; a part to change is `--section <name>`, below. Never overwrite a
  filled profile wholesale, and never put placeholders back into one.
- **`setup going in another chat`**: another chat is writing it. Say its one line ("Your
  setup is still going in your other chat; I'll be ready here once it's done.") and start
  nothing.
- **`setup stopped`**: say its line; on "carry on", finish this setup from what is written.
- **`setup self`**: this chat is the one setting up; carry on where it is.
- **`setting up`**: nothing anywhere. Set them up, from Step 1.

**`--section <name>`** (`history`, `search`, `market`, `voice`, `documents`, `boards`), run by
the person or by `/upgrade` in the background: do that section of `setup-sections.md` alone,
on the existing profile. Run from `/upgrade`, ask nothing: what the profile cannot answer is
written `[CONFIRM: ...]`, which a later session asks. A redo adds what the current method adds
and keeps every value already there: where it shows a value is wrong, the better one goes
beside it as `[CONFIRM: ...]`, never swapped in silently, and nothing is switched off or
narrowed. A setting `python3 tools/learned.py locked` lists is the person's own and is never
changed: record `learned.py offer` for it instead. Then
`python3 tools/build_versions.py record <section>`.

---

## Step 1: First message: start everything, ask two things (in the chat only with no page)

In the background, at once, none waiting on another (Bash with `run_in_background`):

- **Land the day's sync**: the first sync in a new copy brings the app in, and the local
  check is slow until that is on master (RUNBOOK.md, "Landing on master"). Open its pull
  request, run `./tools/ci_local.sh --quick`, and merge it, all in the background.
- **The tools**: in a cloud chat `./tools/setup_env.sh`; on their computer
  `python3 tools/env_check.py --fix`. Nothing is asked of them for either.
- **Job sites**: in a cloud chat, `python3 tools/env_check.py --say` prints the words to pass
  on, word for word, when this chat cannot reach job sites. It reaches the running chat
  within about a minute; setup carries on meanwhile, and only the search waits for it.

With a page, say only the line `app.py start` printed; the page asks these two. Without one
(a chat that cannot publish a page), ask them here instead.
Then say, in about these words and nothing more:

> Let's set up your job search. Two things to start:
> 1. Your resume: attach it (PDF or Word) or paste it.
>    No resume? Say "build one with me" and I'll make it with you.
> 2. The work you want next, and where you'd like to work.
>
> I'll do the research and the rest.

When job sites are blocked, the `--say` words go underneath, with "I'll keep setting you up
meanwhile."

---

## Step 2: On their reply: the first profile, the research, four questions

1. **Read what they sent** (setup-sections.md, `history`): every role, date, title, employer,
   place, result, skill, language, certification (held or in progress) and contact detail. A
   disagreement between documents is written `[CONFIRM: ...]`, never asked now. **"Build one
   with me"** (or no resume, in any words) is the guided history in the same section: the
   fastest source first, then one job a message from `python3 tools/history_interview.py ask`,
   passed on as it prints. The research below starts from their first reply, not the last.
2. **Write the first profile** at once, enough for the tools to run: `profile/person.json`
   (identity; documents from their country's defaults until research says otherwise),
   `01-candidate-profile.md` from the resume, and the place and work they named. Then
   `python3 tools/place.py started` (so any other chat sees a setup under way) and
   `python3 tools/place.py auto` (it records where they work when this chat can tell; nobody
   is asked), commit, push, and **land it on master
   now** (RUNBOOK.md, "Landing on master"), so a chat they open on their computer finds it
   and waits rather than starting again. Push after every step from here on, and land each:
   a dropped chat must never lose their answers.
3. **Read the market tables, then research only what they lack**, as soon as their country
   and field are known: `python3 tools/markets.py brief <country> --field <field> --level
   <graduate|mid|senior|executive> --region <state or province> --city <city> --employers
   <how many they named>` (leave out what you do not know yet). The app ships these tables
   for many countries, fields and levels: national, field, graduate, executive, regional
   and remote boards with what each board's own rules for automated readers allow
   (checked by code, with the date), eligibility wording, document conventions, where pay
   is published, the big metros' place names, a field's titles and interchangeable tools,
   every fact with its page and the day it was read. Write what it prints into `profile/`, keeping each source (setup-sections.md
   says where each part goes), and keep its last block, **Still to research**. Then
   **one** background agent (sonnet, no worktree) for those lines and nothing else, one
   scratch file per topic, `$SCRATCH/research/<topic>.md`, every claim with its source,
   following each topic's section of setup-sections.md: usually pay for their role, level
   and city (`market`), the towns around their city (`market`), anything about their field
   the tables do not hold (`boards`, `documents`), and where the people they should meet are
   named, `PEOPLE_SOURCES` (`voice`), which no table holds. With no table for their country,
   the brief says so and the agent covers every topic. One agent, never one per topic: each
   agent pays the app's whole instructions on every step it takes. Each target employer's
   hiring system is code, not an agent: `python3 tools/ats_boards.py --find "<Employer>"`,
   one per employer, all at once with Bash in the background (`boards`; it works before the
   profile is finished). The agent cannot ask the person anything: what needs their yes
   comes back to you. A board from a table is a lead like any other: it is searched only
   once `/add-portal` has built it, and that checks the board's rules again first.
4. **Ask four things, once**, with your own proposals filled in (on the page when there is
   one: `app.py propose` gives it your roles, and the answers come back in
   `profile/setup_answers.json`; in the chat only without one):

> Thanks. Four quick ones, then I'll get on with it:
> 1. Can you work in <country> without an employer sponsoring you, now and later?
> 2. What do you earn now, and what's the least you'd move for?
> 3. I'd search for <role A>, <role B> and <role C>. Right, or what would you change?
> 4. Any employers or kinds of work to avoid? And should your current employer not find out?

Skip any the resume already answered. Never ask them to name a job board, a hiring system, a
spelling, a pay source or any setting: those are yours.

---

## Step 3: Write the profile, while the research runs

Every file in `profile.example/`, written for them, each by its section of setup-sections.md;
`python3 tools/profile_names.py` lists every name the tools read and which they cannot do
without. The market tables' facts go in first, then each research file as it arrives, both
cited. Where they were not asked, use the default and never a question:

| Not asked | Written |
|---|---|
| Commute, remote, hybrid, on-site | Their metro area, and all three welcome |
| Tone | Plain and confident; their reactions correct it (`learned.py`) |
| Confidential | Yes when they are employed, unless they said otherwise |
| Notice period, achievements the resume gave no number for | `[CONFIRM: ...]`, asked in later sessions |
| Reading LinkedIn profiles | `PROFILE_READS = "browser"` where `place.py auto` prints it (a chat on their computer, or a cloud chat the desktop app started), written without asking; on a phone or the web, unset, so a paste |
| LinkedIn Premium | Unset: notes keep to a free account's limits; asked later |
| Their LinkedIn download | On a computer, requested at once by the networking skill's "On a new computer" step; on a phone or the web, asked later, by the brief |

Then the state files (setup-sections.md, the last section), and commit and push.

---

## Step 4: The first round is the proof

- **Start it the moment the search can run**: `person.json`, `search.py`, `roles.py`,
  `employers.py` and `boards.py` (an empty map is fine) written and pushed:
  `python3 tools/run_round.py --out rounds/r1` in the background, with about 70 minutes'
  timeout. It does not wait for a board being built; it searches what is there.
- **While it runs**: build the board that adds the most with `/add-portal` in the background
  (one whose own rules disallow it is built only on their yes while they are here, asked with
  the shortlist; setup-sections.md, `boards`); finish the remaining files;
  `python3 tools/build_versions.py record --setup`; `python3 tools/profile_upgrades.py`
  (only the questions for later may stay pending: anything else it lists is a step skipped
  here); `./tools/ci_local.sh --quick` (a failure naming an app-owned file is the app's:
  never edit it here). Commit and land it.
- **Their resume, if they had none**: `python3 tools/stage_picks.py general "$SCRATCH/general"`
  once the profile is written, while the round runs. It drafts, renders, checks and keeps a
  one-page resume for the roles they search for, with no letter; send it with the shortlist
  (CLAUDE.md, "Every output is shown") and paste the short copy it prints beside it. Someone
  whose resume is more than a year out of date is offered it once, in one line with the
  shortlist: "Want a fresh one-page resume from your profile too? Say "build my resume"."
- **When it finishes**, show the shortlist the way the job-scraper skill's Step 5 says,
  then offer to write the top pick. That is the test application: everything in `/apply`
  applies, the already-applied question first. A round that misses its target (exit 2) says so
  with its counts and what was tried, and says the boards still being built go into the next.

---

## Step 5: The brief, and the end

- **The brief is theirs to turn on.** Nothing is scheduled at setup: a brief costs a run
  every morning, so it starts only when they press the bell on their Brief (or Settings,
  Your brief), and then in the chat that answers the page, so no chat is made for it (the
  `app` skill, `brief` with `args.setup`). Where there is no page, and they ask for one in
  the chat ("set up my brief"), do the same here: automation/README.md, "For Claude".
- **Where they will work** is never asked: pass on the one line `python3 tools/place.py next`
  prints.
- **Finished**: `python3 tools/place.py finished`, commit, and land it; with a page, bring its
  data up to date (`python3 tools/app.py view`, the `app` skill), so it shows the shortlist
  and the brief. This chat goes on answering the page. In a chat on their computer, go straight on to the networking skill's "On a
  new computer" step.
- **Then, in a few lines:**

> **You're set up.** Everything about you stays in your private copy.
>
> - Say **"find me jobs"** for a new shortlist. It searches <the job sites that are on, by
>   name> and the careers pages of <the employers in `boards.py`>.
> - Paste a posting, or its link, for a resume and cover letter written for it.
> - Say **"who should I talk to at <employer>?"** to find people worth contacting.
>
> Want a quick tour of everything else? Say **"show me around"**.

When they say "show me around", or ask what the app can do or how to use something, run
`python3 tools/tips.py tour` (or `tour <topic>`) and pass on what it prints, as it is.

Nothing more about LinkedIn: no notice, no warning and no question. The job search uses no LinkedIn account.
Claude never switches it off and never suggests it (setup-sections.md, `boards`). Signing in to LinkedIn, on a computer, is the reading step's own, when it needs it
(the networking skill).

---

## Design principles

- The person answers questions about themselves. Claude does the market research and writes
  every file, and never asks what a default or the research can answer.
- Nothing personal is written until the repo is known to be private. The app and any public
  repo are refused.
- `profile/` and the state files are the only things written. App-owned files are never
  edited; a person's rules go in `profile/CLAUDE.md`.
- Never invent a fact. Unconfirmed is `[CONFIRM: ...]`, and every researched setting cites
  where it came from.
- Nothing waits that need not: research, installs, board builds, checks and the first round
  run in the background, and every step is pushed as it finishes.
- Re-runnable: with a profile present it updates the part asked for and leaves the rest alone.
