---
framework_version: 1.0.0
---

# Setup, section by section

`/setup` (`.claude/commands/setup.md`) is the order and the questions; this is how each part
of the profile is written. Read a section before writing its files, and read it alone when
`/setup --section <name>` or `/upgrade` redoes one part. Each part that writes the profile is
a versioned section, marked `<!-- section: <name> -->` (`tools/build_versions.py`): run alone
or in a full setup, record it (`record <section>`, or `record --setup` after a full setup),
which is how a better way of doing a section reaches this profile later, by itself.

`profile.example/` is a complete fictional person, and the shape every profile takes. For
each file in it, write the person's own version at the same name under `profile/`. Read the
example file first: its docstring and comments say what it holds and which tool reads it.
Keep every name the tools read (constants, keys, headings); change only the content. The
example sets only what it needs, so run `python3 tools/profile_names.py` for every name the
tools read from each module, which ones they cannot do without, and the file and line that
reads each: read that line for what a name means and what shape it takes before setting it,
and set the ones their market needs that the example leaves out.

---

## Who they are

<!-- section: history -->
- **What they sent.** Their resume (attached or pasted), a LinkedIn export, reference
  letters, or their own words. Extract: name and contact details; education (degree,
  institution, dates); every role (title, employer, dates, location, what they did and what
  came of it); skills and tools; languages and how well; certifications (and whether each is
  held or only in progress); awards. Cross-check dates and titles between documents; a
  disagreement is written `[CONFIRM: ...]` and asked in a later session, never before the
  profile is written. A LinkedIn "About" and reference letters are the best signal for how
  they work; label anything you infer from them as inferred.
