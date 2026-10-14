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
from text_screen import stated_years  # noqa: E402
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
JUNIOR = getattr(_S, "OPP_BELOW_LEVEL", None) or _NEVER
CONTRACT = re.compile(r"\b(contract|fixed[- ]term|temporary|\d+[- ]month)\b", re.I)
CUR = getattr(_S, "CURRENCY_SYMBOL", "$")
SALARY = re.compile(re.escape(CUR) + r"\s?(\d{2,3})[,\s]?(\d{3})")

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

    seen_core = 0
    for pat, p in CORE:
        if pat.search(hay):
            pts += p
            seen_core += 1
    if seen_core:
        why.append(f"+{sum(p for pat,p in CORE if pat.search(hay))} "
                   f"core capability match on {seen_core} signals")

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

    # Stretch is a cost, never a gate. One shared reading of the bar
    # (text_screen.stated_years): requirement-cued, boast-guarded, low end of a
    # range. The old max() over every "N years" in the body docked -14 for
    # "over 20 years of experience delivering" and "18 years or older".
    bar, _ = stated_years(body)
    if bar and bar >= 10:
        pts -= 14
        why.append(f"-14 stated {bar}+ years, a long way above {YEARS_HELD}")
    elif bar and bar >= 8:
        pts -= 8
        why.append(f"-8 stated {bar}+ years, a real stretch")
    elif bar and bar >= 6:
        pts -= 3
        why.append(f"-3 stated {bar}+ years, a mild stretch")

    # Pay signal. A high stated band is a strong positive; a low one is a
    # penalty rather than a cut, because the range is often negotiable and an
    # unstated range is the norm in many markets.
    sal = [int(f"{a}{b}") for a, b in SALARY.findall(body)]
    sal = [s for s in sal if PLAUSIBLE[0] <= s <= PLAUSIBLE[1]]
    if sal:
        hi = max(sal)
        if hi >= HIGH_PAY:
            pts += 12; why.append(f"+12 stated top of band {CUR}{hi:,}")
        elif hi >= TARGET_PAY:
            pts += 7; why.append(f"+7 stated top of band {CUR}{hi:,}, in the target range")
        elif hi >= FLOOR_PAY:
            pts += 2; why.append(f"+2 stated top of band {CUR}{hi:,}")
        else:
            pts -= 18; why.append(f"-18 stated top of band {CUR}{hi:,}, below the floor")

    d = job.get("date")
    if d:
        try:
            age = ((today or dt.date.today()) - dt.date.fromisoformat(str(d)[:10])).days
            if age <= 2:
                pts += 6; why.append("+6 posted in the last 2 days")
            elif age <= 5:
                pts += 3; why.append("+3 posted this week")
        except ValueError:
            pass

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

    data = json.load(open(a.infile))
    jobs = list(data.values()) if isinstance(data, dict) else list(data)
    out = sorted((score(j, today) for j in jobs),
                 key=lambda x: -x["opportunity"])
    # --out is the pipeline's input for the next stage, so it holds EVERY
    # ranked row. --top controls the console preview only. Truncating the file
    # to --top silently shipped a 1-row file to the next stage, and nothing
    # errored: the run just produced an empty shortlist.
    if a.out:
        json.dump(out, open(a.out, "w"), indent=1)
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
