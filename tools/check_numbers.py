#!/usr/bin/env python3
"""Every number in a generated document must trace back to the profile.

`check_claims.py` is the companion to this and says honestly what it is: a list
of string patterns harvested from errors the grounding reviewer already caught.
It stops the same mistake twice. It cannot stop a new one, because a metric
nobody has invented yet is not in the list, and a fabricated figure that has
never appeared before passes it silently.

SECURITY.md ranks a fabricated claim reaching an employer as the worst thing
this system can do, worse than any leak. This closes the general case for the
one kind of claim that can be checked mechanically: the numeric kind.

The rule is conservation. A number in the output must exist in the source of
truth, which is the profile: the files its person.json names under
`grounding.sources` (by default its candidate profile, its CLAUDE.md and its
bullets.py). There is no judgement in it, and that is the point: "60M+
records" is checkable, "a strong track record" is not. App documentation is
never a source: a number in an app doc would then count as grounded for
everyone and silently whitelist a fabricated figure.

Magnitude and unit are normalised so "5k", "5,000" and "5000" are one claim,
and "$300M+" and "300 million" are another. A resume that rounds 2.5M to "2.5
million" therefore still matches, and one that quietly promotes 60M to 75M
does not.

A number written as a word is a number too (`figures`): "twelve years", "forty
spreadsheets", "more than thirty-five", "a dozen", "two and a half years", a share
("halved" and "by a third" are 50% and 33%), a multiple ("tripled" is 3x) and an ordinal
that counts ("the fifth consecutive year"). Read the same way in the document and in the
profile, so "eleven spreadsheets" is grounded by "eleven spreadsheets" and "forty" is not.

A count with no unit word is a count OF something, and the noun it counts has to
agree. Matched by its size alone, "12 source systems" in the profile grounded "12
clients" in an interview answer, and "40k+ accounts" grounded "40k customers".
Where both the document and the profile name what the number counts, they must
share a word or a known synonym (`SYNONYMS`): "12 systems" and "a 12-store pilot"
still match "12 source systems" and "12 stores". A number with nothing after it on
either side ("a team of 12") is matched by its size, as before.

WHAT IS DELIBERATELY NOT A FINDING:

  - dates and years, which are structure rather than claims
  - LaTeX residue: lengths in em, pt, ex, in, cm, and \\baselineskip factors
  - small ordinals under `SMALL`, because "3 clients" style numbers are as
    likely to be prose as a claim and the noise would drown the signal
  - a company fact in a cover letter, which is verified separately against an
    independently located source and is not the candidate's own claim
  - in an interview or call prep (a .md file), an answer still marked as a draft the
    person asked for (`without_drafts`): it is theirs to confirm, and says so

THE LETTER, with `--drafts`. Only the resume was ever checked, and the letter's
opening, bullets and close are free model text that an interviewer reads as
closely. So the drafts mode checks a draft's `summary`, `p1`, `lead`, `p4` and
`cl_bullets` against the profile, and allows in the opening, the lead line and the
close what the letter may honestly repeat about the employer: the figures in `p2` (the
one verified company fact, which is not itself checked here; the claim map in
tools/draft_audit.py checks it sentence by sentence) and the figures in the posting. The
summary and the letter bullets state the candidate's own work, so only the profile's
figures ground them.

Measured when written: across 53 committed resumes, prose only, exactly one
novel number, and it was LaTeX residue. The documents are already grounded, so
this is a regression guard rather than a repair, the same shape as voice_check.

Usage:
    python3 tools/check_numbers.py cv/<Prefix>_Resume_ACME.tex
    python3 tools/check_numbers.py cv/*.tex
    python3 tools/check_numbers.py --drafts rounds/r1/drafts.json [cv/*.tex]
Exit 0 clean, 1 an ungrounded number, 2 a bad invocation.
"""

from __future__ import annotations

import argparse
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from voice_check import plain  # noqa: E402
import person  # noqa: E402

# Paths in person.json are relative to the profile directory.
SOURCES = tuple(
    os.path.normpath(person.path(p)) for p in
    person.get("grounding.sources", ["01-candidate-profile.md", "CLAUDE.md", "bullets.py"]))

# Below this, a bare number is more likely to be prose than a claim.
SMALL = 10

