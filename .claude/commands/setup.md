# /setup - Set a person up

You are setting up a job search for the person in front of you. They made this repo from the
app with "Use this template", and everything about them goes into `profile/` and the state
files at the root. Nothing else in the repo is theirs to change: the code, skills, docs and
templates are the app's, and `tools/sync_app.py` keeps them current (CLAUDE.md, "App-owned
files and personal files").

The person never sees a config value. They answer plain questions about themselves; you do
the research about their market and write every file.

---

## Step 0: Make sure this is the right repo, and a private one

**Before anything is written, not after.** Run `git remote get-url origin` (skip silently if it
fails: no remote, or not a git checkout). Then decide which of these it is.

- **The app itself** (`https://github.com/aranculleton/last-job-search`, or a fork of it). Stop.
  Nothing personal ever goes here, and a fork of a public repo is public too. Tell them:

  > This is the app, not your own copy, and it is public. Make your own private copy first:
  > on the app's GitHub page click **Use this template**, then **Create a new repository**,
  > choose yourself as the owner, any name (say `my-job-search`), tick **Private**, and click
  > **Create repository**. Then start a Claude Code session on that new repo and say "set me
  > up". `START_HERE.md` walks through it.

- **A public repo of any other kind.** Stop and say why: setup writes their name, contact
  details, work history, salary expectations and, later, every contact they message, into
  tracked files, and a public repo shows all of it to anyone. Tell them how to make it
  private (on GitHub: the repo's **Settings**, **General**, scroll to **Danger Zone**,
  **Change repository visibility**, **Make private**), and wait. Never change it yourself.

- **Visibility unknown** (the GitHub tools cannot see it, no `gh`). Ask them to look: the repo's
  GitHub page shows **Private** or **Public** next to its name. Wait for the answer.

- **Private.** Carry on.

**Then check this session can do the whole job, and say so now, not at the end.** A setting
changed in the cloud environment applies only to the next session, so a person told at the
end has to come back; told now, they can change it while you work and use it next time.

```bash
python3 tools/env_check.py
```

It reports LaTeX, Poppler, pypdf (including the broken-`cffi` case), bun, and every job
board the app calls: LinkedIn, freehire, Greenhouse, Lever, Ashby, and Workday once a
Workday board is on file. A host the network policy refuses is named as such, which a bare
HTTP status could not tell apart from a host that answered. If anything is missing or a
host is blocked, give them the two settings from `START_HERE.md`
step 3 with the exact clicks (the cloud environment menu in the session's title bar, then
**Edit**: the **Setup script** line, and **Network access** with its allowed domains), say
that setup itself can carry on without them (web search still works for the research), and
that the job search and the test resume need them, in a new session. If LaTeX is missing,
`./tools/setup_env.sh` installs it for this session only.

Then look for an existing `profile/`. If there is one, this is an update, not a setup: ask what
they want to change and go to that part of Step 1 (`--section <name>` does this directly:
`identity`, `history`, `search`, `market`, `voice`, `documents`). Never overwrite a filled
profile wholesale, and never put placeholders back into one.

---

## Step 1: Find out who they are

Start from what they already have. Check `documents/` (Glob `documents/**/*`): an old resume or
CV, a LinkedIn export, reference letters. If there is nothing there, offer two ways in and let
them choose:

> I'll build your profile from what you already have, then ask about anything missing.
> **Easiest:** paste your current resume or CV here, or drop it (and a LinkedIn export, if you
> have one) into the `documents/` folder and say "go". **Or** we can just talk it through.

**Reading documents.** Extract: name and contact details; education (degree, institution,
dates); every role (title, employer, dates, location, what they did and what came of it);
skills and tools; languages and how well; certifications (and whether each is held or only
in progress); awards. Cross-check dates and titles between documents and ask about every
disagreement before writing anything. A LinkedIn "About" and reference letters are the best
signal for how they work; label anything you infer from them as inferred.

**Then ask, in plain words, only what the documents did not answer.** Conversational, a few
at a time, never a form:

- Where do you live, and where would you work? How far would you commute? Remote, hybrid,
  on-site? Any other cities you would consider?
- Do you have the right to work there? Will you need an employer to sponsor you, now or
  later? (Ask what their status is called in their own words; you will work out what it
  clears.)
