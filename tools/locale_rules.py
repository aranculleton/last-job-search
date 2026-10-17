#!/usr/bin/env python3
"""The document-language rules, read from the profile once, for every reader.

Four readers check that what a stranger reads follows the person's own conventions:
`check_claims.py` (a resume or letter, as LaTeX), `audit_letters.py` (the compiled
letter's text), `voice_check.py` (any text) and `network/tone.py` (a message). Each
carried its own copy of the rules, and the copies disagreed. check_claims knew four
spelling variants but flagged only the em dash, and only when banned_characters named
it. tone caught a dash typed as "--" and spared a signature delimiter, but knew only
Canadian and American spelling, so a British person's messages were never checked for
"behavior". voice_check banned both dashes whatever the profile said. A rule fixed in
one copy stayed broken in the other three.

This is the one copy. It reads person.json `documents` (spelling, noun, banned_nouns,
banned_characters) and the profile's claims.py LEGITIMATE_ISE once, at import, and the
four take their patterns from here.

    import locale_rules
    L = locale_rules.LOCALE                  # the person's
    L.dashes(text)                           # [(rule, index)], a separator line spared
    L.wrong_spellings(text)                  # [(variety, match)]: another variety's forms
    L.nouns                                  # [Noun(word, document, message)]
    locale_rules.for_documents({"spelling": "american"})    # anyone's, for a test
"""

from __future__ import annotations

import os
import re
import sys
from typing import NamedTuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import person  # noqa: E402

# Written as code points so the one file that bans these characters does not
# itself contain them, which is what the repo-wide check greps for.
EM_DASH = chr(0x2014)
EN_DASH = chr(0x2013)
DEFAULT_BANNED_CHARACTERS = (EM_DASH, EN_DASH)
# The rule each banned character is reported under. Any other character a profile
# bans is a "banned_character".
DASH_RULES = {EM_DASH: "em_dash", EN_DASH: "en_dash"}

# A typed em dash. Two or more hyphens between words is the same punctuation
# mark by another route, and rule 1 of 03-writing-style.md names it that way.
# Runs of three were missed while runs of two were caught, and a dash left
# hanging off a word ("quality-- the rest") was missed as well, which are the
# two forms a draft arrives in when the writer meant an em dash and the editor
# did not convert it. The lookarounds keep a command-line flag out of it:
# "--today" is preceded by a space and followed by a letter, which no
# alternative matches. In LaTeX "--" and "---" are how both dashes are typed,
# so the same pattern finds them in a resume's source.
TYPED_DASH = re.compile(
    r"(?<=\w)-{2,}(?=\w)|(?<=\w)-{2,}(?!\w)|(?<![-\w])-{2,}(?![-\w])")

# The other way LaTeX types them. A reader that strips commands before matching
# turns these into the characters first, or they vanish with the markup.
_LATEX_DASH = re.compile(r"\\text(em|en)dash\b(?:\{\})?")

# A line that is furniture rather than a sentence: "-- " alone on a line is the
# email signature separator every mail client writes, and flagging it told writers
# to delete punctuation they never typed. A Markdown table's rule line ("|---|:--|")
# is the same kind of thing, and a draft that carries a table was flagged once per
# column.
_FURNITURE = frozenset("-|:+ \t")
# A link is not prose either, and a LinkedIn profile id carries "--" as often
# as not.
_URL = re.compile(r"(?:https?://|www\.)\S+", re.I)


def latex_dashes(text: str) -> str:
    """\\textemdash and \\textendash as the characters they print."""
    return _LATEX_DASH.sub(lambda m: EM_DASH if m.group(1) == "em" else EN_DASH, text)


def separator_line(text: str, index: int) -> bool:
    """Is the hyphen run at `index` on a line of furniture rather than a dash?"""
    start = text.rfind("\n", 0, index) + 1
    end = text.find("\n", index)
    line = text[start:end if end != -1 else len(text)].strip()
    return "-" in line and set(line) <= _FURNITURE


def not_a_dash(text: str, index: int) -> bool:
    """Is the hyphen run at `index` furniture or part of a link, not punctuation?"""
    return separator_line(text, index) or any(
        m.start() <= index < m.end() for m in _URL.finditer(text))


