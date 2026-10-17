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
  `tools/text_screen.py`; `tools/score_posting.py`, which reads extracted fields, applies the
  floor itself as its salary cut.
- **Every posting ruled out is written back to `seen_jobs.json`** with `tools/exclude.py add`,
  which stores `status: "excluded"`, a checkable `exclusion_reason`, a date and what the ruling
  rests on, so it never resurfaces while that holds. A ruling under the person's screening
  rules lapses when those rules change and the posting is screened again when next found; one
  in the person's own words holds until `exclude.py lift`. The gate that enforces
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
  the employers named in `profile/boards.py` straight from their ATS (Greenhouse, Lever,
  Ashby, Workday), which is how large employers that a portal under-indexes reach a round,
  and `scrape_wide.py` calls it, so `run_round.py` needs nothing extra. `--probe` re-checks
  every token. A board whose robots.txt disallows it is refused, and so is SmartRecruiters
  by its API's; the reasons are recorded beside each.

## One command

`python3 tools/run_round.py --out rounds/<name> --jobage 14` runs every stage below in order and stops at the ranked shortlist. See `RUNBOOK.md`. The sections below explain each stage.

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
- "health" to run the portal health check only (Step 4.75), without searching, deduplicating, or presenting jobs - e.g. "/scrape health", or "/scrape health linkedin" to probe one portal even if disabled

---

## Execution Steps

### Step 0: Load State

1. Read `job_scraper/seen_jobs.json` (create if missing - start with `{"seen": {}}`)
2. Read `job_search_tracker.csv` to extract already-applied companies+roles
3. Read `profile/search-queries.md` for the search strategy

### Step 1: Search

Read `profile/search-queries.md` for the search strategy. By default, run the top 3 priority query categories. If the user said "broad", run all categories. If the user specified a focus area (e.g. "data science"), prioritize queries from that category.

**Use the installed CLI tools as the primary search mechanism.** Fall back to `WebSearch` only for portals that do not have a CLI skill, or if `bun` is unavailable on the system.

#### 1a. Check bun availability

```bash
bun --version
```

If this fails (bun not installed), skip to **1c (WebSearch fallback)** for all portals and note the fallback in the Step 5 output.

#### 1b. Run CLI tools (primary - run these in parallel where possible)

Discover all installed portal CLI skills by reading every `SKILL.md` found under `.agents/skills/*/SKILL.md`. Each file documents that portal's exact CLI flags and usage examples. **Use each portal's own documented interface - do not guess flags.** This approach automatically includes any new portals added via `/add-portal` without requiring changes to this file.

**Honor the `enabled` toggle.** Run `python3 tools/portals.py`: it prints each portal ON or off and why. A portal's `SKILL.md` frontmatter `enabled:` is the app's default (a missing key means enabled), and `profile/search.py` `PORTALS` is the person's say, which wins for every portal it names. Skip each portal that is off, send it no request at all, and record it for the Step 5 summary. The app's two portals, `linkedin-search` and `freehire-search`, are on by default, and their `SKILL.md` is the app's: never edit it to switch one, because `tools/sync_app.py` would put it back. Every other portal is the person's own, built by `/add-portal`, and its `SKILL.md` is theirs. Running one by hand, keep to its frontmatter as a round does: `crawl-delay` seconds between requests, and never `detail` on a portal that says `detail: false`.

For each **enabled** portal skill:

1. Read its `SKILL.md` to find the correct `bun run …` invocation and supported flags.
2. Translate the query terms from `profile/search-queries.md` into that portal's flag format (e.g. `--key`, `--search-string`, `--query`, filter codes - whatever the portal's SKILL.md specifies).
3. Scope to the last 14 days using the portal's supported recency **filter** flag (`--jobage`, `--since <YYYY-MM-DD>`, etc. - as documented per portal). A portal with **no recency flag** (some boards offer none) still gets scoped: every portal's search output carries a `date` field, so filter client-side - drop results whose `date` is older than 14 days after the call returns, and never invent a flag the portal's SKILL.md does not document (the CLIs reject unknown flags). Sorting by date does not scope the results, because a sort is not a filter: pairing one with a `--limit` is a defensible approximation on a portal that offers nothing better, but apply the client-side date filter on top all the same.
4. **Paginate. Never cap.** A limit flag is not a page size: on the LinkedIn CLI `--limit` is a
   *client-side cap* applied to a page that holds only **10** results, so `--limit 25` silently
   returns 10 and asking for it once returns page 1 alone. Read each portal's `SKILL.md` for its
   real page size, then walk `--page 1..N` until a page comes back empty or wholly duplicated.
5. **Search every location the PASS set covers, not just the biggest city.** A portal files a
   posting under whatever the employer typed, so a metro search that asks only for
   "<City>, <Region>, <Country>" never sees the roles filed under the suburbs by name or
   region-wide. The locations are `SCRAPE_LOCATIONS` in `profile/search.py`.
6. Use `--format json` for machine-readable output.

**Scraping is free.** It spends no model tokens, and so does `tools/prefilter.py` after it. The
run's cost is set by how many postings reach the weighted scoring stage, and that is capped by
selection, not by how much was scraped. So scrape as wide as the portals allow and filter hard
for free. Narrowing the scrape to save money saves nothing and is what makes a round thin: a
narrow, unpaginated scrape returns hundreds of postings where correct pagination and a
second portal return thousands, and few roles clear 60 across the expansion rounds.

