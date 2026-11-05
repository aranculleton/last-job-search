#!/usr/bin/env python3
"""Read the inbound message, name the scenario, and say what the reply has to do.

The brief calls conversation management the largest surface in the system, and
the reason is that the messages look alike while the correct moves do not. "Sure"
and four generous paragraphs are both agreement; one earns a single concrete next
step and the other earns real engagement. Answering the wrong one wastes the
thread, and there is no second first reply.

This module classifies and prescribes. It never writes the message. Drafting
needs a model and a voice; classification needs rules, and a rule that can be
tested is a rule that stops being re-learned every time a thread goes sideways.

Four decisions worth the explanation.

**Precedence is an ordered ladder, not a score.** Two cues fire on the same
message constantly: an address inside a long substantive reply, a referral
offered alongside "we are not hiring". A scoring blend picks whichever regex
happened to be written more generously that day. `SCENARIOS` is ordered, the
first match wins, and everything else comes back as `runners_up` so nothing the
classifier saw is thrown away.

**Action beats substance.** An email address inside four detailed paragraphs is
still `send_resume`. The substance gets engaged with in the email; the address is
the thing that stops being actionable if it is missed. Same for a scheduling
link, which sits above it because slots disappear while inboxes do not.

**Target length is computed, never fixed.** The rule is match their effort, so
one number could not be right for both "sure" and four paragraphs. The ladder
maps their word count to sentences, and each scenario clamps it to a band.

**Two nos end the thread.** `should_continue` counts explicit declines in the log
rather than reading a status, because the status is hand-edited and the messages
are evidence. A third ask after two declines spends a relationship to gain
nothing.

Usage:
    python3 tools/network/reply.py "sure, send your resume to wren@example.com"
    python3 tools/network/reply.py prepare "<name or contact id>" --text-file <their message>
    python3 tools/network/reply.py finish <contact id> --draft-file <the reply>
        [--work <id> --dump <dir> [--thread <thread>]]
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field
from typing import Callable

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (_HERE, os.path.dirname(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import person  # noqa: E402
import schema  # noqa: E402
import state  # noqa: E402
import tone  # noqa: E402

# The candidate's places and status: profile/networking.py. Each place word is
# lower case and regex-escaped; one the profile does not set matches nothing.
_NET = person.module("networking") if person.exists("networking.py") else None


def _w(name):
    v = str(getattr(_NET, name, "") or "").lower()
    return re.escape(v) if v else r"(?!x)x"


_COUNTRY, _ADJ, _CITY = _w("HOME_COUNTRY"), _w("HOME_ADJECTIVE"), _w("HOME_CITY")
TIMEZONE = getattr(_NET, "TIMEZONE", "the local time zone")
TIMEZONE_ABBR = getattr(_NET, "TIMEZONE_ABBR", "")
STATUS_NAME = getattr(_NET, "STATUS_NAME", "the candidate's status")

# Direction aliasing and message ordering live in state.py because the thread CSV
# is hand-edited and the synonym table has to be one table. Binding the private
# helpers here is deliberate: a second copy is how "sent" and "out" start meaning
# different things in two modules that both claim to read the same file.
_direction = state._direction
_ordered = state._ordered
# Counting the nudges already sent is the same count `state.owed` runs, and a
# second copy of it is how /reply and /threads start disagreeing about whether a
# thread has had its one nudge.
_trailing_outbound = state._trailing_outbound
# "Did they say something" has one answer, and it is not the direction cell: an
# accepted connection request is logged inbound with no message in it. Read as
# speech, it had `nudge_due` refusing a contact's nudge because "they answered" and
# `classify` answering the row's own summary as a six-word reply.
_inbound = state.said_something

# The person's own word for the document, read as a resume asked for when it is not one
# of the usual ones (person.json documents.noun).
_NOUN_WORD = str((person.get("documents", {}) or {}).get("noun", "") or "").lower()
if _NOUN_WORD in ("resume", "cv", "résumé"):
    _NOUN_WORD = ""

# Six words or fewer is the low-effort bar. It is deliberately generous: "sure,
# sounds good, send it over" is four words of agreement and one of substance, and
# treating it as a detailed reply produces the paragraph-for-one-word mismatch
# the brief names as a failure.
LOW_EFFORT_WORDS = 6

# Where a reply stops being a note and becomes a considered answer. Below this a
# message can still be substantive, which is what the generosity cues are for.
DETAILED_WORDS = 45

# Two working weeks. Below this, silence on our side is a gap nobody needs told
# about; above it, the brief is explicit that the reply acknowledges the gap
# rather than pretending it did not happen.
LATE_REPLY_BUSINESS_DAYS = 10

# Two explicit nos close the thread. The third ask is the one that costs the
# relationship, and it never recovers the first two.
MAX_DECLINES = 2

# The brief's follow-up window. The fire threshold is schema.FOLLOWUP_BUSINESS_DAYS
# so that /reply and /threads cannot tell the user different things about the same
# thread on the same morning.
NUDGE_WINDOW = (5, 7)

# A thread the user walked away from stays walked away from. `converted_to_application`
# is deliberately absent: a thread that produced an application is the most alive
# thread in the book, and refusing to reply inside it would be the wrong advice.
STOP_STATUSES = frozenset({"closed", "gone_cold", "dropped"})
# Statuses where they have already said yes to something: never read as stopped.
LIVE_STATUSES = frozenset({"call_booked", "referral_in_progress"})


# ---------------------------------------------------------------- text measures

_WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9'’@._+-]*")
_SENTENCE = re.compile(r"[^.!?\n]+[.!?]*")
# Anything outside the Latin-plus-punctuation range, which is enough to spot a
# reaction without carrying an emoji table that goes stale every Unicode release.
_EMOJI = re.compile(r"[\U0001F000-\U0001FAFF←-⯿☀-➿️‍]")
_REACTIONS = {"+1", ":thumbsup:", ":+1:", "thumbs up", "y", "k"}


def word_count(text) -> int:
    return len(_WORD.findall(str(text or "")))


def sentence_count(text) -> int:
    return len([s for s in _SENTENCE.findall(str(text or "")) if s.strip()])


def is_reaction(text) -> bool:
    """True when the whole message is a thumbs up or an equivalent token.

    A reaction is not a short reply, it is an acknowledgement, and the two are
    handled the same way only because the correct move for both is one concrete
    next step.
    """
    raw = str(text or "").strip()
    if not raw:
        return False
    if raw.lower() in _REACTIONS:
        return True
    return not _EMOJI.sub("", raw).strip(" \t\n.!,")


# ---------------------------------------------------------------- extraction

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# People write addresses out in longhand on LinkedIn to dodge scrapers, and an
# address the classifier cannot see is an action the user never takes.
# The dot has to be spelled out or bracketed, never a bare period. Accepting a
# period let "introduce you to the team at Acme. She is closer to it" parse as
# an address at the domain "acme.she", and a bogus address routes the resume
# nowhere.
_DOT = r"(?:[\(\[]\s*(?:dot|\.)\s*[\)\]]|\bdot\b)"
_OBFUSCATED = re.compile(
    r"\b([A-Za-z0-9._%+-]{2,}(?:\s*" + _DOT + r"\s*[A-Za-z0-9._%+-]+)*)"
    r"\s*(?:\(|\[)?\s*(?:at|@)\s*(?:\)|\])?\s+"
    r"([A-Za-z0-9-]{2,}(?:\s*" + _DOT + r"\s*[A-Za-z0-9-]+)*?)"
    r"\s*" + _DOT + r"\s*([A-Za-z]{2,6})\b", re.I)
# "look at the dot com boom" parses as an address at the.com without this. Any local part
# that is an ordinary English word carrying the sentence rather than naming a
# person is not an address.
_NOT_A_LOCAL_PART = frozenset({
    "look", "me", "us", "reach", "back", "get", "in", "touch", "email", "e-mail",
    "here", "over", "great", "available", "arrive", "based", "out", "everything",
    "somewhere", "him", "her", "them", "it", "that", "this",
})
_TRAILING = " \t\n.,;:!?)>]\"'"

# Booking pages, by registrable domain. A bare host with no path is a company
# name rather than an invitation, so every entry below still needs a path: "we use
# Cal.com internally" is not a slot on offer.
_SCHEDULER_DOMAINS = {
    "calendly.com": (),
    "cal.com": (),
    "savvycal.com": (),
    "youcanbook.me": (),
    "chilipiper.com": (),
    "zcal.co": (),
    "tidycal.com": (),
    "koalendar.com": (),
    "calendar.app.google": (),
    "doodle.com": (),
    "when2meet.com": (),
    "cronofy.com": (),
    # HubSpot and Microsoft host a booking page on a domain that is mostly not
    # one, so these two need the path segment as well.
    "hubspot.com": ("meetings",),
    "office.com": ("bookwithme",),
    "office365.com": ("bookwithme",),
}
# A first path segment that means "pick a time" on any domain. Whole segments
# only: "meet-the-team" is a page about people, not a slot, and matching it on a
# prefix is how a careers page becomes a calendar invite.
_BOOKING_SEGMENTS = frozenset({
    "book", "booking", "bookings", "meet", "meeting", "meetings",
    "schedule", "scheduling", "appointment", "appointments",
})
_URLISH = re.compile(
    r"(?:https?://)?(?:www\.)?"
    r"([A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?(?:\.[A-Za-z0-9-]+)+)"
    r"(/[^\s<>\"')\]]*)?", re.I)


def extract_email(text) -> str:
    """The first address in the message, longhand forms included. Empty when there is none."""
    raw = str(text or "")
    m = _EMAIL.search(raw)
    if m:
        return m.group(0).rstrip(_TRAILING)
    m = _OBFUSCATED.search(raw)
    if not m:
        return ""
    spelled = re.compile(r"\s*" + _DOT + r"\s*", re.I)
    local = spelled.sub(".", m.group(1).strip()).lower()
    # The stopword check is on the first segment, which is the word carrying the
    # sentence when this is prose rather than an address.
    if local.split(".")[0] in _NOT_A_LOCAL_PART:
        return ""
    domain = spelled.sub(".", m.group(2).strip())
    return "%s@%s.%s" % (local, domain.strip("."), m.group(3).lower())


def _own_addresses() -> set:
    """The person's own email address (person.json identity.email), lower case, or none."""
    try:
        own = str(person.get("identity.email", "") or "").strip().lower()
    except Exception:  # noqa: BLE001  the app itself, or a profile not set up
        own = ""
    return {own} if "@" in own else set()


def without_own_address(text) -> str:
    """Their message with the person's own address taken out, longhand forms too: it is in
    a pasted thread or a quoted signature of theirs, never an address they gave. Read as
    theirs, a thread pasted whole was a request for the resume at 0.97 (2026-11-05)."""
    out, own = str(text or ""), _own_addresses()
    if not own:
        return out
    out = _EMAIL.sub(lambda m: " " if m.group(0).rstrip(_TRAILING).lower() in own
                     else m.group(0), out)
    for _ in range(3):
        m = _OBFUSCATED.search(out)
        if not m or extract_email(m.group(0)).lower() not in own:
            break
        out = out[:m.start()] + " " + out[m.end():]
    return out


def _is_scheduler(host: str, path: str) -> bool:
    segment = path.strip("/").split("/")[0].lower() if path.strip("/") else ""
    if not segment:
        return False
    parts = host.split(".")
    for domain, required in _SCHEDULER_DOMAINS.items():
        if host == domain or host.endswith("." + domain):
            # The qualifying token sits on either side of the host boundary:
            # meetings.hubspot.com/wren-halloway and app.hubspot.com/meetings/wren are
            # both booking pages, and www.hubspot.com/products is not.
            return not required or any(r in parts or r == segment for r in required)
    return segment in _BOOKING_SEGMENTS


def extract_scheduling_link(text) -> str:
    """The first booking link in the message. Empty when there is none.

    The word "calendar" is not a link. "I will check my calendar" is the most
    common sentence in a thread that has not booked anything, and treating it as a
    slot on offer produces a reply confirming a call nobody scheduled.
    """
    for m in _URLISH.finditer(str(text or "")):
        host = m.group(1).lower().rstrip(".")
        path = (m.group(2) or "").rstrip(_TRAILING)
        if _is_scheduler(host, path):
            return m.group(0).rstrip(_TRAILING)
    return ""


# ---------------------------------------------------------------- match helpers


def _rx(*patterns):
    """Compile a cue table, passing an already-compiled pattern straight through.

    A pattern that another part of the module also reads is defined once as a
    module constant and handed in compiled, rather than kept as a source string
    in one place and re-compiled in the other.
    """
    return tuple((weight, label,
                  rx if isinstance(rx, re.Pattern) else re.compile(rx, re.I))
                 for weight, label, rx in patterns)


def _quote(fragment: str) -> str:
    frag = " ".join(str(fragment or "").split())
    if len(frag) > 60:
        frag = frag[:57].rstrip() + "..."
    return '"%s"' % frag


