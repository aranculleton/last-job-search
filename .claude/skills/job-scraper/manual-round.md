# The hand-run round

Read this only when `tools/run_round.py` cannot run: it is every stage that command runs,
written out to do by hand. A round from `run_round.py` never needs it. Presenting the
result is the skill's own Step 5 (`SKILL.md` beside this file), the same on either path.

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
It also reads the employer boards in `profile/boards.py` through `tools/ats_boards.py`
(every system openroles reads, which is where most employers post, and careers sites that
publish their jobs for search engines), so a named target is asked for everything it has
open instead of being found by keyword. A new employer goes in that map only after
`python3 tools/ats_boards.py --add <ats> <token>` has seen it return jobs.

Run all portal CLI calls in parallel where possible using the Agent tool. Collect all `results` arrays into a single pool for Step 2, keeping each result tagged with its source portal skill (for Step 2 `detail` lookups).

If a CLI tool exits with a non-zero code, log the error message and continue - do not abort the whole search.

#### 1c. WebSearch fallback

**Never when this chat's cloud settings block the job sites.** If `python3 tools/env_check.py
--say` prints anything, tell the person those words first and run no search at all until
they say it is done: a web search in place of the job sites returned postings closed for
months and presented them as leads (2026-10-22). A person must never be left with a search
that quietly does not work.

Otherwise, use `WebSearch` for:
- Portals listed in `profile/search-queries.md` that do **not** have a corresponding directory under `.agents/skills/`
- Any portal whose CLI fails at runtime while the others work
- When bun is unavailable (Step 1a failed)

Use the site-specific query strings from `profile/search-queries.md` directly as WebSearch queries for these portals.

Tag each fallback result as WebSearch-sourced, keeping the portal tag when the fallback stands in for an installed portal whose CLI failed. Step 4 persists this as the entry's `source`, and Step 5 reports which portals ran on the fallback this run.

**A web-search lead is shown only once its own page proves it is open.** A search engine's
index holds postings long after they close. Before a lead reaches the person, fetch its
posting page (Step 2) and keep it only when the page itself is the posting, carries no
closed notice ("no longer accepting applications", "this job has expired", "position
filled"), and shows a closing date, if any, that has not passed. Anything else is dropped
and written to `seen_jobs.json` as `"status": "expired"`, never shown.

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
employer, score them, then surface only the **highest scorer**, by its 0-100 fit, never by
priority (fit times opportunity), which only breaks a tie. Record the others as
`status: "skipped"` with the reason `same-employer duplicate: <the surfaced role> scored higher
this run`. Never present three roles at one company and ask the user to choose; that is the
choice this step exists to make. If the top two are within 3 points and genuinely different
functions, surface one and mention the other in a single clause. The same rule holds at
drafting: when a person's picks name two roles at one employer, `tools/stage_picks.py stage`
holds both and asks which one to draft, unless they say both (`--both`).

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

The tiers below are scoring stages. The networking skill's tier 1 is a person with a quoted
live hiring signal, a different thing.

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
trigger line as its reason and `--rests-on "triage #<n>"` for its blocker, and never reaches
Tier 3.

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
below the cut line. Everything else - a years bar, a stated Master's or PhD, a range under the
floor, job family, the homonym fields, direct reports, a fixed-term contract - becomes a **flag**
that orders the scoring queue and never discards. The raw-text screen, `tools/text_screen.py`, cuts on the other facts listed
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

**What `run_round.py --expand` runs, and what it leaves to you.** The round widens only rung 5's
first half by itself: each wider round searches more pages (from the default 5, then 10, then
30), up to 3 rounds in all, with the same freshness window. It prints rungs 1 to 4 and the
WebSearch fallback as what to try next and never runs them (RUNBOOK.md, "When the round
misses"): a session that wants them runs them by hand, on this manual path.

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
      "last_seen": "YYYY-MM-DD",
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
      "status": "new/surfaced/ranked/estimated/skipped/excluded/applied/expired",
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
which one scored a posting. **This is the manual path** (Steps 1 to 3 run by hand, without
`run_round.py`): a round writes `surfaced` and `skipped` rows instead, never `ranked` ones
(`tools/throttle.py`; `/rank`, "Where the postings are"). On the manual path, a posting that
reached Step 3 is stored with `status: "ranked"`,
its `rank_score`, `rank_verdict`, `rank_date`, `location_verdict`, `language_gate` and its
`strengths`/`gaps`. A posting excluded by a gate is stored with `status: "excluded"`, an
`exclusion_reason` naming the failing gate and an `excluded_date` (Step 4.4). Keep `fit`
populated as the coarse high/medium/low band derived from the score (75+ high, 60-74 medium,
below 60 low) so older readers keep working.

`/rank` uses the same fields: ranked entries carry `rank_score` (0–100 overall score), `rank_verdict` (fit band, e.g. "strong fit"), `rank_date` (ISO date of ranking), the veto fields `location_verdict` and `language_gate` (both PASS/FAIL/FLAG) with `language_note` (the quoted requirement explaining a non-PASS), and `strengths`/`gaps` (1-3 verbatim bullets each, copied from the scoring agent's findings). The `status` field is set to `"ranked"`. Do not drop any of these fields when re-writing entries. Entries ranked before `strengths`/`gaps` existed simply lack them; readers tolerate their absence and never backfill by guessing. Entries ranked before the verdict rename may carry a legacy PASS/FAIL/FLAG string in `location` - read that as the verdict when `location_verdict` is absent; in fresh entries `location` is always a place, never a verdict.

`deadline` is a base field rather than a `/rank` extension: Step 2's detail fetch already extracts the application deadline, so it is written when the job is first seen and refreshed by `/rank` Step 4 when a scoring agent returns a different value. `null` means the posting states no deadline; a missing key means the entry predates this field - **never infer a deadline** from either, and never backfill by guessing.

`posted_date` is the posting's own publication date, taken from the `date` field Step 2's contract already guarantees on every portal CLI's search output. Step 1b uses that date to scope the run to the last 14 days and then drops it, so nothing downstream can distinguish a posting published yesterday from one published two years ago - `first_seen` is when this scraper first saw the entry, not when the employer posted it. Persisting it makes Step 1b's window auditable after the run and gives `/rank` a freshness signal to weigh, instead of rediscovering the date and recording it in prose that nothing reads. That gap is real: a stale posting can be scraped and ranked Strong Fit at the top of a shortlist, its own scoring note observing the listing "may be long stale" with nothing able to act on it. `null` means the portal returned no date for that result (the CLIs emit `date: null` when a listing omits it); a missing key means the entry predates this field - **never infer a posting date** from either, and never backfill by guessing.

**A posting is as old as the first time this search saw it.** A portal relisting a posting
gives it a new date, and LinkedIn's card shows the relist date, so the portal's `date` alone made
a month-old posting look fresh. A round records every posting it surfaces at `status:
"surfaced"` (`tools/throttle.py` `write_back`), with `first_seen` set once and `last_seen` moved
on each sighting; a posting under a new URL with the same title, employer and city as one seen in
the last 30 days (`throttle.RELIST_WINDOW`) is that posting relisted and keeps its `first_seen`.
`tools/prefilter.py` ages a posting by the earlier of its portal date and `first_seen`, and the
freshness bonus in `tools/opportunity.py` is given only on a portal date and never on an unknown
or future one.

2. Only present jobs NOT already in the seen list or tracker.

### Step 4.4: Record every posting you rule out

**A posting rejected on inspection must be written back to `seen_jobs.json`** with
`python3 tools/exclude.py add <url> --title ... --company ... --reason "..."` (`--rests-on
"<part>"` for the blocker row or gate setting it rests on, from `exclude.py parts`; `--basis
person` when it is the person's own call), which writes `status: "excluded"`, the `exclusion_reason`,
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