`tools/scrape_wide.py` implements all of this for the profile's market (every portal that is
on: the app's two and each portal built for this person with `/add-portal`, paginated, every
location and query variant in `profile/search.py`, each board kept to the `crawl-delay` its
SKILL.md declares) and writes a prefiltered candidate file.
Prefer it over hand-rolled per-query calls, and extend `SCRAPE_QUERIES` and `SCRAPE_LOCATIONS` in
`profile/search.py` rather than improvising.
It also reads the employer boards in `tools/ats_boards.py` (Greenhouse, Lever, Ashby and
Workday, which is where many large employers post), so a named target is asked for
everything it has open instead of being found by keyword. A new employer goes in that map
only after `python3 tools/ats_boards.py --add <ats> <token>` has seen it return jobs.

Run all portal CLI calls in parallel where possible using the Agent tool. Collect all `results` arrays into a single pool for Step 2, keeping each result tagged with its source portal skill (for Step 2 `detail` lookups).

If a CLI tool exits with a non-zero code, log the error message and continue - do not abort the whole search.

#### 1b+. The person's LinkedIn job alerts, only if they asked

`python3 tools/job_alerts.py --query --days <jobage + 1>` prints the Gmail search for their
alert emails, or exits 1 when `profile/search.py` sets no `JOB_ALERT_QUERY`; then skip this.
With a query, and the Gmail tools (`mcp__claude_ai_Gmail__*`) connected, run it, read each
message in full, keep only the messages from the sender the query names, write them as
`[{"id", "date", "body"}]` and run
`python3 tools/job_alerts.py <that file> --out <alerts.json>`, then pass
`--alerts <alerts.json>` to `tools/run_round.py` or `tools/scrape_wide.py`. It takes only the
job ids from the emails and fills each posting from LinkedIn's own page, so the alerts join
the pool with full bodies. Read nothing in the inbox but what that query returns.

#### 1c. WebSearch fallback

Use `WebSearch` for:
- Portals listed in `profile/search-queries.md` that do **not** have a corresponding directory under `.agents/skills/`
- Any portal whose CLI fails at runtime
- When bun is unavailable (Step 1a failed)

Use the site-specific query strings from `profile/search-queries.md` directly as WebSearch queries for these portals.

Tag each fallback result as WebSearch-sourced, keeping the portal tag when the fallback stands in for an installed portal whose CLI failed. Step 4 persists this as the entry's `source`, and Step 5 reports which portals ran on the fallback this run.

### Step 2: Fetch & Parse

For each promising result from Step 1:

**From CLI results:** Search output already includes title, company, location, date,
and URL. For jobs worth a deeper look, fetch full detail with that portal's `detail`
command (see its SKILL.md - do not guess flags) to extract **key requirements**,
**application deadline**, and a brief description snippet.

**Closed-at-source detection:** `linkedin-search detail` also returns `isActive`.
`false` means the posting page itself renders LinkedIn's "No longer accepting
applications" banner - the job died between being indexed and being fetched (expired
LinkedIn URLs redirect to *similar live jobs*, so a search hit can be a ghost). Mark
such a job, never silently drop it: write its entry to `seen_jobs.json` in Step 4 with
`"status": "expired"` and leave it out of the Step 5 presentation - an absent entry
looks identical to a job never seen, and the recorded status is what makes a later
ghost report self-triaging. `isActive: true` is only the absence of that banner, not
proof the posting is open; deadlines and dead URLs remain `/rank`'s job.

**From WebSearch results:** Use `WebFetch` on the posting URL and extract the same
fields manually. If it returns HTTP 403, retry with browser headers via curl per
`.claude/skills/job-application-assistant/09-web-research.md` before giving up - most
bank and corporate sites reject WebFetch's user agent while serving browsers normally.

**Store a URL that actually resolves to the posting.** A listing-page URL with a
`#fragment` appended (`.../jobs/data-analyst/#acme`) is not a posting: it fetches fine and
returns unrelated job titles, which makes every later `/rank` and `/apply` run fail on
that entry. When WebSearch only yields a listing page, search the employer's own careers
site for the role and store that URL instead, or drop the candidate rather than saving a
fragment link.

For every candidate:
- Skip if the URL or company+title combo already exists in `seen_jobs.json`
- Skip if the company+role already appears in `job_search_tracker.csv`

In code the first of these is `throttle.ruled_out()`, and `tools/prefilter.py` applies it
with `--seen` **before `hydrate.py` fetches any body**. That placement is the point: the
decision needs only the URL and the (title, employer) pair, both of which the scrape
already has, so running it at the end meant re-fetching and re-scoring every posting the
search had already excluded, and on repeat rounds a large share of everything reaching
hydrate was in that state.
`prefilter` imports the throttle's own function rather than restating it, so the two can
never disagree.

### Step 2.5: Mass-Posting Detection (within this run)

A distribution pattern worth flagging to the user as a caution signal, not as an accusation against the employer - it describes how a listing is being distributed, not a verdict on whether the company is legitimate. It alone proves nothing is wrong (companies do legitimately hire the same role across several cities); flag it so the user can factor it in when deciding whether to invest time, don't downgrade fit or silently exclude the result because of it.

