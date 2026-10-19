#!/usr/bin/env python3
"""The tone rules from the brief, as checks that return violations.

Every rule here is a correction that had to be made by hand, repeatedly, on
drafts that read as machine-written. A rule kept in prose gets re-learned every
time a draft is written; a rule kept as a check fails the draft before the user
ever sees it. That is the whole reason this file exists.

The checks are deliberately literal. They match the phrasings that were actually
corrected, they quote the offending text back so the writer can see what tripped,
and they never rewrite anything. Composing is `compose.py`'s job and rewriting is
the model's. A checker that silently repaired a draft would hide the habit that
produced it, and the habit is the thing worth killing.

Two rules need context the text does not carry, so it is passed in. The
recipient's name, because "never open a mid-message sentence with their name"
cannot be checked without knowing the name. And their seniority, because an
exclamation mark is a tone error to a Director and merely informal to a peer.

`restate_ratio` is the one measurement rather than a match. The brief calls
restating someone's own points back at them the single most common failure mode
of a machine-written reply, and it is invisible to phrase matching: the words
are the recipient's own, so nothing on any banned list appears.

    from tone import check, restate_ratio
    check("Great to connect!", recipient_seniority="senior")
    -> [Violation(rule='exclamation_to_senior', text='Great to connect!')]
"""

from __future__ import annotations

import os
import re
import sys
from typing import NamedTuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import locale_rules  # noqa: E402
import person  # noqa: E402
import voice_check  # noqa: E402

_NET = person.module("networking") if person.exists("networking.py") else None
# The dashes, the spelling variant and the document noun, from the profile's
# documents settings: one copy, which the resume and letter checks read too.
_LOCALE = locale_rules.LOCALE


class Violation(NamedTuple):
    """A rule name and the text that broke it.

    A plain two-tuple by design: callers unpack `(rule, text)` and tests compare
    against literals, while `.rule` and `.text` keep the call sites readable.
    """

    rule: str
    text: str


class Restatement(NamedTuple):
    """The restatement measure: how much of the reply came from their message."""

    ratio: float
    terms: list
    flagged: bool


# Every rule this module can return. Named here so the skill layer, the tests
# and any caller building a report agree on the vocabulary, and so a renamed
# rule breaks loudly instead of quietly never firing again.
RULES = (
    "em_dash",
    "en_dash",
    "banned_phrase",
    "name_starts_sentence",
    "opens_with_laugh",
    "stacked_thanks",
    "exclamation_to_senior",
    "saw_your_post",
    "british_spelling",
    "document_noun",
    "unsupported_claim",
    "sentence_starts_with_contraction",
    "person_dislikes",
)

EM_DASH = locale_rules.EM_DASH
EN_DASH = locale_rules.EN_DASH

# The phrases the brief bans, in the brief's own words, so the list can be read
# against section 6 without translation. Two of them are legitimate in one sense
# and banned in another ("at scale" as padding, "reach out" as a noun); the
# patterns carry that distinction, the list carries the name. What fires is
# voice_check.PHRASES, the one list letters and resumes are checked against
# too, so a phrase added there is caught here without a second copy, and the
# message-only patterns below.
BANNED_PHRASES = (
    "moved the needle",
    "at scale",
    "resonates",
    "deep dive",
    "leverage",
    "excited to share",
    "I'd imagine that's exactly where",
    "circle back",
    "reach out",
    "touch base",
    "synergy",
    "on the data side",
)

# "side" is only a tell when it stands in for a team, department or function,
# so the pattern below matches that list rather than excluding the ordinary
# senses. Excluding was tried first and over-fired: "worked on the side",
# "on the cautious side" and "the input side of the audit" are all ordinary
# English, and a rule that blocks a correct sentence costs more than the tell.
# "client" and "buy"/"sell" are deliberately absent: client-side and buy side
# are the technical and finance terms, not the tell.
_SIDE_FUNCTION = (
    r"credit|risk|data|business|engineering|technical|technology|commercial|"
    r"analytics|product|research|delivery|consulting|modelling|modeling|quant|"
    r"quantitative|sales|marketing|finance|ops|operations|vendor|agency|brand|"
    r"corporate|science|software|platform|infrastructure|design|legal|"
    r"compliance|fraud|pricing|strategy|ai|ml")

