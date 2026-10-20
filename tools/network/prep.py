#!/usr/bin/env python3
"""The prep document for a call that came out of a thread (brief section 8).

Read in the five minutes before the call, on a phone, while walking to a desk.
So the output is shorthand: one fact per line, headings that can be found by
eye, and nothing that has to be read twice. Prose is what a prep doc turns into
when nobody is honest about how it gets used.

Three decisions carry most of this file.

**Every fact prints with its source, or it does not print.** `sourced()` binds a
value to where it came from and `Unsourced` is what the renderer raises when a
value arrives with no attribution. The failure this prevents is specific: a
salary band, a headcount or a funding round that sounded right, got written
down, and then got said out loud on a call where the other person knows the real
number. A blank line costs nothing. An invented one costs the conversation. The
one asymmetry is deliberate: facts pulled from `profile_facts` fall back to
`PROFILE_SOURCE`, because that dict comes from the candidate profile by contract
and naming the file is real attribution, while a research dict can come from
anywhere and has to say where it came from before anything in it is printed.

**Compensation bands are a parameter, never a table in this file.** A checked-in
band is stale the week after it is written, cannot be shown to anyone, and is
indistinguishable from a guess by the time it reaches the document. Bands move
by market, by quarter, by company and by level, and the only defensible band is
one somebody looked up and can name. So `comp_band` renders what the skill layer
researched and attributes it, and with nothing passed in it prints "not
researched" rather than a number. That is the whole design: this module cannot
produce a compensation figure on its own, by construction.

**Nothing here writes prose.** The draft answers are the profile's own wording,
placed against the question it answers. Turning that into something the user
would actually say is a model's job and it happens in the skill layer, where a
model call belongs. A generator that paraphrased the profile would be inventing
the one thing the brief says must never be invented.

Documents land in `documents/network/<contact_id>/prep.md`: beside the
per-application folders `tools/outreach.py` writes, not inside them. A thread is
not an application, and a call that has not converted yet has no application
folder to sit in.

Usage:
    from prep import prep_markdown, write_prep
    path = write_prep(contact, research, application, facts, threads, today="2030-01-15")

    python3 tools/network/prep.py "<contact>"          # one contact's document
    python3 tools/network/prep.py --stale-only         # only those an older prep wrote, or
                                                       # written before the thread moved
    python3 tools/network/prep.py "<contact>" --check  # are its answers fit to say aloud?
    python3 tools/network/prep.py --all [--dry-run]    # every contact's; --dry-run lists, writes nothing
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys
from typing import NamedTuple

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (_HERE, os.path.dirname(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import company_research as research_cache  # noqa: E402
import compose  # noqa: E402
import learned  # noqa: E402
import person  # noqa: E402
import profile_facts  # noqa: E402
import state  # noqa: E402
import tone  # noqa: E402
import voice_check  # noqa: E402
import what_works  # noqa: E402
import why  # noqa: E402
from company_key import key as company_key  # noqa: E402

# A band that names no currency is written in the market's (search.py CURRENCY_CODE).
_CURRENCY_CODE = getattr(person.module("search"), "CURRENCY_CODE", "")
# How a caller is likely to ask about the person's route into the work; a
# networking.py may phrase it for the story it answers (PREP_ROUTE_QUESTION).
_NET = person.module("networking") if person.exists("networking.py") else None
_ROUTE_QUESTION = (getattr(_NET, "PREP_ROUTE_QUESTION", "")
                   or "Walk me through how you got into this work.")

ROOT = os.path.dirname(os.path.dirname(_HERE))
# Where the documents are written and the research is read: the person's state
# root (person.state), which is the repo root unless LJS_STATE moves it.
STATE_ROOT = person.state()
PREP_DIR = ("documents", "network")
# The cache and its freshness rule are tools/company_research.py's; these names
# stay so a caller that imported them from here still finds them.
RESEARCH_DIR = research_cache.DIR
RESEARCH_FRESH_DAYS = research_cache.RESEARCH_FRESH_DAYS

# Where a fact is allowed to say it came from when the caller does not name a
# more specific source. These are files in the repo, so "source: X" stays
# checkable rather than becoming a shrug.
PROFILE_SOURCE = os.path.relpath(
    person.file("candidate_profile", "01-candidate-profile.md"), ROOT).replace(os.sep, "/")
CONTACTS_SOURCE = "network_contacts.csv"
THREADS_SOURCE = "network_threads.csv"
TRACKER_SOURCE = "job_search_tracker.csv"
# Where the phrases the person has said never to use are kept (tools/learned.py).
LEARNED_SOURCE = os.path.relpath(person.path(learned.FILE), ROOT).replace(os.sep, "/")

# The phrase the document uses for anything nobody looked up. One phrase, used
# everywhere, so the user learns to read past it instead of mistaking a blank
# section for a clean bill of health.
NOT_RESEARCHED = "not researched"

# Section headings, in reading order. Named here so the skill layer, the tests
# and anything parsing the document agree, and so a renamed heading breaks
# loudly instead of quietly disappearing from a doc nobody proofreads.
SECTIONS = (
    "Who they are",
    "Thread so far",
    "Their team",
    "The company",
    "Compensation",
    "They will likely ask",
    "Ask them",
    "Fit, honestly",
    "Tone for this call",
)

# Caps, all for the same reason: this is read in five minutes. The research
# cache holds a dozen facts and a thread can hold thirty messages, and printing
# all of them produces a document that gets skimmed instead of read.
MAX_FACTS = 4
MAX_NEWS = 3
MAX_THREAD_LINES = 6
MAX_QUESTIONS = 5
MAX_FACT_QUESTIONS = 2

# The generic fact questions all anchor the same way, so the tail is what stops
# two of them reading as one question asked twice. A prep doc that reused one
# tail printed "How much of that reaches the work day to day?" under two
# consecutive facts, which is exactly the tell this is meant to avoid.
# One tail per slot, so the cap and the rotation cannot drift apart.
FACT_QUESTION_TAILS = (
    "How much of that reaches the work day to day?",
    "What is the part of that an outsider would get wrong?",
)
MAX_STRENGTHS = 3
MAX_GAPS = 3
ANCHOR_CHARS = 90


class Unsourced(ValueError):
    """A fact offered with nothing to attribute it to.

    Raised rather than returned because there is no partial version of this
    problem: a number with no source cannot be printed with a caveat, it has to
    be researched or dropped.
    """


class Fact(NamedTuple):
    """A value and where it came from, kept together so they cannot separate."""

    value: str
    source: str


_WS = re.compile(r"\s+")

# The value and attribution spellings that actually arrive. The research cache
# writes `claim`/`source_url`, a hand-written dict writes `value`/`source`, and
# a scraped one writes `text`/`url`. Accepting all three beats making every
# caller translate, and a translation step is where sources get dropped.
_VALUE_KEYS = ("value", "claim", "text", "fact", "note", "summary", "detail")
# `sources` is deliberately absent: the research cache uses that key for a dict
# of source records, and treating it as an attribution string would print the
# whole nested structure into a bullet.
_SOURCE_KEYS = ("source", "source_url", "url", "cite", "citation")


def _text(value) -> str:
    """One line of plain text from whatever was passed.

    Newlines are collapsed because the research cache stores paragraph-long
    notes and a markdown bullet that contains a line break stops being a bullet.
    """
    if value is None:
        return ""
    return _WS.sub(" ", str(value)).strip()


def sourced(value, source) -> Fact:
    """Bind a value to its source, refusing anything that has neither.

    The gate the whole module runs through. Raises `Unsourced` when there is a
    value and no attribution, because that is the case where something false
    gets printed; a blank value is just a line the caller should not have tried
    to write, and raises a plain ValueError.
    """
    text = _text(value)
    if not text:
        raise ValueError(
            "sourced() was given nothing to attribute (%r). A blank fact is not a "
            "fact: leave the line out rather than printing an empty one." % (value,))
    cite = _text(source)
    if not cite:
        raise Unsourced(
            "%r has no source. This document is read out loud in a call, so a fact "
            "the user cannot attribute is one they cannot defend. Research it or "
            "leave it out." % (text[:80],))
    return Fact(text, cite)


UNREAD = "search summary, not read"


def _fact(value, default_source="") -> Fact | None:
    """Coerce one entry into a `Fact`, or None when there is nothing to print.

    A dict brings its own source and falls back to `default_source`; a bare
    string has only the default. Absence returns None and the caller omits the
    line. Presence without attribution raises, which is the rule the brief asks
    for stated as code.
    """
    if isinstance(value, Fact):
        return value
    if isinstance(value, dict):
        raw = next((value[k] for k in _VALUE_KEYS if _text(value.get(k))), "")
        cite = next((value[k] for k in _SOURCE_KEYS if _text(value.get(k))), default_source)
        # A fact known only from a search engine's summary, because the employer's own
        # page answered 503 every time (09-web-research.md): kept, and said to be unread.
        if value.get("read") is False and _text(raw):
            raw = "%s [%s]" % (_text(raw), UNREAD)
    else:
        raw, cite = value, default_source
    if not _text(raw):
        return None
    return sourced(raw, cite)


def _facts(value, default_source="") -> list:
    """`_fact` over a scalar or a list, dropping the empties."""
    items = value if isinstance(value, (list, tuple)) else [value]
    out = []
    for item in items:
        fact = _fact(item, default_source)
        if fact is not None:
            out.append(fact)
    return out


def _bullet(label, fact) -> str:
    """One fact, one line, source inline.

    The source sits on the same line rather than a continuation line because a
    two-line bullet halves how much of the document fits on a phone screen, and
    an attribution the reader has to scroll to is one they stop checking.
    """
    head = "**%s:** " % label if label else ""
    return "- %s%s (source: %s)" % (head, fact.value, fact.source)


def _first_sentence(value) -> str:
    """The opening sentence, for the fragment that sits inside a question.

    Only `_short` uses this, and only to build an anchor. Cautions and cache
    notes deliberately do not go through it: a caution cut at the first sentence
    boundary reads as a complete instruction while dropping the half that said
    what not to do. A cached caution can keep "Do not round or merge the two
    figures" in its second sentence, which is the whole instruction.
    """
    sentences = tone.sentences(_text(value))
    return sentences[0] if sentences else ""


def clip(text, limit) -> str:
    """`text` whole when it fits, else cut at the last word that fits, with "...": a cut
    at a fixed width left "Connecti" in an interview pack."""
    text = _text(text)
    if len(text) <= limit:
        return text
    head = text[:limit + 1]
    cut = head.rfind(" ")
    return (head[:cut] if cut > limit // 2 else text[:limit]).rstrip(",;:. ") + "..."


def _short(value, limit=ANCHOR_CHARS) -> str:
    """A fragment short enough to sit inside a question, cut at a word."""
    text = _first_sentence(value) or _text(value)
    if len(text) <= limit:
        return text.rstrip(". ")
    head = text[:limit]
    cut = head.rfind(" ")
    return (head[:cut] if cut > limit // 2 else head).rstrip(",;: ") + "..."


# ---------------------------------------------------------------- sources


def _research_source(research) -> str:
    """Attribution for a plain string lifted out of the research cache.

    The cache names itself: a company and a fetch date identify the file the
    claim came from, and the file holds the URLs behind it. A dict carrying
    neither has no provenance at all, so this returns blank and every plain
    string in it raises rather than printing. That is the intended behaviour,
    not an edge case: a research dict assembled from nowhere is exactly the
    input the sourcing rule exists to stop.
    """
    if not research:
        return ""
    explicit = _text(research.get("source"))
    if explicit:
        return explicit
    company = _text(research.get("company"))
    fetched = _text(research.get("fetched_date"))
    if not company and not fetched:
        return ""
    name = "%s/%s.json" % (RESEARCH_DIR, research_cache.file_key(company)) if company else RESEARCH_DIR
    return "%s, fetched %s" % (name, fetched) if fetched else name


def _profile_source(profile_facts) -> str:
    """Where profile facts are attributed to when the caller does not say.

    `01-candidate-profile.md` is the source of truth for everything about the
    candidate and the /prep command loads these facts out of it, so naming the
    file is attribution rather than a default that papers over a missing one.
    """
    return _text((profile_facts or {}).get("source")) or PROFILE_SOURCE


def _contact_source(contact) -> str:
    """The profile the title and location were read off, else the contact book."""
    return _text((contact or {}).get("linkedin_url")) or CONTACTS_SOURCE


def _contact_id(contact) -> str:
    cid = _text((contact or {}).get("contact_id"))
    if cid:
        return cid
    try:
        return state.contact_id((contact or {}).get("name"), (contact or {}).get("company"))
    except ValueError:
        return ""


# ---------------------------------------------------------------- sections


def _section(title, lines, empty_note, extra=()) -> list:
    """A heading and its body, with the empty case saying what to do about it.

    Every section renders even when it is empty. A dropped heading reads as
    "nothing to worry about here", and the sections most likely to be empty are
    compensation and fit, which are the two the user most needs to know were
    never researched.

    `extra` is what the rest of the search holds (a role open there, what the
    letter said), printed after the section's own lines. It never stands in for
    the empty note: a company nobody researched is still not researched because
    a cover letter quoted one fact about it.
    """
    body = (list(lines) if lines else ["- " + empty_note]) + list(extra)
    return ["## " + title, ""] + body + [""]


# `schema.CONTACT_COLUMNS` stores the route as an enum so it can be filtered in a
# spreadsheet. Printed raw it reads as a database field, and this document is
# read under time pressure by someone who wants the sentence, not the key.
ROUTE_WORDS = {
    "cold": "cold",
    "alumni_employer": "shared employer",
    "alumni_school": "shared school",
    "referral": "referred",
    "mutual": "mutual connection",
    "hiring_team": "named on the posting",
}


# A signal in the contact's own voice is a quotation whether or not somebody
# typed the quote marks: "We are seeking 2 Senior Data Scientists in <City>"
# is theirs. "mentioned the team is growing next year" is the system's summary
# of them, and putting quote marks round it invents a sentence
# they never said.
_FIRST_PERSON = re.compile(r"\s*(?:i|i'm|i am|we|we're|we are|my|our|us)\b", re.I)


def _who_lines(contact) -> list:
    contact = contact or {}
    src = _contact_source(contact)
    out = []
    name = state.person_name(contact.get("name")) or _text(contact.get("name"))
    title, company = _text(contact.get("title")), _text(contact.get("company"))
    location = _text(contact.get("location"))
    if name:
        where = ", ".join(p for p in (title, company) if p)
        line = "**%s**" % name + (", " + where if where else "")
        if location:
            line += " (%s)" % location
        out.append("- %s (source: %s)" % (line, src))
    tier, route = _text(contact.get("tier")), _text(contact.get("route"))
    detail = _text(contact.get("route_detail"))
    if tier or route or detail:
        parts = [p for p in ("tier %s" % tier if tier else "",
                             ROUTE_WORDS.get(route, route), detail) if p]
        out.append("- Route in: %s (source: %s)" % (", ".join(parts), CONTACTS_SOURCE))
    signal = _text(contact.get("signal"))
    if signal:
        when = _text(contact.get("signal_date"))
        # Quotation marks only around something that was actually quoted. The
        # brief asks Tier 1 for a verbatim hiring signal, but a signal is often
        # a third-person summary written by the system: "mentioned the team is
        # growing next year" printed as Their words, in
        # quotes, is a sentence the user could read out on the call and be
        # corrected on.
        quoted = ((signal[:1] in "\"\u201c" and signal[-1:] in "\"\u201d")
                  or bool(_FIRST_PERSON.match(signal)))
        if quoted:
            out.append("- Their words%s: \"%s\" (source: %s)"
                       % (", " + when if when else "", signal.strip('"\u201c\u201d'), src))
        else:
            out.append("- Signal%s: %s. Recorded, not quoted. (source: %s)"
                       % (", " + when if when else "", signal.rstrip("."), src))
    referrer = referrer_name(contact)
    if referrer:
        out.append("- Referred by %s. %s (source: %s)"
                   % (referrer, _referrer_advice(contact), CONTACTS_SOURCE))
    return out + _reading_lines(contact)


def referrer_name(contact, contacts=None) -> str:
    """Who referred them, by name. `referred_by` holds the referrer's contact_id, and the
    prep printed the id ("Referred by <employer>_<surname>") where a name belonged."""
    raw = _text((contact or {}).get("referred_by"))
    if not raw or (" " in raw and "_" not in raw):
        return raw                                   # already a name, written by hand
    if contacts is None:
        try:
            book = person.state("network_contacts.csv")
            contacts = state.load_contacts(book) if os.path.exists(book) else []
        except (OSError, ValueError):   # unreadable: the id stands, visibly; a book with
            # merge-conflict markers raises, as it does everywhere else
            contacts = []
    row = state.already_contacted(contacts, contact_id=raw)
    return (state.person_name(row.get("name")) or _text(row.get("name"))) if row else raw


def is_recruiter(contact) -> bool:
    """Is the reader a recruiter or someone in talent acquisition?"""
    return bool(_SCREENER.search(_text((contact or {}).get("title"))))


def _referrer_advice(contact) -> str:
    """Whether to lead with the referrer. To a cold peer the referrer is why they will
    listen, so first. A recruiter who received the referral internally already knows who
    routed it: naming them first is redundant, and one person dropped it from a reply for
    exactly that reason. There it is the answer to "how did you hear about the role"."""
    if is_recruiter(contact):
        return ("They routed it internally, so the recruiter knows: say it when asked how "
                "you heard about the role, not as an opener.")
    return "Name them in the first minute, not the last."


def _reading_lines(contact) -> list:
    """What was read about them before the first note (tools/network/reading.py)."""
    cid = _contact_id(contact)
    try:
        import reading
        found = reading.load(cid) if cid else None
    except (ImportError, ValueError):
        return []
    if not found:
        return []
    src = "documents/network/%s/reading.json, read %s" % (cid, found.get("read_on") or "undated")
    out = []
    for _strength, kind, what, evidence in reading.hooks(found)[:4]:
        if kind == "about":
            continue
        line = "- %s%s" % (what[:1].upper() + what[1:],
                           ': "%s"' % clip(evidence, 160) if evidence else "")
        out.append("%s (source: %s)" % (line, src))
    return out


def _direction_word(row) -> str:
    """"sent" or "they wrote", for one logged message.

    Routed through `state.derive_status` on the single row rather than reading
    the `direction` cell directly. The cell is typed by hand and its synonyms
    ("sent", "them", "me", "o", "i") are resolved in one place in `state`;
    a second copy of that table here is a copy that drifts, and the drift shows
    up as a thread recap that says the wrong person spoke last.
    """
    if state.is_withdrawal(row):
        return "request withdrawn"
    derived = state.derive_status([row])
    if derived == "awaiting_reply":
        return "sent"
    if derived == "replied_needs_response":
        return "they wrote"
    # An accepted request is logged inbound with no message in it. "they wrote"
    # put words in the mouth of somebody who clicked a button, in the document
    # read out on the call.
    if derived == "connected_no_reply":
        return "they accepted"
    return "unlogged direction"


def _thread_lines(contact, threads, today) -> list:
    """The last few exchanges, oldest first, plus what is owed right now.

    Oldest first because the call opens on the most recent message and the user
    reads down to it. What is owed comes from `state.owed` rather than being
    recounted here, so /prep and /threads cannot disagree about the same thread
    on the same morning.
    """
    contact = contact or {}
    cid = _contact_id(contact)
    rows = state.threads_for(threads or (), cid) if cid else []
    out = []
    status = state.effective_status(contact, rows)
    # `effective_status` reads the stored cell and the log together, so citing
    # the contact row alone sent the user to the wrong file to check a value the
    # log had decided. Both are named when both were read.
    out.append("- Status: %s (source: %s)"
               % (status, "%s and %s" % (CONTACTS_SOURCE, THREADS_SOURCE) if rows
                  else CONTACTS_SOURCE))
    if cid:
        # `state.owed` reads `contact_id` off the contact row it is given, and
        # the id here is as often derived from the name as stored in the cell.
        # Handing it the bare row matched nothing, so a thread with an inbound
        # last message printed the messages and silently dropped the line saying
        # a reply was owed on them, which is the line the section exists for.
        for item in state.owed([dict(contact, contact_id=cid)], rows, today):
            if item["kind"] == "reply":
                out.append("- You owe a reply: %d business days since %s."
                           % (item["business_days"], item["since"] or "an undated message"))
            else:
                out.append("- Nudge due %s: %d business days of silence."
                           % (item["due"], item["business_days"]))
    if not rows:
        out.append("- Nothing logged in %s. Whatever booked this call is not written down, "
                   "so read it back off the channel before dialling." % THREADS_SOURCE)
        return out
    for row in rows[-MAX_THREAD_LINES:]:
        said = _text(row.get("summary")) or _short(row.get("full_text"), 120)
        channel = state.channel_of(row)
        out.append("- %s %s%s%s"
                   % (_text(row.get("date")) or "undated",
                      _direction_word(row),
                      " (%s)" % channel if channel else "",
                      ": " + said if said else ""))
    out.append("- Messages above are the log itself (source: %s)." % THREADS_SOURCE)
    return out


# The research cache writes `team_context`; a hand-built dict writes something
# plainer. All of them mean the same field.
_TEAM_KEYS = ("team_context", "team", "what_the_team_does", "team_description")


def _team_lines(research) -> list:
    """What the team does, out of the cache, uncut.

    A long cache note prints whole even though this document is meant to be
    short. Cutting one at a sentence boundary reads as a complete statement
    while dropping whatever followed, and what follows is routinely the caveat:
    a note can end by saying its org mapping is inferred rather than
    confirmed, and a version cut before that sentence turns an inference into a
    fact the user then repeats on the call.
    """
    research = research or {}
    default = _research_source(research)
    out = []
    for keyname in _TEAM_KEYS:
        for fact in _facts(research.get(keyname), default):
            out.append("- %s (source: %s)" % (fact.value, fact.source))
    role_context = _fact(research.get("role_context"), default)
    if role_context is not None:
        out.append(_bullet("The role as posted", role_context))
    return out


_COMPANY_FIELDS = (
    ("What it does", ("what_it_does", "what", "description", "business")),
    ("Size", ("size", "headcount", "employees")),
    ("Funding", ("funding", "funding_stage", "raised", "ownership")),
    ("Recent news", ("recent_news", "news", "recent")),
)


# ------------------------------------------------- the cache's own `sources`

# What `company_research/*.json` is actually shaped like, as opposed to what
# `_COMPANY_FIELDS` was written against. A cached file stores its substance in
# `sources`, a dict of `{name: {url, notes}}`, and many carry nothing else, so
# `/prep` printed an empty company section for those employers even when the
# file held a good deal. None of it reached the page.

# A source with no URL is never a fact. Such a source is an absence note ("Not
# researched this run") or, worse, `posting_facts`, which is lifted from a job
# posting and is untrusted input by definition. `unverified` in the key means
# the drafter wrote down a lead they could not stand behind, sometimes in
# capitals, and this is read out loud on a call.
_SOURCE_SKIP_KEY = re.compile(r"unverif|^posting_facts$|^leads$", re.I)
_SOURCE_SKIP_NOTE = re.compile(
    r"^\s*(?:not\s+(?:researched|checked|independently|verified|yet)"
    r"|leads\s+only|no\s+(?:sources?|notes?)\b)", re.I)

# A URL is not provenance on its own. A source can carry a real link and a note
# saying the link was never opened: a LinkedIn entry that is the posting's own
# companyUrl is untrusted input wearing a URL, and a media entry can say in its
# second sentence to treat the piece as a lead and not cite it.
#
# The discriminator is how the drafter writes: a note that says it *was* fetched
# is verified, and one that says it was *not* is not, wherever in the note that
# sentence sits. So this is deliberately unanchored, unlike `_SOURCE_SKIP_NOTE`.
# It does not fire on a note whose "do not use those" is about stale third-party
# numbers rather than about the page it just fetched at HTTP 200.
_SOURCE_UNVERIFIED = re.compile(
    r"\bnot\s+(?:been\s+)?(?:independently\s+|directly\s+)?"
    r"(?:re-?)?(?:fetch|verif|research|check|read|confirm)\w*"
    r"|\buntrusted\s+origin\b"
    r"|\bunverified\s+lead\b"
    r"|\bposting'?s?\s+(?:own\s+)?company\s*url\b", re.I)

# Provenance, not content. Most notes open with one of these, and it is either
# the file's own date restated or the mechanics of the fetch: "Fetched
# 2030-01-15 via browser-headers curl (HTTP 200; example.com returns 405 to
# WebFetch)." is a line about a tool, in a document somebody reads in the ten
# minutes before a call.
_FETCH_MECHANICS = re.compile(
    r"\b(?:curl|wget|webfetch|robots(?:_check|\.txt)?|user[- ]agent|browser[- ]headers"
    r"|raw html|http\s*\d{3}|\b[2-5]\d\d\s*(?:ok|status)|parsed directly)\b", re.I)
_SOURCE_METADATA = re.compile(
    r"^(?:fetched|re-?fetched|retrieved|accessed|checked|read|verified|confirmed)\b", re.I)


def _is_provenance(sentence) -> bool:
    """A sentence about how the page was got, rather than what it said."""
    if not _SOURCE_METADATA.match(sentence):
        return False
    # "Fetched 2030-01-15." and "Fetched 2030-01-15 via curl (HTTP 200)." both
    # go; "Fetched 2030-01-15, independently re-verifying the drafter's claims"
    # would too, and should, because what it verified follows in its own
    # sentences. Anything longer that is not fetch mechanics is left alone.
    return len(sentence) <= 60 or bool(_FETCH_MECHANICS.search(sentence))

# A sentence that qualifies the one before it. It is carried across the budget
# cut rather than dropped, because the failure this module already knows about
# is a caution that got separated from the figure it cautioned: one note keeps
# "Do not round or merge the two figures" in a second sentence, and another
# calls a headcount "a workforce figure, not a hiring commitment" in a trailing
# parenthetical. Losing either turns a caveat into a claim the user then
# repeats.
_QUALIFIER = re.compile(
    r"^\s*(?:\(|note:|caution|careful|caveat|however|but\b|not\s|no\s|do\s+not"
    r"|the\s+page\s+did\s+not|this\s+is\s+not|only\s+seen)", re.I)

# Sentence boundaries outside brackets. A period inside "12 Main St." or a quoted
# sentence is not a boundary the reader sees, and splitting there is what turns
# one fact into two half-facts.
_ABBREV = re.compile(r"\b(?:[A-Z]|Inc|Ltd|Corp|Co|St|Ave|Dr|Mr|Mrs|Ms|approx|est|no|vs|"
                     r"U\.S|U\.K|e\.g|i\.e|etc)\.$", re.I)

SOURCE_CHARS = 300      # per source, before the qualifier carry-over
MIN_ANCHOR_CHARS = 30   # below this a question anchor says nothing
MAX_SOURCES = 3         # per company, in the order the file lists them


def _sentences(text) -> list:
    """`text` split into whole sentences, never mid-clause.

    Bracket depth is tracked so a period inside a parenthetical or a verbatim
    quote is not read as a boundary, and a fragment that opens lowercase is
    given back to the sentence before it. Both exist for the same reason: the
    notes in the cache put the qualification after the claim, and a cut in the
    wrong place prints the claim without it.
    """
    body = _text(text)
    if not body:
        return []
    out, start, depth, quoted, single = [], 0, 0, False, False
    for i, ch in enumerate(body):
        prev = body[i - 1] if i else ""
        nxt = body[i + 1] if i + 1 < len(body) else ""
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth = max(depth - 1, 0)
        elif ch in '"\u201c\u201d':
            quoted = not quoted
        elif ch in "'\u2018\u2019":
            # An apostrophe has a letter on both sides ("Acme's", "we've"); a
            # quote does not. The cache writes its verbatim material in single
            # quotes and those quotes contain full stops, so reading every
            # apostrophe as a quote and every quote as an apostrophe are both
            # wrong in the same place: "Values copy: 'Fewer meetings. More
            # making.'" came out cut after "Fewer meetings."
            if prev.isalnum() and nxt.isalnum():
                pass
            elif not single and (not prev or prev in " ([{:;,") and (nxt.isalnum() or nxt in '"$'):
                single = True
            elif single and prev and prev != " " and prev not in "sS":
                # A close is only believed when it cannot be a plural
                # possessive. "Growers' Cooperative" and "Readers'
                # Choice Awards" both sit inside a quoted block in the
                # cache, and reading either as the close cut the block in half
                # at the next full stop. Staying inside costs a longer bullet;
                # believing it costs a sentence that ends mid-quotation.
                single = False
        elif ch in ".!?" and depth == 0 and not quoted and not single:
            if nxt and nxt not in " \t":
                continue
            piece = body[start:i + 1]
            if _ABBREV.search(piece):
                continue
            after = body[i + 2:i + 3]
            # A lowercase continuation is the same sentence carrying on.
            if after and after.islower():
                continue
            out.append(piece.strip())
            start = i + 1
    tail = body[start:].strip()
    if tail:
        out.append(tail)
    return [s for s in out if s]


def _source_note(notes) -> str:
    """The usable part of one cached note, whole sentences only.

    Trimmed to `SOURCE_CHARS` so four sources fit a page, except that a
    qualifying sentence is always carried past the cut. Losing the qualifier is
    the one way this can make the document worse than an empty section.
    """
    kept, budget = [], SOURCE_CHARS
    for sentence in _sentences(notes):
        if _is_provenance(sentence):
            continue
        if budget <= 0:
            if kept and _QUALIFIER.match(sentence):
                kept.append(sentence)
            break
        kept.append(sentence)
        budget -= len(sentence) + 1
    return " ".join(kept).strip()


# Acronyms the cache writes in lowercase inside a key. Left as words they read
# as typos on a document somebody is holding during a call.
_SOURCE_ACRONYMS = frozenset({"ai", "ml", "aml", "ceo", "cto", "cio", "cfo", "hr", "q1",
                              "q2", "q3", "q4", "sec", "10k", "us", "uk", "ca", "en",
                              "esg", "kpi", "nlp", "llm", "api", "it"})


def _source_label(name) -> str:
    """A source key as a heading: `northwind_ai_centre` reads as "Northwind AI centre"."""
    words = _text(str(name)).replace("_", " ").replace("-", " ").split()
    if not words:
        return "Source"
    out = [w.upper() if w.lower() in _SOURCE_ACRONYMS else w for w in words]
    head = out[0]
    return " ".join([head if head.isupper() else head.capitalize()] + out[1:])


def _sources_lines(research) -> list:
    """The company section built from `sources`, when nothing structured is there.

    A fallback rather than a merge: where a file carries `facts` or
    `what_it_does`, somebody has already done the selecting and this would
    print the same material twice in a longer form.
    """
    sources = research.get("sources")
    if not isinstance(sources, dict):
        return []
    out = []
    for name, record in sources.items():
        if len(out) >= MAX_SOURCES:
            break
        if _SOURCE_SKIP_KEY.search(str(name)):
            continue
        if not isinstance(record, dict):
            continue
        url = _text(record.get("url"))
        notes = record.get("notes")
        flat = _text(notes)
        if not url or _SOURCE_SKIP_NOTE.match(flat) or _SOURCE_UNVERIFIED.search(flat):
            continue
        body = _source_note(notes)
        if not body:
            continue
        out.append(_bullet(_source_label(name), sourced(body, url)))
    return out


def _stale_line(research, today=None) -> str:
    """A line saying the research is past `RESEARCH_FRESH_DAYS`, or "" when it is not.

    Printed rather than hiding the facts: stale research is still the best lead
    to what to re-check, and the date is what tells the reader to re-check it.
    """
    age = research_cache.age_days(research, today)
    if research_cache.is_fresh(research, today) or age is None:
        return ""
    return ("- Researched %d days ago, past the %d-day mark: check these against the "
            "employer's own pages before the call" % (age, RESEARCH_FRESH_DAYS))


def _company_lines(research, today=None) -> list:
    """The company, entirely out of the research dict. Nothing is inferred here.

    The cautions attached to cached facts are printed with them. They are the
    highest-value lines in the document: each one is a figure somebody already
    got wrong once, and the call is where getting it wrong costs something.
    """
    research = research or {}
    default = _research_source(research)
    out = []
    # `do_not_claim` first, and uncapped. The cache writes it as the list of
    # things somebody already established the user must not say about this
    # employer, and it was being dropped entirely: the document printed three
    # sourced facts and none of the prohibitions attached to them. It leads the
    # section because a long facts list pushes whatever follows off a phone
    # screen, and a prohibition read after the call is not a prohibition.
    for fact in _facts(research.get("do_not_claim"), default):
        out.append(_bullet("Do not say", fact))
    # Older cache files keep the same warnings as a top-level `cautions` list, the
    # draft-applications workflow's own word for them. They were never printed.
    for fact in _facts(research.get("cautions"), default):
        out.append(_bullet("Careful", fact))
    # Everything after this point is substance. The fallback below turns on
    # whether any of it appeared, not on whether `out` is empty: some files
    # carry prohibitions and nothing else, and a company
    # section that prints only what not to say is worse than no section.
    prohibitions = len(out)
    for label, keys in _COMPANY_FIELDS:
        for keyname in keys:
            if keyname not in research:
                continue
            found = _facts(research.get(keyname), default)[:MAX_NEWS]
            out.extend(_bullet(label, fact) for fact in found)
            # Breaking on the key being present rather than on it holding
            # something meant a dict carrying `size: ""` alongside a real
            # `headcount` printed neither.
            if found:
                break
    for raw in list(research.get("facts") or [])[:MAX_FACTS]:
        fact = _fact(raw, default)
        if fact is None:
            continue
        out.append("- %s (source: %s)" % (fact.value, fact.source))
        # Whole, for the reason in `_team_lines`. These cautions put the
        # instruction in the second sentence often enough that a first-sentence
        # cut printed "40 billion is total assets, not AUM" without the
        # sentence saying never to rephrase it as assets under management.
        caution = _text(raw.get("caution")) if isinstance(raw, dict) else ""
        if caution:
            out.append("  - careful: %s" % caution)
    if len(out) == prohibitions:
        out.extend(_sources_lines(research))
    return out


def comp_band(role, location, seniority, sources=None) -> list:
    """Compensation banding for this role and market, from bands passed in.

    `sources` is a parameter and there is no table behind it, for the reason in
    the module docstring: a band with no provenance is a guess wearing a number.
    Accepts a mapping of source name to band, or a list of bands that each name
    their own source. With nothing passed it prints `NOT_RESEARCHED`, which is
    the honest output and is more useful than a figure the user cannot stand
    behind when the recruiter asks where it came from.
    """
    header = ", ".join(p for p in (_text(role), _text(location)) if p)
    if _text(seniority):
        header = "%s (%s)" % (header, _text(seniority)) if header else _text(seniority)
    out = ["- Band for: %s" % header] if header else []

    entries = []
    if isinstance(sources, dict):
        entries = [(name, band) for name, band in sources.items()]
    elif isinstance(sources, (list, tuple)):
        entries = [("", band) for band in sources]
    elif _text(sources):
        # A band handed over as a bare string is a figure with no attribution.
        # Falling through to the empty case printed "No band was passed in"
        # while one had been, so the document was wrong about its own inputs and
        # the number was lost quietly. `sourced` raises on it instead.
        entries = [("", sources)]

    lines = []
    for name, band in entries:
        rendered = _band_text(band)
        if not rendered:
            continue
        lines.append(_bullet("", sourced(rendered, _band_source(band) or name)))
    if not lines:
        out.append("- %s. No band was passed in, so none is printed. Ask their range "
                   "rather than quote a number you cannot source." % NOT_RESEARCHED)
        return out
    out.extend(lines)
    out.append("- These are the sourced numbers and there are no others. Do not round "
               "them up in the moment.")
    return out


def _band_source(band) -> str:
    if isinstance(band, dict):
        return _text(next((band[k] for k in _SOURCE_KEYS if _text(band.get(k))), ""))
    return ""


def _band_text(band) -> str:
    """A band as one readable phrase, whether it arrived as text or as numbers."""
    if not isinstance(band, dict):
        return _text(band)
    stated = next((band[k] for k in _VALUE_KEYS if _text(band.get(k))), "")
    if _text(stated):
        return _text(stated)
    low, high = band.get("low"), band.get("high")
    numbers = [_money(n) for n in (low, high) if n not in (None, "")]
    if not numbers:
        return ""
    currency = _text(band.get("currency")) or _CURRENCY_CODE
    span = " to ".join(numbers)
    basis = _text(band.get("basis"))
    note = _text(band.get("note"))
    return " ".join(p for p in ("%s %s" % (currency, span), basis, note) if p)


def _money(value) -> str:
    """Thousands separators when it is a number, the text as typed when it is not."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return "{:,}".format(int(value))
    return _text(value)