def _hits(text, patterns):
    found = []
    for weight, label, rx in patterns:
        m = rx.search(text)
        if m:
            found.append((weight, "%s: %s" % (label, _quote(m.group(0)))))
    return found


def _confidence(hits) -> float:
    """The strongest cue, nudged up by corroborating ones.

    Kept below 1.0 on purpose. The command shows this number so the user can
    override a confident misread, and a classifier that reports certainty is one
    nobody checks.
    """
    best = max(w for w, _ in hits)
    return round(min(0.97, best + 0.03 * (len(hits) - 1)), 2)


# The verbs a request to be sent something is made with. Inflected forms matter more than
# they look. "Happy to look if you're sharing your resume" missed entirely when the list
# held "share" and not "sharing", and the message came back as detailed_generous: engaged
# with warmly, resume never sent.
_SEND_VERBS = (r"\b(?:send(?:s|ing)?|sent|shar(?:e|es|ed|ing)|forward(?:s|ed|ing)?|"
               r"shoot(?:s|ing)?|pass(?:es|ed|ing)?|fir(?:e|es|ed|ing)|"
               r"drop(?:s|ped|ping)?|e-?mail(?:s|ed|ing)?|ping(?:s|ed|ing)?)\b")
_DOC_OVER = r"\b(resume|r[eé]sum[eé]|cv)\b[^.!?\n]{0,30}\b(over|across|through|my way|to me)\b"

RESUME_ASK = _rx(
    (0.92, "asked for the resume",
     _SEND_VERBS + r"[^.!?\n]{0,40}"
     r"\b(resume|r[eé]sum[eé]|cv|profile|background|details)\b"),
    (0.92, "asked for the resume", _DOC_OVER),
    (0.88, "asked to be emailed", r"\b(email|e-mail|drop|shoot|write)\s+(me|us)\b[^.!?\n]{0,25}"),
    (0.85, "gave a contact route",
     r"\b(my|our)\s+e-?mail\b|\b(reach|contact)\s+me\s+(at|on)\b|\bget in touch (at|on)\b"),
)

# The commonest referral form in this market is not an introduction at all: it
# is being told to name the person on the application. Most realistic
# phrasings missed. A message such as "Put <their address> in the referral
# field when you apply" classified as send_resume because it
# carries an address and send_resume sits above referral_offered in the ladder,
# so the guidance said to email a resume instead of applying with the referral.
# That is the highest-value lead a thread can hold.
#
# Named rather than inlined because _match_send_resume defers to it: an
# instruction to name somebody on an application is not a request for a resume,
# whatever the ladder order says.
REFERRAL_FIELD = re.compile(
    r"\breferr?al\s+(?:field|box|section|form|code|link|program)\b"
    r"|\b(?:put|use|add|list|name|drop|include)\b[^.!?\n]{0,30}"
    r"\b(?:as|in|on|for)\b[^.!?\n]{0,20}\b(?:referr?(?:al|er)|reference)\b"
    r"|\b(?:use|name|list)\s+(?:me|my (?:name|email))\b[^.!?\n]{0,24}"
    r"\b(?:refer\w*|applicat\w*)\b"
    r"|\bI(?:'ve|’ve| have)\s+(?:already\s+)?(?:referred|submitted|put)\s+you\b"
    r"|\bemployee referr?al\b", re.I)

# "Reach out to Wren" names a third party; "I wanted to reach out to initiate a
# discussion" is the sender describing their own message, and it is the most
# common opener a cold inbound has. A cold first message that opened that way
# classified as `referral_offered` at 0.86 and the guidance said to accept an
# introduction nobody had offered. So the bare phrase only counts when
# the sender is not the one reaching out, and never when it is aimed at "you".
SPEAK_TO = re.compile(
    r"\b(you should (speak|talk|reach out)|worth (speaking|talking|reaching out)|"
    r"(?<!wanted to )(?<!want to )(?<!like to )(?<!love to )(?<!would )"
    r"(?<!I'd )(?<!I’d )(?<!\bI )"
    r"(?:reach out|speak) to(?!\s+you\b))\b[^.!?\n]{0,40}"
    # "talk to Wren Halloway", "try Sam on the data team": a named person, so a
    # capital after the verb, which is why this branch is case-sensitive.
    r"|(?-i:\b(?:[Tt]alk|[Ss]peak|[Tt]ry|[Aa]sk|[Pp]ing|[Mm]essage)(?: to| with)? "
    r"(?!You\b|Me\b|Us\b|Them\b|It\b|Him\b|Her\b)[A-Z][a-z]+(?: [A-Z][a-z'-]+)?\b)", re.I)

# What follows "pass" when it means passing something on: "I'll pass it on", "pass your
# CV along", "pass this to the team". A bare "I'll pass" is a no, and read as an
# introduction it made "Thanks, but I'll pass." a referral offer. REFERRAL and REJECTION
# both read "pass" through this one pattern, so the two can never claim the same words.
# "Pass on" is both: "I'll pass on your CV" hands something on, "I'll pass on the
# opportunity" declines it. So after "on" it is passing on only when what follows is
# something that can be handed to somebody (_HANDED_ON), or somebody it goes to follows
# (_TO_SOMEONE). "I'll pass on the offer", "the call", "it" and "my end" are a no.
_HANDED_ON = (r"(?:cv|c\.v\.|r[eé]sum[eé]|profile|details|name|number|e-?mail|message|note|"
              r"info|information|contact|application|portfolio|linkedin|letter|request|word|"
              r"thoughts|feedback|background)s?")
_TO_SOMEONE = (r"\s+(?:on\s+|along\s+)?(?:to|with)\s+(?:the|our|my|your|a|an|him|her|them|"
               r"someone|somebody|(?-i:[A-Z])\w*)")
_PASSED_ON = (r"\s+(?:it|them|your|you|him|her|my|along|over|through"
              r"|(?:this|that|these|those|the\s+\w+)\s+(?:on|along|over|to)"
              r"|on\s+to\s+(?:your|my|the|our|it|him|her|them|someone|(?-i:[A-Z])\w*)"
              r"|on\s+(?:your|my|the|his|her|their|our)\s+(?:[\w'-]+\s+)?" + _HANDED_ON +
              r"|on\s+(?:[\w'-]+\s+){0,2}[\w'-]+" + _TO_SOMEONE + r")\b")

# "Connect" is an introduction only with somebody to be connected: "happy to connect you
# with a recruiter". Bare, it is the reply to a connection request, the commonest message
# LinkedIn carries: "Hi Juno, happy to connect!" and "I'd be happy to connect over a coffee
# chat" both read as referral offers at 0.92, and the guidance said to accept an
# introduction and send the resume unprompted (2026-10-24). "Pass" the same way, through
# _PASSED_ON, as the second pattern already read it.
_INTRO_VERBS = (r"intro\w*|connect\s+you\b|put you|pass(?=" + _PASSED_ON + r")|forward|refer")

REFERRAL = _rx(
    (0.94, "told to name them as the referrer", REFERRAL_FIELD),
    (0.92, "offered an introduction",
     r"\b(happy|glad|pleased|able)\s+to\s+(" + _INTRO_VERBS + r")\b"),
    (0.92, "offered an introduction",
     r"\bI(?:'ll|’ll|'d|’d| will| can| could| would| should)\s+"
     r"(" + _INTRO_VERBS + r"|flag|loop|mention|drop)\b"),
    (0.86, "named someone to speak to", SPEAK_TO),
    (0.84, "knows someone",
     r"\b(I know (someone|a few people|some people|the)|know anyone|there'?s someone)\b"),
    (0.82, "named a colleague",
     r"\b(my|our|a)\s+(colleague|coworker|co-worker|former colleague|friend|contact)\b"),
)

# They offered the conversation itself: a call, a chat, a coffee. That is stage two of
# what outreach is for, and it outranks a "not much overlap" or a "not hiring" in the same
# message, which is why it sits above mismatch and rejection. A bare "happy to connect"
# is not one: that is accepting the request (low_effort, or substance if they wrote more).
# "Feel free to talk to HR" and "open to talk with talented people" send them elsewhere,
# so a talk with somebody other than the person writing is not one.
# A call or a chat, however long and whatever kind: "a quick call", "a 20 minute call", "a
# short introductory phone screen", "a coffee".
_CALL = (r"(?:(?:quick|short|brief|informal|introductory|intro|initial|virtual|phone|video|zoom|"
         r"teams|\d{1,3}[- ]?(?:min(?:ute)?s?|mins?)|half[- ]an[- ]hour|15|20|30)[\s-]+){0,3}"
         r"(?:call|chat|phone\s+screen|phone\s+call|video\s+call|conversation|coffee|catch[- ]up)"
         r"\b(?!\s+cent(?:re|er)s?\b)")
CHAT_OFFER = re.compile(
    r"\b(?:happy|glad|keen|(?<!feel )free|available|open)\s+to\s+(?:"
    r"(?:have|grab|do|set up)\s+a\s+(?:quick\s+|short\s+|virtual\s+)?(?:chat|call|coffee)"
    r"|chat|talk|meet|speak|(?:hop|jump)\s+on\s+a\s+(?:quick\s+)?call"
    r"|connect\s+(?:over|for|on)\s+(?:a\s+)?(?:quick\s+|short\s+|virtual\s+)?"
    r"(?:coffee|call|chat|zoom|teams))\b"
    r"(?!\s+(?:to|with)\s+(?:hr\b|our\b|the\b|an?\b|some(?:one|body)\b|any(?:one|body)\b"
    r"|people\b|recruit|talent|them\b|him\b|her\b))"
    r"|\blet'?s\s+(?:chat|talk|speak|meet|find a time|grab a (?:coffee|call|chat)|set up a (?:call|chat|time))\b"
    r"|\bcoffee chat\b"
    # The forms an invitation most often takes, which were read as a long generous message
    # and answered with "engage with the substance": "free for a 20 minute call", "available
    # for a quick call", "time for a chat", "set up a call", "arrange a 30-minute phone
    # screen", "open to a call". A call centre is somewhere, not a call.
    r"|\b(?:(?<!feel )free|available|time|open)\s+(?:for|to)\s+an?\s+" + _CALL +
    r"|\b(?:set\s+up|arrange|schedule|book|organi[sz]e)\s+(?:an?\s+|some\s+)?(?:time\s+for\s+an?\s+)?"
    + _CALL, re.I)


# An eligibility no is the one rejection that is about the applicant rather
# than the requisition. A test message such as "Thanks but we're only looking
# at people with <country> PR or citizenship for this one" went through as
# detailed_generous at 0.35, which advises engaging with the substance. The
# substance is a closed door.
#
# Named rather than inlined in the table because guidance() reads it too:
# this is the one rejection that carries a fact about the employer out of
# the thread.
ELIGIBILITY_NO = re.compile(
    r"\b(?:only (?:looking at|considering|able to consider|hiring))\b"
    r"[^.!?\n]{0,60}\b(?:pr\b|permanent residen\w+|citizens?h?i?p?\b|"
    r"clearance|status)\b|"
    r"\b(?:must|need to|have to|required to) (?:be|have|hold)\b"
    r"[^.!?\n]{0,40}\b(?:permanent residen\w+|" + _ADJ + r" citizen\w*|"
    r"security clearance|pr status)\b|"
    r"\b(?:we|they)\s*(?:'re|’re| are|do)?\s*(?:not|n't|unable to|cannot|can'?t)\s*"
    r"(?:able to\s+)?sponsor\w*\b|"
    r"\bno sponsorship (?:available|offered|provided)\b|"
    r"\bsponsorship is not (?:available|offered|something we)\b|"
    r"\b(?:requires?|needs?)\b[^.!?\n]{0,20}\b(?:security clearance|"
    r"permanent residen\w+|" + _ADJ + r" citizen\w*|pr status)\b"
, re.I)