# What only a message does wrong, beside voice_check.PHRASES: the word
# "leverage" in any form (a letter is held only to "leverage my", because it
# restates an employer's strategy in the employer's words), a closeness to the
# reader the sender has not earned, the reader's team named as a "side", a
# follow-up excusing the silence it follows, and a message describing itself as
# a chase.
_MESSAGE_ONLY = {
    "leverage": re.compile(r"\bleverag(?:e|es|ed|ing)\b", re.I),
    # The manufactured-connection tell. The contraction and the long form both
    # appear, and the middle of it varies ("that's", "this is", nothing at all).
    "I'd imagine that's exactly where": re.compile(
        r"\bI(?:'d| would) imagine\b[^.!?\n]{0,40}\bexactly where\b", re.I),
    # "side" standing in for a team, department or function ("on the credit
    # side", "the data side of Acme"). A quiet tell, because a person
    # names the team. The senses that are not the tell are spared: the
    # hyphenated technical compounds (client-side, server-side), the finance
    # terms (buy side, sell side, supply side), the spatial and figurative
    # ones (the other side, side by side, upside, a side project), and
    # "the X side of the world/road/coin/story".
    # The determiner set covers possessives too: "your side of the org" is the
    # same tell as "the data side", and a pattern anchored on "the" missed it.
    # The bare "<possessive> side of" form needs no function noun, because
    # "your side of the org" is already the team sense on its own.
    "on the data side": re.compile(
        r"\b(?:on|in|from|over on)\s+(?:the|your|our|their|his|her|its)\s+"
        r"(?:[a-z-]+\s+(?:and\s+)?){0,2}(?:" + _SIDE_FUNCTION + r")\s+side\b"
        r"|\b(?:the|your|our|their|his|her|its)\s+"
        r"(?:[a-z-]+\s+(?:and\s+)?){0,2}(?:" + _SIDE_FUNCTION + r")\s+side\s+of\b"
        r"|\b(?:your|our|their|his|her)\s+side\s+of\s+(?:the\s+)?"
        r"(?:org|organisation|organization|business|company|house|team|shop|world|fence)\b",
        re.I),
    # Inventing an explanation for their silence. "Happy to resend if it got
    # lost" supposes a failure that almost certainly did not happen; a sent email
    # is a sent email, and the sender knows it. Every version of this move does
    # two bad things at once: it reads as desperate, and it hands the reader a
    # ready-made non-answer they can take instead of the real one. A follow-up
    # such as "glad to send that over a second time if it went astray" is the
    # shape. Their silence needs no theory. Ask the question.
    "excusing their silence": re.compile(
        r"\b(?:happy|glad)\s+to\s+(?:re-?send|re-?share|send\s+(?:it|that)\s+again)\b"
        r"|\bin\s+case\s+(?:it|this|that)\s+(?:got|went|was|ended\s+up)\s+"
        r"(?:(?:in|to|into)\s+(?:your\s+)?)?"
        r"(?:lost|buried|missed|spam|junk|overlooked)\w*\b"
        r"|\bif\s+(?:it|this|that)\s+(?:got|went|was)\s+"
        r"(?:lost|buried|missed|overlooked)\w*\b"
        r"|\bin\s+case\s+you\s+(?:missed|did\s*n[o']?t\s+see)\b"
        r"|\bnot\s+sure\s+if\s+you\s+(?:saw|got|received)\b"
        r"|\bI\s+know\s+(?:you(?:'re| are)\s+)?(?:busy|swamped|slammed)\b"
        r"|\bI\s+know\s+(?:things|it)\s+(?:are|is|must\s+be)\s+busy\b",
        re.I),
    # Naming the thing you are disclaiming. "A quick question, not a chase"
    # tells the reader this is a chase; "sorry to nag" asks them to hold the
    # nagging in mind while reading. The move is always the same: the writer is
    # uncomfortable and hands the discomfort to the recipient instead of just
    # asking the question. Deliberately narrow: it catches the message
    # describing ITSELF as a chase, nag, bother or pester, and leaves "chase
    # the invoice" and every other ordinary use alone.
    "naming what you disclaim": re.compile(
        r"\b(?:rather than|not|instead of)\s+(?:a|another)\s+"
        r"(?:chase|nag|nudge|bother|pester|reminder)\b"
        r"|\b(?:sorry|apologies)\s+(?:to|for)\s+"
        r"(?:chas|nagg?|bother|pester|hound)(?:e|ing|ping)?\b"
        r"|\bnot\s+(?:trying\s+)?to\s+(?:chase|nag|pester|hound|bother)\b",
        re.I),
}

# Immigration status the profile does not support: networking.py's
# UNSUPPORTED_STATUS. It lives here rather than in compose.py because compose
# only reached it on the arguments it assembled itself, and the skill layer is
# told to hand-write messages and run them through compose.validate(); a
# hand-written claim to a status the profile does not record would therefore
# pass the only gate there is. The claim is the one an employer verifies first,
# so it fails in the opening HR screen and takes the relationship with it.
UNSUPPORTED_CLAIM = getattr(_NET, "UNSUPPORTED_STATUS", None) or re.compile(r"(?!x)x")

_LINE_BOUND = re.compile(r"\n")

# Sentence splitting mirrors `render_application.SENT_SPLIT` rather than
# importing it: that module pulls in the entire resume generator, and a tone
# check that cannot be imported without the LaTeX toolchain behind it is a tone
# check nobody runs.
_SENT_SPLIT = re.compile(
    r"(?<!\be\.g\.)(?<!\bi\.e\.)(?<!\bvs\.)(?<!\betc\.)(?<!\bInc\.)"
    r"(?<!\bLtd\.)(?<![A-Z]\.)(?<=[.!?])\s+")

