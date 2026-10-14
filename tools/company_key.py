#!/usr/bin/env python3
"""Normalize an employer name so the company throttle actually fires.

The throttle suppresses employers with an open application. It compared raw
strings, so it let through an employer's full legal name while the tracker held
open applications under its initialism. A throttle that a rename defeats is
not a throttle.

Three problems, all handled here:
  legal suffixes   "Acme Inc." and "Acme" are one employer
  qualifiers       "Acme UK", "Acme Financial Group" and "Acme Insurance" are
                   the employer plus a country, a corporate form or a line of
                   business
  common aliases   many employers are posted under either the full legal name
                   or the initialism, interchangeably

The aliases, the parents whose divisions share their application, the
separately incorporated look-alikes and the market's country words are the
profile's (employers.py), because they depend on where the person searches.
This module is the mechanism.

Usage:
    from company_key import key
    key("Acme Bank of Commerce") == key("ABC")   # with a profile alias that says so
"""

from __future__ import annotations

import re

import os  # noqa: E402
import sys  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import person  # noqa: E402

_EMP = person.module("employers") if person.exists("employers.py") else None
ALIASES = dict(getattr(_EMP, "COMPANY_ALIASES", {}))
_COUNTRY = tuple(getattr(_EMP, "COUNTRY_WORDS", ()))

# Legal-form suffixes. Bare "co" is deliberately absent: an employer named
# "Co-<something>" would lose its first word, "co-operators" becoming
# "operators".
SUFFIX = re.compile(
    r"\b(inc|llc|ltd|limited|corp|corporation|company|group|holdings|plc|lp|"
    r"llp|" + "".join(re.escape(c) + r" inc|" for c in _COUNTRY) + r"s\.?a\.?|gmbh|ag)\b\.?", re.I)
# Trailing qualifiers that name where or what the employer is, not who:
# "Acme UK", "Acme Financial Group", "Acme Insurance", "Acme Concession
# Company Limited". Stripped only when a name remains.
TRAILING = re.compile(
    r"\s+(" + "".join(re.escape(c) + "|" for c in _COUNTRY)
    + r"north america|americas|usa|u\.?s\.?|uk|international|global|"
    r"financial group|financial corporation|financial services|financial|"
    r"insurance|concession|technologies|technology|software|solutions|"
    r"services)$", re.I)
# "Bank of England", "Universite de Lyon": a preposition before the
# qualifier means it is part of the name.
KEEP_TRAILING = re.compile(r"\b(of|de|du|des|for)\s+\w+$", re.I)
# A parenthetical qualifier is a listing detail, not a different employer:
# "Acme Bank (UK)" is Acme Bank. Strip it before anything else.
PAREN = re.compile(r"\([^)]*\)")
# Divisions post under their own banner but share the parent's application,
# and separately incorporated employers that happen to start with a parent's
# name must not be folded into it. Both lists are the profile's. An empty list
# matches nothing: "^()" would match every name.
_NEVER = r"(?!x)x"
_PARENTS = tuple(getattr(_EMP, "DIVISION_PARENTS", ()))
_SEPARATE = tuple(getattr(_EMP, "SEPARATE", ()))
DIVISION = re.compile(
    r"^(" + "|".join(re.escape(p) for p in _PARENTS) + r")\b.*" if _PARENTS else _NEVER, re.I)
SEPARATE = re.compile(
    r"^(" + "|".join(re.escape(p) for p in _SEPARATE) + r")\b" if _SEPARATE else _NEVER, re.I)
LEADING_THE = re.compile(r"^the\s+")
PUNCT = re.compile(r"[^a-z0-9 ]+")
SPACE = re.compile(r"\s+")


# Bilingual dual names ("Acme Investments | Investissements Acme") are one
# employer written twice; the first half is the name the tracker holds.
DUAL = re.compile(r"\s*[|/]\s*")


def _norm(s: str) -> str:
    s = PAREN.sub(" ", s.strip().lower())
    halves = [h for h in DUAL.split(s) if h.strip()]
    if len(halves) > 1:
        s = halves[0]
    s = LEADING_THE.sub("", s)
    return SPACE.sub(" ", PUNCT.sub(" ", s)).strip()


# Alias keys go through the same normalization as the input, or a hyphenated
# entry ("acme-dominion bank") can never match its own normalized form.
ALIASES = {_norm(k): v for k, v in ALIASES.items()}


def _strip_trailing(s: str) -> str:
    """Peel trailing qualifiers one at a time while a name remains."""
    while True:
        m = TRAILING.search(s)
        if not m or KEEP_TRAILING.search(s):
            return s
        head = s[:m.start()].strip()
        if not head:
            return s
        s = head


def key(name: str | None) -> str:
    """A stable comparison key for an employer name."""
    if not name:
        return ""
    s = _norm(name)
    if s in ALIASES:
        return ALIASES[s]
    stripped = SPACE.sub(" ", SUFFIX.sub(" ", s)).strip()
    if stripped in ALIASES:
        return ALIASES[stripped]
    m = SEPARATE.match(stripped)
    if m:
        return m.group(1).lower()
    # A division ("<Parent> Wealth Management", "<Parent> Securities") shares
    # its parent's open application, so it must collapse to the parent.
    m = DIVISION.match(stripped)
    if m:
        head = m.group(1)
        return ALIASES.get(head, head)
    trimmed = _strip_trailing(stripped)
    if trimmed in ALIASES:
        return ALIASES[trimmed]
    return trimmed or stripped or s


if __name__ == "__main__":
    import sys
    for n in sys.argv[1:]:
        print(f"{n!r} -> {key(n)!r}")