# ---------------------------------------------------------------- questions

# Titles that mean the person screens rather than hires. Spelled out rather than
# stemmed because a bare `recruit` word boundary does not match "Recruiter",
# which is the title that actually appears on these rows.
# The marks on an answer that is profile wording, not something to say aloud.
RAW_MARK = "[raw profile wording: rewrite to spoken first person before use]"
NARRATIVE_POINTER = ("Tell the arc in your own words, not the profile's: see Personal "
                     "Narrative in 01-candidate-profile.md. Never read it out.")

# One definition, read by the interview pack too (tools/interview_pack.py ANGLES).
_SCREENER = re.compile(
    r"\b(?:recruiter|recruiting|recruitment|talent|sourcer|staffing|people ops|people partner|"
    r"hr)\b", re.I)


_SCREEN_FIRST = ("Do you need sponsorship?", "Why are you looking?")


def likely_questions(contact, role, profile_facts) -> list:
    """What they are likely to ask, with an answer drawn from the profile.

    Every answer is profile wording placed against a question, never a generated
    one, and a question with nothing in the profile behind it is not emitted at
    all. That is why an empty profile returns an empty list: a prep doc full of
    questions the user has no prepared answer to is worse than a short one,
    because it reads as preparation without being any.

    Gaps are the exception worth knowing about. A gap with a recorded framing
    becomes a question and an answer; a gap without one is left to
    `fit_assessment`, which says plainly that a framing still has to be written.
    """
    contact, facts = contact or {}, profile_facts or {}
    source = _profile_source(facts)
    out = []

    def add(question, answer, answer_source=source):
        fact = _fact(answer, answer_source)
        if fact is not None:
            out.append({"question": question, "answer": fact.value, "source": fact.source})

    # Profile wording is written, in the third person or close to it: "Data professional
    # with a background in ..." was printed as the answer to say, and nobody can say it.
    # It is marked for rewriting into spoken first person, which /prep does and `prep.py
    # <contact> --check` holds it to.
    if _text(facts.get("summary")):
        add("Tell me about yourself.", "%s %s" % (RAW_MARK, _text(facts.get("summary"))))
    # The narrative is never pasted: the profile says so, and a near-verbatim copy reached
    # a prep as the answer. The arc is the answer; the words are the person's own, on the day.
    if _text(facts.get("narrative")):
        add(_ROUTE_QUESTION, NARRATIVE_POINTER)
    # Who introduced them, by name: `referred_by` holds a contact_id, and the answer once
    # printed the id itself.
    referrer = _text(contact.get("route_detail")) or referrer_name(contact)
    if _text(contact.get("route")).startswith("referral") and referrer:
        # Phrased to work with whatever the column holds. `route_detail` is as
        # often "introduced by Jane Smith" as it is "Jane Smith", and the
        # question that names it directly reads as broken English on the first.
        add("How did the introduction come about?", referrer, CONTACTS_SOURCE)
    closest = _closest_work(facts)
    if closest is not None:
        add("What have you built that is closest to %s?"
            % ("the %s work" % _text(role) if _text(role) else "this team's work"),
            closest.value, closest.source)
    for gap in _gaps(facts)[:MAX_GAPS]:
        if not gap["framing"]:
            continue
        add("How much %s have you done?" % gap["gap"], gap["framing"], gap["source"])
    add("Do you need sponsorship?", facts.get("work_authorization"))
    add("Why are you looking?", facts.get("motivation"))

    if _SCREENER.search(_text(contact.get("title"))):
        # A screening call opens on eligibility and on why the user is moving,
        # and in the default order those are the last two lines on the page. A
        # hiring manager opens on the work, so this reorder is deliberately not
        # applied to everyone.
        front = [q for q in out if q["question"] in _SCREEN_FIRST]
        out = front + [q for q in out if q not in front]
    return out[:MAX_QUESTIONS + 2]