_GREETING = re.compile(r"^(?:hi|hey|hello|dear|good (?:morning|afternoon|evening))\b", re.I)
_SUBJECT = re.compile(r"^subject\s*:", re.I)
# "Ha", "Hah", "Haha", "Heh", "Lol". Written as repeated syllables because
# a naive ha+h* matches "Ha" and then fails on "Haha", which is the form
# people actually type.
# A laugh is an interjection, not a word that happens to start with those two
# letters. The first version was `ha(?:ha)*h?|he(?:he)*h?|lol+`, in which the
# single-token alternatives made **every sentence opening "He"** a laugh: "He
# mentioned it came through you" was flagged, and so would "He said", "He asked"
# and "He is".
#
# So a laugh has to look like one: doubled (haha, hehe), spelled with a trailing
# h (hah), unambiguous (lol), or a bare "ha" that punctuation marks as an
# interjection ("Ha, fair enough"). A bare "he" is never treated as a laugh,
# because the pronoun is common and the laugh spelled that way is not.
_LAUGH = re.compile(
    r"^(?:"
    r"(?:ha){2,}h?"            # haha, hahaha, hahah
    r"|(?:he){2,}h?"           # hehe, hehehe
    r"|hah+"                   # hah, hahhh
    r"|lol+"                   # lol, lolll
    r"|ha(?=\s*[!,.?\u2026])"  # "Ha!", "Ha, fair enough"
    r")\b", re.I)

# Gratitude, in all the forms that stack. Two of these in one message is the
# grovel the brief bans; one is normal manners.
_THANKS = re.compile(
    r"\b(thank you|thank-you|thanks|thankful|grateful|gratitude|"
    r"appreciate|appreciated|appreciation)\b", re.I)

# Stacking is two thanks in one breath. Counting them across a whole message
# flagged the ordinary email that opens "thanks for taking the time" and closes
# "thanks again", which is manners, not grovelling, and sending the writer back
# to delete one of them was the check being wrong rather than the draft.
THANKS_WINDOW = 120

# "I saw your post about X" names the act of having seen it instead of the
# substance of it, which is what marks a message as one of a batch. Referencing
# what they said is the point; referencing that they said it is the tell.
_SAW_POST = re.compile(
    r"\b(?:saw|noticed|came across|read|spotted|stumbled (?:up)?on)\b[^.!?\n]{0,30}\b"
    r"(?:your|the)\s+(?:recent\s+)?(?:post|update|comment|article|piece|thread)\b"
    r"|\b(?:saw|noticed|read)\s+(?:that\s+)?you\s+(?:posted|shared|wrote)\b", re.I)

# The brief's named example of what not to send a Senior Director. The
# approved wording lives in compose.WORK_AUTH in both registers, and neither is
# this one: work authorization is the single fact a hiring manager has to be
# able to rely on, and a shrug is the wrong register for it at any seniority.
_CASUAL_WORK_AUTH = re.compile(
    r"\bvisa(?:'s|\u2019s| is)?\s*(?:all\s*)?sorted\b"
    r"|\bsorted\b[^.!?\n]{0,12}\bvisa(?:\s*wise)?\b"
    r"|\b(?:I(?:'m|\u2019m| am)\s+)?(?:all\s+)?good\s+(?:on|with|for)\s+the\s+visa\b"
    r"|\bno\s+visa\s+(?:issues|problems|dramas|worries)\b"
    r"|\bvisa\s*[- ]?\s*wise\s+I(?:'m|\u2019m| am)\s+(?:fine|good|sorted)\b", re.I)

# "Manufactured-connection phrasing", the brief's words, with its own example.
# It asserts a closeness the sender has not earned, and a senior reader has seen
# it from every other applicant that week. Saying what the overlap actually is
# costs the same number of words and is checkable.
_MANUFACTURED = re.compile(
    r"\bthat(?:'s|\u2019s| is)\s+exactly\s+(?:where\s+I\s+sit|what\s+I\s+do"
    r"|my\s+world|where\s+I\s+live|the\s+work\s+I\s+do)\b"
    r"|\bthis\s+is\s+exactly\s+(?:my\s+world|what\s+I\s+do|where\s+I\s+sit)\b"
    r"|\bcould\s*n(?:'|\u2019)?t\s+have\s+(?:said|put)\s+it\s+better\b"
    r"|\b(?:really\s+)?speaks\s+to\s+me\b"
    r"|\bright\s+up\s+my\s+(?:street|alley)\b"
    r"|\bwe(?:'re|\u2019re| are)\s+basically\s+(?:the\s+same|doing\s+the\s+same)\b", re.I)


