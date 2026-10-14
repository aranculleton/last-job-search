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

- **LinkedIn is off by default, and a portal that is off is now actually off.**
  `linkedin-search` ships `enabled: false`: LinkedIn's robots.txt disallows every path for
  every crawler it does not name, its guest job endpoints included, and says automated
  access without its permission is "strictly prohibited", while a round sent it thousands of
  requests. The `enabled:` flag used to switch off nothing a round did, because
  `tools/scrape_wide.py` called LinkedIn and freehire by name; it, `tools/hydrate.py` and
  `/scrape` now ask **`tools/portals.py`**, and a portal that is off is sent no search, probe
  or detail request. **If your rounds relied on LinkedIn they will be thinner from now on.**
  Turning it back on is your decision, made knowing the above: `PORTALS =
  {"linkedin-search": True}` in `profile/search.py`. That is also where any portal is
  switched; its `SKILL.md` is the app's, and a sync would undo an edit there.
  `python3 tools/portals.py` prints what the next round searches and why.
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