def _closest_work(facts) -> Fact | None:
    """The most recent employer, as one line of evidence.

    Reads the profile's own employer entries rather than composing a claim, so
    the answer the user reads is wording they have already stood behind.
    """
    employers = facts.get("employers") or []
    for entry in employers:
        if isinstance(entry, dict):
            evidence = entry.get("evidence")
            if isinstance(evidence, (list, tuple)):
                evidence = evidence[0] if evidence else ""
            body = _text(evidence) or _text(entry.get("summary"))
            head = ", ".join(p for p in (_text(entry.get("title")),
                                         _text(entry.get("company"))) if p)
            value = ": ".join(p for p in (head, body) if p)
            if value:
                return _fact(value, _text(entry.get("source")) or PROFILE_SOURCE)
        elif _text(entry):
            return _fact(entry, PROFILE_SOURCE)
    return None


def _gaps(facts) -> list:
    """Gaps as {gap, framing, source}, from either dicts or bare strings."""
    out = []
    for entry in facts.get("gaps") or []:
        if isinstance(entry, dict):
            gap = _text(entry.get("gap") or entry.get("value") or entry.get("name"))
            framing = _text(entry.get("framing") or entry.get("answer"))
            src = _text(entry.get("source")) or _profile_source(facts)
        else:
            gap, framing, src = _text(entry), "", _profile_source(facts)
        if gap:
            out.append({"gap": gap, "framing": framing, "source": src})
    return out