REJECTION = _rx(
    (0.93, "says they are not hiring",
     r"\b(we|i)\s*(?:'re|’re| are|'m|’m| am)?\s*(not|no longer)\s+(currently\s+)?"
     r"(hiring|recruiting|looking|taking on|adding)\b"),
    # Real replies drop the subject: "Not hiring right now, sorry." is the most
    # common form of a no on LinkedIn and has no "we" in front of it to match on.
    (0.86, "says they are not hiring",
     r"\bnot (currently |actively |really )?(hiring|recruiting|taking anyone on)\b"),
    (0.9, "no open roles",
     r"\bno (open |current |live )?(roles|positions|openings|vacancies|headcount)\b|"
     r"\bnothing (open|available|going|live|at the moment|right now)\b|"
     r"\bnothing (that|which) (fits|matches|would suit)\b"),
    (0.9, "hiring is frozen",
     r"\b(hiring|headcount|recruitment)\s+(freeze|frozen|paused|on hold)\b|"
     r"\bwe(?:'ve|’ve| have) (paused|frozen|stopped) (hiring|recruiting)\b"),
    (0.88, "not their market",
     r"\bnot (really )?(my|our) (market|area|space|patch|remit|wheelhouse|world)\b|"
     r"\bI (can'?t|cannot|am not able to|won'?t be able to) help\b|"
     r"\boutside (my|our) (area|remit|scope)\b"),
    (0.85, "the role is gone",
     # Both word orders. "we have filled the role" put the verb first and did
     # not match, so a rejection carrying a signature address classified as
     # send_resume and the guidance said to email a resume into a no.
     r"\b(role|position|req)\b[^.!?\n]{0,25}\b(filled|closed|gone|withdrawn)\b"
     r"|\b(filled|closed|withdrawn|pulled)\b[^.!?\n]{0,25}\b(role|position|req|it)\b"
     r"|\bwe(?:'ve|\u2019ve| have)\s+(?:since\s+)?(?:filled|closed|withdrawn|pulled)\b"
     r"|\bthe\s+(?:role|position|req)\s+(?:has|is)\s+(?:been\s+)?(?:filled|closed|gone)\b"),
    (0.94, "eligibility, not the role", ELIGIBILITY_NO),

    # A no to the conversation itself, not to a role. These classified as
    # low_effort ("Not interested, thanks." is four words), whose guidance is to
    # propose two times: a call invitation to somebody who had said stop.
    (0.95, "asked not to be contacted",
     r"\b(?:please\s+)?(?:stop|don'?t|do not)\s+(?:messag|contact|email|writ|reach)\w*"
     r"|\bremove me\b|\bnot interested\b|\bno,? thanks?\b(?! (?:needed|necessary))"
     r"|\bno thank you\b"),
    (0.88, "declined the conversation",
     r"\b(?:can'?t|cannot|won'?t be able to|unable to|don'?t have)\s+(?:make\s+|find\s+)?"
     r"(?:the\s+)?time\b(?![^.!?\n]{0,40}\bbut\b)"
     # "I'll pass" is a no; "I'll pass it on" (_PASSED_ON) is the opposite, a referral,
     # and read as a no it blocked the resume ask beside it and counted as one of the two
     # declines that end a thread.
     r"|\b(?:going to|gonna|I'?ll|I will|will have to|have to|need to)\s+pass\b(?!" + _PASSED_ON + r")"
     r"|\bnot (?:the right|a good) (?:person|fit|contact)\b|\bwrong person\b"
     r"|\bdon'?t think I'?m the right (?:person|contact)\b"),
    # The same no as "I can't help", said more gently: read as a considered reply, it got
    # the generous guidance and never counted toward the two nos that end a thread
    # (2026-10-21). Pointed on to someone ("but try Wren in planning"), it is that route,
    # which the referral cues read, and no decline; any other "but" leaves it a no.
    (0.84, "a polite no",
     r"(?:\bnot\s+(?:really\s+|quite\s+)?sure\s+(?:that\s+)?I(?:\s+can|\s+could|['\u2019]d be "
     r"able to|\s+would be able to|['\u2019]ll be able to|\s+will be able to)\s+(?:really\s+)?help"
     r"|\bI\s+don['\u2019]?t\s+think\s+I(?:\s+can|\s+could|['\u2019]d be able to|\s+would be "
     r"able to|['\u2019]m able to|\s+am able to|['\u2019]ll be able to)\s+(?:really\s+)?help"
     r"|\bnot\s+(?:really\s+)?(?:the|a)\s+(?:best|right|ideal)\s+(?:person|one|contact)\s+"
     r"to\s+(?:help|ask|speak to|talk to)"
     r"|\bafraid\s+I\s+(?:can['\u2019]?t|cannot|won['\u2019]?t be able to|am not able to|"
     r"['\u2019]m not able to)\s+(?:really\s+)?help)\b"
     r"(?![^.!?\n]{0,40}\bbut\b[^.!?\n]{0,12}\b(?:try|talk|speak|ask|reach out|ping|"
     r"message|contact|email|drop)\b)"),
    (0.8, "brush-off to the careers page",
     r"\b(keep an eye on|watch|check|try|apply (through|via|on))\s+(our|the)\s+"
     r"(careers|jobs)\s+(page|site|board)\b"),
)

_OTHER_FUNCTIONS = getattr(_NET, "OTHER_FUNCTIONS", None)
# "I have moved to marketing" and "I switched over to sales" are the same fact
# as "I'm in marketing"; a move is also to product, design or operations.
_OTHER_FUNCTIONS_MOVED = getattr(_NET, "OTHER_FUNCTIONS_MOVED", None) or _OTHER_FUNCTIONS
_OWN_FUNCTION_WORDS = getattr(_NET, "OWN_FUNCTION_WORDS", None) or "that"

MISMATCH = _rx(
    (0.9, "no longer at the company",
     r"\bI\s+(left|no longer work|am no longer|moved on from|departed)\b|\bmy last day\b|"
     r"\bI(?:'ve|’ve| have) since (joined|moved|left)\b|\bI used to work\b|"
     r"\bI(?:'m|’m| am) now at\b"),
    (0.86, "a different function",
     # The functions that are not the person's, and the words for their own:
     # networking.py OTHER_FUNCTIONS and OWN_FUNCTION_WORDS, regex fragments.
     # "I'm in marketing" is a mismatch to a data analyst and a match to a
     # marketer, so neither list is the app's to set. Unset, only the
     # function-free shapes below count.
     (r"\bI(?:'m|\u2019m| am)\s+(in|on)\s+(" + _OTHER_FUNCTIONS + r")\b|"
      + (r"\bI(?:'m|\u2019m| am) a recruiter\b|" if "recruit" in _OTHER_FUNCTIONS else "")
      + r"\bI(?:'ve|\u2019ve)?\s+(?:have\s+)?(?:moved|switched|transferred|shifted)\s+"
      r"(?:over\s+)?(?:to|into)\s+(" + _OTHER_FUNCTIONS_MOVED + r")\b|"
      if _OTHER_FUNCTIONS else "")
     + r"\bI don'?t work (in|on|with) (" + _OWN_FUNCTION_WORDS + r")\b|"
     r"\bI do not work (in|on|with) (" + _OWN_FUNCTION_WORDS + r")\b|"
     r"\bdifferent (team|part of the business) entirely\b"),
    (0.86, "states there is no presence in this market",
     r"\bwe (don'?t|do not) (hire|recruit|have)\b[^.!?\n]{0,40}\b("
     + _COUNTRY + "|" + _CITY + r"|here)\b|"
     r"\bno (" + _ADJ + "|" + _CITY + r"|local)\s+(presence|team|office|hiring)\b|"
     r"\b(not|isn'?t) based in " + _COUNTRY + r"\b|"
     r"\b(team|group|function) is (all|entirely|only)\b[^.!?\n]{0,20}"
     r"\b(us|u\.s\.|states|uk|europe|india|australia)\b"),
    (0.8, "junior or still studying",
     r"\bI(?:'m|’m| am) (a|an) (student|intern|new grad|recent grad)\b|"
     r"\bI(?:'m|’m| am) (quite |fairly |pretty )?junior\b"),
)

DISCOURAGING = _rx(
    (0.88, "market commentary",
     r"\b(market|job market|hiring market)\b[^.!?\n]{0,30}"
     r"\b(tough|brutal|rough|terrible|awful|dire|slow|competitive|difficult|hard|quiet)\b"),
    (0.88, "market commentary",
     r"\b(tough|brutal|rough|hard|difficult|competitive|slow|quiet)\b[^.!?\n]{0,25}"
     r"\b(market|time to be looking|out there)\b"),
    (0.85, "volume of applicants",
     r"\b(hundreds|thousands|\d{3,})\b[^.!?\n]{0,25}\b(applicants|applications|candidates|resumes|cvs)\b"),
    (0.85, "told to expect a slog",
     r"\b(temper|manage|lower)\s+(your\s+)?expectations\b|"
     r"\bit(?:'ll|’ll| will| could| may| might) take (a while|months|time|a long time)\b|"
     r"\bbe prepared for a (long|slow)\b"),
    (0.82, "general gloom",
     r"\bnobody(?:'s|’s| is) hiring\b|\beveryone(?:'s|’s| is) (frozen|cutting)\b|"
     r"\b(layoffs|redundancies)\b[^.!?\n]{0,30}"),
)

# Their chase: the check-in phrases a draft of ours is refused for (tone.CHECK_IN), and
# the ones only a chase of theirs uses. These come first, so a cue reads as it always did.
CHASING = _rx(
    (0.9, "they are chasing us", re.compile(
        r"\b(?:did you (?:get|see|have a chance)|following up on my|"
        r"just (?:checking|bumping|nudging)|any (?:thoughts|update))\b|" + tone.CHECK_IN.pattern,
        re.I)),
    (0.88, "a call was missed",
     r"\b(missed (each other|you|our call|the call)|weren'?t able to connect|"
     r"couldn'?t find you|didn'?t manage to connect|no.?show|you weren'?t (on|there))\b"),
    (0.85, "asks whether we are still interested",
     r"\bstill (interested|keen|looking|on for)\b|\bno worries if (not|you'?re not)\b|"
     r"\bhaven'?t heard (back )?from you\b"),
)

GENEROUS = _rx(
    (0.82, "substantive and generous",
     r"\b(happy to|glad to|let me know|I(?:'d|’d| would) suggest|worth (a look|knowing)|"
     r"here(?:'s|’s| is) (how|what|the)|we (use|run|built|moved to|are building)|"
     r"my team|our team|the way (it|we) works?)\b"),
)


def _match_gone_quiet(text, ctx):
    if text.strip():
        return []
    if not ctx["has_inbound"]:
        return [(0.9, "nothing inbound in this thread: a nudge, not a reply")]
    if ctx.get("we_spoke_last"):
        return [(0.9, "they have not answered our last message: a nudge (if one is due), "
                      "not a reply")]
    return []


def _match_auto_reply(text, ctx):
    # Not a person: an out-of-office or a "no longer here" template (state.auto_reply).
    # It sits above everything that reads a message, because there is no message: the
    # address in its signature is not a resume ask, and its length is not effort.
    got = state.auto_reply(text, sent_on=ctx.get("today"))
    if not got:
        return []
    what = {"left": "an automatic reply saying they have left",
            "away": "an out-of-office reply"}.get(got["kind"], "an automatic reply")
    back = " (back %s)" % got["back_on"].isoformat() if got.get("back_on") else ""
    return [(0.95, "%s%s: %s" % (what, back, _quote(got["evidence"])))]


def _match_calendar_link(text, ctx):
    if not ctx["link"]:
        return []
    return [(0.95, "shared a booking link: %s" % ctx["link"])]


# "I have shared your profile with the hiring manager" is the sender reporting
# what they already did, not asking for anything, and it reads as a referral.
# Only a first-person subject sitting directly on a past-tense verb counts, so
# "I'd love it if you sent your resume" is still an ask.
_ALREADY_DONE = re.compile(
    r"\b(?:i|we)\s*(?:'ve|'ll)?\s*(?:have\s+|has\s+|had\s+|already\s+)*"
    r"(?:shared|passed|sent|forwarded|dropped|flagged|circulated)\b", re.I)


# The document itself, by name: what `asks_for_resume` needs, where the classifier also
# takes "send me your details" and an address in a signature as a resume to send.
_DOC_NAMED = re.compile(_SEND_VERBS + r"[^.!?\n]{0,40}\b(resume|r[eé]sum[eé]|cv|curriculum vitae"
                        + ("|" + re.escape(_NOUN_WORD) if _NOUN_WORD else "") + r")\b|"
                        + _DOC_OVER, re.I)


# Thanks for one already received: "thanks for sending the resume", "got your CV". The
# resume is with them, so nothing is owed: it was read as a new ask, and a second resume
# was put on the person's list the day the first was thanked for (journeys audit 8).
_THANKED_FOR = re.compile(
    r"\b(?:thanks?|thank\s+you|cheers|appreciated?|grateful)\b[^.!?\n]{0,20}?\bfor\s+"
    r"(?:\w+\s+){0,2}?" + _SEND_VERBS + r"[^.!?\n]{0,40}"
    r"|\b(?:got|received|have\s+got|have\s+received|now\s+have)\s+(?:your|the)\s+"
    r"(?:resume|r[eé]sum[eé]|cv|curriculum vitae)\b", re.I)


def _without_thanks(text: str) -> str:
    return _THANKED_FOR.sub(" ", text)


def asks_for_resume(text) -> bool:
    """Do they ask for the resume itself? "Send me your CV and I'll pass it on" does;
    their address in a signature, "send me your details", a no, a dead end, "I've
    passed your CV on" (done, not asked) and "thanks for sending your resume" do not. What
    the log reads a resume owed from (state.resumes_owed), where the classifier's wider net
    would owe one to every signature."""
    text = _without_thanks(str(text or ""))
    # The one cue first: most messages name no resume, and the checks that can only turn an
    # ask down (a no, a dead end, a referral field) were most of the time a page build spent
    # finding the resumes owed (2026-11-03).
    if not _DOC_NAMED.search(text):
        return False
    return not (_ALREADY_DONE.search(text) or _hits(text, REJECTION) or _hits(text, MISMATCH)
                or REFERRAL_FIELD.search(text))