# LaTeX lengths that survive the strip. A number followed by one of these is
# typography, not a statement about the candidate.
_UNIT_NOISE = r"(?:em|ex|pt|pc|bp|dd|cc|sp|in|cm|mm|baselineskip|textwidth|linewidth)"
_RESIDUE = re.compile(r"\d[\d.]*\s*" + _UNIT_NOISE + r"\b", re.I)

# Every unit word ends on a word boundary. Without it "2024 Weekend" read as
# "2024 week", which is no longer a year, so a resume whose dates run into a
# capitalised word failed verify_batch.sh; "12 monthly reviews", "3 hourly
# checks" and "2023 Daytime cover" broke the same way.
_UNIT = (r"(%|(?:per\s?cent|percent|k|m|bn|b|million|billion|thousand|hours?|hrs?|days?|weeks?|"
         r"months?|years?|x)\b)?")
_NUM = re.compile(
    r"(?<![\w.])"
    r"(\d[\d,]*(?:\.\d+)?)"
    # "8+ years" and "9 per cent" carried no unit: the "+" sat between the number
    # and its unit, and "per cent" was not a unit, so a bare number under 10 was
    # thrown away and an invented "8+ years of experience" passed. A hyphen joins
    # them too: "a 9-hour job" is nine hours, and was read as a bare 9 and dropped.
    r"(?:-(?=[a-z%])|\s*\+?\s*)"
    + _UNIT,
    re.I)

# A number written as a word is a number. Every check here read digits only, so "twelve
# years", "forty spreadsheets" and "more than thirty-five" went past the resume check and
# the claim map alike, and drafters do spell numbers ("eleven spreadsheets"). Read on both
# sides: in the document, and in the profile and the evidence that ground it.
_ONES = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
         "eight": 8, "nine": 9}
_TEENS = {"ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
          "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
         "eighty": 80, "ninety": 90}
_SCALES = {"hundred": 100, "thousand": 1000, "million": 10 ** 6, "billion": 10 ** 9}


def _alt(words) -> str:
    return "|".join(sorted(words, key=len, reverse=True))


# A run starts on a count word ("twelve", "thirty-five") or on "a"/"an" before a scale ("a
# dozen", "a hundred"); a scale word alone never starts one, so the "million" of "1.2
# million" is the digits' unit and not a second number.
_NUMBER_WORD = re.compile(
    r"(?<![\w-])(?:(?:a|an)\s+(?=(?:hundred|thousand|million|billion|dozen)\b)"
    r"(?:" + _alt(list(_SCALES) + ["dozen"]) + r")|(?:" + _alt(list(_ONES) + list(_TEENS)
                                                                + list(_TENS)) + r"))\b"
    r"(?:(?:\s+and\s+|[\s-]+)(?:" + _alt(list(_ONES) + list(_TEENS) + list(_TENS)
                                       + list(_SCALES) + ["dozen"]) + r")\b)*", re.I)
# Counted multiples and fractions. A fraction is a share, so it is read as the percentage
# it is ("halved" and "cut by 50%" are one claim), rounded to the whole number a document
# would print. Only in the shapes that state a share: "a third of", "by a third", "half
# of", "halved"; never "the first half of 2026", "a third party" or "the third quarter".
_MULTIPLE = re.compile(r"(?<![\w-])(doubl(?:ed|ing|es)|tripl(?:ed|ing|es)|quadrupl(?:ed|ing|es)|"
                       r"(two|three|four|five|six|seven|eight|nine|ten)[- ]?fold)\b", re.I)
_FRACTION = {"half": 50, "third": 33, "quarter": 25, "fifth": 20, "tenth": 10}
_FRACTION_SHARE = re.compile(
    r"(?<![\w-])(?:(?P<by>by)\s+)?(?P<n>a|an|one|two|three)[\s-]+(?P<f>half|thirds?|quarters?|"
    r"fifths?|tenths?)\b(?![\s-]+part(?:y|ies)\b)(?P<of>\s+of\b)?", re.I)
# "Half the morning" and "half of the week" are a stretch of time, never a share.
_HALF = re.compile(
    r"(?<![\w-])(?:halv(?:ed|ing|es)\b|(?:by|in)\s+half\b|"
    r"(?<!first )(?<!second )(?<!1st )(?<!2nd )(?<!latter )(?<!former )(?<!back )(?<!front )"
    r"(?<!other )(?<!the )half\s+(?:of|the|its|their|our|all|every)\b"
    r"(?!\s+(?:(?:the|a|an|my|our|their|its|that|this)\s+)?(?:morning|afternoon|evening|day|night|"
    r"week|weekend|month|year|shift)s?\b))", re.I)