# The pages every candidate has already read. A question anchored on a purpose
# statement or a corporate profile is the question they have answered forty
# times, which is the thing `questions_for_them` exists to avoid, so these are
# skipped when the cache has anything else.
_GENERIC_SOURCE = re.compile(
    r"^(?:website|values|corporate|about|homepage|parent|investor_relations|"
    r"about_purpose|website_home|website_about|leadership)", re.I)

# A label the drafter puts in front of the thing they copied. Kept out of the
# anchor so the question reads as a question rather than as a field name.
_ANCHOR_LABEL = re.compile(
    r"^(?:legal entity|exact (?:text|wording[^:]*)|verbatim(?:,? [^:]{0,40})?|purpose"
    r"|mission|brand promise|company history|quote|verbatim opening|stated|also)\s*:\s*",
    re.I)


# A sentence about the research rather than about the company. These are worth
# printing in the company section, where "widely circulated search snippets give
# STALE numbers ... do not use those" is the most useful line in a cached file,
# and useless as the anchor of a question: it made the question "The
# research says 'LIVE FIGURES, confirmed on the page this run'. How much of that
# reaches the work day to day?"
_ABOUT_THE_RESEARCH = re.compile(
    r"\b(?:this (?:run|pass)|the drafter|search snippets?|stale|do not use|do not cite"
    r"|live figures|fetched|re-?verif\w*|corroborat\w*|cross-check\w*|secondhand"
    r"|not (?:stated|found|corroborated) on)\b", re.I)


