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
    r"services|pension plan|pension fund)$", re.I)
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


_INITIALISM = re.compile(r"\(\s*([A-Z][A-Z&.]{1,9})\s*\)")
_MINOR = {"of", "the", "and", "for", "de", "du", "la", "le", "et"}


def _own_initialism(name: str) -> str:
    """The short name a posting gives in brackets, when it is the name's own initials.

    "Northgate Pension Investment Board (NPIB)": the bracket is the one token that
    joins the posting to a tracker row or a listing under the short name, and every
    bracket was stripped as a listing detail like "(UK)", so the same role came in
    twice and an application under the short name did not hold the long one. Only
    an initialism that IS the name's initials counts; "(UK)" and "(Remote)" are not.
    """
    m = _INITIALISM.search(str(name or ""))
    if not m:
        return _own_short_word(name)
    short = re.sub(r"[^A-Za-z]", "", m.group(1)).lower()
    words = [w.lower() for w in re.findall(r"[A-Za-z]+", str(name)[:m.start()])]
    return short if len(short) >= 2 and _initials_of(short, words) else ""


_BRACKET_END = re.compile(r"^(.*\S)\s*\(\s*([^()]{2,40}?)\s*\)\s*$")


def _own_short_word(name: str) -> str:
    """The short name in a closing bracket when it is the name's own first words:
    "Brindle Hart Capital Partners (Brindle Hart)". Never a listing detail such as
    "(UK)" or "(Contract)", which is not how the name starts."""
    m = _BRACKET_END.match(str(name or ""))
    if not m:
        return ""
    short, long_ = _norm(m.group(2)), _norm(m.group(1))
    if not short or short in _MINOR or not long_.startswith(short + " "):
        return ""
    return short


def _initials_of(short: str, words: list[str]) -> bool:
    """Whether `short` is the words' initials, each small word ("of", "the") either
    counted or not: "Northgate of Fernhill Pension Plan" is NFPP and NOFPP alike. Only
    small words may be skipped, so "(UK)" or "(Remote)" never passes for a name."""
    if not short:
        return not any(w not in _MINOR for w in words)
    if not words:
        return False
    w, rest = words[0], words[1:]
    if w[0] == short[0] and _initials_of(short[1:], rest):
        return True
    return w in _MINOR and _initials_of(short, rest)


# Short name -> the long name's key, learned from every "Long Name (LN)" seen:
# the state files at import, and a round's postings before the throttle runs
# (`learn`). The long name stays the key, so nothing joined before is split.
_SHORT: dict[str, str] = {}


def learn(names) -> None:
    """Teach the join from every name that gives its own initialism in brackets."""
    for n in names or ():
        short = _own_initialism(n)
        if short:
            _SHORT.setdefault(short, _key(n))


def key(name: str | None) -> str:
    """A stable comparison key for an employer name."""
    if not name:
        return ""
    short = _own_initialism(name)
    k = _key(name)
    if short:
        _SHORT.setdefault(short, k)
        return k
    return _SHORT.get(k, k)


def _key(name: str) -> str:
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


def _learn_from_state() -> None:
    import csv
    for f in ("job_search_tracker.csv", "network_contacts.csv"):
        try:
            with open(person.state(f), newline="", encoding="utf-8") as fh:
                learn(r.get("company") for r in csv.DictReader(fh))
        except (OSError, ValueError, csv.Error):
            pass


_learn_from_state()


# ------------------------------------------------------------------ the name people write
#
# Not the join key: the employer as a letter, a note or a people search writes
# it, with its case, its "&" and the rest of its name kept, and the legal form
# and a bracketed qualifier off. The salutation and the outreach note
# (render_application.short_name) and the people search (discovery.search_name)
# each kept a list of their own, and each had fixes the other lacked: the search
# turned "Tamworth & Co." into "Tamworth &", the salutation kept "(UK)" and
# "AS", and "ULC" and "Pvt Ltd" came off only one of them. One list now; each
# caller keeps its own rule about Group, Company and Holdings.

# A compound form comes off whole: "Co., Ltd." and "Pvt Ltd" are one suffix,
# and stripping only the last word left "Acme Co" and "Acme Pvt".
_COMPOUND_FORM = re.compile(
    r",?\s+(?:(?:co\.?,?|pvt\.?|private|pte\.?)\s+(?:ltd|limited)|sdn\.?\s+bhd)\.?$", re.I)
# "Co" alone is never one: "Tamworth & Co." is the name. Ireland's DAC, CLG, UC
# and Teoranta, Canada's ULC, and the Nordic AS and A/S are.
_SINGLE_FORM = re.compile(
    r",?\s+(?:inc|incorporated|llc|l\.l\.c|ltd|limited|corp|corporation|plc|p\.l\.c|"
    r"llp|lp|l\.p|s\.a|n\.v|b\.v|bv|s\.p\.a|spa|s\.a\.s|sas|s\.r\.l|srl|"
    r"gmbh|pty|pte|ag|ab|as|a/s|oy|nv|sa|se|kk|dac|clg|uc|ulc|teoranta|teo)\.?$", re.I)
LEGAL_FORM = re.compile(_COMPOUND_FORM.pattern + "|" + _SINGLE_FORM.pattern, re.I)
# A cut that leaves the name ending on a joining word took part of the name:
# "Tamworth & Co., Ltd." is "Tamworth & Co.", never "Tamworth &".
JOINED_END = re.compile(r"(?:&|\b(?:and|of|the|for|de|du|des|y|et))$", re.I)


def drop_brackets(name: str | None) -> str:
    """The name without a bracketed qualifier: "Acme Bank (UK)" is Acme Bank."""
    s = " ".join(PAREN.sub(" ", str(name or "")).split())
    return s or str(name or "").strip()


def strip_legal_forms(name: str | None) -> str:
    """The name with every trailing legal form removed, one at a time:
    "Acme Pty Ltd" is Acme, not "Acme Pty"."""
    name = str(name or "").strip()
    while True:
        for rx in (_COMPOUND_FORM, _SINGLE_FORM):
            cut = rx.sub("", name).strip(" ,")
            if cut != name and cut and not JOINED_END.search(cut):
                name = cut
                break
        else:
            return name


def display_name(name: str | None) -> str:
    """The employer as people write it: brackets and legal forms off, the rest kept."""
    return strip_legal_forms(drop_brackets(name))


def row_key(row) -> str:
    """The employer identity of a contact row.

    Recomputed from the company name, with the stored `company_key` column used
    only when the name is blank. The column is a convenience for filtering in a
    spreadsheet, not the authority: `ALIASES` grows, so a key written last month
    can be stale while the name it came from still resolves correctly. One rule
    for the contact book's readers: the throttle skipped a row with only the
    column, so a referral in flight at that employer held nothing back, while
    tools/network/state.py read the same row as that employer.
    """
    k = key(row.get("company"))
    if k:
        return k
    return str(row.get("company_key") or "").strip().lower()
