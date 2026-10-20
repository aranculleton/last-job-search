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

import advice  # noqa: E402
import company_key  # noqa: E402
import person  # noqa: E402
import schema  # noqa: E402
import tone  # noqa: E402

# The person's voice, work authorization and places: profile/networking.py.
_NET = person.module("networking")
_ROLES = person.module("roles") if person.exists("roles.py") else None
_SKILLS = person.module("skills") if person.exists("skills.py") else None
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


class UngroundedNote(ValueError):
    """The common ground rests on nothing that was read about them (reading.grounded)."""


class UnconfirmedReading(ValueError):
    """A note that says the sender read, saw or watched something of theirs, when the
    sender has not said they did. "I saw your package on GitHub" went to someone the
    person had found through a search of the team: "clearly that's not how I found him"."""


class UnrecordedReaction(ValueError):
    """Drafting again over a reaction from the person that nobody recorded
    (tools/learned.py pending)."""


def _no_reaction_waiting(what: str = "compose") -> None:
    """Refuse to draft while a reaction from the person waits to be recorded."""
    try:
        import learned
        msg = learned.refuse_over_pending(what)
    except (ImportError, SystemExit):
        return
    if msg:
        raise UnrecordedReaction(msg)


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
# The words the person greets and asks with. Defaults are how anyone starts;
# once the person says how they would put it, their words go in
# profile/networking.py and every message uses them (tools/learned.py records
# why). GREETING opens every message; REFERRAL_LINE ({role} filled in) and
# REFERRAL_CLOSE ({noun} filled in) are the two sentences of a referral ask.
GREETING = str(getattr(_NET, "GREETING", "") or "Hi").strip()
REFERRAL_LINE = str(getattr(_NET, "REFERRAL_LINE", "") or
                    "The {role} looks like a strong fit for what we talked about")
REFERRAL_CLOSE = str(getattr(_NET, "REFERRAL_CLOSE", "") or
                     "Would you be comfortable referring me for it? Happy to send my {noun} "
                     "and a couple of lines you can forward, and no problem at all if not.")

_SALUTATION = re.compile(
    r"^(?:hi|hey|hello|dear|good (?:morning|afternoon|evening)|" + re.escape(GREETING) +
    r")\b[^,\n]{0,40},\s*", re.I)
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


def _names_employer(sentence, employer) -> bool:
    return bool(re.search(re.escape(str(employer)), sentence, re.I)) \
        or company_key.key(str(employer)) in _employer_keys(sentence)


def employers_first(text, employers, within=2) -> str:
    """The note with the sentences naming its buried employers moved up, to follow the
    greeting, or "" when that cannot be done by moving sentences alone (no sentence
    names one, or the move still leaves one buried).

    validate() said only "employers_buried", and a writer had to work out what to
    change (2026-10-19). This is the change, made mechanically where it can be: the
    same sentences, in another order, each word kept as written.
    """
    buried = employers_early(text, employers, within)
    if not buried:
        return ""
    # Each sentence as the writer typed it (tone.sentences straightens curly quotes),
    # and the greeting with its own line break when it has one.
    text = str(text or "")
    plain, sents, at = tone._plain(text), [], 0
    for s in tone.sentences(text):
        i = plain.find(s, at)
        sents.append(text[i:i + len(s)] if i >= 0 else s)
        at = i + len(s) if i >= 0 else at
    m = _SALUTATION.match(sents[0]) if sents else None
    if not m:
        return ""
    rest = sents[0][m.end():].strip()
    joined = bool(rest) and not _COURTESY.match(rest)
    if joined:
        # "Hi Robin, saw your talk on ...": the greeting runs into the first sentence.
        # That sentence takes a capital when it moves down, and the one moved up follows
        # the greeting the way _after_greeting writes any clause after it.
        lead, body = [], [rest[:1].upper() + rest[1:]] + sents[1:]
    else:
        lead = [sents[0]]
        if not rest and len(sents) > 1 and _COURTESY.match(sents[1]):
            lead.append(sents[1])
        body = sents[len(lead):]
    up = [s for s in body if any(_names_employer(s, e) for e in buried)]
    if not up or up == body[:len(up)]:
        return ""
    order = up + [s for s in body if s not in up]
    if joined:
        out = " ".join([f"{m.group(0).strip()} {_after_greeting(order[0])}"] + order[1:])
    else:
        i = text.find(lead[-1])
        out = (text[:i + len(lead[-1])] if i >= 0 else " ".join(lead)) + " " + " ".join(order)
    return "" if employers_early(out, employers, within) else out


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
    return any(n and re.search(rf"(?<!\w){re.escape(n)}(?!\w)", lead, re.I)
               for n in (given, tone.first_name(bare)))


def _greeting(name) -> str:
    given = tone.first_name(name)
    if not given:
        raise ValueError("a message needs the recipient's name; an unaddressed note reads as a batch")
    # Directories and some exports write names in capitals: "Hi JANE," shouts.
    if given.isupper() and len(given) > 1:
        given = "-".join(p.capitalize() for p in given.split("-"))
    return f"{GREETING} {given},"


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


# Names a nudge or a note opens on that are one capitalized word: an employer, a
# tool. "Hi Robin, Acme opened a data role" came out "Hi Robin, acme opened...",
# because one word with a capital looks the same as a sentence-starting "Saw".
# The common tools are here; the person's own names come from the profile and
# the state files (`_known_names`).
_TOOL_NAMES = frozenset("""
python excel tableau looker snowflake databricks azure google microsoft amazon apple meta
salesforce jira slack spark airflow kubernetes docker terraform claude anthropic linux
oracle sap workday hubspot stripe figma notion github gitlab redshift bigquery
""".split())


def _first_word(name) -> str:
    words = re.findall(r"[A-Za-z][\w&'.-]*", str(name or ""))
    return words[0].lower().rstrip(".'") if words and words[0][:1].isupper() else ""


_KNOWN: set | None = None


def _known_names() -> frozenset:
    """One-word names this person's messages may open on, lowercased.

    The tools list above, the profile's employers and skills, and every company
    in the contact book and the tracker. Read once per process.
    """
    global _KNOWN
    if _KNOWN is None:
        names = set(_TOOL_NAMES)
        for role in getattr(_ROLES, "ROLES", ()) or ():
            for n in [role.get("employer")] + list(
                    [role.get("known_as")] if isinstance(role.get("known_as"), str)
                    else role.get("known_as") or []):
                names.add(_first_word(n))
        for item in getattr(_SKILLS, "ITEMS", ()) or ():
            names.add(_first_word(item[1] if len(item) > 1 else ""))
        try:
            import csv
            for f in ("network_contacts.csv", "job_search_tracker.csv"):
                with open(person.state(f), newline="", encoding="utf-8") as fh:
                    for r in csv.DictReader(fh):
                        names.add(_first_word(r.get("company")))
        except (OSError, ValueError):
            pass
        names.discard("")
        _KNOWN = names - _PLAIN
    return frozenset(_KNOWN)


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
    if stem != first or stem.lower() in _PROPER or stem.lower() in _known_names():
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
    hard = voice_check.hard(text)
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
    _no_reaction_waiting("connection note")
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
# has turned up in a draft queued for sending. Two kinds, each with what to write
# instead: saying the role the sender wants (allowed where SAY_THE_ROLE says so for this
# reader, as it is for a decision-maker by default), and asking for the job, which only
# a recruiter is asked. The fix is named with the phrase: "asks for the job" alone sent a
# writer back to guess which of several sentences tripped it (2026-10-20).
_SAY_ROLE_FIX = ("say the work you are looking for, not that you want their role; or allow "
                 "it for this kind of reader (profile/networking.py SAY_THE_ROLE)")
