# Changelog

> **Claude, if a sync just printed this line and nothing about profile upgrades:** this repo's
> `tools/sync_app.py` was older than the one it brought in, so it could not apply the app's
> improvements itself. Run
> `python3 tools/profile_upgrades.py --after-sync` now and do what it prints. From the next
> sync on, the sync does this by itself.

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

- **Every improvement to the app reaches what you already have, by itself.** A sync always
  brought the app's new code, but not what the old code had already made: the profile your
  `/setup` wrote, the job boards it built, your call-prep documents, drafts not yet sent,
  postings ruled out under older rules. Those stayed as they were, and nothing told you the
  app now did them better. Every part of the app that leaves something in your repo is now
  versioned, and your repo records which version made what it has
  (`profile/build_versions.json`). When a part gets better in a way worth redoing, it is
  redone with no one asking: `/upgrade` in the background for a part of setup, the boards,
  drafts, interview packs, research, contacts or upskilling plans; the sync itself for
  prep documents; every round for postings ruled out by an older screen. A profile with no
  record is dated from when it was made, so one set up on the first release redoes every
  part of setup improved since, starting with your job boards. A redo adds and corrects but
  never removes: a value it would change goes beside yours as a question. Anything that
  needs your consent (your scheduled tasks) is asked, a few at a time. Changing how any part
  is done, or adding any file to the app, now fails the app's CI until that decision is made.
  No profile upgrade: this is what lists them.
- **Profile upgrades apply themselves.** Listing what a profile was missing and waiting for a
  yes meant nothing happened: nobody knows which of nineteen upgrades matter, so nobody asked.
  Now, when the sync lists any, Claude starts `/upgrade` in a background agent and gets on with
  what you asked; it researches and builds your job boards, writes the settings your field needs
  and the rest, from your profile, one commit each. At the end of its reply it tells you what
  changed and how to undo each (`git revert`). Only what needs you is asked, at most three
  questions at the end of a session: whether to read your LinkedIn job alerts, and every fact
  in your profile still marked `[CONFIRM: ...]`, which is now asked until it is answered instead
  of waiting for someone to run `/setup` again. The twice-weekly shortlist takes the app's
  updates and applies the upgrades before its round, so a board it builds is searched that
  round. The morning brief is unchanged.
  No profile upgrade: this is what applies them.
- **Profile upgrades: what the app added since you set up, and what it needs from you.** `/setup`
  runs once, so a part of the app that needs something on your side (your job boards researched,
  a setting with no safe default, a portal rebuilt) never reached a profile written before it.
  `tools/profile_upgrades.py` checks your repo for each one, and every sync now ends by listing
  what is pending, with what runs it and how long it takes; the twice-weekly shortlist carries
  the same line. **If you set up before 15 October 2026,** your next sync lists the upgrades
  waiting for you. This sync is the old copy of the sync and cannot, so the session runs
  `python3 tools/profile_upgrades.py` once to see them now. Nothing runs without a yes.
  No profile upgrade: this is what lists them.
- **Your LinkedIn job alerts can feed every round.** LinkedIn's alert emails are its own match
  for you, and they carry roles a keyword search ranks out of reach. Set `JOB_ALERT_QUERY` in
  `profile/search.py` (off unless you set it, because it reads your inbox) and the job round
  searches Gmail for those emails only, `tools/job_alerts.py` takes the job ids from them and
  fills each posting from LinkedIn's own page, and `run_round.py --alerts` screens and scores
  them with everything else. Built and tested on invented alert emails; the LinkedIn fetch was
  checked live. If your first real alerts yield nothing, say so: the id pattern is the one
  thing a real email could prove wrong.
  Profile upgrade: `job-alerts`.