_HALF_UNIT = re.compile(r"(?<![\w-])(?:(?P<n>" + "|".join(list(_ONES) + list(_TEENS))
                        + r"|\d+)\s+and\s+)?(?:a\s+)?half\s+(?:an?\s+)?(?=(?:hours?|days?|"
                          r"weeks?|months?|years?|million|billion|thousand|dozen)\b)", re.I)
# "the fifth consecutive year", "for the third year running": an ordinal that counts.
_ORDINAL = {"second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7,
            "eighth": 8, "ninth": 9, "tenth": 10, "eleventh": 11, "twelfth": 12,
            "fifteenth": 15, "twentieth": 20}
_ORDINAL_COUNT = re.compile(
    r"(?<![\w-])(?P<o>" + "|".join(_ORDINAL) + r")\s+(?:(?:consecutive|straight|successive)\s+"
    r"(?P<u1>hours?|days?|weeks?|months?|years?)\b|(?P<u2>hours?|days?|weeks?|months?|years?)"
    r"\s+(?:running|in\s+a\s+row)\b)", re.I)


# "A decade" and "two decades" are ten and twenty years; "by a factor of three" is 3x.
# Both went unread, so "over a decade of experience" passed a seven-year profile.
_COUNT = r"(?:\d+(?:\.\d+)?|" + _alt(list(_ONES) + list(_TEENS) + list(_TENS)) + r")"
_DECADE = re.compile(r"(?<![\w-])(?:(?P<n>a|an|" + _COUNT + r")[\s-]+)(?:decades?)\b", re.I)
_FACTOR = re.compile(r"(?<![\w-])(?:by\s+)?a\s+factor\s+of\s+(?P<n>" + _COUNT + r")\b", re.I)
# How long a call would take ("a thirty-minute conversation", "happy to talk for fifteen
# minutes") is an offer, not a claim about the candidate's work; minutes in any other
# sentence ("cut the run from 45 minutes to 3") still are.
_MINUTES = re.compile(r"(?<![\w-])(?:" + _COUNT + r"|a\s+few|a\s+couple\s+of)(?:[\s-]+and[\s-]+a[\s-]+half)?"
                      r"(?:[\s-]+|\s*-\s*)(?:minutes?|mins?)\b", re.I)
_MEETING = re.compile(r"\b(?:call|calls|conversation|chat|meeting|talk|speak|discuss\w*|"
                      r"catch[- ]up|coffee|introduction|intro|of your time)\b", re.I)
# A day of the month beside its month ("on 21 October", "October 21st") is a date, and
# dates are structure. Month names are read in capitals: "may" is a verb first.
_MONTHS = (r"(?-i:January|February|March|April|May|June|July|August|September|October|"
           r"November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept|Sep|Oct|Nov|Dec)\.?")
_DATE = re.compile(r"(?<![\w-])\d{1,2}(?:st|nd|rd|th)?\s+(?:of\s+)?" + _MONTHS + r"(?![\w-])|"
                   # "October 21st", "October 21, 2026", "by October 21.", never "In May 12
                   # analysts joined", where 12 counts analysts.
                   r"(?<![\w-])" + _MONTHS + r"\s+\d{1,2}(?:(?:st|nd|rd|th)\b|"
                   r"(?=\s*,\s*\d{4}\b)|(?=\s*(?:[.;:!?)]|,\s|$)))", re.I)


def _count_value(tok: str) -> float | None:
    t = tok.lower().strip()
    if t in ("a", "an"):
        return 1.0
    try:
        return float(t)
    except ValueError:
        return _word_value(t)


def _sentence_around(body: str, a: int, b: int) -> str:
    start = max(body.rfind(c, 0, a) for c in ".!?\n") + 1
    ends = [i for i in (body.find(c, b) for c in ".!?\n") if i >= 0]
    return body[start:min(ends) if ends else len(body)]


