#!/usr/bin/env python3
"""Mechanical screen that decides which postings deserve a real fit score.

## What this is, and what it deliberately is not

It is NOT a scorer. Producing the 0-100 fit score cheaply was tried twice and
measured against a sample of postings that a capable model had already scored
properly:

    cheap model estimating the score directly   mean error about 18
    a deterministic weighted formula            mean error about 21

The formula was *worse*, and it produced false negatives - good roles it would
have discarded. Looking at where it broke explains why, and the reason is not
fixable by tuning constants. Its worst errors were all one kind: a posting whose
words match the profile while the job does not. "Forecasting" that means
financial planning and budgeting, not demand. "Modelling" that means valuation
spreadsheets, not statistics. "Analytics" in a team that exists to serve sales.
And a stated eligibility condition the extraction did not pick up.

The words are homonyms. "Forecasting", "modelling" and "analytics" name different jobs
in different functions, and separating them IS the judgment a fit score
exists to make. No feature vector built from posting keywords will do it.

So this file does the part that genuinely is mechanical: it applies the hard
gates and the stated-fact disqualifiers, and it answers one question per posting.

    Could this posting possibly score 60, given the facts it states?

A `false` is always backed by a stated fact and a quote. A `true` means "the
stated facts do not rule it out", never "this is a good fit" - that call still
costs a real scoring pass, and it should, because it is the call that is hard.

## Why this still saves most of the money

In a typical round, a few dozen postings survive triage and many are fully
scored to find the handful that clear 60. With the disambiguation fields below,
postings like those are screened out on stated facts before scoring - and they
were the formula's worst errors, which is not a coincidence: they are the
postings whose words most misdescribe the work.

Usage:
    python3 tools/score_posting.py extracted.json              # screen verdicts
    python3 tools/score_posting.py extracted.json --pass-only  # ids to score
    python3 tools/score_posting.py extracted.json --explain
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import person  # noqa: E402

# The metro the location gate names (search.py LOCATION metro_name).
_METRO = person.module("search").LOCATION.get("metro_name", "home area")
# The degree held, as the profile's Education line bolds it.
_EDU = re.search(r"\\textbf\{([^}]*)\}", getattr(person.module("roles"), "EDUCATION", "") or "")
_DEGREE_HELD = _EDU.group(1) if _EDU else "the profile's degree"

_SEARCH = person.module("search")
YEARS_HELD = getattr(_SEARCH, "YEARS_HELD", 0)
SALARY_FLOOR = getattr(_SEARCH, "SALARY_FLOOR", 0)
_CUR = getattr(_SEARCH, "CURRENCY_SYMBOL", "$")

# Job families that are not the person's, and the homonym fields that separate
# two jobs sharing a vocabulary. Both are the profile's (search.py
# SCREEN_WRONG_FAMILY and SCREEN_HOMONYMS), because they name the person's own
# field: an analyst's are "reporting and dashboard building is the whole job"
# and "'modelling' here is valuation, not statistics", and those mean nothing
# to a teacher or a nurse. Each pairs the value the extractor returns with the
# reason printed beside the flag:
#   SCREEN_WRONG_FAMILY  {core_function value: why}
#   SCREEN_HOMONYMS      {(field, value): why}
# The extractor is asked for exactly these fields (job-scraper SKILL.md).
# Unset, nothing is flagged on them; flags only order the queue, never cut.
WRONG_FAMILY = dict(getattr(_SEARCH, "SCREEN_WRONG_FAMILY", {}) or {})
HOMONYM_FAILS = dict(getattr(_SEARCH, "SCREEN_HOMONYMS", {}) or {})


def screen(r: dict) -> dict:
    """Cut on stated FACTS only. Flag judgments. Never discard on a classification.

    The first version of this screen also cut on `core_function`, and validation
    caught it discarding roles that scored well: one labelled reporting_bi when
    the job is business analytics with SQL, Python and Tableau; one labelled
    ml_engineering because the narrative mentions deep learning; one cut on a
    Master's the extractor read as required and the scorer did not.

    The lesson is the same one the whole redesign keeps teaching. A job family is a
    judgment, and a cheap model's single label for it is not reliable enough to end
    a posting's life. Facts are different: a stated "7+ years", a stated
    "Master's required", a stated range topping out below the floor. Those are
    quotable, and a quote is now REQUIRED before any cut is made on them.

    So: `cut` for facts, `flags` for everything else. Flags order the scoring queue
    and appear in the report; they never discard.
    """
    cuts: list[str] = []
    flags: list[str] = []
    quote = (r.get("evidence") or "").strip()

    # --- Gates. Hard, and never a matter of degree.
    if r.get("citizenship_pr_or_clearance_required"):
        cuts.append("GATE eligibility: citizenship, PR or a security clearance is "
                    "required as a condition of the role")
    # `language_required` names the language (or is True); `french_required` is the
    # older extraction field, still read so earlier extractions score the same.
    lang = r.get("language_required") or ("French" if r.get("french_required") else None)
    if lang:
        cuts.append("GATE language: %s required as a job condition"
                    % (lang if isinstance(lang, str) else "a language the profile does not hold"))
    if r.get("location_verdict") == "FAIL":
        cuts.append(f"GATE location: {r.get('location') or f'on-site outside the {_METRO}'}")

    # --- Stated-fact disqualifiers. Each needs a quote, or it is only a flag.
    # Years and degree used to CUT here. They no longer do, and the reason is
    # measured: a long scrape yielded only a couple of postings above 60, and
    # the losses were roles a recruiter would shortlist, rejected on a number.
    # Employers pad years bars and screeners read them as guides, so both are
    # now signals that ORDER the queue and let a real scoring pass weigh them.
    yr = r.get("years_required")
    if yr is not None and yr - YEARS_HELD >= 4:
        flags.append(f"stated {yr}+ years against roughly {YEARS_HELD} held; "
                     f"a real stretch, weigh it against the domain match")
    elif yr is not None and yr - YEARS_HELD >= 2:
        flags.append(f"stated {yr}+ years against roughly {YEARS_HELD} held; "
                     f"a stretch, not a bar")

    deg = (r.get("degree_required") or "none").lower()
    if deg in ("masters", "phd"):
        escape = any(p in quote.lower() for p in (
            "or equivalent", "or comparable", "or relevant experience",
            "equivalent experience", "equivalent practical", "or an equivalent"))
        msg = f"stated {deg} required; a {_DEGREE_HELD} is held"
        flags.append(msg + (", but the posting offers an equivalent-experience route"
                            if escape else ""))

    hi = r.get("salary_max")
    if hi is not None and hi < SALARY_FLOOR:
        cuts.append(f"whole stated range tops out at {_CUR}{hi:,}, below the "
                    f"{_CUR}{SALARY_FLOOR:,} walk-away floor")

    # --- Judgment signals. These ORDER the queue. They never discard.
    if r.get("people_management_required") and not getattr(_SEARCH, "MANAGES_PEOPLE", False):
        flags.append("direct reports required; no formal people management held")
    fn = r.get("core_function") or "other"
    if fn in WRONG_FAMILY:
        flags.append(f"job family may be wrong: {WRONG_FAMILY[fn]}")
    for (field, bad), why in HOMONYM_FAILS.items():
        if (r.get(field) or "") == bad:
            flags.append(f"vocabulary: {why}")
    if r.get("contract_not_permanent"):
        flags.append("fixed-term or contract role, not permanent")

    return {
        "id": r.get("id"), "company": r.get("company"), "title": r.get("title"),
        "score_it": not cuts,
        "cuts": cuts,
        "flags": flags,
        "priority": len(flags),   # fewer flags first in the scoring queue
        "evidence": quote,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("infile")
    ap.add_argument("--pass-only", action="store_true",
                    help="print only the ids that should be scored")
    ap.add_argument("--explain", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    recs = json.load(open(a.infile))
    if isinstance(recs, dict):
        recs = list(recs.values())
    out = [screen(r) for r in recs]
    keep = [s for s in out if s["score_it"]]

    if a.json:
        print(json.dumps(out, indent=1))
    elif a.pass_only:
        for s in keep:
            print(s["id"])
    else:
        for s in sorted(out, key=lambda x: (not x["score_it"], x["priority"], x["company"] or "")):
            mark = "SCORE " if s["score_it"] else "screen"
            print(f"{mark} {(s['company'] or '')[:28]:28} {(s['title'] or '')[:44]:44}")
            for why in s["cuts"]:
                print(f"         CUT  {why}")
            if a.explain:
                for why in s["flags"]:
                    print(f"         flag {why}")

    print(f"\n{len(recs)} screened, {len(keep)} go to full scoring, "
          f"{len(recs) - len(keep)} ruled out on stated facts (0 model tokens)",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