- **No resume ("build one with me", or none in any words).** The fastest source first, so
  nothing they have already written is asked again: on their computer, their own LinkedIn
  page read in the browser the chat uses (the networking skill's reading step, which signs in
  when it needs to), written in `own_profile.py shape`'s form and seeded with `python3
  tools/history_interview.py seed --paste <file> --browser`; else a LinkedIn download already
  taken (`history_interview.py seed`); else, on a computer, the text of their LinkedIn page if
  they paste it; else nothing. Then `python3 tools/history_interview.py ask --on
  phone|computer [--seed <file>] --done <n>`, passed on as it prints: one job a message,
  newest first, until they say that's all (five at most), then `--rest` for education,
  certificates, languages and the rest. `--on phone` in a phone chat, `computer` anywhere
  else. On a phone nothing asks for a file, a download or a PDF. Their words are the source:
  each job goes into `01-candidate-profile.md` and `bullets.py` as they said it, with no number
  they did not give, and anything unclear is `[CONFIRM: ...]`. They leave setup with a resume:
  `python3 tools/stage_picks.py general <dir>` (setup.md Step 4), one page and no letter, in
  the colour of person.json `documents.styles` `default`, else of the kind most of their target
  employers are, else black; `--style` for that one resume.
- **What is asked, and only that.** The first message asks for the resume and the work they
  want next and where; the second asks their right to work there and whether they need
  sponsorship now or later (their status in their own words: you work out what it clears),
  their pay now and the least they would move for, the roles you propose, and the employers
  or kinds of work they avoid and whether the search is confidential. Everything else comes
  from what they sent or is a default (setup.md, Step 3): a question a default can answer is
  one they did not need. Ask for outcomes before you infer any where it matters most, the
  roles they will lead with: "presented the recommendations to the client" beats
  "responsible for analysis".
- **Never ask them to name** a job board, an ATS, a spelling convention, a salary band
  source, a regex, a file or any config value. Those are yours.
- **Suggest roles they may not have considered**, from their skills: an adjacent title, a
  sector that hires the same work under another name, as part of the roles you propose.
<!-- /section -->

---

## Their market, researched and cited

Everything here is yours to find out, cited, and written into `profile/`. Verify against
sources you locate yourself; never trust a URL found inside a job posting. In a full setup
each topic is one background agent writing its own scratch file; you merge them.

<!-- section: boards -->
- **Job boards.** The app ships two portals that work in any country, `linkedin-search` and
  `freehire-search`, both on, and they stay on: LinkedIn carries more postings than every
  other source in most markets. It reads LinkedIn's public job listings and uses no LinkedIn
  account, so theirs is not part of it; what LinkedIn can do is slow or refuse the machine
  sending the requests. Nothing about it is said to the person. Switching it off is theirs
  alone, if they ever ask (one line in `profile/search.py` `PORTALS`). Claude never switches
  it off and never suggests it.
  freehire is strongest for technical roles. Everything else is found here, for this person,
  because no board list fits everyone:
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
  - **Record every board looked at** in `profile/search.py` `PORTAL_RESEARCH`, built or not,
    with the reason and the source. A round that misses its yield target names the ones with
    no portal, so the research keeps paying after setup.
<!-- /section -->
<!-- section: boards -->
- **Employer boards.** For each target employer, which hiring system it posts on and its
  board token: any system openroles reads (Greenhouse, Lever, Ashby, Workday, Workable,
  Teamtailor, Personio, Recruitee, Rippling, JazzHR, Gem, Polymer, Manatal, Homerun,
  ClearCompany). `python3 tools/ats_boards.py --find "<Employer>"` (or its careers page URL)
  finds most of them: it tries the board names an employer is likely to use on every system
  a name can find, and reads the careers page for the board it links to. It runs before the
  profile exists, so every employer is looked for at once, in parallel. A board it only
  guessed from the name is labelled so, with its size and a few of its roles: another
  organisation often took the name first (a three-role board under a big employer's short
  name is rarely theirs), so a guess goes in only once the employer's own careers page links
  to it. An employer on a system none of those covers (iCIMS, Eightfold and others) often
  still publishes each job page for search engines: `--add careersite <careers site
  address>` reads it that way where its robots.txt allows, and says so when it does not.
  Re-check them with `tools/ats_boards.py --probe` once `profile/` exists. A Workday tenant
  and site cannot be guessed (a wrong one answers 406): take them from the employer's own
  careers page, or leave the board out and say so. These go in `profile/boards.py` and are
  how large employers that portals under-index reach a round.
<!-- /section -->
<!-- section: market -->
- **Eligibility.** The wording postings in their country use for citizenship, permanent
  residence, security clearance and sponsorship, and what their status does and does not
  clear. This is what the eligibility gate in `profile/search.py` matches, so get the
  phrasing from real postings.
<!-- /section -->
<!-- section: market -->
- **Pay.** Salary norms for their role, level and city, from sources you can cite: the
  walk-away floor, the target and the top of the band, in the local currency. Where they gave
  no floor, the researched one is written with `[CONFIRM: ...]`.
<!-- /section -->
<!-- section: documents -->
- **Documents.** Local conventions: resume or CV, photo or not, paper size, spelling variant,
  date format, how a letter is signed off. The renderer fits the resume to one page; where
  the market expects two, tell the person and record it in `profile/CLAUDE.md`.
<!-- /section -->
<!-- section: market -->
- **Places.** The names their area goes by in postings (the metro area, the towns around it,
  the region), the places worth a flag rather than a fail, and what counts as too far. What a
  round searches follows from it: `SCRAPE_LOCATIONS` is the home city first, the towns of the
  metro area a posting may name instead, and the country itself last, so a board that matches
  places exactly still returns the towns nobody listed and the location gate keeps the
  commutable ones. `SCRAPE_REMOTE_LOCATIONS` is where remote roles open to them are filed: their
  country, and, where they can work remotely for an employer abroad, the wider regions such
  employers post under (a continent, EMEA, worldwide), which the location gate passes.
<!-- /section -->
<!-- section: market -->
- **Languages.** Which languages postings in their market tend to require, for the language
  gate.
<!-- /section -->
<!-- section: search -->
- **Search terms.** The titles their target work is posted under, including the ones they
  did not think of, and the queries `/scrape` should run.
<!-- /section -->

---

## The profile's files

<!-- section: documents -->
### 1. Write `profile/person.json`
Identity (name, pronouns, file prefix, contact line, LinkedIn) and documents (noun, banned
nouns, spelling, paper, date format, headings, sign-off), from what they sent and the
research. The letter is printed on the resume's paper unless `documents.letter_paper` says
otherwise. Also, from their market and level: `resume_pages` (1 unless their market or a
long career expects 2), `section_order` (a recent graduate often leads with education), and,
for a letter in another language, `salutation_prefix` and `page_label`. Where they will work
is recorded by `python3 tools/place.py auto` once this file exists, or from their answer
with `python3 tools/place.py record computer|phone|both`. **How the page looks**
(`templates/doc_design.py`): write `documents.designs.kinds` from its `SUGGESTED_KINDS`,
keeping only the kinds their employer lists use (`classic` for banks, insurers, professional
services, law and the public sector; `modern` for technology companies, startups and software
products). Leave `documents.design` unset unless they said how they like their documents to
look, and then write only what they said (`doc_design.py set` or `adjust`). Never ask about
fonts, sizes or margins; the page size comes from their country (`person.paper`).
<!-- /section -->

<!-- section: history -->
### 2. Write `profile/01-candidate-profile.md`
The source of truth for every fact about them. Everything established, with the detail that
will not fit on one page kept under each role's "Additional detail available for tailoring".
Each role's heading is `### Title - Employer (dates), City`, the dash separating title from
employer, because the tools read the roles off those headings. Anything not yet confirmed is
written `[CONFIRM: ...]`, never guessed. Every one left is asked again, a few at a time at
the end of later sessions, until it is answered (the `unconfirmed-facts` profile upgrade):
nobody has to remember them.
<!-- /section -->