def _word_value(words: str) -> float | None:
    """The value of a run of number words ("two hundred and fifty", "thirty-five", "a
    dozen"), or None when the run is not one number ("five ten" is two)."""
    total, current, last = 0, 0, ""
    for tok in re.split(r"[\s-]+", words.lower().strip()):
        if tok in ("", "and"):
            continue
        if tok in ("a", "an"):
            current, last = 1, "ones"
            continue
        if tok in _ONES:
            if last in ("ones", "teens"):
                return None
            current += _ONES[tok]
            last = "ones"
        elif tok in _TEENS:
            if last in ("ones", "teens", "tens"):
                return None
            current += _TEENS[tok]
            last = "teens"
        elif tok in _TENS:
            if last in ("ones", "teens", "tens"):
                return None
            current += _TENS[tok]
            last = "tens"
        elif tok == "dozen":
            current = (current or 1) * 12
            last = "ones"
        elif tok == "hundred":
            current = (current or 1) * 100
            last = "hundred"
        elif tok in _SCALES:
            total += (current or 1) * _SCALES[tok]
            current, last = 0, "scale"
        else:
            return None
    value = total + current
    return float(value) if value else None


def figures(body: str):
    """(start, end, value, unit, shown) for every number in `body`: digits, number words,
    multiples ("tripled" is 3x) and shares ("a third of" is 33%). `value` is the digits as
    a string, the unit as written, `end` where what it counts begins, `shown` the words."""
    out, taken = [], []

    def free(a, b):
        return not any(a < y and x < b for x, y in taken)

    def add(a, b, value, unit, end=None):
        if free(a, b):
            taken.append((a, b))
            out.append((a, b if end is None else end, value, unit, body[a:b]))

    for m in _DATE.finditer(body):
        taken.append(m.span())                  # a date: read by nothing below
    for m in _MINUTES.finditer(body):
        if _MEETING.search(_sentence_around(body, m.start(), m.end())):
            taken.append(m.span())              # how long a call would take
    for m in _DECADE.finditer(body):
        n = _count_value(m.group("n"))
        if n:
            add(m.start(), m.end(), "%g" % (n * 10), "years")
    for m in _FACTOR.finditer(body):
        n = _count_value(m.group("n"))
        if n:
            add(m.start(), m.end(), "%g" % n, "x")
    for m in _ORDINAL_COUNT.finditer(body):
        add(m.start(), m.end(), str(_ORDINAL[m.group("o").lower()]), m.group("u1") or m.group("u2"))
    for m in _HALF_UNIT.finditer(body):
        n = m.group("n")
        whole = (_ONES.get(n.lower()) or _TEENS.get(n.lower()) if n and not n.isdigit()
                 else int(n) if n else 0)
        unit = _UNIT_AFTER.match(body, m.end())
        if unit:
            if unit.group(1).lower() == "dozen":
                add(m.start(), unit.end(), "%g" % (whole * 12 + 6), "")
            else:
                add(m.start(), unit.end(), "%g" % (whole + 0.5), unit.group(1))
    for m in _HALF.finditer(body):
        add(m.start(), m.end(), "50", "%")
    for m in _FRACTION_SHARE.finditer(body):
        if not (m.group("by") or m.group("of")):
            continue
        f = m.group("f").lower().rstrip("s")
        if m.group("n").lower() in ("a", "an", "one"):
            share = _FRACTION[f]
        else:
            share = round({"two": 2, "three": 3}[m.group("n").lower()] * 100 /
                          {"half": 2, "third": 3, "quarter": 4, "fifth": 5, "tenth": 10}[f])
        add(m.start(), m.end(), str(share), "%")
    for m in _MULTIPLE.finditer(body):
        word = m.group(1).lower()
        n = 2 if word.startswith("doubl") else 3 if word.startswith("tripl") else \
            4 if word.startswith("quadrupl") else (_ONES.get(m.group(2).lower())
                                                   or _TEENS.get(m.group(2).lower()))
        add(m.start(), m.end(), str(n), "x")
    for m in _NUM.finditer(body):
        add(m.start(), m.end(), m.group(1), m.group(2))
    for m in _NUMBER_WORD.finditer(body):
        value = _word_value(m.group(0))
        if value is None:
            continue
        unit = _NUM_UNIT.match(body, m.end())
        u = unit.group(1) if unit and unit.group(1) else None
        # "one" alone is as often a pronoun as a count ("the one thing"): with no unit it
        # is under SMALL and dropped by claim_key anyway.
        add(m.start(), unit.end() if u else m.end(), "%g" % value, u)
    out.sort()
    return out


_NUM_UNIT = re.compile(r"(?:-(?=[a-z%])|\s*\+?\s*)" + _UNIT, re.I)
_UNIT_AFTER = re.compile(r"(hours?|days?|weeks?|months?|years?|million|billion|thousand|dozen)\b",
                         re.I)

