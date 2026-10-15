#!/usr/bin/env python3
"""Message assembly, with the limits that are actually hard treated as hard.

Four message types, one shape each, taken from section 4 of the brief. The
shapes are not style preferences. Each one is the arrangement that got replies:
named employers early because a recognizable brand is what earns the read, the
hook before the pitch because a hook specific to that person is the only thing
separating this from a template sweep, the referrer in the first sentence
because a buried referral wastes the highest-converting message in the system.

Length is where this module is deliberately unfriendly. A connection note over
300 characters is not a slightly long note, it is a note LinkedIn cuts off
mid-sentence, and the fix is always to cut something specific rather than to let
a truncator choose. So the composers raise, with the count, and nothing here
ever silently shortens a draft.

`validate()` is the other half and behaves the opposite way: it returns every
problem at once rather than raising on the first, because it runs on text the
model wrote by hand and the writer needs the whole list to do one rewrite
instead of four.

    from compose import connection_note, validate
    note = connection_note("Wren Halloway", hook, who_line, work_auth=True)
    validate(note, "connection", name="Wren Halloway", seniority="senior")
"""

from __future__ import annotations

import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (_HERE, os.path.dirname(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import company_key  # noqa: E402
import person  # noqa: E402
import schema  # noqa: E402
import tone  # noqa: E402

# The person's voice, work authorization and places: profile/networking.py.
_NET = person.module("networking")
# The person's word for the document ("resume", "CV"): person.json
# documents.noun. Every message says it the way their market does; a CV market
# reading "My resume is attached" sees a template from somewhere else.
NOUN = person.get("documents.noun", "resume")


class TooLong(ValueError):
    """A draft that exceeds a limit the platform enforces.

    Carries the count because "too long" without a number sends the writer back
    to a character counter, and the first question is always how much to cut.
    """

    def __init__(self, kind, count, limit, unit="characters"):
        self.kind, self.count, self.limit, self.unit = kind, count, limit, unit
        super().__init__(
            f"{kind} is {count} {unit}, {count - limit} over the {limit} "
            f"{unit.rstrip('s')} limit. Cut and recompose; nothing is truncated here.")


class BuriedReferral(ValueError):
    """A warm intro whose body does not name the referrer in the first sentence."""


class UnsupportedClaim(ValueError):
    """A work-authorization claim the profile does not support."""


class AsksForTheJob(ValueError):
    """A first note that asks for a job instead of a conversation.

    The purpose of a first message is a reply, and a reply is what leads to a
    referral. A note that names the role it wants, asks whether the reader is
    hiring, or states work authorization to someone who is not a recruiter is an
    application in 300 characters, and strangers do not answer applications.
    """


class NoteIsAllAboutTheSender(ValueError):
    """A connection note that never reaches the person it is addressed to.

    Refused here rather than flagged, for the same reason length is: what to
    change is a judgment about what you actually know about this person, and
    nothing downstream can supply that.

    Checked on the whole note. The first version of this checked the hook alone
    and the result was worse than the fault it fixed: forbidding "I am an
    analyst in <City>" as an opening pushed every draft into an observation
    about the reader's job, delivered by a stranger with no standing to make it.
    See tone.reaches_them for the full account.
    """


# The original name. Nothing should raise it any more, but an except clause
# somewhere is cheaper to keep working than to find.
HookIsAboutTheSender = NoteIsAllAboutTheSender


# LinkedIn's InMail body cap. The 150 to 200 word band in schema.LIMITS is the
# target; this is the wall, and a draft over it cannot be sent at all.
INMAIL_CHAR_LIMIT = 1900

# An email is the one channel where brevity is the failure. Someone who asked
# for an email expects the context paragraph, the substance and the resume; a
# three-line reply reads as though the request was an imposition. The ceiling is
# there because a senior reader still stops scrolling somewhere.
EMAIL_WORDS = (70, 320)

# A warm intro is read in a message pane, not a connection request, so it has
# room. There is no floor: the referrer's name is the message, and "Jane
# suggested I get in touch, would love a quick word" is a complete one. Length
# is the only way it fails.
INTRO_WORDS = (None, 200)

# Work authorization, in the two registers the brief allows and no others:
# networking.py's WORK_AUTH, {"senior": ..., "peer": ...}. Both assert present
# authorization and whether sponsorship is needed, exactly as the
# profile supports, and neither claims a status the profile does not hold.
WORK_AUTH = dict(_NET.WORK_AUTH)

# How an email ends: networking.py's SIGN_OFF, {"senior": ..., "peer": ...}.
# `sign_off=None` meant no sign-off at all, so an email that opened "Hi Robin,"
# ended on "My resume is attached." with no closing and no name on it. A
# LinkedIn message can get away with that; something arriving in an inbox
# cannot, and this is the one message type that does.
#
# Register-matched for the same reason everything else here is: the formal
# version reads as stiff from a peer and the short one reads as careless to a
# director.
SIGN_OFF = dict(_NET.SIGN_OFF)

# Claims the profile cannot back. One definition, in tone.py, so that a
# hand-written draft run through validate() is refused on the same words the
# composers refuse, instead of only the arguments this module assembled itself.
_UNSUPPORTABLE = tone.UNSUPPORTED_CLAIM

# The phrasings a draft actually arrives with, all of which mean the same thing
# and only one of which is the approved wording: networking.py's
# WORK_AUTH_CLAUSE. "visa's sorted" is the brief's named example of what not to
# send a Senior Director.
_WORK_AUTH_CLAUSE = _NET.WORK_AUTH_CLAUSE

# The opening furniture: the salutation, the courtesy line that follows it, and
# an email subject line. None of them is a sentence the reader takes content
# from, so none of them counts against the "employers in the first two
# sentences" rule.
_SALUTATION = re.compile(
    r"^(?:hi|hey|hello|dear|good (?:morning|afternoon|evening))\b[^,\n]{0,40},\s*", re.I)
_COURTESY = re.compile(
    r"^(?:hope|trust)\b[^.!?]{0,40}\b(?:well|finds you|good|going well)\b[.!?]?$", re.I)
_SUBJECT_LINE = re.compile(r"^subject\s*:", re.I)

# What `validate` will check, and the aliases callers reach for. An unknown kind
# raises rather than defaulting, because a typo that quietly skipped the length
# check would ship a 340-character connection note.
_KIND_ALIASES = {
    "connection": "connection",
    "connection_note": "connection",
    "connection request": "connection",
    "note": "connection",
    "inmail": "inmail",
    "email": "email",
    "intro": "intro",
    "warm_intro": "intro",
    "referral": "intro",
    "reply": "reply",
    "referral_ask": "referral_ask",
    "nudge": "nudge",
    "follow_up": "nudge",
    "intro_connection": "intro_connection",
    "warm_intro_connection": "intro_connection",
}

KIND_LIMITS = {
    "connection": {"chars": schema.LIMITS["connection_note_chars"]},
    "inmail": {"chars": INMAIL_CHAR_LIMIT, "words": schema.LIMITS["inmail_words"]},
    "email": {"words": EMAIL_WORDS},
    "intro": {"words": INTRO_WORDS},
    # A reply's correct length is the length of the message it answers, which
    # `reply.guidance()` derives from that message. There is no fixed band to
    # enforce here, but the tone rules still apply, so the kind exists.
    "reply": {},
    # Read in a message pane by someone who already knows the sender, so it has room,
    # but it is a favour being asked and a favour asked at length is a burden.
    "referral_ask": {"words": (None, 90)},
    # Below the note it chases; only compose.nudge() enforced it.
    "nudge": {"chars": schema.LIMITS["nudge_chars"]},
    # A warm intro whose instruction was "connect with X" is the request itself.
    "intro_connection": {"chars": schema.LIMITS["connection_note_chars"]},
}

# There is no default close and no default opener any more, and the reason
# shows up in any message log. Count the sent messages that carry their text:
#
#     most  open "hope you're well"              (this file's DEFAULT_OPENER)
#     most  close on "would love" or "I'd love"  (this file's DEFAULT_CLOSE)
#
# A default phrase ends up in nearly every message: the same opener on all of
# them and the same close on all of them. Neither phrase is wrong in one
# message, which is exactly why both survive: `tools/voice_check.py` even
# carries a test saying "hope you're well" is a normal human opener, and for
# one message it is. Repeated across everything a person has sent it is a
# form, and the recipients are in overlapping networks.
#
# The close is also the sentence that asks for the reply, which makes it the
# worst sentence in the message to hand a default to. So it is required, like
# the hook and the who-line, and for the same reason.
DEFAULT_CLOSE = None
DEFAULT_OPENER = None


def _sentence(text) -> str:
    """One clause, whitespace collapsed, terminated exactly once.

    The pieces arrive from a model and some carry their full stop while some do
    not. Concatenating both without this produced "..." runs and doubled stops
    in the middle of otherwise fine notes.
    """
    s = " ".join(str(text or "").split())
    if not s:
        return ""
    # Each piece becomes its own sentence after a full stop, so it has to start
    # like one. A hook handed over as "saw you are recruiting..." rendered as
    # "hope you're well. saw you are recruiting...", which is a visible typo in
    # an outbound message to a recruiter. Only the first character is touched,
    # so "iOS", "dbt" and a lowercase product name mid-sentence are unaffected.
    if s[0].islower():
        s = s[0].upper() + s[1:]
    # The person's own ASK ("Would you have 15 minutes for a few questions
    # sometime") ended every first note on a question with a full stop.
    if _QUESTION_OPENER.match(s):
        return s.rstrip(".!") + "?" if s[-1] != "?" else s
    return s if s[-1] in ".!?" else s + "."


# How a question opens, narrowly: "Would love to hear" and "Do let me know" are
# not questions, so the auxiliaries count only before a pronoun or "there".
_QUESTION_OPENER = re.compile(
    r"^(?:(?:would|could|can|will|do|did|are|were)\s+(?:you|we|there|they)"
    r"|does\s+\w+|is\s+(?:there|it|that|this|your|the)"
    # A question word only before its verb: "What you wrote about forecasting
    # stuck with me" is common ground, not a question.
    r"|(?:how|what|why|when|where|who|which)\s+(?:do|does|did|is|are|was|were|would|could|"
    r"can|should|has|have|had|will)"
    r"|how (?:many|much|long|often|big)|any chance)\b", re.I)


def work_auth_line(seniority="peer") -> str:
    """The approved work-authorization sentence for this register."""
    return _sentence(WORK_AUTH["senior" if tone.is_senior(seniority) else "peer"])


def _checked_claim(work_auth, seniority):
    """Resolve the work_auth argument into a sentence, or refuse it.

    `True` means "use the approved line". A string means the caller wrote their
    own, which is allowed as long as it does not assert citizenship or PR.
    """
    if work_auth is True:
        return work_auth_line(seniority)
    text = str(work_auth or "").strip()
    if not text:
        return ""
    m = _UNSUPPORTABLE.search(text)
    if m:
        raise UnsupportedClaim(
            f"{m.group(0)!r} is not something the profile supports: "
            f"{getattr(_NET, 'UNSUPPORTED_WHY', 'the profile does not hold that status')}. "
            f"Use compose.work_auth_line() or say nothing.")
    return _sentence(text)


def body_sentences(text) -> list:
    """Sentences with the salutation and its courtesy opener removed.

    "Hi Wren, hope you're well." is not a sentence anyone reads for content, and
    counting it pushes the who-line to sentence three, which is where the
    brief's own 4.1 template puts it while the same section says the employers
    belong in the first or second. Read as first or second sentence *of the
    body*, the rule and the template agree, which is the only reading under
    which the template is not in breach of its own rule.
    """
    sents = tone.sentences(text)
    body = []
    for i, sentence in enumerate(sents):
        if i < 2:
            trimmed = _SALUTATION.sub("", sentence).strip()
            if not trimmed or _COURTESY.match(trimmed) or _SUBJECT_LINE.match(sentence):
                continue
            body.append(trimmed)
            continue
        body.append(sentence)
    return body


_HEAD_WORD = re.compile(r"[A-Za-z0-9&']+")
# How many words an employer name runs to. A pension fund's full legal name
# can be five; nothing a tracker has held is longer.
_MAX_NAME_WORDS = 5


def _employer_keys(head) -> set:
    """Every short word run in `head`, canonicalized as an employer name.

    Employer identity is company_key's job everywhere else in the repo, and it
    has to be here too: a substring match reported a bank's legal name as
    buried in a note that named it by its initials in its first sentence, and
    reported an employer buried in a note that wrote its name with "plc".
    """
    words = _HEAD_WORD.findall(head)
    keys = set()
    for i in range(len(words)):
        for n in range(1, _MAX_NAME_WORDS + 1):
            if i + n > len(words):
                break
            k = company_key.key(" ".join(words[i:i + n]))
            if len(k) > 1:
                keys.add(k)
    return keys


def employers_early(text, employers, within=2) -> list:
    """Which named employers fail to land in the first `within` body sentences.

    Recognizable brands are what earn the read, and a brand in sentence four is
    a brand the reader never got to. Returns the buried ones, so an empty list
    is a pass.
    """
    employers = [e for e in employers if str(e).strip()]
    if not employers:
        return []
    head = " ".join(body_sentences(text)[:within])
    keys = _employer_keys(head)
    buried = []
    for e in employers:
        if re.search(re.escape(str(e)), head, re.I):
            continue
        if company_key.key(str(e)) in keys:
            continue
        buried.append(e)
    return buried


def referrer_in_lead(text, referrer_name) -> bool:
    """Is the referrer named in the first sentence?

    Their full name or their given name both count: "Jane suggested I get in
    touch" is as warm as the full name and is how people write it.
    """
    given = tone.first_name(referrer_name)
    if not given:
        return False
    # The body's first sentence, not the message's: a greeting on its own line
    # would otherwise count as the lead and every warm intro would look buried.
    sents = body_sentences(text)
    lead = sents[0] if sents else ""
    # A referrer written "Xiu Mei (Sally) Ho" is named in the lead by
    # "Sally" or by "Xiu Mei Ho", and neither form carries the bracket.
    full = str(referrer_name).strip()
    bare = " ".join(re.sub(r"\([^)]*\)", " ", full).split())
    if any(form and re.search(re.escape(form), lead, re.I) for form in (full, bare)):
        return True
    return any(n and re.search(rf"\b{re.escape(n)}\b", lead, re.I)
               for n in (given, tone.first_name(bare)))


def _greeting(name) -> str:
    given = tone.first_name(name)
    if not given:
        raise ValueError("a message needs the recipient's name; an unaddressed note reads as a batch")
    # Directories and some exports write names in capitals: "Hi JANE," shouts.
    if given.isupper() and len(given) > 1:
        given = "-".join(p.capitalize() for p in given.split("-"))
    return f"Hi {given},"


# Words that open a clause with a capital only because they open it. Checked
# before any sign that the first word is a name, so "Saw Acme posted the role"
# still reads "Hi Sasha, saw Acme" and "It's" is a contraction, not a
# possessive.
_PLAIN = frozenset("""
a an the this that these those my your our their his her its some any no every each all
both either neither one another other such what which who whom whose how why where when
while if as because since after before until though although unless whether and but or
nor so yet for from with without within into onto upon about above below over under
between through during across along alongside around at by in on of off out to up down
via per like i me we us you they them he him she it is are was were be been am do does
did have has had can could will would shall should may might must not also still just
only even again already never always here there now then today tomorrow yesterday
tonight everyone everybody someone somebody anyone anybody nobody nothing everything
something anything let saw seen spotted noticed read heard met following thanks thank
congrats congratulations hope hoping welcome great good nice happy glad quick
""".split())

# A day, a month, or a place the profile names. "May" is left to _PLAIN,
# where "May I ask" puts it. The places are networking.py's PLACE_WORDS: a hook
# that opens on a city name would otherwise go through `_after_greeting` and
# greet a stranger with the city in lower case.
_PROPER = frozenset("""
monday tuesday wednesday thursday friday saturday sunday january february march april
june july august september october november december
""".split()) | frozenset(w.lower() for w in getattr(_NET, "PLACE_WORDS", ()))


def _names_something(sentence, first, keep=()) -> bool:
    """Does the clause open on a name, so its capital is spelling rather than position?

    A name the caller vouches for in `keep`, a possessive ("Acme's"), a day,
    month or place, or a word followed by another capitalized word, which is
    what a name of two words looks like: "Harbour Freight", "Claude Code". What
    this cannot see is a one-word name nobody vouched for, "Acme opened a
    role", which is what `keep` is for.
    """
    stem = re.sub(r"['’]s$", "", first)
    for term in keep or ():
        words = str(term or "").split()
        if words and words[0][:1].isupper() and words[0].lower().rstrip(",.") == stem.lower():
            return True
    if stem.lower() in _PLAIN:
        return False
    if stem != first or stem.lower() in _PROPER:
        return True
    rest = sentence.split()[1:2]
    return bool(rest) and rest[0][:1].isupper() and rest[0][1:2].islower()


def _after_greeting(text, keep=()) -> str:
    """A clause that follows "Hi Riley," stays lowercase, unless it opens on a name.

    `_sentence` capitalizes every piece it is given, which is right after a
    full stop and wrong after the greeting comma. The InMail opened "Hi Riley,
    Saw the Senior Data Scientist, Fraud opening on your team." Capital S after
    a comma is the kind of error a reader notices before they read the sentence.

    The same rule applied to a name is the same error from the other side: a
    first draft can read "Hi Quinn, acme's Future Opportunities". `keep` holds
    names the caller knows are in the text; see `_names_something` for the
    rest.
    """
    s = _sentence(text)
    if not s:
        return ""
    # Only lower a plain word. "SQL", "I", "NASA" and a name keep their case.
    #
    # The length guard on the isupper() branch is the whole difference between
    # an acronym and an article. A single capital letter is .isupper(), so "A"
    # was read as an acronym and a hook opening "A research and innovation seat"
    # rendered "Hi Taylor, A research and innovation seat", which is the same
    # visible typo this function exists to prevent, arriving from the other
    # direction. "I" is the one single letter that keeps its capital, so it is
    # named rather than inferred.
    first = s.split(" ", 1)[0].rstrip(",.")
    if first == "I" or (len(first) > 1
                        and (first.isupper() or first[1:].lower() != first[1:])):
        return s
    # A name keeps its capital only where the caller wrote one. A clause handed
    # over in lower case was written to follow the comma, and `_sentence` is
    # what put the capital there.
    if str(text).lstrip()[:1].isupper() and _names_something(s, first, keep):
        return s
    return s[0].lower() + s[1:]


class ReadsAsGenerated(ValueError):
    """A message carrying a phrase that marks it as machine-written."""


def _voice(kind: str, text: str) -> str:
    """Refuse a message that gives itself away, the way TooLong refuses length.

    The anti-cliche rules lived only in 03-writing-style.md. A rule a model is
    asked to follow is followed at whatever rate it is followed at, and nothing
    here measured the rate. The cost is specific: a senior person who reads
    "I hope this message finds you well" has already decided this was sent to
    forty people, and the reply rate on that is zero. Length is refused rather
    than truncated here for the same reason, so voice is refused too.

    Only hard findings raise. A soft one is a smell, and the composer is not
    the place to argue about rhythm.
    """
    try:
        import voice_check
    except ImportError:                       # pragma: no cover - path issue only
        return text
    hard = [f for f in voice_check.check(text) if f["severity"] == "hard"]
    if hard:
        raise ReadsAsGenerated(
            "%s reads as generated: %s. %s"
            % (kind, "; ".join(sorted({f["match"] for f in hard}))[:160],
               hard[0]["fix"]))
    return text


def connection_note(name, hook, who_line, work_auth=None, seniority="peer",
                    close=DEFAULT_CLOSE, opener=DEFAULT_OPENER, their=()) -> str:
    """The brief 4.1 shape, inside the 300 character limit or not at all.

    Hook first because a hook tied to that person is the only thing separating
    this from a sweep, the who-line second because the named employers have to
    be read before the reader decides, work authorization only when it removes
    an objection, and a soft close because a five-second reply is the ask.

    Raises TooLong rather than truncating. What to cut is a judgment about which
    detail matters least, and a truncator always cuts the close, which is the
    part that asks for the reply.
    """
    if not str(hook or "").strip():
        raise ValueError(
            "a connection note without a hook specific to this person is a template "
            "sweep, and senior people spot it instantly")

    if not str(who_line or "").strip():
        raise ValueError("a connection note has to say who the sender is, with employers named")
    if not str(close or "").strip():
        raise ValueError(
            "a connection note needs a close written for this person: it is the "
            "sentence that asks for the reply, and it is the one sentence a "
            "default ruins. A default close ends up identical in every message "
            "sent, which is what a form looks like")
    # With no opener the hook runs straight on from "Hi Wren," as one sentence,
    # so it must NOT be capitalized the way a standalone sentence is.
    # `_sentence()` upper-cases a leading lowercase letter, which is right
    # after a full stop and wrong after a comma. `nudge()` already carried this
    # fix; removing DEFAULT_OPENER gave `connection_note` the same problem and
    # it rendered "Hi Sasha, Saw you are recruiting", a visible typo in the
    # first line of an outbound message.
    #
    # Lowering it unconditionally was the same bug wearing the other face: a
    # hook that legitimately opens on "I", "SQL" or "NASA" came out as
    # "Hi Quinn, i moved teams last year", which is a typo in the one
    # line every reader sees. `_after_greeting()` already drew that
    # distinction for `inmail()` and is now the single place it is drawn.
    if opener:
        head = [f"{_greeting(name)} {opener}.", _sentence(hook)]
    else:
        head = [f"{_greeting(name)} {_after_greeting(hook, keep=their)}"]
    parts = head + [_sentence(who_line),
                    _checked_claim(work_auth, seniority) if work_auth else "",
                    _sentence(close)]
    note = " ".join(p for p in parts if p)
    # Checked on the assembled note, not on the hook. Taking the hook alone
    # forbade "I am an analyst in <City>" as an opening, which is the
    # plainest and best one there is, and pushed every draft into explaining the
    # reader's own job back to them. The note has to reach them; it does not
    # have to reach them in the first sentence.
    if not tone.reaches_them(note, their):
        raise NoteIsAllAboutTheSender(
            "nothing in this note reaches %s: it names no second person, and none "
            "of their= appears in it. A stranger reading it learns who you are and "
            "nothing about why you wrote to THEM. Name what you know about their "
            "work, or pass their= with the employer, product or event the note "
            "refers to." % (tone.first_name(name) or "them"))
    limit = schema.LIMITS["connection_note_chars"]
    if len(note) > limit:
        raise TooLong("connection note", len(note), limit)
    return _voice("connection note", note)


# ---------------------------------------------------------------------------
# The first message
# ---------------------------------------------------------------------------
#
# What the connection note is FOR: a reply, then a conversation, and out of the
# conversation a referral. A referral comes that way: a cold note, a reply, a
# role mentioned, the person's name on the referral.
#
# The failure mode is a note that has turned into an application in 300
# characters: "who I am, years at named employers, full working rights here, no
# sponsorship needed". Sent as a batch, that shape draws almost no replies. The
# notes that get answered have one shape: shared ground (a past employer or
# school in common, a field both had moved into), one modest line about the
# sender, a question about THEM ("how is the team set up?"), and a small ask:
# fifteen minutes, not a job. That is the shape below, and its defaults are the
# person's own words, from their networking.py: OPENER, ABOUT_ME, ASK.
#
# Two consequences for the rules that came before it:
#   - "hope you're well" and "I'd love to" were banned on a frequency count.
#     Frequency was never the problem: the notes that get replies carry both
#     phrases, and so do the ones that do not. What separates them is the body.
#     In a first note the person's own phrases (networking.py's OWN_VOICE) are
#     allowed; voice_check still flags them in letters.
#   - Work authorization comes out of first notes to anyone but a recruiter. It
#     costs about a fifth of the 300 characters and it is the sentence that
#     turns a conversation into an application. It belongs in the referral ask,
#     or in the reply to "are you able to work here?".

OPENER = getattr(_NET, "OPENER", "")
ABOUT_ME = getattr(_NET, "ABOUT_ME", "")
ASK = getattr(_NET, "ASK", "")

# The phrasings that turn a first note into an application. Every one of them
# has turned up in a draft queued for sending.
JOB_ASK = re.compile(
    r"\b(?:the|a) (?:job|role) I want\b"
    r"|\bI want (?:the |a |an |my next )?[\w'&,. -]{0,60}?\brole\b"
    r"|\bI want a role\b"
    r"|\bis (?:it|that|the role) on your team\b"
    r"|\b(?:does|would) it report into your team\b"
    r"|\bwho hires for (?:it|this|that)\b"
    r"|\bdo you recruit for (?:it|this|that)\b"
    r"|\bwho should I (?:speak|talk) to\b"
    r"|\b(?:is|are) (?:you|your team|the team|[A-Z][\w&.]*(?: [A-Z][\w&.]*){0,2}) hiring\b"
    r"|\bdoes the team hire\b"
    r"|\bwhere I want (?:my next role|to go(?: next)?|to take (?:it|that))\b"
    r"|\bis where I want\b"
    r"|\bwhat I want next\b"
    r"|\bthe direction I am aiming\b"
    # The plain forms, all of which passed: "Do you have any openings on your
    # team?", "Could you refer me", "I'd like to be considered for".
    r"|\b(?:any|have|has|got)\b[^.?!]{0,25}\b(?:openings?|vacanc\w+|open (?:roles?|positions?|reqs?))\b"
    r"|\brefer me\b"
    r"|\b(?:be )?considered for (?:the|a|an|your|this|that)\b"
    r"|\b(?:I am|I'm|I've been|I have been|I just)\s+appl(?:ying|ied)\b"
    r"|\b(?:are|is) (?:you|your team|the team) (?:recruiting|looking to (?:hire|add|grow))\b"
    r"|\bis (?:your|the) team growing\b", re.I)

# Common ground that is their hiring: a post, an open role. Beside it the
# default ABOUT_ME's looking clause turns the note back into a job ask, which
# the skill has always said to drop and nothing dropped.
HIRING_GROUND = re.compile(
    r"\b(?:hiring|recruiting|open (?:role|position|req)s?|vacanc\w+|job (?:post|ad|opening)s?)\b",
    re.I)
_LOOKING = re.compile(
    r"(?:,\s*|\s+)(?:and\s+)?(?:I'?m|I am|currently)\s+(?:looking|searching|open)\s+(?:for|to)\b.*$",
    re.I)


def _about_me_for(common_ground, about_me):
    """The person's ABOUT_ME, without its looking clause where the ground is their hiring."""
    if about_me == ABOUT_ME and about_me and HIRING_GROUND.search(str(common_ground or "")):
        return _LOOKING.sub("", about_me).strip(" ,")
    return about_me

# Work authorization in any of the shapes a draft arrives in: networking.py's
# WORK_AUTH_ANY.
_WORK_AUTH_ANY = _NET.WORK_AUTH_ANY


# Who counts as a recruiter for the one exception: their job is roles, so a
# role question and work authorization are what they need to hear.
RECRUITER_TITLE = re.compile(
    r"\b(?:recruit\w*|talent acquisition|talent partner|sourcer)\b|\btalent\s*@", re.I)


def is_recruiter(title) -> bool:
    return bool(RECRUITER_TITLE.search(str(title or "")))


def first_note_findings(text, recruiter=False) -> list:
    """Why this first note reads as asking for the job, as (rule, text) pairs."""
    if recruiter:
        return []
    out = [tone.Violation("asks_for_the_job", m.group(0)) for m in JOB_ASK.finditer(text)]
    out += [tone.Violation("work_auth_in_first_note", m.group(0))
            for m in _WORK_AUTH_ANY.finditer(text)]
    return out


# The person's own opener and close, allowed back into a first note: only the
# exact phrases networking.py's OWN_VOICE names. "hope this message finds you
# well" and the rest stay banned.
_OWN_VOICE = getattr(_NET, "OWN_VOICE", re.compile(r"(?!x)x"))


def _first_note_voice(text) -> str:
    try:
        import voice_check
    except ImportError:                       # pragma: no cover - path issue only
        return text
    hard = [f for f in voice_check.check(text) if f["severity"] == "hard"
            and not (f["rule"] == "house-style" and _OWN_VOICE.match(f["match"]))]
    if hard:
        raise ReadsAsGenerated(
            "first note reads as generated: %s. %s"
            % ("; ".join(sorted({f["match"] for f in hard}))[:160], hard[0]["fix"]))
    return text


def first_note(name, common_ground, question, about_me=ABOUT_ME, ask=ASK,
               opener=OPENER, recruiter=False, seniority="peer", their=()) -> str:
    """The first message to anyone, as a connection request: a reply is the goal.

        Hi Robin, hope you're well. <common ground>. <about me>. <question>? <ask>.

    `common_ground` is the one true thing that links the sender to them, or
    the one thing about their work that prompted the note: a shared employer or
    school, a team, a talk, a post. Required, because without it the note is a
    sweep.

    `question` is about THEM and answerable in a line: how they got into the field,
    how the team is set up, what the work is like. Never whether they are
    hiring, and never about a role the sender wants: that is the referral ask, later,
    once there is a conversation to ask inside.

    `about_me` and `ask` default to the person's own words (their networking.py). Pass `ask=None` when the
    question already carries the ask. `recruiter=True` is for a recruiter, whose
    job is roles: the job-ask rules lift and work authorization is added.
    """
    if not str(common_ground or "").strip():
        raise ValueError(
            "a first note needs the common ground: the shared employer, school or "
            "move, or the one thing about their work that prompted the note")
    q = " ".join(str(question or "").split())
    if not q:
        raise ValueError(
            "a first note needs a question about them, answerable in a line: it is "
            "what gets the reply")
    q = q.rstrip(".!")
    if not q.endswith("?"):
        q += "?"
    if q[0].islower():
        q = q[0].upper() + q[1:]
    about_me = _about_me_for(common_ground, about_me)
    parts = [f"{_greeting(name)} {opener}." if opener else _greeting(name),
             _sentence(common_ground), _sentence(about_me) if about_me else "",
             work_auth_line(seniority) if recruiter else "",
             q, _sentence(ask) if ask else ""]
    note = " ".join(p for p in parts if p)
    findings = first_note_findings(note, recruiter=recruiter)
    if findings:
        raise AsksForTheJob(
            "this first note asks for the job: %s. A first note asks for a "
            "conversation; the role belongs in compose.referral_ask() once they "
            "have replied." % "; ".join(sorted({v.text for v in findings})))
    if not tone.reaches_them(note, their):
        raise NoteIsAllAboutTheSender(
            "nothing in this note reaches %s. Put what links you to them in "
            "common_ground, or pass their= with the employer or event it names."
            % (tone.first_name(name) or "them"))
    limit = schema.LIMITS["connection_note_chars"]
    if len(note) > limit:
        raise TooLong("first note", len(note), limit)
    return _first_note_voice(note)


def referral_ask(name, context, role, link, close=None, work_auth=None,
                 seniority="peer") -> str:
    """The ask the first note exists to earn, sent once they have engaged.

    Only inside a live thread: after a reply, a call or an offer of help. Asked
    of a stranger it is the cold application the first note was rebuilt to
    stop sending. It names one role and links it, so the referrer can act from
    the message alone, and it makes saying no easy, because a referral given
    reluctantly is worth less than none.

    `context` is what they already did or said ("thanks again for the chat on
    Tuesday"), one line, no restating. `role` names the role and employer;
    `link` is the posting.
    """
    for what, value in (("context", context), ("role", role), ("link", link)):
        if not str(value or "").strip():
            raise ValueError(f"referral_ask needs {what}")
    if not re.match(r"https?://", str(link).strip()):
        raise ValueError("link must be the posting's URL, so they can act from the message")
    close = close or ("Would you be comfortable referring me for it? Happy to send my "
                      f"{NOUN} and a couple of lines you can forward, and no problem at "
                      "all if not.")
    # The link goes on its own line at the end: a URL closing a sentence picks
    # up the full stop, and LinkedIn then links to a page that does not exist.
    # Work authorization belongs here, not in a first note: the referrer
    # forwards this message, and the hiring side's first question is whether
    # the candidate can work there.
    auth = _checked_claim(work_auth, seniority) if work_auth else ""
    text = " ".join(p for p in (f"{_greeting(name)} {_after_greeting(context)}",
                                _sentence(f"The {role} looks like a strong fit for what we talked about"),
                                auth, _sentence(close)) if p)
    text = f"{text}\n\n{link.strip()}"
    words = len(text.split())
    high = KIND_LIMITS["referral_ask"]["words"][1]
    if words > high:
        raise TooLong("referral ask", words, high, unit="words")
    return text


def nudge(name, reason, close=None, opener=None, their=()) -> str:
    """One short chase on a thread that went quiet, capped below the original.

    The cap is the argument: a message that was ignored at 300 characters is not
    going to land at 900, and the longer it gets the more it reads as arguing
    with someone who has already declined to engage. Seniority makes this worse,
    not better. So a nudge gets less room than the note it chases, and `reason`
    is the only substantive slot: something that has changed, not a restatement
    of the first message.

    `their` is the names the reason may open on, their employer first, the same
    argument `connection_note` takes. A reason opening "Acme opened a
    role" is otherwise indistinguishable from one opening "Saw the role".

    Raises TooLong, like everything else here, rather than trimming.
    """
    if not str(reason or "").strip():
        raise ValueError(
            "a nudge with no new reason is a check-in, and a check-in is why the "
            "first message went unanswered; give them something to answer")
    # No opener means the reason runs straight on from "Hi Robin," as one
    # sentence, so it must NOT be capitalized the way a standalone sentence is.
    # _sentence() upper-cases a leading lowercase letter, which is right after a
    # full stop and wrong after a comma: it rendered "Hi Robin, Since we
    # connected", a visible typo in an outbound message. `_after_greeting()`
    # lowers only a plain word, so a reason opening on "I" or "SQL" keeps its
    # case instead of arriving as "Hi Robin, i have since".
    if opener:
        parts = [f"{_greeting(name)} {opener}.", _sentence(reason)]
    else:
        parts = [f"{_greeting(name)} {_after_greeting(reason, keep=their)}"]
    if close:
        parts.append(_sentence(close))
    text = " ".join(p for p in parts if p)
    limit = schema.LIMITS["nudge_chars"]
    if len(text) > limit:
        raise TooLong("nudge", len(text), limit)
    return text


# The subjects every mass InMail carries. A subject is the one line read before
# deciding to open the message, so it names the common ground or the question.
_GENERIC_SUBJECT = re.compile(
    r"^\s*(?:re:\s*)?(?:hi|hello|hey|quick question|a question|question|introduction|intro|"
    r"networking|connecting|let'?s connect|job (?:inquiry|enquiry|application)|"
    r"opportunit\w*|career\w*(?: advice)?|role|position|following up|touching base)\W*$", re.I)


def inmail_subject(subject, recruiter=False) -> str:
    """The InMail's subject line: a few words naming why them, never the job.

    LinkedIn shows the subject before the message, and nothing ever wrote one.
    Held to the first note's rules: it is the first thing they read.
    """
    s = " ".join(str(subject or "").split()).rstrip(".")
    if not s:
        raise ValueError(
            "an InMail needs a subject: it is read before the message is opened. Name the "
            "common ground or the question in a few words")
    if _GENERIC_SUBJECT.match(s):
        raise ValueError(
            f"{s!r} is the subject of every mass InMail; name the common ground or the "
            "question instead")
    words, limit = len(s.split()), schema.LIMITS["inmail_subject_words"]
    if words > limit:
        raise TooLong("InMail subject", words, limit, unit="words")
    if len(s) > schema.LIMITS["inmail_subject_chars"]:
        raise TooLong("InMail subject", len(s), schema.LIMITS["inmail_subject_chars"])
    findings = first_note_findings(s, recruiter=recruiter)
    if findings:
        raise AsksForTheJob("this InMail subject asks for the job: %s"
                            % "; ".join(sorted({v.text for v in findings})))
    return s


def inmail(name, subject, common_ground, question, evidence, about_me=ABOUT_ME, ask=ASK,
           opener=OPENER, recruiter=False, seniority="peer", their=(), sign_off=None) -> str:
    """The first note with room in it, and a subject line.

        Subject: <subject>

        Hi Sasha, hope you're well. <common ground>.

        <about me>.

        <evidence>.

        <question>? <ask>.

    The same moves as `first_note()` and the same rules (never a job ask, no work
    authorization except to a recruiter, it has to reach them), plus one
    paragraph of evidence: a named piece of work, its scale, an outcome. That
    paragraph is what the credit buys; without it this is a connection note that
    cost a scarce credit. The word limit is a ceiling, not a target.
    """
    for what, value in (("common_ground", common_ground), ("question", question),
                        ("evidence", evidence)):
        if not str(value or "").strip():
            raise ValueError(
                f"an InMail needs {what}: the common ground and a question about them, as "
                "in a first note, and one paragraph of concrete evidence (a named piece of "
                "work, its scale, an outcome), which is what the credit buys")
    subj = inmail_subject(subject, recruiter=recruiter)
    q = " ".join(str(question).split()).rstrip(".!")
    q = (q[0].upper() + q[1:]) if q[0].islower() else q
    q = q if q.endswith("?") else q + "?"
    about_me = _about_me_for(common_ground, about_me)
    paragraphs = [
        " ".join(p for p in (f"{_greeting(name)} {opener}." if opener else _greeting(name),
                             _sentence(common_ground)) if p),
        " ".join(p for p in (_sentence(about_me) if about_me else "",
                             work_auth_line(seniority) if recruiter else "") if p),
        _sentence(evidence),
        " ".join(p for p in (q, _sentence(ask) if ask else "") if p),
        " ".join(str(sign_off or "").split()),
    ]
    body = "\n\n".join(p for p in paragraphs if p)
    findings = first_note_findings(body, recruiter=recruiter)
    if findings:
        raise AsksForTheJob(
            "this InMail asks for the job: %s. It asks for a conversation; the role belongs "
            "in compose.referral_ask() once they have replied."
            % "; ".join(sorted({v.text for v in findings})))
    if not tone.reaches_them(body, their):
        raise NoteIsAllAboutTheSender(
            "nothing in this InMail reaches %s. Put what links you to them in common_ground, "
            "or pass their= with the employer or event it names." % (tone.first_name(name) or "them"))
    if len(body) > INMAIL_CHAR_LIMIT:
        raise TooLong("InMail", len(body), INMAIL_CHAR_LIMIT)
    high = schema.LIMITS["inmail_words"][1]
    if high and len(body.split()) > high:
        raise TooLong("InMail", len(body.split()), high, unit="words")
    return f"Subject: {subj}\n\n{_first_note_voice(body)}"


def email(name, subject, context, body, ask, sign_off=None, attachment=True,
          seniority="peer") -> str:
    """The brief 4.3 shape, for when someone gives an address.

    `sign_off` defaults to the register's own closing. Passing False leaves it
    off deliberately; passing None used to leave it off by accident, which is
    an email that greets the reader by name and then stops.

    The context paragraph is not padding. They gave the address in a LinkedIn
    thread they will not go back and reread, so the email has to carry enough of
    that thread to stand on its own. Trimming it to one line is the failure this
    shape exists to prevent.

    The attachment is named in the body so the filename is visible to the tone
    check: a file called First_Last_CV_Employer.pdf contradicts a message that
    says resume, and the reader sees both. The word is the person's
    (documents.noun).
    """
    if not str(context or "").strip():
        raise ValueError(
            "the email needs a context line saying where this conversation started; "
            "they will not go back to LinkedIn to work it out")
    blocks = []
    if subject:
        blocks.append(f"Subject: {' '.join(str(subject).split())}")
    blocks.append(_greeting(name))
    blocks.append(_sentence(context))
    if str(body or "").strip():
        blocks.append(str(body).strip())
    if str(ask or "").strip():
        blocks.append(_sentence(ask))
    if attachment:
        # The default used to be the string "resume", which wrote "My resume is
        # attached (resume)." into every email composed without a filename. A
        # parenthetical is only worth writing when it names the actual file.
        named = "" if attachment is True else " ".join(str(attachment).split())
        blocks.append(f"My {NOUN} is attached ({named})."
                      if named and named.lower() not in ("resume", "cv", NOUN.lower())
                      else f"My {NOUN} is attached.")
    # `False` is how a caller says no sign-off on purpose; `None` takes the
    # register default rather than silently ending the email on a full stop.
    if sign_off is None:
        sign_off = SIGN_OFF["senior" if tone.is_senior(seniority) else "peer"]
    if sign_off:
        blocks.append(str(sign_off).strip())
    return "\n\n".join(b for b in blocks if b)


def warm_intro(referrer_name, name, body, close=None, work_auth=None,
               seniority="peer", channel="message") -> str:
    """The brief 4.4 shape: the referrer's name in the first sentence, always.

    This is the highest-converting message in the system and the entire reason
    it converts is that the reader recognises a name they trust before they
    decide whether to keep reading. A body that opens with the sender's own
    background and reaches the referrer in sentence three has thrown that away,
    so it is refused here rather than sent.

    `channel` decides the length, and getting it wrong is how a referral gets
    wasted. INTRO_WORDS assumes a message pane, which is right when the referrer
    made the introduction or the target is already a connection. It is wrong
    whenever the instruction was "connect with X", because then the message IS
    the connection request and LinkedIn cuts it at 300 characters like any other.
    A warm intro drafted at message length for someone the referrer said to
    *connect with* would be truncated mid-way, and the strongest asset in the
    book spent on a broken sentence.
    """
    if channel not in ("message", "connection"):
        raise ValueError("channel is 'message' (a message pane) or 'connection' "
                         "(a connection request, capped at 300 characters)")
    if not str(referrer_name or "").strip():
        raise ValueError("warm_intro needs the referrer's name; without one this is a cold message")
    if not str(body or "").strip():
        raise ValueError("warm_intro needs a body naming the referrer in its first sentence")
    auth = _checked_claim(work_auth, seniority) if work_auth else ""
    text = " ".join(p for p in (f"{_greeting(name)} {_after_greeting(body, keep=(referrer_name,))}".strip(),
                                auth,
                                _sentence(close) if close else "") if p)
    if not referrer_in_lead(text, referrer_name):
        lead = tone.sentences(text)[0] if tone.sentences(text) else text
        raise BuriedReferral(
            f"{referrer_name} is not named in the first sentence: {lead!r}. "
            f"The referral is the whole reason this message gets read; move the name "
            f"to the opening sentence and recompose.")
    if channel == "connection":
        limit = schema.LIMITS["connection_note_chars"]
        if len(text) > limit:
            raise TooLong("warm intro sent as a connection request", len(text), limit)
    else:
        high = INTRO_WORDS[1]
        if high and len(text.split()) > high:
            raise TooLong("warm intro", len(text.split()), high, unit="words")
    return text


def register(text, seniority) -> str:
    """Calibrate the surface of a finished draft to the recipient (brief 4.5).

    Same content, different surface. Two things change and nothing else:
    work-authorization phrasing becomes the approved wording for the register,
    and a senior recipient's copy loses its exclamation marks and its "Hey".
    Rewriting more than that would be editing the writer's argument, which is
    not this function's business.

    Refuses outright when the draft claims citizenship or permanent residency.
    That is not a register problem and no phrasing fixes it.
    """
    s = str(text or "")
    if not s.strip():
        return s
    m = _UNSUPPORTABLE.search(s)
    if m:
        raise UnsupportedClaim(
            f"{m.group(0)!r} is not something the profile supports: "
            f"{getattr(_NET, 'UNSUPPORTED_WHY', 'the profile does not hold that status')}.")
    approved = WORK_AUTH["senior" if tone.is_senior(seniority) else "peer"]
    s = _WORK_AUTH_CLAUSE.sub(lambda _m: approved, s)
    if tone.is_senior(seniority):
        s = re.sub(r"!+", ".", s)
        s = re.sub(r"^hey\b", "Hi", s, flags=re.I | re.M)
    return s


def validate(message, kind, name=None, seniority="peer", employers=(),
             referrer=None, their_message=None, recruiter=False) -> list:
    """Every reason this draft should not be sent, as (rule, offending_text).

    What the skill layer runs before showing the user anything. Returns instead
    of raising: a draft usually breaks more than one rule, and a writer given
    one problem at a time rewrites the same message four times.
    """
    k = _KIND_ALIASES.get(str(kind or "").strip().lower())
    if k is None:
        raise ValueError(
            f"unknown message kind {kind!r}; expected one of "
            f"{sorted(set(_KIND_ALIASES.values()))}. A typo here would skip the "
            f"length check entirely.")
    text = str(message or "")
    # A reply goes to somebody who has already written back, which is what
    # `live_thread` means. Without it a reply such as "That's great, thank you
    # Riley" fails on the one rule that is scoped to cold messages.
    out = list(tone.check(text, recipient_seniority=seniority, name=name,
                          live_thread=(k in ("reply", "referral_ask"))))
    if k in ("connection", "inmail"):
        out += first_note_findings(text, recruiter=recruiter)
    if k == "inmail":
        first = text.lstrip().split("\n", 1)[0]
        if not _SUBJECT_LINE.match(first):
            out.append(tone.Violation("no_subject", "an InMail with no 'Subject:' line"))
        elif _GENERIC_SUBJECT.match(_SUBJECT_LINE.sub("", first)):
            out.append(tone.Violation("generic_subject", first.strip()))
    limits = KIND_LIMITS[k]
    chars, words = len(text), len(text.split())
    if "chars" in limits and chars > limits["chars"]:
        out.append(tone.Violation("too_long", f"{chars} characters, limit {limits['chars']}"))
    if "words" in limits:
        low, high = limits["words"]
        if high and words > high:
            out.append(tone.Violation("too_long", f"{words} words, limit {high}"))
        elif low and words < low:
            out.append(tone.Violation("too_short", f"{words} words, at least {low}"))
    for buried in employers_early(text, employers):
        out.append(tone.Violation("employers_buried", str(buried)))
    if referrer and not referrer_in_lead(text, referrer):
        out.append(tone.Violation("referrer_buried", str(referrer)))
    if their_message:
        restated = tone.restate_ratio(text, their_message)
        if restated.flagged:
            out.append(tone.Violation(
                "restates_their_points",
                f"{restated.ratio:.2f} of the content words are theirs: "
                f"{', '.join(restated.terms)}"))

    # `_voice()` already refuses a composed message that reads as generated.
    # This is the other path: a draft written freehand by the model and handed
    # straight here, which got `tone.check` and nothing else. Same rules, same
    # message, different door, and the door without the check is the one a
    # model uses when the composer's shape does not fit what it wants to say.
    for f in _voice_findings(text, k):
        out.append(tone.Violation("reads_as_generated",
                                  f"{f['rule']}: {f['match']} -> {f['fix']}"))
    return out


# A light "hope you're well" inside a live thread is allowed: stripped from a
# follow-up it can read as an ultimatum, and "Hope you're well. Any update on
# the timing?" is a normal thing to send. The finding that banned it (the same
# opener on most messages of a batch) was about FIRST messages to strangers, so
# the ban stays for every cold kind and lifts for a reply. Without this,
# validate() refused the sentence the skill tells a reply to use, and writers
# dressed it up as "hope the week has been a good one" to get past the check.
_THREAD_WARMTH = re.compile(r"\s*hope\b", re.I)


def _voice_findings(text: str, kind: str | None = None) -> list:
    """voice_check's HARD findings, or nothing if it cannot be imported.

    Soft findings are dropped deliberately, the same way `_voice()` drops them.
    `uniformity` is a statistical read that needs a real sample and a
    connection note is four short sentences by design, so every one of them
    trips it, and a checker that always fires is a checker nobody reads.
    """
    try:
        import voice_check
    except ImportError:
        return []
    hard = [f for f in voice_check.check(text) if f["severity"] == "hard"]
    if kind in ("connection", "inmail"):
        hard = [f for f in hard
                if not (f["rule"] == "house-style" and _OWN_VOICE.match(f["match"]))]
    if kind in ("reply", "referral_ask"):
        hard = [f for f in hard
                if not (f["rule"] == "house-style" and _THREAD_WARMTH.match(f["match"]))]
    return hard