# Register buckets, not job titles. The argument says how formal the surface
# should be.
#
# The list held only senior/exec/executive/director/vp/head/chief/formal, so
# every one of these read as a PEER and got peer register, exclamation marks
# included: "Associate Partner", "Principal", "Founder and CEO", "Data Science
# Manager" and every C-suite title spelled out rather than abbreviated.
#
# The opposite error was in the same list. Bare "senior" is a seniority prefix
# on an IC title far more often than a register marker: "Senior Data Scientist"
# is a peer and was being written to as an executive. So "senior" only counts
# when it qualifies something that is itself senior.
SENIOR_MARKERS = frozenset({
    "exec", "executive", "director", "vp", "head", "chief", "formal",
    "partner", "principal", "founder", "cofounder", "owner",
    "ceo", "cto", "coo", "cfo", "cio", "cdo", "cpo", "president",
    "managing", "officer", "lead", "leader", "leadership", "manager",
})

# "senior" promotes only when it sits on one of these.
_SENIOR_QUALIFIES = frozenset({
    "director", "manager", "vp", "partner", "principal", "executive",
    "lead", "leader", "officer", "president",
})

_HONORIFICS = frozenset({"mr", "mrs", "ms", "miss", "mx", "dr", "prof", "professor", "sir"})
# Only the abbreviations that turn up in a directory listing after the comma.
# state.person_name holds the full list; this one exists so a credential is not
# mistaken for a given name when deciding whether a name is written backwards.
_CREDENTIALS = frozenset({"phd", "md", "mba", "msc", "bsc", "meng", "llb", "jd",
                          "cfa", "cpa", "cma", "cfp", "pmp", "frm", "peng", "esq",
                          "jr", "sr", "ii", "iii", "iv"})
_PAREN = re.compile(r"\([^)]*\)")
# Unicode letters, not ASCII ones. The ASCII class cut a name at its first
# accent, so "Zoé Ruíz" came back as "Zo" and the note opened "Hi Zo,",
# a mangled name in the first two words of an outbound message. The repo
# already knew accented names arrive here: state.already_contacted folds
# accents before comparing because LinkedIn can return one person as
# "Zoe Ruiz" in one snippet and "Zoé Ruíz" in the next. Folding to
# compare and truncating to greet were the same blind spot seen from two
# sides. The apostrophe and hyphen stay in the continuation class so
# "O'Brien" and "Jean-Luc" are still one token.
_NAME_TOKEN = re.compile(r"[^\W\d_](?:[^\W\d_]|['\-])*")
_CURLY = {"’": "'", "‘": "'", "“": '"', "”": '"'}


def _plain(text) -> str:
    """Straighten curly quotes so "I'd" and "I’d" are one phrase to match.

    Dashes are untouched: they are a rule, not a nuisance.
    """
    s = str(text or "")
    for curly, straight in _CURLY.items():
        s = s.replace(curly, straight)
    return s


def is_senior(seniority) -> bool:
    """Does this title warrant the formal register?

    `seniority` is usually one of the literal strings "peer" / "senior", but
    callers also pass a real job title, so both have to work.
    """
    tokens = re.findall(r"[a-z]+", str(seniority or "").lower())
    if "senior" in tokens:
        # "Senior Director" yes, "Senior Data Scientist" no. A bare "senior",
        # which is what the peer/senior argument passes, still counts.
        if len(tokens) == 1 or any(t in _SENIOR_QUALIFIES for t in tokens):
            return True
    return any(t in SENIOR_MARKERS for t in tokens)


# What a bracket in a name holds when it is not the name somebody goes by:
# pronouns, and the notes people add to a LinkedIn name field. Credentials and
# honorifics are the sets above.
_PRONOUNS = frozenset({"he", "him", "his", "she", "her", "hers", "they", "them", "their",
                       "theirs", "ze", "zir", "xe", "xem", "pronouns"})
_NOT_A_NAME = frozenset({"hiring", "recruiting", "retired", "remote", "freelance", "contract",
                         "open", "formerly", "former", "nee", "née", "born", "aka"})


def preferred_name(name) -> str:
    """The name written in brackets, when the brackets hold a name. "" otherwise.

    "Xiu Mei (Sally) Ho, PhD" is how a contact book writes a person with a
    preferred name, and the bracket is where they put the name they go by. Only a bracket of one or two capitalized name words counts: "(She/Her)",
    "(PhD)", "(Hiring)", "(ex-Google)" and a name in another script are not
    somebody to greet.
    """
    for m in _PAREN.finditer(_plain(name)):
        words = m.group(0)[1:-1].split()
        if not 1 <= len(words) <= 2 or not all(_NAME_TOKEN.fullmatch(w) for w in words):
            continue
        if any(w.lower() in _PRONOUNS | _NOT_A_NAME | _CREDENTIALS | _HONORIFICS
               for w in words):
            continue
        if words[0][:1].isupper() and words[0][1:2].islower():
            return words[0]
    return ""