If two or more results in this run's pool (from the same company, or sharing the same req/job ID visible in the URL or title) have substantially the same description and differ only in city/location/title, don't present them as separate rows. Consolidate into a single row and note the spread, e.g. "posted identically across 6 cities (BR, MX, GT)".

### Step 2.9: Company throttle and one-role-per-company

Run this **before** spending anything on scoring. It is pure bookkeeping and it removes work.
In code it is `tools/throttle.py`, which `tools/run_round.py` runs after `fit.py`: it
normalizes employer names through `tools/company_key.py`, URLs through `lookup_score.norm`,
and records every skip in `seen_jobs.json`.

**Suppress companies already applied to.** Read `job_search_tracker.csv`. Any company with a
row whose application was sent and is still live (`applied`, `interview`, `offer`) is
**suppressed**: do not surface further roles there, and record them in `seen_jobs.json` with
`status: "skipped"` and the reason `company throttle: an application is already open at this
employer`. A `drafted` row is not sent, so it does not suppress: the new role surfaces with a
note that a draft exists. A sent row with no reply for 45 days (`throttle.SILENCE_DAYS`) stops
suppressing too, unless it is at `interview` or `offer`, which are live however long they run;
the tracker row itself is left alone, because marking silence as `no_response` is `/outcome`'s
job. Applying to a third and fourth role at the same employer in the same fortnight reads
as spray-and-pray to the recruiter reviewing them and it is not what the candidate wants.

The one override: a suppressed company's posting may still be surfaced when it is **materially
better** than what was already sent there, meaning it scores 10 or more points higher. Say so
explicitly and name the earlier application, so the user can decide whether to withdraw or ignore.

**One role per company per run.** Where a run turns up several eligible roles at the same
employer, score them, then surface only the **highest scorer**. Record the others as
`status: "skipped"` with the reason `same-employer duplicate: <the surfaced role> scored higher
this run`. Never present three roles at one company and ask the user to choose; that is the
choice this step exists to make. If the top two are within 3 points and genuinely different
functions, surface one and mention the other in a single clause.

### Step 3: Tiered scoring (cheap knockout first, full framework second)

Scoring every candidate against the full weighted framework is the most expensive thing this
skill does and most of it is wasted. In an early version each full evaluation cost roughly
70k tokens, and most of what it scored came back excluded. The majority were decided by a
single stated fact, a degree requirement or a years bar, which costs nothing to check.

**The tiers exist to make the expensive stage rare.** Each one is cheaper than the next and its
only job is to shrink what reaches the one below it. The rule that governs all of them: **never
run a stage on a posting that stage cannot change the fate of.** Full-scoring a posting you will
never surface is waste no matter how good the scoring is.

**Freshness is a hard rule.** Nothing older than **14 days** is in scope, no exceptions and no
matter how good the fit looks. Pass `--jobage 14` to every portal search, and let
`tools/prefilter.py` enforce it again on the returned dates: a portal filter is a request, not a
guarantee, and a stale posting is the most expensive false positive this pipeline has - it
survives every tier, gets fully scored, gets drafted for, and the role was filled a month ago.

Within the window, **newer wins**. Order the scoring queue by age ascending, present the shortlist
with each posting's age, and where two postings score within a few points of each other prefer the
fresher one. A 14-day-old posting is worth pursuing only when the fit is genuinely strong.

A posting the portal gave no date for is kept, not dropped: absence of a date is not evidence of
age. It is scored normally and reported as `date not stated`.

**Tier 1: mechanical pre-filter. Run `tools/prefilter.py`. No model tokens.**

```bash
python3 tools/prefilter.py <scraped.json> --out kept.json --dropped dropped.json --explain
```

It is a script, not a judgment call, and it must stay one. An improvised title regex dropped a
genuinely good posting (Harbour Freight, "Manager, Demand Planning & Analytics") on the bare
word "Manager", contradicting `profile/10-triage-blockers.md`'s own rule that "Manager" without stated
direct reports is not a knockout. The script drops only what a title or location settles on its
own, logs a reason for every drop, and **never filters on seniority** - Manager, Senior, Lead,
Staff, Principal and Head all survive to Tier 2, which reads the actual requirements.

Read `dropped.json` before moving on. A drop list longer than about 10% of the pool means the
filter is over-cutting; widen `POSITIVE` in the script rather than accepting the loss.

**Tier 2: knockout triage. Small model (haiku).** Agents read **only**
`profile/10-triage-blockers.md` and the posting, and answer one closed question: does the posting state a
requirement the candidate provably does not meet? Do not give this agent the framework, the
behavioural profile, or the candidate profile.

*Batching:* one posting per agent below ~20 candidates. Above that, batch **up to 8 postings per
agent** and dispatch the batches in parallel in a single message. Triage is a closed mechanical
test against a short card, so the anchoring risk that rules out batching at Tier 3 is small here,
and at 85 candidates batching is the difference between 12 agents and 85. Tell the batched agent
explicitly to judge each posting independently and to return one verdict per posting.

