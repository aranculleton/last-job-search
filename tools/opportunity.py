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
    python3 tools/opportunity.py documents/rounds/<round>.json --leverage-words
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
from text_screen import _PAY_LOCAL, entry_years, money_values, salary_range  # noqa: E402
from prefilter import age_days as _age_days, posted_age  # noqa: E402
import person  # noqa: E402
import wants as _wants  # noqa: E402

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
# Each set is the one in employers.py joined to the employers the record of what the person
# wants lifts (profile/wants.json, tools/wants.py, issue 327), which the profile upgrade
# wants-moved takes the sets into, every entry's lift unchanged.
_IN = _wants.held_tiers()
TIER_1 = set(getattr(_E, "TIER_1", ())) | _IN["TIER_1"]
YC_AND_BACKED = set(getattr(_E, "YC_AND_BACKED", ())) | _IN["YC_AND_BACKED"]
TIER_2 = set(getattr(_E, "TIER_2", ())) | _IN["TIER_2"]
TIER_3 = set(getattr(_E, "TIER_3", ())) | _IN["TIER_3"]
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
#   LEVERAGE      (pattern, points, why[, where it reads][, "set_aside_self_portrait"]).
#                 Where it reads is SCOPES, below. The lifts count strongest first,
#                 each after the first at half the one before (count_lifts), and
#                 together up to LEVERAGE_CAP; a penalty (negative points) counts in
#                 full, whatever the lifts came to
#   CORE          (pattern, points) for each held capability a posting names
#   TITLE_FAMILY  (pattern, points[, why]) read from the title alone: a job
#                 family is the title's claim, and the body's words are the
#                 tools and the neighbouring teams
#   WRONG_FAMILY  (pattern, points[, why]) read from the whole posting
# A family entry with no why says "job family looks wrong" when it docks, as it
# always did; one that lifts, or a penalty for a preference (long hours, a live
# coding test), says its own why. Neither family list is capped.
# --------------------------------------------------------------------------
LEVERAGE = list(getattr(_S, "OPP_LEVERAGE", []))
CORE = list(getattr(_S, "OPP_CORE", []))
TITLE_FAMILY = list(getattr(_S, "OPP_TITLE_FAMILY", []))
WRONG_FAMILY = list(getattr(_S, "OPP_WRONG_FAMILY", []))
# The most the lifts of LEVERAGE add together, so leverage tilts rather than dominates. Only
# the lifts: a penalty written there was swallowed by the cap on any posting whose lifts passed
# it by more than the penalty, so it bit only on postings that were already weak (2026-11-16).
LEVERAGE_CAP = 30
# And each lift after the strongest counts half what it would have one place higher: a posting
# that named five things the person finds a little familiar, six points each, outranked one that
# was squarely the work they want, twenty points, 30 against 20 (issue 327).
_FRACTIONS = {1: "half", 2: "a quarter", 3: "an eighth", 4: "a sixteenth"}


def count_lifts(points: list) -> list[tuple[int, int, float, bool]]:
    """Each lift as it counts, strongest first (a tie in the profile's order): (its place in
    `points`, its rank from 0, what it counts, whether LEVERAGE_CAP held it back). The
    strongest counts in full, the next at half, the next at a quarter and so on, each rounded
    to whole points, and together they stop at LEVERAGE_CAP: one strong reason to want a job is
    not outweighed by many small ones."""
    out, total = [], 0
    for rank, i in enumerate(sorted(range(len(points)), key=lambda k: -points[k])):
        p = points[i]
        full = p if rank == 0 else int(p / 2 ** rank + 0.5)
        got = max(0, min(full, LEVERAGE_CAP - total))
        total += got
        out.append((i, rank, got, got < full))
    return out


def _lift_says(points, rank: int, got, held: bool, reason: str) -> str:
    """A lift's line in `why`: what it counted, and where that is not its points, why."""
    if rank == 0 and not held:
        return f"{points:+d} leverage: {reason}"
    bits = [f"{points:+d}"]
    if rank:
        nth = rank + 1
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(nth % 10 if nth % 100 not in (11, 12, 13)
                                                 else 0, "th")
        bits.append(f"the {nth}{suffix} lift, counts "
                    + _FRACTIONS.get(rank, f"1/{2 ** rank}"))
    if held:
        bits.append(f"the lifts held to +{LEVERAGE_CAP}")
    return f"{got:+d} leverage: {reason} ({', '.join(bits)})"