def first_name(name) -> str:
    """The given name, for the greeting and for the name-tic rule.

    Deliberately small. `state.person_name` does the full job (pronouns,
    credentials, a reversed "Halloway, Wren") but it belongs to the store, and this
    module stays pure text logic so that checking a draft never touches a CSV.
    The two agree on every ordinary case, which is all a salutation needs.

    They part on a preferred name in brackets, deliberately. `person_name` drops
    the bracket because it builds an id from the surname; this reads it first,
    because a greeting is the one place the name someone goes by is the point.
    Deleting it greeted "Xiu Mei (Sally) Ho, PhD" as "Hi Xiu".
    """
    preferred = preferred_name(name)
    if preferred:
        return preferred
    cleaned = _PAREN.sub(" ", _plain(name))
    head, comma, tail = cleaned.partition(",")
    head_tokens = [t for t in _NAME_TOKEN.findall(head)
                   if t.lower().strip(".") not in _HONORIFICS]
    tail_tokens = _NAME_TOKEN.findall(tail.partition(",")[0])
    # "Halloway, Wren" is a surname-first listing, which is how LinkedIn exports
    # and conference directories write it. Read left to right it greets the
    # reader as "Hi Halloway," which is the one salutation error they are certain
    # to notice. A trailing credential or honorific is not a given name, so
    # "Wren Halloway, MSc" is left alone.
    if (comma and len(head_tokens) == 1 and 1 <= len(tail_tokens) <= 2
            and all(t.lower().strip(".") not in _CREDENTIALS
                    and t.lower().strip(".") not in _HONORIFICS for t in tail_tokens)):
        cleaned = tail + " " + head_tokens[0]
    else:
        cleaned = head
    # A credential is never a given name, wherever it sits: "Ph.D. Jane Doe" was
    # greeted "Hi Ph,". An initial is not one either: "J. Smith" was "Hi J,".
    # With nothing but an initial, the name goes in whole ("Hi J. Smith,"); with
    # nothing but a surname after a title, the title stays ("Hi Dr Smith,").
    words = [w for w in cleaned.split()
             if re.sub(r"[^\w]", "", w).lower() not in _CREDENTIALS]
    titles = [w for w in words if w.lower().strip(".") in _HONORIFICS]
    names = [w for w in words if w.lower().strip(".") not in _HONORIFICS]
    tokens = [t for w in names for t in _NAME_TOKEN.findall(w)]
    if not tokens:
        return ""
    if len(tokens[0]) == 1:
        return " ".join(names).strip(" ,")
    if titles and len(tokens) == 1:
        return f"{titles[0]} {tokens[0]}"
    return tokens[0]


# Whose message is this? A connection note has four moves and three of them are
# legitimately about the sender: the who-line names the employers, the
# work-authorization line answers the first objection, and the close asks for
# the reply. The HOOK is the one that has to be about the reader, and
# SKILL.md is explicit: "Specific hook tied to THAT person ... Reference the
# substance of what they said."
#
# The failure it catches is a batch of notes in which every hook opens on the
# sender. "I built our stock dashboards", "I run the weekly sales and
# operations numbers", "my team owns replenishment". Each is true, each is
# relevant, and together they read as a resume read aloud at someone, a list of
# credentials where a question should be. Nothing in compose.validate() measured it,
# because length, cliche and restatement all pass on a note that is simply
# about the wrong person.
#
# The rule is deliberately narrow so it does not fire on good writing. A hook
# with no first person at all is fine ("The new audit rules changed what a
# model file has to carry" is about their world). A hook that names the reader, their company or
# something of theirs is fine however much "I" it also contains. Only the hook
# that talks about the sender and never reaches the reader is refused.
# re.I on both, and it is load-bearing rather than tidy: without it "You have
# been hiring into the payments team here" was read as a hook that never
# reaches the reader, because the pattern was lowercase and the sentence
# starts with a capital. A hook opens a sentence, so the second-person word
# is capitalised exactly when it matters most.
_FIRST_PERSON = re.compile(r"\b(?:I|I'm|I've|I'd|I'll|me|my|mine|myself)\b", re.I)
_SECOND_PERSON = re.compile(r"\b(?:you|you're|your|yours|yourself|yourselves)\b", re.I)


def reaches_them(text, their=()) -> bool:
    """Does this message get to the reader anywhere, or is it only about the sender?

    `their` is anything on the reader's side the message may name instead of
    using "you": their employer, their product, their event, a phrase of their
    own. The caller passes it because only the caller knows what the message is
    referring to; a checker cannot tell that "Day of Data" is their conference.

    CHECKED OVER THE WHOLE MESSAGE, NOT THE HOOK, and that correction is the
    whole history of this function. The first version took the hook alone, on
    the reasoning that the hook is the one move that is about the reader. The
    reasoning was right and the mechanism was wrong: the plain alternative is
    to state who the sender is and what they are looking for, with a custom
    line tailored to the reader.

    Demanding the FIRST sentence be about the reader forbids the plainest and
    best opening there is, "I am an analyst in <City>", and pushes the
    writer into saying something about the reader's job before they have earned
    the standing to. What came out was a note telling a senior analytics leader
    what their own sector sees, and a note telling a director that their
    function is a hard sell. Both are true, both are about the reader, and both
    are a stranger explaining the reader's own job to them.

    So the note has to reach them, and it does not have to reach them first.
    """
    text = _plain(text or "")
    if not text.strip():
        return False
    if not _FIRST_PERSON.search(text):
        # Nothing about the sender to crowd the reader out.
        return True
    if _SECOND_PERSON.search(text):
        return True
    for term in (their or ()):
        t = str(term or "").strip()
        if t and re.search(re.escape(t), text, re.I):
            return True
    return False


