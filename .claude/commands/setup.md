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

---

## Step 0: The right copy, and a private one (no questions)

Run `git remote get-url origin` (skip silently if it fails).

- **The app itself** (`https://github.com/aranculleton/last-job-search`, or a fork of it,
  which is public too). Stop: nothing personal ever goes here. Tell them they need their own
  private copy first: on the app's page, **Use this template**, then **Create a new
  repository**, with **Private** chosen, as
  `python3 tools/claude_surfaces.py steps make-copy` prints, then a chat on that copy,
  saying "set me up".
- **Any other repo.** Check it is private, never by asking first: in a cloud chat
  `gh api repos/<owner>/<name> --jq .private` (it answers where `gh repo view` is refused), on a
  computer the same command, or the GitHub tools where the chat has them. **Public**: stop,
  and say why (setup writes their name, work history, pay and later every contact into
  tracked files, which a public repo shows to anyone) and how to make it private
  (`python3 tools/claude_surfaces.py steps make-private`). Never change it yourself.
  **Unknown** (no `gh`, no tools): ask them once to look: GitHub shows **Private** or
  **Public** beside the copy's name.

**Is it set up already?** Before anything is asked or written,
`python3 tools/place.py state`. It looks here, on master and on every other chat's unlanded
branch, and says which:

- **here** (or **landed** or **branch**, which it brings in first, as its `do:` line says):
  the search is set up, and /setup never starts it again (that is `/reset`). Ask nothing,
  and never for a resume or anything else the copy already holds. **In a chat on their
  computer**: say only "Your search is already set up; this computer is ready for it too.",
  start the installs in the background (`python3 tools/env_check.py --fix`), write
  `PROFILE_READS = "browser"` in `profile/networking.py` if it is unset, and go straight on
  to the networking skill's "On a new computer" step: its browser, LinkedIn, the download,
  all without a question. **In a cloud chat**: say only "Your search is already set up.",
  and do what they ask; a part to change is `--section <name>`, below. Never overwrite a
  filled profile wholesale, and never put placeholders back into one.
- **going**: another chat is writing it. Say its one line ("Your setup is still going in
  your other chat; I'll be ready here once it's done.") and start nothing.
- **stopped**: say its line; on "carry on", finish this setup from what is written.
- **self**: this chat is the one setting up; carry on where it is.
- **none**: nothing anywhere. Set them up, from Step 1.

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

## Step 1: First message: start everything, ask two things

In the background, at once, none waiting on another (Bash with `run_in_background`):

- **Land the day's sync**: the first sync in a new copy brings the app in, and the local
  check is slow until that is on master (CLAUDE.md, "Master is the trunk"). Open its pull
  request, run `./tools/ci_local.sh --quick`, and merge it, all in the background.
- **The tools**: in a cloud chat `./tools/setup_env.sh`; on their computer
  `python3 tools/env_check.py --fix`. Nothing is asked of them for either.
- **Job sites**: in a cloud chat, `python3 tools/env_check.py --say` prints the words to pass
  on, word for word, when this chat cannot reach job sites. It reaches the running chat
  within about a minute; setup carries on meanwhile, and only the search waits for it.

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
   `python3 tools/place.py auto` (it records where they work when this chat can tell, and
   otherwise hands you one question for the end), commit, push, and **land it on master
   now** (CLAUDE.md, "Master is the trunk"), so a chat they open on their computer finds it
   and waits rather than starting again. Push after every step from here on, and land each:
   a dropped chat must never lose their answers.
3. **Start the research in the background** as soon as their country and field are known:
   **one** background agent (sonnet, no worktree) that writes one scratch file per topic,
   `$SCRATCH/research/<topic>.md`, every claim with its source (you write `profile/` from
   them), following each topic's section of setup-sections.md:
   - job boards for their country, city, field and level, and whether each may be read (`boards`);
   - pay for their role, level and city (`market`);
   - eligibility wording, place names, languages, and the local document conventions
     (`market`, `documents`);
   - where the people they should meet are named, `PEOPLE_SOURCES` (`voice`).
   One agent, never one per topic: each agent pays the app's whole instructions on every
   step it takes, so five cost about five times as much for the same research. Each target
   employer's hiring system is code, not an agent: `python3 tools/ats_boards.py --find
   "<Employer>"`, one per employer, all at once with Bash in the background (`boards`; it
   works before the profile is finished). The agent cannot ask the person anything: what
   needs their yes comes back to you.
4. **Ask four things, once**, with your own proposals filled in:

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
without. Merge each research file as it arrives, cited. Where they were not asked, use the
default and never a question:

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
- **When it finishes**, show the shortlist the way CLAUDE.md's "Job Search Behaviour" says,
  then offer to write the top pick. That is the test application: everything in `/apply`
  applies, the already-applied question first. A round that misses its target (exit 2) says so
  with its counts and what was tried, and says the boards still being built go into the next.

---

## Step 5: The brief, and the end

- **The brief, set up with no questions.** List their scheduled tasks (`list_triggers`, every
  page) and run `python3 tools/routines.py brief --triggers <each page>`. A brief that exists,
  under any name, is attached to and never made twice. In a cloud chat, with none, it prints
  the calls to make, in order (`create_session` on their copy, `create_trigger` bound to it,
  and a one-off first brief: never `fire_trigger`), then `routines.py record`; make them, and
  tell them its one line. On a computer it says what to do (CLAUDE.md, Automation).
- **Where they will work**: if `place.py auto` handed you its question, ask it now, record the
  answer (`python3 tools/place.py record computer|phone|both`), and pass on the one line
  `python3 tools/place.py next` prints.
- **Finished**: `python3 tools/place.py finished`, commit, and land it. In a chat on their
  computer, go straight on to the networking skill's "On a new computer" step.
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
