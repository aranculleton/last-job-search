#!/usr/bin/env python3
"""Is this employer a technology company, and is it one worth working for?

`opportunity.tier()` already answers how good an employer is. It does not
answer what the employer *is*: a tier can hold a software company's peers
beside banks, insurers and telcos, all correctly scored and none of them tech. So
"only good tech" had no definition in the repo and was answered by eye, which
is how a shortlist ends up with a staffing shell and a retailer on it.

Two questions, kept apart:

  SECTOR   tech, tech-adjacent, or neither. A product company that ships
           software is tech. A fintech, marketplace or health platform whose
           product IS software, built by its own engineers, is tech-adjacent:
           the work and the stack are the same, the industry is not. A bank, an
           insurer, a telco, a retailer or a professional-services firm is
           neither, however good an employer it is and however much technology
           it buys.

  QUALITY  `opportunity.tier()`, unchanged. A staffing agency scores -30 there
           and is excluded here outright, because an undisclosed employer
           cannot be a good technology company: nobody knows who it is.

An unknown name is not guessed at from the name. It is read out of the posting:
a company describing its own product, platform, users or engineering team is
tech; one describing staff augmentation, placements or a client's site is not.
Where the text settles nothing, the verdict is `unknown` and it says so, which
is a different answer from `other` and is meant to be read differently.
"""
from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from opportunity import AGENCY, _names_in  # noqa: E402
import person  # noqa: E402

# The catalogues are the profile's (employers.py), because which employers a
# person meets depends on where they search:
#   EXTRA_AGENCY        staffing firms whose name carries no "staffing" or
#                       "recruit", so the shared AGENCY pattern misses them
#   TECH_COMPANIES      product companies that ship software
#   ADJACENT_COMPANIES  software products sold into another industry
#   NOT_TECH            name -> what it is (a bank, an insurer, a retailer...)
_E = person.module("employers") if person.exists("employers.py") else None
_EXTRA_AGENCY = getattr(_E, "EXTRA_AGENCY", None) or re.compile(r"(?!x)x")
TECH_COMPANIES = set(getattr(_E, "TECH_COMPANIES", ()))
ADJACENT_COMPANIES = set(getattr(_E, "ADJACENT_COMPANIES", ()))
NOT_TECH = dict(getattr(_E, "NOT_TECH", {}))


# Read out of the posting when the name is unknown. A company describing its own
# product is tech; one describing a placement at a client is not.
# Only phrases a staffing posting or a non-tech employer does not use. The first
# cut accepted "our customers", "our users", "the platform" and "our product",
# which are in nearly every posting ever written, and called an HVAC company and
# a staffing firm technology companies on the strength of them.
_PRODUCT = re.compile(
    r"\b(saas|b2b software|software company|developer platform|"
    r"series [a-e] (?:funded|company|startup)|series [a-e]\b|venture[- ]backed|"
    r"yc[- ]backed|y combinator|our engineering (?:team|org)|"
    r"we (?:build|ship) (?:software|products?|tools)|open[- ]source)\b", re.I)
_PLACEMENT = re.compile(
    r"\b(our client|the client|client site|staff augmentation|placement|"
    r"contract (?:position|role) (?:with|for) (?:our|a) client|"
    r"we are (?:recruiting|hiring) on behalf|end client)\b", re.I)

# The verdicts. Deliberately not named TECH: an earlier cut of this file used
# that name for both the constant and the set above it, and the assignment
# silently emptied the set, so two of the best-known software companies came
# back "unknown".
V_TECH, V_ADJACENT, V_OTHER, V_UNKNOWN = "tech", "tech_adjacent", "other", "unknown"


def _norm(x: str) -> str:
    """One normalisation for names AND list keys.

    They were normalised differently: the name lost its hyphens and the key kept
    them, so a hyphenated name ("Acme-Two Interactive") never matched its key
    ("acme-two") and came back unknown.
    """
    x = re.sub(r"[^a-z0-9&' ]+", " ", str(x or "").lower())
    return re.sub(r"\s+", " ", x).strip()


def _in(c: str, names) -> str | None:
    return _names_in(c, {_norm(n) for n in names})


def tech_name(company: str | None) -> str | None:
    """The entry on the person's tech list (employers.py TECH_COMPANIES) this employer is,
    as normalised, or None. The one reading of that list: tools/bar.py matched it without
    normalising either side, so a hyphenated or capitalised entry never matched there."""
    c = " %s " % _norm(str(company or "").split("|")[0])
    return _in(c, TECH_COMPANIES) if c.strip() else None


def verdict(company: str | None, posting: str = "") -> tuple[str, str]:
    """(sector, reason). See the module docstring for what each verdict means."""
    first = str(company or "").split("|")[0]
    c = " %s " % _norm(first)
    if not c.strip():
        return V_UNKNOWN, "no company name on the posting"
    if AGENCY.search(c) or _EXTRA_AGENCY.search(c):
        return V_OTHER, "staffing agency or body shop: the employer is undisclosed"
    n = tech_name(first)
    if n:
        return V_TECH, "technology company (%s)" % n
    n = _in(c, ADJACENT_COMPANIES)
    if n:
        return V_ADJACENT, "software product sold into another industry (%s)" % n
    for name, what in NOT_TECH.items():
        if _in(c, {name}):
            return V_OTHER, "%s, not a technology company" % what
    text = posting or ""
    if _PLACEMENT.search(text) and not _PRODUCT.search(text):
        return V_OTHER, "the posting describes a placement at a client, not a product"
    if _PRODUCT.search(text):
        return V_TECH, "unlisted, but the posting describes its own product and engineers"
    return V_UNKNOWN, "not a name on file and the posting settles nothing"


def kind(company: str | None) -> str:
    """What the person's own catalogue (employers.py) says this employer is, in its words:
    NOT_TECH's ("professional services", "bank"), "technology company" or "software product"
    for the two tech lists, and "" for a name it does not hold. Nothing is guessed."""
    c = " %s " % _norm(str(company or "").split("|")[0])
    if not c.strip():
        return ""
    if tech_name(company):
        return "technology company"
    if _in(c, ADJACENT_COMPANIES):
        return "software product"
    return next((what for name, what in NOT_TECH.items() if _in(c, {name})), "")


def keep(company: str | None, posting: str = "", include_unknown: bool = False) -> bool:
    """Does this row survive a tech-and-tech-adjacent filter?"""
    v, _ = verdict(company, posting)
    return v in (V_TECH, V_ADJACENT) or (include_unknown and v == V_UNKNOWN)


if __name__ == "__main__":  # pragma: no cover
    if not sys.argv[1:] or sys.argv[1] in ("-h", "--help"):
        print('usage: python3 tools/sector.py "<employer name>" [...]: the sector on file and why')
        sys.exit(0 if sys.argv[1:] else 2)
    for name in sys.argv[1:]:
        print("%-28s %-14s %s" % ((name,) + verdict(name)))
