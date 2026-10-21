#!/usr/bin/env python3
"""Zero-token screen over raw posting text, before any model reads it.

Many triage knockouts used to be nothing more than a stated salary range whose
maximum sat below the walk-away floor, and each one cost a share of a model
call to discover. A regex finds those for free.

Same discipline as `tools/score_posting.py`: this cuts ONLY on a quotable
stated fact, and every cut carries the sentence it was made from. Anything
requiring judgment is left alone for the model stages.

Cuts made here:
  eligibility  citizenship, permanent residency, a security clearance or a
               work-status condition the profile does not meet, stated as a
               condition (the profile's own patterns)
  salary       the whole stated range tops out below the floor (the market's
               currency only; a range in another currency is not compared)
  language     a language the profile does not hold, named as a requirement
               and not a nice-to-have

Flags (never cuts): a years bar, a stated or equivalence-clause degree.

`stated_years()` is the one reading of a years bar shared by this screen,
`fit.py` and `opportunity.py`. It is sentence-level, needs a requirement cue,
refuses a company boast, and reads the LOW end of a range.

Usage:
    python3 tools/text_screen.py postings.json --out screened.json
"""

from __future__ import annotations

import argparse
import functools
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import person  # noqa: E402
import places as _places  # noqa: E402

_S = person.module("search")
CUR = getattr(_S, "CURRENCY_SYMBOL", "$")
SALARY_FLOOR = _S.SALARY_FLOOR

# Below this a posting is not a low offer, it is a different job level, and no
# negotiation closes the gap. Between the two numbers the posting is flagged and
# ranked, never deleted: CLAUDE.md's own rule is that a stated range under the
# target "is a decision input, not an exclusion", and the code was cutting.
# A posted range is a starting position, it is often stale, and it is the one
# number in a posting that moves for the right candidate.
ABSURD_SALARY = getattr(_S, "SALARY_CUT_BELOW", 0)
YEARS_HELD = _S.YEARS_HELD
_BOUNDS = tuple(getattr(_S, "SALARY_RANGE_BOUNDS", (0, 10 ** 9)))

# ---------------------------------------------------------------------------
# Money in the market's currency, however the posting writes it. The old
# pattern needed the symbol in front of every figure and a comma or dot
# thousands separator, so "EUR 35,000", "45 000 €", "GBP 45,000 to 52,000",
# "€45-55k" and "₹12,50,000" were all read as no salary stated: a range under
# the floor was never flagged, and a high one never earned its points.
#
# An amount counts when the market's symbol or ISO code (search.py
# CURRENCY_CODE) sits right before or right after it, or when it is the other
# end of a range whose first end does ("GBP 45,000 to 52,000"); a multiplier on
# one end of a range carries to a bare other end ("€45-55k"). Thousands may be
# written with a comma, a dot or a space, and a rupee market's lakh grouping
# and lakh, crore and LPA words are read. One parser serves this screen,
# tools/bar.py (through salary_range) and tools/opportunity.py.
# ---------------------------------------------------------------------------
CODE = str(getattr(_S, "CURRENCY_CODE", "") or "")
_NUMBER = (r"\d{1,2}(?:,\d{2})+,\d{3}(?!\d)"                       # 12,50,000
           r"|\d{1,3}(?:(?:,|\.|[ \u00a0\u202f])\d{3}(?!\d))+(?:[.,]\d{1,2}(?!\d))?"
           r"|\d+(?:[.,]\d+)?")
_RANGE_JOIN = re.compile(r"\s*(?:-|\u2013|\u2014|to|and|until)\s*", re.I)
_SCALE = {"k": 1_000, "lakh": 100_000, "lakhs": 100_000, "lac": 100_000, "lacs": 100_000,
          "lpa": 100_000, "l": 100_000, "crore": 10_000_000, "crores": 10_000_000}
_RUPEE_WORDS = {"lakh", "lakhs", "lac", "lacs", "lpa", "l", "crore", "crores"}
# A single figure is read as pay only when a pay label sits right before it:
# "Salary: €38,000", "salary up to £62,000", "base pay from $80,000". A lone
# figure anywhere else in a pay sentence is as often a bonus, an allowance or
# the employer's turnover, so it is left alone, as it always was.
_LABELLED = re.compile(
    r"\b(?:salary|base pay|base salary|pay|compensation|remuneration|package)\b\W{0,3}"
    r"(?:(?:is|of|circa|c\.|approx\w*\.?|around|about|will be)\s*)*"
    r"(?:(?P<up>up to|max\w*\.?)\s*|(?P<from>from|starting (?:at|from)|min\w*\.?)\s*)?$",
    re.I)


def _number(num: str) -> float:
    """The figure a posting wrote, with its thousands separators read as such."""
    if re.fullmatch(r"\d{1,2}(?:,\d{2})+,\d{3}", num):
        return float(num.replace(",", ""))
    if re.fullmatch(r"\d{1,3}(?:[,. \u00a0\u202f]\d{3})+(?:[.,]\d{1,2})?", num):
        whole = re.sub(r"[.,]\d{1,2}$", "", num)
        return float(re.sub(r"\D", "", whole))
    return float(num.replace(",", "."))


def money_parser(cur: str, code: str = ""):
    """(money_values, labelled_value) for a market's symbol and ISO code."""
    rupee = cur == "\u20b9" or code.upper() == "INR"
    mark = "|".join(x for x in (re.escape(cur) if cur else "",
                                r"(?<![A-Za-z])(?i:%s)(?![A-Za-z])" % re.escape(code) if code else "")
                    if x) or r"(?!x)x"
    mult = r"(?i:k|lakhs?|lacs?|lpa|crores?)(?![A-Za-z])" + (r"|L(?![A-Za-z])" if rupee else "")
    amount = re.compile(r"(?P<pre>" + mark + r")?\s?(?P<num>" + _NUMBER + r")"
                        r"(?:\s?(?P<mult>" + mult + r"))?(?:\s?(?P<post>" + mark + r"))?")

    def values(sentence: str, loose: bool = False) -> list[int]:
        """Every amount in the market's currency in one sentence, in order.

        `loose` also reads a range with no currency on either end ("Salary: 95-125K",
        "95,000.00 - 125,000.00 annually"), for a sentence that is about pay: most
        postings write a band that way, and it was read as no salary stated. The
        caller's bounds keep "5-7 years" and "2020-2024" out."""
        found = []
        for m in amount.finditer(sentence or ""):
            mu = (m.group("mult") or "").lower()
            marked = bool(m.group("pre") or m.group("post")) or (rupee and mu in _RUPEE_WORDS)
            found.append([m, _number(m.group("num")), mu, marked])
        # A range's bare end takes the other end's currency and multiplier.
        for a, b in zip(found, found[1:]):  # noqa: B905  (adjacent pairs)
            if not _RANGE_JOIN.fullmatch(sentence[a[0].end():b[0].start()]):
                continue
            if a[3] == b[3] and not (loose and not a[3]):
                continue
            a[3] = b[3] = True
            if a[2] and not b[2] and b[1] < 1000:
                b[2] = a[2]
            elif b[2] and not a[2] and a[1] < 1000:
                a[2] = b[2]
        return [int(round(v * _SCALE.get(mu, 1))) for _, v, mu, marked in found if marked]

    def labelled(sentence: str) -> tuple[int | None, int | None]:
        """(low, high) for one figure introduced by a pay label, or (None, None).
        "up to" states only the top and "from" only the bottom; a bare label
        states both."""
        for m in amount.finditer(sentence or ""):
            if not (m.group("pre") or m.group("post")):
                continue
            lab = _LABELLED.search(sentence[:m.start()])
            if not lab:
                continue
            v = int(round(_number(m.group("num")) * _SCALE.get((m.group("mult") or "").lower(), 1)))
            if not _BOUNDS[0] <= v <= _BOUNDS[1]:
                continue
            if lab.group("up"):
                return None, v
            if lab.group("from"):
                return v, None
            return v, v
        return None, None

    return values, labelled


money_values, labelled_value = money_parser(CUR, CODE)

# "per annum", "p.a." and "DOE" are how the UK and Ireland write it, and a
# range stated only that way ("We offer GBP 45,000 to 52,000 DOE") was read as
# no salary at all.
RANGE_CUE = re.compile(r"salary|compensation|remuneration|\bpay\b|hiring range|"
                       r"annual|per year|/yr|per annum|\bp\.\s?a\b|\bpa\b|"
                       r"depending on experience|\bdoe\b|\bote\b|we offer|package|"
                       r"\bctc\b|\blpa\b", re.I)