_QUOTES = "'\u2018\u2019\"\u201c\u201d"


def _is_apostrophe(body, i) -> bool:
    """Is the quote character at `i` part of a word rather than a delimiter?

    The same rule `_sentences` runs on: a letter on both sides is an
    apostrophe, and so is one after a plural possessive. Without it an anchor
    cut at "We're" and the prepared question read: The research says "We".
    """
    prev = body[i - 1] if i else ""
    nxt = body[i + 1] if i + 1 < len(body) else ""
    return (prev.isalnum() and nxt.isalnum()) or (prev in "sS" and not nxt.isalnum())


def _quoted_head(text) -> str:
    """The quoted phrase at the front of `text`, or `text` with its quotes stripped.

    The cache writes `Verbatim: 'Moving goods with less waste, every day.'
    (note: no word 'logistics' in the phrase)`. Stripping
    only the outer quotes leaves the closing one stranded mid-anchor, which is
    how a prepared question ends up reading like a transcription error.
    """
    body = _text(text)
    if body[:1] in _QUOTES:
        closing = next((i for i, c in enumerate(body[1:], 1)
                        if c in _QUOTES and not _is_apostrophe(body, i)), -1)
        if closing > 1:
            return body[1:closing].strip()
    return body.strip(_QUOTES).strip()


def _source_anchors(research) -> list:
    """`(anchor, url)` per source, best sources first, for question-building.

    Ordered so the substantive pages come before the boilerplate ones rather
    than in file order, because the cache writes the corporate profile first
    every time and it is the least useful thing in the file.
    """
    sources = (research or {}).get("sources")
    if not isinstance(sources, dict):
        return []
    picked, generic = [], []
    for name, record in sources.items():
        if _SOURCE_SKIP_KEY.search(str(name)) or not isinstance(record, dict):
            continue
        url, flat = _text(record.get("url")), _text(record.get("notes"))
        if not url or _SOURCE_SKIP_NOTE.match(flat) or _SOURCE_UNVERIFIED.search(flat):
            continue
        # First usable sentence with something in it. "Who we are" and "PRIMARY
        # FACT SOURCE." are headings the drafter typed before pasting, and a
        # question anchored on either says nothing at all.
        body = ""
        for candidate in _sentences(flat):
            if _is_provenance(candidate) or _ABOUT_THE_RESEARCH.search(candidate):
                continue
            head = _quoted_head(_ANCHOR_LABEL.sub("", candidate).strip())
            if len(head) >= MIN_ANCHOR_CHARS:
                body = head
                break
        body = _quoted_head(_ANCHOR_LABEL.sub("", body).strip())
        if not body:
            continue
        (generic if _GENERIC_SOURCE.match(str(name)) else picked).append((body, url))
    return picked + generic


def _ask(lead, anchor, question) -> str:
    """One question, with the researched fragment it came from quoted inside it.

    The fragment is quoted rather than dropped into the sentence bare. A cached
    note starts with a capital letter and often arrives already shortened, so
    unquoted it reads as a typo in the middle of a question and its trailing
    ellipsis collides with the full stop after it.
    """
    return '%s "%s". %s' % (lead, _short(anchor), question)


# Question shapes, each anchored to a field that has to be present for the
# question to exist. Generic questions are deliberately absent: "what does the
# first six months look like" can be asked without reading anything, and a prep
# doc that supplies it is padding its own page count.
def questions_for_them(company_research, role) -> list:
    """Questions worth asking, each anchored to something actually researched.

    Returns an empty list when the research dict holds nothing to anchor on.
    Company name and fetch date are provenance, not content, so a dict holding
    only those yields nothing: the point of this section is questions the other
    person can tell were prepared, and a question derived from no information is
    one they have answered forty times.
    """
    research = company_research or {}
    default = _research_source(research)
    out = []

    def add(question, anchor, source):
        if _text(anchor) and _text(source):
            out.append({"question": question, "anchor": _text(anchor), "source": _text(source)})

    for keyname in _TEAM_KEYS:
        fact = _fact(research.get(keyname), default)
        if fact is not None:
            add(_ask("The research says", fact.value,
                     "Is that still how the team is set up?"), fact.value, fact.source)
            break
    for keyname in ("funding", "funding_stage", "raised"):
        fact = _fact(research.get(keyname), default)
        if fact is not None:
            add(_ask("The research says", fact.value,
                     "What does that mean for headcount on this team?"),
                fact.value, fact.source)
            break
    for fact in _facts(research.get("recent_news") or research.get("news"), default)[:MAX_NEWS]:
        add(_ask("The research says", fact.value, "What has that changed for your team?"),
            fact.value, fact.source)
    # Two cached facts, not four. The template is the same each time, so a third
    # and fourth read as one question asked four ways rather than four questions.
    for i, raw in enumerate(list(research.get("facts") or [])[:MAX_FACT_QUESTIONS]):
        fact = _fact(raw, default)
        if fact is None:
            continue
        add(_ask("The research says", fact.value, FACT_QUESTION_TAILS[i]),
            fact.value, fact.source)
    role_context = _fact(research.get("role_context"), default)
    if role_context is not None:
        add(_ask("The posting describes", role_context.value,
                 "What is the first thing it needs someone to fix?"),
            role_context.value, role_context.source)
    elif _text(role) and out:
        # Anchored on the researched company rather than on the role name alone,
        # which is why this only fires when something else already did.
        add("Where does the %s sit against what you have just described?" % _text(role),
            _text(role), CONTACTS_SOURCE)
    if not out:
        # Same fallback as `_company_lines`, for the same reason: a cached file
        # can put everything in `sources`, and this section printed "nothing
        # researched to anchor a question on" while the file held several
        # sourced facts.
        for i, (anchor, url) in enumerate(_source_anchors(research)[:MAX_FACT_QUESTIONS]):
            add(_ask("The research says", anchor, FACT_QUESTION_TAILS[i]), anchor, url)
        if _text(role) and out:
            add("Where does the %s sit against what you have just described?" % _text(role),
                _text(role), CONTACTS_SOURCE)
    return out[:MAX_QUESTIONS]


# ---------------------------------------------------------------- judgment


def fit_assessment(application, profile_facts) -> list:
    """The honest read: what to lead with, what to be ready for, what is a hard no.

    The brief's distinction is the load-bearing part. A skills gap is bridgeable
    and is worth naming with the strongest honest framing available; a
    categorical blocker (citizenship, clearance, a required domain) is a hard no
    that no framing fixes, and pretending otherwise burns the call and the
    relationship behind it. So blockers print first, in their own voice, and are
    never softened into gaps.
    """
    facts = profile_facts or {}
    app = application or {}
    source = _profile_source(facts)
    out = []

    for entry in facts.get("blockers") or []:
        fact = _fact(entry, source)
        if fact is not None:
            out.append("- BLOCKER: %s. No framing fixes this; do not let the call "
                       "pretend otherwise. (source: %s)" % (fact.value, fact.source))
    rating = _text(app.get("fit_rating"))
    if rating:
        role = _text(app.get("role"))
        out.append("- Scored %s%s (source: %s)"
                   % (rating, " for " + role if role else "", TRACKER_SOURCE))
    for entry in list(facts.get("strengths") or [])[:MAX_STRENGTHS]:
        fact = _fact(entry, source)
        if fact is not None:
            out.append("- Lead with: %s (source: %s)" % (fact.value, fact.source))
    for gap in _gaps(facts)[:MAX_GAPS]:
        if gap["framing"]:
            out.append("- Gap: %s. Say: %s (source: %s)"
                       % (gap["gap"], gap["framing"], gap["source"]))
        else:
            out.append("- Gap: %s. No framing recorded. Write one before the call rather "
                       "than improvising it on the call. (source: %s)"
                       % (gap["gap"], gap["source"]))
    return out


# A role open at their employer that the search scored this well is the one thing
# a call there should not end without mentioning, and the prep said nothing of it.
OPEN_ROLE_FIT = 70
MAX_OPEN_ROLES = 3

# A `concession` that records there is none. The workflow's default is none, and
# printing "Conceded in the letter: none" would read as a concession.
_NO_CONCESSION = re.compile(r"^\W*(?:none|nil|n/?a|nothing|no\s+(?:concessions?|gaps?))\b", re.I)


def _fit_number(value):
    try:
        return float(str(value).strip())
    except ValueError:
        return None