A knockout is recorded straight to `seen_jobs.json` with `tools/exclude.py add`, the quoted
trigger line as its reason, and never reaches Tier 3.

**Tier 2.5: fact extraction and mechanical screen. Small model (haiku), batched 8.**

Every Tier 2 survivor goes through one cheap **extraction** pass and then
`tools/score_posting.py`, which costs nothing.

The extraction agent does **not** judge fit and does **not** score. It reports what the posting
states, as closed fields: years required, degree required, citizenship or clearance, a required
language (the language gate in `profile/search.py`), location, salary range, direct reports,
contract or permanent, the tools named, and the disambiguation fields below. `null` and `false`
are correct answers; most postings are silent about most of this. Every field that could end a posting must come with a quote.

**Why extraction and not a cheap score.** Both cheaper substitutes for the fit score were built
and measured against postings a capable model had already scored:

| Approach | Mean error | Max error |
|---|---|---|
| Small model estimating the 0-100 score directly | 18.1 | 38 |
| A deterministic weighted formula over extracted facts | **21.4** | **58** |

The formula was worse than the guess, and the reason is not a tuning problem. The vocabulary is
homonymous: "risk" can mean packaging derivatives pricing libraries; "modelling" can mean
financial and valuation modelling for a fund; genuine risk-scoring methodology can serve a sales
function. A keyword formula scores each of those far above what a capable model does. Telling
them apart from the analytics job the profile is in
**is** the judgment a fit score exists to make, and no keyword feature vector performs it.

**The disambiguation fields** exist because of exactly those cases, and they are the person's,
because the homonyms are their field's: `profile/search.py` `SCREEN_HOMONYMS` names each field and
the value that means a different job, and `SCREEN_WRONG_FAMILY` the `core_function` values that
are not their job. Ask the extractor `core_function` and every field named there, as closed
questions. The example person's (an analyst's) are `modelling_kind` (statistical_ml /
financial_valuation / none), `risk_kind` (account_credit_fraud / market_investment /
quant_library_engineering / none) and `analytics_serves` (product_pricing_risk / sales_gtm /
operations / none). They are closed questions a small model answers well, and they are what
separates a matching role from one that merely shares its nouns. A profile with none set gets no
flags from them, and loses nothing else.

**The screen cuts on facts and flags judgments.** `tools/score_posting.py` ends a posting only on
a stated, quoted fact: a gate failure (eligibility, language, location) or a whole salary range
below the floor. Everything else - a years bar, a stated Master's or PhD, job family, the homonym
fields, direct reports, a fixed-term contract - becomes a **flag** that orders the scoring queue
and never discards. The raw-text screen, `tools/text_screen.py`, cuts on the other facts listed
under the hard cuts above.

That split was learned the hard way. An earlier version also cut on the job-family label and
discarded roles that a full evaluation scored as good fits. A cheap model's single classification is
not reliable enough to end a posting's life; a quoted requirement is.
`tests/test_only_a_verdict_blocks_a_posting.py` locks the property that only a stated verdict
blocks a posting, and a cut posting must always carry its reason.

**Score in queue order, fewest flags first, and stop at the yield target.** Do not full-score the
whole screen output. Take the queue in order until 5 postings clear 60 with 2 at 75+, then stop
and record the remainder as `status: "estimated"` with their flags. Those are not exclusions; a
later run can promote them without re-deriving anything.

**Tier 3: full weighted scoring. Sonnet, one posting per agent, in parallel, never batched.**

Only for postings the screen passed, taken in queue order, and only until the yield target is
met. Each agent reads **`profile/12-scoring-brief.md` and the posting, and nothing else** - not
`profile/04-job-evaluation.md`, not `profile/01-candidate-profile.md`, not `profile/CLAUDE.md`. The brief is those three
distilled to what scoring uses, and it is why this tier costs a fraction of the ~70k per posting
it cost when every agent read all three.

**Never batched.** A Tier 3 exclusion is written to `seen_jobs.json` and never revisited, so a
posting scored in the shadow of a stronger one in the same batch is lost silently. The brief
already removed the duplicated reading that batching would have amortized.

This is the only tier where a model exercises judgment about fit, and that is deliberate: two
attempts to move it onto cheaper machinery were measured and both were too inaccurate to rank on.

**Tier 4: adversarial verification.** Only for postings scoring 70+ where the score could change a
decision.

Report the funnel in the Step 5 summary: how many entered each tier and how many survived. A run
that knocks out most of its candidates in Tier 2 has done its job well, not badly.

### Step 3b: Tier 3 in detail - scoring against the fit framework

Everything below applies to **Tier 3 survivors only**. Nothing here is read by the Tier 2
triage agent, and nothing here is spent on a posting a knockout already rejected.

**Do not eyeball this.** Every Tier 3 candidate is scored against
`profile/04-job-evaluation.md` - the same framework `/rank`
and `/apply` use. A scrape that returns a pile of unscored links is a wasted scrape: the
point of the run is a ranked shortlist the user can act on, not a list of things that
contain the word "analyst".

Read `04-job-evaluation.md` once at the start of this step, then for each candidate:

1. **Run the gates first.** Eligibility Gate, then Language Gate, then the Location table
   (dimension 4). A gate failure is a hard exclusion: record it in `seen_jobs.json` with
   `status: "excluded"` and the reason (Step 4.4), and never present it. Gates are not scored and never
   averaged away by a strong score elsewhere.
