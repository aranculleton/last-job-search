---
name: scrape
description: >
  Finds new job postings matching your profile via installed portal-search CLIs
  (LinkedIn, freehire, local job boards, and any skills added with /add-portal; whichever
  are on, per tools/portals.py) and employer ATS boards. Deduplicates
  across runs. Triggers on: job scrape, find jobs, search jobs, new jobs, job search,
  scrape jobs, /scrape
allowed-tools: Read, Write, Edit, Glob, Grep, Bash(bun --version), Bash(bun run .agents/skills/*/cli/src/cli.ts *), WebFetch, WebSearch, Agent, AskUserQuestion
---

# Job Scraper

---

## The rules every search keeps

These are the rules CLAUDE.md summarises, in full. Most are enforced in code; this is what
the code is doing and why.

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
  or a posted range under target (bar the one salary cut below). Those are scoring inputs; the
  role still surfaces and the candidate decides. Enforced in `tools/fit.py`, which weights every
  gap by how hard they asked and by what sits next to it, and in `tools/text_screen.py`, where a
  degree minimum and a range above the cut line are flags rather than cuts.
- **Only these are hard cuts**, because no framing survives them, and each one carries the
  quoted sentence it was cut on: an **eligibility** bar the profile cannot clear (a citizenship,
  residency or clearance requirement, or a requirement to live elsewhere), a **language**
  requirement (or a title written in another language), a **location** the Location table fails,
  a **professional credential** gate (actuarial exams, an accounting or engineering licence), a
  role whose **core is a discipline the person does not hold** that the profile names as a
  different job (`search.py` `RESEARCH_ML`, research machine learning for an analyst; nothing for
  a researcher), a vacancy **open to the employer's own staff only** ("internal applicants only",
  an "Internal Mobility" title), and a stated salary range whose **top** sits below the person's
  cut line (`SALARY_CUT_BELOW` in `profile/search.py`, well under the walk-away floor: a different
  job level, not a negotiation). Those are different jobs, not missing skills. Everything else
  gets ranked. A top between the cut line and the floor is a flag, never a cut, in
  `tools/text_screen.py` and in `tools/score_posting.py`, which reads extracted fields.
- **Every posting ruled out is written back to `seen_jobs.json`** with `tools/exclude.py add`,
  which stores `status: "excluded"`, a checkable `exclusion_reason`, a date and what the ruling
  rests on, so it never resurfaces while that holds. A ruling under the person's screening
  rules lapses when the part it rests on changes (`--rests-on "triage #4"`, or a reason citing
  "blocker 4"; with neither, any change to the rules) and the posting is screened again when
  next found; one in the person's own words holds until `exclude.py lift`. **An exclusion stands
  only while today's rules would still cut it** (`throttle.is_stale_exclusion`): one resting on a
  named part of the person's rules stands while that part does, and any other is judged by its
  reason. Eligibility, a language, a credential, a different discipline, internal-only and a fact
  about the posting (closed, a duplicate) stand; a pay reason stands only on a range topping out
  below `SALARY_CUT_BELOW`; a place only where the location gate still fails the place the entry
  recorded; a degree, a score or a years bar never. A round records the text screen's own cuts
  this way by itself (`tools/text_screen.py --seen`, which `run_round.py` passes), each with its
  quote, so the next round drops them before hydrate fetches them again. The prefilter's drops
  (age, place, title) are not recorded: they are decided again for free, before any fetch, and
  thousands a round would bury the rulings. The gate that enforces
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
  top falls below the walk-away floor gets flagged alongside the score, and even then it
  is a decision input, not an exclusion (the cut line above is the one exception). See "How much
  weight salary actually gets" in `04-job-evaluation.md`.

### Portals and employer boards

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
  the employers named in `profile/boards.py` straight from their ATS (every system the
  vendored openroles reads: Greenhouse, Lever, Ashby, Workday, Personio, Teamtailor and the
  rest) or their careers site (`careersite`), which is how large employers that a portal
  under-indexes reach a round,
  and `scrape_wide.py` calls it, so `run_round.py` needs nothing extra. `--probe` re-checks
  every token. A board whose robots.txt disallows it is refused, and so is SmartRecruiters
  by its API's; the reasons are recorded beside each.

## One command

`python3 tools/run_round.py --out rounds/<name> --jobage 14` runs every stage of a round in order and stops at the ranked shortlist. See `RUNBOOK.md`. When it cannot run, `manual-round.md` beside this file has every stage written out to do by hand: read it only then. Its step numbers are the ones cited below.

## How It Works

This skill searches job portals using the **installed portal-search CLIs** in
`.agents/skills/` (plus WebSearch as a fallback), using queries from your profile.
It deduplicates against previously seen jobs and the application tracker, scores every
surviving candidate against the fit framework in `profile/04-job-evaluation.md`, and presents a
ranked shortlist. A run that does not surface enough passing roles expands its search and
goes again rather than reporting a thin result.

## Invocation

The user triggers this skill by saying things like:
- "Find new jobs"
- "Scrape for jobs"
- "Any new positions?"
- "/scrape"

Optional arguments:
- A focus area, e.g. "/scrape data science" or "/scrape demand planning"
- "broad" to run all search categories, e.g. "/scrape broad"
- "health" to run the portal health check only (`manual-round.md` Step 4.75), without searching, deduplicating, or presenting jobs - e.g. "/scrape health", or "/scrape health linkedin" to probe one portal even if disabled


### Step 5: Present Results

One line of counts, then the table, then a line only for what is off. Never more.

```
**P of N cleared the pass bar (60+), Q of them strong (75+); target 5 and 2: met** (or: missed after R rounds)

| # | Score | Verdict | Title | Company | Location | Salary | Deadline | Check | Apply |
|---|-------|---------|-------|---------|----------|--------|----------|-------|-------|
| 1 | 82 | Strong fit | ... | ... | ... | stated range, or `not stated` | ... | what to check first | [Apply](https://...) |
```

- **Sorted by score, highest first**, with the score shown. Never alphabetically, by portal or
  by posting date, and never an unscored posting.
- **Every row carries a working apply link**, and so does every posting you later draft
  documents for. The link is the posting URL stored in `seen_jobs.json`, which already
  resolves to the posting itself rather than to a listing page. When documents are produced
  for a posting, repeat its link next to them.
- **Check** says what needs checking before applying, and any red flag: a mass-posting
  pattern ("posted in 6 cities"), a **stated** salary range whose top is below the walk-away
  floor, an unstated on-site expectation, a language level below the posting's bar. An absent
  salary range is not a red flag. A row's warm route from the contact book goes here too
  (`warm_route_note`: "DO NOT APPLY COLD" and who; `outreach_pending_note`): those are the
  referral links.
- **A line only when something is off**: `skipped (disabled): <portals>` when a portal is
  switched off (`python3 tools/portals.py` says which), so an opt-out is never silent;
  `fallback (websearch): <portals>` when results came from the search fallback, which can be
  stale (omit the line when every portal ran its CLI); one `health: <portal> - <what>` line for each portal the round (or
  `manual-round.md` Step 4.75) found degraded, broken or inconclusive; and when the target was
  missed, a short note: the count against target, the expansions run, the likely blocker and
  the next move. Never pad the table with sub-60 postings.
- **A portal found broken**: after the report, offer to switch it off until it is fixed. For
  the app's two portals (`linkedin-search`, `freehire-search`) that is a `PORTALS` entry in
  `profile/search.py` (`{"freehire-search": False}`), never an edit to their `SKILL.md`,
  which a sync puts back; for a portal built for this person by `/add-portal` it is
  `enabled: false` in that portal's own `SKILL.md` frontmatter. Only with the user's
  confirmation, and never edit anything else in the skill.
- LinkedIn people-search links for a recruiter or a peer at an employer
  (`manual-round.md` Step 4.5) only when the person asks: `/network` is the route to people.

### Step 5.5: Stop at the shortlist

The run ends at the table. Nothing is drafted unasked, and nothing is drafted before the
already-applied question ("The rules every search keeps", items 5 and 6, at the top of this
skill). Ask once:
> "Which of these should I take forward? And have you already applied to any of them?"

A yes to the second is recorded as a tracker row at `applied` with the date they give. Each
pick goes to `/apply`, which reuses the round's score and asks nothing already answered here.

Do **not** suggest `/rank` after a normal run: the run already scored everything it presented (a round's scores are in `documents/rounds/<round>.json`; on the manual path `manual-round.md` Step 3 wrote them to `ranked`), so `/rank` would only score them again. `/rank` is for the two cases `/scrape` does not cover: re-scoring after a change to the candidate profile or `profile/12-scoring-brief.md` (`/rank --all`, which skips permanent exclusions), and scoring a backlog added outside the normal flow. (`/rank` sets the `ranked` and `expired` status values in `seen_jobs.json`; treat both as already-seen for dedup purposes.)

### Step 6: Update Tracker (Optional)

If the user decides to apply to any job, the tracker row is written by **job-application-assistant Step 3b**, which Step 5 already routes into - do not add a second row here. Only when the user says they applied to something outside that path, add a row using the header and the match-then-update rule in `/outcome` Step 1.

---

---

## Important Rules

1. **Never fabricate job postings.** Only present jobs from actual CLI search/detail output or WebSearch/WebFetch results.
2. **Respect deduplication.** Always check seen_jobs.json AND job_search_tracker.csv before presenting.
3. **Focus on configured geographic area.** Skip jobs that require relocation or are clearly outside commute range.
4. **Only open positions.** Skip postings with expired deadlines or those marked as closed.
5. **Be efficient with detail fetches.** Don't run `detail` or WebFetch on every search hit - pre-filter by title/snippet, then fetch only promising matches.
6. **Parallel searches.** Run portal CLI searches in parallel; use WebSearch only for gaps the CLIs don't cover.
7. **No automated people lookups.** Referral contacts (`manual-round.md` Step 4.5) are LinkedIn search links only - never fetch or scrape LinkedIn people-search result pages programmatically.
8. **Health checks are bounded and honest.** `manual-round.md` Step 4.75 spends at most one probe, one retry, and (in `health` mode) one detail fetch per portal - a diagnosis, not a crawl. A rate-limit is never evidence of breakage. Health verdicts come only from observed CLI output; a portal that could not be tested is reported as inconclusive, never guessed. The on/off switch (`PORTALS` in `profile/search.py`, or `enabled:` in a person's own portal) is the only thing the health check may edit, and only with confirmation.
9. **Score everything you present, and rank by that score.** No posting reaches the user unscored, and the table is ordered by score. A list of unranked links is a failed run.
10. **An under-target run expands before it reports.** `manual-round.md` Step 3.5's expansion ladder runs before the summary is written, up to 3 rounds (`run_round.py --expand` widens the pages itself and prints the other rungs, Step 3.5). Never pad a thin result with sub-60 postings, and never relax a gate or the location filter to make the yield target.
11. **Flag distribution patterns, never accuse.** The mass-posting signal (`manual-round.md` Step 2.5) describes how a listing is being distributed, not a claim that the employer is a scam. Never name a company as fraudulent or untrustworthy - present the observation and let the user decide.
12. **Paginate. Never cap.** A search walks `--page 1..N` until a page comes back empty or wholly duplicated, and covers every location the PASS set covers, not just the biggest city. `run_round.py` does both; `manual-round.md` Step 1b says how by hand.
13. **Full scoring is one posting per agent, never batched** (Tier 3, `manual-round.md` Step 3), whatever batch size `/rank` uses.