- **Every round searches the job boards built for you.** A portal made by `/add-portal` for
  your country, field or level used to run only when you typed `/scrape`; `tools/scrape_wide.py`
  called LinkedIn and freehire by name and nothing else. Now any portal that is on and follows
  the portal contract is searched, health-checked and hydrated in every round, scheduled ones
  included, each kept to the `crawl-delay` its `SKILL.md` declares (one request a second when
  it declares none), on its own thread so LinkedIn and freehire send exactly the requests they
  did. A portal is called only when its `SKILL.md` says `contract: 1` (`/add-portal` writes it
  once the CLI takes the round's flags). A board that fails three requests in a row, or runs
  past 20 minutes, is stopped and the round goes on; its detail fetches get 15. `PORTAL_LOCATIONS`
  in `profile/search.py` gives a board its places as it writes them.
- **`/setup` researches and builds your boards.** It finds the boards that serve your country,
  city, field and level, checks each one's robots.txt, builds the best one or two with
  `/add-portal`, and records every board it looked at, built or not, with its source, in
  `profile/search.py` `PORTAL_RESEARCH`. `python3 tools/portals.py` lists the ones with no
  portal, and a round that misses its yield target names them.
- **`START_HERE.md`**, the five steps from this page to a working search, in plain words:
  make a private copy with "Use this template", let Claude see it, set up the cloud
  environment (the setup line and the job-board domains), say "set me up", and use it.
  Linked from the top of the README.

### Changed

- **The app ships no country's job boards.** The four Danish portals (`jobindex-search`,
  `jobnet-search`, `jobdanmark-search`, `jobbank-search`) are deleted: the app is for anyone,
  anywhere, and a board for one market belongs to the people in it. The app keeps
  `linkedin-search` and `freehire-search`, which work in any country. Every other folder in
  `.agents/skills/` is now yours (`tools/personal_paths.py`): a sync never touches it or calls
  it drift, and the app's leak scan fails if one reaches the app. **If you search Denmark and
  had one of the four on,** this sync deletes it. Build it again with `/add-portal`, which makes
  it a portal every round searches. Putting the old one back (`git checkout <this sync's
  commit>^1 -- .agents/skills/<name>`) gives one `/scrape` can run by hand only: it predates
  the portal contract, so rounds skip it.
  had one of the four on,** this sync deletes it; put it back as your own with
  `git checkout <this sync's commit>^1 -- .agents/skills/<name>` and commit, or build it
  fresh with `/add-portal`.
  Profile upgrade: `missing-portal`.
- **The screen's job-family flags and two networking reasons are your profile's.**
  `tools/score_posting.py`'s wrong-family and homonym flags ("reporting and dashboard building
  is the whole job", "'modelling' here is valuation") were an analyst's, and the networking
  revenue-role reason said "dressed as technical" to everybody. They are now `SCREEN_WRONG_FAMILY`
  and `SCREEN_HOMONYMS` in `search.py` and `NOT_HIRING_REASON` in `networking.py`, with neutral
  defaults; `SPAM_BULK_ROLES` in `networking.py` can take your own job off the staffing-spam
  list. **If you are an analyst and want the old flags**, copy the example's
  `SCREEN_WRONG_FAMILY`, `SCREEN_HOMONYMS` (`profile.example/search.py`) and
  `NOT_HIRING_REASON` (`profile.example/networking.py`) into your profile.
  Profile upgrade: `screen-flags`.