HOURLY = re.compile(r"per hour|hourly|/\s?h(ou)?r|an hour", re.I)
# The market's patterns are the profile's (search.py), loaded here:
#   FOREIGN_CURRENCY  a range in another currency is not compared against the
#                     floor, it is left to the scorer
#   LANGUAGE_GATE     (language, required pattern, asset pattern) for each
#                     language the market raises that the candidate lacks
#   ELIGIBILITY, ENTITLED, PERMIT_ACCEPTED and the ELIGIBILITY_* terms: the
#                     statuses a posting can require and how the candidate's
#                     own status meets them
#   DESIGNATION, DESIGNATED_TITLE  the market's professional credentials
#   RESEARCH_ML       a discipline the candidate does not hold, whose
#                     techniques mark a role whose core is research
_NEVER = re.compile(r"(?!x)x")
FOREIGN_CURRENCY = getattr(_S, "FOREIGN_CURRENCY", _NEVER)
LANGUAGE_GATE = list(getattr(_S, "LANGUAGE_GATE", []))


# The language gate once covered only the one language the market keeps
# raising. A posting that made another language essential for working with
# overseas suppliers sailed through.
# Any language the candidate does not hold, stated as a requirement, is
# the same hard bar, so every language below is checked except those the
# profile holds (search.py LANGUAGES_HELD).
#
# "polish" is the trap here and it is not hypothetical: it is ordinary business
# English ("strong communication skills and polish in client-facing work"), it
# lands in the same sentence as "required" by construction because that is what
# a communication-skills bullet looks like, and the cut fired on it. It needs
# language context. So do the handful of others that are also English words or
# nationalities: German, Italian, Dutch, Hebrew, Turkish, Korean.
_HELD = {x.lower() for x in getattr(_S, "LANGUAGES_HELD", ("english",))}
_UNAMBIGUOUS_LANGUAGE = "|".join(
    x for x in ("mandarin|cantonese|chinese|spanish|portuguese|hindi|"
                "punjabi|urdu|arabic|japanese|tagalog|vietnamese|"
                "russian|ukrainian|farsi|persian").split("|") if x not in _HELD)
_ALSO_AN_ENGLISH_WORD = "|".join(
    x for x in "polish|german|italian|dutch|hebrew|turkish|korean".split("|") if x not in _HELD)
# A language cue next to the word, on either side, is what makes it a language.
_LANG_CUE = (r"(?:language|fluen\w*|nativ\w*|speak\w*|spoken|written|"
             r"bilingual|proficien\w*|literac\w*|translat\w*)")
OTHER_LANGUAGE = re.compile("|".join(
    ([r"\b(?:" + _UNAMBIGUOUS_LANGUAGE + r")\b"] if _UNAMBIGUOUS_LANGUAGE else [])
    + ([r"\b(?:" + _ALSO_AN_ENGLISH_WORD + r")\s+" + _LANG_CUE,
        _LANG_CUE + r"\s+(?:in\s+)?(?:" + _ALSO_AN_ENGLISH_WORD + r")\b"]
       if _ALSO_AN_ENGLISH_WORD else [])
) or r"(?!x)x", re.I)
LANGUAGE_REQUIRED = re.compile(
    r"\b(fluen\w*|nativ\w*|bilingual|proficien\w*|requir\w*|must speak|"
    r"mandatory|essential|written and (spoken|oral))\b", re.I)

# A language named as a language, not as a market or a supplier. "Experience with Spanish
# and Portuguese markets is required" and "analysing Chinese supplier lead times" were cut
# as language requirements: the unambiguous names were read with no cue at all, and
# "required" sat in the same sentence. A name counts when a language cue sits beside it,
# with nothing between but other languages and the words a level is written in ("fluent
# in English and Spanish", "Spanish (written and spoken)", "Spanish-speaking"), or when a
# requirement follows it straight away ("Spanish is required"). The names that are also
# English words keep the closer reading OTHER_LANGUAGE gives them.
_ANY_LANGUAGE = "|".join(sorted(
    {"english", "french", "welsh", "irish", "gaelic", "german", "italian", "dutch", "polish",
     "hebrew", "turkish", "korean", *_UNAMBIGUOUS_LANGUAGE.split("|"), *_HELD,
     *(str(g[0]).lower() for g in LANGUAGE_GATE)} - {""}, key=len, reverse=True))
_LANG_SEP = r"[\s,/&()\-:]+"
# A level is written as a test or a grade as often as a word: "Japanese (JLPT N2) required",
# "German, C1, essential". Read the grade as filler and a short bracket as one step, or the
# narrower reading lets a stated requirement through as a plus.
_LANG_FILLER = (r"(?:in|of|and|or|both|either|business|professional|working|conversational|"
                r"full|excellent|strong|good|advanced|fluent|written|spoken|oral|verbal|level|"
                r"above|minimum|jlpt|hsk|cefr|dele|topik|[abc][12]|n[1-5]|"
                + _ANY_LANGUAGE + r")")
_LANG_STEP = r"(?:" + _LANG_SEP + _LANG_FILLER + r"|\s*\([^()\n]{1,40}\))"
_CUE_BEFORE = re.compile(r"\b" + _LANG_CUE + r"(?:" + _LANG_SEP + _LANG_FILLER + r"){0,4}"
                         + _LANG_SEP + r"$", re.I)
_CUE_AFTER = re.compile(_LANG_STEP + r"{0,3}" + _LANG_SEP
                        + r"(?:" + _LANG_CUE + r"|(?:(?:is|are)\s+(?:also\s+)?)?"
                        r"(?:required|essential|mandatory|necessary|a must)\b)", re.I)
_UNAMBIGUOUS_RX = (re.compile(r"(?:" + _UNAMBIGUOUS_LANGUAGE + r")", re.I)
                   if _UNAMBIGUOUS_LANGUAGE else _NEVER)

# A second language named as a nice-to-have. The screen's own preference words (PREFERRED,
# and ENCOURAGE, which holds "not required" and "welcome"), and the few a language line adds.
# "Bilingual in Spanish is a plus", "Fluency in Mandarin would be an advantage" and
# "Proficiency in Japanese is preferred but not required" were all cut as requirements:
# "bilingual", "fluency" and the "requir" inside "not required" read as the requirement,
# and only the profile's own language had its nice-to-have words checked.
_LANGUAGE_SOFT = re.compile(
    r"\b(?:is|are|be|as|considered|seen as)\s+an?\s+(?:\w+\s+)?advantage\b"
    r"|[:(,\-]\s*an?\s+(?:\w+\s+)?advantage\b"
    r"|\b(?:is|are|be)\s+(?:\w+\s+)?(?:beneficial|helpful|useful)\b"
    r"|\bnot\s+(?:a\s+)?(?:required|requirement|essential|mandatory|necessary|needed)\b"
    r"|\boptional\b", re.I)


def _language_preferred(sentence: str) -> bool:
    """Does the sentence name what it asks for as a preference, not a requirement?"""
    return bool(PREFERRED.search(sentence) or ENCOURAGE.search(sentence)
                or _LANGUAGE_SOFT.search(sentence))


def other_language_named(sentence: str):
    """The first language the candidate does not hold that `sentence` names as a language,
    as a match, or None. Its text is what a cut names ("Spanish", "fluent in German")."""
    s = sentence or ""
    for m in OTHER_LANGUAGE.finditer(s):
        if not _UNAMBIGUOUS_RX.fullmatch(m.group(0)):
            return m                    # an English word, matched only beside its cue
        if (_CUE_BEFORE.search(s[max(0, m.start() - 100):m.start()])
                or _CUE_AFTER.match(s, m.end())):
            return m
    return None


def other_language_cut(sentence: str):
    """The language match a sentence states as a requirement, or None.

    A language the candidate does not hold, named as a language, in a sentence with a
    requirement word and no preference word, that the profile's own language rows
    (search.py LANGUAGE_GATE) do not call a nice-to-have."""
    if _language_preferred(sentence) or any(soft.search(sentence)
                                            for _, _, soft in LANGUAGE_GATE):
        return None
    m = other_language_named(sentence)
    return m if m is not None and LANGUAGE_REQUIRED.search(sentence) else None