2. **Score the four weighted dimensions**: Technical Skills (30%), Experience Match (25%),
   Behavioral Fit (15%), Career Alignment (30%). Behavioral and cultural signal is thin from
   a search result alone, so score it from the posting text you have and mark it provisional
   rather than inventing a company-culture read.
3. **Compute the overall score, 0-100**, and assign the band from the Thresholds section of
   `.claude/skills/job-application-assistant/04-job-evaluation.md`, the one home of the band
   edges (the 60 and 75 used below are two of them).
4. **Record 1-3 strengths and 1-3 gaps** in the candidate's own terms, for the Step 4 store.

Scoring a full search pool at this depth is expensive. Keep it proportionate: pre-filter on
title and location first, score the ones that survive, and fetch posting detail only for
candidates that look like they could clear the pass bar. A one-line title is not enough to
score Technical Skills honestly, so a candidate that reaches scoring gets its detail fetched.

**Salary check.** Follow "How much weight salary actually gets" in section 5b of
`profile/04-job-evaluation.md`. In short: **a posting with no stated range costs the posting
nothing.** Many postings omit it, and silence is not a red flag. Report it as
`not stated`, deduct nothing from the score, and assume the band is met where the employer
is established and there is checkable evidence they pay and treat people well. Where a range
*is* stated and its top falls below the walk-away floor, report that next to the score
so the user does not have to discover it themselves. Salary never overrides a gate and never
changes the score.

### Step 3.5: Yield Check and Search Expansion (do not skip)

A run that surfaces nothing above the pass bar has not finished. It has failed, and stopping
there wastes the search.

**Pass bar:** a posting scoring **60 or above** (Good Fit or better) that clears every gate.

**Yield target:** at least **5 passing postings**, of which at least **2 score 75+**
(Strong Fit). If the user gave a focus area, the target applies within that area.

If the target is not met after the first pass, **expand and search again** rather than
reporting a thin result. Work through these in order, re-running Steps 1 to 3 on each new
sweep and re-checking the target after each:

1. **More title variants.** The same work is posted under many labels; `profile/search-queries.md`
   lists them per category. Exhaust the variants in the categories you already ran before
   moving on.
2. **The remaining priority categories.** A default run covers the top 3; go to all of them.
3. **Widen location within the PASS set.** Add remote-in-country and region-wide terms, then
   the rest of the metro area by name (the PASS set and `SCRAPE_LOCATIONS` in
   `profile/search.py`). Never widen into a location the Location table fails, and never
   relax a gate to make the numbers.
4. **Adjacent sectors from the Target Sectors list** in `profile/CLAUDE.md` that this run has not
   touched, and named target employers by company.
5. **More pages per portal**, and then the Step 1c WebSearch fallback for boards without a
   CLI.

**Bound it.** At most **3 expansion rounds**. Stop early the moment the target is met.
Portal CLIs rate-limit, so keep each round's volume comparable to the first pass rather than
multiplying it.

**If the target is still unmet after 3 rounds, say so plainly and specifically.** Report how
many passing postings were found against the target, which expansions were tried, and what
the blocker looks like: a genuinely thin market this fortnight, a location filter doing most
of the excluding, a portal that returned nothing, or a profile whose salary floor is cutting
out most of the band. Then recommend the concrete next move: `/scrape broad`, a named focus
area, re-running after a portal is fixed, or revisiting a specific line in
`04-job-evaluation.md` with the user. Never present an under-target run as if it were a
normal result, and never pad the list with sub-60 postings to make it look fuller.

**Language override:** before finalizing any score, check the posting against
`profile/04-job-evaluation.md`'s Language Gate. A required language that is entirely undeclared in
the `profile/CLAUDE.md` Languages table is a gate **FAIL**, not a low score: it is excluded, not
ranked. A **declared** language at a requirement reading higher than the declared level is
not a fail - score normally and add a red-flag bullet under that job's highlights (Step 5)
quoting the posting's requirement next to the declared level, so the gap is visible without
being auto-excluded.

### Step 4: Deduplicate & Store

1. Add ALL fetched jobs (new, skipped and excluded) to `seen_jobs.json` with structure:
```json
{
  "seen": {
    "<url_or_company_title_key>": {
      "title": "...",
      "company": "...",
      "url": "...",
      "first_seen": "YYYY-MM-DD",
      "posted_date": "YYYY-MM-DD" | null,
      "deadline": "YYYY-MM-DD" | null,
      "fit": "high/medium/low",
      "rank_score": 0-100,
      "rank_verdict": "strong fit | good fit | moderate fit | weak fit | poor fit",
      "rank_date": "YYYY-MM-DD",
      "location_verdict": "PASS/FAIL/FLAG",
      "language_gate": "PASS/FAIL/FLAG",
      "strengths": ["...", "..."],
      "gaps": ["...", "..."],
      "status": "new/ranked/estimated/skipped/excluded/applied/expired",
      "portal": "<source portal skill, e.g. linkedin-search>",
      "source": "cli/websearch"
    }
  }
}
```