# The original name, kept so nothing breaks while it is still referenced.
# Same function; the caller decides whether to hand it a hook or a whole note,
# and everything in this repo now hands it the whole note.
hook_reaches_them = reaches_them


def sentences(text) -> list:
    """Sentences, with a line break counting as a boundary.

    Messages break lines where letters do not. "Hi Wren," on its own line above a
    blank line is a complete salutation with no full stop in it, and without the
    newline boundary the whole first paragraph reads as one sentence, which
    makes the greeting exemption in the name rule swallow the tic it exists to
    catch.
    """
    out = []
    for line in _plain(text).splitlines():
        line = line.strip()
        if not line:
            continue
        out.extend(s.strip() for s in _SENT_SPLIT.split(line) if s.strip())
    return out


def _greeting_exempt(sents) -> set:
    """Indices that are the opening salutation, where the name belongs.

    "Hi Wren," is how every message starts. The rule is about the *second*
    "Wren," further down, the one that tries to sound personal and reads as a
    mail merge. An email whose first line is a subject line pushes the greeting
    to index one, so the first two are considered.
    """
    exempt = {0}
    if len(sents) > 1 and (_SUBJECT.match(sents[0]) or _GREETING.match(sents[1])):
        exempt.add(1)
    return exempt


def _dashes(text) -> list:
    return [Violation(rule, _around(text, i)) for rule, i in _LOCALE.dashes(text)]


def _around(text, index, width=24) -> str:
    """The offending character with enough either side to find it by eye."""
    return text[max(0, index - width):index + width].strip()


def _banned(text) -> list:
    # One violation per stretch of text: "leverage my" is the message rule's
    # "leverage" and the shared "leverage my" at once.
    found = [m for pattern in _MESSAGE_ONLY.values() for m in pattern.finditer(text)]
    found += [m for _, m in voice_check.banned_phrases(text)]
    kept = []
    for m in found:
        if not any(m.start() < k.end() and k.start() < m.end() for k in kept):
            kept.append(m)
    return [Violation("banned_phrase", m.group(0)) for m in kept]


def _name_starts_sentence(text, name) -> list:
    given = first_name(name)
    if not given:
        return []
    sents = sentences(text)
    exempt = _greeting_exempt(sents)
    out = []
    for i, sentence in enumerate(sents):
        if i in exempt:
            continue
        lead = _NAME_TOKEN.match(sentence)
        if lead and lead.group(0).lower() == given.lower():
            out.append(Violation("name_starts_sentence", sentence[:60]))
    return out


def _opens_with_laugh(text) -> list:
    sents = sentences(text)
    if not sents:
        return []
    # The laugh can sit either at the very start or immediately after the
    # salutation, and both read the same way to the recipient.
    candidates = [re.sub(r"^(?:hi|hey|hello|dear)\b[^,\n]{0,40},\s*", "", sents[0], flags=re.I)]
    if len(sents) > 1 and _GREETING.match(sents[0]):
        candidates.append(sents[1])
    for candidate in candidates:
        m = _LAUGH.match(candidate)
        if m:
            return [Violation("opens_with_laugh", candidate[:40])]
    return []


def _stacked_thanks(text) -> list:
    spans = [(m.start(), m.end(), m.group(0)) for m in _THANKS.finditer(text)]
    # Deliberately offset by one: this walks adjacent pairs, so the
    # sequences differ in length by design and strict would be wrong.
    for (_s1, e1, w1), (s2, _e2, w2) in zip(spans, spans[1:]):  # noqa: B905
        if s2 - e1 <= THANKS_WINDOW:
            return [Violation("stacked_thanks", f"{w1}, {w2}")]
    return []


def _exclamation(text, seniority) -> list:
    if not is_senior(seniority):
        return []
    return [Violation("exclamation_to_senior", s[:60]) for s in sentences(text) if "!" in s]


def _saw_your_post(text) -> list:
    return [Violation("saw_your_post", m.group(0)) for m in _SAW_POST.finditer(text)]


# A sentence start that is not capitalized. The composers assemble a note from
# pieces a model hands over, and a hook written as "saw you are recruiting..."
# came out as "hope you're well. saw you are recruiting...". The composer now
# capitalizes, but the same text can arrive hand-written through validate(), so
# the rule lives here where both paths hit it. Anything beginning with a digit
# or a known lowercase token is left alone.
_LOWERCASE_START = re.compile(r"(?<=[.!?])\s+([a-z][a-z']{2,})")
_LOWERCASE_OK = frozenset("""
dbt iOS iPhone eBay pandas scikit numpy matplotlib pytest lualatex xelatex http https www
""".lower().split())