# Where a leverage entry reads. Every lift read the whole posting, and every posting repeats the
# same boilerplate, so an entry meant to recognize the employer's sector or the work fired on
# words that say nothing about either: over one evening's 73 postings the travel-industry lift
# fired 11 times on "travel", none at a travel employer ("Travel Requirements: 15%", "travel to
# customers up to 30% of the time", "global travel coverage" in a benefits list), the
# consulting lift 21 times on "stakeholder engagement", and the work-life lift 20 times on a
# bare "hybrid" (2026-11-16, #306). An entry names where it reads as an item after its why:
#   "employer"  what the employer is: the employer field, the title, what the person's own
#               catalogue calls it (employers.py, sector.kind) and the posting's sentences
#               about the employer itself, boilerplate set aside. For a sector or a kind of
#               employer (media, travel, consulting, the public sector)
#   "work"      the title and the posting with its boilerplate set aside: benefits and perks,
#               the equal-opportunity paragraph, travel asked of the person and the work model,
#               and duties every posting lists ("stakeholder engagement"). For what the role
#               does (pricing, risk, experiments)
#   "terms"     the whole posting, travel and the work model included, but a bare "hybrid",
#               which most office jobs say, is no sign of anything. For working terms
#               ("flexible hours", "no on-call")
#   "any"       the whole posting
# Named nowhere, a lift reads "work", or "terms" where its pattern names a working term whole
# (TERMS_SAID), and a penalty reads "any": a penalty for heavy travel reads the travel asked.
SCOPES = ("employer", "work", "terms", "any")
# A cue that the sentence it is in is boilerplate.
BOILERPLATE = re.compile(
    r"\b(?:"
    # benefits and perks
    r"benefits?|perks?|group (?:rrsp|insurance|benefits)|rrsp match\w*|pension match\w*|"
    r"matched pension|401\s?\(?k\)?|paid time off|pto|(?:paid|weeks? of|days? of) vacation|"
    r"vacation (?:days|time|allowance)|parental leave|"
    r"wellness (?:days?|allowance|stipend|programs?)|(?:staff|employee|travel) discounts?|"
    r"(?:health|dental|medical|life|travel) (?:insurance|coverage|cover)|"
    # the equal-opportunity paragraph
    r"equal (?:employment )?opportunit\w*|regardless of|"
    r"(?:request|need|require)\w* (?:an? )?accommodations?|"
    r"accommodations? (?:are|is|will be) (?:available|provided)|"
    # travel asked of the person
    r"travel requirements?|travel (?:is )?required|(?:willing\w*|able|ability) to travel|"
    r"travel (?:of )?up to|\d{1,3}\s?% (?:of the time )?travel|travel \d{1,3}\s?%|"
    r"occasional(?:ly)? travel|travel to (?:customers?|clients?|the office|our offices?|sites?)|"
    # the work model
    r"hybrid|in[- ]office|on[- ]site|work(?:ing)? model|days? (?:a|per) week (?:in|at|from)|"
    r"remote[- ](?:role|position|work\w*|first|option)|work(?:ing)? remotely"
    r")\b", re.I)
# A sentence, or the run of punctuation between two. Read piece by piece, a body is set aside in
# one pass: a pattern spanning "the sentence around a cue" backtracked over the whole of a body
# with no full stop in it, 26 seconds for one posting of 20,000 characters.
_PIECE = re.compile(r"[^.!?\n]+[.!?]?|[.!?\n]+")
# Longer than this, a piece is no sentence (a body with no full stops), and only the words
# around each cue are set aside.
_LONG_PIECE = 400
_NEAR_CUE = re.compile(r"(?:\S+\s+){0,8}?\S*" + BOILERPLATE.pattern + r"\S*(?:\s+\S+){0,8}",
                       re.I)


def set_aside_boilerplate(text: str) -> str:
    """`text` with each sentence holding a boilerplate cue set aside (BOILERPLATE)."""
    out = []
    for piece in _PIECE.findall(text):
        if not BOILERPLATE.search(piece):
            out.append(piece)
        elif len(piece) <= _LONG_PIECE:
            out.append(" ")
        else:
            out.append(_NEAR_CUE.sub(" ", piece))
    return "".join(out)


# Duties every posting lists, never the employer's line of business.
DUTY_WORDS = re.compile(r"\b(?:stakeholder|customer|employee|community|user)s?\s+engagement\b",
                        re.I)
BARE_HYBRID = re.compile(r"\bhybrid\b", re.I)
# A sentence where the employer says what it is.
SAYS_WHAT_IT_IS = re.compile(r"\b(?:about us|about the company|who we are|"
                             r"we(?: are|'re|\u2019re) (?:a|an|one of)|our mission|founded|"
                             r"headquartered)\b", re.I)
# Working terms a lift may name whole; an entry whose pattern matches one of them entire reads
# "terms" unless it says otherwise. A sector's word inside one ("travel" in "travel up to 50%")
# is not a term named whole.
TERMS_SAID = ("flexible hours", "flexible working", "flexible schedule", "work-life balance",
              "work life balance", "4-day week", "four-day week", "remote-first", "fully remote",
              "summer hours", "compressed hours", "no on-call")
_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")