<!-- section: history -->
### 3. Write `profile/02-behavioral-profile.md`
How they work, from an assessment if they have one, or from their answers and references.
Inferred lines are labelled as inferred.
<!-- /section -->

<!-- section: market -->
### 4. Write `profile/04-job-evaluation.md`
Start from the app's template (`.claude/skills/job-application-assistant/04-job-evaluation.md`)
and fill every `[PLACEHOLDER: ...]`: their gates, match areas, salary table and preferences.
This is the copy scoring reads.
<!-- /section -->

<!-- section: history -->
### 5. Write `profile/07-interview-prep.md`
Three or four STAR examples from their real achievements, in their words, plus answers to the
hard questions their history invites. Stubs marked `[CONFIRM]` where details are missing.
Every story ends on a `Use for:` line naming, in quotes, the interview questions it answers
("Tell me about a model you built", "How do you handle conflicting numbers"): it is how
`tools/interview_pack.py` matches a story to a likely question, and a story without one is
reached by no question. Each hard answer sits under the question as its heading, in quotes,
with the answer as a `>` quote below it. An answer that argues against a kind of employer
("depth rather than rotating clients", "product companies rather than more consulting") ends
on a `Not for:` line naming it, so a pack never hands it over for that employer. The answer
about a permit or visa follows the disclosure rule they give: when they say only that they
are entitled to work, the answer is for when they are asked directly, and is never
volunteered. `profile.example/07-interview-prep.md` shows the shape.
<!-- /section -->

<!-- section: search -->
### 6. Write `profile/search-queries.md`
The queries `/scrape` runs: role titles in priority order (their main direction, their domain,
adjacent roles, a wider net), their key skills as search terms, and the location tiers.
<!-- /section -->

<!-- section: voice -->
### 7. Write `profile/CLAUDE.md`
The summary the root CLAUDE.md imports: identity, history in brief, skills, target sectors,
deal-breakers, and any rule that is theirs rather than the app's (how they want to come
across, what must never be said, confidentiality). Include 2-3 **profile statement templates**,
one per main role type they want, built from their own strongest evidence: `/apply` drafts the
resume summary from these, never from the example person's in `05-cv-templates.md`. Then
"This search's automation": the brief's days, time and zone once it is made.
<!-- /section -->