ELIGIBILITY = getattr(_S, "ELIGIBILITY", _NEVER)
ENTITLED = getattr(_S, "ENTITLED", _NEVER)
PERMIT_ACCEPTED = getattr(_S, "PERMIT_ACCEPTED", _NEVER)
_STATUS_TERMS = getattr(_S, "ELIGIBILITY_STATUS_TERMS", _NEVER)
_NOT_BY_PERMIT = getattr(_S, "ELIGIBILITY_NOT_BY_PERMIT", _NEVER)
_ALWAYS = getattr(_S, "ELIGIBILITY_ALWAYS", _NEVER)
ELIGIBILITY_CUT_REASON = getattr(_S, "ELIGIBILITY_CUT_REASON",
                                 "eligibility gate: a status the candidate does not hold stated as a condition")
CONDITION = re.compile(
    r"\b(must|required|require[sd]?|requirement|only|eligib\w+|need to be|"
    r"needs? to|restricted to|limited to|condition of|prerequisite|"
    r"be able to obtain|ability to obtain|hold(?:s|ing)? a|will be required|"
    r"is mandatory|mandatory|are subject to)\b", re.I)
ENCOURAGE = re.compile(
    r"\b(encouraged?|welcome|preference|priority|equal opportunity|diversity|"
    # "private equity" is a line of business, not an equity statement: "due to
    # our private equity mandates, this role requires citizenship" passed.
    r"self[- ]identify|(?<!private )equity|inclusi\w+|regardless of|all qualified|"
    r"without regard|indigenous|accommodat\w+|do not require|not required|"
    r"no (?:citizenship|clearance|security clearance) (?:is )?required)\b", re.I)


WORD_NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
            "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
            "twelve": 12, "fifteen": 15, "twenty": 20}
_NUM = r"(\d{1,2}|" + "|".join(WORD_NUM) + r")"
# A range ("3-7 years", "4 to 6 years") states its LOW end as the bar. Reading
# the high end as the requirement cut postings whose real bar the profile met,
# so the low end is what counts and every dash form matches.
# The token right after "years" must open an experience phrase, or "18 years
# or older ... criminal background check" reads as a bar.
YEARS = re.compile(
    r"\b" + _NUM + r"\s*(?:\+|(?:\s*(?:-|–|—|to)\s*" + _NUM + r"))?\s*(?:\+\s*)?"
    r"(?:years?|yrs?)\b\.?\s*"
    r"(?:(?:of|in|’|'|working|relevant|progressive|professional|hands[- ]on|"
    r"related|industry|practical|proven|demonstrated|direct|prior|full[- ]time|"
    r"solid|strong|recent|previous|combined|equivalent|total|minimum|"
    r"post[- ]\w+|as an?|as)\b[^.\n]{0,40}?)?"
    r"(experience|exp\b|\brole\b|\bbackground\b)", re.I)
# A professional designation is a credential gate, not a skills gap: no amount
# of adjacent experience substitutes for an examining body's credential. A
# pricing posting can require an actuarial designation in progress, and a full
# resume and cover letter used to be written for one before this existed.
DESIGNATION = getattr(_S, "DESIGNATION", _NEVER)
DESIGNATED_TITLE = getattr(_S, "DESIGNATED_TITLE", _NEVER)
# The words a posting uses to make the credential a condition. "Must be
# registered", "essential" and "mandatory" are how the UK and Ireland say it
# ("Membership of CIPS is mandatory", "a recognised accounting qualification
# (ACA, ACCA or CIMA) is essential"), and each of those passed the gate: a full
# application could be drafted for a job the candidate cannot legally hold.
# The sentence still has to name one of the profile's credentials, and
# PREFERRED and ENCOURAGE still win ("CIMA desirable"). Words that also mean
# something else in a sentence naming a credential ("registered as a charity",
# "reporting to our Chartered Accountant") are deliberately not here: a false
# cut loses a role, which costs more than a false pass.
DESIGNATION_REQUIRED = re.compile(
    r"\b(progress(ing|ion)? (toward|towards)|working toward|actively pursuing|"
    r"enrolled in|passed|completed|must (hold|have|possess|be)|required|requirement|"
    r"essential|mandatory|a must|eligible for (registration|membership))\b", re.I)

# Research-grade ML: the deep-learning blocker was narrowed to roles whose core
# IS deep learning, which let through a role built on causal inference,
# contextual bandits and off-policy evaluation. Those are a different discipline
# from applied analytics, not a harder version of it. The techniques are the
# profile's (search.py RESEARCH_ML).
RESEARCH_ML = getattr(_S, "RESEARCH_ML", _NEVER)

# "Minimum Qualifications" is usually a heading a sentence or two above the
# degree line, and postings arrive with markdown in them, so a sentence-local
# regex misses it. One posting read "- **Education:** Advanced degree (Master's or
# Ph.D.)" under a "**Minimum Qualifications:**" heading.
MINIMUM_HEADING = re.compile(r"minimum (qualification|requirement)s?|"
                             r"basic qualifications|required qualifications", re.I)
EDUCATION_LABEL = re.compile(r"education\W{0,4}\s*(an?\s+)?advanced\s+degree", re.I)


def under_minimum_qualifications(text, sentence):
    """True when this sentence sits under a minimum-qualifications heading.

    Looks back a short way from where the sentence starts rather than inside
    it, because the heading is nearly always its own line above.
    """
    if EDUCATION_LABEL.search(sentence):
        return True
    i = text.find(sentence[:60])
    if i < 0:
        return False
    return bool(MINIMUM_HEADING.search(text[max(0, i - 700):i]))

# A graduate degree, however a posting names it. One definition: tools/fit.py docks
# points on this pattern (fit.GRAD) and the screen flags on it, and while each kept
# its own the score read no degree in "An MBA is required", "an advanced degree in
# statistics" or "a graduate degree" that the screen flagged, and the screen read
# none in "M.S. in statistics" or "a doctoral degree" that the score docked.
DEGREE = re.compile(r"\b(?:master|msc|m\.sc\.?|m\.s\.?|mba|ph\.?\s?d\.?|doctora\w*"
                    r"|(?:post-?)?graduate degree|advanced degree)(?:'?s)?(?![\w'])", re.I)
# "Master" is a data-architecture word before it is a degree. A posting can
# list "master data management" among its data skills and be flagged as
# stating a graduate requirement. `mastering`, `master plan` and
# `masterclass` are the same trap. A degree word followed by one of these is
# not a degree. Nor is a Scrum Master, which a business analyst posting asks
# for, or the verb: a posting says "learn to use and master the various
# internal data warehouse tables", and `fit.py` docked it 9 points for a
# graduate degree. Nor the supply-chain terms: a "Master Production Schedule (MPS)",
# a master scheduler, a Lean Six Sigma Master Black Belt.
NOT_A_DEGREE = re.compile(
    r"\bmaster'?s?\s+(?:data|plan|class|file|record|copy|agreement|service|key|list|"
    r"catalog\w*|schedule|scheduler|scheduling|production|black\s+belt|budget|brand|"
    r"template|node|branch)\b"
    r"|\bmaster(?:ing|ed|y)\b"
    r"|(?<=\bscrum\s)master\b"
    r"|\bmaster\s+(?:the|a|an|our|your|its|their|this|these|those|new)\b", re.I)
ESCAPE = re.compile(r"or equivalent|or comparable|or relevant experience|equivalent experience|"
                    r"or an equivalent|equivalent practical|or related experience", re.I)
# Preference in its own words. "asset" and "bonus" count only as "is an asset" or
# "would be a bonus": anywhere in a sentence they read "the CFA is required for our
# asset management team" and "a bonus-eligible role" as nice-to-haves, so a real
# credential gate, a years bar and a required degree went unseen.
PREFERRED = re.compile(
    r"\bpreferred\b|\bpreferably\b|\bnice[- ]to[- ]have\b|\bideally\b|\ba plus\b|\bdesirable\b"
    r"|\badvantageous\b|\bbonus points?\b"
    r"|\b(?:is|are|be|considered|seen as|counts as)\s+(?:an?\s+)?(?:(?:strong|definite|real|big|"
    r"great|added|additional)\s+)?(?:asset|bonus)\b", re.I)