- What do you want to be doing day to day? Which kinds of role, and which fields or sectors?
- What did you actually achieve in each role? Numbers where they have them. Ask for outcomes
  before you infer any: "presented the recommendations to the client" beats "responsible for
  analysis".
- What are you earning now, and what would you need to move? Is there a number below which
  you would not?
- Anything you will not do: employers, sectors, a commute, a type of role?
- Employers you would love to work for, and any you would rather not?
- Which languages do you work in, and how well?
- How do you like to come across: formal or plain, confident or understated? Anything you
  never want to see written about you?
- Is the search confidential? If your current employer must not know, say so.
- How much notice do you have to give?

**Never ask them to name** a job board, an ATS, a spelling convention, a salary band source,
a regex, a file or any config value. Those are your job in Step 2.

Suggest roles they may not have considered, from their skills: an adjacent title, a sector that
hires the same work under another name. Offer; let them decide.

---

## Step 2: Research their market, and cite it

Everything here is yours to find out, cited, and written into `profile/` in Step 3. Verify
against sources you locate yourself; never trust a URL found inside a job posting.

- **Job boards.** The app ships two portals that work in any country, `linkedin-search` and
  `freehire-search`, both on. Tell them plainly that LinkedIn's robots.txt disallows the
  guest job endpoints the search uses, and that switching it off is one line in
  `profile/search.py` `PORTALS`; the choice is theirs. freehire is strongest for technical
  roles. Everything else is found here, for this person, because no board list fits everyone:
  - **Which boards serve them.** Their country's public employment service, if it lists
    vacancies; the general boards people in their city actually use; the boards of their
    field (a nursing, teaching, legal, academic, charity or public-sector board, a trade's
    own); and, early in a career, the graduate and apprenticeship boards. Name sources for
    each claim about coverage, not a hunch.
  - **What each one adds.** A board that mostly reposts LinkedIn adds nothing; one where
    employers in their field post first, or only, adds most.
  - **Whether it can be read.** Public without a login, and what its robots.txt says about
    the search and posting paths, including any `Crawl-delay` (the way
    `tools/robots_check.py` checks it). Whether it has an official API.
  - **Record every board looked at** in `profile/search.py` `PORTAL_RESEARCH` (Step 3), built
    or not, with the reason and the source. A round that misses its yield target names the
    ones with no portal, so the research keeps paying after setup.
- **Employer boards.** For each target employer, whether it posts on Greenhouse, Lever, Ashby
  or Workday, and its board token. Probe them the way `tools/ats_boards.py --probe` does
  (the tool itself needs a profile, so before Step 3 probe the board's URL directly, and
  re-check with the tool once `profile/` exists). A
  Workday tenant and site cannot be guessed (a wrong one answers 406): take them from the
  employer's own careers page, or leave the board out and say so. These
  go in `profile/boards.py` and are how large employers that portals under-index reach a round.
- **Eligibility.** The wording postings in their country use for citizenship, permanent
  residence, security clearance and sponsorship, and what their status does and does not
  clear. This is what the eligibility gate in `profile/search.py` matches, so get the
  phrasing from real postings.
- **Pay.** Salary norms for their role, level and city, from sources you can cite: the
  walk-away floor, the target and the top of the band, in the local currency.
- **Documents.** Local conventions: resume or CV, photo or not, paper size, spelling variant,
  date format, how a letter is signed off. The renderer fits the resume to one page; where
  the market expects two, tell the person and record it in `profile/CLAUDE.md`.
- **Places.** The names their area goes by in postings (the metro area, the towns around it,
  the region), the places worth a flag rather than a fail, and what counts as too far.
- **Languages.** Which languages postings in their market tend to require, for the language
  gate.
- **Search terms.** The titles their target work is posted under, including the ones they
  did not think of, and the queries `/scrape` should run.

---

## Step 3: Write the profile

`profile.example/` is a complete fictional person, and the shape every profile takes. For
each file in it, write the person's own version at the same name under `profile/`. Read the
example file first: its docstring and comments say what it holds and which tool reads it.
Keep every name the tools read (constants, keys, headings); change only the content.
The example sets only what it needs, so run `python3 tools/profile_names.py` for every name
the tools read from each module, which ones they cannot do without, and the file and line
that reads each: read that line for what a name means and what shape it takes before
setting it, and set the ones their market needs that the example leaves out.