The `portal` field records which CLI skill produced the job (results are already tagged per portal in Step 1b - persist that tag here). Entries written before this field existed lack it; the health check (Step 4.75) attributes those by matching the URL's domain against each portal's base URL, so do not backfill.

The `source` field records which mechanism produced the entry: `cli` for Step 1b portal-CLI output, `websearch` for the Step 1c fallback. This is what keeps a ghost-job report diagnosable after the run's summary is gone: a stored entry whose URL later resolves to nothing (or to a different job) reads very differently depending on whether it came from live CLI output or from a search index that can be weeks stale - and a presented job with no entry here at all points at fabrication, which Rule 1 forbids. Entries written before this field existed lack it; never backfill it - the mechanism was not recorded.

**Step 3 now writes the scoring fields directly**, using exactly the field names `/rank`
uses, so both commands produce interchangeable entries and nothing downstream needs to know
which one scored a posting. A posting that reached Step 3 is stored with `status: "ranked"`,
its `rank_score`, `rank_verdict`, `rank_date`, `location_verdict`, `language_gate` and its
`strengths`/`gaps`. A posting excluded by a gate is stored with `status: "excluded"`, an
`exclusion_reason` naming the failing gate and an `excluded_date` (Step 4.4). Keep `fit`
populated as the coarse high/medium/low band derived from the score (75+ high, 60-74 medium,
below 60 low) so older readers keep working.