# A years figure only bars the candidate if the sentence is ABOUT the candidate.
# "With more than 40 years of experience, we're the team behind <a lender>" must
# not cut a role: company history is not a requirement. So a years cut needs a
# requirement cue and must not carry a company-boast cue.
WANTS = re.compile(r"\b(?:requir\w*|qualificat\w*|must have|minimum|at least|you have|"
                   r"you'?ll bring|you bring|you'?ll need|you need|you should have|"
                   r"we'?re looking for|looking for|proven|demonstrated|ideal candidate|"
                   r"experience (?:in|with|as)|background in|track record|"
                   r"candidates? (?:should|must|will))\b", re.I)
# "We're looking for" is a requirement heading, not a company boast, and reading
# it as one discarded the sentence behind it: "Who We're Looking For 5+ years
# of experience in data science" had its bar thrown away by the rule meant to
# ignore "we've been in business since 1994".
BOAST = re.compile(r"\b((?:we'?re|we are|we have|we'?ve)"
                   r"(?!\s+(?:looking\s+for|seeking|hiring|after|in\s+search))|"
                   r"our (team|company|firm|history|story)|"
                   r"the team behind|serving (customers|clients)|in business|founded|"
                   r"is an? (leading|global|proud|canadian|trusted|top|growing|fast)|"
                   r"company with|firm with|provider|pioneer|since \d{4}|has been)\b", re.I)
# A figure this far out is a boast unless the sentence is unmistakably a bar.
STRONG_WANT = re.compile(r"\b(requir|must|minimum|at least|qualificat)\w*", re.I)


# A bullet list scraped out of HTML arrives with the punctuation stripped, so
# the whole list is one "sentence". The longest runs to thousands of
# characters against a median of 100, and every gate here works on proximity
# inside a sentence: with a 40-character window, "required" from one bullet
# and "French" from another land next to each other and the posting is cut for
# a language nobody asked for. Roles in the candidate's own city were cut that
# way.
MAX_SENTENCE = 300

# What separates two bullets when the full stops are gone. The last one is the
# signature of a list joined with nothing: a word ending mid-clause butting
# straight into the capitalised start of the next bullet, as in "...prevent
# customer dissatisfaction Conduct audits of dealers' warehouse operations".
_BULLET_BREAK = re.compile(
    r"\s*[\u2022\u2023\u25aa\u25cf\u00b7\u2043]\s*"
    r"|\s{2,}"
    r"|\s+[|]\s+"
    r"|(?<=[a-z,)])\s+(?=[A-Z][a-z]{2,}\s)")

# `findall` needs a group to count, and the pattern above has none by design:
# splitting on a captured group would keep the separator in the output.
_BULLET_BREAK = re.compile("(%s)" % _BULLET_BREAK.pattern)

# The headings a posting puts between its blocks. They are the real separator
# inside a joined blob and they are high-precision, so they are taken as a
# boundary whatever sits in front of them: a "5+ years of experience in data
# science" bar follows "Who We're Looking For" immediately after a sentence of
# company boast, and without this the boast and the bar stay in one sentence
# and the boast wins. The heading stays with the text it introduces,
# which is why this is a lookahead.
_SECTION_HEADING = re.compile(
    r"(?=\b(?:who (?:you are|we(?:'re| are)? looking for)"
    r"|what (?:you(?:'ll| will)? do|we(?:'re| are)? looking for|you(?:'ll| will)? bring)"
    r"|the impact you(?:'ll| will)? have"
    r"|(?:minimum|preferred|basic|required|key)\s+qualifications"
    r"|qualifications|requirements|responsibilities|what you need"
    r"|about (?:you|the role|the team|this role)"
    r"|your (?:profile|background|experience)"
    r"|you (?:will|'ll) (?:have|bring|need))\b)", re.I)


# A full stop that ends an abbreviation, not a sentence. Split there, "5+ yrs. of
# experience" lost its bar ("5+ yrs." alone has no experience phrase), "Ph.D. in
# statistics required." lost the word "required", and "must be U.S. citizens" lost
# the status. An initialism ("U.S.", "Ph.D.", "e.g.", "a.m.") is a letter and a full
# stop after another full stop; the words are those a posting abbreviates mid-sentence.
# Only where the next word carries on in lower case or with a figure: "based in the
# U.S. We are an equal opportunity employer" is two sentences, and joined, the second
# would excuse the first. A lone capital ("Python or R.") is a sentence end.
ABBREVIATIONS = ("vs", "approx", "min", "max", "yrs", "yr", "incl", "inc", "ltd", "co",
                 "etc", "dr", "mr", "mrs", "ms", "st", "sr", "jr", "sc")
SENTENCE_END = re.compile(
    r"(?<=[.!?;])(?:(?<!\.[A-Za-z]\.)"
    + "".join(r"(?<!\b(?i:%s)\.)" % a for a in ABBREVIATIONS)
    + r"\s+|\s+(?![\sa-z0-9]))|\n+")


def sentences(text: str) -> list[str]:
    """Sentences, with run-together bullet lists broken back apart.

    Only over-long pieces are split further. Ordinary prose is left exactly as
    it was, because the aggressive break would cut it at every proper noun; a
    piece three times the median length is a list, not a sentence.

    Every gate reads a posting's sentences, so one posting's body is split about
    fifteen times across the screen, the opportunity score, fit and the bar, and the
    split was most of what those stages cost. The split of a body is kept for the
    next reader (`_split`); each caller gets its own list, so none can change
    another's.
    """
    return list(_split(text or ""))


@functools.lru_cache(maxsize=128)
def _split(text: str) -> tuple:
    out = []
    for piece in SENTENCE_END.split(text):
        piece = piece.strip()
        if not piece:
            continue
        if _is_run_together(piece):
            out.extend(_break_bullets(piece))
        else:
            out.append(piece)
    return tuple(out)


# The shortest thing a bullet can be. Without a floor the capitalised-word rule
# shreds a heading: "process Who You Are 5+ years of Fintech" came apart into
# "Who", "You", "Are 5+ years of" and "Fintech or payments experience", and the
# piece holding the number lost the requirement cue that makes it a bar, and
# the flag disappeared.
MIN_PIECE = 40


def _break_bullets(piece: str) -> list:
    """`piece` split at bullet boundaries, keeping each part long enough to read.

    A boundary is only taken when there is a clause in front of it, so the rule
    separates two bullets without taking a heading apart word by word.
    """
    # (where the piece ends, where the next begins, is it a heading). A bullet
    # boundary is whitespace and is consumed; a heading is a lookahead and stays
    # with the block it introduces.
    breaks = sorted([(m.start(), m.end(), False) for m in _BULLET_BREAK.finditer(piece)]
                    + [(m.start(), m.start(), True)
                       for m in _SECTION_HEADING.finditer(piece) if m.start()])
    out, start = [], 0
    for begin, after, heading in breaks:
        if begin < start or (not heading and begin - start < MIN_PIECE):
            continue
        chunk = piece[start:begin].strip()
        if chunk:
            out.append(chunk)
        start = after
    tail = piece[start:].strip()
    if tail:
        out.append(tail)
    return out or [piece]


def _is_run_together(piece: str) -> bool:
    """Is this a bullet list with the punctuation gone, or one long sentence?

    Length alone does not tell them apart: a list that cut a local role for
    French ran only a couple of hundred characters, comfortably inside anything
    a real sentence might reach. What tells them apart is how many times a
    clause ends mid-flow and the next word starts capitalised, which happens
    once in an ordinary sentence with a proper noun in it and four times in a
    joined list.

    The count matters because the split is not free. "Must be fluent in French"
    breaks at "in French", and the half with the language in it no longer
    carries the cue, so a genuine requirement written as a short bullet would
    stop being caught. Requiring several boundaries keeps those intact.
    """
    if len(piece) > MAX_SENTENCE:
        return True
    # A posting heading part-way through is a joined blob whatever its length.
    # A bar can follow "Who We're Looking For" one clause after a sentence of
    # company boast, and while they share a sentence the boast rule wins and the
    # bar is never seen.
    if any(m.start() for m in _SECTION_HEADING.finditer(piece)):
        return True
    # Counted the same way the split takes them, which is the only count that
    # means anything: three raw boundaries is an ordinary sentence with three
    # proper nouns in it. "The role reports to the Director of Analytics in
    # Manchester and owns forecasting" has exactly three, and it is one sentence.
    return len(_break_bullets(piece)) >= 3