_MAGNITUDE = {"k": 1e3, "thousand": 1e3, "m": 1e6, "million": 1e6,
              "b": 1e9, "bn": 1e9, "billion": 1e9}
_UNIT_ALIAS = {"hrs": "hour", "hr": "hour", "percent": "%", "per cent": "%"}
# A four-digit number in this range is a year, and a year is structure.
_YEAR = re.compile(r"^(19|20)\d{2}$")


def claim_key(value: str, unit: str) -> tuple[float, str] | None:
    """(magnitude, unit) for one number, or None when it is not a claim."""
    unit = re.sub(r"\s+", " ", (unit or "").lower()).rstrip("s")
    unit = _UNIT_ALIAS.get(unit, unit)
    raw = value.replace(",", "")
    if _YEAR.match(raw) and not unit:
        return None
    try:
        n = float(raw)
    except ValueError:
        return None
    if unit in _MAGNITUDE:
        return (n * _MAGNITUDE[unit], "")
    if not unit and n < SMALL:
        return None
    return (n, unit)


def claims(text: str) -> set[tuple[float, str]]:
    """Every numeric claim in `text`, normalised."""
    body = _RESIDUE.sub(" ", plain(text or ""))
    out = set()
    for _a, _b, value, unit, _shown in figures(body):
        key = claim_key(value, unit)
        if key is not None:
            out.add(key)
    return out


# What a count counts. In the document, the noun right after the number, up to the first word
# that is not part of it ("12 source systems in Azure" counts source systems); a hyphen right
# after the number joins its noun to it ("a 12-store pilot" counts stores). In the profile,
# every content word in the next WINDOW words of the same clause, because the noun a profile
# counts can sit behind its modifiers ("1.5M+ sensitive public-sector debt, healthcare and
# financial records"): wide on the side that grounds, narrow on the side that claims.
WINDOW = 8
_NOUN_AFTER = re.compile(r"-?\s*([A-Za-z][A-Za-z'/-]*(?:\s+[A-Za-z][A-Za-z'/-]*){0,2})")
_CLAUSE = re.compile(r"[^.;:()!?\d\n]*")
_ENDS_NOUN = frozenset("""a an the and or of to in on for with by at from into across over per
than as is are was were be been being each every which that who whose while via through
within under after before between during plus more less fewer times this these those it its
their his her our my your up down out off about against around also only just nearly
approximately roughly almost some""".split())
_PLAIN_ADJ = frozenset("""new other different key major main large small big separate distinct
unique total active regional global internal external senior junior weekly daily monthly
quarterly annual yearly live core several high low top full""".split())
# Words that count the same thing. Kept to true synonyms: "30 people" and "30+ operations
# managers" are not one claim, and neither are accounts and customers.
SYNONYMS = (
    frozenset({"people", "person", "staff", "employee", "headcount", "colleague", "fte"}),
    frozenset({"client", "customer"}),
    frozenset({"store", "shop", "branch", "outlet"}),
    frozenset({"sku", "product", "item"}),
    frozenset({"record", "row", "transaction", "entry"}),
    frozenset({"centre", "center", "site", "depot", "warehouse", "dc", "facility"}),
    frozenset({"spreadsheet", "workbook", "sheet"}),
    frozenset({"supplier", "vendor"}),
    frozenset({"test", "experiment", "trial", "pilot"}),
    frozenset({"dashboard", "report"}),
    frozenset({"system", "platform"}),
    frozenset({"user", "listener", "viewer", "subscriber", "member"}),
    frozenset({"organisation", "organization", "company", "business", "firm"}),
)
_SYNONYM = {w: min(group) for group in SYNONYMS for w in group}


def _stem(word: str) -> str:
    w = re.sub(r"^[^a-z0-9]+|[^a-z0-9']+$", "", word.lower().replace("\u2019", "'"))
    w = w[:-2] if w.endswith("'s") else w.rstrip("'")
    if len(w) > 4 and w.endswith("ies"):
        w = w[:-3] + "y"
    elif w.endswith(("sses", "ches", "shes", "xes")):
        w = w[:-2]
    elif len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        w = w[:-1]
    return _SYNONYM.get(w, w)