def _names_terms(pat) -> bool:
    for t in TERMS_SAID:
        m = pat.search(t)
        if m and m.group(0).lower() == t:
            return True
    return False


def scope_named(entry) -> str:
    """The scope a leverage entry names after its why, or ""."""
    return next((x for x in entry[3:] if isinstance(x, str) and x in SCOPES), "")


def _scoped(entry) -> tuple:
    """(pattern, points, why, where it reads, what it sets aside) for a leverage entry: its
    why may be followed by a scope (SCOPES) and "set_aside_self_portrait" (or a pattern of
    its own to set aside), in either order."""
    pat, p, reason, *rest = entry
    aside = None
    for x in rest:
        if x == "set_aside_self_portrait":
            aside = SELF_PORTRAIT
        elif hasattr(x, "sub"):
            aside = x
    scope = scope_named(entry) or (
        "any" if (p or 0) < 0
        else "terms" if pat is not None and _names_terms(pat)
        else "work")
    return pat, p, reason, scope, aside


def unscoped() -> list[str]:
    """The why of each lift in the profile's leverage that names no scope: one meant for the
    employer's sector reads the work instead, duties and all, until it says "employer"."""
    return [str(e[2]) for e in LEVERAGE if len(e) >= 3 and (e[1] or 0) > 0
            and not scope_named(e)]


def employer_says(job: dict, body: str) -> str:
    """What a posting says its employer is: the employer field, the title, what the person's
    own catalogue calls it, and the posting's sentences about the employer itself (one that
    says what it is, or names it and goes on "is" or "are"), its boilerplate set aside."""
    company = str(job.get("company") or "")
    kind = ""
    try:
        import sector  # it imports this module, so it is read here, at call time
        kind = sector.kind(company)
    except Exception:  # noqa: BLE001  no catalogue to read: the posting's own words stand
        pass
    first = re.escape(company.split()[0]) if company.split() else ""
    named = (re.compile(r"\b" + first + r"\w*(?:\s+\S+){0,3}?\s+(?:is|are|was|has been)\b", re.I)
             if first and len(company.split()[0]) > 2 else None)
    said = [s for s in _SENTENCE.split(DUTY_WORDS.sub(" ", set_aside_boilerplate(body)))
            if SAYS_WHAT_IT_IS.search(s) or (named and named.search(s))]
    return "\n".join([company, str(job.get("title") or ""), kind] + said[:6])


def read_for(scope: str, job: dict, title: str, body: str) -> str:
    """The text a leverage entry of `scope` reads."""
    if scope == "employer":
        return employer_says(job, body)
    if scope == "work":
        return f"{title}\n" + DUTY_WORDS.sub(" ", set_aside_boilerplate(body))
    if scope == "terms":
        return BARE_HYBRID.sub(" ", f"{title}\n{body}")
    return f"{title}\n{body}"


def family_says(points: int, why: str = "") -> str:
    """A job family entry's line in a score's reasons: its own why where the profile gives one,
    else the wrong-family words for a penalty and plain words for a lift."""
    if why:
        return f"{points:+d} {why}"
    return f"{points} job family looks wrong" if points < 0 else f"{points:+d} a job family you rank up"


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
    # Only a name the text holds can match on its boundaries, so it alone is looked for, by
    # an expression made once: one made for every name of the person's lists on every call,
    # past the few hundred Python keeps, was made again each time, 1.46 million lookups a page
    # build (the second audit, 2026-11-10, D8). And only those are put in order, longest
    # first: the whole list of some 500 names was sorted again on every call, 0.6 s a build.
    for name in sorted((n for n in names if n and n in c), key=len, reverse=True):
        if _bounded(name).search(c):
            return name
    return None


_BOUNDED: dict = {}


def _bounded(name: str) -> "re.Pattern":
    got = _BOUNDED.get(name)
    if got is None:
        got = _BOUNDED[name] = re.compile(r"(?<![a-z0-9])" + re.escape(name) + r"(?![a-z0-9])")
    return got


def tier(company: str | None) -> tuple[int, str]:
    """The employer's tier (`_tier`), worked out once a page build for each employer: a job's
    employer was read against every list twice a job (the second audit, D8)."""
    import remembered
    return remembered.get("tier", company, lambda: _tier(company))


def _tier(company: str | None) -> tuple[int, str]:
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
    leverage = sum(got for _, _, got, _ in count_lifts([e[1] for e in LEVERAGE if e[1] > 0]))
    families = sum(max(0, e[1]) for e in (*TITLE_FAMILY, *WRONG_FAMILY))
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
                      r"package|earn\w*|range|" + _PAY_LOCAL + r")\b", re.I)


def _public(company, posting) -> bool:
    """bar.is_public, read here at call time (bar imports this module's tiers)."""
    try:
        import bar
        return bar.is_public(company, posting)
    except Exception:  # noqa: BLE001  no bar to read: no public rule to hold to
        return False