def _match_send_resume(text, ctx):
    # A no outranks an address, whatever the ladder order says.
    #
    # send_resume sits above rejection in SCENARIOS and classify() takes the
    # first match rather than the most confident, so "Thanks but we are not
    # hiring right now. Best, Wren | wren@example.com" classified as send_resume
    # and the guidance told the user to email a resume to somebody who
    # had just turned them down. Every professional signature carries an
    # address, so the bare-address cue fires on almost every real rejection.
    #
    # The asymmetry in the note below was the wrong way round: a resume sent
    # into a no does not merely waste an email, it spends the relationship and
    # reads as not listening.
    # A referral-field instruction carries an address and is not a resume ask.
    # "Put <their address> in the referral field when you apply" means apply and
    # name them, not email them a PDF.
    blocked = (_hits(text, REJECTION) or _hits(text, MISMATCH)
               or bool(REFERRAL_FIELD.search(text)))
    asked = _without_thanks(text)
    hits = [] if (_ALREADY_DONE.search(asked) or blocked) else _hits(asked, RESUME_ASK)
    if ctx["email"] and not blocked:
        # An address with no ask around it is usually a signature block rather than
        # an invitation, and the classifier cannot tell the two apart. It still
        # classifies here, at a confidence that says "check this", because the cost
        # of a resume sent to a signature is far below the cost of one never sent.
        hits.append((0.95 if hits else 0.7, "gave an email address: %s" % ctx["email"]))
    return hits


def _match_referral(text, ctx):
    return _hits(text, REFERRAL)


# "I'm not available to chat", "I won't be free to talk", "not keen to talk about roles":
# the same words with a no in front of them, within a couple of words, are a decline.
# "Not sure I'm free to talk this week" is a hedge, not a no.
_NOT_BEFORE = re.compile(r"(?:\bnot|n['’]t|\bnever|\bno longer)\s+(?:[\w'’]+\s+){0,2}$", re.I)
_HEDGE = re.compile(r"not\s+(?:sure|certain)\b", re.I)


def offered_chat(text):
    """The words in which they offered a chat, or None: CHAT_OFFER with no no before it."""
    for m in CHAT_OFFER.finditer(text or ""):
        no = _NOT_BEFORE.search(text[max(0, m.start() - 40):m.start()])
        if not no or _HEDGE.match(no.group(0)):
            return m.group(0)
    return None


def _match_chat_offer(text, ctx):
    said = offered_chat(text)
    return [(0.9, "offered a chat: %s" % _quote(said))] if said else []


def _match_mismatch(text, ctx):
    return _hits(text, MISMATCH)


def _match_rejection(text, ctx):
    # "Not hiring right now, but happy to chat" is a yes to the conversation:
    # read as a rejection, the guidance closed a door they had just opened.
    if accepts(text):
        return []
    return _hits(text, REJECTION)


def _match_user_at_fault(text, ctx):
    hits = _hits(text, CHASING)
    if ctx["late_business_days"] >= LATE_REPLY_BUSINESS_DAYS:
        hits.append((0.8, "their message has sat unanswered for %d business days"
                     % ctx["late_business_days"]))
    return hits


def _match_discouraging(text, ctx):
    return _hits(text, DISCOURAGING)


def _match_low_effort(text, ctx):
    if is_reaction(text):
        return [(0.95, "a reaction, not a message: %s" % _quote(text))]
    if not ctx["words"] or ctx["words"] > LOW_EFFORT_WORDS:
        return []
    return [(0.88, "%d words: %s" % (ctx["words"], _quote(text)))]


def _match_detailed(text, ctx):
    hits = []
    if ctx["words"] >= DETAILED_WORDS:
        hits.append((0.8, "%d words of considered reply" % ctx["words"]))
    hits.extend(_hits(text, GENEROUS))
    return hits if hits else []


# ---------------------------------------------------------------- the ladder


@dataclass(frozen=True)
class Scenario:
    """One row of the playbook: what happened, what to do, how long, what is owed."""
    name: str
    move: str
    sentences: tuple              # (floor, ceiling) the computed length clamps into
    owes_action: bool             # is there something to do outside the thread
    next_action: str              # may carry {email} or {link}
    do_not: tuple
    matcher: Callable = field(compare=False, repr=False, default=None)


# The person's word for the document, and the one their market does not use:
# person.json documents.noun and banned_nouns. The guidance said "Email the
# resume" and "Do not attach a file named CV" to a person whose document is a
# CV, which is the opposite of their rule.
_DOCS = person.get("documents", {}) or {}
_NOUN = _DOCS.get("noun", "resume")
_NOUN_RULE = tuple(f"Do not attach a file named {b}; the attachment says {_NOUN}."
                   for b in _DOCS.get("banned_nouns", [])[:1])

# Sent when they asked for the resume but left no address. Asking for one is a
# reply; guessing at a corporate address format is how a first impression lands
# in a bounce folder.
NO_ADDRESS_ACTION = (f"Ask for the best address, or attach the {_NOUN} in this thread if the "
                     "channel carries attachments.")

# Which resume goes, said with every action that sends one. A networking chat said "Email
# the resume today", a drafting chat made one, and nothing said which, or recorded which
# went: a role they named gets one made for it, through the referral route; no role named
# gets the person's current one, never a document tailored to a guess at the role.
RESUME_ROUTE_SCENARIOS = frozenset({"send_resume", "referral_offered"})


def resume_routes(contact_id="<contact_id>", referral_field=False) -> str:
    """The two routes to the resume that goes, and the command that logs it with its file.

    `referral_field`: they said to apply and name them, so nothing is sent to them: the
    resume goes in through the portal, drafted for them so the tracker files it under
    their route."""
    if referral_field:
        return (f"Which {_NOUN}: one drafted for the role and filed under them: python3 "
                "tools/stage_picks.py single <dir> --company <their employer> --role <the role> "
                f"--posting-file <the posting> --for-contact {contact_id} --referral-field. "
                f"{state.route_words(state.ROUTE_PORTAL)[:1].upper()}"
                f"{state.route_words(state.ROUTE_PORTAL)[1:]}, so there is no message to log: "
                "tell them in the thread once the application is in.")
    try:
        import docpaths
        current = docpaths.resume_to_offer()
    except Exception:  # noqa: BLE001  no profile, or no documents/cv/
        current = ""
    if not current:
        return (f"Which {_NOUN}: for a role they named, one made for it and for them: python3 "
                "tools/stage_picks.py single <dir> --company <their employer> --role <the role> "
                f"--posting-file <the posting> --for-contact {contact_id}. With no role named, "
                f"there is no {_NOUN} of yours the app made and checked to send, and an older "
                f"file is never sent: make one for them first (the page offers Make one for them, "
                "or python3 tools/stage_picks.py general <dir>), then log it with the file: "
                f"python3 tools/network/state.py message {contact_id} --attached <the file> "
                "--text-file <the message as sent>.")
    return (f"Which {_NOUN}: for a role they named, one made for it and for them: python3 "
            "tools/stage_picks.py single <dir> --company <their employer> --role <the role> "
            f"--posting-file <the posting> --for-contact {contact_id}. With no role named, your "
            f"current {_NOUN} ({current}), never one tailored to a "
            f"guess at the role. When it goes, log it with the file: python3 "
            f"tools/network/state.py message {contact_id} --attached <the file> --text-file "
            "<the message as sent>.")


# Sent when the scenario is a booking but the message carries no link, which
# happens when the user overrides the read by hand. Formatting the template
# anyway printed "Book a slot at , then confirm in the thread", an instruction
# with nowhere to go that reads as a working one.
NO_LINK_ACTION = ("No booking link in the message: propose two specific times in "
                  + TIMEZONE + " rather than asking them to pick.")

# Iteration order is the precedence ladder, and every entry below is here because
# two cues collide in real messages:
#
#   gone_quiet        first, because with nothing inbound there is no message to read
#   auto_reply        an out-of-office or "no longer here": a machine, so nothing below
#                     applies (its signature's address is not an ask, its length not effort)
#   calendar_link     an offered slot expires; booking it is the only urgent action
#   send_resume       an ask or an address, even buried in four generous paragraphs
#   referral_offered  outranks a no, because "we are not hiring but talk to Wren"
#                     is a referral with a decline attached, not a decline
#   chat_offered      a call or a coffee offered: a yes to the conversation, whatever
#                     "not much overlap" or "not hiring" sits beside it
#   mismatch          the person cannot help at all, which decides more than a no does
#   rejection         a decision, so it outranks both the apology and the word count
#   user_at_fault     an apology is the opener, never the whole move
#   discouraging_market  commentary, not a decision
#   low_effort        word count only decides once no cue has fired
#   detailed_generous last, and the fallback when nothing matched at all
SCENARIOS = {s.name: s for s in (
    Scenario(
        name="gone_quiet",
        move="One nudge, short, with a reason to answer now. Never a second.",
        sentences=(2, 2),
        owes_action=False,
        next_action="",
        do_not=(
            "Do not nudge inside 5 business days; it reads as impatience.",
            "Do not send a second nudge on the same thread.",
            "Do not repeat the original message; give them a reason to answer now.",
        ),
        matcher=_match_gone_quiet,
    ),
    Scenario(
        name="auto_reply",
        move=("Nothing to answer: an automatic reply, not them. Log it inbound with scenario "
              "auto_reply and leave the thread as it is; it is not a reply, not a warm route, "
              "and nothing is owed."),
        sentences=(0, 0),
        owes_action=False,
        next_action="",
        do_not=(
            "Do not reply to the automatic message.",
            "Do not count it as their answer: the thread is still waiting on them.",
            "Do not spend the one nudge before they are back.",
        ),
        matcher=_match_auto_reply,
    ),
    Scenario(
        name="calendar_link",
        move="Book a slot, then confirm in the thread so they know it is done.",
        sentences=(1, 2),
        owes_action=True,
        next_action=("Book a slot at {link}, then confirm in the thread. Set the timezone "
                     "field explicitly to " + TIMEZONE + ", give the invite a real "
                     "title and a one-line description, attach the video link, and check "
                     "the date is the one you meant and not today."),
        do_not=(
            "Do not invent a timezone abbreviation; write "
            + (TIMEZONE_ABBR + " or " if TIMEZONE_ABBR else "") + TIMEZONE + ".",
            "Do not confirm a slot before it is actually booked.",
            "Do not send a paragraph; one line saying it is booked.",
        ),
        matcher=_match_calendar_link,
    ),
    Scenario(
        name="send_resume",
        move=(f"Email the {_NOUN} now, attached, with a short context paragraph. Say once in "
              "the thread that it is sent."),
        sentences=(1, 2),
        owes_action=True,
        next_action=("Email the " + _NOUN + " to {email} today, attached, with a short "
                     "paragraph of context so they do not have to go and find the original "
                     "message."),
        do_not=(
            "Do not wait to be asked twice.",
            "Do not over-trim the email; someone who asked for it expects substance.",
            *_NOUN_RULE,
        ),
        matcher=_match_send_resume,
    ),
    Scenario(
        name="referral_offered",
        move=(f"Accept immediately and make it easy: offer the {_NOUN} unprompted, one "
              "clarifying question at most."),
        sentences=(2, 4),
        owes_action=True,
        next_action=(f"Have the {_NOUN} ready to send, and record the chain in "
                     "network_contacts.csv (route=referral, referred_by) so the intro "
                     "message can lead with their name."),
        do_not=(
            "Do not bury the referrer's name when writing to the person they named.",
            f"Do not make them chase you for the {_NOUN}.",
            "Do not ask more than one clarifying question.",
        ),
        matcher=_match_referral,
    ),
    Scenario(
        name="chat_offered",
        move=("Say yes in a line and settle a time: confirm the one they gave, or propose two "
              "specific times in " + TIMEZONE + " rather than asking them to pick."),
        sentences=(1, 3),
        owes_action=True,
        next_action=("Settle the time in the thread, and once it is agreed record the call: "
                     "state.py set <contact> --status call_booked --next-action \"Call on "
                     "<date>\" --due <date>."),
        do_not=(
            "Do not answer the substance at length; that is what the chat is for.",
            f"Do not ask for a referral or send the {_NOUN} in this reply; the conversation "
            "comes first.",
            "Do not ask them to suggest a time from nothing; give two.",
        ),
        matcher=_match_chat_offer,
    ),
    Scenario(
        name="mismatch",
        move=("Tell the user plainly that this is a dead end. A polite two-line exit, then "
              "move on."),
        sentences=(2, 2),
        owes_action=False,
        next_action="",
        do_not=(
            "Do not draft an optimistic message to keep the thread alive.",
            "Do not ask for a referral into a company they have left.",
            "Do not spend an InMail credit here.",
        ),
        matcher=_match_mismatch,
    ),
    Scenario(
        name="rejection",
        move="Close gracefully and short. One low-cost ask only if they engaged genuinely.",
        sentences=(2, 3),
        owes_action=False,
        next_action="",
        do_not=(
            "Do not argue and do not re-pitch.",
            "Do not ask for the onward name unless they engaged genuinely.",
            "Do not stack thanks.",
        ),
        matcher=_match_rejection,
    ),
    Scenario(
        name="user_at_fault",
        move="Apologise once, plainly, own it, and propose a concrete alternative.",
        sentences=(3, 4),
        owes_action=False,
        next_action="",
        do_not=(
            "Do not stack apologies; once, plainly.",
            "Do not over-explain the reason.",
            "Do not pretend the gap did not happen when it has been weeks.",
        ),
        matcher=_match_user_at_fault,
    ),
    Scenario(
        name="discouraging_market",
        move=("Acknowledge the read without adopting it. Say whether it is generally true "
              "but not specific to this search."),
        sentences=(2, 4),
        owes_action=False,
        next_action="",
        do_not=(
            "Do not argue with them about the market.",
            "Do not let one person's read reshape the search.",
            "Do not sound defensive about the profile.",
        ),
        matcher=_match_discouraging,
    ),
    Scenario(
        name="low_effort",
        move=(f"Move it forward with one concrete, low-friction step: offer the {_NOUN}, or "
              "propose two specific times."),
        sentences=(1, 2),
        owes_action=False,
        next_action="",
        do_not=(
            "Do not read it as enthusiasm, and do not read it as a brush-off.",
            "Do not send a paragraph in reply to one word.",
            "Do not ask an open question that needs thought; give them something to accept.",
        ),
        matcher=_match_low_effort,
    ),
    Scenario(
        name="detailed_generous",
        move=("Engage with the substance. Pick the two or three most useful specifics and "
              "answer those."),
        sentences=(2, 6),
        owes_action=False,
        next_action="",
        do_not=(
            "Do not restate their points back at them; it is the clearest tell of a "
            "machine-written reply.",
            "Do not answer every point; pick the two or three worth engaging with.",
            "Do not ask more than one genuine question.",
            # A sender who describes what is keeping their team busy, to explain why
            # they need nobody yet, is giving context. A draft that offers to help with
            # that work answers a question the message never asked.
            "Do not offer help with what they described as their own workload; that was "
            "context, not a request. Answer the question they actually asked.",
        ),
        matcher=_match_detailed,
    ),
)}