# Opening a sentence on a contraction ("I've worked in planning...", "I'm keen
# to hear") reads as sloppy, and in a 300-character note it is usually
# there to save two characters rather than because it sounds better. Mid-sentence
# contractions are untouched, which is where they read as speech rather than
# shorthand: "the kind of team I'd love to join" stays exactly as it is.
# Only the endings that are unambiguously a contraction, plus the handful of
# `'s` words that can only be one. A bare `'s` is far more often a possessive,
# and the first version of this rule flagged "<Company>'s own annual
# results...", "<Company>'s about page...", "<Company>'s mission..." and
# "<Company>'s leadership principle..." across most letters. Opening on a
# company's name in the possessive is not the sloppiness this rule is for.
_CONTRACTION_WORDS = r"(?:it|that|there|here|what|who|let|he|she|nothing|everything)'s"
_SENT_START_CONTRACTION = re.compile(
    r"^([A-Za-z]+'(?:ll|ve|d|re|m)\b" r"|" + _CONTRACTION_WORDS + r"\b)", re.I)


def _sentence_starts_with_contraction(text) -> list:
    out = []
    for s in sentences(text):
        m = _SENT_START_CONTRACTION.match(s.strip())
        if m:
            out.append(Violation("sentence_starts_with_contraction", m.group(1)))
    return out


def _lowercase_sentence_start(text) -> list:
    return [Violation("lowercase_sentence_start", m.group(1))
            for m in _LOWERCASE_START.finditer(text)
            if m.group(1).lower() not in _LOWERCASE_OK]


# An unfilled placeholder in a message that reaches a real person is the single
# most damaging defect in this module: it says the sender did not read what they
# sent. validate() is the only gate on a model-written draft, and it had no rule
# for this, so "[First Name]", "{company}", "<role>", "TBD" and "XX" all passed.
_PLACEHOLDER = re.compile(
    r"\[[^\]\n]{1,40}\]"
    r"|\{[A-Za-z_][A-Za-z0-9_ ]{1,30}\}"
    r"|<[A-Za-z_][A-Za-z0-9_ ]{1,30}>"
    r"|\bTBD\b|\bTODO\b|\bFIXME\b"
    # Case-sensitive: these are only placeholders when they are shouted.
    # "YOUR[_ ][A-Z]{2,}" under re.I matched the ordinary words "your team".
    r"|(?-i:\bXX+\b)"
    r"|(?-i:\bYOUR[_ ][A-Z]{2,}\b)"
    r"|(?-i:\bINSERT\b|\bPLACEHOLDER\b)", re.I)

# Two spaces mid-sentence, or a space before punctuation. Cheap to spot by eye
# and cheap to miss when a message is assembled from parts.
_SPACING = re.compile(r"\S {2,}\S|\s+[,.;:!?]")


def _placeholder(text) -> list:
    return [Violation("unfilled_placeholder", m.group(0))
            for m in _PLACEHOLDER.finditer(text)]


def _spacing(text) -> list:
    return [Violation("spacing", " ".join(m.group(0).split()))
            for m in _SPACING.finditer(text)]


def _casual_work_auth(text) -> list:
    return [Violation("casual_work_auth", m.group(0))
            for m in _CASUAL_WORK_AUTH.finditer(text)]


def _manufactured_connection(text) -> list:
    return [Violation("manufactured_connection", m.group(0))
            for m in _MANUFACTURED.finditer(text)]


def _unsupported_claim(text) -> list:
    return [Violation("unsupported_claim", m.group(0))
            for m in UNSUPPORTED_CLAIM.finditer(text)]


def _british(text) -> list:
    """Another variety's spelling, and the document noun the market does not use.

    Reported as the variety the form belongs to: "british_spelling" for "organise"
    in a Canadian message, "american_spelling" for "behavior" in it or in a
    British one. A name and a quotation keep their own spelling (locale_rules
    says how each is told). "CV" where the profile bans it is reported as british_spelling, the
    name it has always had: people's own suites pin it (profile/tests), and renaming a
    label breaks them for no change in what is caught. The other banned nouns are
    document_noun.
    """
    # "american_spelling" is not in RULES, and neither is "banned_character" from
    # _dashes: a person's own suite pins RULES against a fixture per rule
    # (profile/tests), and a name added there fails it until they write one.
    out = [Violation(f"{variety}_spelling", m.group(0))
           for variety, m in _LOCALE.wrong_spellings(text, theirs=True)]
    for n in _LOCALE.nouns:
        rule = "british_spelling" if n.word == "CV" else "document_noun"
        out += [Violation(rule, _around(text, m.start(), 16)) for m in n.message.finditer(text)]
    return out


# Rules that only make sense on a first, short, cold message. A connection note
# is 300 characters to a stranger, so an opening contraction is nearly always
# there to save two characters rather than because it sounds better, and it reads
# as sloppy. That reasoning does not survive contact with a live thread: replying
# "That's great, thank you Riley" to someone who wrote "Hi Robin - ... :)" is how
# people actually speak, and "That is great" is the stilted version. The rule
# is scoped to cold messages because enforcing it there produces a formality
# the register does not want.
COLD_ONLY_RULES = frozenset({"sentence_starts_with_contraction"})