_POINTER_FIX = ("ask for a pointer instead: \"would you know the right person to speak to "
                "about <the work>?\" (shape=\"pointer\")")
_LATER_FIX = "that is the referral ask, after they reply: compose.referral_ask()"
_OPEN_FIX = ("to a decision-maker, ask openly: \"would love to hear if you have anything coming "
             "up\"; to a peer, ask about them, or for a pointer")
JOB_ASKS = (
    # (pattern, kind, what to write instead). "wants" is saying the role wanted.
    (r"\b(?:the|a) (?:job|role) I want\b", "wants", _SAY_ROLE_FIX),
    # Within one clause: "the work I want to be doing, and I'm looking for my next role" is
    # two clauses, and the second is allowed (2026-10-20).
    # The words between are the role's own ("a senior data science role"): never "to",
    # "your" or "how", which make it a sentence about something else ("I want to
    # understand how your role changed"), and never across a full stop.
    (r"\bI want (?:the |a |an |my next )?(?:(?!(?:to|your|their|his|her|how|what|why)\b)"
     r"[\w'&-]+ ){0,6}role\b", "wants", _SAY_ROLE_FIX),
    (r"\bI want to (?:move|get|step|go|transition|pivot|switch) (?:in)?to (?:a|an|the)\b"
     r"[^.?!,]{0,40}\brole\b", "wants", _SAY_ROLE_FIX),
    (r"\bwhere I want (?:my next role|to go(?: next)?|to take (?:it|that))\b", "wants", _SAY_ROLE_FIX),
    (r"\bis where I want\b", "wants", _SAY_ROLE_FIX),
    (r"\bwhat I want next\b", "wants", _SAY_ROLE_FIX),
    (r"\bthe direction I am aiming\b", "wants", _SAY_ROLE_FIX),
    (r"\bis (?:it|that|the role) on your team\b", "asks", _OPEN_FIX),
    (r"\b(?:does|would) it report into your team\b", "asks", _OPEN_FIX),
    (r"\bwho hires for (?:it|this|that)\b", "asks", _POINTER_FIX),
    (r"\bdo you recruit for (?:it|this|that)\b", "asks", _POINTER_FIX),
    (r"\bwho should I (?:speak|talk) to\b", "asks", _POINTER_FIX),
    # An employer's name is capitalized however the pattern is compiled: "they are slow
    # hiring" is not a question about their hiring.
    (r"\b(?:is|are) (?:you|your team|the team|(?-i:[A-Z])[\w&.]*(?: (?-i:[A-Z])[\w&.]*){0,2})"
     r" hiring\b",
     "asks", _OPEN_FIX),
    (r"\bdoes the team hire\b", "asks", _OPEN_FIX),
    # The plain forms, all of which passed: "Do you have any openings on your team?",
    # "Could you refer me", "I'd like to be considered for".
    (r"\b(?:any|have|has|got)\b[^.?!]{0,25}\b(?:openings?|vacanc\w+|open (?:roles?|positions?|reqs?))\b",
     "asks", _OPEN_FIX),
    (r"\brefer me\b", "asks", _LATER_FIX),
    (r"\b(?:be )?considered for (?:the|a|an|your|this|that)\b", "asks", _LATER_FIX),
    (r"\b(?:I am|I'm|I've been|I have been|I just)\s+appl(?:ying|ied)\b", "asks", _LATER_FIX),
    (r"\b(?:are|is) (?:you|your team|the team) (?:recruiting|looking to (?:hire|add|grow))\b",
     "asks", _OPEN_FIX),
    (r"\bis (?:your|the) team growing\b", "asks", _OPEN_FIX),
    # Plain asks that passed: "Is the <role> still open?", "I'd love to apply",
    # "Would you consider me for the role?", "I'm interested in the <role> opening".
    (r"\b(?:role|position|opening|job|req)\b[^.?!]{0,30}\bstill open\b", "asks", _LATER_FIX),
    # Applying for something, not applying a method: "I like to apply statistics" passes.
    (r"\b(?:love|like|keen|want|hoping) to apply(?=\s*(?:[.!?,]|$|for\b|to (?:the|a|an|your|"
     r"this|that|one)\b|there\b|here\b|now\b))|\bconsider me\b", "asks", _LATER_FIX),
    # Interest in a role, not in their move into one ("your move from finance into a
    # product role" is about their path).
    (r"\binterested in (?:the|your|this|that|an?) (?:(?!(?:move|moving|switch\w*|transition\w*|"
     r"path|journey|career|from|into|time)\b)[\w'&-]+ ){0,6}(?:role|position|opening|vacancy|job)\b",
     "asks", _LATER_FIX),
)
_JOB_ASKS = [(re.compile(rx, re.I), kind, fix) for rx, kind, fix in JOB_ASKS]
# All of them as one pattern, as callers have always used it.
JOB_ASK = re.compile("|".join(f"(?:{rx})" for rx, _k, _f in JOB_ASKS), re.I)

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
# A recruiter by job, not anyone whose snippet says "recruiting": a hiring
# manager described as "recruiting Senior Data Scientists" lifted the first-note
# rules for a note to them, and an agency recruiter whose title read "Connecting
# Data & AI Talent" kept them.
RECRUITER_TITLE = re.compile(
    r"\brecruit(?:er|ers|ment)\b|\brecruiting (?:coordinator|manager|lead|partner|specialist|"
    r"director|consultant|team|operations)\b|\btalent (?:acquisition|partner|scout|sourcer|"
    r"lead|manager|director|advisor)\b|\bsourcer\b|\bheadhunter\b|\bexecutive search\b"
    r"|\b(?:connecting|placing)\b[^,;]{0,40}\btalent\b|\btalent\s*@"
    # The department as the title: "Recruiting, <Company>", "Recruitment | <Company>",
    # "Recruiting at <Company>". The verb with a role after it is a hiring manager.
    r"|^\W*recruit(?:ing|ment)\b(?!\s+(?:senior|junior|lead|staff|principal|data|"
    r"talented|great|engineers?|analysts?|scientists?|developers?|designers?|managers?)\b)", re.I)


def is_recruiter(title) -> bool:
    return bool(RECRUITER_TITLE.search(str(title or "")))


# ---------------------------------------------------------------- who reads it
#
# Three kinds of reader, told different things. A recruiter's job is roles. A
# decision-maker can place someone, and the message that drew a reply from one within
# three hours said plainly who the sender was, that they needed no sponsorship and that
# they could start quickly, and asked "if you have anything coming up". A peer can only
# advise, so they get who the sender is, one reason tied to their own path, and a plain
# request for a short call or a pointer. Each setting is the person's, in
# profile/networking.py, per reader type, and a message can override it.
READER_TYPES = ("recruiter", "decision_maker", "peer")


