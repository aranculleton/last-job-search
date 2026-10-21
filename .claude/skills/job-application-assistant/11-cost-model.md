---
framework_version: 1.1.5
---

# Cost Model for the Application Lifecycle

Optimize the **whole lifecycle**, not any single prompt. A cheap shortlist that surfaces the wrong
roles costs far more than it saves, because the expensive stages (drafting, reviewing, and the
candidate's own time applying) then run on a bad target.

## Where the money actually goes

Measured on real runs in this repo:

| Stage | Cost per unit | Units per run | Notes |
|---|---|---|---|
| Scrape (portal CLIs) | ~0 model tokens | 15-25 queries | Bash, not a model. Effectively free. |
| Mechanical pre-filter | ~0 | 60-80 postings | `tools/prefilter.py`. Regex over title and location. |
| Free text screen | ~0 | survivors of pre-filter | `tools/text_screen.py`, over RAW POSTING TEXT. Cuts only on a quoted stated fact. |
| Free weighted score | ~0 | survivors of the text screen | `tools/opportunity.py` and `tools/fit.py`. Produces the ranked shortlist. |
| **Knockout triage** | **~3-5k** | survivors of pre-filter | Small model, one question, blockers card only. |
| **Fact extraction** | **~1k** | survivors of triage | Small model, batched. Closed fields, every cut quoted. Not a score. |
| **Mechanical screen** | **0** | every extraction | `tools/score_posting.py`, over EXTRACTED FIELDS. Cuts on stated facts, flags judgments. |
| **Full weighted scoring** | **~19k** | postings the estimate promoted | Was ~70k before `profile/12-scoring-brief.md`. Still the dominant cost. Ration it. |
| Adversarial verify | ~40k | postings scoring 70+ | Only where it could change a decision. |
| Drafting resume + letter | see below | per application | One call from the drafting pack (`tools/draft_pack.py`). |
| Grounding audit | 0, then one model call if flagged | per application | Code first (`tools/draft_audit.py`); the model reads one packet. |

The dominant cost is full scoring. Drafting was the other, until it was measured.

## Drafting a batch: what it cost, and what changed

Measured on one batch of ten postings at eight employers (2026-10-21, as the Workflow tool
reported it): research agents 147k to 213k tokens each; drafters about 200k to 230k with 44
to 46 tool calls and 7 to 8 minutes each; auditors about the same again. Roughly 550k to
650k tokens an application. Most of it was the same reading done by every agent: each
drafter read about 35k tokens of the same static files (the profile, `03-writing-style.md`,
`06-cover-letter-templates.md`, the positioning brief, `tools/bridges.py`, the field
contract, `render_application.build()`, two letters) and carried them through every tool
call, and each auditor re-read most of it and re-ran the checks the drafter had just run.

What runs now (RUNBOOK.md step 2):

| Stage | What it reads | Model |
|---|---|---|
| Research | the employer's own pages (unchanged; a cheaper fetch script is to replace it) | sonnet |
| Draft | the pack (a few thousand tokens, the same bytes for the whole batch, so cached), the posting, the research facts: one call, no file reads, at most two repairs from the code audit's failures | strongest |
| Code audit | the claim map against the evidence, and every existing check | none |
| Model audit | one packet, under 10k tokens, and only for a draft the code audit flagged | strongest |
| Outreach body | the letter's two paragraphs, only when the person wants a note written | strongest |

Static reading per drafter, from the files' own sizes (characters / 4, an approximation):
the example person's was about 16k tokens of files and is a 3k pack. A long profile makes
a longer pack (every fact and rule is kept; nothing is cut to meet the 6k target), but the
same profile made every drafter's reading longer by more. The auditor's reading (about 13k
for the example person, before the posting and the draft) is gone: the code audit costs
nothing, and the packet, about 3k for the example person, is read only when a draft is
flagged. **A live before-and-after of tokens and time has not been run**: the next
batch through the Workflow tool is that measurement, recorded with `tools/draft_cost.py`.

What did not get cheaper, on purpose: drafting and the model audit stay on the strongest
model, and every check the auditor ran still runs (the code audit's, or the model's when
code cannot settle it). `verify_batch.sh` and the PDF read are unchanged.

**Two screens, and they are not alternatives.** The table lists both because both run, on
different inputs at different points, and confusing them wastes a round.

| | `tools/text_screen.py` | `tools/score_posting.py` |
|---|---|---|
| Reads | the raw posting text | the extracted closed fields |
| Runs in | `tools/run_round.py`, every free round | the tiered path, after a model extraction |
| Costs | nothing, and nothing upstream of it either | nothing, but the extraction feeding it costs ~1k |
| Catches | a gate, a salary range, a language requirement, a years bar | all of that plus the homonym fields, which no regex reads |

The free round alone is what most runs need: `python3 tools/run_round.py --out rounds/<name>`
goes from portals to a ranked shortlist with no model call at all, and the yield target is
usually met there. The tiered
path exists for what the free round cannot decide, which is the judgment the homonym fields
separate: whether "risk" here means account risk or derivatives pricing. Reach for it when a round
misses its target or when a shortlist reads as though the words matched and the jobs did not.

## The rationing rules

1. **Never full-score what a knockout can reject.** See `profile/10-triage-blockers.md`. A stated Master's
   requirement is a two-token fact; discovering it inside a weighted evaluation is pure waste.
1b. **Never full-score what you will not surface.** Surviving triage is not the same as being a
   candidate for the shortlist. At ~19k per posting, scoring fifty survivors where ten are wanted
   costs roughly a million tokens, most of it spent producing exclusions nobody reads. A cheap estimate from
   the agent that is *already reading the posting* gates this at nearly no marginal cost. This is
   the same mistake as rule 1, made one tier higher, and it is easy to make twice.
2. **Never score a posting you will not surface.** Apply the company throttle and the
   one-role-per-company rule *before* scoring, not after.
3. **Never verify a score that cannot change a decision.** A 45 does not need a sceptic.
4. **Never re-derive what is already recorded.** Scores live in `seen_jobs.json`; company research
   lives in `company_research/*.json`, fresh for `RESEARCH_FRESH_DAYS` (`tools/company_research.py`).
   Read before you fetch.
5. **Never read a file an agent does not need.** The single worst offender was every reviewer
   reading `cv/main_example.tex`, an unpopulated template contributing zero facts.

## Model selection by stage

Match the model to the shape of the task, not to its importance. A task with one right answer
findable by reading a page does not need the strongest model; a task where a plausible-sounding
error is expensive does.

| Stage | Model | Why |
|---|---|---|
| Knockout triage | **haiku** | One closed question against a short card. Mechanical, high precision, no judgment. |
| Full weighted scoring | **sonnet** | Bounded judgment against an explicit rubric. |
| Adversarial verification | **sonnet**, `effort: high` | Needs scepticism more than raw capability; the prompt supplies the adversarial frame. |
| Company research and targeting | **sonnet** | Fetching, reading and summarizing. |
| **Grounding and rules audit** | **default (the session's own)** | Where the expensive mistakes hide. This agent catches a metric attached to the wrong model, a "most recently" that contradicts the dates printed below it, and a superseded corporate strategy presented as current. Never downgrade it. |
| Drafting | **default** | One call per posting, from the drafting pack. Never downgraded. |

In a Workflow script this is `opts.model` and `opts.effort` per `agent()` call. Omit both to
inherit the session model when unsure: an inherited default is a smaller mistake than a wrong
downgrade.

**"Strongest" means the session's own model.** The drafting and the grounding audit set no
model, so they run on whatever the session runs on, and are never moved to a cheaper one.
When the session's model is not strong enough for a piece of work, `tools/model_guide.py`
says so (at the day's sync, and with `--on` before the work), and its one line goes first in
the reply.

**The one rule that overrides cost:** anything that could put a false claim in front of an employer
runs on the strongest model available, which is the session's own (above). Cheapness is never a reason to risk a fabrication.

**The corollary, learned by measuring:** a cheap model may *extract* and it may *reject on a
quoted fact*, but it may not *judge*. Two attempts to move the fit score onto cheap machinery
were measured against a capable model's scores and both failed - a small model estimating the
score directly was off by 18 points on average, and a deterministic formula over extracted
features was off by 21. Fit turns on whether adjacent-sounding work is actually adjacent, which
is a judgment. The saving comes from sending *fewer postings* to that judgment, never from
faking it. See the table in `job-scraper/SKILL.md` Tier 2.5.

## What not to cut

These look like savings and are not:

- **The second reviewer.** Two parallel reviewers with different jobs cost the same as one doing
  both serially, and catch more, because the grounding audit is not competing with a research pass
  for the same context. In a batch the grounding half is now code first: what the reviewer
  checked mechanically runs in `tools/draft_audit.py`, and the model reads only what code
  flags. That cut the re-reading, never a check.
- **Independent verification of company claims.** Rule 5 in `03-writing-style.md`. Exercised, it
  keeps catching things: a stale strategy, a superseded plan, snippet figures that disagree
  with the live page.
- **Compiling and reading the PDFs.** LaTeX page breaks are not predictable from source.
- **The ATS text-layer extraction.** Cheap, and it verifies what the employer's parser sees.