def _open_roles_lines(roles) -> list:
    """The roles open at their employer that scored `OPEN_ROLE_FIT` or more, as one line.

    Only asked for when nothing has been applied for there (`prep_markdown`
    decides), because with an application in, that application is what the call
    is about. Each role keeps its fit score, and the line is sourced to the round
    file the scores came from.
    """
    good, seen = [], set()
    for role in roles or ():
        fit = _fit_number((role or {}).get("fit"))
        title = _text((role or {}).get("title"))
        if fit is None or fit < OPEN_ROLE_FIT or not title or title.lower() in seen:
            continue
        seen.add(title.lower())
        good.append((title, fit, role))
    if not good:
        return []
    good.sort(key=lambda t: -t[1])
    shown = ", ".join("%s (%d)" % (title, fit) for title, fit, _ in good[:MAX_OPEN_ROLES])
    more = len(good) - MAX_OPEN_ROLES
    if more > 0:
        shown += ", and %d more" % more
    source = next((_text(r.get(k)) for _, _, r in good for k in _SOURCE_KEYS if _text(r.get(k))), "")
    fact = sourced("Open there, scored %d or more, nothing applied for: %s"
                   % (OPEN_ROLE_FIT, shown), source)
    return ["- %s (source: %s)" % (fact.value, fact.source)]


def _letter_lines(draft) -> tuple:
    """(company lines, fit lines) from the draft the application's letter was rendered from.

    The company fact the letter used goes beside the research, and any gap the
    letter conceded goes under fit, so what is said on the call matches what the
    employer was already told. Sourced to the draft file itself, which is the
    record of what went out.
    """
    draft = draft or {}
    source = _text(draft.get("_path") or draft.get("source"))
    company, fit = [], []
    told = _text(draft.get("p2"))
    if told:
        company.append(_bullet("The letter told them", sourced(told, source)))
    conceded = _text(draft.get("concession"))
    if conceded and not _NO_CONCESSION.match(conceded):
        fit.append(_bullet("Conceded in the letter", sourced(conceded, source)))
    return company, fit


def _flag_banned(lines, dislikes) -> list:
    """`lines`, each followed by a flag where it uses a phrase the person has banned.

    Flagged, never dropped: the line still says what to do, and a prep document
    only gains lines. Run over the sections whose wording this file supplies or
    the user says out loud (the answers, the questions to ask, fit and tone),
    because those are where a phrase they have said never to use would reach
    the call.
    """
    out = []
    for line in lines:
        out.append(line)
        hits = list(dict.fromkeys(h.strip() for h in (dislikes(line) or ()) if h.strip()))
        if hits:
            out.append("  - careful: %s is wording you have said never to use; say it your "
                       "way (source: %s)" % (", ".join('"%s"' % h for h in hits), LEARNED_SOURCE))
    return out


def work_auth_for(contact) -> str:
    """The work-authorization line in the register this reader gets. A recruiter or
    anyone on the hiring side gets the employer-facing wording (WORK_AUTH["employer"] in
    networking.py, or the senior register where the profile names none): the peer line
    ("I can already work here") reached a recruiter on a screen."""
    contact = contact or {}
    # A booked call is not a hiring process by itself: most are a peer's coffee chat.
    if is_recruiter(contact) or _text(contact.get("route")) == "hiring_team" or \
            _text(contact.get("status")) == "referral_in_progress":
        return compose.WORK_AUTH.get("employer") or compose.WORK_AUTH["senior"]
    senior = tone.is_senior(_text(contact.get("title"))) or tone.is_senior(contact.get("seniority"))
    return compose.WORK_AUTH["senior" if senior else "peer"]


def _tone_lines(contact) -> list:
    """How to talk to this person, and how to write the note afterwards."""
    contact = contact or {}
    title = _text(contact.get("title"))
    senior = tone.is_senior(title) or tone.is_senior(contact.get("seniority"))
    out = []
    if senior:
        out.append("- Register: senior. Full sentences, no exclamation marks, one thank you "
                   "and not three.")
    else:
        out.append("- Register: peer. Plain and short, the way you would say it out loud.")
    if _text(contact.get("referred_by")) or _text(contact.get("route")).startswith("referral"):
        if is_recruiter(contact):
            out.append("- The referral is why this call exists, and the recruiter already "
                       "knows who made it: the answer to \"how did you hear about us\", "
                       "never the opener.")
        else:
            out.append("- The referral is why this call exists. Name them early, not as a "
                       "footnote at the end.")
    signal = _text(contact.get("signal"))
    if signal:
        # The recorded signal, not a claim about it. This asserted "They said
        # publicly they are hiring" for every non-empty signal, including one
        # that recorded only a quick reply, which is neither public nor about
        # hiring.
        out.append("- There is a recorded hiring signal, under Who they are. Treat the call "
                   "as being about the role, not about whether there is one.")
    out.append("- If work authorization comes up: \"%s.\"" % work_auth_for(contact))
    out.append("- Match their length afterwards. Two lines back to two lines; a paragraph "
               "in reply to one word reads as trying too hard.")
    out.append("- Do not repeat their own points back at them. Answer the shape of what "
               "they said instead.")
    return out


# ---------------------------------------------------------------- document


def _comp_sources(research, application):
    """Where a researched band arrives from.

    The research dict, because a band belongs with the rest of what somebody
    looked up for this company. The tracker row is checked too, since a posting
    that stated a range is itself a source and a stated range beats any estimate.
    """
    for holder, holder_source in ((research or {}, _research_source(research)),
                                  (application or {}, TRACKER_SOURCE)):
        for keyname in ("compensation", "comp_sources", "comp", "salary", "salary_sources"):
            value = holder.get(keyname)
            if not value:
                continue
            if isinstance(value, (dict, list, tuple)):
                return value
            # A band typed into the cache as one line of text is sourced by the
            # file holding it, the same as every other plain string in that
            # file. Without this it reached `comp_band` bare and the document
            # refused to render over a band somebody had actually looked up.
            return {holder_source: value} if holder_source else value
    return None


def _same_employer(contact, other, what) -> None:
    """Refuse research or a tracker row that belongs to a different employer.

    `company_key` is the join the rest of the system uses and it is the only
    thing between a prep doc for one company and the facts of another company
    with the same name, which is the collision the brief names. Nothing downstream would notice the swap: the
    wrong company's facts print with real sources attached, so the document
    reads as better researched the more wrong it is. Silent on either name
    being blank, because a hand-built dict that names no company is a fragment
    the caller assembled, not a mismatch.
    """
    mine = _text((contact or {}).get("company"))
    theirs = _text((other or {}).get("company"))
    if not mine or not theirs or company_key(mine) == company_key(theirs):
        return
    raise ValueError(
        "%s names %r but the contact works at %r, and those key differently (%s vs %s). "
        "The lookup that found it is wrong; a prep doc carrying another employer's "
        "facts is read out loud as if it were this one's."
        % (what, theirs, mine, company_key(theirs), company_key(mine)))


# A call this close with nothing researched about the employer goes in front of the
# person only after the research: "Their team" and "The company" both printed "not
# researched" on a booked call with a priority employer, and nothing asked for more.
RESEARCH_BEFORE_DAYS = 2


LIVING = "interview_prep.md"         # tools/interview_pack.py LIVING


def _process_lines(contact, application) -> list:
    """Where a live hiring process at this employer keeps its prep, and when this call is
    really one of its stages. A recruiter screen on a live process got a networking prep
    because /interview refused a process with no application; the answers then lived in
    four places. The process's own document holds them, and this file points there."""
    if not application:
        return []
    import outreach
    status = _text(application.get("status")).lower()
    if status not in ("interview", "offer"):
        return []
    folder = outreach.app_folder(_text(application.get("company")), _text(application.get("role")))
    path = os.path.relpath(os.path.join(folder, LIVING), STATE_ROOT).replace(os.sep, "/")
    out = []
    # A recruiter or the hiring team only: a peer's coffee chat at the same employer, or the
    # referrer who started the process, is still a networking call.
    if is_recruiter(contact) or _text(contact.get("route")) == "hiring_team":
        out.append("**This call is a stage of a live hiring process at %s (%s): prepare it with "
                   "/interview %s, whose document holds the answers. This file is the briefing "
                   "on the person.**" % (_text(application.get("company")),
                                          _text(application.get("role")),
                                          _text(application.get("company"))))
    if os.path.exists(os.path.join(folder, LIVING)):
        out.append("The process's own prep document, one for the whole process: %s" % path)
    return out + ([""] if out else [])


_A_CALL = re.compile(r"\b(?:call|meeting|meet|chat|coffee|interview|screen|zoom|teams)\b", re.I)


def research_needed(contact, company_research, today=None) -> str:
    """The line /prep must act on before presenting, or "" when there is nothing to do. A
    call is a booked call, or a next step that names one: "send the CV" due tomorrow is not
    a call and needs no research first."""
    if company_research:
        return ""
    contact = contact or {}
    today_d = state.as_date(_text(today)) or datetime.date.today()
    due = state.as_date(_text(contact.get("next_action_due")))
    soon = (_text(contact.get("status")) == "call_booked"
            or (due is not None and 0 <= (due - today_d).days <= RESEARCH_BEFORE_DAYS
                and _A_CALL.search(_text(contact.get("next_action")))))
    if not soon or not _text(contact.get("company")):
        return ""
    return ("RESEARCH FIRST: the call is %s and nothing is researched about %s. Claude: run the "
            "employer-researcher subagent (company_research/), then this prep again, before "
            "this goes to the person." % ("on " + due.isoformat() if due else "booked",
                                          _text(contact.get("company"))))