_YES = {"true", "yes", "y", "1", "on"}
_NO = {"false", "no", "n", "0", "off", ""}


def _as(value, like):
    """A profile setting as the type of its default: "no" is False and "130" is 130, and a
    value that cannot be read keeps the default rather than breaking every import."""
    if isinstance(like, bool):
        if isinstance(value, str):
            v = value.strip().lower()
            return True if v in _YES else False if v in _NO else like
        return bool(value)
    if isinstance(like, int):
        try:
            return int(str(value).strip())
        except (TypeError, ValueError):
            return like
    return value


def _per_reader(got, default: dict) -> dict:
    out = dict(default)
    if isinstance(got, dict):
        out.update({k: _as(v, default[k]) for k, v in got.items() if k in default})
    return out


# Whether a first message states work authorization. The profile's own rule: "for a
# recruiter or anyone whose reply could be about a role"; left out for a peer, who keeps
# it for the reply or the referral stage.
ELIGIBILITY = _per_reader(getattr(_NET, "ELIGIBILITY", None),
                          {"recruiter": True, "decision_maker": True, "peer": False})
# Whether a first message may say the role the sender wants. Asking for the job stays a
# recruiter's alone.
SAY_THE_ROLE = _per_reader(getattr(_NET, "SAY_THE_ROLE", None),
                           {"recruiter": True, "decision_maker": True, "peer": False})
# How long an InMail need be for each reader: past this it is warned, never refused. The
# 200-word ceiling is a ceiling.
INMAIL_WORDS_FOR = _per_reader(getattr(_NET, "INMAIL_WORDS", None),
                               {"recruiter": 170, "decision_maker": 170, "peer": 130})
# "warn" (the default): the employer named late is a warning with the reordering; "refuse"
# makes it a finding. The message that drew a reply named its target in the third
# paragraph, not the first sentence.
EMPLOYERS_FIRST = str(getattr(_NET, "EMPLOYERS_FIRST", "") or "warn").strip().lower()


def reader_type(title="", seniority=None, recruiter=False) -> str:
    """"recruiter", "decision_maker" or "peer", from their title (and the register)."""
    if recruiter or is_recruiter(title):
        return "recruiter"
    import why
    if why.seniority(title) == "senior" or (seniority and tone.is_senior(seniority)):
        return "decision_maker"
    return "peer"


def first_note_findings(text, recruiter=False, reader=None, work_auth=None) -> list:
    """Why this first message reads as asking for the job, as (rule, text) pairs, each
    naming the phrase and what to write instead. `reader` (READER_TYPES) and the person's
    settings decide what is allowed: a recruiter is asked about roles; a decision-maker
    may be told the role wanted and the sender's work authorization; a peer neither,
    unless `work_auth=True` says this message should state it."""
    if recruiter or reader == "recruiter":
        return []
    reader = reader or "peer"
    out = []
    for rx, kind, fix in _JOB_ASKS:
        if kind == "wants" and SAY_THE_ROLE.get(reader):
            continue
        out += [tone.Violation("asks_for_the_job", f"\"{m.group(0)}\": {fix}")
                for m in rx.finditer(text)]
    allowed = ELIGIBILITY.get(reader, False) if work_auth is None else bool(work_auth)
    if not allowed:
        out += [tone.Violation("work_auth_in_first_note",
                               f"\"{m.group(0)}\": a {reader.replace('_', '-')} is not told "
                               "this in a first message (profile/networking.py ELIGIBILITY); "
                               "pass work_auth=True to say it in this one")
                for m in _WORK_AUTH_ANY.finditer(text)]
    return out


# ---------------------------------------------------------------- the phrase bank
#
# Several natural ways to say each thing a note says that carries no fact, so a batch
# varies without a model call. The person's own (profile/networking.py TEMPLATES, per
# reader type or "any", each intent a list) come first; their single OPENER and ASK next;
# these last. A variant is chosen per contact, so the same person always gets the same
# one and the next contact a different one.
# The opener is the person's own (networking.py OPENER) or none: the bank has no stock
# opener, since every "hope you're well" shape is the house style voice_check refuses.
BANK = {
    "ask": {
        "peer": ("Would you be up for a quick chat sometime?",
                 "Would you have 15 minutes for a call in the next couple of weeks?",
                 "I'd really appreciate a short call if you're open to it."),
        "decision_maker": (advice.OPEN_ASK,
                           "If anything's coming up on your team, or there's someone better "
                           "placed to speak to, I'd love to hear.",
                           "Would love to hear if anything's coming up, or who'd be the right "
                           "person to speak to."),
        "recruiter": ("Would love to hear if you have anything coming up that fits.",
                      "If anything you're working on fits, I'd love to hear about it."),
    },
    "pointer": {"any": ("Would you know the right person to speak to about that?",
                        "Is there someone on that team you'd suggest I speak to?",
                        "Would you know who'd be best to speak to about it?")},
    "hedge": {"any": advice.HEDGES},
}
# What the bank says instead where the person's own voice check refuses all of it: "would
# love to" is theirs only where OWN_VOICE says so, and the app's default must never be the
# draft its own check refuses.
BANK_PLAIN = {
    "ask": {
        "decision_maker": ("If anything's coming up on your team, or there's someone better "
                           "placed to speak to, it'd be great to hear.",),
        "recruiter": ("If you have anything coming up that fits, it'd be great to hear about it.",),
    },
}
TEMPLATES = getattr(_NET, "TEMPLATES", None)
TEMPLATES = TEMPLATES if isinstance(TEMPLATES, dict) else {}


def _voice_ok(text: str) -> bool:
    """Would the person's own voice check pass this line?"""
    try:
        import voice_check
    except ImportError:                       # pragma: no cover - path issue only
        return True
    return not voice_check.hard(text, allow=_OWN_VOICE)


def _variants(intent: str, reader: str) -> list:
    out = []
    for where in (TEMPLATES, ):
        for key in (reader, "any"):
            got = where[key].get(intent) if isinstance(where.get(key), dict) else None
            if got:
                out += list(got) if isinstance(got, (list, tuple)) else [got]
    return [str(v) for v in out if str(v).strip()]


def options(intent: str, reader: str = "peer", fallback: str = "") -> list:
    """Every way the composer may say `intent` to this reader: the person's TEMPLATES, else
    their own wording (`fallback`), else the bank's lines their voice check passes."""
    got = _variants(intent, reader)
    if not got and str(fallback or "").strip():
        got = [str(fallback)]
    if not got:
        bank = BANK.get(intent) or {}
        got = [o for o in (bank.get(reader) or bank.get("any") or ()) if _voice_ok(o)]
        if not got:
            plain = BANK_PLAIN.get(intent) or {}
            got = list(plain.get(reader) or plain.get("any") or ())
    return got


def phrase(intent: str, reader: str = "peer", key: str = "", fallback: str = "") -> str:
    """One way to say `intent` ("ask", "pointer", "hedge", or "opener" from TEMPLATES) for
    this reader, chosen by `key` (the contact id) so a batch varies and a redraft does not."""
    options_ = options(intent, reader, fallback)
    if not options_:
        return ""
    import hashlib
    i = int(hashlib.sha1(str(key or "").encode()).hexdigest(), 16) % len(options_) if key else 0
    return options_[i]