PRECEDENCE = tuple(SCENARIOS)

# What to say when a next_action template has a placeholder and nothing to put in
# it. Every scenario whose action carries `{email}` or `{link}` needs an entry
# here; the test suite pins that, so a new scenario cannot ship an action with a
# blank destination in it.
NO_DESTINATION = {
    "send_resume": NO_ADDRESS_ACTION,
    "calendar_link": NO_LINK_ACTION,
}

# Nothing matched. Engaging with the substance at matched length is the safe
# default, and the confidence says plainly that it was a default rather than a
# read, so the skill layer can ask instead of guessing confidently.
FALLBACK = "detailed_generous"
FALLBACK_CONFIDENCE = 0.35


# ---------------------------------------------------------------- target length

# Their words, mapped to the sentences we send back. The brief's rule is "match
# their effort, roughly": two informal lines earns two lines, four paragraphs
# earns real engagement, and a mismatch in either direction reads badly.
#
# Words rather than sentences, because "ok. sure. thanks." is three sentences and
# no effort at all, and one 90-word paragraph is effort with a single full stop.
# Each scenario then clamps the result into its own band, which is what stops a
# 400-word rejection earning a 6-sentence answer.
TARGET_LADDER = ((6, 1), (25, 2), (60, 3), (120, 4), (250, 5))
TARGET_MAX = 6


def _sentences_for_words(words: int) -> int:
    for limit, target in TARGET_LADDER:
        if words <= limit:
            return target
    return TARGET_MAX


def effort_sentences(text) -> int:
    """How many sentences their message earns, before the scenario clamps it."""
    return _sentences_for_words(word_count(text))


def target_sentences(text, scenario=None) -> int:
    """The effort-matched length, clamped to the scenario's band."""
    n = effort_sentences(text)
    if scenario is None:
        return n
    low, high = _resolve(scenario).sentences
    return max(low, min(high, n))


# ---------------------------------------------------------------- classify


def _row_text(row) -> str:
    return str(row.get("full_text") or row.get("summary") or "")


def _contact_ids(rows) -> set:
    return {i for i in (str(r.get("contact_id") or "").strip() for r in rows) if i}


def _one_contact(rows, what: str) -> None:
    """Refuse a message log that belongs to more than one person.

    `state.load_threads()` returns the whole file and the obvious call passes it
    straight in, which is silent rather than wrong-looking: a nudge clock run
    over two contacts reads somebody else's reply as this thread's and reports
    "they answered" on a thread nobody answered. Naming the filter in the error
    is the whole fix.
    """
    ids = _contact_ids(rows)
    if len(ids) > 1:
        raise ValueError(
            "%s takes one contact's messages, got %d (%s). Filter with "
            "state.threads_for(threads, contact_id) first."
            % (what, len(ids), ", ".join(sorted(ids)[:4])))


def _late_business_days(history, today) -> int:
    """Business days their last message has sat unanswered, 0 when we are not the late ones."""
    spoken = [r for r in history if not state.is_acceptance(r) and not state.is_auto_reply(r)]
    if today is None or not spoken:
        return 0
    last = spoken[-1]
    if not _inbound(last):
        return 0
    when = state.as_date(last.get("date"))
    if when is None:
        return 0
    return max(0, state.business_days_between(when, today))


def classify(inbound_text, thread_history=(), today=None) -> dict:
    """The scenario, how confident the read is, and what it was read from.

    `thread_history` is that contact's rows from network_threads.csv. It is not
    decoration: it carries the two facts the message itself cannot show, namely
    that nothing has ever come back (`gone_quiet`) and that their last message has
    been sitting unanswered long enough that the reply opens with an apology.

    Passing an empty `inbound_text` is the nudge case, and it falls back to the
    last logged inbound message so that re-classifying an old thread does not
    silently become a nudge.
    """
    rows = list(thread_history or [])
    _one_contact(rows, "classify")
    history = [r for r in _ordered(rows) if _direction(r)]
    inbound_rows = [r for r in history if _inbound(r)]
    text = without_own_address(inbound_text).strip()
    # Their last message is the one to read only while it is still the last
    # word. Once we have answered it, an empty paste is a quiet thread: reading
    # the old message again re-drafted a CV already sent, or a second nudge.
    we_spoke_last = bool(history) and not _they_spoke_last(history)
    if not text and inbound_rows and not we_spoke_last:
        text = without_own_address(_row_text(inbound_rows[-1])).strip()

    ctx = {
        "email": extract_email(text),
        "link": extract_scheduling_link(text),
        "words": word_count(text),
        "sentences": sentence_count(text),
        "has_inbound": bool(inbound_rows),
        "we_spoke_last": we_spoke_last,
        "late_business_days": _late_business_days(history, today),
        "today": state.as_date(today) if today else None,
    }

    scored = []
    for name, scenario in SCENARIOS.items():
        hits = scenario.matcher(text, ctx)
        if hits:
            scored.append({"scenario": name,
                           "confidence": _confidence(hits),
                           "evidence": [e for _, e in hits]})

    if scored:
        best = scored[0]
        runners = scored[1:]
    else:
        evidence = ["no scenario cue matched"]
        if not text:
            # A logged inbound row with no text: the summary column was filled in
            # and the message body never was. Saying so is more use than a
            # confident classification of nothing.
            evidence = ["the logged inbound message carries no text"]
        best = {"scenario": FALLBACK, "confidence": FALLBACK_CONFIDENCE, "evidence": evidence}
        runners = []

    return {"scenario": best["scenario"],
            "confidence": best["confidence"],
            "evidence": best["evidence"],
            "runners_up": runners,
            "email": ctx["email"],
            "scheduling_link": ctx["link"],
            "words": ctx["words"],
            # The day it was read for, so guidance() reads "back on 5 January" against it.
            "today": ctx["today"].isoformat() if ctx["today"] else "",
            # The message itself, so `guidance(classify(t))` has everything it
            # needs without the caller passing the text a second time. Any rule
            # in guidance that reads the message silently saw "" without it.
            "text": text}


# ---------------------------------------------------------------- guidance


def _resolve(scenario) -> Scenario:
    """A Scenario from a name, a Scenario, or a whole classify() result.

    Accepting the classification dict whole means the skill layer cannot pass the
    wrong half of it, which is the one integration mistake that produces confident
    guidance for a scenario nobody classified.
    """
    if isinstance(scenario, Scenario):
        return scenario
    name = scenario.get("scenario") if isinstance(scenario, dict) else scenario
    name = str(name or "")
    if name not in SCENARIOS:
        raise KeyError("unknown scenario %r; expected one of %s" % (name, ", ".join(PRECEDENCE)))
    return SCENARIOS[name]


def _as_int(value) -> int:
    """A word count read back off a classification result, 0 when it is not one."""
    try:
        return max(int(value), 0)
    except (TypeError, ValueError):
        return 0


def guidance(scenario, their_message="", contact_id="") -> dict:
    """The move, the length it should run to, what to avoid, and what is owed outside the thread.

    `their_message` is read for two things: the length rule in brief 5.2, and the
    address or booking link that turns the next action from advice into an
    instruction with a destination in it.

    `contact_id` fills the commands `which_resume` names: for a resume they asked for, or a
    referral that will want one, which file goes and how it is logged (`resume_routes`).

    When `scenario` is a whole `classify()` result and the message is not passed
    again, the result is read for all three. `classify` already extracted them
    from the message it was given, and the obvious two-line call site is
    `guidance(classify(text))`: without this it silently loses the address and
    answers four paragraphs in two sentences, both of which look like working
    output.
    """
    sc = _resolve(scenario)
    read = scenario if isinstance(scenario, dict) else {}
    text = str(their_message or "") or str(read.get("text") or "")
    email = extract_email(text) or str(read.get("email") or "")
    link = extract_scheduling_link(text) or str(read.get("scheduling_link") or "")
    words = word_count(text) or _as_int(read.get("words"))

    next_action = ""
    if sc.owes_action:
        missing = any(token in sc.next_action and not value
                      for token, value in (("{email}", email), ("{link}", link)))
        # A template with an unfilled destination is the one case where saying
        # nothing useful beats saying something that reads as an instruction.
        next_action = (NO_DESTINATION[sc.name] if missing
                       else sc.next_action.format(email=email, link=link))

    # An eligibility no is the one rejection that carries outside the thread.
    # When the person's work authorization, as the profile states it
    # (networking.py STATUS_NAME), does not clear the bar, "PR or citizenship
    # only" and "we cannot sponsor" are standing facts about that employer, and
    # the search should stop surfacing their gated roles rather than
    # rediscovering the same no through a second application. Nothing else in
    # the system would learn it: the tracker records outcomes per application,
    # not per employer.
    if sc.name == "rejection" and ELIGIBILITY_NO.search(text):
        next_action = (next_action + " " if next_action else "") + (
            "Record this against the employer, not just this role: they have "
            "stated an eligibility bar the " + STATUS_NAME + " does not clear. Their "
            "citizenship-gated roles should stop being surfaced.")

    if sc.name == "auto_reply":
        # The day classify() was given, so "back on 5 January" read on 28 December is the
        # coming January; without it the year was the wall clock's, and the date a past one.
        next_action = auto_reply_action(text, sent_on=read.get("today") or None)

    low, high = sc.sentences
    out = {"move": sc.move,
           "target_sentences": max(low, min(high, _sentences_for_words(words))),
           "do_not": list(sc.do_not),
           "next_action": next_action}
    if sc.name in RESUME_ROUTE_SCENARIOS:
        # Beside the next action, never inside it: the address and the resume are two
        # questions, and a next action that asks for the address is that and nothing more.
        out["which_resume"] = resume_routes(contact_id or "<contact_id>",
                                            referral_field=bool(REFERRAL_FIELD.search(text)))
    return out


def auto_reply_action(text, sent_on=None) -> str:
    """What to do about an automatic reply: wait for their return, or find who replaced them."""
    got = state.auto_reply(text, sent_on=sent_on) or {}
    if got.get("kind") == "left":
        return ("They have left: this address no longer reaches them. Close the contact "
                "(state.py set <contact> --status closed --note \"left\") and find who holds "
                "the role now, rather than nudging an inbox nobody reads.")
    if got.get("back_on"):
        return ("They are away until %s. The thread is still waiting on them: the one nudge "
                "waits until %d working days after they are back (%s)."
                % (got["back_on"].isoformat(), state.AWAY_GRACE_BUSINESS_DAYS,
                   state.add_business_days(got["back_on"],
                                           state.AWAY_GRACE_BUSINESS_DAYS).isoformat()))
    return ("The thread is still waiting on them: the nudge follows the usual clock from your "
            "message.")


# ---------------------------------------------------------------- judgment


def _they_spoke_last(rows) -> bool:
    """Is the last message theirs? An acceptance after it changes nothing either way.
    One answer, the one the follow-up log reads too (state.they_spoke_last)."""
    return state.they_spoke_last(rows)