def prep_markdown(contact, company_research=None, application=None, profile_facts=None,
                  threads=(), today=None, open_roles=(), draft=None, never_say=None,
                  kept=None) -> str:
    """The whole prep document, as markdown.

    Assembled from what was passed in and nothing else. Sections with no input
    say so rather than disappearing, because a missing heading reads as an
    absence of risk and the empty sections are usually compensation and fit.

    `open_roles` (round rows, each naming its `source`) and `draft` (the draft
    object the application's documents were rendered from) are what the rest of
    the search already holds about this employer; `search_context` loads both.
    `never_say` finds the phrases the person has banned in a line, and defaults
    to theirs (`learned.dislikes`).
    """
    contact = contact or {}
    today = _text(today) or datetime.date.today().isoformat()
    name = state.person_name(contact.get("name")) or _text(contact.get("name"))
    if not name:
        raise ValueError("prep_markdown needs a contact with a name: the document is a "
                         "briefing about one person and there is nobody to brief on.")
    company = _text(contact.get("company"))
    _same_employer(contact, company_research, "the research")
    _same_employer(contact, application, "the application row")
    _same_employer(contact, draft, "the letter's draft")
    banned = never_say or learned.dislikes
    # Roles open there only when nothing has been applied for: with an
    # application in, that is what the call is about. The letter only with one.
    roles = _open_roles_lines(open_roles) if not application else []
    letter_company, letter_fit = _letter_lines(draft) if application else ([], [])
    role = _text((application or {}).get("role")) or _text(contact.get("role"))

    lines = ["# Prep - %s" % ", ".join(p for p in (name, company) if p), ""]
    when = _text(contact.get("next_action_due"))
    booked = _text(contact.get("next_action"))
    head = "Written %s." % today
    if booked or when:
        # The action is written by hand and often arrives as two sentences, so
        # a blind trailing stop produced "…including the panel stage. on
        # 2030-01-18." The date is attached before the stop, and a stop is only
        # added when the text does not already end in one.
        action = (booked or "call").strip()
        # The date leads. The action is written by hand and is routinely two or
        # three sentences, so appending "on <date>" to the end attached the date
        # to whichever clause happened to be last: "…is currently 'this week'
        # with no date, on 2030-01-16."
        head += " Next%s: %s%s" % (" (by %s)" % when if when else "", action,
                                   "" if action.endswith((".", "?", "!")) else ".")
    lines += [head,
              "Read it in the five minutes before. Every fact carries its source; anything "
              "unsourced was left out rather than guessed at.", ""]
    need = research_needed(contact, company_research, today)
    if need:
        lines += ["**%s**" % need, ""]
    lines += _process_lines(contact, application)

    lines += _section(SECTIONS[0], _who_lines(contact),
                      "Only a name is recorded. Read the profile before dialling.")
    lines += _section(SECTIONS[1], _thread_lines(contact, threads, today),
                      "Nothing logged in %s." % THREADS_SOURCE)
    lines += _section(SECTIONS[2], _team_lines(company_research),
                      "%s. Ask them what the team owns; first-hand beats researched anyway."
                      % NOT_RESEARCHED)
    company = _company_lines(company_research, today)
    # Every line in the section is a sourced fact; how old the research is, is not
    # one, so the warning stands after them with the other context.
    stale = _stale_line(company_research, today) if company else ""
    lines += _section(SECTIONS[3], company,
                      "%s. Nothing is printed here that nobody looked up." % NOT_RESEARCHED,
                      extra=([stale] if stale else []) + list(letter_company))
    lines += _section(SECTIONS[4],
                      comp_band(role, _text(contact.get("location")),
                                "senior" if tone.is_senior(contact.get("title")) else "",
                                _comp_sources(company_research, application)),
                      "%s." % NOT_RESEARCHED)

    asked = []
    for item in likely_questions(contact, role, profile_facts):
        said = (kept or {}).get(_qkey(item["question"]))
        if said:
            item = dict(item, answer=said[0], source=said[1])
        asked.append("- **Q.** %s" % item["question"])
        answer = "\n".join("    " + ln if ln else "" for ln in
                           _text(item["answer"]).split("\n")).strip()
        asked.append("  **A.** %s%s" % (answer, " (source: %s)" % item["source"]
                                         if _text(item["source"]) else ""))
    lines += _section(SECTIONS[5], _flag_banned(asked, banned),
                      "No profile facts were passed in, so no answers are drafted. Prepare "
                      "them before the call rather than in it.")

    ask = ["- %s (source: %s)" % (q["question"], q["source"])
           for q in questions_for_them(company_research, role)]
    lines += _section(SECTIONS[6], _flag_banned(ask, banned),
                      "Nothing researched to anchor a question on. Ask what the team owns "
                      "and what the first six months need.")
    lines += _section(SECTIONS[7], _flag_banned(fit_assessment(application, profile_facts), banned),
                      "Nothing recorded. Do not improvise a fit story on the call.",
                      extra=roles + letter_fit)
    lines += _section(SECTIONS[8], _flag_banned(_tone_lines(contact), banned),
                      "Nothing recorded about this person. Default to plain and short.")
    return "\n".join(lines).rstrip() + "\n"


# Which prep wrote a document, as its last line: the prep-docs method's version in
# tools/build_versions.py, which a change to this file cannot skip. `--all` rewrote
# every document whenever the generator changed (hundreds in one contact book, one
# per contact, called or not) and left a file for every contact that never had one;
# `--stale-only` rewrites only a document older than the last version that asked for
# documents to be made again, or with no stamp, and `--dry-run` lists what would be
# written and writes nothing.
_STAMP = re.compile(r"^<!-- prep v(\d+)\b[^\n]*-->[ \t]*$", re.M)


def _versions() -> tuple:
    import build_versions
    return build_versions.METHODS["prep-docs"]["versions"]


def generator_version() -> int:
    """The version of prep writing documents now."""
    return _versions()[-1][0]


def redo_from() -> int:
    """The oldest version whose documents are still current: the last that asked for
    documents to be made again. A wording-only version leaves documents alone."""
    return max((v[0] for v in _versions() if v[2]), default=1)


def stamp_line(as_of_digest: str = "") -> str:
    return "<!-- prep v%d: tools/network/prep.py%s -->" % (
        generator_version(), "; as of %s" % as_of_digest if as_of_digest else "")


_AS_OF = re.compile(r"^<!-- prep v\d+\b[^\n]*?; as of ([0-9a-f]{12})", re.M)
_WRITTEN = re.compile(r"^Written (\d{4}-\d{2}-\d{2})\.", re.M)


def as_of(contact, threads=(), research=None, application=None, today=None) -> str:
    """What a prep was written from, as a short digest: the contact row's status, next
    action and its date, every message logged with them, when the employer was last
    researched, the application or process there, and whether the call is now close enough
    to need research first. A prep dated the 17th said "awaiting reply" and "wait until
    Monday" after the row moved to a booked call on the 19th; one said "not researched"
    after the research was saved; and nothing regenerated either."""
    import hashlib
    contact, research, application = contact or {}, research or {}, application or {}
    cid = _contact_id(contact)
    rows = sorted((_text(r.get("date")), _text(r.get("direction")), _text(r.get("scenario")),
                   _text(r.get("summary"))) for r in state.threads_for(list(threads or ()), cid))
    blob = json.dumps([_text(contact.get(k)) for k in ("status", "next_action", "next_action_due")]
                      + [list(r) for r in rows]
                      + [_text(research.get("fetched_date")) or ("cached" if research else ""),
                         _text(application.get("status")), _text(application.get("role")),
                         bool(research_needed(contact, research, today))])
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:12]


_Q_LINE = re.compile(r"^- \*\*Q\.\*\* (.+?)\s*$")
_A_LINE = re.compile(r"^  \*\*A\.\*\* (.*?)\s*$")
_SOURCE_TAIL = re.compile(r"\s*\(source: ([^)]*)\)\s*$")


def answers_in(text) -> list:
    """[(question, answer, source)] from a prep document's likely questions. An answer the
    person wrote over several lines (each indented under the first) is read whole; the
    "careful" flag lines this file adds are not part of it."""
    out, lines = [], str(text or "").splitlines()
    for i, line in enumerate(lines[:-1]):
        mq, ma = _Q_LINE.match(line), _A_LINE.match(lines[i + 1])
        if not (mq and ma):
            continue
        body = [ma.group(1)]
        for j, more in enumerate(lines[i + 2:], i + 2):
            bare = more.strip()
            if bare.startswith(("- careful:", "**A.**", "- **Q.**", "#", "<!--")) or \
                    re.match(r"^- ", more):
                break
            if not bare:
                # A blank line ends the answer unless the person's next paragraph follows.
                after = next((x for x in lines[j + 1:] if x.strip()), "")
                if not after or after.lstrip().startswith(("- ", "#", "<!--", "**")):
                    break
            body.append(bare)
        while body and not body[-1]:
            body.pop()
        a = "\n".join(body)
        m = _SOURCE_TAIL.search(a)
        out.append((mq.group(1), a[:m.start()] if m else a, m.group(1) if m else ""))
    return out


def _qkey(question) -> str:
    """A question's identity across rebuilds: the "closest to" question names the role, which
    changes when a process is registered, and an answer written for it is still the answer."""
    q = _text(question)
    if q.lower().startswith("what have you built that is closest to"):
        return "closest"
    return what_works._norm(q)


def fit_to_say(answer) -> bool:
    """Can this answer be said as it stands: no raw profile wording, and read as said
    (voice_check.spoken_findings)? The pointer to the narrative is an instruction, not an
    answer, and is never held to it."""
    answer = _text(answer)
    if answer == NARRATIVE_POINTER:
        return True
    return bool(answer) and RAW_MARK not in answer and not voice_check.spoken_findings(answer)


def unsayable(lines) -> list:
    """Why an answer, as the lines it was written in, is not yet fit to say aloud, or []:
    raw profile wording, a paste with its source still on it, bullet points, or written
    rather than spoken register (voice_check.spoken_findings). The one rule both the call
    prep and the interview pack hold answers to."""
    lines = [ln for ln in (lines or ()) if _text(ln)]
    text = " ".join(_text(ln) for ln in lines)
    if RAW_MARK in text:
        return ["raw profile wording: rewrite it as you would say it"]
    if "(source:" in text or re.match(r"\s*(?:Prepared|Story|Say):", text):
        return ["pasted from the profile: say it in your own words"]
    if any(re.match(r"\s*(?:[-*+]|\d+[.)])\s", ln) for ln in lines):
        return ["written as bullet points: say it as sentences"]
    return voice_check.spoken_findings(text)


def check_answers(text) -> list:
    """[(question, why)] for every answer in a prep document not yet fit to say."""
    out = []
    for q, a, _src in answers_in(text):
        if a == NARRATIVE_POINTER:
            continue
        out += [(q, why) for why in unsayable(a.split("\n"))]
    return out


_GENERATED = re.compile(r"^<!-- generated answers: (\{.*\}) -->$", re.M)


def _digest(answer) -> str:
    import hashlib
    return hashlib.sha1(" ".join(_text(answer).split()).encode("utf-8")).hexdigest()[:10]


def generated(contact, application=None, profile_facts=None) -> dict:
    """{question key: digest} of the answers this file writes for them now: kept beside the
    version stamp, out of the document's body, so a rebuild can tell the person's rewrites
    from its own words."""
    contact = contact or {}
    role = _text((application or {}).get("role")) or _text(contact.get("role"))
    return {_qkey(i["question"]): _digest(i["answer"])
            for i in likely_questions(contact, role, profile_facts)}