# How they were found, said truthfully as the reason for writing: the alternative to a
# pretext. A reading-based specific is colour on top, used only when the sender has
# looked themselves (`looked=True`).
HOW_FOUND = {
    "team_search": "I came across your profile while looking at {company}'s {team} team",
    "people_page": "I found you on {company}'s people page",
    "search": "I came across your profile while looking at {company}",
    "referral": "{referrer} suggested I get in touch",
    "event": "I saw your name on {event}'s speaker list",
    "alumni": "We both worked at {shared}",
}


def how_found_line(kind: str, **fields) -> str:
    """The sentence for how they were found (HOW_FOUND), with its blanks filled."""
    if kind not in HOW_FOUND:
        raise ValueError(f"how_found is one of {', '.join(HOW_FOUND)}, not {kind!r}")
    try:
        return HOW_FOUND[kind].format(**fields)
    except KeyError as e:
        raise ValueError(f"how_found {kind!r} needs {e.args[0]}=") from None


# A claim to have read, seen or watched something of theirs.
_SENDER_LOOKED = re.compile(
    r"(?:\bI(?:'ve| have)?\s+|(?:^|(?<=[.!?,]\s)))(?:read|saw|seen|watched|listened to|"
    r"came across|enjoyed|liked|loved|noticed|spotted|found)\b[^.?!]{0,40}\b(?:your|their)\b[^.?!]{0,30}\b(?:post|article|talk|"
    r"piece|package|repo(?:sitory)?|paper|podcast|blog|newsletter|thread|video|presentation|"
    r"library|project|code|panel|interview|keynote|book)s?\b", re.I)


def _honest(note: str, looked: bool, said=()) -> None:
    """Refuse a note that says the sender looked at something of theirs, unless they did.
    `said` is the composer's own line of how they were found ("I saw your name on the
    event's speaker list"), true by construction and never a claim to have read them."""
    if looked:
        return
    for line in said:
        line = str(line or "").strip().rstrip(".")
        if line:
            note = re.sub(re.escape(line), " ", note, flags=re.I)
    m = _SENDER_LOOKED.search(note)
    if m:
        raise UnconfirmedReading(
            f"\"{m.group(0)}\" says you looked at it, and you have not said you did. Say how "
            "you found them instead (how_found=), or pass looked=True once you have read it "
            "yourself")


# The person's own opener and close, allowed back into a first note: only the
# exact phrases networking.py's OWN_VOICE names. "hope this message finds you
# well" and the rest stay banned.
_OWN_VOICE = getattr(_NET, "OWN_VOICE", re.compile(r"(?!x)x"))


def _first_note_voice(text) -> str:
    try:
        import voice_check
    except ImportError:                       # pragma: no cover - path issue only
        return text
    hard = voice_check.hard(text, allow=_OWN_VOICE)
    if hard:
        raise ReadsAsGenerated(
            "first note reads as generated: %s. %s"
            % ("; ".join(sorted({f["match"] for f in hard}))[:160], hard[0]["fix"]))
    return text


def _question(question) -> str:
    """A question as it is sent: one line, a capital, a question mark. "" for none."""
    q = " ".join(str(question or "").split()).rstrip(".!")
    if not q:
        return ""
    q = q if q.endswith("?") else q + "?"
    return q[0].upper() + q[1:] if q[0].islower() else q


# The shape a first note takes, from who they are and what was read about them.
# One shape for everyone is how a batch comes out alike, and the same length for
# a director as for a peer is the 300 characters a senior reader ignored.
#   shared      shared history leads: the default, and the form that has replied most
#   their_work  their talk, post, paper or code leads, with no opener before it
#   brief       a senior reader: the true line, who you are and the ask; no question
#   recruiter   their job is roles, so who you are, what you want and work authorization
#   connected   already connected: a message, with room for the question and the ask
#   pointer     the kind of team or work named, ending on a question they can answer by
#               pointing to the right person: makes a helpful reply easy without asking
SHAPES = ("shared", "their_work", "brief", "recruiter", "connected", "pointer")
# The brief note's length for a senior reader: profile/networking.py SENIOR_NOTE_CHARS.
BRIEF_CHARS = _as(getattr(_NET, "SENIOR_NOTE_CHARS", 0) or 220, 220)
CONNECTED_CHARS = 600
_WORK_KINDS = ("talk", "article", "podcast", "code", "publication", "featured")


def shape_for(title="", reading=None, route="") -> str:
    """Which shape suits this person, from their title, the reading and the route."""
    reading = reading or {}
    if is_recruiter(title):
        return "recruiter"
    if reading.get("reach") == "message" or str(route or "").lower() == "connection":
        return "connected"
    import why
    senior = why.seniority(title) == "senior"
    shared = reading.get("shared") or {}
    route = str(route or "").lower()
    if any(shared.get(k) for k in ("employers", "schools", "places")) \
            or route.startswith("alumni") or route in ("referral", "mutual"):
        return "brief" if senior else "shared"
    if any(i.get("kind") in _WORK_KINDS + ("post",) for i in reading.get("items") or []):
        return "brief" if senior else "their_work"
    # Nothing shared and nothing of theirs to lead on: a senior reader still gets the
    # brief note, and a peer the standard one at the plan's limit. Every peer with no
    # posts got the 220 meant for senior readers, and a manager read as a peer could
    # not fit the one specific line the note rested on (2026-10-19).
    return "brief" if senior else "shared"


_DEFAULT = object()      # "the caller did not say": the phrase bank chooses