# English words that end in -ise in EVERY variety, so they are never a spelling
# error. Without this list the -ise check fires on "enterprise-scale" and the
# whole report gets discounted.
LEGITIMATE_ISE = [
    "enterprise", "enterprises", "expertise", "fundraise", "fundraising", "precise", "concise", "comprise",
    "comprised", "comprises", "supervise", "supervised", "supervising", "advise",
    "advised", "advising", "otherwise", "likewise", "wise", "rise", "rises",
    "arise", "arises", "arising", "promise", "promised", "promises", "franchise",
    "merchandise", "surprise", "surprised", "exercise", "exercised", "exercises",
    "raise", "raised", "raises", "praise", "noise", "cruise", "devise", "devised",
    "revise", "revised", "revising", "disguise", "paradise", "compromise",
    "premise", "premises", "demise", "excise", "improvise", "televise", "chastise",
    "despise",
    # Words that merely CONTAIN "ising"/"ise" and are spelled the same in every
    # dialect. Each of these produced a false positive on a real document.
    "advertising", "advertise", "advertised", "merchandising", "franchising",
    "supervision", "revision", "provision", "division", "precision", "decision",
    # More words that end in -ise in every variety.
    "wise", "clockwise", "streetwise", "noise", "poise", "guise", "expertise",
    # -ising forms of the verbs above, and -ising words with no -izing form.
    # "comprising", "promising", "surprising" and "exercising" each fired on a
    # real document.
    "comprising", "promising", "surprising", "exercising", "compromising",
    "raising", "praising", "arising", "supervising", "revising", "devising",
    "improvising", "cruising", "disguising", "televising", "chastising",
    "despising", "advertising", "franchising", "merchandising", "uprising",
    "enterprising", "unsurprising", "unpromising", "poised", "advertised",
]
# Every -ise word above in its -ises form too, now that -ises is read: "supervises"
# and "advises" are spelled that way in every variety.
LEGITIMATE_ISE += sorted({w + "s" for w in LEGITIMATE_ISE if w.endswith("ise")}
                         - set(LEGITIMATE_ISE))

# The verbs whose -ise and -ize forms are both real words, so either spelling
# is a choice and the wrong one is a finding. A closed list on purpose: it is
# what an -ise variety checks a draft for, where an open "-ize" pattern would
# have to know every word like "size" and "prize" that has only the one form.
_ISE_STEMS = (r"organi|prioriti|optimi|recogni|speciali|standardi|summari|"
              r"apologi|reali|utili|minimi|maximi|emphasi|customi|personali|categori|"
              r"digiti|moderni|normali|visuali")

# `analy` is split out and deliberately does NOT take the `es` ending.
# "analyses" is the plural of the noun "analysis" in every variety of English,
# including American, and it is core vocabulary for an analyst: "sensitivity
# analyses" turns up in ordinary letters, and an early version of this rule
# flagged each one as a British spelling. The British verb form that would be
# a real finding ("the team analyses the data") is rarer in this corpus than
# the noun by a wide margin, so the false positive costs more than the miss.
_ANALYSE = r"\banalys(?:e|ed|ing|ation|ations)\b"
_ANALYZE = r"\banalyz(?:e|ed|es|ing)\b"

# Two British words an -ize variety does not keep, beside the spelling: "whilst"
# and "amongst" read as British to a North American reader, and so does
# "programme" for what they call a program.
_BRITISH_ONLY = r"\b(?:whilst|amongst|programmes?)\b"

# The forms each variety does not use. Canadian English keeps modelling,
# behaviour, centre and colour, so it is checked only for the American forms of
# those words; American English for the British ones; British and Australian
# English for the American ones and for -ize.
_AMERICAN_FORMS = r"behaviors?|behavioral|modeling|modelers?|centers?"
_AMERICAN_FORMS_WIDE = _AMERICAN_FORMS + r"|colors?|favors?"
_BRITISH_FORMS = r"behaviours?|behavioural|modelling|modellers?|centres?|colours?|favours?"

# spelling -> (the variety whose forms are flagged, pattern, why)
VARIANT_WORDS = {
    "canadian": ("american", r"\b(?:" + _AMERICAN_FORMS + r")\b",
                 "Canadian English keeps modelling, behaviour and centre. Use American "
                 "spelling only for a US posting, and then consistently throughout."),
    "american": ("british", r"\b(?:" + _BRITISH_FORMS + r")\b",
                 "American English: behavior, modeling, center, color, favor, analyze."),
    "british": ("american",
                r"\b(?:" + _AMERICAN_FORMS_WIDE + r")\b"
                r"|\b(?:" + _ISE_STEMS + r")z(?:e|es|ed|ing|ation|ations)\b|" + _ANALYZE,
                "British English: behaviour, modelling, centre, colour, favour, analyse, "
                "and -ise (organise, prioritise)."),
    "australian": ("american",
                   r"\b(?:" + _AMERICAN_FORMS_WIDE + r")\b"
                   r"|\b(?:" + _ISE_STEMS + r")z(?:e|es|ed|ing|ation|ations)\b|" + _ANALYZE,
                   "Australian English: behaviour, modelling, centre, colour, favour, "
                   "analyse, and -ise (organise, prioritise)."),
}