def _rows_for(contact, threads):
    """That contact's messages, whether the caller filtered them or not.

    Filtering on contact_id and returning nothing when the caller has already
    filtered would report "no declines" for a thread full of them, which is the
    exact failure this function exists to prevent.
    """
    rows = list(threads or [])
    cid = str((contact or {}).get("contact_id") or "").strip()
    if _contact_ids(rows) - {cid}:
        # The rows name somebody else, so this is the whole file rather than one
        # thread and filtering is the only safe read. Counting every row would let
        # two declines belonging to a different contact close a conversation that
        # had never had a no in it.
        return state.threads_for(rows, cid)
    return _ordered(rows)


# What turns a "not hiring" into a yes to the conversation: they offered time,
# help or a slot in the same message. "We're not hiring right now but happy to
# chat" counted as a decline, so two such messages on a booked call read as two
# nos and /reply recommended closing it.
# A chat offered counts too (`accepts`), read with its guard: "I'm not available to chat"
# is a no.
ACCEPTS = re.compile(
    r"\b(?:happy|glad|keen) to (?:chat|talk|meet|speak|have a call)\b"
    r"|\b(?:works|suits) (?:for )?(?:me|us)\b"
    r"|\b(?:mon|tues|wednes|thurs|fri|satur|sun)day\b[^.!?\n]{0,25}\b(?:works|suits|is (?:fine|good|free))\b"
    r"|\b\d{1,2}(?::\d{2})?\s?(?:am|pm)\b[^.!?\n]{0,20}\b(?:works|suits)\b"
    r"|\blet'?s (?:chat|talk|speak|meet|find a time|grab)\b", re.I)


def accepts(text) -> bool:
    """Did they say yes to the conversation: a time, a slot, or a chat offered."""
    return bool(ACCEPTS.search(text or "") or offered_chat(text))


def declines_in(threads) -> list:
    """Their messages that say no, with the phrase each was read from.

    A message that says no to a role and yes to the conversation in the same
    breath ("not hiring, but happy to chat") is not a decline.
    """
    found = []
    for row in threads:
        if not _inbound(row):
            continue
        text = _row_text(row)
        hits = _hits(text, REJECTION)
        if not hits:
            continue
        # GENEROUS is too wide to excuse a no: it holds "my team" and "let me
        # know", so "We are not hiring on my team right now" stopped counting
        # and the stop-after-two-nos rule never fired.
        if accepts(text) or extract_scheduling_link(text) or extract_email(text):
            continue
        # A no that points them on ("I can't help, but talk to Wren in planning") is read
        # as a referral, and counted as a no it ended the thread the referral opened.
        if _hits(text, REFERRAL):
            continue
        found.append({"date": row.get("date", ""), "evidence": hits[0][1]})
    return found


def should_continue(contact, threads=()) -> tuple:
    """Whether this thread is worth another ask, and why. (bool, reason).

    Counted from the messages rather than read off the contact row, because the
    row is hand-edited and the messages are evidence. The brief's rule is the
    whole of it: after two nos, stop. A third ask reads as not listening, and the
    relationship is worth more later than the ask is worth now.
    """
    contact = contact or {}
    rows = _rows_for(contact, threads)
    stored = str(contact.get("status") or "").strip()
    if stored in STOP_STATUSES:
        return False, "the thread is already %s; reopening it needs a new reason, not a nudge" % stored
    if stored in LIVE_STATUSES:
        return True, ("the thread is at %s: a 'not hiring' inside it is information, not a no; "
                      "keep going" % stored)

    nos = declines_in(rows)
    if len(nos) >= MAX_DECLINES:
        return False, ("%d explicit declines in the thread (%s). Stop here: a third ask after "
                       "two nos costs the relationship and gains nothing."
                       % (len(nos), "; ".join(n["evidence"] for n in nos[:MAX_DECLINES])))
    if len(nos) == 1:
        return True, ("one decline so far (%s). One low-cost ask is warranted if they engaged "
                      "genuinely, then stop." % nos[0]["evidence"])
    return True, "no decline in the thread; it is worth continuing"


# ---------------------------------------------------------------- nudge timing


# Scenarios whose outbound row leaves something concretely outstanding. A resume
# they asked for, a call that was booked, an introduction requested: each one is
# a thing the reader can be reminded OF. Everything else is just a message that
# was sent.
PENDING_SCENARIOS = frozenset({
    "send_resume", "send_email", "ask_referral", "intro_request",
    "scheduling", "calendar_link", "application_sent",
})

# An inbound row that promises something. "I will see about openings" is a
# commitment with a lead time, and chasing inside it reads as not trusting them
# to do what they said.
_COMMITMENT = re.compile(
    r"\bI(?:'ll| will| shall)\b|\blet me (?:look|check|see|ask|find)"
    r"|\bget back to you\b|\bcome back to you\b|\bwill see\b|\blooking into\b",
    re.I)


def following_up_is_honest(threads, today=None) -> tuple:
    """Whether "following up on X" is a truthful frame for this thread.

    The phrase says something is outstanding. That is true when they asked for a
    resume and it went unacknowledged, and false after a conversation that
    concluded with nobody promising anything: there the writer is not following
    up, they are asking for a status, and saying "following up" on a call
    somebody gave you their time for reads as poking a person who owes you
    nothing. The check exists because a draft to a contact who had given their
    time on a call opened that way.

    Returns (honest, reason). The reason is written to be shown to a person.
    """
    rows = [r for r in _ordered(list(threads or [])) if _direction(r)]
    if not rows:
        return False, "nothing has been sent on this thread yet"
    if _they_spoke_last(rows):
        return False, "they spoke last; a reply is owed, not a follow-up"

    # A commitment from them outranks a pending item from us, because the pending
    # item is usually the very thing they undertook to handle: a contact who
    # asks for the resume AND says "I will see about openings" has made the
    # unacknowledged resume their promise in progress, not our loose end. It
    # only outranks while it is fresh; once the window has passed the promise is
    # itself the outstanding thing and the follow-up is fair.
    inbound = [r for r in rows if _inbound(r)]
    if inbound and _COMMITMENT.search(_row_text(inbound[-1])):
        # The clock starts when they could actually act, not when they promised.
        # "Send it to my email and I will see about openings" is conditional on
        # something we owe, so a resume delivered four days later resets it: a
        # promise made on a Monday has not started running until the resume
        # arrives on the Friday. Measuring from the promise would make a fresh
        # commitment look days staler than it was and turn a premature chase
        # into a due one.
        said = state.as_date(inbound[-1].get("date"))
        delivered = [state.as_date(r.get("date")) for r in rows
                     if _direction(r) == "out" and state.as_date(r.get("date"))]
        after = [d for d in delivered if said and d >= said]
        started = max(after) if after else said
        waited = (state.business_days_between(started, today)
                  if (started and today) else 0)
        if not today or not started or state.as_date(today) < state.follow_up_on(started):
            return False, ("they committed to something%s and the clock is theirs; chasing inside "
                           "it reads as not trusting them to do it"
                           % (" %d business days ago" % waited if today else ""))

    trailing = []
    for row in reversed(rows):
        if state.is_acceptance(row) or state.is_auto_reply(row):
            continue
        if _inbound(row):
            break
        trailing.append(row)
    pending = [r for r in trailing
               if str(r.get("scenario") or "").strip().lower() in PENDING_SCENARIOS]
    if pending:
        what = str(pending[0].get("scenario") or "").replace("_", " ")
        return True, "an unacknowledged %s is genuinely outstanding" % what

    return False, ("nothing was promised, so there is no pending item to follow up ON. Ask for a "
                   "status, or give them something, but do not open on 'following up'")


def nudge_due(threads, today, new_development="") -> dict:
    """Whether a nudge is due on this thread, and when it will be.

    The trigger is `state.follow_up_on`: the person's own FOLLOW_UP_DAYS where
    profile/networking.py sets them, else `schema.FOLLOWUP_BUSINESS_DAYS` (a 5 to 7
    business-day window), shared with `state.owed` so /reply and /threads cannot
    disagree about the same thread on the same morning. Calendar
    days are what make a follow-up read as impatient: six of them from a Wednesday
    is the following Tuesday, and the person has had two working days to answer.

    `new_development` is the brief's one exception. A role going live or a company
    announcement is a reason to write sooner and reads as initiative, so it fires
    early, but it still cannot buy a second nudge.
    """
    given = list(threads or [])
    _one_contact(given, "nudge_due")
    rows = [r for r in _ordered(given) if _direction(r)]
    window = "follow-up window of %d to %d business days" % NUDGE_WINDOW
    base = {"due": False, "reason": "", "business_days": 0, "nudges_sent": 0,
            "due_date": "", "last_out": "", "window": NUDGE_WINDOW}

    if not rows:
        return dict(base, reason="nothing has been sent on this thread yet")
    if state.is_withdrawal(rows[-1]):
        return dict(base, reason=("the connection request was withdrawn: nothing reached them, "
                                  "and the thread is closed"))
    if state.request_pending(rows) is not None:
        return dict(base, reason=("the connection request has not been accepted, so there is "
                                  "nowhere to send a nudge: wait, or withdraw it after %d days"
                                  % state.REQUEST_WITHDRAW_DAYS))
    if state.inmail_only(rows):
        return dict(base, reason=("they have only been sent an InMail and have not replied: "
                                  "another would be a second InMail, not a follow-up"))
    if state.accepted_never_messaged(rows) is not None:
        return dict(base, reason=("they accepted a request that carried no note and nothing has "
                                  "been sent since: a first message is owed "
                                  "(compose.first_note), not a nudge"))
    if state.call_held(rows[-1]):
        return dict(base, reason=("the last thing on this thread is a call, not a message: what "
                                  "follows it (a thank-you, the referral ask) is in next_action"))
    if _they_spoke_last(rows):
        return dict(base, reason="they answered; a reply is owed, not a nudge")

    # What chases them, never a message answering them (state._chases).
    nudges = state._chases(rows) - 1
    # The last row is an acceptance when that is the last thing that happened,
    # and its date is the one the networking skill counts from: "from the
    # acceptance, not from the send". An automatic reply is not: the clock runs
    # from our message, and an away message's return date holds the nudge.
    real = [r for r in rows if not state.is_auto_reply(r)] or rows
    sent = state.as_date(real[-1].get("date"))
    base["nudges_sent"] = max(nudges, 0)
    base["last_out"] = sent.isoformat() if sent else ""
    if sent is None:
        return dict(base, reason="the last outbound message has no usable date")
    due_on = state.follow_up_on(sent)
    back = state.away_until(rows)
    if back is not None:
        due_on = max(due_on, state.add_business_days(back, state.AWAY_GRACE_BUSINESS_DAYS))
    base["due_date"] = due_on.isoformat()

    waited = state.business_days_between(sent, today)
    base["business_days"] = waited
    if nudges >= schema.MAX_NUDGES:
        return dict(base, reason=("%d messages have gone with no reply, the most your follow-up "
                                  "rule allows (%s); another costs more than it recovers. Let "
                                  "it go cold." % (nudges + 1, schema.follow_up_rule())))
    if back is not None and state.as_date(today) < due_on:
        return dict(base, reason=("an automatic reply says they are away until %s: the nudge "
                                  "waits until %s, when they have had time to see it"
                                  % (back.isoformat(), base["due_date"])))
    if new_development and waited >= 1:
        return dict(base, due=True,
                    reason="new development (%s) is a legitimate reason to write inside the %s"
                           % (new_development, window))
    if state.as_date(today) < due_on:
        return dict(base, reason="%d business days since the last message; due %s (%s)"
                    % (waited, base["due_date"], schema.follow_up_rule()))
    return dict(base, due=True,
                reason="%d business days of silence, past %s" % (waited, schema.follow_up_rule()))


# ---------------------------------------------------------------- one command each side of the draft

# A reply pasted into a chat took about fifteen steps before the person saw the draft, five
# of them spent finding how a received message is logged (2026-11-03), and every step reads
# the whole chat again. `prepare` is everything before the draft in one command: who it is,
# their message logged, what it is, whether a reply is owed, the guidance, the thread and
# what the person has taught it. `finish` is everything after: the draft check, the draft
# put where the page shows it, what drew the reply, and the page's finishing batch. The
# draft between them is the chat's own.

THREAD_SHOWN = 6
TEXT_SHOWN = 400