def evidence(sentence: str, match, width: int = 90) -> str:
    """The matched phrase with enough either side to check it.

    Quoting the first 200 characters of the containing sentence is what a cut
    used to show, and on a 4,601-character list that is 200 characters of
    something else entirely: the reader is asked to accept "French stated as a
    requirement" under a quote about warehouse audits.
    """
    if match is None:
        return sentence[:200]
    start = max(match.start() - width, 0)
    end = min(match.end() + width, len(sentence))
    return ("..." if start else "") + sentence[start:end].strip() + ("..." if end < len(sentence)
                                                                     else "")


def _num(tok: str) -> int:
    return int(tok) if tok.isdigit() else WORD_NUM[tok.lower()]


def years_bars(text: str) -> list[tuple[int, str]]:
    """Every years bar a posting states for the CANDIDATE, with its sentence.

    Sentence-level. A sentence counts only when it carries a requirement cue and
    no company-boast cue, is not a nice-to-have, and the figure opens an
    experience phrase. A range contributes its low end. Sorted ascending, so the
    first entry is the lowest bar stated anywhere in the posting.
    """
    found = []
    for s in sentences(text or ""):
        if PREFERRED.search(s) or BOAST.search(s) or not WANTS.search(s):
            continue
        for m in YEARS.finditer(s):
            n = _num(m.group(1))
            if n > 25 or (n > 12 and not STRONG_WANT.search(s)):
                continue
            found.append((n, s[:220]))
    return sorted(found, key=lambda x: x[0])


def stated_years(text: str) -> tuple[int | None, str]:
    """The HIGHEST years bar stated, and the sentence it came from.

    Kept at the highest because a screening decision should read a posting at
    its harshest. `entry_years()` is the companion for the scoring decision,
    which should not.
    """
    bars = years_bars(text)
    return (bars[-1][0], bars[-1][1]) if bars else (None, "")


def entry_years(text: str) -> tuple[int | None, int | None, str]:
    """The bar that actually gates entry, the highest stated, and the quote.

    A posting is a wish list written by several people. "3+ years of SQL" in the
    requirements and "10+ years in logistics" three paragraphs down are
    not one bar of ten; the three is what the recruiter screens on and the ten is
    somebody's aspiration for the ideal hire.

    Reading only the highest made every multi-bar posting look like a Principal
    role. That is not a rare shape: it is how a posting that lists requirements
    per skill is written.

    So the entry bar is the LOWEST stated, and the highest travels alongside it
    so the scorer can say the spread out loud. A posting stating one bar is
    unaffected: low and high are the same number.
    """
    bars = years_bars(text)
    if not bars:
        return None, None, ""
    return bars[0][0], bars[-1][0], bars[0][1]


# A year of full-time hours, for a band stated by the hour: read as no salary, an hourly
# posting skipped both the pay cut and the pay score.
HOURS_PER_YEAR = int(getattr(_S, "HOURS_PER_YEAR", 2080) or 2080)
# One band of several in a sentence, each with the place it is for: "$58,000 - $66,000
# (Toronto), $70,000 - $80,000 (New York)". Split at a comma or semicolon followed by a
# space, which a thousands separator never is.
_BAND_SPLIT = re.compile(r"[,;]\s+(?=\D{0,40}\d)|\s+(?:and|or)\s+(?=\D{0,40}\d)")


def _home(text: str) -> bool:
    """Does `text` name the person's own place: their metro, region or country?

    The one place matcher the residence cut uses (`_names_home`). This kept its own,
    which matched a metro town inside any word and the country only as written, so a
    "wholesale" desk read as the town of Sale, "Canterbury" as Bury, and a band marked
    "(UK remote)" as somewhere else: the wrong band was the one cut or scored."""
    return _names_home(str(text or ""))


def _bands(s: str, loose: bool) -> list:
    """[(low, high, the part of the sentence that states it)] for each band in it."""
    hourly = bool(HOURLY.search(s))
    out = []
    for part in _BAND_SPLIT.split(s) if len(money_values(s, loose)) > 2 else [s]:
        vals = money_values(part, loose)
        if hourly:
            vals = [v * HOURS_PER_YEAR for v in vals if v < 1000]
        vals = [v for v in vals if _BOUNDS[0] <= v <= _BOUNDS[1]]
        if len(vals) >= 2:
            out.append((min(vals), max(vals), part))
    return out


def salary_range(text: str) -> tuple[int | None, int | None, str]:
    """(low, high, quote) of the stated pay range, in the market's currency: the band for
    the person's own place where the posting gives one per place, otherwise the one
    with the highest top.

    One parser for both callers. `salary_max()` needs only the top, to flag a
    range under the floor; `tools/bar.py` needs the midpoint, to say whether a
    posting clears the candidate's pay bar, and reading the range twice two
    different ways is how the two would come to disagree about one posting.

    A band with no currency on either end, a band by the hour (annualised at
    HOURS_PER_YEAR) and a band whose pay label is a heading on the line before it are
    read too. Given a band per place, the highest was read, so a posting whose band
    for the person's own city sat under their cut line was never cut.
    """
    bands = []
    single = (None, None, "")
    prev = ""
    for s in sentences(text):
        cue = RANGE_CUE.search(s) or HOURLY.search(s) or (
            prev and len(prev) <= 60 and RANGE_CUE.search(prev))
        heading, prev = prev, s
        if not cue or FOREIGN_CURRENCY.search(s):
            continue
        found = _bands(s, loose=True)
        for lo, hi, part in found:
            bands.append((lo, hi, s[:220], part, heading))
        if not found and single[2] == "" and not HOURLY.search(s):
            one_lo, one_hi = labelled_value(s)
            if one_lo or one_hi:
                single = (one_lo, one_hi, s[:220])
    if not bands:
        return single
    # A stated range wins; a single labelled figure is read only when there is none.
    home = [b for b in bands if _home(b[3])]
    lo, hi, quote = (home[0] if home else max(bands, key=lambda b: b[1]))[:3]
    return lo, hi, quote


def salary_max(text: str) -> tuple[int | None, str]:
    """Highest annual figure in a sentence that reads like a pay range."""
    _, hi, quote = salary_range(text)
    return hi, quote


# A permit named only to be refused: "not open to work permit holders", "unable
# to sponsor a work visa". Read as accepting the permit, such a sentence was a
# list of routes in and passed, which is the opposite of what it says.
_REFUSED = re.compile(r"\b(?:not|no|unable|cannot|can't|won't|will not|ineligible|excluding|"
                      r"except|nor|without)\b[^.;:]{0,40}$", re.I)


def _permit_accepted(s: str) -> bool:
    return any(not _REFUSED.search(s[:m.start()]) for m in PERMIT_ACCEPTED.finditer(s))


def _states_ineligibility(s: str) -> bool:
    """Does this sentence state, as a condition, a status the candidate lacks?"""
    if not ELIGIBILITY.search(s) or ENCOURAGE.search(s):
        return False
    # "must be legally entitled to work in <country>" alone is met by a
    # candidate who is; only a status term beside it, with a condition cue,
    # is a bar.
    if ENTITLED.search(s) and not _STATUS_TERMS.search(s):
        return False
    # The same sentence naming a work permit as an ACCEPTED status is a
    # list of routes in, and the candidate's own status may be one of them.
    # Some bars (a clearance) are never satisfied that way, so they still cut.
    if _permit_accepted(s) and not _NOT_BY_PERMIT.search(s):
        return False
    return bool(CONDITION.search(s) or _ALWAYS.search(s))


# A sentence that ends on an initialism: "Applicants must be a U.S." is split from
# "Citizen or Permanent Resident." because the next word is capitalised, which is how a
# new sentence starts and also how a status is written. The status was never read whole.
_ENDS_ON_INITIALISM = re.compile(r"(?<![A-Za-z.])(?:[A-Za-z]\.){2,}$")


def eligibility_cut(text: str) -> str | None:
    """The sentence that states, as a condition, a status the candidate lacks.

    A sentence ending on an initialism is read on its own and joined with the one after
    it, and either is a cut: joined, "must be a U.S. Citizen" is the status it states,
    and read alone as well, an equal opportunity line after it never excuses it."""
    parts = sentences(text)
    for i, s in enumerate(parts):
        if _states_ineligibility(s):
            return s[:220]
        if i + 1 < len(parts) and _ENDS_ON_INITIALISM.search(s):
            joined = s + " " + parts[i + 1]
            if _states_ineligibility(joined):
                return joined[:220]
    return None