`/rank` uses the same fields: ranked entries carry `rank_score` (0–100 overall score), `rank_verdict` (fit band, e.g. "strong fit"), `rank_date` (ISO date of ranking), the veto fields `location_verdict` and `language_gate` (both PASS/FAIL/FLAG) with `language_note` (the quoted requirement explaining a non-PASS), and `strengths`/`gaps` (1-3 verbatim bullets each, copied from the scoring agent's findings). The `status` field is set to `"ranked"`. Do not drop any of these fields when re-writing entries. Entries ranked before `strengths`/`gaps` existed simply lack them; readers tolerate their absence and never backfill by guessing. Entries ranked before the verdict rename may carry a legacy PASS/FAIL/FLAG string in `location` - read that as the verdict when `location_verdict` is absent; in fresh entries `location` is always a place, never a verdict.

`deadline` is a base field rather than a `/rank` extension: Step 2's detail fetch already extracts the application deadline, so it is written when the job is first seen and refreshed by `/rank` Step 4 when a scoring agent returns a different value. `null` means the posting states no deadline; a missing key means the entry predates this field - **never infer a deadline** from either, and never backfill by guessing.

`posted_date` is the posting's own publication date, taken from the `date` field Step 2's contract already guarantees on every portal CLI's search output. Step 1b uses that date to scope the run to the last 14 days and then drops it, so nothing downstream can distinguish a posting published yesterday from one published two years ago - `first_seen` is when this scraper first saw the entry, not when the employer posted it. Persisting it makes Step 1b's window auditable after the run and gives `/rank` a freshness signal to weigh, instead of rediscovering the date and recording it in prose that nothing reads. That gap is real: a stale posting can be scraped and ranked Strong Fit at the top of a shortlist, its own scoring note observing the listing "may be long stale" with nothing able to act on it. `null` means the portal returned no date for that result (the CLIs emit `date: null` when a listing omits it); a missing key means the entry predates this field - **never infer a posting date** from either, and never backfill by guessing.

2. Only present jobs NOT already in the seen list or tracker.

### Step 4.4: Record every posting you rule out

**A posting rejected on inspection must be written back to `seen_jobs.json`** with
`python3 tools/exclude.py add <url> --title ... --company ... --reason "..."` (`--basis person`
when it is the person's own call), which writes `status: "excluded"`, the `exclusion_reason`,
the `excluded_date` and what the ruling rests on. Otherwise the next run
rediscovers it, re-fetches its detail, re-scores it and re-presents it, and the user has to
rule it out again.

This applies to every rejection route, not just gate failures:

- a gate failure (eligibility, language, location)
- a stated hard requirement the profile cannot meet (a Master's degree, a named mandatory
  tool, a clearance)
- a specialism the role is built entirely around that the profile does not have
- a stated range whose top sits below the person's salary cut line (`SALARY_CUT_BELOW`): a
  different job level, not a negotiation. A range above that line but under the walk-away floor
  is a flag, never an exclusion
- a vacancy open to the employer's own staff only
- a posting the user looks at and declines

Write the reason in enough detail that a later run can tell whether the exclusion still
holds. "Not a fit" is useless; "requires a Master's in a quantitative discipline, not held"
is checkable.

**Exclusions are per posting, never per company.** The key is the posting URL. A different
role at the same employer is a fresh candidate and must still be scraped, scored and
presented. Never filter a company out because one of its postings was excluded. When you
record an exclusion, say so in the reason, for example "a different role at this employer is
still in scope".

**On the next run, treat an `excluded` entry as already-seen for dedup**, exactly like
`ranked` and `applied`, and do not re-present it. If a genuinely new fact would overturn the
exclusion (the posting was re-issued at a different level, the candidate gained the missing
credential), say so explicitly rather than silently re-surfacing it.

### Step 4.5: Generate Referral Contact Links (passing postings only)

For every job from this run that cleared the Step 3.5 pass bar (score 60 or above),
build two LinkedIn people-search URLs so the user can find a recruiter or team member to
reach out to for a referral or a warm intro. This is deliberately a link-generation step,
not an automated lookup: no scraping, no third-party API, zero runtime dependencies or
credentials required.

**A. Recruiters / Talent Acquisition (the referral path)**
```
https://www.linkedin.com/search/results/people/?keywords=<url-encoded "<Company Name> recruiter">&origin=GLOBAL_SEARCH_HEADER
```

**B. Role/team peers (informational-outreach / warm-intro path)**
```
https://www.linkedin.com/search/results/people/?keywords=<url-encoded "<Company Name> <role keyword>">&origin=GLOBAL_SEARCH_HEADER
```
Use a short keyword drawn from the posting's title for `<role keyword>` - e.g. a posting
titled "AI Program Manager" becomes `"<Company Name> AI Program Manager"`.

Both links are for the user to open and browse themselves - never fetch or scrape the
LinkedIn people-search result pages programmatically. Never fabricate contacts or claim a
specific person was found; these are search links, not results.

### Step 4.75: Portal Health Check

Scraper-based portal CLIs rot silently: when a portal changes its markup, the parser usually exits 0 with zero results or with null/garbled fields, and the Step 1c fallback never fires because it only triggers on hard failure. This step catches that from evidence the run already holds.

**Free pass (no extra requests).** For each enabled portal that ran in Step 1b:

- **Degraded scan:** inspect the results it returned this run. Flags: `company` null or empty on every result, empty titles, undecoded entities (`&amp;`) or HTML fragments in titles, URLs that do not point at the portal. Any of these means the parser is half-working and `/scrape` is silently collecting junk.
- **Yield history:** if the portal returned zero results across all of this run's queries, check whether `seen_jobs.json` holds prior entries from it (via the `portal` field, or by matching URL domains for entries predating the field). A portal that produced jobs on earlier runs and produces nothing now is suspect - the same queries worked before.

**Escalation (bounded, on suspicion only).** A suspect portal gets **one** sentinel probe: run its documented `search` with the example query from its own SKILL.md (that query provably worked when the skill was registered), the portal's limit flag capped at 3, `--format json`. If that returns nothing, retry **once** with a single common word. Only then is the verdict **broken**. A 429 or block page is **never** evidence of breakage - record the portal as **inconclusive (rate-limited)**, back off, and do not retry.

**Verdicts.** Healthy portals get silence - no table, no line. Anything else surfaces in the Step 5 summary as a health line.

**Probe-only mode (`/scrape health`).** Skip Steps 1-4 and this step's free pass (there is no fresh run to scan); instead probe every installed portal directly - enabled ones by default, a disabled one only when named explicitly (e.g. `/scrape health linkedin`). Each portal gets the sentinel probe above, the degraded criteria applied to whatever it returns, and - since the user explicitly asked for diagnosis - one `detail` fetch on the first result of each healthy portal (description must be readable decoded text; a failure downgrades to degraded). Report all statuses in this mode, including healthy. Volume stays bounded: one search, at most one retry, at most one detail per portal.

### Step 5: Present Results

Present new jobs in a table **sorted by `rank_score`, highest first**, with the score shown. Never sort alphabetically, by portal, or by posting date, and never present an unscored posting. When Step 1b skipped
portals that are switched off (`python3 tools/portals.py` says which), report them with the `skipped (disabled):` line below
so opting one out stays visible rather than silent; omit the line when nothing
was skipped. When any portal's results came from the Step 1c fallback this run
(bun unavailable, or its CLI failed at runtime), report it with the
`fallback (websearch):` line - fallback results come from a search index that
can be stale, so the reader should know which rows carry that caveat; omit the
line when every portal ran its CLI. When Step 4.75 found a portal degraded, broken, or inconclusive,
add one `health:` line per suspect portal (healthy portals get no line); after
the report, offer to switch that portal off so `/scrape` stops running it (and
covers it via the Step 1c fallback) until it is fixed. For the app's two portals
(`linkedin-search`, `freehire-search`) that is a `PORTALS` entry in `profile/search.py`
(`{"freehire-search": False}`), never an edit to their `SKILL.md`, which a sync puts
back; for a portal built for this person by `/add-portal` it is `enabled: false` in that
portal's own `SKILL.md` frontmatter. Only switch with the user's confirmation, and never
edit anything else in the skill.

```
## New Job Matches - YYYY-MM-DD

Scored N new postings against the fit framework. **P cleared the pass bar (60+)**, of which
Q are Strong Fit (75+). Target is 5 passing and 2 strong.

yield: met after R expansion round(s)   |   or: NOT MET after 3 rounds - see the note below

funnel: A scraped -> B after Tier 1 (tools/prefilter.py) -> C after the company throttle -> D triaged -> E estimated -> F full-scored -> P passing

gates: E excluded by the Eligibility Gate, L by the Language Gate, O on location

skipped (disabled): <portal-name>, <portal-name>

fallback (websearch): <portal-name>, <portal-name>

health: <portal-name> - degraded (company null on all 12 results); parsing anchors in .agents/skills/<portal-name>/url-reference.md
health: <portal-name> - broken (0 results for the SKILL.md test query and a broader retry); parsing anchors in .agents/skills/<portal-name>/url-reference.md

| # | Score | Verdict | Title | Company | Location | Salary | Deadline | Apply |
|---|-------|---------|-------|---------|----------|--------|----------|-------|
| 1 | 82 | Strong fit | ... | ... | ... | stated range, or `not stated` | ... | [Apply](https://...) |

**Every row carries a working apply link**, and so does every posting you later draft
documents for. The link is the posting URL stored in `seen_jobs.json`, which Step 2 already
guarantees resolves to the posting itself rather than to a listing page. When documents are
produced for a posting, repeat its link next to them so the user can go straight from the
files to the application form without searching for the ad again.

If Step 2.5 flagged a mass-posting pattern, note it in the Title cell (e.g. "Frontend Developer (posted in 6 cities)") rather than burying it. Do the same for a declared-language-insufficient-level flag from the Language Gate (e.g. "Backend Engineer ⚠ fluent English required") - both are signals the user should see at a glance, not just in the detail highlights below.

### Top Matches
For each posting scoring 75+, add 2-3 bullet points drawn from the Step 3 `strengths` and
`gaps`:
- The strongest specific match to the profile, named concretely
- Key requirements to check before applying
- Any red flags: mass-posting signals from Step 2.5, a **stated** salary range whose top is below the
  walk-away floor, an unstated on-site expectation, a declared-language level below the
  posting's bar. An absent salary range is not a red flag and is not listed as one

**If the yield target was not met**, follow the table with a short, specific note: passing
count against target, which expansions were run, what the blocker appears to be, and the
concrete next move. Do not bury this and do not pad the table with sub-60 postings.

### Contacts
For each passing posting from Step 4.5, add a short contacts block with the two
LinkedIn search links:
- Recruiters/TA search link, for the referral path
- Role/team-peer search link, for the warm-intro / informational-outreach path
```

### Step 5.5: Stop at the shortlist

**Do not draft resumes or cover letters unless the user asked for them.** The run ends at the
ranked table plus its supporting context: salary read, deadlines, referral and warm-intro
links for passing postings, and anything that needs a human decision.

**Before drafting for any posting later, confirm the user has not already applied to it.**
The tracker only records applications made through this repo, so it cannot rule out one the
user made directly on a company site or through a recruiter. Ask first, then record the
answer so the next run knows.

After presenting, ask:
> "Want me to evaluate any of these in detail? Just give me the number(s)."

If the user picks a number, invoke the **job-application-assistant** skill workflow (fit evaluation first, then CV + cover letter if approved).

Do **not** suggest `/rank` after a normal run: Step 3 already scored everything it presented and wrote it to `ranked`, so `/rank`'s default selection (`status: new`) would find nothing. `/rank` is for the two cases `/scrape` does not cover: re-scoring after a change to the candidate profile or `profile/12-scoring-brief.md` (`/rank --all`, which skips permanent exclusions), and scoring a backlog added outside the normal flow. (`/rank` sets the `ranked` and `expired` status values in `seen_jobs.json`; treat both as already-seen for dedup purposes.)

### Step 6: Update Tracker (Optional)

If the user decides to apply to any job, the tracker row is written by **job-application-assistant Step 3b**, which Step 5 already routes into - do not add a second row here. Only when the user says they applied to something outside that path, add a row using the header and the match-then-update rule in `/outcome` Step 1.

---

## Important Rules

1. **Never fabricate job postings.** Only present jobs from actual CLI search/detail output or WebSearch/WebFetch results.
2. **Respect deduplication.** Always check seen_jobs.json AND job_search_tracker.csv before presenting.
3. **Focus on configured geographic area.** Skip jobs that require relocation or are clearly outside commute range.
4. **Only open positions.** Skip postings with expired deadlines or those marked as closed.
5. **Be efficient with detail fetches.** Don't run `detail` or WebFetch on every search hit - pre-filter by title/snippet, then fetch only promising matches.
6. **Parallel searches.** Run portal CLI searches in parallel; use WebSearch only for gaps the CLIs don't cover.
7. **No automated people lookups.** Referral contacts (Step 4.5) are LinkedIn search links only - never fetch or scrape LinkedIn people-search result pages programmatically.
8. **Health checks are bounded and honest.** Step 4.75 spends at most one probe, one retry, and (in `health` mode) one detail fetch per portal - a diagnosis, not a crawl. A rate-limit is never evidence of breakage. Health verdicts come only from observed CLI output; a portal that could not be tested is reported as inconclusive, never guessed. The on/off switch (`PORTALS` in `profile/search.py`, or `enabled:` in a person's own portal) is the only thing the health check may edit, and only with confirmation.
9. **Score everything you present, and rank by that score.** No posting reaches the user unscored, and the table is ordered by score. A list of unranked links is a failed run.
10. **An under-target run expands before it reports.** Steps 3.5's expansion ladder runs before the summary is written, up to 3 rounds. Never pad a thin result with sub-60 postings, and never relax a gate or the location filter to make the yield target.
11. **Flag distribution patterns, never accuse.** The mass-posting signal (Step 2.5) describes how a listing is being distributed, not a claim that the employer is a scam. Never name a company as fraudulent or untrustworthy - present the observation and let the user decide.