<!-- section: search -->
### 8. Write the rest of `profile/`
`roles.py` (chronology, titles, education, certifications), `bullets.py` (every achievement
as a themed bullet, more than any one page needs), `skills.py` (what they hold, what they do
not, and the honest bridges between, with `FAMILIES` for the tools their field treats as
interchangeable that `tools/bridges.py` FAMILIES does not already list), `search.py` (pay,
gates, locations, titles, what the scrape searches), `employers.py`, `boards.py`,
`networking.py` (their voice: opener, a line about them, the ask, their home city and
timezone; on a free account the whole connection note is 200 characters, so the opener, the
line about them and the ask together stay near 120), `claims.py`, `screening.py` (standard
form answers, sponsorship answered exactly as their status allows), `10-triage-blockers.md`,
`12-scoring-brief.md` and `13-positioning.md`. `routines.json` is written when the brief is
made (`tools/routines.py record`), not before.

`PROFILE_READS` is written without asking: `"browser"` in a chat on their computer or a cloud
chat the desktop app started (`python3 tools/place.py auto` prints it), where people's
profiles are read in that browser; on a phone or the web it is left unset, so a note rests on
what they paste. `LINKEDIN_PLAN` is left unset (notes keep to a free account's 200
characters, which fits either plan) and asked later by its profile upgrade.
`CONNECTIONS_EXPORT`: on a computer, the networking skill's "On a new computer" step requests
their LinkedIn download at once; on a phone or the web the brief asks for it later.

Settings the example's values would get wrong for anybody outside its field, level or
market, so write each one for this person, never copy it:
<!-- /section -->

<!-- section: documents -->
- **The Skills headings**, `LABELS` in `skills.py`: one `(line, heading)` per line, in their
  own words for their work (a nurse's are not a data analyst's). Each `line` is a category
  used in `ITEMS` (or a `MERGE` target), and the items in that category print under it. A
  resume will not render without them.
<!-- /section -->
<!-- section: search -->
- **The scoring vocabulary**, every `FIT_*` and `OPP_*` name in `search.py` (`FIT_BANDS`,
  `FIT_CORE`, `FIT_DOMAIN`, `FIT_ROLE_SHAPE`, `OPP_CORE`, `OPP_TITLE_FAMILY` and the rest):
  the example's are a mid-career analyst's, and copied they mis-rank anyone else. Write them
  from the person's field and level, then score two or three invented postings (a clear
  match, a role above them, a different field) and check the order is right.
<!-- /section -->
<!-- section: voice -->
- **Their outreach words**, `voice.py` (`OUTREACH_ASKS`, `OUTREACH_OPENING`): optional; the
  defaults use their `documents.noun`.
<!-- /section -->
<!-- section: search -->
- **The screen's job-family flags**, `SCREEN_WRONG_FAMILY` and `SCREEN_HOMONYMS` in
  `search.py`: the job families that are not theirs, and the words that name two different
  jobs in their field (the example's are an analyst's: "modelling" that means valuation).
  Optional; unset, nothing is flagged on them. Flags order the queue and never cut.
<!-- /section -->
<!-- section: search -->
- **Their level**, `FIT_BELOW_LEVEL`, `OPP_BELOW_LEVEL` and `OPP_ABOVE_LEVEL` in `search.py`:
  the titles below and above them, which are ranked down, never cut. For someone early in
  their career "junior" and "graduate" are the target, so leave them out of the below-level
  patterns.
<!-- /section -->
<!-- section: history -->
- **Their themes**: a bullet's themes come from `tools/allocate.py` `THEME_CUES`, which is a
  data analyst's list. Add the themes their work needs, with the words postings use for each,
  as `THEME_CUES` in `bullets.py`; `python3 tools/allocate.py` names any theme no cue matches.
<!-- /section -->
<!-- section: search -->
- **`YEARS_HELD`** in `search.py`: their years in the work they are applying for. Every
  experience threshold is measured from it.
<!-- /section -->
<!-- section: market -->
- **Their working week and contract preference**, in `search.py`: `WEEKEND` where it is not
  Saturday and Sunday, `OPP_CONTRACT = None` for someone who wants contract, locum, supply or
  seasonal work, and `MANAGES_PEOPLE = True` for someone who has had direct reports.
