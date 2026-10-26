#!/usr/bin/env python3
"""Rank postings by OPPORTUNITY VALUE, deterministically, for zero model tokens.

## What changed and why

The pipeline used to spend most of its budget deciding *not* to apply. The
rejections were the expensive part: a capable model read every posting to emit
one number that was then compared against a bar. That is backwards. Applying is
cheap once tailoring is automated; the scarce resources are the candidate's
review time and the model budget, and neither is well spent on adjudicating
whether a role is a 62 or a 68.

So this file answers a different question, and answers it for free:

    Of everything open right now, which are the BEST ONES TO GO AFTER?

Not "does the candidate clear the bar". Rank, then tailor the top N. A ranking cannot
silently lose a good role the way a threshold can, because nothing is discarded
- the tail is simply not reached.

## What it models that the old scorer did not

**Employer quality.** A 65 at a top-tier employer beats a 75 at a staffing
agency, every time, on pay, brand and what it does for the next move. The old
scorer was blind to who the employer was, so agency reposts and no-name
consultancies outranked real companies.

**Brand leverage.** The names on the candidate's resume carry weight that
offsets stated requirements, and they carry MORE weight in some places than
others: a retailer reading a marquee retailer, or a bank reading a marquee
bank, discounts a missing year in a way a generic employer does not.
This is the single biggest thing the old model ignored, and it is the
candidate's real edge. Where each name carries weight is the profile's.

**Stretch as a cost, not a gate.** A years bar above what is held lowers rank a
little. It never removes a posting. Employers pad those numbers and screeners
read them as guides.

Usage:
    python3 tools/opportunity.py postings.json --top 60 --out ranked.json
    python3 tools/opportunity.py postings.json --explain
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from company_key import key as company_key  # noqa: E402
from text_screen import entry_years, money_values, salary_range  # noqa: E402
from prefilter import age_days as _age_days, posted_age  # noqa: E402
import person  # noqa: E402

# --------------------------------------------------------------------------
# Employer tiers. The point is to spend the candidate's applications on places
# worth working, and to stop agency reposts outranking real companies. The
# lists are the profile's (employers.py), because which employers are worth it
# depends on the person and the market:
#   TIER_1 +30 (top-of-market pay and brand), TIER_2 +20 (major brands),
#   YC_AND_BACKED +14 (trajectory over size), TIER_3 +10 (solid mid-market),
#   AGENCY -30 (staffing agencies and body shops: undisclosed employer,
#   margin-set pay, no next-move value; deprioritised, never removed).
# --------------------------------------------------------------------------
_E = person.module("employers") if person.exists("employers.py") else None
_S = person.module("search")
TIER_1 = set(getattr(_E, "TIER_1", ()))
YC_AND_BACKED = set(getattr(_E, "YC_AND_BACKED", ()))
TIER_2 = set(getattr(_E, "TIER_2", ()))
TIER_3 = set(getattr(_E, "TIER_3", ()))
AGENCY = getattr(_E, "AGENCY", None) or re.compile(r"(?!x)x")


# --------------------------------------------------------------------------
# Brand leverage. Where the names on the resume do disproportionate work.
# --------------------------------------------------------------------------

# The employer describing itself. "We pride ourselves on a culture of
# experimentation" and "a culture rooted in transparency, idea-sharing, and
# experimentation" (one employer's boilerplate on every posting) say nothing
# about the job, so the clause is set aside before an entry that
# names it is read.
SELF_PORTRAIT = re.compile(r"\b(?:culture|foster\w*)\b[^.;!?\n]{0,80}", re.I)

# --------------------------------------------------------------------------
# Brand leverage, core capabilities and the wrong job families are the
# profile's (search.py, OPP_*): where the candidate's own employers do
# disproportionate work, what is held, and which families are a different job.
#   LEVERAGE      (sector pattern, points, why[, "set_aside_self_portrait"])
#   CORE          (pattern, points) for each held capability a posting names
#   TITLE_FAMILY  (pattern, points) read from the title alone: a job family
#                 is the title's claim, and the body's words are the tools and
#                 the neighbouring teams
#   WRONG_FAMILY  (pattern, points) read from the whole posting
# --------------------------------------------------------------------------
LEVERAGE = [(*e[:3], SELF_PORTRAIT) if e[3:] == ("set_aside_self_portrait",) else e
            for e in getattr(_S, "OPP_LEVERAGE", [])]
CORE = list(getattr(_S, "OPP_CORE", []))
TITLE_FAMILY = list(getattr(_S, "OPP_TITLE_FAMILY", []))
WRONG_FAMILY = list(getattr(_S, "OPP_WRONG_FAMILY", []))


# Titles above and below the person's level, docked 12 and 25. Both are the
# person's (profile/search.py OPP_ABOVE_LEVEL, OPP_BELOW_LEVEL): a graduate
# title is below one person and the target of the next. Unset, nothing is
# docked for level.
_NEVER = re.compile(r"(?!x)x")
SENIOR_UP = getattr(_S, "OPP_ABOVE_LEVEL", None) or _NEVER
# Unset, the fit score's own list of levels below the person (FIT_BELOW_LEVEL).
JUNIOR = getattr(_S, "OPP_BELOW_LEVEL", None) or getattr(_S, "FIT_BELOW_LEVEL", None) or _NEVER
# A contract, fixed-term or temporary title, docked 6. Most people want a
# permanent role, so this is the default; a locum, supply or seasonal worker
# sets OPP_CONTRACT = None in search.py (or a narrower pattern).
CONTRACT = getattr(_S, "OPP_CONTRACT",
                   re.compile(r"\b(contract|fixed[- ]term|temporary|\d+[- ]month)\b", re.I)
                   ) or _NEVER
CUR = getattr(_S, "CURRENCY_SYMBOL", "$")

YEARS_HELD = _S.YEARS_HELD
TARGET_PAY = _S.SALARY_TARGET
FLOOR_PAY = _S.SALARY_FLOOR
HIGH_PAY = getattr(_S, "SALARY_HIGH", 2 * TARGET_PAY)
PLAUSIBLE = tuple(getattr(_S, "SALARY_PLAUSIBLE", (0, 10 ** 9)))
_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six",
          7: "seven", 8: "eight", 9: "nine", 10: "ten"}
YEARS_WORDS = _WORDS.get(YEARS_HELD, str(YEARS_HELD))


def _names_in(c: str, names) -> str | None:
    """Match an employer name on word boundaries, longest first.

    Plain substring matching found a short company name ("ace") inside a
    longer word ("Palace" holds "ace"), so unrelated employers were scored as
    YC-backed startups. Short names are exactly the ones that need the
    boundary, and they are the ones a substring test silently ruins.
    """
    for name in sorted(names, key=len, reverse=True):
        if re.search(r"(?<![a-z0-9])" + re.escape(name) + r"(?![a-z0-9])", c):
            return name
    return None


def tier(company: str | None) -> tuple[int, str]:
    """The employer's tier, read through `company_key` as well as the raw name.

    The tier sets are written as the names people say: an initialism. The
    scrape delivers the legal entity, a division's banner or a bilingual dual
    name, and all of those scored zero until the name went through company_key:
    twenty points off the employers the profile names first.

    The raw name is still read first and an agency verdict is final, because the
    key is what strips the tell: `company_key("Creative Solutions Services,
    LLC")` is "creative", and a body shop that comes back as an unknown employer
    has lost the thirty-point penalty that is the whole point of recognizing it.
    """
    raw = _tier_of((company or "").lower().strip())
    if raw[0] < 0:
        return raw
    through_key = _tier_of(company_key(company))
    return through_key if through_key[0] > raw[0] else raw


def _tier_of(c: str) -> tuple[int, str]:
    c = (c or "").lower().strip()
    if not c:
        return 0, ""
    if AGENCY.search(c):
        return -30, "staffing agency or body shop: undisclosed employer, "\
                    "margin-set pay, brand does nothing for the next move"
    n = _names_in(c, TIER_1)
    if n:
        return 30, f"tier 1 employer ({n}): pay, brand and next-move value"
    n = _names_in(c, TIER_2)
    if n:
        return 20, f"tier 2 employer ({n}): major brand, strong pay band"
    # Checked after tier 2 so a name in both keeps the higher score, and above
    # tier 3 because a well-backed startup outranks solid mid-market on pay,
    # equity and what the next move looks like.
    n = _names_in(c, YC_AND_BACKED)
    if n:
        return 14, f"YC or top-tier backed ({n}): equity, pace, senior scope early"
    n = _names_in(c, TIER_3)
    if n:
        return 10, f"tier 3 employer ({n}): solid mid-market or scale-up"
    return 0, ""


def ceiling() -> int:
    """The most this profile's opportunity score can reach: every positive term
    in `score` at its top. A profile with no employer tiers, no leverage and no
    core capabilities tops out at 58 (base 40, a high stated band, posted today).
    """
    tier_top = (30 if TIER_1 else 20 if TIER_2 else 14 if YC_AND_BACKED
                else 10 if TIER_3 else 0)
    core = sum(p for _, p in CORE if p > 0)
    leverage = min(30, sum(e[1] for e in LEVERAGE if e[1] > 0))
    families = sum(max(0, p) for _, p in (*TITLE_FAMILY, *WRONG_FAMILY))
    return 40 + tier_top + core + leverage + families + 12 + 6


# What tools/fit.py divides opportunity by before multiplying it into priority.
# 130 was calibrated on a profile with tiers, leverage and core capabilities,
# whose raw opportunity runs well past 130. Fixed at 130 for everybody, a
# profile without them could never reach the yield target: its opportunity
# tops out near 58, so no posting's priority passed about 45, and every round
# reported a thin market that was really the scale. So the scale is 130 or the
# most this profile can score, whichever is lower; a profile that reaches 130
# ranks exactly as before. `OPP_SCALE` in search.py pins it.
CALIBRATED_SCALE = 130
SCALE = getattr(_S, "OPP_SCALE", None) or min(CALIBRATED_SCALE, ceiling())


_PAY_CUE = re.compile(r"\b(?:salary|salaries|pay|paid|compensation|base|wage|remuneration|"
                      r"per (?:year|annum|hour)|annual(?:ly)?|/\s*(?:yr|year|hr|hour)|ote|"
                      r"package|earn\w*|range)\b", re.I)


def score(job: dict, today: dt.date | None = None) -> dict:
    body = (job.get("desc") or "")[:20000]
    title = job.get("title") or ""
    hay = f"{title}\n{body}"
    pts = 40  # everyone starts as a plausible candidate, not a suspect
    why: list[str] = []

    t, treason = tier(job.get("company"))
    if t:
        pts += t
        why.append(f"{t:+d} {treason}")

    core = [p for pat, p in CORE if pat.search(hay)]      # each pattern searched once
    pts += sum(core)
    if core:
        why.append(f"+{sum(core)} core capability match on {len(core)} signals")

    lev = 0
    for pat, p, reason, *aside in LEVERAGE:
        if pat.search(aside[0].sub(" ", hay) if aside else hay):
            lev += p
            why.append(f"+{p} leverage: {reason}")
    pts += min(lev, 30)  # cap, so leverage tilts rather than dominates

    for families, text in ((TITLE_FAMILY, title), (WRONG_FAMILY, hay)):
        for pat, p in families:
            if pat.search(text):
                pts += p
                why.append(f"{p} job family looks wrong")

    if SENIOR_UP.search(title):
        pts -= 12
        why.append(f"-12 title is a level or two above {YEARS_WORDS} years")
    if JUNIOR.search(title):
        pts -= 25
        why.append("-25 junior or student posting, below the candidate's level")
    if CONTRACT.search(title):
        pts -= 6
        why.append("-6 contract rather than permanent")

    # Stretch is a cost, never a gate. One shared reading of the bar: the entry bar
    # (text_screen.entry_years), the one fit.py scores on, because this is a scoring
    # decision too. The highest bar (stated_years) is for screening: read here it
    # made every posting that lists years per skill look like a Principal role, the
    # fault fit.py had already fixed. Measured from the years held (see tools/fit.py).
    bar, _, _ = entry_years(body)
    over = (bar - YEARS_HELD) if bar else 0
    if bar and over >= 6:
        pts -= 14
        why.append(f"-14 stated {bar}+ years, a long way above {YEARS_HELD}")
    elif bar and over >= 4:
        pts -= 8
        why.append(f"-8 stated {bar}+ years, a real stretch")
    elif bar and over >= 2:
        pts -= 3
        why.append(f"-3 stated {bar}+ years, a mild stretch")

    # Pay signal. A high stated band is a strong positive; a low one is a
    # penalty rather than a cut, because the range is often negotiable and an
    # unstated range is the norm in many markets.
    # The screen's own reading of the stated range (text_screen.salary_range),
    # so the two never disagree about one posting. Where it finds no range and
    # no labelled figure, any amount in the market's currency is the top, as
    # this always read it; a figure stated only as a minimum ("from £40,000")
    # is not a top and earns or costs nothing.
    lo, hi, _ = salary_range(body)
    if hi is None and lo is None:
        # Only a figure in a sentence about pay. Credit and lending postings
        # quote loan limits and portfolio sizes ("loans of up to $50,000"), and
        # read as the pay band they swung opportunity by 30 points for a posting
        # that states no salary at all, which is never penalised.
        pay = " ".join(s for s in re.split(r"(?<=[.!?;])\s+|\n+", body) if _PAY_CUE.search(s))
        sal = [v for v in money_values(pay) if PLAUSIBLE[0] <= v <= PLAUSIBLE[1]]
        hi = max(sal) if sal else None
    if hi is not None and not PLAUSIBLE[0] <= hi <= PLAUSIBLE[1]:
        hi = None
    if hi is not None:
        if hi >= HIGH_PAY:
            pts += 12; why.append(f"+12 stated top of band {CUR}{hi:,}")
        elif hi >= TARGET_PAY:
            pts += 7; why.append(f"+7 stated top of band {CUR}{hi:,}, in the target range")
        elif hi >= FLOOR_PAY:
            pts += 2; why.append(f"+2 stated top of band {CUR}{hi:,}")
        else:
            pts -= 18; why.append(f"-18 stated top of band {CUR}{hi:,}, below the floor")

    # Fresh only on the portal's own date, and only as fresh as the first time this
    # search saw the posting: a relist carries a new portal date, and a month-old
    # posting relisted yesterday earned +6. No date, or a date in the future, is
    # unknown, never fresh.
    age = _age_days(job, today or dt.date.today()) if posted_age(job, today) is not None else None
    if age is not None and 0 <= age <= 2:
        pts += 6; why.append("+6 posted in the last 2 days")
    elif age is not None and 0 <= age <= 5:
        pts += 3; why.append("+3 posted this week")

    if len(body) < 400:
        pts -= 5
        why.append("-5 posting body too thin to read")

    return {**job, "opportunity": pts, "why": why}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("infile")
    ap.add_argument("--out")
    ap.add_argument("--top", type=int, default=60)
    ap.add_argument("--today")
    ap.add_argument("--explain", action="store_true")
    a = ap.parse_args()
    today = dt.date.fromisoformat(a.today) if a.today else dt.date.today()

    data = json.load(open(a.infile, encoding="utf-8"))
    jobs = list(data.values()) if isinstance(data, dict) else list(data)
    out = sorted((score(j, today) for j in jobs),
                 key=lambda x: -x["opportunity"])
    # --out is the pipeline's input for the next stage, so it holds EVERY
    # ranked row. --top controls the console preview only. Truncating the file
    # to --top silently shipped a 1-row file to the next stage, and nothing
    # errored: the run just produced an empty shortlist.
    if a.out:
        json.dump(out, open(a.out, "w", encoding="utf-8", newline="\n"), indent=1)
    for j in out[:a.top]:
        print(f"{j['opportunity']:>4}  {(j.get('company') or '')[:30]:30} "
              f"{(j.get('title') or '')[:52]}")
        if a.explain:
            for w in j["why"]:
                print(f"        {w}")
    print(f"\n{len(jobs)} ranked, top {min(a.top, len(out))} shown "
          f"(0 model tokens)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