def counted(text: str, at: int, wide: bool = False) -> frozenset:
    """What the number ending at `at` counts, as its stemmed words with synonyms folded
    together; empty when no noun follows it. `wide` reads the profile's way (WINDOW)."""
    if wide:
        words = re.split(r"[\s,/-]+", " ".join(_CLAUSE.match(text, at).group(0).split()[:WINDOW]))
        return frozenset(_stem(w) for w in words
                         if w and w.lower() not in _ENDS_NOUN | _PLAIN_ADJ and w[0].isalpha())
    return frozenset(_stem(w) for w in _noun_words(text, at)
                     if w.lower() not in _PLAIN_ADJ)


def _noun_words(text: str, at: int) -> list:
    """The words of the noun right after the number ending at `at`, as written."""
    m = _NOUN_AFTER.match(text, at)
    out = []
    for w in (re.split(r"(?<=\S)[\s/]+|-", m.group(1).strip()) if m else ()):
        if not w:
            continue
        if w.lower() in _ENDS_NOUN:
            break
        out.append(w)
    return out


def _after(text: str, at: int) -> str:
    """The words after a number as written, for saying what it counts."""
    return " ".join(_CLAUSE.match(text, at).group(0).split()[:WINDOW]).strip(" ,-\"'")


class Grounded(set):
    """The grounded claims, with `nouns`: {claim: [the noun each occurrence counts]}.
    A set like any other to a caller that only asks whether a claim is in it."""

    def __init__(self, keys=(), nouns=None, said=None):
        super().__init__(keys)
        self.nouns = {k: list(v) for k, v in (nouns or {}).items()}
        self.said = {k: list(v) for k, v in (said or {}).items()}

    def add_text(self, text: str, nouns: bool = True) -> None:
        """Every claim in `text`; with nouns=False, each matched by its size alone (the
        employer's own figures a letter may repeat, whatever it says they count)."""
        body = _RESIDUE.sub(" ", plain(text or ""))
        for _a, end, value, unit, _shown in figures(body):
            key = claim_key(value, unit)
            if key is None:
                continue
            self.add(key)
            self.nouns.setdefault(key, []).append(counted(body, end, wide=True) if nouns
                                                  else frozenset())
            self.said.setdefault(key, []).append(_after(body, end))

    def agrees(self, key, noun: frozenset) -> bool:
        """Does an occurrence of `key` count what `noun` counts, or name nothing?"""
        if key[1] or not noun or key not in self.nouns:
            return True
        return any(not have or have & noun for have in self.nouns[key])


def grounded(paths=SOURCES) -> set[tuple[float, str]]:
    """Every numeric claim the source of truth supports (a `Grounded`, which also knows
    what each count counts)."""
    out = Grounded()
    for path in paths:
        try:
            with open(path, encoding="utf-8") as fh:
                out.add_text(fh.read())
        except OSError:
            continue
    return out


def quote(text: str, value: str) -> str:
    body = plain(text or "")
    m = re.search(r"[^.\n]{0,70}" + re.escape(value) + r"[^.\n]{0,50}", body)
    return (m.group(0).strip() if m else "")[:140]


# An answer in an interview or call prep (markdown) drafted at the person's request, under
# the line interview_pack.DRAFT_MARK starts with: its metric is theirs to confirm, and it is
# marked as such, so it is not a finding. It runs from that line to the next heading, the
# next question, or the next answer. Only markdown: a draft never reaches a resume or a
# letter, so in a .tex or a drafts.json nothing is skipped.
_DRAFT_START = re.compile(r"^\s*(?:\*\*|__|\*|_)?draft(?:\*\*|__|\*|_)?\s*:", re.I)
_ANSWER_END = re.compile(r"^\s*(?:#{1,6}\s|- \*\*Q\.\*\*|\*\*A\.\*\*)")


def without_drafts(text: str) -> str:
    """`text` with every answer that still carries a draft's mark taken out."""
    out, skipping = [], False
    for line in str(text or "").splitlines():
        if _DRAFT_START.match(re.sub(r"^\s*\*\*A\.\*\*\s*", "", line)):
            skipping = True
            continue
        if skipping and _ANSWER_END.match(line):
            skipping = False
        if not skipping:
            out.append(line)
    return "\n".join(out)