<!-- /section -->
<!-- section: market -->
- **`CANARY_QUERY`** in `search.py` where "data" is not a word every board in their market
  has thousands of postings for (another language, or a field where it is rare).
<!-- /section -->
<!-- section: voice -->
- **Who they network with**, in `networking.py`: `TITLE_SETS` (the job titles of the people
  to find: hiring authority, senior peers, their own function, recruiters), `FUNCTION_TITLE`
  (a title on a team in their function), `HIRING_ROLE_NOUNS` (what a hiring post in their
  field calls the role), and for reading replies `OTHER_FUNCTIONS` and `OWN_FUNCTION_WORDS`.
  `/network` will not search without `TITLE_SETS`; the example's are a data team's.
  `OPENALEX = True` only where the people worth meeting in their field publish papers
  (research science, pharma, academia, quantitative finance); leave it off otherwise.
  `NOT_HIRING_REASON` says in their terms why revenue titles are skipped, and
  `SPAM_BULK_ROLES` is the role list that marks a staffing harvest: drop their own job from
  it if it is there (a nurse, a technician).
- **Where their people are named**, in `networking.py` `PEOPLE_SOURCES`: research it, never
  ask it. From their field, level and country, pick the 6 to 12 kinds in
  `tools/network/sources.py` `KINDS` that name the people they should meet, best first, each
  as `(kind, why it pays for them)` or `(kind, why, the exact search)` where their field has
  its own place: the professional body whose branch committees name people, the country's
  official staff directory for a public-sector search, the firm directories of their city
  for a lawyer, the repositories for an engineer, the graduate recruiters for a student.
  Search for each to check it names real people at employers like theirs before it goes in,
  and cite what you found in a comment. `python3 tools/network/sources.py` prints the
  result. A graduate's plan leads with alumni, school features and early-careers recruiters;
  a senior person's with team pages, press and rosters; anyone's with their own connections.
- **Their connections**: on a computer, requested at once by the networking skill's "On a new
  computer" step; on a phone or the web, asked for later by the brief. What they attach is
  taken with `python3 tools/network/sources.py import-connections <it>` (the whole download,
  the ZIP or its folder, is saved and its message history imported in one step, never read
  straight from where they downloaded it), or `CONNECTIONS_EXPORT = "declined"` on a no.
<!-- /section -->

<!-- section: boards -->
### 9. Build their job boards
In the background, once the research names them: run `/add-portal` for the board that adds
the most coverage for them, and for the next if it is quick. A portal already built for them
is brought up to the current `/add-portal` too (its frontmatter, the contract, a live test),
so a better way of building boards reaches the ones they have. Each one is verified live
before it counts (its Step 4), and from then on every round searches it at every place in
`SCRAPE_LOCATIONS`, and for remote roles where the board can filter for them, with nothing
else to wire. A board whose robots.txt disallows the search is built only on their yes, while
they are present, never by a background agent. Write `PORTAL_LOCATIONS` only where the board
cannot read those names, and mark each built board `"status": "built"` in `PORTAL_RESEARCH`.
Boards not built yet keep an entry saying why (lower coverage, a login wall, robots.txt,
blocked by this session's network policy), and are offered again when a round comes back
thin. `python3 tools/portals.py` shows the result: what the next round searches, and what was
researched and not built.

Never ask for their email or to connect anything: the job round and the brief are their
alerts, inside Claude.
<!-- /section -->

<!-- section: none -->
### 10. Write the state files
At the repo root, each with the header row from its counterpart in `profile.example/state/`
and nothing else: `job_search_tracker.csv`, `network_contacts.csv`, `network_threads.csv`.
And `job_scraper/seen_jobs.json` as `{"seen": {}}` and `job_scraper/do_not_target.json` as
`{"companies": {}}`. The tracker and the seen-jobs file are ignored by `.gitignore` on
purpose: `python3 tools/save_state.py` stages them (CLAUDE.md's persistence rule), and
`.gitignore` is never edited. A portal built here (`.agents/skills/<name>/`) is theirs, and
takes a plain `git add`.
<!-- /section -->

---