def said_answers(text) -> dict:
    """{question key: (answer, source)} for the answers someone rewrote in an earlier version.
    A rebuild keeps them, over profile wording and the pointer to the narrative alike: they
    are the person's words. What this file wrote and nobody touched is never kept, so a
    corrected profile always reaches the next version: the document records what it wrote
    (`generated answers`), and only an answer that differs from that is the person's. A
    document from before that record keeps only answers said in the first person."""
    m = _GENERATED.search(str(text or ""))
    try:
        wrote = json.loads(m.group(1)) if m else None
    except ValueError:
        wrote = None
    out = {}
    for q, a, src in answers_in(text):
        key = _qkey(q)
        if not _text(a) or a == NARRATIVE_POINTER:
            continue
        if wrote is not None:
            if wrote.get(key) != _digest(a):
                out[key] = (a, src)
        elif fit_to_say(a) and len(a.split()) >= 6 and \
                re.search(r"\b(?:I|I'm|I've|I'd|my|me)\b", a):
            out[key] = (a, src)
    return out


def stamp_of(text) -> int | None:
    """The version a document says wrote it, or None."""
    found = _STAMP.findall(str(text or ""))
    return int(found[-1]) if found else None


def stale(path, contact=None, threads=(), research=None, application=None, today=None) -> bool:
    """Is the document at `path` older than the current prep, unstamped, or (given the
    contact) written before their row or their thread changed? A missing document is not
    stale: `--stale-only` never writes one nobody asked for."""
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return False
    version = stamp_of(text)
    if version is None or version < redo_from():
        return True
    if contact is None:
        return False
    m = _AS_OF.search(text)
    if m:
        return m.group(1) != as_of(contact, threads, research, application, today)
    # Stamped before the digest existed: a message logged after the day it was written.
    w = _WRITTEN.search(text)
    cid = _contact_id(contact)
    latest = max((_text(r.get("date"))[:10] for r in state.threads_for(list(threads or ()), cid)),
                 default="")
    return bool(w and latest and latest > w.group(1))


def prep_path(contact, root=STATE_ROOT) -> str:
    cid = _contact_id(contact)
    if not cid:
        raise ValueError("write_prep needs a contact_id, or a name with a surname to build "
                         "one from: the document is filed under the person.")
    return os.path.join(root, *PREP_DIR, cid, "prep.md")


def _read(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return None


def write_prep(contact, company_research=None, application=None, profile_facts=None,
               threads=(), today=None, root=STATE_ROOT, open_roles=(), draft=None,
               never_say=None, keep_if_same=False) -> str:
    """Write the prep document and return its path.

    Filed under the contact id rather than a company or a date, because the next
    call with the same person overwrites the same file: a folder of six dated
    prep docs for one contact is six documents nobody reads.
    """
    path = prep_path(contact, root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, encoding="utf-8") as fh:
            kept = said_answers(fh.read())
    except OSError:
        kept = {}
    text = prep_markdown(contact, company_research, application, profile_facts, threads, today,
                         open_roles=open_roles, draft=draft, never_say=never_say, kept=kept)
    wrote = generated(contact, application, profile_facts)
    new = (text + "\n" + stamp_line(as_of(contact, threads, company_research, application, today))
           + "\n" + ("<!-- generated answers: %s -->\n" % json.dumps(wrote, sort_keys=True)
                     if wrote else ""))
    old = _read(path)
    # In a rewrite of them all, a document that would change only its date is left as it
    # is: two chats that each regenerated every prep wrote the same documents a day apart,
    # and all 217 conflicted. Asked for one contact, it is written, date and all.
    if keep_if_same and old is not None and _WRITTEN.sub("", old) == _WRITTEN.sub("", new):
        return path
    with open(path, "w", encoding="utf-8") as f:
        f.write(new)
    return path


# ---------------------------------------------------------------- loading


def load_research(company, root=STATE_ROOT) -> dict:
    """The cached research for an employer, or {} when nothing is cached.

    The lookup is tools/company_research.py's, through `company_key`, so this
    reads the file every other reader and writer of the cache finds. How old it
    is reaches the document through `_stale_line`, from the file's own date.
    """
    data, _age, _fresh = research_cache.load(company, root=root)
    return data


def search_context(contact, application, root=STATE_ROOT) -> tuple:
    """(open roles, draft): what the rest of the search holds about their employer.

    With no application there, the roles open at the employer in the newest kept
    round (`why.open_roles`), each sourced to its round file. With one, the
    draft its letter was rendered from (`what_works.draft_for`, which never takes
    another role's draft), or None when none was kept.
    """
    if application:
        return (), what_works.draft_for(application, what_works.drafts(root))
    company = _text((contact or {}).get("company"))
    if not company:
        return (), None
    roles = why.open_roles(company, os.path.join(root, "documents", "rounds"))
    return [dict(r, source=os.path.relpath(r["_path"], root).replace(os.sep, "/"))
            for r in roles if r.get("_path")], None


def find_application(contact, tracker_rows) -> dict:
    """The tracker row for the same employer, most recent first, or {}.

    The join the brief asks for, and it is `company_key` again: a contact filed
    under an employer's legal name has to find the application filed under its
    initials.
    """
    for link in state.link_to_applications([contact], tracker_rows or []):
        apps = link["open_applications"] or link["applications"]
        if apps:
            return apps[0]
    return {}


# ---------------------------------------------------------------- CLI


def _write_one(row, tracker, a, keep_if_same=False) -> str:
    """One prep document, with the profile facts built when none were passed.

    Nothing ever passed a `--profile-facts` file, so every document on disk had
    two of its nine sections empty: "They will likely ask" and "Fit, honestly",
    which are the two a call actually turns on. `profile_facts.build` reads
    `01-candidate-profile.md`, which is where `PROFILE_SOURCE` already says
    these facts come from, so the attribution was true before the facts were.
    """
    application = find_application(row, tracker)
    if a.profile_facts:
        facts = json.load(open(a.profile_facts, encoding="utf-8"))
    else:
        facts = profile_facts.build(
            role=_text(application.get("role")) or _text(row.get("role")),
            posting=_text(application.get("notes")))
    roles, draft = search_context(row, application, a.root)
    return write_prep(row,
                      company_research=load_research(row.get("company"), a.root),
                      application=application,
                      profile_facts=facts,
                      threads=state.load_threads(a.threads),
                      today=a.today,
                      root=a.root,
                      open_roles=roles,
                      draft=draft,
                      keep_if_same=keep_if_same)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Prep document for a booked call.")
    ap.add_argument("contact", nargs="?", default="",
                    help="contact_id, or the person's name")
    ap.add_argument("--all", action="store_true",
                    help="rewrite every contact's prep document")
    ap.add_argument("--stale-only", action="store_true",
                    help="rewrite only the documents an older prep wrote, with no stamp, or "
                         "written before the contact's row or thread changed; never write "
                         "one for a contact who has none")
    ap.add_argument("--dry-run", action="store_true",
                    help="list the documents that would be written, and write nothing")
    ap.add_argument("--check", action="store_true",
                    help="are the answers in this contact's prep fit to say aloud? Exits 1 "
                         "while any is profile wording or reads as written")
    ap.add_argument("--contacts", default=state.CONTACTS_CSV)
    ap.add_argument("--threads", default=state.THREADS_CSV)
    ap.add_argument("--tracker", default=state.TRACKER_CSV)
    ap.add_argument("--profile-facts", default="",
                    help="JSON of facts drawn from 01-candidate-profile.md. Nothing is "
                         "invented when this is absent; the section says so instead.")
    ap.add_argument("--root", default=STATE_ROOT)
    ap.add_argument("--today", default=datetime.date.today().isoformat())
    a = ap.parse_args(argv)
    if not (a.contact or a.all or a.stale_only):
        ap.error("name a contact (their contact_id or name), or --all")

    contacts = state.load_contacts(a.contacts)
    threads = state.load_threads(a.threads) if os.path.exists(a.threads) else []
    if a.all or a.stale_only:
        # The documents on disk are only as current as the code that wrote
        # them. Without a way to refresh the whole set, a fix to the company
        # section or the question shapes reaches whichever one somebody happens
        # to run next and no others.
        todo, needs = [], []
        tracker = state.load_tracker(a.tracker) if os.path.exists(a.tracker) else []
        for row in contacts:
            if not _text(row.get("name")):
                continue
            path = prep_path(row, a.root)
            research = load_research(row.get("company"), a.root)
            if os.path.exists(path):
                # Every prep on disk, rebuilt or not: a call close enough to need research.
                need = research_needed(row, research, a.today)
                if need:
                    needs.append("%s: %s" % (_text(row.get("name")), need))
            if a.stale_only and not stale(path, row, threads, research,
                                          find_application(row, tracker), a.today):
                continue
            todo.append((row, path))
        if a.dry_run:
            for _row, path in todo:
                print("would %s %s" % ("rewrite" if os.path.exists(path) else "write",
                                       os.path.relpath(path, a.root)))
            print("%d prep documents would be written (prep v%d); nothing written"
                  % (len(todo), generator_version()))
            return 0
        wrote = same = 0
        for row, path in todo:
            before = _read(path)
            _write_one(row, tracker, a, keep_if_same=True)
            if _read(path) == before:
                same += 1
            else:
                wrote += 1
        print("%d prep documents written%s%s" % (
            wrote, " (the ones older than prep v%d, or whose contact or thread has changed "
            "since)" % redo_from() if a.stale_only else "",
            "; %d already current, left as they were" % same if same else ""))
        for line in needs:
            print(line)
        return 0
    row = (state.already_contacted(contacts, contact_id=a.contact)
           or state.already_contacted(contacts, name=a.contact))
    if not row:
        print("no contact matching %r in %s" % (a.contact, a.contacts), file=sys.stderr)
        return 1

    if a.check:
        path = prep_path(row, a.root)
        try:
            with open(path, encoding="utf-8") as fh:
                found = check_answers(fh.read())
        except OSError:
            print("prep: no %s yet: write it first" % os.path.relpath(path, a.root),
                  file=sys.stderr)
            return 1
        for q, why_ in found:
            print("- %s: %s" % (q, why_))
        print("%d answer(s) not fit to say yet." % len(found) if found else
              "Every answer is fit to say aloud.")
        return 1 if found else 0
    if a.dry_run:
        print("would write %s; nothing written" % os.path.relpath(prep_path(row, a.root), a.root))
        return 0
    tracker = state.load_tracker(a.tracker) if os.path.exists(a.tracker) else []
    print(os.path.relpath(_write_one(row, tracker, a), a.root))
    need = research_needed(row, load_research(row.get("company"), a.root), a.today)
    if need:
        print(need)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
