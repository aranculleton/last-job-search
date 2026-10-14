#!/usr/bin/env python3
"""Will they call the candidate back? Scored separately from whether the job is worth having.

## Why this file exists

Two models were tried and both failed in opposite directions.

The conservative model scored clause satisfaction. It passed almost nothing,
and the applications it did produce were all in one seniority band - Senior
Analyst, Consultant, Analyst II, Manager. It was too tight, but what it did
surface was the right shape.

The opportunity model replaced it and swung the other way. It ADDED employer
tier (up to +30) and brand leverage (up to +30) to the fit signals, so prestige
outweighed a seniority mismatch worth -12, and a large share of its picks were
Lead or Staff roles. **A Lead, Staff or Principal title is a different band
from the one the years held support.** That is the overreach, and it is
measurable rather than a matter of taste.

## The fix

Two questions, kept apart:

    fit          would this employer plausibly interview the candidate?
    opportunity  is this a job worth having? (tools/opportunity.py)

`priority = fit * opportunity / 100`, a PRODUCT rather than a sum. A brilliant
job they will not get scores low. A job they would walk into that is not worth
having scores low. Only both together score high. Addition let one compensate
for the other, which is precisely the bug.

Seniority is the single strongest predictor here and neither model had it.
The bands (the profile's FIT_BANDS) are calibrated on real applications, not
on intuition.

Seniority words are read as TITLE TOKENS, not substrings: "Analyst, VP Finance"
names a department, "Principal Component Analysis" names a method, and neither
is a band. The years bar comes from `text_screen.entry_years`, which returns the
LOWEST bar a posting states rather than the highest: a requirements list saying
"3+ years in analytics" beside an ideal-candidate paragraph saying "10+ years in
logistics" is a wish list, not a ten-year role, and the lower figure is
what a recruiter screens on. Both readings share the screen's sentence parsing,
so a company boast ("over 20 years of experience delivering...") never docks a
posting here.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from text_screen import NOT_A_DEGREE, entry_years, sentences  # noqa: E402
from prefilter import location_verdict  # noqa: E402
import person  # noqa: E402

_S = person.module("search")
YEARS_HELD = _S.YEARS_HELD
_PRON = person.get("identity.pronouns", {"object": "them", "possessive": "their"})
_HIS, _HIM = _PRON.get("possessive", "their"), _PRON.get("object", "them")
_FLAG_COSTS = list(getattr(_S, "LOCATION_FLAG_COSTS", []))
_FLAG_DEFAULT = tuple(getattr(_S, "LOCATION_FLAG_DEFAULT", (10, "outside the home pass set, decided later")))
_DEGREE_FLAGS = getattr(_S, "DEGREE_FLAGS", True)

# Below this, a callback is unlikely enough that the draft is not worth writing.
FIT_FLOOR = 65

# What a live contact at the employer is worth. Deliberately large: a referred
# application is read by a person rather than sorted by a queue, and that is a
# bigger swing than any single tool named in a posting. It also lifts the role
# clear of the floor's demotion, because the floor's own justification is that
# below it an application is a lottery ticket, which a referral is not.
REFERRAL_BONUS = 12

# --------------------------------------------------------------------------
# What the candidate's job is, from the profile (search.py FIT_*). Each list is
# (pattern, points, label) unless noted; first match wins where order matters.
#   BANDS         seniority from the title, calibrated to the years held
#   WRONG_FAMILY  professions that share a word with the target job
#   WRONG_DOMAIN  domains, tested against the title's family head only
#   CORE          capabilities the candidate uses daily, as a posting names them
#   MISSING       capabilities genuinely not held: weighed by how hard they are
#                 asked for and what honest neighbour covers them
#   DOMAIN        (pattern, weight, label) industries actually worked, which buy
#                 down gaps
#   ROLE_SHAPE    the job the candidate already does (pattern)
#   DOMAIN_YEARS  a years bar qualified to a domain never worked (pattern)
#   IN_FAMILY_HEAD  unambiguous in-family role nouns (pattern)
# --------------------------------------------------------------------------
BANDS = list(_S.FIT_BANDS)
WRONG_FAMILY = list(getattr(_S, "FIT_WRONG_FAMILY", []))
WRONG_DOMAIN = list(getattr(_S, "FIT_WRONG_DOMAIN", []))
_REPORTS_RULE = getattr(_S, "FIT_REPORTS_RULE", None)
REPORTS = _REPORTS_RULE[0] if _REPORTS_RULE else re.compile(r"(?!x)x")
CORE = list(_S.FIT_CORE)
MISSING = list(getattr(_S, "FIT_MISSING", []))
DOMAIN = list(getattr(_S, "FIT_DOMAIN", []))
ROLE_SHAPE = getattr(_S, "FIT_ROLE_SHAPE", re.compile(r"(?!x)x"))
DOMAIN_YEARS = getattr(_S, "FIT_DOMAIN_YEARS", re.compile(r"(?!x)x"))
IN_FAMILY_HEAD = getattr(_S, "FIT_IN_FAMILY_HEAD", re.compile(r"(?!x)x"))
JUNIOR = re.compile(
    r"\b(intern|internship|co[- ]?op|student|graduate|junior|entry[- ]level|"
    # "New Grad" is a common phrasing and does not contain "graduate".
    r"new grad\w*|campus|early career|apprentice|trainee|"
    # A postdoc is a research post, not a step up from four years in industry.
    r"post[- ]?doc\w*|postdoctoral|research fellow|phd candidate)\b", re.I)

# Job boards and aggregators list other companies' roles under their own name.
# The posting may be real, but the employer is unknown, so it cannot be scored
# or written to. Ranked down rather than dropped, since the role can be traced.
BOARD = re.compile(
    r"\b(jobright|gamblingcareers|jobgether|ziprecruiter|glassdoor|talent\.com|"
    r"jooble|neuvoo|whatjobs|careerbuilder|simplyhired|adzuna|jobsite|"
    r"jobs?\s*board|careers?\s*page)\b", re.I)


# How hard a sentence actually asks for something.
#
# A bare mention keeps most of its weight: a tool listed under "Requirements"
# with no qualifier is a real ask. What changes is the two ends.
HARD_REQUIRE = re.compile(
    r"\b(must have|must be|required|requires?|minimum|at least|essential|"
    r"you (?:will )?need|proven|demonstrated|extensive|deep|strong|expert|"
    r"\d\+?\s*years?)\b", re.I)
SOFT_WANT = re.compile(
    r"\b(preferred|nice to have|a plus|bonus|desirable|an asset|ideally|"
    r"familiarity|exposure|awareness|willing(?:ness)? to learn|"
    r"appetite for|curiosity about|would be great|welcome)\b", re.I)
# The employer describing itself, not asking the candidate for anything. "Our platform is
# built on Kafka" is context; "you will build on Kafka" is a requirement.
COMPANY_CONTEXT = re.compile(
    r"\b(our|we|the team|the company|the platform|the stack|built on|runs on|"
    r"powered by|migrating to)\b", re.I)

DEMAND_HARD, DEMAND_BARE, DEMAND_SOFT, DEMAND_NONE = 1.0, 0.6, 0.2, 0.0

# How much an honest neighbour reduces the risk. A bridge is not a claim to the
# skill; it is evidence the candidate can do the work the skill was listed for,
# which is what the penalty was ever trying to measure.
BRIDGE_MULTIPLIER = {"held": 0.0, "near": 0.15, "mid": 0.45, "far": 0.75}


# ---------------------------------------------------------------- the slack
#
# Gaps are not read in isolation. A posting can be missing three of its named
# tools and still be the best fit in the round, because the industry is one the
# candidate has worked, the job is the shape of the job they do now, and the
# posting's core asks are things they do daily. A similar industry, a very
# similar role, a live contact or meeting the core requirements each buys down
# a gap, and all on a sliding scale.
#
# So strengths buy down gaps. `slack()` returns 0.0 to SLACK_CAP, and every gap
# penalty and the years bar are multiplied by (1 - slack). It never reaches 1.0:
# a genuinely wrong role must still score down, or the ranking stops meaning
# anything and everything reaches the shortlist.
SLACK_CAP = 0.8

# Core capability, and why the cap is soft.
#
# It used to be `min(sum(...), 36)`. A posting naming five of the candidate's core
# capabilities and one naming nine both scored 36, and that hard clamp is most
# of why so many rows shared a fit score with another row. The ranking stopped
# discriminating exactly in the band the candidate chooses from.
#
# Full value to CORE_FULL, then half value, hard stop at CORE_MAX. A ninth
# match is worth less than the first but is no longer worth nothing, and the
# ceiling still stops a keyword-stuffed posting outscoring a real one.
CORE_FULL, CORE_TAPER, CORE_MAX = 36, 0.5, 48

# How much of the years bar the slack may buy down, by band. A strong domain
# and role-shape match is a reason to stretch, and the whole point of the slack
# is that a wish list is not law. It is not a reason to pretend a Principal
# posting is an analyst one, so the rescue shrinks as the bar climbs.
YEARS_SLACK_CAP = {9: 0.45, 11: 0.25}


def _core_points(raw: int) -> int:
    """Diminishing returns above CORE_FULL rather than a cliff at it."""
    if raw <= CORE_FULL:
        return raw
    return min(CORE_MAX, CORE_FULL + round((raw - CORE_FULL) * CORE_TAPER))


# Weights. Core density is the largest because it is the most direct evidence:
# it counts how much of what the posting actually asks for the candidate already does.
W_CORE, W_DOMAIN, W_SHAPE, W_WARM = 0.40, 0.30, 0.15, 0.15


def slack(hay, title, core_points, warm=False):
    """How much benefit of the doubt this posting has earned, 0.0 to SLACK_CAP.

    Returns (slack, reasons). Multiplied into every gap penalty and the years
    bar, so a posting that matches the candidate's industry and job shape is not thrown
    away over three tools it happens to name.
    """
    reasons = []

    # Density against CORE_FULL, uncapped on the way in. `core_points` is the
    # raw sum, not the tapered score, so a posting matching nine of the candidate's
    # capabilities earns more benefit of the doubt than one matching five.
    core = max(0.0, min(1.0, core_points / float(CORE_FULL)))
    if core:
        reasons.append("core capabilities %d%%" % round(core * 100))

    dom, dom_why = 0.0, ""
    for pat, weight, label in DOMAIN:
        if pat.search(hay):
            if weight > dom:
                dom, dom_why = weight, label
    dom = min(1.0, dom / 0.30)
    if dom_why:
        reasons.append(dom_why)

    shape = 1.0 if ROLE_SHAPE.search(title or "") else 0.0
    if shape:
        reasons.append("same job shape")

    warm_f = 1.0 if warm else 0.0
    if warm_f:
        reasons.append("live contact at the employer")

    raw = W_CORE * core + W_DOMAIN * dom + W_SHAPE * shape + W_WARM * warm_f
    return min(SLACK_CAP, raw), reasons


def _demand(sentence):
    """0.0 to 1.0: how much this sentence asks the candidate for the thing."""
    if SOMEONE_ELSES.search(sentence):
        return DEMAND_NONE
    if SOFT_WANT.search(sentence):
        return DEMAND_SOFT
    if HARD_REQUIRE.search(sentence):
        return DEMAND_HARD
    if COMPANY_CONTEXT.search(sentence):
        return DEMAND_NONE
    return DEMAND_BARE


def _bridge_multiplier(sentence):
    """How much an honest adjacent capability softens this, 0.0 to 1.0."""
    try:
        import bridges
    except ImportError:
        return 1.0
    found = bridges.assess(sentence)
    if not found:
        return 1.0
    best = found[0]
    if best.verdict == bridges.HELD:
        return BRIDGE_MULTIPLIER["held"]
    if best.verdict == bridges.BRIDGE:
        return BRIDGE_MULTIPLIER.get(bridges.strength_of(best.asked), 0.45)
    return 1.0

# A capability named as somebody else's is not a gap. "Collaborate with Java
# engineering teams to consume event-based data" costs nothing: the Java is
# theirs, the consuming is the candidate's. Checked against the sentence a
# MISSING pattern matched, so the penalty only lands when the posting asks the
# CANDIDATE for it.
SOMEONE_ELSES = re.compile(
    r"\b(collaborat\w*|partner\w*|work(ing)? with|alongside|liaise|interface)\b"
    r"[^.]{0,60}\b(team|engineer|group|counterpart|colleague)", re.I)


DOMAIN_YEARS_COST = 16

# Degree bars. Real but soft, and often waived for a strong candidate.
#
# "Master" is matched as a whole word: `master\w*` read a brand name that
# starts with "master" as a graduate requirement and docked a posting 9. The
# senses that are whole words ("master data", "Scrum Master", the verb) are the
# screen's NOT_A_DEGREE, so the screen and the score cannot disagree about them.
GRAD = re.compile(r"\b(?:master(?:'?s)?\b|msc|m\.s\.|phd|ph\.d|doctora)\w*", re.I)
GRAD_COST = 9
# An equivalence route means there is no bar, so it is read across a window
# rather than the sentence: the route often sits past a list the sentence
# splitter cuts in two, as in "Master's degree in Mathematics, Statistics,
# Operations Research, Engineering, or equivalent".
GRAD_ESCAPE = re.compile(r"or equivalent|or comparable|or relevant experience|"
                         r"equivalent experience", re.I)
# Offered beside a bachelor's, it is a bar a BSc clears: "Bachelor's or
# Master's degree in" used to cost the full 9.
BACHELOR_OR = re.compile(r"\b(?:bachelor|b\.?sc|undergraduate)[^.;:]{0,60}?"
                         r"(?:\bor|/)\s*(?:an?\s+)?$", re.I)


def _sentence_spans(text: str):
    """(offset, sentence) for every sentence the screen reads, in order.

    `text_screen.sentences` returns stripped slices of `text` in order, so each
    one is found from where the last one ended.
    """
    pos = 0
    for s in sentences(text):
        at = text.find(s, pos)
        if at < 0:
            continue
        pos = at + len(s)
        yield at, s


def _domain_bar(body: str):
    """(demand, match) for the hardest-asked years bar in a domain not worked.

    Weighed like a missing skill, by its own sentence. It was a flat 16, so
    "5+ years in retail is a plus" cost what "is required" cost. The hardest
    ask decides, so a preference stated first cannot hide a requirement later.
    """
    hardest, found = DEMAND_NONE, None
    for _, s in _sentence_spans(body):
        for m in DOMAIN_YEARS.finditer(s):
            d = _demand(s)
            if found is None or d > hardest:
                hardest, found = d, m
    return hardest, found


def _degree_ask(body: str):
    """How hard the posting asks for a graduate degree, or None if it names none.

    The degree's own sentence decides, the way it does for a missing skill. It
    was a flat 9 with a 150-character window for the soft words, so "A master's
    degree is a plus, not a requirement" cost the full 9 ("a plus" was not one
    of them), and "Master's degree required. Excel experience
    preferred." cost nothing because the window read Excel's preference.
    """
    hardest = None
    for at, s in _sentence_spans(body):
        for m in GRAD.finditer(s):
            if NOT_A_DEGREE.match(s, m.start()):
                continue
            a = at + m.start()
            if (GRAD_ESCAPE.search(body[max(0, a - 150):a + len(m.group(0)) + 150])
                    or BACHELOR_OR.search(s[:m.start()])):
                d = DEMAND_NONE
            else:
                d = _demand(s)
            hardest = d if hardest is None else max(hardest, d)
    return hardest


def _title_tokens(title: str) -> str:
    """The title without parentheticals: "(CFO office)" is a location detail."""
    return re.sub(r"\([^)]*\)", " ", title)


def _family_tokens(ttoks: str) -> str:
    """The part of a title that names the JOB, not the domain it sits in.

    Employers write both orders. "Senior Analyst, Supply Chain" is a supply
    chain analyst. "Senior Product Analyst, Supply Chain Systems" is a product
    analyst who works on supply chain, which is ordinary product analytics and
    is in scope. The words are identical; the position is what separates them.

    So when the head of the title, before the first comma or dash, already
    names a specific in-family role, only the head is tested against the
    wrong-family list and the trailing domain is ignored. When the head names
    nothing more specific than a level, the whole title is tested.
    """
    head = re.split(r"[,\u2013\u2014]|\s+[-\u2212]\s+", ttoks, maxsplit=1)[0]
    return head if IN_FAMILY_HEAD.search(head) else ttoks


def fit(job: dict) -> dict:
    """0-100. The probability-shaped question, not the desirability one."""
    title = job.get("title") or ""
    ttoks = _title_tokens(title)
    body = (job.get("desc") or "")[:20000]
    hay = f"{title}\n{body}"
    pts = 50
    why: list[str] = []

    for pat, p, label in BANDS:
        if pat.search(ttoks):
            pts += p
            why.append(f"{p:+d} {label}")
            break
    if JUNIOR.search(ttoks):
        pts -= 25
        why.append(f"-25 junior, new-grad or student posting, below {_HIS} level")

    if BOARD.search(job.get("company") or ""):
        pts -= 20
        why.append("-20 listed by a job board, so the real employer is unknown")

    for pat, p, label in WRONG_FAMILY:
        if pat.search(ttoks):
            pts += p
            why.append(f"{p:+d} {label}")
            break
    else:
        family = _family_tokens(ttoks)
        for pat, p, label in WRONG_DOMAIN:
            if pat.search(family):
                pts += p
                why.append(f"{p:+d} {label}")
                break

    # The location gate's verdict travels with the row from prefilter; compute
    # it when the row arrived without one. FLAG is a real cost (a selectively
    # considered city, an unknown city, a US-anchored remote role), FAIL should not be here at all.
    lv = job.get("location_verdict")
    lreason = job.get("location_reason") or ""
    if lv not in ("PASS", "FLAG", "FAIL"):
        lv, lreason = location_verdict(job.get("location") or "", title)
    if lv == "FLAG":
        # A flat penalty treated different flags as the same thing. They are
        # not: a second city the candidate would consider, a home-region city
        # off the metro list (a commute question), and a remote role anchored in
        # another country that passes only if the employer happens to hire from
        # home, which a location string cannot show. One of those deserves
        # triple the cost of another. The costs are the profile's
        # (LOCATION_FLAG_COSTS), keyed on the reason its own LOCATION spec
        # writes.
        low_reason = lreason.lower()
        cost, note = _FLAG_DEFAULT
        for has, unless, c, n in _FLAG_COSTS:
            if has in low_reason and not (unless and unless in low_reason):
                cost, note = c, n
                break
        pts -= cost
        why.append(f"-{cost} location flagged: {note}")
    elif lv == "FAIL":
        pts -= 40
        why.append("-40 location fails the gate")

    if _REPORTS_RULE and REPORTS.search(body):
        pts += _REPORTS_RULE[1]
        why.append(f"{_REPORTS_RULE[1]:+d} {_REPORTS_RULE[2]}")

    hits = [(p, label) for pat, p, label in CORE if pat.search(hay)]
    got = raw_core = 0
    if hits:
        raw_core = sum(p for p, _ in hits)
        got = _core_points(raw_core)
        pts += got
        why.append(f"+{got} core match: {', '.join(l for _, l in hits[:5])}")
    else:
        pts -= 12
        why.append("-12 no core capability named anywhere in the posting")

    # Everything below this line is a penalty, and every one of them is scaled
    # by how much benefit of the doubt the posting has earned.
    give, give_why = slack(hay, title, raw_core, warm=bool(job.get("warm_route")))
    if give:
        why.append("gaps below softened %d%% (%s)"
                   % (round(give * 100), "; ".join(give_why)[:110]))
    keep = 1.0 - give

    for pat, p, label in MISSING:
        m = pat.search(hay)
        if not m:
            continue
        start = hay.rfind(".", 0, m.start()) + 1
        end = hay.find(".", m.end())
        sentence = hay[start:end if end > 0 else len(hay)]

        # The penalty is what the gap is worth, times how hard they asked,
        # times how much of it an honest neighbour already covers. A flat
        # penalty here treated "must have" and "a plus" and "we use it" as the
        # same fact, and cut roles worth applying for on a single word.
        demand = _demand(sentence)
        if not demand:
            continue
        scaled = round(p * demand * _bridge_multiplier(sentence) * keep)
        if not scaled:
            continue
        pts += scaled
        detail = label
        if demand <= DEMAND_SOFT:
            detail += ", but named as a preference rather than a bar"
        if scaled > p:
            detail += f" (softened from {p:+d}: adjacent experience covers part of it)"
        why.append(f"{scaled:+d} {detail}")

    demand, m = _domain_bar(body)
    cost = round(DOMAIN_YEARS_COST * demand)
    if cost:
        pts -= cost
        soft = demand <= DEMAND_SOFT
        why.append(f"-{cost} {m.group(1)}+ years {'wanted' if soft else 'demanded'} in a "
                   f"domain not worked ({m.group(2).lower()}), "
                   + ("a preference rather than a bar" if soft
                      else "the bar that actually screens people out"))

    # Years of experience, against 4 held. This is the requirement the
    # candidate is most often asked about and the one a posting is least
    # honest about, so it gets the most careful treatment in the file.
    #
    # Two separate corrections are happening here.
    #
    # FIRST, which bar. A posting is a wish list written by several people.
    # "3+ years of SQL" in the requirements and "10+ years in logistics"
    # three paragraphs down are not one bar of ten. Reading only the
    # highest made every posting that lists requirements per skill look like a
    # Principal role, and that is a common shape, not a rare one. `entry_years`
    # returns the lowest stated bar, which is what a recruiter screens on, and
    # the highest travels with it so the note can say the spread out loud. A
    # posting stating one bar is unaffected: the two numbers are the same.
    #
    # SECOND, the shape of the cost. This used to be a flat, explicitly
    # unrecoverable 40 at 9 years, with a comment saying no slack, no domain
    # match and no referral could rescue it. That is a qualification treated as
    # law, which is the one thing the rest of this file exists not to do, and it
    # deleted roles where everything except a number matched. The rule is
    # direct: a stretch on years, against an otherwise excellent match, is
    # still worth evaluating.
    #
    # So every band is now recoverable, and the rescue shrinks as the bar
    # climbs. A 9-year line on a posting in the candidate's industry and job shape,
    # with a live contact, costs about 11 instead of 40 and reaches the
    # shortlist carrying its own explanation. A 15-year line still sinks,
    # because at that point it is a different seniority of role and no framing
    # survives it, but it sinks by 36 rather than vanishing.
    bar, top_bar, _ = entry_years(body)

    def _years_cost(full: int, cap: float) -> int:
        return round(full * (1.0 - min(give, cap)))

    cost = 0
    if bar and bar >= 13:
        cost = _years_cost(40, 0.10)
    elif bar and bar >= 11:
        cost = _years_cost(30, 0.25)
    elif bar and bar >= 9:
        cost = _years_cost(20, 0.45)
    elif bar and bar >= 7:
        cost = round(5 * keep)
    if cost:
        pts -= cost
        note = f"-{cost} stated {bar}+ years against {YEARS_HELD} held"
        if top_bar and top_bar > bar:
            note += (f"; the posting also states {top_bar}+ elsewhere, and the "
                     f"lower bar is the one a recruiter screens on")
        why.append(note)
    elif bar and bar >= 5:
        why.append(f"stated {bar}+ years against {YEARS_HELD} held; no deduction, "
                   f"a bar this close is routinely waived")

    demand = _degree_ask(body) if _DEGREE_FLAGS else None
    if demand is not None:
        cost = round(GRAD_COST * demand)
        if cost:
            pts -= cost
            why.append(f"-{cost} graduate degree stated without an equivalence route"
                       + (", but named as a preference rather than a bar"
                          if demand <= DEMAND_SOFT else ""))
        else:
            why.append("+0 graduate degree mentioned, but with an equivalence route "
                       f"or not asked of {_HIM}")

    pts = max(0, min(100, pts))
    return {"fit": pts, "fit_why": why, "location_verdict": lv}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("infile")
    ap.add_argument("--out")
    ap.add_argument("--top", type=int, default=40)
    ap.add_argument("--explain", action="store_true")
    a = ap.parse_args()
    data = json.load(open(a.infile))
    jobs = list(data.values()) if isinstance(data, dict) else list(data)

    # A live conversation at the employer changes the odds more than any line in
    # the posting does. The floor exists because "below it the application is a
    # lottery ticket", and a referral is precisely what stops it being one: the
    # resume gets read by a person instead of a queue. So a warm route both adds
    # points and exempts the role from the floor's demotion.
    try:
        from throttle import warm_routes
        from company_key import key as _ckey
        warm = warm_routes()
    except Exception:
        warm, _ckey = {}, None

    out = []
    for j in jobs:
        f = fit(j)
        route = warm.get(_ckey(j.get("company")), []) if _ckey else []
        if route:
            f = dict(f)
            f["fit"] = min(100, f["fit"] + REFERRAL_BONUS)
            f["warm_route"] = route
            f["fit_why"] = list(f["fit_why"]) + [
                "+%d live contact at this employer (%s), so this is not a cold "
                "application" % (REFERRAL_BONUS, route[0]["name"])]
        opp = j.get("opportunity")
        # Product, not sum: neither score may compensate for the other.
        o = opp if opp is not None else 60
        # Opportunity is unbounded above, so it is rescaled to sit on the same
        # scale as fit. It used to be clamped to 100 here as well, and the clamp
        # threw away the whole top of the range: raw opportunity runs well past
        # 130, so everything from there up landed on the same number. Combined
        # with the old hard cap on core, that is why so many shortlist rows
        # shared a score with another row.
        #
        # So the rescaled value is kept unclamped for ranking and clamped only
        # for display. The product still cannot be carried by one factor: fit is
        # 0-100 and a spectacular employer with a poor match is still demoted by
        # the floor below.
        o_rank = o * 100 / 130.0
        o = max(0, min(100, round(o_rank)))
        pri = round(f["fit"] * o_rank / 100)
        # A floor, because the product alone still lets a spectacular employer
        # carry a poor match: a sales role at a big-tech employer could score a
        # low fit and still reach the shortlist on opportunity alone. Below the
        # floor the application is a lottery ticket, so it is ranked but never
        # promoted, whatever the logo is worth.
        if f["fit"] < FIT_FLOOR and not f.get("warm_route"):
            pri = min(pri, f["fit"] - 20)
        # Kept on the row so a tie on the presented integer still has something
        # real to break on, rather than falling back to scrape order.
        out.append({**j, **f, "priority": pri,
                    "priority_exact": round(f["fit"] * o_rank / 100, 3)})
    out.sort(key=lambda x: (-x["priority"], -x.get("priority_exact", 0),
                            -(x.get("fit") or 0), -(x.get("opportunity") or 0)))
    if a.out:
        json.dump(out, open(a.out, "w"), indent=1)
    for j in out[:a.top]:
        print(f"  pri{j['priority']:>4} fit{j['fit']:>4} opp{str(j.get('opportunity')):>4}  "
              f"{(j.get('company') or '')[:28]:28} {(j.get('title') or '')[:46]}")
        if a.explain:
            for w in j["fit_why"]:
                print(f"          {w}")
    print(f"\n{len(out)} ranked (0 model tokens)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