# The varieties that spell the -ise family -ize, and what to say when a draft
# does not.
IZE_SPELLINGS = {
    "canadian": "Canadian English uses -ize/-ization, analyze, while, among and program. "
                "(modelling, behaviour and centre keep their British forms and are not "
                "matched here.)",
    "american": "American English uses -ize/-ization, analyze, while, among and program.",
}


# The prefixes a word spelled -ise everywhere keeps that spelling under.
_PREFIX = r"un|im|in|non|pre|re|mis|over|under|semi|self"


def ise_pattern(legitimate=()) -> str:
    """The British forms an -ize variety does not keep, as one pattern.

    Only -ise words with a real -ize counterpart. Words spelled -ise in every
    variety (enterprise, expertise, precise, comprise, supervise, advise,
    otherwise, ...) are excluded, or the check fires on "enterprise-scale" in
    every resume and gets ignored. So are their prefixed forms ("unsupervised",
    "imprecise"): a prefix cannot give a word an -ize spelling it never had. So
    is every word ending in "wise" (pairwise, stepwise), none of which has a
    "-wize" form.
    """
    words = list(LEGITIMATE_ISE) + [w for w in legitimate if w not in LEGITIMATE_ISE]
    return (r"\b(?!(?:" + _PREFIX + r")?(?:" + "|".join(re.escape(w) for w in words)
            + r")\b)(?!\w*wise\b)"
            r"\w{4,}(?:ise|ises|ised|ising|isation|isations)\b"
            r"|" + _ANALYSE + r"|" + _BRITISH_ONLY)


class Noun(NamedTuple):
    """A banned document noun and the two ways it is looked for.

    `document` is every use: in a resume or a letter the word can only be the
    document, and in its filename (<Name>_CV_<Employer>.pdf) a word boundary does
    not separate it, so letters are what bound it. `message` is only where it is
    the document: "resume" is also a verb, and "happy to resume the conversation"
    is ordinary English in a message.
    """

    word: str
    document: re.Pattern
    message: re.Pattern


_DETERMINER = (r"my|the|a|an|your|our|their|his|her|updated|attached|full|current")


def noun(word: str) -> Noun:
    """The patterns for one banned noun."""
    if word.isupper():
        # An abbreviation is never a verb, so both are the word itself, plural
        # included, and in its own case: "cv" in a path is not the document.
        rx = re.compile(r"(?-i:(?<![A-Za-z])%ss?(?![A-Za-z]))" % re.escape(word))
        return Noun(word, rx, rx)
    w = re.escape(word)
    if word.lower() == "resume":
        w = w.replace("e", "[eé]")          # resume, résumé, resumé
    return Noun(word,
                re.compile(r"(?<![A-Za-z])(?:%s)(?![A-Za-z])" % w, re.I),
                re.compile(r"(?:\b(?:%s)\s+|_)(?:%s)s?(?![A-Za-z])" % (_DETERMINER, w), re.I))