# Rules that fire only on the person's own data, never on fixed text: a test
# that gives every rule in RULES a firing case subtracts these. Adding a rule
# here, not only to RULES, keeps a person's own completeness tests passing.
DATA_DRIVEN_RULES = frozenset({"person_dislikes"})


def _person_dislikes(text) -> list:
    """A phrase the person has said never to use (profile/learned.json, tools/learned.py)."""
    try:
        import learned
    except ImportError:
        return []
    return [Violation("person_dislikes", m) for m in learned.dislikes(text)]


def check(text, recipient_seniority="peer", name=None, live_thread=False) -> list:
    """Every tone violation in `text`, as (rule, offending_text) pairs.

    Returns rather than raises: a draft usually breaks two or three rules at
    once and the writer needs all of them in one pass, not the first one.

    `live_thread=True` drops COLD_ONLY_RULES. Pass it whenever the recipient has
    already replied: the register is different and enforcing cold-open rules
    there is what makes a warm reply read like a form letter.
    """
    plain = _plain(text)
    found = (_dashes(plain)
            + _banned(plain)
            + _name_starts_sentence(plain, name)
            + _opens_with_laugh(plain)
            + _stacked_thanks(plain)
            + _exclamation(plain, recipient_seniority)
            + _saw_your_post(plain)
            + _placeholder(plain)
            + _spacing(plain)
            + _casual_work_auth(plain)
            + _manufactured_connection(plain)
            + _lowercase_sentence_start(plain)
            + _sentence_starts_with_contraction(plain)
            + _british(plain)
            + _unsupported_claim(plain)
            + _person_dislikes(plain))
    if live_thread:
        found = [v for v in found if v.rule not in COLD_ONLY_RULES]
    return found


# Words long enough to carry content but empty enough to be shared by any two
# messages on any subject. Length alone removes "the" and "and"; these are the
# five-letter-plus passengers that would otherwise inflate every overlap.
STOPWORDS = frozenset("""
about above after again against almost along already also although always among
another anyone anything around because been before behind being below besides
better between both cannot could couldn doing during each either enough especially
even every everyone everything first from further getting given gives going good
great happy have having here hope however indeed instead into itself just keep
kind know later least less like likely little looking maybe might more most much
must myself never next nothing often once only other others ought over particularly
perhaps please probably quite rather really right same seems several should since
some someone something sometimes still such sure than that their theirs them then
there therefore these they thing things think this those though through thus time
together toward towards under until upon using usually very want well were what
when where whether which while with within without would your yours yourself
""".split())

# Two in five. Below that, shared vocabulary is topic continuity: a reply about
# pricing has to say pricing, and penalising that would push drafts into
# thesaurus English, which reads worse than the parroting it was meant to fix.
# Above it, the reply has stopped bringing vocabulary of its own, which is
# exactly what a paraphrase back at them looks like from the recipient's side.
RESTATE_THRESHOLD = 0.4

# Under six distinctive words the ratio is noise: "Sent, thanks" that happens to
# reuse two of their words scores 1.0 and is a perfectly good reply.
MIN_CONTENT_WORDS = 6

MIN_CONTENT_WORD_LEN = 5   # the brief's ">4 chars"


def _stem(word) -> str:
    """Plural and possessive off, nothing else.

    "pipelines" handed back as "pipeline" is still their word. Anything more
    aggressive starts merging words that are genuinely different and the measure
    stops being explainable, which matters because the caller has to show the
    overlapping terms to justify a rewrite.
    """
    w = word.lower().rstrip("'")
    if w.endswith("'s"):
        w = w[:-2]
    if len(w) > MIN_CONTENT_WORD_LEN and w.endswith("s") and not w.endswith("ss"):
        w = w[:-1]
    return w


def _content_words(text) -> list:
    out = []
    for token in _NAME_TOKEN.findall(_plain(text)):
        if len(token) < MIN_CONTENT_WORD_LEN:
            continue
        stem = _stem(token)
        if stem in STOPWORDS or len(stem) < MIN_CONTENT_WORD_LEN - 1:
            continue
        out.append(stem)
    return out


def restate_ratio(reply_text, their_message) -> Restatement:
    """How much of the reply's vocabulary came out of their message.

    The share of the reply's distinct content words that also appear in theirs,
    plus the overlapping terms, so a caller can show the writer which words gave
    it away rather than asserting the draft "sounds AI-generated".
    """
    reply = _content_words(reply_text)
    theirs = set(_content_words(their_message))
    if not reply:
        return Restatement(0.0, [], False)
    distinct = list(dict.fromkeys(reply))
    overlap = [w for w in distinct if w in theirs]
    ratio = len(overlap) / len(distinct)
    flagged = ratio >= RESTATE_THRESHOLD and len(distinct) >= MIN_CONTENT_WORDS
    return Restatement(round(ratio, 3), overlap, flagged)