# A vacancy open only to the employer's own staff. Nobody outside can be hired
# into it, however well they match: a test round put "Data Analyst Support |
# Internal Mobility" eighth on a shortlist. The title says so ("Internal
# Mobility", "internal applicants only") or a sentence restricts who may apply.
# "Internal candidates will be prioritised" and "internal and external
# applicants welcome" are not restrictions, and "Internal Audit" is a job. The
# patterns are English; a profile in another language sets search.py
# INTERNAL_ONLY_TITLE and INTERNAL_ONLY.
INTERNAL_ONLY_TITLE = getattr(_S, "INTERNAL_ONLY_TITLE", None) or re.compile(
    r"\binternal (?:mobility|only|transfer|candidates? only|applicants? only)\b", re.I)
INTERNAL_ONLY = getattr(_S, "INTERNAL_ONLY", None) or re.compile(
    r"\b(?:open|available|restricted|limited) (?:only )?to (?:current|existing|internal) "
    r"(?:\w+ )?(?:employees|staff|colleagues|team members|candidates|applicants)"
    r"(?! and)(?:,? only)?"
    r"|\b(?:internal|existing staff|current employees) (?:applicants|candidates|staff)? ?only\b"
    r"|\bonly (?:open to |for )?(?:current|existing|internal) "
    r"(?:\w+ )?(?:employees|staff|colleagues|candidates|applicants)\b", re.I)
_RESTRICTS = re.compile(r"\bonly\b|\brestricted\b|\blimited to\b", re.I)


def internal_only(title: str, text: str) -> str | None:
    """The title or sentence that restricts a vacancy to the employer's own staff."""
    if INTERNAL_ONLY_TITLE.search(title or ""):
        return (title or "")[:200]
    for s in sentences(text):
        m = INTERNAL_ONLY.search(s)
        if m and _RESTRICTS.search(m.group(0)):
            return s[:200]
    return None


# A credential named as one the role does not need: "No actuarial exams are needed",
# "you do not need to be qualified".
_NOT_NEEDED = re.compile(
    r"\bnot\s+(?:a\s+)?(?:needed|required|necessary|essential|mandatory|a requirement)\b"
    r"|\bno\s+(?:\w+\s+){0,4}(?:is|are)\s+(?:needed|required|necessary)\b"
    r"|\b(?:do|does|will)\s+not\s+(?:need|require)\b|\b(?:don'?t|doesn'?t)\s+(?:need|require)\b",
    re.I)


def designation_cut(text, title: str = ""):
    """The sentence stating a professional designation as a condition, or None.

    "Support for actuarial exams" and "CPA an asset" are not gates; a title
    that IS the designation, or a qualification line demanding progress toward
    one, is. Held designations are none of these, so any match is a real bar.
    """
    lifted = False
    for s in sentences(text):
        if not DESIGNATION.search(s):
            continue
        if PREFERRED.search(s) or ENCOURAGE.search(s) or _NOT_NEEDED.search(s):
            lifted = True
            continue
        if DESIGNATION_REQUIRED.search(s):
            return s[:200]
    # A title naming the profession outright, repeated through the posting,
    # is the same bar whether or not a qualification line spells it out. It is the
    # posting's own title that has to name it, where there is one: "Data Analyst to
    # support our actuarial pricing team" names the team, not the role, and a data role
    # beside an actuarial function was cut as a credential gate. A sentence saying the
    # credential is a preference or not needed lifts it.
    head = title if title else text[:400]
    if (not lifted and DESIGNATED_TITLE.search(head)
            and len(DESIGNATED_TITLE.findall(text)) >= 3):
        return (title or head.split("\n")[0])[:200]
    return None


RESEARCH_ML_MIN = 3


def research_ml_flag(text):
    """(sentence, count) when research ML is the core of the role, else (None, 0).

    One mention is a nice-to-have on an applied role. Three or more distinct
    techniques means the job IS the research: a posting can name causal
    inference, treatment effects, bandits, policy learning, off-policy
    evaluation and uncertainty estimation, and a full application used to be
    written for it.
    """
    hits = {m.group(0).lower() for m in RESEARCH_ML.finditer(text)}
    if len(hits) < RESEARCH_ML_MIN:
        return None, 0
    for s in sentences(text):
        if RESEARCH_ML.search(s):
            return s[:200], len(hits)
    return None, 0


def _states_a_degree(sentence: str) -> bool:
    """Does this sentence name a degree as a qualification, not as a data-modelling term?

    Every degree word is read, the way tools/fit.py reads them: "master data" first
    does not hide "a Master's degree is required" later in the same sentence."""
    return any(not NOT_A_DEGREE.match(sentence, m.start()) for m in DEGREE.finditer(sentence))


# Under this a body is a snippet, not a posting: what it states is read, and
# the row is marked thin so nobody mistakes silence for a clean posting.
THIN = 400


# A requirement to live somewhere else, one of the hard cuts CLAUDE.md names: "must
# be based in one of our talent hub countries (US, UK, Spain, Kenya and Ghana)"
# passed at fit 91 for somebody who lives in none of them. A sentence that also
# names the home country is a list that includes them, and passes. The places
# are the profile's (search.py LOCATION, through tools/places.py).
RESIDE = re.compile(
    r"\b(?:must|need to|needs to|required to|have to)\s+(?:be\s+)?(?:based|located|resid\w*|"
    r"live|living)\s+(?:in|within)\b|\b(?:based|located|residing) in one of\b"
    r"|\bopen (?:only )?to (?:candidates|applicants|people) (?:based|located|residing|living) in\b"
    r"|\b(?:candidates|applicants) (?:must|should) (?:reside|be based|be located|live)\b", re.I)


# The same requirement in the words of who is hired rather than where they must
# live: "we only hire in the United States", "this role is remote within the US",
# "US residents only". Each passed for somebody living elsewhere. These name the
# place right beside the restriction, so they are read around the place itself,
# and only a country counts: a region ("EMEA") may take in the person's own.
# Between "only" and the place, only words about who is hired or where they are:
# "we only sell in the US" describes a market, not a requirement.
_HIRE_WORDS = (r"(?:able|to|can|be|hire|hiring|hires|employ\w*|recruit\w*|consider\w*|"
               r"accept\w*|candidates?|applicants?|people|those|individuals|residents|"
               r"located|based|living|open|available|eligible|currently|legally)")
_BEFORE_PLACE = re.compile(
    r"(?:\bonly\b(?:\s+" + _HIRE_WORDS + r"){0,4}\s+(?:in|from|within)"
    r"|\bremote\s+(?:with)?in"
    r"|\b(?:restricted|limited)\s+to(?:\s+(?:candidates|applicants|residents)\s+(?:in|of|from))?)"
    r"\s+(?:the\s+)?$", re.I)
_HOURS = re.compile(r"\s*(?:-\s*)?(?:time\s*zones?|timezones?|business hours|working hours|hours)\b",
                    re.I)
_AFTER_PLACE = re.compile(r"^\s*(?:-\s*)?(?:only\b|residents?\s+only\b|(?:residents|citizens)\b"
                          r"(?=[^.;]{0,30}\bonly\b)"
                          r"|based\s+(?:candidates|applicants|people|residents|hires)\s+only\b)",
                          re.I)


def _names_home(s: str) -> bool:
    """Does the sentence name the person's own country, region or metro as a place?

    A metro town counts only bare or followed by a home region or country:
    "Manchester, NH" and "Sale, Australia" are somewhere else. The home country counts
    by its code too ("remote within the US" for somebody in the US), whether or not the
    profile's own pattern lists the code.
    """
    low = s.lower()
    if _places.HOME_COUNTRY_RX.search(low) or _places.home_code_in(s):
        return True
    for r in _places.REGIONS:
        # A region's short code is read in capitals, like a country code: "on"
        # and "in" are words before they are provinces or states.
        if (re.search(r"(?<![A-Za-z])" + re.escape(r.upper()) + r"(?![A-Za-z])", s)
                if len(r) <= 3 else re.search(r"(?<!\w)" + re.escape(r) + r"(?!\w)", low)):
            return True
    for g in _places.METRO:
        for m in re.finditer(r"(?<!\w)" + re.escape(g) + r"(?!\w)", low):
            after = re.match(r"\s*,\s*([a-z][a-z .]{0,30}?)\s*(?=[,.;:)]|$)", low[m.end():])
            if not after or after.group(1).strip() in _places.REGIONS:
                return True
    return False


