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
import unicodedata

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
    r"\b(inc|llc|ltd|limited|pty|corp|corporation|company|group|holdings|plc|lp|"
    r"llp|" + "".join(re.escape(c) + r" inc|" for c in _COUNTRY) + r"s\.?a\.?|gmbh|ag)\b\.?", re.I)
# Legal forms that are only ever a suffix, so they come off the end alone:
# "uc" or "se" mid-name ("UC Davis") is part of the name. Ireland's DAC, CLG,
# UC and Teoranta, Canada's ULC, and the forms the punctuation pass splits
# ("S.p.A." arrives as "s p a"). "co" goes too, after "ltd" has gone:
# "Acme Co., Ltd." and "Acme & Co." are the employer the tracker calls Acme.
TRAILING_FORM = re.compile(
    r"\s+(dac|clg|uc|ulc|teoranta|teo|pvt|private|pte|sdn bhd|bhd|incorporated|"
    r"bv|b v|nv|n v|oy|ab|se|spa|s p a|sas|s a s|srl|s r l|s a|p l c|kk|co)$")
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
# Any letter in any script survives, accents folded first: "[^a-z0-9 ]" turned
# "Nestl\u00e9" into "nestl" and a Cyrillic or Chinese name into "", which is no
# employer at all, so nothing at it could ever match.
PUNCT = re.compile(r"[^\w ]+|_")
SPACE = re.compile(r"\s+")
# "Brindle & Hart" and "Brindle and Hart" are one employer. The ampersand was
# dropped as punctuation and the word was not, so the two keyed apart.
_AND = re.compile(r"\band\b")
# Letters NFKD does not decompose: "S\u00f8ren", "\u0141\u00f3d\u017a", "Stra\u00dfe".
_FOLD = str.maketrans({"\u00f8": "o", "\u00d8": "O", "\u0142": "l", "\u0141": "L", "\u00df": "ss",
                       "\u0111": "d", "\u0110": "D", "\u00e6": "ae", "\u00c6": "AE",
                       "\u0153": "oe", "\u0152": "OE", "\u00fe": "th", "\u00de": "Th",
                       "\u0131": "i"})


def fold(s: str) -> str:
    """The text with its accents dropped, every script's letters kept."""
    return "".join(c for c in unicodedata.normalize("NFKD", str(s or "").translate(_FOLD))
                   if not unicodedata.combining(c))


# Bilingual dual names ("Acme Investments | Investissements Acme") are one
# employer written twice; the first half is the name the tracker holds.
DUAL = re.compile(r"\s*[|/]\s*")


def _norm(s: str) -> str:
    s = PAREN.sub(" ", fold(s).strip().lower())
    halves = [h for h in DUAL.split(s) if h.strip()]
    if len(halves) > 1:
        s = halves[0]
    s = LEADING_THE.sub("", s)
    return SPACE.sub(" ", _AND.sub(" ", PUNCT.sub(" ", s))).strip()


# Alias keys go through the same normalization as the input, or a hyphenated
# entry ("acme-dominion bank") can never match its own normalized form. The
# values are keys, so they lose "and" the same way.
ALIASES = {_norm(k): SPACE.sub(" ", _AND.sub(" ", str(v))).strip() for k, v in ALIASES.items()}
# The parents and look-alikes are matched against a normalised name, so they are
# normalised too: "Procter & Gamble" written in the profile never matched the
# "procter gamble" it was compared against.
DIVISION = re.compile(
    r"^(" + "|".join(re.escape(_norm(p)) for p in _PARENTS) + r")\b.*" if _PARENTS else _NEVER, re.I)
SEPARATE = re.compile(
    r"^(" + "|".join(re.escape(_norm(p)) for p in _SEPARATE) + r")\b" if _SEPARATE else _NEVER, re.I)


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


def near_misses(left, right) -> list[tuple[str, str]]:
    """Employer names on the two sides that are probably one employer and do not join.

    "Fernhill" and "Fernhill Freight", "Larkspur" and "Larkspur Retail Bank": one
    key is the start of the other, word for word, so a contact and an
    application there never link and nothing says so. Reported, never merged:
    a bank's custody arm can be a different firm from the bank, which only the
    person knows.
    The fix is a line in profile/employers.py COMPANY_ALIASES.
    """
    lk = {key(n): n for n in left if key(n)}
    rk = {key(n): n for n in right if key(n)}
    out = []
    for a, an in sorted(lk.items()):
        for b, bn in sorted(rk.items()):
            if a == b:
                continue
            short, long_ = (a, b) if len(a) < len(b) else (b, a)
            if long_.split()[:len(short.split())] == short.split():
                out.append((an, bn))
    return out


def key(name: str | None) -> str:
    """A stable comparison key for an employer name."""
    if not name:
        return ""
    s = _norm(name)
    if s in ALIASES:
        return ALIASES[s]
    stripped = SPACE.sub(" ", SUFFIX.sub(" ", s)).strip()
    while TRAILING_FORM.search(stripped) and TRAILING_FORM.sub("", stripped).strip():
        stripped = TRAILING_FORM.sub("", stripped).strip()
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
