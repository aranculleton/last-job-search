# Changelog

The app's history starts here. It began as a fork of
[MadsLorentzen/ai-job-search](https://github.com/MadsLorentzen/ai-job-search) at v1.7.0; that
project's history is archived, unmaintained, in [CHANGELOG-upstream.md](CHANGELOG-upstream.md).
Version numbers here are this app's own and do not track upstream's.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). An entry says what
changed and, where it matters, the failure that caused the change, because that is the part a
future session needs. `tools/sync_app.py` prints the lines a sync brings in, so write each one to
make sense to somebody whose repo just received it.

---

## [Unreleased]

### Added

- **`START_HERE.md`**, the five steps from this page to a working search, in plain words:
  make a private copy with "Use this template", let Claude see it, set up the cloud
  environment (the setup line and the job-board domains), say "set me up", and use it.
  Linked from the top of the README.

### Changed

- **A profile without employer tiers can meet the yield target.** `tools/fit.py` divided
  opportunity by a fixed 130 before multiplying it into priority, a number calibrated on a
  profile with tiers, leverage and core capabilities. Without them opportunity tops out at
  58, so no posting ranked above about 45 and every round reported MISSED after three
  expansions. The divisor is now 130 or the most your profile can score, whichever is lower
  (`opportunity.SCALE`; `OPP_SCALE` in `search.py` pins it). **A profile that can score 130
  ranks exactly as before**; one that cannot sees every priority rise in proportion, in the
  same order.