def _countries_named(s: str):
    """Every place in the sentence that is one country and not home, as matches."""
    for c in _places.OTHER_COUNTRIES:
        yield from re.finditer(r"(?<!\w)" + re.escape(c) + r"(?!\w)", s, re.I)
    for m in _places.COUNTRY_CODES.finditer(s):
        if not _places.code_is_home(m.group(0)):
            yield m


def _hours_after(s: str, m) -> bool:
    """Is the place followed by a time-zone or hours phrase? "remote within US time
    zones" and "based in a US time zone" ask for hours, not a home."""
    return bool(_HOURS.match(s[m.end():m.end() + 30]))


def _abroad_places(s: str) -> list:
    """The countries a sentence names that are not home, the way RESIDE reads them: the
    profile's other countries, the codes, and "the United States" or "the United
    Kingdom" written out; less any followed by a time-zone or hours phrase."""
    found = list(_countries_named(s)) + list(re.finditer(r"\b(?:united states|united kingdom)\b",
                                                         s, re.I))
    return [m for m in found if not _hours_after(s, m)]


def resides_abroad(s: str) -> bool:
    """Does this one sentence require the candidate to live in a country that is not theirs?"""
    reside = RESIDE.search(s)
    if not reside and not re.search(r"\bonly\b|\bremote\b|\brestricted\b|\blimited\b", s, re.I):
        return False
    if _names_home(s):
        return False
    # A region cuts only when it leaves home out: "based in EMEA" cut somebody in the
    # UK, which EMEA takes in. A list with a region that takes home in ("Europe or the
    # US") is a list that includes them; one the table cannot place is the location
    # gate's to flag, never a cut. A region or a country followed by "time zones" asks
    # for hours: "must be based in a US time zone" was cut as a requirement to live
    # abroad, because this branch returned before the hours were read.
    inside, _ = _places.region_takes_in_home(s, keep=lambda m: not _hours_after(s, m))
    if inside is True:
        return False
    if reside and (_abroad_places(s) or inside is False):
        return True
    for m in _countries_named(s):
        if _hours_after(s, m):
            continue
        if (_BEFORE_PLACE.search(s[max(0, m.start() - 60):m.start()])
                or _AFTER_PLACE.match(s[m.end():m.end() + 50])):
            return True
    return False


def residence_cut(text: str) -> str | None:
    """The sentence requiring the candidate to live in a country that is not theirs."""
    for s in sentences(text):
        if resides_abroad(s):
            return s[:220]
    return None


# What each cut says, and the search.py settings that decide it. The screen writes its
# reasons from these words, and two readers take them back: tools/exclude.py, for what
# a ruling rests on (`cut_settings`), and tools/throttle.py, for whether a ruling still
# cuts (`GATE_CUT_WORDS`) and the pay it quotes (`pay_cut_top`). Each kept its own copy
# of the wording, and they drifted: eligibility, internal-only and other-language
# rulings named no setting, so they rested on the whole rules and lapsed on any change
# to them, and a pay ruling in "C$" or "kr" quoted no figure anybody could read back.
CUTS = {
    "eligibility": (ELIGIBILITY_CUT_REASON,
                    ("ELIGIBILITY", "ENTITLED", "PERMIT_ACCEPTED", "ELIGIBILITY_STATUS_TERMS",
                     "ELIGIBILITY_NOT_BY_PERMIT", "ELIGIBILITY_ALWAYS")),
    "residence": ("eligibility gate: a requirement to live in another country", ("LOCATION",)),
    "internal_only": ("open to the employer's own staff only",
                      ("INTERNAL_ONLY", "INTERNAL_ONLY_TITLE")),
    "salary": ("stated range tops out at", ("SALARY_CUT_BELOW",)),
    "language": ("stated as a requirement", ("LANGUAGE_GATE", "LANGUAGES_HELD")),
    "title_language": ("job title is in", ("TITLE_LANGUAGE",)),
    "designation": ("professional designation stated as a requirement",
                    ("DESIGNATION", "DESIGNATED_TITLE")),
    "research_ml": ("research-grade ML is the core of the role", ("RESEARCH_ML",)),
}
PAY_CUT = "stated range tops out at {cur}{top:,}, below {cur}{line:,}"
_PAY_CUT_READ = re.compile(r"stated range tops out at \D{0,6}?(\d{1,3}(?:,\d{3})+|\d+), below\b")
_CUT_READ = {
    # The profile's own words, and the app's opening for them that older rulings carry.
    "eligibility": re.compile(re.escape(ELIGIBILITY_CUT_REASON) + r":"
                              r"|eligibility gate: (?!a requirement to live in another country)",
                              re.I),
    "salary": _PAY_CUT_READ,
    "title_language": re.compile(r"\bjob title is in \w+:", re.I),
}
_LANGUAGE_CUT = re.compile(r"([^:;\"]{1,60}?) stated as a requirement\b", re.I)
# Every cut but pay, which is judged against today's cut line rather than read as a
# verdict: what tools/throttle.py reads as a ruling that still cuts.
GATE_CUT_WORDS = re.compile("|".join(
    re.escape(words) for code, (words, _) in CUTS.items() if code not in ("salary", "language")),
    re.I)


def _language_cut(reason: str) -> bool:
    """Does the reason carry a language cut, in the words the screen wrote it?"""
    gated = tuple(str(g[0]).lower() for g in LANGUAGE_GATE)
    for m in _LANGUAGE_CUT.finditer(reason):
        what = m.group(1).strip().lower()
        if (gated and what.endswith(gated)) or OTHER_LANGUAGE.search(what):
            return True
    return False


def cut_settings(reason: str) -> list:
    """The search.py settings the screen's cuts in `reason` rest on, in its own words.

    Empty when the reason holds none of the screen's cuts."""
    text = str(reason or "")
    found = []
    for code, (words, names) in CUTS.items():
        read = _CUT_READ.get(code)
        hit = (_language_cut(text) if code == "language"
               else read.search(text) if read is not None
               else re.search(re.escape(words), text, re.I))
        if hit:
            found += names
    return list(dict.fromkeys(found))


# One cut as the screen writes it into a ruling, "<what>: "<the sentence it quotes>"", and
# several are joined with "; ".
_RULING_PART = re.compile(r'(?P<words>[^";]*?): "(?P<quote>.*?)"(?=;\s|\s*$)', re.S)


def _quoted_words(quote: str) -> str:
    """The quote `evidence()` wrote, less the "..." and the part-word at a cut end."""
    q = quote.strip()
    if q.startswith("..."):
        q = q[3:].split(None, 1)[1] if len(q[3:].split(None, 1)) > 1 else ""
    if q.endswith("..."):
        q = q[:-3].rsplit(None, 1)[0] if len(q[:-3].rsplit(None, 1)) > 1 else ""
    return q


def _language_refused(what: str, quote: str) -> bool:
    """Would today's screen refuse this language cut, on the sentence it quotes?

    False for anything but the second-language reading this re-judges: the profile's
    own language rows (LANGUAGE_GATE) are read as they always were. Only what changed
    is asked again, a preference word in the sentence and a cue beside the name, because
    both sit right beside the name the quote is centred on; the requirement word may
    sit further off than the quote reaches, and is not."""
    what = what.strip().lower()
    gated = tuple(str(g[0]).lower() for g in LANGUAGE_GATE)
    if not what or (gated and what.endswith(gated)) or not OTHER_LANGUAGE.search(what):
        return False
    q = _quoted_words(quote)
    return bool(q) and (_language_preferred(q) or other_language_named(q) is None)