def first_note(name, common_ground="", question=None, about_me=ABOUT_ME, ask=_DEFAULT,
               opener=_DEFAULT, recruiter=False, seniority="peer", their=(),
               reading=None, shape="shared", title="", reader=None, work_auth=None,
               how_found="", looked=False, parallel="", mutual="", variant_key="") -> str:
    """The first message to anyone, as a connection request: a reply is the goal.

        Hi Robin, hope you're well. <the reason for writing>. <about me>. <question>? <ask>.

    The reason for writing is one or more of, in this order: a mutual connection the
    person confirmed (`mutual=`, a name), how they were found, said truthfully
    (`how_found=`, a sentence; `how_found_line()` writes one), the common ground (a shared
    employer or school, or the one thing about their work that prompted the note), and a
    parallel in their own path (`parallel=`, from `reading.py show`, hedged once). At
    least one is required, because without it the note is a sweep.

    `question` is optional. When there is a real one, it is about THEM and answerable in
    a line. With no real one the note is the true line and a plain ask for a
    conversation, which is a complete note.

    Who reads it decides what it says (`reader=`, else from `title=`, `recruiter=` and
    `seniority=`; READER_TYPES): work authorization by ELIGIBILITY (a recruiter and a
    decision-maker by default, never a peer unless `work_auth=True`), the role wanted by
    SAY_THE_ROLE, and the ask from the phrase bank for that reader unless `ask=` is
    given (`ask=None` when the question carries it). `variant_key` (the contact id)
    picks the variant, so a batch varies.

    `reading` is what was read about them. A common ground given alone must rest on it
    (their name and employer do not count: a snippet had them). A note that says the
    sender read, saw or watched something of theirs needs `looked=True`, the sender's own
    word that they did: a reading the chat did is not the sender having looked.

    `shape` is one of SHAPES (`shape_for()` chooses it); "pointer" ends on a question
    the reader can answer by pointing to the right person.
    """
    _no_reaction_waiting("first note")
    if shape not in SHAPES:
        raise ValueError(f"shape must be one of {', '.join(SHAPES)}, not {shape!r}")
    if shape == "recruiter":
        recruiter = True
    rtype = reader or reader_type(title, seniority, recruiter)
    if rtype not in READER_TYPES:
        raise ValueError(f"reader is one of {', '.join(READER_TYPES)}, not {rtype!r}")
    recruiter = recruiter or rtype == "recruiter"
    if opener is _DEFAULT:
        opener = phrase("opener", rtype, variant_key, fallback=OPENER) if OPENER else ""
    if shape in ("their_work", "brief"):
        opener = ""
    if shape == "brief":
        question = None
    if ask is _DEFAULT:
        ask = (phrase("pointer", rtype, variant_key) if shape == "pointer"
               else phrase("ask", rtype, variant_key, fallback=ASK))
    reasons = [x for x in (f"We're both connected to {mutual}" if str(mutual or "").strip()
                           else "", how_found, common_ground, parallel)
               if str(x or "").strip()]
    if not reasons:
        raise ValueError(
            "a first note needs a reason for writing to them: how you found them (how_found=), "
            "the common ground (a shared employer, school or move, or the one thing about "
            "their work), or a parallel in their path (parallel=)")
    if reading is not None and str(common_ground or "").strip() \
            and not (how_found or parallel or mutual):
        import reading as _reading
        ok, why = _reading.grounded(common_ground, reading)
        if not ok:
            raise UngroundedNote(
                f"{why}. Take the common ground from what was read "
                f"(python3 tools/network/reading.py show <contact_id>), never from the snippet, "
                "or say how you found them (how_found=)")
    q = _question(question)
    if not q and not str(ask or "").strip():
        raise ValueError(
            "a first note needs something to answer: a real question about them, or "
            "the plain ask for a conversation (ask=)")
    about_me = _about_me_for(" ".join(reasons), about_me)
    # A brief note to a senior reader has no room for it: there it is said only when this
    # message asks for it.
    say_auth = (ELIGIBILITY.get(rtype, False) if work_auth is None else bool(work_auth))
    if shape == "brief" and work_auth is None:
        say_auth = False
    register = "senior" if rtype == "decision_maker" else seniority
    auth = ((_checked_claim(work_auth, register) if isinstance(work_auth, str)
             else work_auth_line(register)) if say_auth else "")
    # With no opener the reason runs straight on from "Hi Robin," and takes the case a
    # clause after a comma takes: "Hi Robin, Saw your post" is the capital the other
    # composers already fixed.
    first, rest = reasons[0], reasons[1:]
    # The referrer's name in "Ana suggested I get in touch" keeps its capital after the comma.
    referrer = re.match(r"\s*(\S+(?:\s+\S+)?)\s+suggested\b", str(how_found or ""))
    keep = tuple(their or ()) + (mutual,) + ((referrer.group(1),) if referrer else ())
    lead = (f"{_greeting(name)} {opener}. {_sentence(first)}" if opener
            else f"{_greeting(name)} {_after_greeting(first, keep=keep)}")
    parts = [lead] + [_sentence(r) for r in rest] + [
        _sentence(about_me) if about_me else "", auth, q, _sentence(ask) if ask else ""]
    note = " ".join(p for p in parts if p)
    _honest(note, looked, said=(how_found,))
    findings = first_note_findings(note, recruiter=recruiter, reader=rtype,
                                   work_auth=say_auth or None)
    if findings:
        raise AsksForTheJob(
            "this first note asks for the job: %s. A first note asks for a conversation; "
            "the role belongs in compose.referral_ask() once they have replied."
            % "; ".join(sorted({v.text for v in findings})))
    if not tone.reaches_them(note, tuple(their or ()) + ((mutual,) if mutual else ())):
        raise NoteIsAllAboutTheSender(_reaches_fix(name, their))
    limit = {"brief": min(BRIEF_CHARS, schema.LIMITS["connection_note_chars"]),
             "connected": CONNECTED_CHARS}.get(shape, schema.LIMITS["connection_note_chars"])
    if len(note) > limit:
        raise TooLong("first note", len(note), limit)
    return Note(_first_note_voice(note), rtype, recruiter)