- **Networking looks for your colleagues, not a data team's.** `/network` searched every
  employer for data scientists, counted only data titles as "in function" (so a nurse's run
  would write every employer off as having no relevant presence), and read "I'm in
  marketing" in a reply as a mismatch for everybody. `profile/networking.py` now holds
  `TITLE_SETS`, `FUNCTION_TITLE`, `HANDS_ON_TITLE`, `HIRING_ROLE_NOUNS`,
  `HIRING_HEADLINE_NOUNS`, `OTHER_FUNCTIONS`, `OTHER_FUNCTIONS_MOVED`, `OWN_FUNCTION_WORDS`
  and optionally `NOT_HIRING_TITLES` (`None` for someone in sales).
  **After this sync, add them to your `networking.py`**: `/network` refuses to search
  without `TITLE_SETS`, and without `FUNCTION_TITLE` every in-market manager counts as in
  your function. `profile.example/networking.py` shows the shape (a data team's values).

Found by a sweep of the whole app for anything that assumed a data analyst a few years in,
in North America. **Nothing to do unless a default below is wrong for you**; each is a
setting now, and `python3 tools/profile_names.py` lists every one.

- **Experience thresholds are measured from your own `YEARS_HELD`.** They were fixed at 7, 9,
  11 and 13 years in `tools/fit.py` (6, 8 and 10 in `tools/opportunity.py`, and the screens'
  flags likewise), which is right for someone with four years: twenty years' experience lost
  points on "10+ years", and a new graduate lost nothing on "6+". If your scores move after
  this sync, this is why, and it is the fix.
- **`/interview` uses your own STAR examples** (`profile/07-interview-prep.md`). It read the
  app's guide, whose examples belong to the fictional example person. And `/apply` drafts your
  summary from the profile statement templates in your `profile/CLAUDE.md`, never from the
  example person's in `05-cv-templates.md`. If your `profile/CLAUDE.md` has none, add 2-3.
- **Your resume's page count and section order** are `documents.resume_pages` (default 1)
  and `documents.section_order` (default summary, experience, skills, education,
  certifications) in `person.json`; `fit_to_page.py` and `verify_batch.sh` follow them. A
  recent graduate can lead with education; a long career can take two pages.
- **The letter's "Dear" and "Page"** are `documents.salutation_prefix` and
  `documents.page_label`, for a letter in another language.
- **Your weekend** (`search.py` `WEEKEND`, default Saturday and Sunday) sets every
  business-day follow-up date. **Contract work** is docked 6 unless `OPP_CONTRACT = None`.
  `MANAGES_PEOPLE = True` stops the screen flagging roles with direct reports. The portal
  health probe's word is `CANARY_QUERY` (default "data").

Found by the first person set up outside data analysis. **If your profile was written before
this, three things to do after this sync**, all in `profile/`:

- **Your resume's Skills headings are yours now, and a resume will not render without them.**
  They were hard-coded as a data analyst's ("Languages and modelling", "Data engineering and
  cloud", "BI, tooling and delivery") and printed on everybody's resume. Set `LABELS` in
  `skills.py`: one `(line, heading)` per line, in your own words; `MERGE` and `MAX_PER_LINE`
  are optional (`profile.example/skills.py` shows the shape). Rendering stops with
  `NoHeadings` until you do.
- **No title is docked for its level unless your profile says so.** `tools/fit.py` docked
  every junior, graduate, intern or trainee title 25 points, and `tools/opportunity.py` docked
  those 25 and director, head-of and principal titles 12, for everybody. They now read
  `FIT_BELOW_LEVEL`, `OPP_BELOW_LEVEL` and `OPP_ABOVE_LEVEL` from `search.py`. If you are
  mid-career and want the old behaviour, copy the three patterns from
  `profile.example/search.py`. **If you cancelled the junior penalty in your profile** (a
  bonus for junior titles, say), take the cancellation out, or junior roles now score high
  twice over.
- **Your bullets' themes can be your own.** `tools/allocate.py` matched postings only against
  a data analyst's theme words, so a theme outside them scored nothing and bullets were picked
  on weight alone. Add `THEME_CUES` (theme -> the words postings use for it) to `bullets.py`;
  `python3 tools/allocate.py` names every theme no cue matches.

- **Every portal has a switch that works, and it is the person's.** The `enabled:` flag in
  a portal's `SKILL.md` used to switch off nothing a round did, because
  `tools/scrape_wide.py` called LinkedIn and freehire by name. It, `tools/hydrate.py` and
  `/scrape` now ask **`tools/portals.py`**: the `SKILL.md` default, then the person's
  `PORTALS` in `profile/search.py` (`{"linkedin-search": False}` turns LinkedIn off). A
  portal that is off is sent no search, probe or detail request. **`linkedin-search` and
  `freehire-search` are on by default**; `/setup` tells the person that LinkedIn's
  robots.txt disallows the guest endpoints the search uses, and the choice is theirs.
  `python3 tools/portals.py` prints what the next round searches and why.
- **A4 or US Letter follows the country.** `person.paper()` prints on US Letter across most
  of the Americas and A4 everywhere else, from `identity.country` in `person.json` (or
  `search.py` `PORTAL_COUNTRY`). `documents.paper` and `documents.letter_paper` still win
  where set, so **if your profile sets them only because the app once needed it, remove
  them** and let the country decide.
- **The guides no longer steer towards data work.** The networking skill and discovery
  playbook, the writing style's role-type language, `/expand`'s competency taxonomy and the
  upskill skill use field-neutral wording, with examples from several fields.
- **`/setup` writes `profile/` and nothing else.** It refuses the app itself and any public
  repo before a word is written, asks the person only plain questions about themselves,
  researches their market (boards, employer ATS, eligibility wording, pay, document
  conventions, place names) and writes every profile file in the shape of
  `profile.example/`, plus empty state files. It used to edit the app's own skill files,
  CLAUDE.md and the example CV, which the next sync would undo.
- **`/reset` has a `state` scope** and removes `profile/` whole rather than blanking files.
  It never deletes the app's templates and fonts.
- SECURITY.md, SETUP.md and the README describe the app as public and a person's copy as
  private.

### Fixed

- **`verify_batch.sh` no longer fails letters written the way the style guide asks.**
  `audit_letters.py` required the opening to name the role, which pushed every letter back
  to the "I am applying for the <role> role" opener `03-writing-style.md` bans; it now flags
  that opener instead, and asks for the role only when the batch holds two roles at one
  employer. The opening must still name one of your employers, but as people write it: "at
  Brindle & Hart" names Brindle & Hart Logistics. **If you call an employer something
  `roles.py` does not hold** ("Oakmere" for Oakmere Foods), add `known_as="Oakmere"` to that
  role; the outreach note's hook uses the same matcher.
- **A date running into a capitalised word is no longer a claim.** `check_numbers.py` read
  "2024 Weekend" as "2024 week" (and "12 monthly", "3 hourly", "2023 Daytime" likewise), an
  ungrounded number that failed the batch.
- **Ireland's DAC, CLG, UC and Teoranta, Canada's ULC, and "Pvt Ltd", "Pte Ltd", "Pty Ltd" and
  "Co., Ltd."** come off the salutation, the outreach note, the document file name and the
  company key, so the throttle sees "Acme DAC" and "Acme" as one employer. "Acme Pty Ltd"
  used to become "Acme Pty". A draft re-rendered after this sync for an employer with one of
  these forms is written under the shorter name.
- **A draft's file name is settled before it is rendered.** `fit_to_page.py` read a
  hand-written `abbr` ("FF") before the renderer replaced it with the derived one, so the
  last compile looked for a file never written; a draft with no `abbr` was a bare
  `KeyError` there, in `outreach.py` and in `record_drafts.py`. A shortlist row with none
  now says so and names the employer.
- **The leak scan no longer treats a placeholder as a person.** An employer entry such as
  "Projects", "Freelance" or "Career break" became a denylist entry, matched the app's own
  headings, and forced a rename on the person's resume. Placeholders are skipped; a real
  employer with such a word in its name ("Acme Projects") is still an entry.
- `/setup` checks for LaTeX and the job-board hosts first, and gives the environment settings
  then, so they can be changed before the session that needs them rather than after.
- The prefilter's title reason no longer says "analytics, data, modelling, risk or pricing";
  it names the profile's `POSITIVE` list.
- `tools/build_app.py` no longer writes a phone number out as an example: the one it had was
  a test person's own, and their leak scan failed on the app's file.

Found by the first end-to-end setup of a fictional person in a new market, from a fresh
template copy:

- **The leak scan failed for anyone without a North American phone number.** A non-North
  American number now yields its national grouping (with and without the trunk 0) instead of
  a three-digit slice that matched everywhere, and the reserved `example.*` domains the app's
  templates use are never entries (`build_app.phone_forms()`).
- **An app test read the person's own tracker**, and failed after a new repo's first `/apply`.
  It reads the example person's temporary state, as every app test does.
- **Scoring crashed on a profile shaped like the example.** The example's `FIT_MISSING` held
  pairs where `tools/fit.py` reads triples; a new test scores a posting against the example.
- **`tools/profile_names.py`** lists every name the tools read from a profile, whether a tool
  needs it, whether the example sets it, and where it is read; `/setup` uses it, and a test
  checks the example sets every name a tool cannot do without.
- `/setup` writes `seen_jobs.json` as `{"seen": {}}` (the tools read that key), commits before
  the checks that read the commit, states the role-heading shape, and says a Workday board
  cannot be guessed.
- The commit recipe in CLAUDE.md adds one existing path at a time: one `git add` with a path a
  new repo does not have yet staged nothing at all.
- The cover letter is printed on the profile's paper (`documents.letter_paper`, defaulting to
  `documents.paper`), no longer always US Letter.