def ruling_refused(reason: str) -> bool:
    """True when a ruling the screen wrote is one today's screen would not make.

    Every cut in the reason has to be one this re-judges, and today's screen has to
    refuse each one on the sentence the ruling quotes; any other cut, or any words the
    screen did not write, and the ruling stands. Re-judged: the second-language cut,
    which read a language named only as a nice-to-have ("Bilingual in Spanish is a plus")
    or a nationality word ("Spanish and Portuguese markets") as a requirement; and the
    requirement to live in another country, which read the person's own country written
    as a code ("remote within the US" for somebody in the US) and a time zone ("based in
    a US time zone") as somewhere to live. Those rulings were kept for good, resting on
    settings the person never changed; this lets
    tools/throttle.py ruled_out release them on the next round, with nobody asking, and
    the posting is screened again when a round finds it. A ruling today's screen makes
    is never refused here, so a posting is not fetched again round after round.
    """
    text = str(reason or "").strip()
    parts = list(_RULING_PART.finditer(text))
    ends = [0] + [p.end() for p in parts]
    starts = [p.start() for p in parts] + [len(text)]
    if not parts or any(not re.fullmatch(r"[;\s]*", text[a:b]) for a, b in zip(ends, starts)):
        return False
    for p in parts:
        words, quote = p.group("words").strip(), p.group("quote")
        if words.lower() == CUTS["residence"][0]:
            # The quote is the whole sentence when it is shorter than the 220 characters
            # the cut keeps; a longer one cannot be judged again from what is left.
            if len(quote) >= 220 or resides_abroad(quote):
                return False
        elif words.lower().endswith(CUTS["language"][0]):
            if not _language_refused(words[:-len(CUTS["language"][0])], quote):
                return False
        else:
            return False
    return True


def pay_cut_top(reason: str):
    """The top of the range a pay cut the screen wrote quotes, whatever the currency."""
    m = _PAY_CUT_READ.search(str(reason or ""))
    return int(m.group(1).replace(",", "")) if m else None


def screen(job: dict) -> dict:
    text = (job.get("desc") or "")
    cuts, flags = [], []
    # A short body used to skip every gate and pass as "thin". A snippet that
    # says "Active SC clearance required" or "Fluency in Welsh is essential" is
    # the whole bar in one line, and it went through to scoring and drafting.
    # So every gate reads what there is; the row is only marked thin.
    thin = len(text) < THIN
    if thin:
        flags.append("posting body too short to screen fully; gates read what there is")

    e = eligibility_cut(text)
    if e:
        cuts.append(f'{CUTS["eligibility"][0]}: "{e}"')
    else:
        w = residence_cut(text)
        if w:
            cuts.append(f'{CUTS["residence"][0]}: "{w}"')

    i = internal_only(job.get("title") or "", text)
    if i:
        cuts.append(f'{CUTS["internal_only"][0]}: "{i}"')

    hi, q = salary_max(text)
    if hi is not None and hi < ABSURD_SALARY:
        cuts.append(PAY_CUT.format(cur=CUR, top=hi, line=ABSURD_SALARY)
                    + f': a different job level, not a negotiation: "{q}"')
    elif hi is not None and hi < SALARY_FLOOR:
        flags.append(f'stated range tops out at {CUR}{hi:,}, under the {CUR}{SALARY_FLOOR:,} '
                     f'target; a decision input, never a cut, because a posted range '
                     f'is a starting position and is often stale: "{q}"')

    for lang, required, soft in LANGUAGE_GATE:
        for s in sentences(text):
            m = required.search(s)
            if m and not soft.search(s):
                cuts.append(f'{lang} {CUTS["language"][0]}: "{evidence(s, m)}"')
                break

    for s in sentences(text):
        m = other_language_cut(s)
        if m is not None:
            cuts.append(f'{m.group(0)} {CUTS["language"][0]}: "{evidence(s, m)}"')
            break

    # A title written in another language is that language's job: the whole
    # working language is that one, whatever the body says.
    title_lang = getattr(_S, "TITLE_LANGUAGE", None)
    head = (job.get("title") or "") + " " + text[:200]
    if title_lang and title_lang[1].search(head):
        cuts.append(f'{CUTS["title_language"][0]} {title_lang[0]}: '
                    f'"{(job.get("title") or head)[:120]}"')

    # Measured from the years held (see tools/fit.py), not from fixed numbers.
    n, q = stated_years(text)
    if n is not None and n - YEARS_HELD >= 2:
        flags.append(f'stated {n}+ years against roughly {YEARS_HELD} held; a stretch the scorer weighs, never a cut: "{q[:200]}"')
    elif n is not None and n - YEARS_HELD == 1:
        flags.append(f"stated {n} years; a stretch, not a bar")

    d = designation_cut(text, job.get("title") or "")
    if d:
        cuts.append(f'{CUTS["designation"][0]}: "{d}"')

    r, hits = research_ml_flag(text)
    if r:
        cuts.append(f'{CUTS["research_ml"][0]} ({hits}): "{r}"')

    for s in sentences(text) if getattr(_S, "DEGREE_FLAGS", True) else ():
        if not _states_a_degree(s) or PREFERRED.search(s):
            continue
        if ESCAPE.search(s):
            flags.append("graduate degree named, but the same sentence offers an equivalence route")
        elif under_minimum_qualifications(text, s):
            # This was once a CUT, added after a posting listed "Advanced degree
            # (Master's or Ph.D.)" under Minimum Qualifications and only got a
            # flag. It was reversed on a general
            # rule: a candidate who has everything else is not filtered out for
            # one missing item, and plenty of these postings hire without the
            # Master's.
            #
            # So it stays visible and the scorer decides: fit.py already docks
            # points for a stated graduate requirement, which demotes the role
            # without deleting it. The bar is real and it is not a wall.
            flags.append(f'advanced degree under a minimum-qualifications heading, '
                         f'with no equivalence route offered. Ranked down, not cut: '
                         f'apply anyway where the rest matches: "{s[:200]}"')
        elif re.search(r"required|must have|qualifications", s, re.I):
            flags.append(f'graduate degree stated as required: "{s[:200]}"')
        else:
            # A degree mentioned in passing ("many of our data scientists hold
            # advanced degrees") is not a requirement, so keep reading. The loop
            # used to stop at the first degree word whatever it said, and a
            # later "Minimum Qualifications: Master's ... required" was never
            # read.
            continue
        break

    return {**job, "text_screen": "cut" if cuts else ("thin" if thin else "pass"),
            "cuts": cuts, "flags": flags}


def load_jobs(path: str) -> list[dict]:
    data = json.load(open(path))
    return list(data.values()) if isinstance(data, dict) else list(data)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("infile")
    ap.add_argument("--out", help="survivors, for the next stage")
    ap.add_argument("--out-all", dest="out_all", help="every record with its verdict")
    ap.add_argument("--seen", default=None,
                    help="seen_jobs.json: record each cut there (tools/exclude.py), so the "
                         "next round drops it before hydrate fetches it again")
    ap.add_argument("--today", default="", help="YYYY-MM-DD for the record; defaults to today")
    a = ap.parse_args()
    jobs = load_jobs(a.infile)
    out = [screen(j) for j in jobs]
    keep = [j for j in out if j["text_screen"] != "cut"]
    cut = [j for j in out if j["text_screen"] == "cut"]
    # Every posting ruled out is written back, with its reason and what it rests
    # on, or each round fetched and screened the same cuts again. Cuts only: a
    # flag is a scoring input and never a ruling.
    recorded = 0
    if a.seen and cut:
        import exclude
        recorded = exclude.add_many(
            [{"url": j.get("url"), "reason": "; ".join(j["cuts"]), "title": j.get("title"),
              "company": j.get("company"), "location": j.get("location")} for j in cut],
            today=a.today, path=a.seen)
    # --out is what the next stage extracts, so it holds SURVIVORS only. It
    # used to hold every record tagged with its verdict, which meant a caller
    # that forgot to filter paid a model to re-read postings this stage had
    # already cut for free - exactly what used to happen. Use
    # --out-all when the cut records are wanted too (to record why).
    if a.out:
        json.dump(keep, open(a.out, "w"), indent=1)
    if a.out_all:
        json.dump(out, open(a.out_all, "w"), indent=1)
    for j in cut:
        print(f"CUT  {(j.get('company') or '')[:26]:26} {(j.get('title') or '')[:38]:38} {j['cuts'][0][:70]}")
    print(f"\n{len(jobs)} screened, {len(keep)} survive, {len(cut)} cut on a quoted stated fact "
          f"(0 model tokens)" + (f"; {recorded} recorded in {os.path.basename(a.seen)}"
                                 if a.seen else ""), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