def _reaches_fix(name, their=()) -> str:
    """What to add when a note never reaches the person it is addressed to: the word."""
    who = tone.first_name(name) or "them"
    named = next((str(t) for t in their or () if str(t).strip()), "")
    return ("nothing in this note reaches %s: it says who you are and nothing about why you "
            "wrote to them. Add \"you\" or \"your\" to the reason for writing (\"your move "
            "into ...\", \"I found you on ...\")%s, or say how you found them (how_found=)."
            % (who, f", or name {named}, which their= holds" if named else ""))


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
    _no_reaction_waiting("referral ask")
    for what, value in (("context", context), ("role", role), ("link", link)):
        if not str(value or "").strip():
            raise ValueError(f"referral_ask needs {what}")
    if not re.match(r"https?://", str(link).strip()):
        raise ValueError("link must be the posting's URL, so they can act from the message")
    close = close or REFERRAL_CLOSE.replace("{noun}", NOUN)
    # The link goes on its own line at the end: a URL closing a sentence picks
    # up the full stop, and LinkedIn then links to a page that does not exist.
    # Work authorization belongs here, not in a first note: the referrer
    # forwards this message, and the hiring side's first question is whether
    # the candidate can work there.
    auth = _checked_claim(work_auth, seniority) if work_auth else ""
    text = " ".join(p for p in (f"{_greeting(name)} {_after_greeting(context)}",
                                _sentence(REFERRAL_LINE.replace("{role}", str(role))),
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
    _no_reaction_waiting("nudge")
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


class Note(str):
    """A first note: the text, as it always was, and who it was written for (`.reader`,
    `.recruiter`), so validate() and advise() check it for that reader without being told
    again."""

    def __new__(cls, text: str, reader: str = "peer", recruiter: bool = False):
        obj = super().__new__(cls, text)
        obj.reader, obj.recruiter = reader, recruiter
        return obj

    def __reduce__(self):
        return (Note, (str(self), self.reader, self.recruiter))


class InMail(str):
    """An InMail: the whole message as a string, as it always was, and its two parts,
    `.subject` and `.body`, also `m["subject"]` and `m["body"]`. The subject goes in
    LinkedIn's subject field and the body in the message, so validate() no longer needs a
    "Subject:" line inside the text. `.reader` is who it was written for."""

    def __new__(cls, subject: str, body: str, reader: str = "", recruiter: bool = False):
        obj = super().__new__(cls, f"Subject: {subject}\n\n{body}")
        obj.subject, obj.body = subject, body
        obj.reader, obj.recruiter = reader, recruiter
        return obj

    def __reduce__(self):
        return (InMail, (self.subject, self.body, self.reader, self.recruiter))

    def __getitem__(self, key):
        if key in ("subject", "body"):
            return getattr(self, key)
        return super().__getitem__(key)

    def parts(self) -> dict:
        return {"subject": self.subject, "body": self.body}


def identity_subject() -> str:
    """The subject that drew a reply: who the sender is, not a topic. "<title>, ex-<the
    employers they left>", from profile/roles.py, or networking.py SUBJECT."""
    own = str(getattr(_NET, "SUBJECT", "") or "").strip()
    if own:
        return own
    roles = list(getattr(_ROLES, "ROLES", ()) or ())
    if not roles:
        return ""
    title = str(roles[0].get("title") or "").strip()
    past = []
    for r in roles[1:]:
        aka = r.get("known_as")
        nm = (aka if isinstance(aka, str) and aka else r.get("employer") or "").strip()
        if nm and nm not in past:
            past.append(nm)
    for n in (2, 1, 0):
        out = title + (", ex-" + " and ".join(past[:n]) if n and past else "")
        if len(out.split()) <= schema.LIMITS["inmail_subject_words"]:
            return out
    return title


def inmail(name, subject=None, common_ground="", question=None, evidence="",
           about_me=ABOUT_ME, ask=_DEFAULT, opener=_DEFAULT, recruiter=False,
           seniority="peer", their=(), sign_off=_DEFAULT, title="", reader=None,
           work_auth=None, how_found="", looked=False, parallel="", variant_key="") -> InMail:
    """The message with room in it, in the shape that drew a reply:

        Subject: <who you are: "<title>, ex-<employers>" by default>

        Hi Sasha, hope you're well.

        <about me: who you are, with the years>.

        <evidence: one piece of real work, with its numbers>.

        <why this person> <eligibility, by reader> <question>? <the open ask>.

        <sign-off>

    Returns an InMail: the text as before, and `.subject` and `.body` for LinkedIn's two
    fields. The same rules as `first_note()` (never a job ask, work authorization by who
    reads it, it has to reach them, no claim to have read what the sender has not), plus
    one paragraph of evidence, which is what the credit buys. Sized to the reader: about
    150 words to a decision-maker or a recruiter, 100 to 130 to a peer (warned past
    INMAIL_WORDS, never refused); the 200-word ceiling is a ceiling.
    """
    _no_reaction_waiting("InMail")
    rtype = reader or reader_type(title, seniority, recruiter)
    recruiter = recruiter or rtype == "recruiter"
    reasons = [x for x in (how_found, common_ground, parallel) if str(x or "").strip()]
    if not reasons or not str(evidence or "").strip():
        raise ValueError(
            "an InMail needs a reason for writing to this person (how_found=, common_ground= "
            "or parallel=, as in a first note) and one paragraph of concrete evidence (a named "
            "piece of work, its scale, an outcome), which is what the credit buys")
    if opener is _DEFAULT:
        opener = phrase("opener", rtype, variant_key, fallback=OPENER) if OPENER else ""
    if ask is _DEFAULT:
        ask = phrase("ask", rtype, variant_key, fallback=ASK if rtype == "peer" else "")
    q = _question(question)
    if not q and not str(ask or "").strip():
        raise ValueError("an InMail needs something to answer: a real question about them, "
                         "or the plain ask (ask=)")
    subj = inmail_subject(subject if str(subject or "").strip() else identity_subject(),
                          recruiter=recruiter)
    about_me = _about_me_for(" ".join(reasons), about_me)
    say_auth = ELIGIBILITY.get(rtype, False) if work_auth is None else bool(work_auth)
    register = "senior" if rtype == "decision_maker" else seniority
    auth = ((_checked_claim(work_auth, register) if isinstance(work_auth, str)
             else work_auth_line(register)) if say_auth else "")
    if sign_off is _DEFAULT:
        sign_off = SIGN_OFF["senior" if tone.is_senior(seniority) or rtype != "peer" else "peer"]
    paragraphs = [
        f"{_greeting(name)} {opener}." if opener else _greeting(name),
        _sentence(about_me) if about_me else "",
        _sentence(evidence),
        " ".join(p for p in [_sentence(r) for r in reasons] + [auth, q, _sentence(ask) if ask
                                                              else ""] if p),
        str(sign_off or "").strip(),
    ]
    body = "\n\n".join(p for p in paragraphs if p)
    _honest(body, looked, said=(how_found,))
    findings = first_note_findings(body, recruiter=recruiter, reader=rtype,
                                   work_auth=say_auth or None)
    if findings:
        raise AsksForTheJob(
            "this InMail asks for the job: %s. It asks for a conversation; the role belongs "
            "in compose.referral_ask() once they have replied."
            % "; ".join(sorted({v.text for v in findings})))
    if not tone.reaches_them(body, their):
        raise NoteIsAllAboutTheSender(_reaches_fix(name, their))
    if len(body) > INMAIL_CHAR_LIMIT:
        raise TooLong("InMail", len(body), INMAIL_CHAR_LIMIT)
    high = schema.LIMITS["inmail_words"][1]
    if high and len(body.split()) > high:
        raise TooLong("InMail", len(body.split()), high, unit="words")
    return InMail(subj, _first_note_voice(body), rtype, recruiter)


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
    _no_reaction_waiting("email")
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
    _no_reaction_waiting("warm intro")
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


# A check-in gives them nothing to answer, which is why the first message went
# unanswered. `nudge()` refuses an empty reason; a hand-written draft reached
# validate() with "just checking in to see if you had a chance to look at my note"
# and came back clean.
CHECK_IN = re.compile(
    r"\b(?:just\s+)?checking\s+in\b|\bjust\s+check\s+in\b|\bcircl(?:e|ing)\s+back\b"
    r"|\bbump(?:ing)?\s+(?:this|my|it)\b|\btop\s+of\s+(?:your|the)\s+inbox\b"
    r"|\b(?:did|have)\s+you\s+(?:get|had|have)\s+(?:a\s+)?chance\s+to\b"
    r"|\bhad\s+a\s+chance\s+to\s+(?:look|read|see|review)\b|\bjust\s+following\s+up\b"
    r"|\bfollowing\s+up\s+on\s+my\s+(?:last|previous|earlier)\s+(?:message|note|email)\b",
    re.I)


def lowered_names(text) -> list[str]:
    """A known one-word name written in lower case right after the greeting comma."""
    m = re.match(r"\s*\w+\s+[^,\n]{1,40},\s+([a-z][\w&'-]*)", str(text or ""))
    if m and m.group(1).islower() and re.sub(r"['’]s$", "", m.group(1)) in _known_names():
        return [m.group(1)]
    return []


def validate(message, kind, name=None, seniority="peer", employers=(),
             referrer=None, their_message=None, recruiter=False, reader=None, title="",
             work_auth=None, subject=None, _all=False) -> list:
    """Every reason this draft should not be sent, as (rule, offending_text).

    What the skill layer runs before showing the user anything. Returns instead
    of raising: a draft usually breaks more than one rule, and a writer given
    one problem at a time rewrites the same message four times.

    What reads badly but may go is `advise()`'s, never this: a late employer (unless
    EMPLOYERS_FIRST is "refuse"), a hedge, an exit. A rule the person said outranks a
    check (`learned.py record --overrides <rule>`) drops that check from here; advise()
    still mentions it. An InMail's subject is `subject=`, or the InMail's own.
    """
    k = _KIND_ALIASES.get(str(kind or "").strip().lower())
    if k is None:
        raise ValueError(
            f"unknown message kind {kind!r}; expected one of "
            f"{sorted(set(_KIND_ALIASES.values()))}. A typo here would skip the "
            f"length check entirely.")
    text = str(message or "")
    if subject is None and isinstance(message, InMail):
        subject = message.subject
        text = message.body
    # A note the composer wrote knows who it is for: checked for that reader, not a peer.
    recruiter = recruiter or bool(getattr(message, "recruiter", False))
    rtype = (reader or (getattr(message, "reader", "") if not title else "")
             or reader_type(title, seniority, recruiter))
    # A reply goes to somebody who has already written back, which is what
    # `live_thread` means. Without it a reply such as "That's great, thank you
    # Riley" fails on the one rule that is scoped to cold messages.
    out = list(tone.check(text, recipient_seniority=seniority, name=name,
                          live_thread=(k in ("reply", "referral_ask"))))
    if k in ("connection", "inmail"):
        out += first_note_findings(text, recruiter=recruiter, reader=rtype, work_auth=work_auth)
    if k == "inmail":
        first = text.lstrip().split("\n", 1)[0]
        if subject is not None:
            if not str(subject).strip():
                out.append(tone.Violation("no_subject", "an InMail with no subject"))
            elif _GENERIC_SUBJECT.match(str(subject)):
                out.append(tone.Violation("generic_subject", str(subject).strip()))
        elif not _SUBJECT_LINE.match(first):
            out.append(tone.Violation("no_subject", "an InMail with no subject: pass subject= "
                                                    "(or a 'Subject:' first line)"))
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
    for word in lowered_names(text):
        out.append(tone.Violation("lowercase_name", word))
    for found in CHECK_IN.findall(text):
        out.append(tone.Violation("check_in", found if isinstance(found, str) else found[0]))
    if EMPLOYERS_FIRST == "refuse":
        out += _buried(text, employers)
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
    if _all:
        return out
    over = _overrides()
    return [v for v in out if v.rule not in over]


def _overrides() -> set:
    try:
        import learned
        return learned.overrides()
    except (ImportError, SystemExit):
        return set()


def _buried(text, employers) -> list:
    out = []
    buried_all = employers_early(text, employers)
    moved = employers_first(text, employers) if buried_all else ""
    for buried in buried_all:
        # What to do, and the reordering where moving sentences makes it.
        out.append(tone.Violation(
            "employers_buried",
            f"{buried}: name {buried} in the first sentence after the greeting (by the "
            "second at the latest)"
            + (f"; for example: {moved}" if moved else
               "; no sentence names it yet, so put it in the common ground or the line "
               "about you")))
    return out


def advise(message, kind, name=None, seniority="peer", employers=(), reader=None, title="",
           reading=None, first_contact=None, recruiter=False) -> list:
    """Every warning for a draft that may go but reads worse than it should, each an
    advice.Advice(rule, text, fix): what reads as generated, a hedge stacked or a
    disclaimer, an exit in a first message, a claim about them written as fact, a
    credential with no reason in its sentence, the employer named late, an InMail longer
    than this reader needs, and any check the person's rules outrank. Shown with the draft
    after a rewrite, never instead of one."""
    k = _KIND_ALIASES.get(str(kind or "").strip().lower(), str(kind or ""))
    text = message.body if isinstance(message, InMail) else str(message or "")
    recruiter = recruiter or bool(getattr(message, "recruiter", False))
    rtype = (reader or (getattr(message, "reader", "") if not title else "")
             or reader_type(title, seniority, recruiter))
    out = advice.check(text, k, reader=rtype, first_contact=first_contact, reading=reading)
    if EMPLOYERS_FIRST != "refuse":
        out += [advice.Advice(v.rule, v.text.split(":", 1)[0], v.text.split(":", 1)[-1].strip())
                for v in _buried(text, employers)]
    if tone.CONTRACTIONS == "warn":
        out += [advice.Advice("sentence_starts_with_contraction", v.text,
                              "you asked to be told: the long form where it reads better")
                for v in tone.contractions_at_start(text)]
    if k == "inmail":
        words, most = len(text.split()), INMAIL_WORDS_FOR.get(rtype)
        if most and words > most:
            out.append(advice.Advice(
                "longer_than_this_reader_needs", f"{words} words",
                f"about {most} is right for a {rtype.replace('_', '-')} (profile/networking.py "
                "INMAIL_WORDS); cut the paragraph that is not about them or the work"))
    over = _overrides()
    if over:
        out += [advice.Advice("your_rule_outranks", f"{v.rule}: {v.text}",
                              "your recorded rule outranks this check, so it is only mentioned")
                for v in validate(message, kind, name=name, seniority=seniority,
                                  employers=employers, reader=rtype, _all=True)
                if v.rule in over]
    return out


# ---------------------------------------------------------------- read it aloud

READ_ALOUD = (
    "Read this note aloud as the person would say it to {who}, and write that version: "
    "the most natural spoken English, contractions welcome, every fact, name and number "
    "kept, nothing added, every rule of theirs kept (python3 tools/learned.py brief "
    "messages). Show it beside the original, then run compose.read_aloud(original, yours) "
    "and keep it only if that passes.")
# A capital is any Latin one: "\u00c9lo\u00efse" is a name as much as "Eloise".
_CAP = "A-Z" + "".join(chr(c) for c in range(0xC0, 0x250) if chr(c).isupper())
_FACT = re.compile(r"\b\d[\d,.]*\s?(?:%|k\b|m\b|x\b|\+)?"
                   r"|(?<![\w'])[" + _CAP + r"][\w'-]*(?:\s(?:&\s|of\s|and\s)?[" + _CAP
                   + r"][\w&'-]*)*")
# Words that take a capital only for opening a sentence.
_OPENING = frozenset("""hi hey hello dear hope thanks would could i i'm i'd i've we we're your you
the a an it it's if is are do did any my at in on for with from to by of after before when
while as since so but and or this that these those there here what how why who which""".split())


def _facts(text: str) -> set:
    """The names and numbers in a text: what a rewrite must keep and must not add."""
    out = set()
    for s in tone.sentences(text):
        for m in _FACT.finditer(s):
            words = m.group(0).strip().rstrip(".,").split()
            if m.start() == 0 or s[:m.start()].rstrip().endswith(","):
                while words and words[0].lower().rstrip(",") in _OPENING:
                    words = words[1:]
            while words and words[-1] in ("I", "I'm", "I'd", "I've"):
                words = words[:-1]                  # "At Brindle & Hart I cut ..."
            f = " ".join(words)
            if f and f.lower() not in _OPENING and f != "I":
                out.add(f)
    return out


def read_aloud(original: str, rewrite: str, kind: str = "connection", **kw) -> dict:
    """Check the spoken rewrite against the original (READ_ALOUD says how to make one):
    {"ok", "lost", "added", "findings"}. A fact, name or number the original had and the
    rewrite dropped is lost; one the rewrite brought in is added, which is a new claim.
    Either, or a finding validate() makes, and the original stands."""
    a, b = _facts(original), _facts(rewrite)
    # A word that had a capital only for opening a sentence ("Curious how ...") is kept
    # where the rewrite says it at all ("I'm curious how ...").
    lost = sorted(f for f in a if f not in b and not any(f in x for x in b)
                  and not (" " not in f and re.search(r"\b%s\b" % re.escape(f.lower()), rewrite)))
    added = sorted(f for f in b if f not in a and not any(f in x for x in a)
                   and not (" " not in f and re.search(r"\b%s\b" % re.escape(f.lower()), original)))
    findings = [f"{v.rule}: {v.text}" for v in validate(rewrite, kind, **kw)]
    return {"ok": not (lost or added or findings), "lost": lost, "added": added,
            "findings": findings}


# ---------------------------------------------------------------- what drew replies

def examples(channel: str | None = None, limit: int = 3, contacts=None, threads=None) -> list:
    """The person's own sent messages that drew a reply, newest first, with their words:
    the few-shot a draft follows ahead of every default here. Read from the message log
    (what_works.message_cases); a message logged without its text cannot be one."""
    import state
    import what_works
    contacts = state.load_contacts() if contacts is None else contacts
    threads = state.load_threads() if threads is None else threads
    won = [c for c in what_works.message_cases(contacts, threads)
           if c["won"] and c["text"] and (not channel or c["channel"] == channel)]
    won.sort(key=lambda c: c["date"], reverse=True)
    return [{"text": c["text"], "channel": c["channel"], "date": c["date"],
             "route": c["route"], "days_to_reply": c["days_to_reply"]} for c in won[:limit]]


# ---------------------------------------------------------------- a batch alike

def _own_lines() -> list:
    """The sentences that are the person's to repeat in every note: their opener, the line
    about them, their ask, the work-authorization lines, and every ask the composer may
    use. A batch sharing these was written the way they set it."""
    lines = [OPENER, ABOUT_ME, ASK, work_auth_line("peer"), work_auth_line("senior")]
    lines += [v for intent in ("ask", "pointer", "opener") for rt in READER_TYPES
              for v in options(intent, rt, {"ask": ASK, "opener": OPENER}.get(intent, ""))]
    return [advice._norm(x) for x in lines if str(x or "").strip()]


def skeleton(text: str, own=None) -> tuple:
    """A note's shape: how each sentence after the greeting opens, and how many there are,
    leaving out the person's own fixed sentences (`_own_lines`), which every note carries by
    their choice. "Identical in structure" is what the person called a batch that shared it."""
    own = _own_lines() if own is None else own
    out = []
    for s in body_sentences(text):
        n = advice._norm(s)
        if any(o and (o == n or (len(o) > 12 and o in n)) for o in own):
            continue
        words = re.findall(r"[a-z']+", tone._plain(s).lower())[:2]
        out.append(" ".join(words))
    return tuple(out)


def alike(notes: dict) -> list:
    """[(id, id, the shape)] for each pair of notes in a batch built the same way: the same
    number of sentences, each opening the same, after the greeting."""
    own = _own_lines()
    shapes = {k: skeleton(v, own) for k, v in notes.items() if str(v or "").strip()}
    ids = sorted(shapes)
    out = []
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            sa, sb = shapes[a], shapes[b]
            if len(sa) >= 3 and sa == sb:
                out.append((a, b, " / ".join(sa)))
    return out


def main(argv=None) -> int:
    import argparse
    import json
    ap = argparse.ArgumentParser(description="Check a draft, or see what the composer offers.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="what refuses a draft, and what it is warned about")
    c.add_argument("file", help="the draft, or - for stdin")
    c.add_argument("--kind", default="connection")
    c.add_argument("--name", default=None)
    c.add_argument("--title", default="")
    c.add_argument("--reader", default=None, choices=READER_TYPES)
    c.add_argument("--subject", default=None)
    c.add_argument("--employer", action="append", default=[])
    c.add_argument("--contact", default="", help="their contact id: their reading is used")
    r = sub.add_parser("read-aloud", help="check a spoken rewrite against the original")
    r.add_argument("original")
    r.add_argument("rewrite")
    r.add_argument("--kind", default="connection")
    e = sub.add_parser("examples", help="your own messages that drew a reply")
    e.add_argument("--channel", default=None)
    e.add_argument("--limit", type=int, default=3)
    sub.add_parser("subject", help="the InMail subject offered by default")
    sub.add_parser("phrases", help="the phrase bank, yours first")
    a = ap.parse_args(argv)
    if a.cmd == "subject":
        print(identity_subject() or "(no roles in the profile to build one from)")
        return 0
    if a.cmd == "phrases":
        for intent in ("opener",) + tuple(BANK):
            for rt in READER_TYPES:
                got = options(intent, rt, fallback={"opener": OPENER}.get(intent, ""))
                print(f"{intent} ({rt}): " + (" | ".join(got) or "(none)"))
        return 0
    if a.cmd == "examples":
        got = examples(a.channel, a.limit)
        for x in got:
            print(json.dumps(x, ensure_ascii=False))
        print(f"{len(got)} message(s) of yours that drew a reply"
              + ("" if got else ": none logged with its words yet"))
        return 0
    if a.cmd == "read-aloud":
        res = read_aloud(open(a.original, encoding="utf-8").read(),
                         open(a.rewrite, encoding="utf-8").read(), a.kind)
        print(json.dumps(res, ensure_ascii=False, indent=1))
        return 0 if res["ok"] else 1
    text = sys.stdin.read() if a.file == "-" else open(a.file, encoding="utf-8").read()
    rd = None
    if a.contact:
        import reading as _reading
        rd = _reading.load(a.contact)
    bad = validate(text, a.kind, name=a.name, title=a.title, reader=a.reader,
                   employers=a.employer, subject=a.subject)
    warn = advise(text, a.kind, name=a.name, title=a.title, reader=a.reader,
                  employers=a.employer, reading=rd)
    for v in bad:
        print(f"refused: {v.rule}: {v.text}")
    for w in warn:
        print(f"warn: {w.rule}: {w.text} -> {w.fix}")
    waiting = ""
    try:
        import learned
        waiting = learned.refuse_over_pending("compose")
    except (ImportError, SystemExit):
        pass
    if waiting:
        print(waiting)
    print(f"{len(bad)} refused, {len(warn)} warning(s)")
    return 1 if bad or waiting else 0


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

    Soft findings are dropped deliberately, the same way `_voice()` drops them
    (voice_check.hard says why). A first note may carry the person's own
    opener and close, and a live thread a light "hope".
    """
    try:
        import voice_check
    except ImportError:
        return []
    allow = {"connection": _OWN_VOICE, "inmail": _OWN_VOICE,
             "reply": _THREAD_WARMTH, "referral_ask": _THREAD_WARMTH}.get(kind)
    return voice_check.hard(text, allow=allow)


if __name__ == "__main__":
    sys.exit(main())
