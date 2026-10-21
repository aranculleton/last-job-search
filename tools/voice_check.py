#!/usr/bin/env python3
"""Catch the text that reads as machine-written, before a stranger reads it.

Why this is code and not another paragraph in 03-writing-style.md.

That file already bans cliches, and the ban works most of the time, which is
the problem. A rule a model is asked to follow is followed at whatever rate it
is followed at, and nothing measured the rate. This repo's own stated principle
is that a rule enforceable in Python gets enforced in Python, and the voice
rules were the largest set still living only in a prompt.

The cost of missing one is not cosmetic. A recruiter who has read forty
applications this week can spot a generated cover letter in a sentence, and the
moment they do, the reader stops asking whether the candidate is good and
starts asking whether the candidate wrote this. An outreach note that reads as generated
gets no reply, and a reply is the whole point of sending it.

What it looks for, in rough order of how badly each one gives the game away:

  cliche        "passionate about", "hit the ground running", "leverage my",
                "circle back": one list, PHRASES, which network/tone.py reads
                too, so a phrase added there is caught in a message and a
                letter alike
  ai-diction    "delve", "robust", "seamless", "tapestry", "landscape",
                "in today's fast-paced", "testament to"
  ai-shape      "not just X, but Y"; "It's not about X. It's about Y.";
                the three-item list where two would do; "From X to Y, ..."
  opener        "I hope this message finds you well"; "I am reaching out to";
                "As a <role> with <n> years of experience"
  enthusiasm    "thrilled", "excited to", "I would love the opportunity"
  hedge-stack   "I believe I could potentially help"
  em-dash       banned outright in this repo, and a reliable tell besides
  uniformity    every sentence the same length, which is what generated prose
                does and what a person almost never does

A list of words to avoid, written between QUOTED_OPEN and QUOTED_CLOSE, is skipped:
it quotes what not to say, and is nobody's prose.

`uniformity` is the only statistical check and the only one that can be wrong
about a human, so it needs a real sample and reports at a lower severity.

Usage:
    python3 tools/voice_check.py --text "..."
    python3 tools/voice_check.py cover_letters/<Prefix>_Cover_Letter_ACME.tex
    python3 tools/voice_check.py --json drafts.json
Exit 0 clean, 1 findings, 2 a bad invocation.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import locale_rules  # noqa: E402

# --------------------------------------------------------------- the phrases
#
# The phrases banned in anything a stranger reads, a message or a document. One
# list: network/tone.py reads it for every message, and the "cliche" rule below
# reads it for everything else, so a phrase added here is caught in both. It was
# two lists, and the phrases in both matched differently: this one caught "move
# the needle" but never "moved the needle", its "synergi" never matched
# "synergy" or "synergies", and its "leverage my" missed "leveraging my". Each
# phrase carries the inflections it actually appears in. What only a message
# does wrong (naming the reader's team as a "side", excusing their silence)
# stays in tone.py.
PHRASES: dict[str, re.Pattern] = {
    "moved the needle": re.compile(r"\bmov(?:e|es|ed|ing) the needle\b", re.I),
    # Padding only without a stated scale: see `padding` below.
    "at scale": re.compile(r"\bat scale\b", re.I),
    "resonates": re.compile(r"\bresonat(?:e|es|ed|ing)\b", re.I),
    "deep dive": re.compile(r"\bdeep[ -]div(?:e|es|ed|ing)\b", re.I),
    # The candidate leveraging their own skills. A message bans the word in
    # every form (tone.py); a letter restates the employer's own strategy, which
    # is often "a leader in leveraging data", so only this form is the tell.
    "leverage my": re.compile(r"\bleverag(?:e|es|ed|ing) my\b", re.I),
    "excited to share": re.compile(r"\bexcited to share\b", re.I),
    "circle back": re.compile(r"\bcircl(?:e|es|ed|ing) back\b", re.I),
    # Only the noun. "I'll reach out next week" is how people speak; "a reach
    # out", "the first reach-out" and "reachouts" are recruiter dialect.
    "reach out": re.compile(
        r"\b(?:a|an|the|this|that|my|your|our|their|another|first|second|initial|"
        r"cold|quick|last|next)\s+reach[ -]?out\b|\breach[ -]?outs\b|\breachout\b", re.I),
    "touch base": re.compile(r"\btouch(?:ing|ed)? base\b", re.I),
    "synergy": re.compile(r"\bsynerg(?:y|ies|istic|ise|ize)\b", re.I),
    "passionate about": re.compile(r"\bpassionate about\b", re.I),
    "hit the ground running": re.compile(r"\bhit the ground running\b", re.I),
    "think outside the box": re.compile(r"\bthink outside the box\b", re.I),
    "wear many hats": re.compile(r"\bwear many hats\b", re.I),
    "self-starter": re.compile(r"\bself[- ]starter\b", re.I),
    "team player": re.compile(r"\bteam player\b", re.I),
    "go-getter": re.compile(r"\bgo[- ]getter\b", re.I),
    "results-driven": re.compile(r"\bresults[- ]driven\b", re.I),
    "proven track record": re.compile(r"\bproven track record\b", re.I),
    "drive results": re.compile(r"\bdrive results\b", re.I),
    "value-add": re.compile(r"\bvalue[- ]add\b", re.I),
    "low-hanging fruit": re.compile(r"\blow[- ]hanging fruit\b", re.I),
    "best of both worlds": re.compile(r"\bbest of both worlds\b", re.I),
    "at the end of the day": re.compile(r"\bat the end of the day\b", re.I),
}

# Boundaries for locating the sentence a match sits in: offsets, not tidy
# sentences.
_SENT_BOUND = re.compile(r"[.!?\n]")


def _sentence_around(text: str, index: int) -> str:
    """The run of text between the nearest sentence boundaries either side.

    By offset, not by searching for the phrase. Resolving the sentence by
    looking up the matched words found whichever sentence used them first, so a
    message that wrote the honest "at scale across 60M records" above the
    padded "we also work at scale" cleared both on the first sentence's digit
    and the padding shipped unflagged.
    """
    start = 0
    for m in _SENT_BOUND.finditer(text, 0, index):
        start = m.end()
    end = _SENT_BOUND.search(text, index)
    return text[start:end.start() if end else len(text)]


def padding(text: str, match: re.Match) -> bool:
    """"At scale" earns its place only when the scale is stated.

    "2.5M records at scale" is a fact with a number attached. "building pipelines
    at scale" is the same sentence with the claim removed, which is why it reads
    as filler. A digit anywhere in the sentence is the cheap, checkable proxy.
    """
    return not re.search(r"\d", _sentence_around(text, match.start()))


def banned_phrases(text: str) -> list[tuple[str, re.Match]]:
    """(phrase, match) for every banned phrase in `text`, in PHRASES order."""
    out = []
    for name, pattern in PHRASES.items():
        for m in pattern.finditer(text or ""):
            if name == "at scale" and not padding(text, m):
                continue
            out.append((name, m))
    return out

# --------------------------------------------------------------- the rules
#
# Each entry is (id, severity, compiled pattern, what to do instead). Severity
# "hard" is never acceptable in anything an employer or a contact reads;
# "soft" is a smell worth a second look.

RULES: list[tuple[str, str, re.Pattern, str]] = [
    # ---- outright cliche -------------------------------------------------
    ("cliche-fit", "hard", re.compile(
        r"\b(I (?:believe I|am confident I|know I) would be (?:a )?(?:great|"
        r"perfect|excellent|strong) fit|I am the ideal candidate|"
        r"my (?:unique )?(?:blend|combination) of)\b", re.I),
     "let the evidence make the claim; asserting fit is what everyone does"),

    # ---- diction that reads as generated in 2026 -------------------------
    ("ai-diction", "hard", re.compile(
        r"\b(delve|delving|robust solutions?|"
        r"seamless(?:ly)?|tapestry|myriad|plethora|"
        r"in today'?s (?:fast[- ]paced|ever[- ]evolving|dynamic|competitive)|"
        r"ever[- ]evolving|testament to|underscores? the|"
        r"pivotal role|crucial role|it'?s worth noting|"
        r"cutting[- ]edge|state[- ]of[- ]the[- ]art|game[- ]?changer|"
        r"unlock(?:ing)? (?:the )?(?:potential|value)|"
        r"harness(?:ing)? the power)\b", re.I),
     "plain words; none of these survive a recruiter's eye in 2026"),

    ("ai-shape-notjust", "hard", re.compile(
        r"\bnot (?:just|only|merely|simply)\b[^.!?]{2,70}?\bbut\b", re.I),
     "drop the setup and state the point once"),

    ("ai-shape-itsabout", "hard", re.compile(
        r"\b(?:it'?s|this is) not (?:just )?about\b[^.!?]{2,60}[.!?]\s*"
        r"(?:it'?s|this is) about\b", re.I),
     "the reversal construction is the single clearest tell"),

    ("ai-shape-fromto", "soft", re.compile(
        r"(?:^|[.!?]\s)From [a-z][^,.]{3,40} to [a-z][^,.]{3,40},\s", re.M),
     "the sweeping 'From X to Y' opener reads as filler"),

    # ---- openers ---------------------------------------------------------
    ("opener-hope", "hard", re.compile(
        r"\bI hope (?:this (?:message|email|note) finds you well|you'?re well|"
        r"you are (?:doing )?well)\b", re.I),
     "open on the reason for writing"),

    ("opener-reaching-out", "hard", re.compile(
        r"\bI(?:'m| am) (?:reaching out|writing to you) (?:to|because|regarding)\b", re.I),
     "say the thing instead of announcing that you are about to"),

    ("opener-as-a", "soft", re.compile(
        r"(?:^|[.!?]\s)As an? [A-Za-z ]{3,40} with \d+\+? years?\b", re.I),
     "a resume header sentence; lead on what you did"),

    # ---- enthusiasm ------------------------------------------------------
    ("enthusiasm", "hard", re.compile(
        r"\b(thrilled|delighted to|I would love the (?:opportunity|chance)|"
        r"excited (?:to|about|by) the (?:opportunity|prospect|chance)|"
        r"eager to contribute|keen to contribute)\b", re.I),
     "interest shows in what you noticed about them, not in adjectives"),

    # ---- the house style, which is a tell of a different kind -----------
    #
    # Neither phrase is bad on its own, and that is exactly why they survived.
    # A corpus pass over a few dozen letters and outreach notes found "would
    # welcome the chance" and "What I would bring" in nearly half of them.
    # A recruiter reads one letter and notices nothing; an agency, or a company
    # posting three roles, reads two and sees a form letter with the nouns
    # swapped. `--corpus` is what found these, and it is how the next ones get
    # found: the rule below only pins the two already known.
    ("house-style", "hard", re.compile(
        r"\b(would welcome (the (chance|opportunity)|a conversation)|"
        r"what I would bring|is the same (shape|mechanic|pattern)|"
        r"is where I have done|hiring team,? I am applying for|"
        # The outreach half, measured the same way over network_threads.csv:
        # most logged messages open "hope you're well" and most close on some
        # form of "would love to". The enthusiasm rule below catches only
        # "I would love the opportunity", so every other shape of it went
        # through, including the composer's own default close.
        r"hope you'?re well|hope you are well|"
        # The same opener in other clothes. A follow-up pack composed "Hi
        # <name>, hope the week has been a good one" and it passed, because
        # only the literal "you're well" was pinned.
        r"hope (?:the|your) (?:week|weekend|day|morning)\b[^.!?]{0,30}|"
        r"hope (?:all is|all's|everything is) well|hope you had a (?:good|great|nice)|"
        r"(would|I'?d) love (to|a\b)|love to connect)\b", re.I),
     "a stock phrase that recurs from letter to letter; say this one "
     "differently or cut it"),

    # ---- hedging ---------------------------------------------------------
    ("hedge-stack", "soft", re.compile(
        r"\b(?:I (?:believe|think|feel)|perhaps|possibly)\b[^.!?]{0,50}"
        r"\b(?:could|might|may|potentially)\b", re.I),
     "two hedges in one clause reads as apologising for writing"),

    # ---- typography ------------------------------------------------------
    # The characters the profile bans (documents.banned_characters, both
    # dashes unless it says otherwise) and the dash typed as "--".
    ("em-dash", "hard", re.compile(locale_rules.LOCALE.dash_pattern or r"(?!x)x"),
     "banned repo-wide, and a reliable tell; use a comma or a full stop"),

    ("rule-of-three", "soft", re.compile(
        r"\b\w+(?:,\s\w+){1},\s(?:and|or)\s\w+\b[^.!?]{0,20}[.!?]"
        r"[^.!?]{0,80}?\b\w+(?:,\s\w+){1},\s(?:and|or)\s\w+\b", re.I),
     "two tricolons close together is a rhythm people notice"),
]

# A body this short is a connection note, where uniformity means nothing.
UNIFORMITY_MIN_SENTENCES = 5
# Standard deviation of sentence length, in words, below which prose reads as
# machine-even. Human writing varies a lot more than people expect.
UNIFORMITY_STDEV = 3.5

_TEX = re.compile(r"\\[a-zA-Z]+\s*(?:\[[^\]]*\])?\s*\{([^{}]*)\}")
_SENT = re.compile(r"(?<=[.!?])\s+")


def plain(text: str) -> str:
    """Strip LaTeX down to what the reader actually reads.

    The preamble and the comment lines go first. They are not prose, and
    leaving them in both adds noise to the pattern matches and skews the
    uniformity reading with fragments that are not sentences.
    """
    text = text or ""
    # Only treat the input as LaTeX when it actually is. `%` starts a comment
    # in LaTeX and a literal percent is written `\%`, so stripping to end of
    # line is right there and catastrophic anywhere else: on plain prose it
    # silently deletes everything after the first percent sign, which is most
    # of the sentence a metric appears in. Caught by feeding a plain-text
    # string to check_numbers and watching "a 12% lift in orders" arrive as
    # "a 12".
    is_latex = bool(re.search(r"\\[a-zA-Z]+", text))
    if is_latex:
        body = re.split(r"\\begin\{document\}", text, maxsplit=1)
        text = body[1] if len(body) > 1 else text
        text = re.sub(r"(?<!\\)%.*", "", text)
        text = locale_rules.latex_dashes(text)
    prev = None
    while prev != text:
        prev = text
        text = _TEX.sub(r"\1", text)
    text = re.sub(r"\\[a-zA-Z]+", " ", text)
    text = text.replace("\\%", "%").replace("\\&", "&").replace("\\$", "$")
    text = re.sub(r"[{}]", "", text)
    return re.sub(r"[ \t]+", " ", text)


def sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT.split(text) if s.strip()]


def uniformity(text: str) -> tuple[float | None, int]:
    """(stdev of sentence length in words, n). (None, n) when too short."""
    lens = [len(s.split()) for s in sentences(text) if len(s.split()) > 2]
    if len(lens) < UNIFORMITY_MIN_SENTENCES:
        return None, len(lens)
    return statistics.pstdev(lens), len(lens)


# A list of words to avoid, quoted in a document so the person knows not to say them (an
# interview pack's "Do not say"), is wrapped in these and never read as the person's own
# words: read as prose, the pack's own list came back as seven hard findings, so a pack
# that carried one could never come back clean.
QUOTED_OPEN = "<!-- quoted: words to avoid, not to say -->"
QUOTED_CLOSE = "<!-- /quoted -->"
_QUOTED = re.compile(r"<!--\s*quoted\b.*?-->.*?<!--\s*/quoted\s*-->", re.S)


def unquoted(text: str) -> str:
    """`text` without its quoted lists of words to avoid."""
    return _QUOTED.sub(" ", text or "")


# An HTML comment is never shown and never read: the marks the tools write in their own
# files (an interview pack's `<!-- stages: Recruiter screen; Technical interview -->`, a
# `<!-- claude-surface: <id> -->` block). Read as prose, the pack's stage line came back
# as two em-dash findings for its own "<!--" and "-->" (2026-10-19). Taken out after the
# quoted lists, whose markers are comments too.
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)


def uncommented(text: str) -> str:
    """`text` without its HTML comments, each left as a line break."""
    return _HTML_COMMENT.sub("\n", text or "")


def check(text: str, *, source: str = "") -> list[dict]:
    """Every finding in `text`. Empty list means it reads as written by a person."""
    body = plain(uncommented(unquoted(text or "")))
    out: list[dict] = []
    for _, m in banned_phrases(body):
        start = max(0, m.start() - 40)
        out.append({
            "source": source,
            "rule": "cliche",
            "severity": "hard",
            "match": m.group(0).strip()[:80],
            "context": body[start:m.end() + 40].strip()[:160],
            "fix": "say the specific thing that phrase is standing in for",
        })
    for rid, severity, pat, fix in RULES:
        for m in pat.finditer(body):
            # A signature delimiter, a table's rule line or a link is not a dash.
            if (rid == "em-dash" and m.group(0).startswith("-")
                    and locale_rules.not_a_dash(body, m.start())):
                continue
            start = max(0, m.start() - 40)
            out.append({
                "source": source,
                "rule": rid,
                "severity": severity,
                "match": m.group(0).strip()[:80],
                "context": body[start:m.end() + 40].strip()[:160],
                "fix": fix,
            })
    # The person's own: a phrase they have said never to use is a hard finding
    # in a letter or a CV as much as in a message (tools/learned.py).
    try:
        import learned
        for hit in learned.dislikes(body):
            out.append({"source": source, "rule": "person-dislikes", "severity": "hard",
                        "match": hit[:80], "context": "",
                        "fix": "they have said never to use this; say it their way "
                               "(python3 tools/learned.py brief)"})
    except ImportError:
        pass
    sd, n = uniformity(body)
    if sd is not None and sd < UNIFORMITY_STDEV:
        out.append({
            "source": source,
            "rule": "uniformity",
            "severity": "soft",
            "match": f"stdev {sd:.1f} words over {n} sentences",
            "context": "",
            "fix": "vary the sentence lengths; a short one after two long ones "
                   "is what a person writes and a generator does not",
        })
    return out


# The one rule a caller may lift. The house style is about a phrase recurring
# from document to document, so a phrase of the person's own (networking.py
# OWN_VOICE in a first note) or a light "hope" inside a live thread can share
# it. A cliche, a dash, or a phrase the person has said never to use is never
# lifted, whatever `allow` matches.
# ------------------------------------------------------------ said aloud

# An answer the person will say out loud is held to the spoken register, not the
# written one. A prep printed the resume summary as the answer to "tell me about
# yourself" ("Data professional with a background in ... Builds risk-scoring models
# ..."), and a person said the answers read as "weird short sentences or things that
# start with 'At this', hard to say out loud". Three things mark written register in
# an answer: no "I" in its opening (third person, or a resume line), a sentence that
# opens on a verb with no subject ("Built ...", "Led ..."), and an opener that is a
# label with a colon ("At <Employer>: ...").
_FIRST_PERSON_WORD = re.compile(r"\b(?:i|i'm|i've|i'd|i'll|me|my|we|we're|we've|our)\b", re.I)
_RESUME_VERB = re.compile(
    r"^(?:built|builds|led|leads|designed|designs|delivered|delivers|owned|owns|created|"
    r"creates|developed|develops|managed|manages|drove|drives|launched|launches|reduced|"
    r"reduces|improved|improves|cut|cuts|ran|runs|engineered|engineers|implemented|"
    r"implements|analy[sz]ed|analy[sz]es|automated|automates|established|spearheaded|"
    r"oversaw|oversees|introduced|grew|grows|increased|partnered|partners|presented|"
    r"presents|supported|supports|identified|validated|validates|onboarded|migrated|"
    r"rebuilt|mapped|maps|wrote|writes|shipped|ships|scaled|scales)\b"
    # "Works in Python" is a resume line; "Works for me" is an answer.
    r"|^(?:works|worked)\s+(?:in|with|on|at|across|as)\b"
    # A resume's adjective openers, only as a resume uses them: "Comfortable with SQL" is
    # written, and "Comfortable, yes." is how someone answers.
    r"|^(?:comfortable|experienced|skilled|passionate|proficient)\s+(?:with|in|at|about|"
    r"working)\b", re.I)
# An answer this short ("One month.", "Manchester, by the canal.") is said as it stands,
# with or without an "I" in it.
SPOKEN_SHORT_WORDS = 15
# A headline about the person in the third person, however short: "Senior operations analyst
# with seven years in logistics."
_HEADLINE = re.compile(r"^(?:[A-Z][\w-]*\s+){0,4}(?:analyst|engineer|scientist|professional|"
                       r"consultant|manager|specialist|leader|developer|architect|economist)s?\b"
                       r"[^.]{0,80}\bwith\b", re.I)
_LABEL_OPENER = re.compile(r"^(?:at|in|for|with|on|from)\s+[^.:!?]{1,40}:\s", re.I)


def spoken_findings(answer: str) -> list[str]:
    """Why an answer reads as written rather than said, or [] when it reads as said."""
    text = " ".join(str(answer or "").split())
    if not text:
        return ["empty"]
    out = []
    sents = [x for x in sentences(text) if x.strip()]
    # A clause after a semicolon opens like a sentence: "I'm an analyst; spearheaded ...".
    clauses = [c.strip() for x in sents for c in x.split(";") if c.strip()]
    # A spoken answer often opens on a short framing line ("Two things. First, the scale.
    # Second, I ..."): first person anywhere in its first three sentences is said as said.
    if not _FIRST_PERSON_WORD.search(" ".join(sents[:3]) or text) and (
            len(text.split()) >= SPOKEN_SHORT_WORDS or _HEADLINE.match(text)):
        out.append("not in the first person: say it as \"I ...\"")
    verbs = [x for x in clauses if _RESUME_VERB.match(x.strip())]
    if verbs:
        out.append("opens a sentence the way a resume line does, with no \"I\": \"%s\""
                   % verbs[0][:60])
    labels = [x for x in sents if _LABEL_OPENER.match(x.strip())]
    if labels:
        out.append("opens on a label and a colon: \"%s\"; say it as a sentence" % labels[0][:60])
    return out


# Two things the register test cannot see without the question. An answer far longer than
# the moment allows reads well and is cut off when said: people speak at about 150 words a
# minute (a rule of thumb, not a measurement), a screen answer has about 60 to 90 seconds and
# a story in a later round about two minutes, and it is flagged once it would run past that
# by a quarter again. And "we" counted as first person above, so an answer that said "we"
# throughout passed, where the question asked what the person did and "we" is exactly what
# hides it: for those questions, "I" is the test.
SPOKEN_WPM = 150
SCREEN_SECONDS = 90
ANSWER_SECONDS = 120
LONG_FACTOR = 1.25
OWN_WE_MIN = 3
_I_WORD = re.compile(r"\b(?:i|i'm|i've|i'd|i'll|me|my|mine|myself)\b", re.I)
_WE_WORD = re.compile(r"\b(?:we|we're|we've|we'd|we'll|us|our|ours|ourselves)\b", re.I)
_WHAT_YOU_DID = re.compile(
    r"\b(?:a time (?:when )?you|give (?:me )?an example|an example of (?:a time|when)|"
    r"describe a (?:time|situation|project|moment)|what did you (?:do|build|change|own|decide|"
    r"learn)|what was your (?:role|part|contribution)|how did you\b|walk me through (?:a|the|"
    r"your) (?:project|piece of work|model|analysis)|tell me about (?:a|your|the) (?:project|"
    r"model|analysis|piece of work)|a project (?:in|end to end)|you (?:led|built|owned|delivered|"
    r"ran|changed)\b|your (?:own )?experience (?:with|of|in))", re.I)


def asks_what_you_did(question: str) -> bool:
    """Does the question ask what the person did, not what a team did or what they think?"""
    return bool(_WHAT_YOU_DID.search(str(question or "").replace("’", "'")))


def answer_findings(answer: str, question: str = "", seconds: int = 0) -> list[str]:
    """Why an answer to `question` is not ready to say in the `seconds` it has, beyond the
    register (spoken_findings): far too long to say in its time, or "we" where they asked
    what you did. [] when neither."""
    text = " ".join(str(answer or "").replace("’", "'").split())
    words = len(text.split())
    out = []
    if seconds and words > SPOKEN_WPM * seconds / 60 * LONG_FACTOR:
        said = round(words * 60 / SPOKEN_WPM / 10) * 10
        out.append("about %d seconds said aloud (%d words at about %d a minute), where an answer "
                   "here has about %d: cut it to about %d words" % (
                       said, words, SPOKEN_WPM, seconds, SPOKEN_WPM * seconds // 60))
    if question and asks_what_you_did(question):
        mine, ours = len(_I_WORD.findall(text)), len(_WE_WORD.findall(text))
        opening = " ".join(sentences(text)[:3]) or text
        if ours and (ours >= OWN_WE_MIN and ours > mine or not _I_WORD.search(opening)
                     and words >= SPOKEN_SHORT_WORDS):
            out.append("says \"we\" %d time(s) and \"I\" %d where they asked what you did: say "
                       "what you did, as \"I\", and name the team once" % (ours, mine))
    return out


ALLOWABLE = frozenset({"house-style"})


def hard(text: str, allow: re.Pattern | None = None) -> list[dict]:
    """The hard findings in `text`: what a composer refuses a message on.

    Soft findings are dropped. `uniformity` is a statistical read that needs a
    real sample and a connection note is four short sentences by design, so
    every one of them trips it, and a checker that always fires is a checker
    nobody reads.

    `allow` is a compiled pattern, matched against the start of a finding's
    match: a house-style finding it matches is not returned.
    """
    return [f for f in check(text) if f["severity"] == "hard"
            and not (allow is not None and f["rule"] in ALLOWABLE
                     and allow.match(f["match"]))]


# --------------------------------------------------------------- the corpus
#
# Everything above reads one document and asks whether a machine wrote it.
# This reads all of them and asks a different question: whether the same
# machine wrote all of them the same way.
#
# It is the check that found the house style. Each letter is individually
# clean, specific and well evidenced, and dozens of them close on "I would
# welcome the chance to discuss the role". Nothing reading one document could
# see that, which is why nothing did.

CORPUS_MIN_N, CORPUS_MAX_N = 4, 8
# A phrase in this share of the corpus is a template, not a choice.
CORPUS_SHARE = 0.15
CORPUS_MIN_DOCS = 4

_PROPER = re.compile(r"\d|\b[A-Z][a-z]{2,}")


_SALUTATION = re.compile(r"^\s*(dear|hi|hello)\b[^,\n]{0,60},?\s*", re.I)
_LETTERCONTENT = re.compile(r"\\lettercontent\s*\{", re.I)
_ITEM = re.compile(r"\\item\s+([^\\]+)")


def _balanced(text: str, open_at: int) -> str:
    """The contents of the brace group starting at `open_at`."""
    depth, i = 0, open_at
    while i < len(text):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[open_at + 1:i]
        i += 1
    return text[open_at + 1:]


_NOTE = re.compile(r"^---[ \t]*\n(.*?)\n---[ \t]*$", re.S | re.M)


def prose(text: str) -> str:
    """Only the sentences a reader reads, for a corpus pass.

    A first run reported the letterhead: the email address, the LinkedIn URL
    and "flushright regards flushright document" were in nearly every
    document, which is true and useless. Boilerplate is SUPPOSED to be identical. What
    is being looked for is the writing, so for a LaTeX letter this keeps the
    `\\lettercontent` blocks and the list items and drops everything else.
    Anything that is not a LaTeX letter is returned as it is.
    """
    if "\\lettercontent" not in text:
        # An outreach.md: the note is what sits between its two `---` rules.
        # The instructions around it ("Send on LinkedIn to the hiring manager
        # or the recruiter named on the posting...") are in every file by
        # design, and read as the notes' own phrasing they took most of the top
        # rows of the report.
        m = _NOTE.search(text)
        return plain(m.group(1) if m else text)
    # In document order, so the LAST sentence is the closing paragraph and not
    # whichever bullet happened to be appended after it.
    pieces: list[tuple[int, str]] = []
    for m in _LETTERCONTENT.finditer(text):
        pieces.append((m.start(), _balanced(text, m.end() - 1)))
    for m in _ITEM.finditer(text):
        pieces.append((m.start(), m.group(1)))
    pieces.sort()
    return plain("\n".join(p for _, p in pieces))


def phrases(text: str) -> set[str]:
    """Every 4-to-8 word phrase in a document, lowercased, once each.

    Proper nouns and numbers are dropped, because an employer name and a
    metric are SUPPOSED to repeat: "at <employer> I forecast demand across
    1,200 SKUs in SQL and Python" is the candidate's experience, and it
    appearing in many letters is the system working. What must not repeat is the connective
    tissue around it.
    """
    out: set[str] = set()
    for sentence in sentences(text):
        if _PROPER.search(sentence):
            words = [w for w in re.findall(r"[A-Za-z']+", sentence)
                     if not w[0].isupper() or w.lower() in _STOP]
        else:
            words = re.findall(r"[A-Za-z']+", sentence)
        low = [w.lower() for w in words]
        for n in range(CORPUS_MIN_N, CORPUS_MAX_N + 1):
            for i in range(len(low) - n + 1):
                out.add(" ".join(low[i:i + n]))
    return out


_STOP = {"i", "a", "the", "and", "at", "in", "on", "of", "to", "for", "it",
         "that", "this", "with", "is", "was", "as", "my", "what", "where",
         "when", "which", "they", "their", "so", "but", "if", "an", "he"}


def corpus(paths: list[str]) -> list[tuple[int, str]]:
    """Phrases shared by too many documents, longest and commonest first."""
    from collections import Counter
    seen: Counter = Counter()
    docs = 0
    for path in paths:
        try:
            with open(path, encoding="utf-8") as fh:
                body = prose(fh.read())
        except OSError:
            continue
        docs += 1
        seen.update(phrases(body))
    if docs < CORPUS_MIN_DOCS:
        return []
    floor = max(CORPUS_MIN_DOCS, int(docs * CORPUS_SHARE))
    hits = [(n, p) for p, n in seen.items() if n >= floor]
    # Keep the longest form of any phrase, so one template reports once
    # instead of once per sub-phrase.
    hits.sort(key=lambda x: (-len(x[1].split()), -x[0]))
    kept: list[tuple[int, str]] = []
    for n, phrase in hits:
        if not any(phrase in longer and n <= m for m, longer in kept):
            kept.append((n, phrase))
    kept.sort(key=lambda x: -x[0])
    return kept


def end_key(sentence: str) -> str:
    """How rule 9 compares an opening or a closing: its first eight words, lower case."""
    return " ".join(str(sentence or "").split()[:8]).lower()


def ends_of(text: str) -> tuple[str, str]:
    """(opening, closing) of one document, as the corpus counts them, or ("", "").

    The salutation carries the employer's name, which differs by construction and
    would make every opener look unique, so it is dropped and the sentence that
    actually starts the letter is compared. Sentences under four words are not
    an opening or a closing.
    """
    body = _SALUTATION.sub("", prose(text or ""), count=1).lstrip()
    ss = [s for s in sentences(body) if len(s.split()) >= 4]
    if not ss:
        return "", ""
    return end_key(ss[0]), end_key(ss[-1])


def _ends(paths: list[str]) -> tuple[list, list]:
    """How the documents open and how they close, counted.

    The clearest view in the whole check. The middle of a letter is about the
    job and differs because the jobs differ. The first sentence and the last
    are where a template shows, and where a recruiter looks first.
    """
    from collections import Counter
    first: Counter = Counter()
    last: Counter = Counter()
    for path in paths:
        try:
            with open(path, encoding="utf-8") as fh:
                opening, closing = ends_of(fh.read())
        except OSError:
            continue
        if not opening:
            continue
        first[opening] += 1
        last[closing] += 1
    return first.most_common(6), last.most_common(6)


def corpus_report(paths: list[str]) -> str:
    docs = len(paths)
    hits = corpus(paths)
    floor = max(CORPUS_MIN_DOCS, int(docs * CORPUS_SHARE))
    lines = ["voice_check --corpus: %d documents" % docs, ""]

    opens, closes = _ends(paths)
    if opens:
        lines += ["HOW THEY OPEN", ""]
        lines += ["  %4d/%d  %r..." % (n, docs, s) for s, n in opens]
        lines += ["", "HOW THEY CLOSE", ""]
        lines += ["  %4d/%d  ...%r" % (n, docs, s) for s, n in closes]
        lines += [""]

    if not hits:
        lines.append("No phrase is shared by %d or more of them." % floor)
        return "\n".join(lines)

    lines += ["SHARED PHRASING, %d documents or more" % floor, "",
              "  Two kinds show up here and they need opposite treatment.",
              "  A phrase carrying one of the candidate's own facts SHOULD repeat:",
              "  a headline metric, a named result. That is the",
              "  profile doing its job. Everything else is connective tissue, and",
              "  connective tissue in half the letters is a form letter with the",
              "  nouns swapped.",
              ""]
    for n, phrase in hits[:25]:
        lines.append("  %4d/%d  %r" % (n, docs, phrase))
    return "\n".join(lines)


def report(findings: list[dict]) -> str:
    if not findings:
        return "voice_check: clean"
    hard = [f for f in findings if f["severity"] == "hard"]
    lines = [f"voice_check: {len(findings)} finding(s), {len(hard)} hard"]
    for f in findings:
        where = f" [{f['source']}]" if f["source"] else ""
        lines.append(f"  {f['severity'].upper():4} {f['rule']}{where}: "
                     f"{f['match']!r}")
        if f["context"]:
            lines.append(f"       ...{f['context']}...")
        lines.append(f"       -> {f['fix']}")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("paths", nargs="*", help=".tex or .md files to read")
    ap.add_argument("--text", help="check a literal string instead")
    ap.add_argument("--json", dest="json_in",
                    help="a drafts.json; every string value is checked")
    ap.add_argument("--soft-ok", action="store_true",
                    help="exit 0 when only soft findings were made")
    ap.add_argument("--corpus", action="store_true",
                    help="read PATHS together and report the phrasing they share")
    a = ap.parse_args()

    if a.corpus:
        if not a.paths:
            print("voice_check: --corpus needs paths", file=sys.stderr)
            return 2
        print(corpus_report(a.paths))
        return 1 if corpus(a.paths) else 0

    findings: list[dict] = []
    if a.text:
        findings += check(a.text, source="--text")
    for path in a.paths:
        try:
            with open(path, encoding="utf-8") as fh:
                findings += check(fh.read(), source=os.path.basename(path))
        except OSError as e:
            print(f"voice_check: cannot read {path}: {e}", file=sys.stderr)
            return 2
    if a.json_in:
        try:
            with open(a.json_in, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError) as e:
            print(f"voice_check: cannot read {a.json_in}: {e}", file=sys.stderr)
            return 2

        def walk(node, trail):
            if isinstance(node, str):
                if len(node.split()) >= 6:
                    findings.extend(check(node, source=trail))
            elif isinstance(node, dict):
                for k, v in node.items():
                    walk(v, f"{trail}.{k}" if trail else str(k))
            elif isinstance(node, list):
                for i, v in enumerate(node):
                    walk(v, f"{trail}[{i}]")
        walk(data, os.path.basename(a.json_in))

    if not (a.text or a.paths or a.json_in):
        ap.print_usage(sys.stderr)
        return 2

    print(report(findings))
    hard = [f for f in findings if f["severity"] == "hard"]
    if hard or (findings and not a.soft_ok):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