def score(job: dict, today: dt.date | None = None) -> dict:
    body = (job.get("desc") or "")[:20000]
    title = job.get("title") or ""
    hay = f"{title}\n{body}"
    pts = 40  # everyone starts as a plausible candidate, not a suspect
    why: list[str] = []

    t, treason = tier(job.get("company"))
    if t > 0 and _public(job.get("company"), body):
        # A public body earns no employer-tier lift, whichever tier list names it: the
        # public rule is a hard no but for pay, and a provincial agency on a tier list
        # ranked +10 next to the agencies the profile names as hard nos (2026-11-03).
        why.append(f"+0 a public body: no lift from its employer tier ({treason})")
        t = 0
    if t:
        pts += t
        why.append(f"{t:+d} {treason}")

    core = [p for pat, p in CORE if pat.search(hay)]      # each pattern searched once
    pts += sum(core)
    if core:
        why.append(f"+{sum(core)} core capability match on {len(core)} signals")

    lifts, docks = [], []
    texts: dict = {}
    for entry in LEVERAGE:
        pat, p, reason, scope, aside = _scoped(entry)
        if scope not in texts:
            texts[scope] = read_for(scope, job, title, body)
        if pat.search(aside.sub(" ", texts[scope]) if aside else texts[scope]):
            (lifts if p >= 0 else docks).append((p, reason))
    counted = count_lifts([p for p, _ in lifts])
    for i, rank, got, held in counted:
        pts += got
        why.append(_lift_says(lifts[i][0], rank, got, held, lifts[i][1]))
    total = sum(got for _, _, got, _ in counted)
    if total != sum(p for p, _ in lifts):
        why.append(f"leverage lifts counted {total:+d} of {sum(p for p, _ in lifts):+d}: the "
                   "strongest in full, the next at half, the next at a quarter and so on, "
                   f"+{LEVERAGE_CAP} at most")
    for p, reason in docks:
        pts += p
        why.append(f"{p:+d} leverage: {reason}")

    for families, text in ((TITLE_FAMILY, title), (WRONG_FAMILY, hay)):
        for pat, p, *said in families:
            if pat.search(text):
                pts += p
                why.append(family_says(p, str(said[0]) if said else ""))

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


def leverage_words(jobs) -> list[str]:
    """Each leverage entry's hits over `jobs` (rows with their posting text) and the five
    words it most often matched, read as score() reads them."""
    from collections import Counter
    out = []
    for entry in LEVERAGE:
        pat, p, reason, scope, aside = _scoped(entry)
        words: Counter = Counter()
        hits = 0
        for j in jobs:
            if not isinstance(j, dict):
                continue
            text = read_for(scope, j, j.get("title") or "", (j.get("desc") or "")[:20000])
            text = aside.sub(" ", text) if aside else text
            found = [m.group(0).lower() for m in pat.finditer(text)]
            if found:
                hits += 1
                words.update(set(found))
        top = ", ".join(f"{w} {n}" for w, n in words.most_common(5))
        out.append(f"{p:+d} ({scope}) {hits} of {len(jobs)}: {reason[:60]}"
                   + (f" [{top}]" if top else ""))
    return out


def with_kept_text(jobs: list, infile: str) -> list:
    """`jobs` with the posting text a search keeps beside its list (bodies/<name>.json, as
    tools/rescore.py keeps it) where a row has none of its own."""
    path = os.path.join(os.path.dirname(os.path.abspath(infile)), "bodies",
                        os.path.basename(infile))
    try:
        with open(path, encoding="utf-8") as fh:
            bodies = (json.load(fh) or {}).get("bodies") or {}
    except (OSError, ValueError, AttributeError):
        return jobs
    from lookup_score import norm
    return [dict(j, desc=bodies.get(norm(str(j.get("url") or "")) or "", ""))
            if isinstance(j, dict) and not j.get("desc") else j for j in jobs]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("infile")
    ap.add_argument("--out")
    ap.add_argument("--top", type=int, default=60)
    ap.add_argument("--today")
    ap.add_argument("--explain", action="store_true")
    ap.add_argument("--leverage-words", dest="leverage_words", action="store_true",
                    help="for each leverage entry, where it reads, how many of the postings "
                         "in infile it fires on and the words it most often matched: a word "
                         "firing for the wrong reason shows here. A search's kept list "
                         "(documents/rounds/<round>.json) is read with the text kept beside it")
    a = ap.parse_args()
    today = dt.date.fromisoformat(a.today) if a.today else dt.date.today()

    data = json.load(open(a.infile, encoding="utf-8"))
    jobs = list(data.values()) if isinstance(data, dict) else list(data)
    if a.leverage_words:
        for line in leverage_words(with_kept_text(jobs, a.infile)):
            print(line)
        return 0
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