- "Pty" is a company suffix; the duplicated-word check no longer fires on a phone number's
  repeated digit groups; the example's role headings use the shape the prep tools read;
  `/apply`'s rule on gaps now matches rule 8 of the writing style.

## [3.0.0] - 2026-10-14

The first release as a template: one app, any number of people, each in their own private repo.

### Added

- **Everything about a person lives in `profile/`.** Identity, history, bullets, skills, market,
  preferences and voice, read by every tool through `tools/person.py`. No tool names a person, an
  employer, a city or a currency of its own; a repo with no `profile/` starts with `/setup`.
- **`tools/personal_paths.py`, the one list of what belongs to a person**: the profile and the
  search's state (tracker, contact book, threads, documents, research). Everything else is the
  app's.
- **An example person, `profile.example/`.** Fictional, complete, and what the app's own tests run
  against, so the suite gives the same answer in the app and in a person's repo. A person's own
  tests live in `profile/tests/` and run in a separate process.
- **`tools/sync_app.py`.** A person's repo pulls the app's updates and never sends anything back.
  The first sync of a template-made repo merges unrelated histories; an app-owned file edited in a
  person's repo is put back and named; personal paths are never touched; `--check` reports how far
  behind and any drift.
- **`tools/build_app.py` and `tools/leak_scan.py`.** The app is built from a person's repo by
  removing every personal path, then scanned for anything of theirs that is left: contact details
  by shape, and every name and fact the person's own data holds, in every form it is written in.
  `tools/ci_local.sh` runs it on every check in a person's repo, and the app's CI runs it on every
  push.

### Changed

- **Private repos spend no Actions minutes by default.** Every CI job runs on a public repo or a
  manual dispatch; `./tools/ci_local.sh` runs the same checks locally, Python 3.10 leg included.