- **`person.json`'s keys are listed with everything else.** `python3 tools/profile_names.py
  person` shows every key a tool reads, whether it is needed or optional, whether the example
  sets it, and where it is read.
- **The evaluation template is written for any work status.** `04-job-evaluation.md` assumed a
  permit holder; a citizen now writes one line, and a free-movement row covers EU/EEA and
  Swiss, Common Travel Area and Trans-Tasman citizens. **If your profile is a citizen's and
  was written from the old template**, nothing breaks; `/setup --section market` rewrites it.
  No profile upgrade: nothing breaks, and the rewrite only tidies a citizen's eligibility gate.
- **Scheduled briefings have two set-ups that work, written out step by step.**
  `automation/README.md` now walks through **(a)** one chat per task ("Job search: morning
  brief", and "Job search: shortlist" for the twice-weekly round, whose key and prompt file
  stay `job_round`), created with your private repo and each task bound to its own chat,
  whose reply is the briefing; or **(b)** each task made in the
  Claude app's Routines screen with the repo ticked and notifications on, for a push. It
  gives the exact prompt each task stores (`python3 tools/routines.py stub <key>` prints
  yours) and how to test without `fire_trigger`. `_common.md` makes the final reply the
  message and depends on no relay. **If your registry has an `ops_session` and a relay**,
  nothing changes for you: that older set-up is still recognised and still relays, and
  the README says why never to rebuild that chat (a chat made now is refused the hand-off).
  `python3 tools/routines.py check` validates `profile/routines.json` (prompt files exist,
  ids well formed and unique, every cron carries `CRON_TZ`), and `ci_local.sh` runs it.
  A long-lived scheduled chat is capped with `CLAUDE_CODE_AUTO_COMPACT_WINDOW=200000` on a
  cloud environment only those chats use; the app's `.claude/settings.json` is synced to
  everyone, so a per-model cap there would squeeze every chat on that model.
  No profile upgrade: scheduled briefings are optional, set up from `automation/README.md`.
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
  No profile upgrade: every profile already sets `YEARS_HELD`.
- **`/interview` uses your own STAR examples** (`profile/07-interview-prep.md`). It read the
  app's guide, whose examples belong to the fictional example person. And `/apply` drafts your
  summary from the profile statement templates in your `profile/CLAUDE.md`, never from the
  example person's in `05-cv-templates.md`. If your `profile/CLAUDE.md` has none, add 2-3.
  Profile upgrade: `interview-prep`.
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
  Profile upgrade: `market-week`.

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
  Profile upgrade: `level`.
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
  Profile upgrade: `country`.
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

- **Postings blocked for good by a skip that was never a verdict, and internal postings
  surfaced.** `seen_jobs.json` skips the throttle derives afresh every run blocked their
  postings permanently: a referral hold kept 59 postings at one employer out for a month
  after the referral had converted, and a do-not-target entry's skips outlived its review
  date. A referral hold, do-not-target, the company throttle, a same-employer duplicate
  and the candidate's bar no longer block from the record (the live hold is applied at the
  prefilter instead, so they still cost no fetch while it lasts), and neither do older
  rounds' queue decisions ("not scored this round", "never read by a model"); an
  `excluded` entry citing any of them is treated the same. A posting on a Workday
  internal site (`/Privileged/`), which an outside applicant cannot use, is dropped at the
  prefilter with the reason `eligibility: internal Workday site`; a profile can name its
  employers' other internal sites in `search.py` `WORKDAY_INTERNAL_SITES`. No profile
  upgrade: both take effect on the next round.
- **Finding people: the same person twice, the wrong people as tier 1, employers written off
  on nothing.**
  - "Already contacted" matched on names alone. A name in another script reduced to
    nothing and matched the first person at that employer; "Søren Møller" and "Łukasz"
    lost letters; the profile URL every result carries was never compared. It now
    matches on the URL first, keeps every script's letters, and folds ø, ł, ß and the rest.
    Employers key alike written with "&" or "and", with accents or without.
  - Tier 1 is a live hiring post about your own work: another job seeker's "I'm looking
    for my next opportunity", a marketing director's "we're hiring", a remote role in
    another country and an undated headline no longer count. Post permalinks, where those
    posts live, are kept with their exact date instead of being filtered out.
  - A result with no location is kept as unverified, not read as somebody elsewhere; an
    empty search records nothing; "no relevant presence" holds for 90 days, not for ever.
  - Places match on whole words: Aylesbury is not Bury, Manchester, New Hampshire is not
    Manchester, and a home city of two words gets its metro.
  - A hiring post with a few emoji and an in-house recruiter are no longer dropped as
    spam, and "after 8 years at Acme I lead data" is tenure, not a departure.
  - Searches use the employer's everyday name, alumni are searched once per run, drafts
    are kept in `documents/network/<id>/draft.md`, and LinkedIn's connections export in
    `documents/linkedin/Connections.csv`, if you add it, puts the people you already know
    first. No profile upgrade: the new title settings default to the English ones.
- **Networking messages you could not send, and replies read the wrong way round.**
  - Connection notes were capped at 300 characters and InMail drafted for everyone, which is
    a Premium account's limits: a free account (a 200-character note, a handful of
    personalised notes a month, no InMail except to an Open Profile) was handed drafts it
    could not send. The limits now follow your LinkedIn plan (`profile/networking.py`
    `LINKEDIN_PLAN`), the free ones until you say, and the weekly budget counts drafts
    already queued. Profile upgrade: linkedin-plan.
  - An InMail had no subject line and none of the first note's rules. It now has a
    subject of a few words naming the common ground (never "Quick question" or a job),
    the first note's shape and one paragraph of evidence.
  - "Not interested, thanks." and "Please stop messaging me." read as friendly short
    replies and drew a call invitation; "not hiring, but happy to chat" read as a no, so
    two of them closed a booked call. Both now read right, "talk to <a colleague>" reads as
    a referral, and a thread at `call_booked` or `referral_in_progress` is never stopped.
  - An empty `/reply` on a thread we had already answered re-read their old message and
    drafted a CV already sent; it is now a quiet thread, and `/reply` drafts no second
    nudge.
  - "Do you have any openings on your team?", "could you refer me" and five other plain
    job asks passed the first-note check; a note whose common ground is their hiring
    drops the "looking for my next role" clause; a question ends in a question mark.
  - The per-application outreach note is checked by the same tone rules, says its
    character count, comes with a version that fits a connection request, and no longer
    tells you to ask someone who never replied for a referral. `/apply` now checks who is
    already talking to the employer before drafting, and writes the note.
- **A job board built for you searched your home city and nothing else.** A round sent a
  person's own board one place, the first in `SCRAPE_LOCATIONS`, unless someone had listed
  its places by hand, so the towns around it, the region and the country went unsearched
  while LinkedIn searched all of them; and it never asked any board for remote roles. Every
  board now searches every place in `SCRAPE_LOCATIONS`, home deep and the rest two pages, and
  remote roles where it can filter for them (`remote: true`, `--remote`). `/add-portal` builds
  CLIs that read places as LinkedIn writes them, cover a commute's radius around each, and
  take `--remote`; `/setup` writes the whole metro area and the country as places, and the
  wider regions an employer abroad files remote roles under. Boards you already have are
  rebuilt this way in the background (boards version 3), and your places widened (market
  version 3). No profile upgrade: build_versions carries it.
- **A portal that went quiet is reported again.** `run_round.py` read the health probe's file
  after pruning had deleted it, so a portal returning nothing was never named and a MISSED
  round blamed the market. It is read first now, and a DOWN portal is named on every round,
  met or missed.
- **`ci_local.sh` is green again in a person's repo.** The check that no real scheduled-task or
  chat id is committed to the app read every tracked file, so after a sync it failed on
  `profile/routines.json` and `handoff/`, the person's own files and exactly where their ids
  belong. It now skips what `tools/personal_paths.py` calls personal.
- **A vacancy open only to the employer's own staff is cut.** A test of the scheduled
  shortlist ranked an "Internal Mobility" posting eighth; nothing screened for it. A title
  saying "internal mobility", "internal only" or "internal applicants only", or a sentence
  restricting the role to current or existing staff, is now a cut with the quote. "Internal
  candidates will be prioritised" and "Internal Audit" are not. Postings in another language
  use `INTERNAL_ONLY_TITLE` and `INTERNAL_ONLY` in `search.py`.
- **The shortlist message reads well on a phone.** One role per block (role, employer and
  score first, location, posting date and one reason on the next line, the link on its own
  line), warm-route notes under their role, and a failure line only when a step failed.

- **A junior role no longer scores mentoring bullets up.** `tools/allocate.py` counted the
  bare word "junior" as a mentoring cue, so every posting for a junior role pulled your
  mentoring bullets forward. It now counts "junior" only as the object of the work
  ("develop junior", "train junior", "support junior"), plus "upskill".
- **`/setup`'s environment check is `python3 tools/env_check.py`.** The old inline check read
  any HTTP status as success, so a host your network policy refused still "answered", and it
  never looked at Ashby, Workday, pypdf or bun. It now names a policy refusal as one, catches
  a pypdf that is installed but panics (the `cffi` case), checks bun, and probes LinkedIn,
  freehire, Greenhouse, Lever, Ashby and your first Workday board.

- **Messages say your word for the document.** The email composer wrote "My resume is
  attached", the referral ask "Happy to send my resume", one outreach-note close "does not
  fit on a resume", and the reply guidance "Do not attach a file named CV; the attachment
  says resume", whatever `person.json` `documents.noun` said. All of them now use your noun,
  the guidance names your banned word, and `tone.check` reports any word in
  `documents.banned_nouns` in a message (`document_noun`; "CV" keeps its old rule), so
  "my resume" no longer passes in a CV market. "Resume" as a verb is not flagged.

- **A credential stated as "essential", "mandatory" or "must be registered" is a credential
  gate.** "A recognised accounting qualification (ACA, ACCA or CIMA) is essential" passed,
  so a full application could be drafted for a job you cannot hold. The sentence must still
  name one of your profile's `DESIGNATION` credentials, and "desirable" still wins.
- **A short posting is still read for its bars.** A body under 400 characters skipped every
  gate; "Active SC clearance required" or "Fluency in Welsh is essential" in a snippet went
  through. Every gate now reads what there is, and the row is still marked `thin`.
- **Pay is read however the posting writes it.** "EUR 35,000", "45 000 €", "GBP 45,000 to
  52,000", "€45-55k", "£45k-50k pa" and "₹12,50,000" (and lakh, crore and LPA) were read as
  no salary stated, so a range under your floor was never flagged and a high one never
  earned its points. The market's symbol or `CURRENCY_CODE` may sit before or after the
  figure, a range's bare end takes the other end's currency, and "per annum", "p.a.",
  "DOE", "package" and "CTC" are pay cues. A single figure counts only right after a pay
  label ("Salary: €38,000"; "up to" is a top, "from" is a minimum and is not scored as one).
  `tools/opportunity.py` now reads the screen's range rather than its own pattern, so the two
  cannot disagree. **Scores move after this sync** where postings state pay in a form the
  old pattern missed (a "k" figure, a code, a space separator); that is the fix.

- **`verify_batch.sh` no longer fails letters written the way the style guide asks.**
  `audit_letters.py` required the opening to name the role, which pushed every letter back
  to the "I am applying for the <role> role" opener `03-writing-style.md` bans; it now flags
  that opener instead, and asks for the role only when the batch holds two roles at one
  employer. The opening must still name one of your employers, but as people write it: "at
  Brindle & Hart" names Brindle & Hart Logistics. **If you call an employer something
  `roles.py` does not hold** ("Oakmere" for Oakmere Foods), add `known_as="Oakmere"` to that
  role; the outreach note's hook uses the same matcher.
  No profile upgrade: the audit names the employer when a short name needs `known_as`.
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