def check(text: str, source: str = "", allowed=None) -> list[dict]:
    """Numbers in `text` that the source of truth does not support: a figure it never
    states, and a count of something else (`Grounded.agrees`). A plain set passed as
    `allowed` is matched by size and unit alone, as it always was."""
    allowed = allowed if allowed is not None else grounded()
    body = _RESIDUE.sub(" ", plain(text or ""))
    out = []
    for _a, end, value, unit, shown in figures(body):
        key = claim_key(value, unit)
        if key is None:
            continue
        noun = counted(body, end)
        if key in allowed and (not isinstance(allowed, Grounded) or allowed.agrees(key, noun)):
            continue
        finding = {
            "source": source,
            "value": shown.strip(),
            "normalised": f"{key[0]:g}{(' ' + key[1]) if key[1] else ''}",
            "context": quote(text, shown.strip()) or quote(body, shown.strip()),
        }
        if key in allowed:
            finding["counts"] = " ".join(_noun_words(body, end))
            finding["profile_counts"] = sorted({x for x in allowed.said.get(key, ()) if x},
                                               key=len)[:2]
        out.append(finding)
    return out


# The draft fields that are the candidate's own words, rendered. `p2` is the
# researched paragraph and is allowed rather than checked; `concession` and the
# notes are never rendered.
DRAFT_FIELDS = ("summary", "p1", "lead", "p4")


def _bullet_text(b) -> str:
    if isinstance(b, dict):
        return f"{b.get('label', '')}: {b.get('text', '')}"
    return " ".join(str(x) for x in b)


# The fields that state the candidate's own work and nothing about the employer: a figure
# in them comes from the profile, never from the posting or p2. "Where the posting's 12
# operations managers" put into a letter bullet is a metric moved onto the candidate.
CANDIDATE_ONLY = ("summary", "cl_bullets")


def check_draft(a: dict, allowed=None) -> list[dict]:
    """Numbers in one draft's letter and summary that nothing supports. The opening, the
    lead line and the close may repeat the posting's figures and p2's; the summary and the
    letter bullets, which are the candidate's own evidence, only the profile's."""
    allowed = allowed if allowed is not None else grounded()
    if isinstance(allowed, Grounded):
        ok = Grounded(allowed, allowed.nouns, allowed.said)
        for k in ("p2", "posting"):
            ok.add_text(a.get(k) or "", nouns=False)
    else:
        allowed = set(allowed)
        ok = allowed | claims(a.get("p2") or "") | claims(a.get("posting") or "")
    name = a.get("abbr") or a.get("company") or "draft"
    out = []
    for k in DRAFT_FIELDS:
        out += check(a.get(k) or "", f"{name}.{k}", allowed if k in CANDIDATE_ONLY else ok)
    for i, b in enumerate(a.get("cl_bullets") or []):
        out += check(_bullet_text(b), f"{name}.cl_bullets[{i}]", allowed)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--drafts", help="a drafts.json: check each letter and summary as well")
    a = ap.parse_args()
    if not (a.paths or a.drafts):
        ap.error("give a document, or --drafts drafts.json")

    allowed = grounded()
    if not allowed:
        print("check_numbers: the source of truth is unreadable; refusing to "
              "pass everything by default", file=sys.stderr)
        return 2

    findings = []
    for path in a.paths:
        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            if path.endswith(".md"):
                text = without_drafts(text)
            findings += check(text, os.path.basename(path), allowed)
        except OSError as exc:
            print(f"check_numbers: cannot read {path}: {exc}", file=sys.stderr)
            return 2
    drafts = []
    if a.drafts:
        # Through fit_to_page's loader: a kept draft.json names its posting,
        # and the posting's own figures are allowed in the letter.
        import fit_to_page
        try:
            drafts, _ = fit_to_page.load(a.drafts)
        except (OSError, ValueError) as exc:
            print(f"check_numbers: cannot read {a.drafts}: {exc}", file=sys.stderr)
            return 2
        for d in drafts:
            findings += check_draft(d, allowed)

    if not findings:
        print(f"check_numbers: {len(a.paths)} file(s) and {len(drafts)} letter(s) clean, "
              f"{len(allowed)} grounded values")
        return 0
    print(f"check_numbers: {len(findings)} number(s) not in the profile")
    for f in findings:
        print(f"  {f['source']}: {f['value']!r} (as {f['normalised']})")
        if "counts" in f:
            print(f"      the profile counts {f['normalised']} \"" + "\", \"".join(
                f["profile_counts"]) + f"\", and this counts \"{f['counts']}\"")
        if f["context"]:
            print(f"      ...{f['context']}...")
    print("  Either the profile is missing a fact the document states, or the "
          "document states a fact the candidate cannot support. Both need a "
          "person; neither is safe to ship.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