def find_contact(contacts, who, company="") -> dict:
    """{"row", "sure", "how", "others"}: the contact `who` names, by their id, their profile
    address or their name (`company` narrows it to one employer). `sure` only for an id, an
    address or a name one row carries; otherwise `row` is None and `others` holds who it
    could be (two rows with the name; a nickname, an initial or a letter out; the first name
    alone), each as (row, why), so nothing is logged to the wrong person's thread."""
    want = " ".join(str(who or "").split())
    pool = list(contacts or ())
    if company:
        key = state.company_key(company)
        pool = [c for c in pool if state.row_company_key(c) == key]
    out = {"row": None, "sure": False, "how": "", "others": []}
    if not want:
        return out
    row = state.already_contacted(pool, contact_id=want)
    if row is None and "linkedin.com/" in want.lower():
        row = state.already_contacted(pool, linkedin_url=want)
        if row is not None:
            return dict(out, row=row, sure=True, how="profile address")
    if row is not None:
        return dict(out, row=row, sure=True, how="contact id")
    key = state._match_name(want)
    same = [c for c in pool if key and state._match_name(c.get("name")) == key]
    if len(same) == 1:
        return dict(out, row=same[0], sure=True, how="name")
    if same:
        return dict(out, how="the same name", others=[(c, "the same name") for c in same])
    words = state.person_name(want).split()
    near = []
    for c in pool:
        if len(words) >= 2:
            _how, why = state._why_same(want, c.get("name"))
            if why:
                near.append((c, why))
        elif len(words) == 1:
            given, _mid, surname, _gen = state._name_parts(c.get("name"))
            w = state._bare(words[0])
            if w and (w in (given, surname) or (given and state.same_given_name(w, given))):
                near.append((c, "one name only"))
    return dict(out, how="near", others=near)


def _one_line(text, most=TEXT_SHOWN) -> str:
    t = " ".join(str(text or "").split())
    return t if len(t) <= most else t[:most - 3].rstrip() + "..."


def _who_line(c) -> str:
    title, company = str(c.get("title") or "").strip(), str(c.get("company") or "").strip()
    return ", ".join(x for x in (str(c.get("name") or "").strip(),
                                 " at ".join(y for y in (title, company) if y)) if x)


def _reader(c) -> str:
    try:
        import compose
        return compose.reader_type(c.get("title") or "")
    except Exception:  # noqa: BLE001  the brief still reads without a reader
        return ""


def _words(path, prog):
    """A file's words, or the command's input for "-" (a heredoc: one step, not two)."""
    if path == "-":
        return sys.stdin.read()
    return state._words_from(path, prog)


def needs_no_answer(text, scenario="") -> str:
    """The words that say they will come back to the person ("I'll get back to you"), in a
    message that asks nothing and owes no action, or "": /reply step 2's message that needs
    no answer. A short thanks back is the person's call, never a reply owed."""
    sc = SCENARIOS.get(str(scenario or ""))
    if (sc is not None and sc.owes_action) or "?" in str(text or ""):
        return ""
    m = _COMMITMENT.search(str(text or ""))
    return m.group(0) if m else ""


# Their words that close a conversation kindly for now: they will keep the person in mind,
# or wish them luck. Not a promise to come back ("I'll get back to you"), which a later
# follow-up may fairly ask after.
_KEEP_IN_MIND = re.compile(
    r"\bkeep (?:you|your (?:details|profile|name|cv|r[ée]sum[ée]))\b[^.!?\n]{0,30}?"
    r"\b(?:in mind|on file|on (?:my|our) radar)\b"
    r"|\b(?:have|has) your (?:details|profile|name|cv|r[ée]sum[ée]) on file\b"
    r"|\b(?:best of|good) luck\b|\ball the best\b|\bwish(?:ing)? you (?:the best|luck|well)\b",
    re.I)
# Our answer that only thanks them: nothing asked, nothing offered, nothing sent.
_THANKS = re.compile(r"\b(?:thanks?|thank you|cheers|much appreciated|appreciate (?:it|that))\b",
                     re.I)
_ASKS_OR_OFFERS = re.compile(
    r"\?|\b(?:let me know|would you|could you|can you|are you|do you|happy to|keen to|"
    r"(?:i'?d|i would|would) love to|any chance|available|attached|attaching|here(?:'s| is) my)\b",
    re.I)
CLOSE_WORDS = 60


def closing_exchange(theirs, ours, scenario="") -> str:
    """The words that end a conversation kindly for now, or "": their message asks nothing
    and owes nothing, and either keeps the person in mind ("I'll keep you in mind", "good
    luck") or says no, and ours only thanks them. Nothing is chased after it: a follow-up to
    "Thanks so much!" asks after a door they closed kindly (2026-11-05: one was set, due the
    same day). A message of theirs later is owed a reply as any other."""
    t, o = str(theirs or ""), " ".join(str(ours or "").split())
    if not t or not o or len(o.split()) > CLOSE_WORDS or not _THANKS.search(o) \
            or _ASKS_OR_OFFERS.search(o):
        return ""
    scen = str(scenario or "")
    sc = SCENARIOS.get(scen)
    if "?" in t or (sc is not None and sc.owes_action):
        return ""
    m = _KEEP_IN_MIND.search(t)
    if m:
        return m.group(0)
    if scen in ("rejection", "mismatch") or (not scen and _hits(t, REJECTION)):
        return "their no"
    return ""


# A LinkedIn conversation copied whole: each block opens on who wrote it and when ("Juno
# Castellan  10:42 AM", "Juno Castellan sent the following message at 10:42 AM", "Juno
# Castellan · 10:42 AM"), under a line for the day ("Today", "Monday", "Oct 24", "24 October
# 2026"), with "View Juno's profile" lines between. Logged whole, the person's own words were
# two rows of theirs on one day (2026-11-05).
_CLOCK = r"\d{1,2}[:.]\d{2}\s*(?:[ap]\.?\s?m\.?)?"
_SPEAKER = re.compile(r"^(?P<name>[^\W\d_][\w'’.-]*(?:[ \t]+[^\W\d_][\w'’.-]*){0,4}?)"
                      r"[ \t]*(?:[·•|-][ \t]*|[ \t]+sent the following messages?"
                      r"(?:[ \t]+at)?[ \t]+|[ \t]+)(?P<time>" + _CLOCK + r")[ \t]*$", re.I)
_VIEW = re.compile(r"^view\b.{1,80}\bprofile$|^(?:seen|sent|delivered|read)\b.{0,30}$", re.I)
_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_MONTHS = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
_DAY_LINE = re.compile(
    r"^(?:(?P<rel>today|yesterday)|(?P<wd>mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)[a-z]*"
    r"|(?P<m1>" + _MONTHS + r")[ \t]+(?P<d1>\d{1,2})(?:,?[ \t]+(?P<y1>\d{4}))?"
    r"|(?P<d2>\d{1,2})[ \t]+(?P<m2>" + _MONTHS + r")(?:,?[ \t]+(?P<y2>\d{4}))?"
    r"|(?P<iso>\d{4}-\d{2}-\d{2}))$", re.I)


def _day_line(line: str, today):
    """The day a line of a pasted conversation names on its own, or None."""
    import datetime
    m = _DAY_LINE.match(" ".join(line.split()))
    if not m:
        return None
    if m.group("rel"):
        return today - datetime.timedelta(days=0 if m.group("rel").lower() == "today" else 1)
    if m.group("wd"):
        want = next(i for i, w in enumerate(_WEEKDAYS) if w.startswith(m.group("wd").lower()[:3]))
        back = (today.weekday() - want) % 7 or 7
        return today - datetime.timedelta(days=back)
    if m.group("iso"):
        return state.as_date(m.group("iso"))
    mon, d, y = ((m.group("m1"), m.group("d1"), m.group("y1")) if m.group("m1")
                 else (m.group("m2"), m.group("d2"), m.group("y2")))
    try:
        month = datetime.datetime.strptime(mon[:3].title(), "%b").month
        got = datetime.date(int(y) if y else today.year, month, int(d))
    except ValueError:
        return None
    if not y and got > today:
        got = got.replace(year=got.year - 1)
    return got


def _own_names() -> tuple:
    """(the person's first name, their full name), lower case, from person.json."""
    try:
        first = str(person.get("identity.first", "") or "")
        full = str(person.get("identity.name", "") or "")
    except Exception:  # noqa: BLE001
        first, full = "", ""
    first = first or (full.split() or [""])[0]
    return first.strip().lower(), " ".join(full.split()).lower()


def pasted_thread(text, their_name, today) -> list[dict] | None:
    """A LinkedIn conversation pasted whole, as its messages: [{"who": "them" or "me",
    "date", "text"}], oldest first, each block under its sender's line and dated by the day
    line above it (`today` where none is). Whose a block is comes from the name on its line:
    the person's own (person.json) or the contact's. None when the paste is one message, with
    no sender lines in it."""
    own_first, own_full = _own_names()
    them = " ".join(str(their_name or "").split()).lower()
    them_first = (them.split() or [""])[0]
    if not them_first:
        return None
    day, who, buf, out = today, None, [], []

    def flush():
        words = "\n".join(buf).strip()
        if who and words:
            out.append({"who": who, "date": day, "text": words})
        buf.clear()

    for line in str(text or "").splitlines():
        s = line.strip()
        m = _SPEAKER.match(s)
        name = " ".join(m.group("name").split()).lower() if m else ""
        sender = None
        if name and (name == them or name.split()[0] == them_first):
            sender = "them"
        elif name and (name == own_full or name.split()[0] == own_first):
            sender = "me"
        if sender:
            flush()
            who = sender
            continue
        d = _day_line(s, today) if s and len(s) <= 24 else None
        if d is not None:
            flush()
            day = d
            continue
        if _VIEW.match(s) or s.lower() in (them, own_full):
            continue
        buf.append(line)
    flush()
    return out if out else None