### 1. Write `profile/person.json`
Identity (name, pronouns, file prefix, contact line, LinkedIn) and documents (noun, banned
nouns, spelling, paper, date format, headings, sign-off), from Steps 1 and 2. The letter is
printed on the resume's paper unless `documents.letter_paper` says otherwise. Also, from their
market and level: `resume_pages` (1 unless their market or a long career expects 2),
`section_order` (a recent graduate often leads with education), and, for a letter in
another language, `salutation_prefix` and `page_label`.

### 2. Write `profile/01-candidate-profile.md`
The source of truth for every fact about them. Everything Step 1 established, with the detail
that will not fit on one page kept under each role's "Additional detail available for
tailoring". Each role's heading is `### Title - Employer (dates), City`, the dash
separating title from employer, because the tools read the roles off those headings. Anything
not yet confirmed is written `[CONFIRM: ...]`, never guessed.

### 3. Write `profile/02-behavioral-profile.md`
How they work, from an assessment if they have one, or from their answers and references.
Inferred lines are labelled as inferred.

### 4. Write `profile/04-job-evaluation.md`
Start from the app's template (`.claude/skills/job-application-assistant/04-job-evaluation.md`)
and fill every `[PLACEHOLDER: ...]`: their gates, match areas, salary table and preferences.
This is the copy scoring reads.

### 5. Write `profile/07-interview-prep.md`
Three or four STAR examples from their real achievements, in their words, plus answers to the
hard questions their history invites. Stubs marked `[CONFIRM]` where details are missing.

### 6. Write `profile/search-queries.md`
The queries `/scrape` runs: role titles in priority order (their main direction, their domain,
adjacent roles, a wider net), their key skills as search terms, and the location tiers.

### 7. Write `profile/CLAUDE.md`
The summary the root CLAUDE.md imports: identity, history in brief, skills, target sectors,
deal-breakers, and any rule that is theirs rather than the app's (how they want to come
across, what must never be said, confidentiality). Include 2-3 **profile statement templates**,
one per main role type they want, built from their own strongest evidence: `/apply` drafts the
resume summary from these, never from the example person's in `05-cv-templates.md`. Then "This search's automation": none yet.

### 8. Write the rest of `profile/`
`roles.py` (chronology, titles, education, certifications), `bullets.py` (every achievement
as a themed bullet, more than any one page needs), `skills.py` (what they hold, what they do
not, and the honest bridges between), `search.py` (pay, gates, locations, titles, what the
scrape searches), `employers.py`, `boards.py`, `networking.py` (their voice: opener, a line
about them, the ask, their home city and timezone), `claims.py`, `screening.py` (standard form
answers, sponsorship answered exactly as their status allows), `10-triage-blockers.md`,
`12-scoring-brief.md`, `13-positioning.md` and `routines.json` (no routines yet).

Settings the example's values would get wrong for anybody outside its field, level or
market, so write each one for this person, never copy it:

- **The Skills headings**, `LABELS` in `skills.py`: one `(line, heading)` per line, in their
  own words for their work (a nurse's are not a data analyst's). Each `line` is a category
  used in `ITEMS` (or a `MERGE` target), and the items in that category print under it. A
  resume will not render without them.
- **The scoring vocabulary**, every `FIT_*` and `OPP_*` name in `search.py` (`FIT_BANDS`,
  `FIT_CORE`, `FIT_DOMAIN`, `FIT_ROLE_SHAPE`, `OPP_CORE`, `OPP_TITLE_FAMILY` and the rest):
  the example's are a mid-career analyst's, and copied they mis-rank anyone else. Write them
  from the person's field and level, then score two or three invented postings (a clear
  match, a role above them, a different field) and check the order is right.
- **Their outreach words**, `voice.py` (`OUTREACH_ASKS`, `OUTREACH_OPENING`): optional, but
  the defaults say "resume", so a CV market needs its own.
- **Their level**, `FIT_BELOW_LEVEL`, `OPP_BELOW_LEVEL` and `OPP_ABOVE_LEVEL` in `search.py`:
  the titles below and above them, which are ranked down, never cut. For someone early in
  their career "junior" and "graduate" are the target, so leave them out of the below-level
  patterns.