class Locale:
    """The rules for one profile's `documents` settings."""

    def __init__(self, documents=None, legitimate_ise=()):
        doc = dict(documents or {})
        self.spelling = str(doc.get("spelling", "") or "").lower()
        self.noun = doc.get("noun", "resume")
        self.banned_nouns = list(doc.get("banned_nouns", []))
        self.banned_characters = tuple(doc.get("banned_characters", DEFAULT_BANNED_CHARACTERS))
        self.legitimate_ise = list(LEGITIMATE_ISE) + [
            w for w in legitimate_ise if w not in LEGITIMATE_ISE]
        self.nouns = [noun(n) for n in self.banned_nouns]

        chars = "".join(re.escape(c) for c in self.banned_characters)
        self._chars = re.compile("[%s]" % chars) if chars else None
        # A typed dash is an em dash by another route, so it is banned with it.
        self.typed_dashes = EM_DASH in self.banned_characters
        parts = (["[%s]" % chars] if chars else []) + (
            [TYPED_DASH.pattern] if self.typed_dashes else [])
        # Every banned dash as one pattern, for a reader that takes patterns
        # (check_claims). It spares nothing: in LaTeX a line of hyphens prints.
        self.dash_pattern = "|".join(parts) or None

        self.ise = (re.compile(ise_pattern(legitimate_ise), re.I)
                    if self.spelling in IZE_SPELLINGS else None)
        self.ise_why = IZE_SPELLINGS.get(self.spelling, "")
        variety, pat, why = VARIANT_WORDS.get(self.spelling, ("", None, ""))
        self.variant = re.compile(pat, re.I) if pat else None
        self.variant_of = variety
        self.variant_why = why

    def dashes(self, text: str) -> list:
        """(rule, index) for every banned dash, a typed one included.

        The characters first, then the typed runs, each in the order they appear.
        A run on a line of furniture (a signature delimiter, a table's rule line)
        or inside a link is not a dash and is spared.
        """
        text = text or ""
        out = []
        if self._chars is not None:
            out += [(DASH_RULES.get(m.group(0), "banned_character"), m.start())
                    for m in self._chars.finditer(text)]
        if self.typed_dashes:
            out += [("em_dash", m.start()) for m in TYPED_DASH.finditer(text)
                    if not not_a_dash(text, m.start())]
        return out

    def wrong_spellings(self, text: str, theirs: bool = False) -> list:
        """(variety, match) for every form the person's variety does not use.

        `variety` names whose spelling the match is: "british" for an -ise form in
        an -ize variety, "american" for "behavior" in a Canadian draft.

        `theirs=True` spares what is somebody else's and keeps its own spelling:
        a capitalised word in mid-sentence, which is a name, and words inside
        quotation marks, which are theirs. A message names the reader's
        employer, team and title in every line ("Xpertise Recruitment", "Risk
        Modeling Lead") and quotes what they wrote. A resume is not read that
        way: its skills line is title case ("Data Visualisation") and is not a
        name.
        """
        text = text or ""
        out = []
        if self.ise is not None:
            out += [("british", m) for m in self.ise.finditer(text)]
        if self.variant is not None:
            out += [(self.variant_of, m) for m in self.variant.finditer(text)]
        if theirs:
            out = [(v, m) for v, m in out if not (_named(text, m) or _quoted(text, m))]
        return out


def _named(text: str, m: re.Match) -> bool:
    """A capitalised word straight after a word or a comma: a name."""
    before = text[max(0, m.start() - 2):m.start()]
    return (m.group(0)[:1].isupper() and len(before) == 2 and before[1] in " \t"
            and (before[0].isalnum() or before[0] in ",;)'\""))


# Quotation marks, told from apostrophes: a single quote opens after a space or
# a bracket and closes before one, where "it's" and "Morgan's" have a letter on
# both sides.
_OPEN_SINGLE = re.compile(r"(?:^|(?<=[\s(\[]))['\u2018](?=\w)")
_CLOSE_SINGLE = re.compile(r"(?<=[\w.,!?])['\u2019](?=[\s.,;:!?)\]]|$)")


def _quoted(text: str, m: re.Match) -> bool:
    """Is the match inside quotation marks on its own line?"""
    start = text.rfind("\n", 0, m.start()) + 1
    before = text[start:m.start()]
    opened = sum(1 for q in _OPEN_SINGLE.finditer(text, start, m.end()) if q.start() < m.start())
    closed = sum(1 for q in _CLOSE_SINGLE.finditer(text, start, m.start()))
    return (before.count('"') % 2 == 1
            or before.count("\u201c") > before.count("\u201d")
            or opened > closed)


def for_documents(documents=None, legitimate_ise=()) -> Locale:
    """The rules for any `documents` settings. The person's are LOCALE."""
    return Locale(documents, legitimate_ise)


def _from_profile() -> Locale:
    # voice_check runs with no profile (a document for somebody else, the app's
    # own tests of it), so no profile is the defaults rather than an error.
    try:
        documents = person.get("documents", {})
    except person.NoProfile:
        return Locale()
    # A person's documents can carry proper nouns of their own that end in -ise
    # (a product an employer names, say); their claims.py lists them.
    extra = (getattr(person.module("claims"), "LEGITIMATE_ISE", [])
             if person.exists("claims.py") else [])
    return Locale(documents, list(extra))


LOCALE = _from_profile()