def prepare(argv) -> int:
    import argparse
    import datetime
    ap = argparse.ArgumentParser(
        prog="reply.py prepare",
        description="Everything before a reply is drafted, in one go: who wrote, their "
                    "message logged with its words, what kind of message it is, whether a "
                    "reply is owed, the guidance, the thread, and the person's own rules.")
    ap.add_argument("who", help="their contact id, or their name as it appears")
    ap.add_argument("--text-file", default="",
                    help="their message, as it came; - reads it from the input (none: their "
                         "newest logged message, as for the page's Reply)")
    ap.add_argument("--company", default="", help="their employer, when two people share a name")
    ap.add_argument("--date", default="", help="the day it came (default today)")
    ap.add_argument("--channel", default="", choices=("",) + state.RECEIVED_CHANNELS,
                    help="default: the way the thread runs (a message on LinkedIn)")
    ap.add_argument("--scenario", default="", help="what it is, where the reading here is wrong")
    ap.add_argument("--subject", default="")
    ap.add_argument("--contacts", default=state.CONTACTS_CSV)
    ap.add_argument("--threads", default=state.THREADS_CSV)
    ap.add_argument("--today", default=datetime.date.today().isoformat())
    a = ap.parse_args(argv)
    text = _words(a.text_file, "prepare") if a.text_file else ""
    if text is None:
        return 2
    contacts = state.load_contacts(a.contacts)
    threads = state.load_threads(a.threads) if os.path.exists(a.threads) else []
    found = find_contact(contacts, a.who, a.company)
    if not found["sure"]:
        if not found["others"]:
            print(f"prepare: nobody called {a.who!r} is in the contact book"
                  + (f" at {a.company}" if a.company else "") + ". Add them the networking "
                  "skill's way, then run this again. Nothing was logged.")
            return 2
        print(f"prepare: not sure who {a.who!r} is ({found['how']}), so nothing was logged. "
              "Run it again with their contact id:")
        for c, why in found["others"][:8]:
            print(f"  {c.get('contact_id')}: {_who_line(c)} ({why})")
        return 2
    c = found["row"]
    cid = str(c.get("contact_id") or "").strip()
    day = state.as_date(a.date or a.today) or datetime.date.today()
    before = [r for r in state.threads_for(threads, cid) if _direction(r)]
    theirs = [r for r in before if _direction(r) == "in" and _inbound(r)]
    reader = _reader(c)
    print(f"contact: {_who_line(c)} ({cid}), found by {found['how']}"
          + (f"; writes as a {reader.replace('_', '-')}" if reader else ""))
    body = state._paragraphs(text)
    # A conversation pasted whole: only their messages, each on its own day; the person's own
    # words are never logged as theirs (2026-11-05).
    pasted = pasted_thread(text, c.get("name"), day) if body else None
    if pasted is not None:
        mine = [i for i, m in enumerate(pasted) if m["who"] == "me"]
        theirs_p = [m for m in pasted if m["who"] == "them"]
        if not theirs_p:
            print(f"prepare: the conversation pasted holds no message from {_first(c)}, only "
                  "yours, so nothing was logged.")
            return 2
        tail = [m for m in pasted[(mine[-1] + 1 if mine else 0):] if m["who"] == "them"]
        body = "\n\n".join(m["text"] for m in tail) or theirs_p[-1]["text"]
        day = (tail or theirs_p)[-1]["date"]
        print(f"pasted: a conversation of {len(pasted)} message(s); {len(theirs_p)} from "
              f"{_first(c)} read as theirs" + (f", {len(mine)} of yours left out" if mine else ""))
    if not body:
        # The page's Reply, or "draft my reply to Juno": their newest message, already logged.
        if not theirs or not _they_spoke_last(before):
            print("reply owed: no: nothing of theirs is waiting, the last word is yours. A "
                  "follow-up, if one is due, is python3 tools/followup_drafts.py --contact "
                  f"{cid}.")
            return 0
        body = _row_text(theirs[-1]).strip()
        day = state.as_date(theirs[-1].get("date")) or day
    read = classify(body, before, day)
    scen = re.sub(r"[\s-]+", "_", a.scenario.strip().lower()) or read["scenario"]
    logged = bool(text.strip()) and pasted is None
    if pasted is not None:
        added = 0
        for m in theirs_p:
            last = m is theirs_p[-1]
            try:
                got = state.received(contacts, threads, cid, a.today, text=m["text"],
                                     date=m["date"].isoformat(), channel=a.channel,
                                     scenario=scen if last else "", subject=a.subject)
            except ValueError as e:
                if not str(e).startswith("already logged"):
                    print(f"prepare: not recorded: {e}")
                    return 1
                continue
            added += 1
            print(f"received: {got['row']['summary']} on {got['row']['date']}, read as "
                  f"{got['row']['scenario'] or '?'}")
            if got["said"]:
                print(f"  {got['said']}")
        if added:
            state.save_threads(threads, a.threads)
            state.save_contacts(contacts, a.contacts)
            state._interview_times(c.get("company"), contacts, threads, a.today)
        else:
            print("received: every message of theirs in it is logged already; nothing logged "
                  "twice")
        if mine and mine[-1] > max(i for i, m in enumerate(pasted) if m["who"] == "them"):
            print("  your own message is the last in it: if it went, log it with python3 "
                  f"tools/network/state.py message {cid} --text-file <it>")
    # Their newest message carrying these words is this one, logged already (by another chat,
    # the page, or the LinkedIn download): never a second row for it.
    if logged and theirs and state._same_words_sent(theirs[-1].get("full_text"), body):
        logged = False
        print(f"received: already logged on {theirs[-1].get('date') or '?'}; nothing logged "
              "twice")
    if logged:
        try:
            got = state.received(contacts, threads, cid, a.today, text=text,
                                 date=a.date or None, channel=a.channel, scenario=scen,
                                 subject=a.subject)
        except ValueError as e:
            if not str(e).startswith("already logged"):
                print(f"prepare: not recorded: {e}")
                return 1
            print(f"received: {e}; nothing logged twice")
            logged = False
    if logged:
        state.save_threads(threads, a.threads)
        state.save_contacts(contacts, a.contacts)
        row = got["row"]
        print(f"received: {row['summary']} on {row['date']}, read as {row['scenario'] or '?'}; "
              f"now {c.get('status') or '?'}")
        if got["said"]:
            print(f"  {got['said']}")
        state._interview_times(c.get("company"), contacts, threads, a.today)
    print("scenario: %s (confidence %.2f)" % (scen, read["confidence"] if scen == read["scenario"]
                                               else 1.0))
    for line in read["evidence"] if scen == read["scenario"] else ["given with --scenario"]:
        print(f"  evidence: {line}")
    for other in read["runners_up"]:
        print("  also matched: %s (%.2f)" % (other["scenario"], other["confidence"]))
    machine = scen in state.AUTO_REPLY_SCENARIOS or state.auto_reply(body, a.subject, day)
    if machine:
        print("reply owed: no, it is an automatic reply. "
              + auto_reply_action(body, sent_on=day.isoformat()))
        print("Nothing to draft.")
        return 0
    advice = guidance(dict(read, scenario=scen), body, contact_id=cid)
    go_on, why = should_continue(c, threads)
    cue = needs_no_answer(body, scen)
    if not go_on:
        print(f"reply owed: not another ask: {why}. A short warm close, if anything.")
    elif cue:
        print(f"reply owed: probably not: they said they will come back to the person "
              f"(\"{cue}\"). If so, draft nothing: python3 tools/network/state.py no-reply "
              f"{cid} --why \"<what they said>\". A short thanks is the person's call.")
    else:
        print("reply owed: yes, they wrote last.")
    print(f"move: {advice['move']}")
    print(f"length: {advice['target_sentences']} sentences")
    if advice["next_action"]:
        print(f"owed outside the thread: {advice['next_action']}")
    if advice.get("which_resume"):
        print("which %s: %s" % (_NOUN, advice["which_resume"].split(": ", 1)[-1]))
    for line in advice["do_not"]:
        print(f"  avoid: {line}")
    rows = [r for r in state.threads_for(threads, cid) if _direction(r)]
    print(f"the thread, oldest first (the last {min(len(rows), THREAD_SHOWN)} of {len(rows)}):")
    for r in rows[-THREAD_SHOWN:]:
        who = "them" if _direction(r) == "in" else "you"
        print(f"  {r.get('date') or '?'} {who} ({state.channel_of(r) or '?'}): "
              f"{_one_line(_row_text(r)) or '(no words logged)'}")
    try:
        import learned
        rules = learned.brief("messages", channel="reply", reader=reader or None)
        waiting = learned.refuse_over_pending("drafting")
    except Exception:  # noqa: BLE001  the app itself, with no profile: the defaults apply
        rules, waiting = "", ""
    print("before drafting, what the person has taught it (follow these over any default):")
    print("\n".join("  " + ln for ln in (rules or "(nothing learned yet: the defaults "
                                                  "apply)").splitlines()))
    if waiting:
        print(f"first: {waiting}")
    print(f"then: python3 tools/network/reply.py finish {cid} --draft-file - with the reply "
          "on its input (for the page's work: --work <id> --dump \"$D\").")
    return 0


def _first(c) -> str:
    try:
        return tone.first_name(c.get("name")) or "them"
    except Exception:  # noqa: BLE001
        return (str(c.get("name") or "").split() or ["them"])[0]


def save_draft(contact_id: str, text: str, msgs=None) -> str:
    """The reply, saved where the page's Messages shows it with Copy and "I sent it"
    (documents/network/<id>/draft.md), as it stands: a reply rests on their message, never
    on a profile read, so it carries no marker. Logged only once they say it went. Beside it,
    what of theirs it answers (`state.note_draft_answers`, from `msgs`, their message rows,
    or the log): a message of theirs it never saw sets it aside."""
    import reading
    path = reading.draft_path(contact_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(str(text).strip() + "\n")
    try:
        state.note_draft_answers(contact_id, msgs)
    except Exception:  # noqa: BLE001  the draft stands without it
        pass
    return path


def finish(argv) -> int:
    import argparse
    import datetime
    import json
    ap = argparse.ArgumentParser(
        prog="reply.py finish",
        description="Everything after a reply is drafted: the draft check (refused while it "
                    "finds anything), the draft put where the page shows it, what drew their "
                    "reply, and, for the page's work, its finishing batch. Nothing is sent.")
    ap.add_argument("contact_id")
    ap.add_argument("--draft-file", required=True,
                    help="the reply as drafted; - reads it from the input")
    ap.add_argument("--work", default="", help="the page's work item this answers")
    ap.add_argument("--thread", default="", help="the page's conversation (default: the item's own)")
    ap.add_argument("--dump", default="", help="the page's database, as read ($D)")
    ap.add_argument("--summary", default="", help="one short sentence (default: the reply is ready)")
    ap.add_argument("--kind", default="", choices=("", "cloud", "computer"))
    ap.add_argument("--out", default="", help="where the batch goes (default <dump>/out)")
    ap.add_argument("--contacts", default=state.CONTACTS_CSV)
    ap.add_argument("--threads", default=state.THREADS_CSV)
    ap.add_argument("--today", default=datetime.date.today().isoformat())
    ap.add_argument("--now", default=None)
    a = ap.parse_args(argv)
    if a.work and not a.dump:
        print("finish: --work needs the page's database as read (--dump \"$D\")")
        return 2
    draft = _words(a.draft_file, "finish")
    if draft is None:
        return 2
    draft = draft.strip()
    contacts = state.load_contacts(a.contacts)
    threads = state.load_threads(a.threads) if os.path.exists(a.threads) else []
    c = state.already_contacted(contacts, contact_id=a.contact_id.strip())
    if c is None:
        print(f"finish: no contact {a.contact_id!r} in the contact book (prepare names their id)")
        return 2
    cid = str(c.get("contact_id")).strip()
    if not draft:
        print("finish: the draft file is empty")
        return 2
    try:
        import learned
        waiting = learned.refuse_over_pending("finish")
    except (ImportError, SystemExit):
        waiting = ""
    if waiting:
        # What the person said about a draft is recorded before any draft is saved, as every
        # composer refuses to draft over it.
        print(f"REFUSED, nothing saved. {waiting}")
        return 1
    import followup_drafts
    # A follow-up to the person's own unanswered message is checked as the follow-up it is:
    # checked as a reply, every one to someone who never wrote was refused as having nothing
    # to reply to, and the page's Follow up could not be finished (2026-11-04).
    import compose
    rows = [r for r in state.threads_for(threads, cid) if _direction(r)]
    kind = "reply"
    if compose.unanswered_ours(rows) is not None:
        kind = "message" if state.channel_of(c) == "email" else "nudge"
    got = followup_drafts.check([{"id": cid, "text": draft, "kind": kind}], contacts,
                                threads, a.today)[0]
    if got["findings"]:
        print("finish: REFUSED, nothing saved: the draft check found what must change first.")
        for f in got["findings"]:
            print(f"  fix: {f}")
        print("Rewrite it and run finish again.")
        return 1
    print(f"check: passed ({len(draft)} characters)")
    for w in got["warnings"]:
        print(f"  warning: {w}")
    if got["warnings"]:
        print("  Rewrite what a warning is right about before it is shown; a soft close is "
              "allowed in a reply.")
    path = save_draft(cid, draft, state.threads_for(threads, cid))
    import local_path
    print(f"saved: {local_path.rel(path, person.state())}, shown in the page's Messages with "
          "Copy and \"I sent it\". Nothing is sent; it is logged only once they say it went.")
    extra = []
    try:
        import what_works
        said = what_works.event_contact(contacts, threads, cid, a.today)
    except Exception:  # noqa: BLE001  counting must never stop a reply
        said = ""
    if said:
        # For Claude, never for the person: the counts ("35 of 627 answered") reached the
        # reply on the page while they were part of the answer (2026-11-05). Said here, marked
        # as Claude's, and never added to what the page shows.
        print(f"what worked (for you, not for the reply): {said}")
    try:
        import tips
        tip = ""
        if person.exists("person.json"):
            kept = tips.load()
            tip = tips.line("reply", state=kept)
            if tip:
                tips.save(kept)
    except Exception:  # noqa: BLE001
        tip = ""
    if tip:
        extra.append(tip)
        print(f"end with: {tip}")
    print("Show the draft in full, ready to copy, never only where it was saved.")
    if not a.work:
        return 0
    import app_listen
    import app_model
    import page_db
    _, now = app_model.clock(None, a.now)
    db = page_db.load(a.dump)
    first = _first(c)
    what = "reply" if kind == "reply" else "follow-up"
    answer = "\n\n".join([f"Your {what} to {first}, ready to copy (nothing is sent):", draft]
                         + extra)
    item = ((db.get("work") or {}).get(page_db.safe_id(a.work)) or {}).get("data") or {}
    args = item.get("args") if isinstance(item.get("args"), dict) else {}
    thread = a.thread or str(args.get("thread") or "")
    summary = a.summary or (f"Your {what} to {first} is ready to copy"
                            + ("." if thread else " in Messages."))
    try:
        done = page_db.finish(db, a.work, now, a.out or os.path.join(a.dump, "out"),
                              summary=summary, reply=answer if thread else "", thread=thread,
                              chat_kind=a.kind or app_listen.chat_kind(), dump_dir=a.dump)
    except (KeyError, ValueError) as e:
        print(f"finish: the page's work not finished: {e.args[0] if e.args else e}")
        return 2
    print("page: send each batch (ArtifactData batch), then bring the page up to date "
          "(app.py view, the app skill's step 5):")
    print(json.dumps(done, ensure_ascii=False, indent=1))
    return 0


# ---------------------------------------------------------------- CLI


def main() -> int:
    if sys.argv[1:2] == ["prepare"]:
        return prepare(sys.argv[2:])
    if sys.argv[1:2] == ["finish"]:
        return finish(sys.argv[2:])
    if sys.argv[1:2] in (["-h"], ["--help"]):
        print('usage: python3 tools/network/reply.py "<their message>" (or on stdin): what kind '
              "of reply it is, and the evidence")
        return 0
    text = " ".join(sys.argv[1:]).strip()
    if not text and not sys.stdin.isatty():
        text = sys.stdin.read().strip()
    result = classify(text)
    advice = guidance(result, text)
    print("scenario: %s (confidence %.2f)" % (result["scenario"], result["confidence"]))
    for line in result["evidence"]:
        print("  evidence: %s" % line)
    for other in result["runners_up"]:
        print("  also matched: %s (%.2f)" % (other["scenario"], other["confidence"]))
    print("move: %s" % advice["move"])
    print("length: %d sentences" % advice["target_sentences"])
    if advice["next_action"]:
        print("owed outside the thread: %s" % advice["next_action"])
    if advice.get("which_resume"):
        print("which %s: %s" % (_NOUN, advice["which_resume"].split(": ", 1)[1]))
    for line in advice["do_not"]:
        print("  avoid: %s" % line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