- **Their themes**: a bullet's themes come from `tools/allocate.py` `THEME_CUES`, which is a
  data analyst's list. Add the themes their work needs, with the words postings use for each,
  as `THEME_CUES` in `bullets.py`; `python3 tools/allocate.py` names any theme no cue matches.
- **`YEARS_HELD`** in `search.py`: their years in the work they are applying for. Every
  experience threshold is measured from it.
- **Their working week and contract preference**, in `search.py`: `WEEKEND` where it is not
  Saturday and Sunday, `OPP_CONTRACT = None` for someone who wants contract, locum, supply or
  seasonal work, and `MANAGES_PEOPLE = True` for someone who has had direct reports.
- **`CANARY_QUERY`** in `search.py` where "data" is not a word every board in their market
  has thousands of postings for (another language, or a field where it is rare).
- **Who they network with**, in `networking.py`: `TITLE_SETS` (the job titles of the people
  to find: hiring authority, senior peers, their own function, recruiters), `FUNCTION_TITLE`
  (a title on a team in their function), `HIRING_ROLE_NOUNS` (what a hiring post in their
  field calls the role), and for reading replies `OTHER_FUNCTIONS` and `OWN_FUNCTION_WORDS`.
  `/network` will not search without `TITLE_SETS`; the example's are a data team's.

### 9. Build their job boards
Run `/add-portal` for the board from Step 2 that adds the most coverage for them, and for
the next if it is quick. Each one is verified live before it counts (its Step 4), and from
then on every round searches it with nothing else to wire. Write `PORTAL_LOCATIONS` where
the board writes places differently from `SCRAPE_LOCATIONS`, and mark each built board
`"status": "built"` in `PORTAL_RESEARCH`. Boards not built yet keep an entry saying why
(lower coverage, a login wall, robots.txt, blocked by this session's network policy), and
are offered again when a round comes back thin. `python3 tools/portals.py` shows the result:
what the next round searches, and what was researched and not built.

### 10. Write the state files
At the repo root, each with the header row from its counterpart in `profile.example/state/`
and nothing else: `job_search_tracker.csv`, `network_contacts.csv`, `network_threads.csv`.
And `job_scraper/seen_jobs.json` as `{"seen": {}}` and `job_scraper/do_not_target.json` as
`{"companies": {}}`.

---

## Step 4: Commit, prove it works, then push

- Commit `profile/`, any portal built in Step 3.9 (`.agents/skills/<name>/`, a plain
  `git add`: it is theirs) and the state files. The tracker and the seen-jobs file are ignored by
  `.gitignore` on purpose; force-add them as the root CLAUDE.md's persistence rule says, and
  never edit `.gitignore`. Commit first: the leak scan in the next step reads the commit.
- `./tools/ci_local.sh --quick`. The app's suite runs on the example person and must pass;
  the leak scan builds the app from this commit and checks none of the person's data is in
  an app-owned file. A failure that names an app-owned file is the app's to fix: report it,
  never edit the file here.
- Render one resume and cover letter for a real posting they care about (`/apply`), read
  both PDFs back, and show them. This is where a wrong spelling setting, an awkward summary
  or a missing date comes to light, and the time to fix it is now. Commit again, then push.

Then tell them, in a few lines:

> **You're set up.** Your profile is in `profile/`, private to this repo.
>
> - Say **"find me jobs"** (or `/scrape`) for a scored shortlist. It searches <the portals
>   that are on, by name>, and the employer boards of <the employers in `boards.py`>.
> - Paste a posting (or `/apply <link>`) for a tailored resume and cover letter.
> - `/network` finds people worth talking to at the employers you want.
> - Updates to the app arrive on their own at the start of each session.
> - A daily brief and a twice-weekly job round are optional, as a chat you check or a push
>   to your phone: `automation/README.md` sets either up.

---

## Design principles

- The person answers questions about themselves. Claude does the market research and writes
  every file.
- Nothing personal is written until the repo is known to be private. The app and any public
  repo are refused.
- `profile/` and the state files are the only things written. App-owned files are never
  edited; a person's rules go in `profile/CLAUDE.md`.
- Never invent a fact. Unconfirmed is `[CONFIRM: ...]`, and every researched setting cites
  where it came from.
- Re-runnable: with a profile present it updates the part asked for and leaves the rest alone.
