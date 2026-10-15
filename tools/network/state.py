#!/usr/bin/env python3
"""The contact book, the message log, and the join back to the application tracker.

`tools/network/schema.py` decides what a contact row and a thread row hold.
This module is the only thing that reads and writes them, so every rule about
identity, staleness and what the user owes lives in one place instead of being
re-derived by each command.

Four decisions are worth the explanation.

**Employer identity is `company_key.key()`, never a string compare.** The
throttle learned this first: a tracker row can hold an employer's initials
while the scrape produces its legal name, and a comparison on raw text lets the
duplicate through. A contact book has the same failure with worse consequences,
because the cost of getting it wrong is a second cold message to a company that
already has one in flight.

**Status is derived from the message log, not read off the contact row.** A
stored status drifts the moment someone answers and the row is not edited, and
the row is edited by hand. `derive_status` reads the messages; `reconcile`
reports every row whose stored value disagrees, so the drift is visible rather
than silent. The log cannot see everything: it knows who spoke last, not
whether a call got booked, so the six statuses outside `DERIVABLE` are still
carried on the contact row and are never "corrected" against the log.

**Unknown CSV columns survive a round trip.** These files are opened in a
spreadsheet. Someone will add a column, and a loader that writes back only the
schema columns would delete it on the next save without anyone noticing until
the column was needed.

**Follow-up timing is counted in business days.** Six calendar days from a
Wednesday is the following Tuesday; six business days is the Thursday after
that. Nudging on the calendar count is what makes a follow-up read as impatient,
which is exactly what the cadence in `schema.FOLLOWUP_BUSINESS_DAYS` exists to
avoid.

Usage:
    python3 tools/network/state.py [--today YYYY-MM-DD]
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import datetime
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (_HERE, os.path.dirname(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import schema  # noqa: E402
from company_key import key as company_key, fold as _ck_fold  # noqa: E402
from throttle import FINAL as _THROTTLE_FINAL  # noqa: E402
import person  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(_HERE))
# The person's weekend, as Python weekday numbers (Monday 0). Saturday and
# Sunday unless profile/search.py WEEKEND says otherwise: in much of the world
# the working week runs Sunday to Thursday, and a follow-up "five business
# days" later lands on a different date there.
try:
    WEEKEND = frozenset(getattr(person.module("search"), "WEEKEND", (5, 6)))
except person.NoProfile:
    WEEKEND = frozenset((5, 6))
CONTACTS_CSV = person.state("network_contacts.csv")
THREADS_CSV = person.state("network_threads.csv")
TRACKER_CSV = person.state("job_search_tracker.csv")

# The statuses the log is the authority on: it knows who spoke last. A stored
# value in this set that disagrees with the log is drift. `call_booked`,
# `in_conversation`, `referral_in_progress` and the three terminal statuses
# record facts no message log carries, so a stored value outside it is
# information, not drift.
#
# `derive_status` can also return `connected_no_reply`, when the log holds an
# acceptance, and it is kept out of this set on purpose. The log can show an
# acceptance but cannot rule one out: the repo cannot see LinkedIn, so most
# acceptances arrive as the user saying so and the row being edited, and a
# stored `connected_no_reply` over a log that shows only the request is the log
# being behind, not the row being wrong.
DERIVABLE = frozenset({"not_contacted", "awaiting_reply", "replied_needs_response"})

# Tracker statuses that close an application, taken from `throttle.FINAL` rather
# than restated. A second copy written from the vocabulary in
# .claude/commands/outcome.md had already drifted: that list does not name
# `declined`, which the tracker can hold, and `throttle.FINAL` carries it for
# exactly that reason. The drift made an employer
# the user had walked away from read as an open application here. Frozen so a
# caller cannot reach through the alias and edit the scraper's own set.
TRACKER_FINAL = frozenset(_THROTTLE_FINAL)

# Statuses the nudge clock does not run on. A terminal thread is finished, a
# booked call is a scheduled event rather than silence, and `not_contacted` has
# nothing to chase. Everything else is waiting on them and takes the clock,
# including `in_conversation` and `referral_in_progress`, which go quiet in
# exactly the way the brief describes.
NO_NUDGE = frozenset(schema.TERMINAL | {"call_booked", "not_contacted"})

# The brief's instruction for a hit connection cap, kept here so every caller
# gives the same advice.
# What a free account does when its personalised notes for the month are spent,
# and why it has no InMail. LinkedIn lets a request go without a note, and a
# 1st-degree connection can be messaged without limit.
NO_NOTES_LEFT = ("This month's personalised notes are used up: send the connection request "
                 "without a note, and send the drafted note as a message once they accept.")
NO_INMAIL = ("No InMail on a free account, except to an Open Profile (their profile shows a "
             "Message button). Use a connection request instead.")
CAPPED_NOTE = ("Connection cap reached for this week. Following a target costs nothing "
               "and lets the request go out warm when the cap resets.")


# ---------------------------------------------------------------- dates

_ISO = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


def as_date(value) -> datetime.date | None:
    """A date from a date, a datetime, or text. None when there is nothing usable.

    Thread rows are hand-edited, so a date arrives as a bare `2030-01-15`, as a
    timestamp a mail client pasted in, or as a blank. Pulling the first ISO date
    out of the text handles all three without a format list to keep in sync.
    """
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    m = _ISO.search(str(value or ""))
    if not m:
        return None
    try:
        return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _need_date(value, what: str) -> datetime.date:
    d = as_date(value)
    if d is None:
        raise ValueError(f"{what} must be a date or an ISO date string, got {value!r}")
    return d


def business_days_between(a, b) -> int:
    """Weekdays strictly after `a` up to and including `b`. Negative if `b` precedes `a`.

    Counted by whole weeks rather than a day loop: any seven consecutive days
    hold exactly five weekdays, so only the remainder needs walking, and a
    contact last touched two years ago costs the same as one from Tuesday.
    """
    a, b = _need_date(a, "start date"), _need_date(b, "end date")
    if b < a:
        return -business_days_between(b, a)
    weeks, extra = divmod((b - a).days, 7)
    days = weeks * (7 - len(WEEKEND))
    d = a
    for _ in range(extra):
        d += datetime.timedelta(days=1)
        if d.weekday() not in WEEKEND:
            days += 1
    return days


def add_business_days(start, count: int) -> datetime.date:
    """The date `count` weekdays after `start`. A count of zero returns `start` unchanged.

    The inverse of `business_days_between`, so a due date can be shown as a day
    the user recognizes instead of "six business days from whenever you sent it".
    """
    d = _need_date(start, "start date")
    for _ in range(max(count, 0)):
        d += datetime.timedelta(days=1)
        while d.weekday() in WEEKEND:
            d += datetime.timedelta(days=1)
    return d


# ---------------------------------------------------------------- CSV store


def _write_csv(path: str, rows, columns) -> None:
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    fields = list(columns)
    seen = set(fields)
    # Columns somebody added by hand keep their place after the schema ones.
    # Dropping them here is how a spreadsheet edit gets silently reverted. Only
    # columns already in the file's header count: a key a tool put on a row in
    # memory (triage's `undated_signal`, `location_unverified`, a search
    # snippet) is not a column, and taking every key as one wrote them into the
    # contact book.
    try:
        with open(path, newline="", encoding="utf-8") as f:
            header = next(csv.reader(f), [])
    except OSError:
        header = []
    for k in header:
        if k and k not in seen:
            seen.add(k)
            fields.append(k)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, restval="", extrasaction="ignore",
                           lineterminator="\n")
        w.writeheader()
        for row in rows:
            w.writerow({k: ("" if row.get(k) is None else row.get(k)) for k in fields})


def _read_csv(path: str, columns) -> list[dict]:
    """Rows as dicts, with every schema column present and every extra column kept.

    Built on `csv.reader` rather than `DictReader` so a short row fills with
    blanks and an over-long one cannot land under a `None` key that then breaks
    the writer.
    """
    if not os.path.exists(path):
        _write_csv(path, [], columns)
        return []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader, [])
        header = [h.strip() for h in header]
        rows = []
        for raw in reader:
            if not any(cell.strip() for cell in raw):
                continue
            row = {c: "" for c in columns}
            for i, name in enumerate(header):
                if name:
                    row[name] = raw[i] if i < len(raw) else ""
            rows.append(row)
    return rows


def load_contacts(path: str = CONTACTS_CSV) -> list[dict]:
    return _read_csv(path, schema.CONTACT_COLUMNS)


def save_contacts(rows, path: str = CONTACTS_CSV) -> None:
    _write_csv(path, rows, schema.CONTACT_COLUMNS)


def load_threads(path: str = THREADS_CSV) -> list[dict]:
    return _read_csv(path, schema.THREAD_COLUMNS)


def save_threads(rows, path: str = THREADS_CSV) -> None:
    _write_csv(path, rows, schema.THREAD_COLUMNS)


def load_tracker(path: str = TRACKER_CSV) -> list[dict]:
    """The application tracker, read only. Nothing here ever writes it."""
    with open(path, newline="", encoding="utf-8") as f:
        return [dict(r) for r in csv.DictReader(f)]


# ---------------------------------------------------------------- identity

_PAREN = re.compile(r"\([^)]*\)")
# Every separator LinkedIn puts between a name and a headline. The em dash and
# the bullet are written as escapes so the source file stays free of both
# characters; leaving the em dash out turned "Wren Halloway \u2014 Acme" into the
# surname "Acme" and the id "acme_acme".
_TRAILER = re.compile(r"\s+[|\u2013\u2014\u00b7\u2022-]\s+")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _fold(s: str) -> str:
    """The same text with its accents dropped.

    LinkedIn returns one person as "Juno Castellan" in one snippet and
    "Juno Castell\u00e1n" in the next. Slugging the raw text gives
    `acme_castellan` and `acme_castell_n`, so the second harvest looks like a new
    person, `already_contacted` misses the row that is already there, and the
    user can send a second cold message to someone already written to.
    """
    # company_key.fold also folds the letters NFKD leaves alone: "S\u00f8ren
    # M\u00f8ller" slugged to "s_ren_m_ller" and "\u0141ukasz" to "ukasz".
    return _ck_fold(s)

# A name harvested from a search snippet carries whatever the person appended to
# it: "Wren Halloway, MSc", "Daniel Lee (He/Him)", "Wren Halloway | Acme". Taking the
# last token as the surname turned those into ids of "msc" and "he_him", which
# collide across unrelated people at one company.
_HONORIFICS = {"mr", "mrs", "ms", "miss", "mx", "dr", "prof", "professor", "sir"}
_CREDENTIALS = {
    "phd", "md", "mba", "msc", "bsc", "bcomm", "meng", "mphil", "llb", "jd",
    "cfa", "cpa", "cma", "cfp", "pmp", "frm", "cissp", "peng", "mcp", "esq",
}
# Generational suffixes only ever trail the name. Credentials are stripped from
# a trailing position too, but never from a position that would leave a single
# token: "Jack Ma" and "Sofia Ca" are names, and an over-eager list of short
# abbreviations would eat the surname it was meant to protect.
_SUFFIXES = _CREDENTIALS | {"jr", "sr", "ii", "iii", "iv"}


def _bare(token: str) -> str:
    return _NON_ALNUM.sub("", _fold(token).lower())


def person_name(name: str | None) -> str:
    """The bare first-and-last name: pronouns, honorifics and credentials removed."""
    s = _PAREN.sub(" ", str(name or ""))
    s = _TRAILER.split(s)[0]
    chunks = [c.strip() for c in s.split(",")]
    tokens = chunks[0].split()
    for chunk in chunks[1:]:
        extra = chunk.split()
        # "Wren Halloway, MSc, CFA" drops the credential chunks. "Halloway, Wren" is a
        # name written back to front and keeps both halves.
        if extra and all(_bare(t) in _CREDENTIALS for t in extra):
            continue
        tokens.extend(extra)
    tokens = [t for t in tokens if _bare(t) not in _HONORIFICS]
    while len(tokens) > 2 and _bare(tokens[-1]) in _SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def surname(name: str | None) -> str:
    parts = person_name(name).split()
    return parts[-1] if parts else ""


def first_initial(name: str | None) -> str:
    parts = person_name(name).split()
    for ch in parts[0] if parts else "":
        if ch.isalnum():
            return ch.lower()
    return ""


# Letters of any script are kept. "[^a-z0-9]" emptied a Cyrillic, Greek, Arabic
# or Chinese name, and an empty name skipped the name test: already_contacted()
# matched the first person at that employer, so a stranger read as somebody
# already messaged, and contact_id() refused the name outright.
_NON_WORD = re.compile(r"[\W_]+")


def _slug(s: str | None) -> str:
    return _NON_WORD.sub("_", _fold(str(s or "")).lower()).strip("_")


# A LinkedIn profile URL is the one identifier that survives a nickname, a
# married name, a reversed "Halloway, Wren" and a change of employer.
_PROFILE_HANDLE = re.compile(r"linkedin\.com/in/([^/?#\s]+)", re.I)


def profile_handle(url: str | None) -> str:
    """The /in/<handle> of a LinkedIn profile URL, lowercased and decoded, or ""."""
    from urllib.parse import unquote
    m = _PROFILE_HANDLE.search(str(url or ""))
    return unquote(m.group(1)).strip().lower() if m else ""


def _by_handle(rows, url):
    want = profile_handle(url)
    if not want:
        return None
    for row in rows or ():
        if isinstance(row, dict) and profile_handle(row.get("linkedin_url")) == want:
            return row
    return None


def contact_id(name: str | None, company: str | None) -> str:
    """A stable slug for one person: employer key plus surname.

    Keyed on the employer rather than the raw company name so the same person
    gets the same id whether the search snippet gave an employer's initials or
    its legal name. Two people sharing a surname at one employer land on the same slug
    by design; `unique_contact_id` is what resolves that, because a collision
    has to be resolved against the ids that already exist, not guessed at here.
    """
    sn = _slug(surname(name))
    if not sn:
        raise ValueError(f"contact_id needs a name with a surname in it, got {name!r}")
    ck = _slug(company_key(company))
    if ck:
        return f"{ck}_{sn}"
    # With no employer the surname is the whole id, and a one-letter surname
    # makes it useless: "Robin S" and "Quinn S" both became "s". Recruiter
    # contacts can arrive this way, initial only and no company named. Fall back to
    # the full name so the id still identifies somebody.
    if len(sn) < 2:
        full = _slug(name)
        if full:
            return full
    return sn


def _id_set(existing) -> set:
    """Ids from either a list of id strings or a list of contact rows."""
    out = set()
    for item in existing or ():
        if isinstance(item, dict):
            item = item.get("contact_id")
        item = str(item or "").strip()
        if item:
            out.add(item)
    return out


def unique_contact_id(name: str | None, company: str | None, existing=(),
                      linkedin_url: str | None = None) -> str:
    """`contact_id`, with a first-initial suffix when the slug is already taken.

    Deterministic for a given set of existing ids: the same person added against
    the same book always gets the same id, so re-running a discovery pass cannot
    fork one person into two rows.

    A person already in the book keeps the id they already have. Suffixing it
    instead is what made the promise above false: a second pass over the same
    companies would turn Wren Halloway into `acme_halloway_w` beside her own
    `acme_halloway`, and the duplicate would only surface when a second message
    went out. Only contact rows can answer this; a bare id string does not say
    whose it is.
    """
    same = _by_handle(existing, linkedin_url)
    if same and str(same.get("contact_id") or "").strip():
        return str(same["contact_id"]).strip()
    want_name = _match_name(name)
    if want_name:
        want_key = company_key(company)
        for row in existing or ():
            if not isinstance(row, dict):
                continue
            if _match_name(row.get("name")) != want_name:
                continue
            if row_company_key(row) != want_key:
                continue
            found = str(row.get("contact_id") or "").strip()
            if found:
                return found

    taken = _id_set(existing)
    base = contact_id(name, company)
    if base not in taken:
        return base
    stem = base
    initial = first_initial(name)
    if initial:
        stem = f"{base}_{initial}"
        if stem not in taken:
            return stem
    n = 2
    while f"{stem}_{n}" in taken:
        n += 1
    return f"{stem}_{n}"


def row_company_key(row) -> str:
    """The employer identity of a contact row.

    Recomputed from the company name, with the stored `company_key` column used
    only when the name is blank. The column is a convenience for filtering in a
    spreadsheet, not the authority: `company_key.ALIASES` grows, so a key written
    last month can be stale while the name it came from still resolves correctly.
    """
    k = company_key(row.get("company"))
    if k:
        return k
    return str(row.get("company_key") or "").strip().lower()


def _match_name(name: str | None) -> str:
    return _slug(person_name(name))


def first_degree(path=None) -> list:
    """The person's own LinkedIn connections, from LinkedIn's data export, or [].

    LinkedIn (Settings, Data privacy, Get a copy of your data, Connections)
    writes Connections.csv with a few lines of notes above the header. Dropped
    into documents/linkedin/, it is the one source of who the person is already
    connected with, which no search can see.
    """
    path = path or person.state("documents", "linkedin", "Connections.csv")
    try:
        with open(path, encoding="utf-8-sig", newline="") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return []
    start = next((i for i, ln in enumerate(lines) if ln.lower().startswith("first name")), None)
    if start is None:
        return []
    out = []
    for row in csv.DictReader(lines[start:]):
        name = " ".join(x for x in (row.get("First Name"), row.get("Last Name")) if x).strip()
        if not name:
            continue
        out.append({"name": name, "linkedin_url": row.get("URL") or "",
                    "company": row.get("Company") or "", "title": row.get("Position") or "",
                    "connected_on": row.get("Connected On") or ""})
    return out


def connections_at(connections, company) -> list:
    """The person's 1st-degree connections at one employer: the first people to message."""
    k = company_key(company)
    return [c for c in connections or () if k and company_key(c.get("company")) == k]


def already_contacted(contacts, name=None, company=None, contact_id=None, linkedin_url=None):
    """The existing row for this person, or None.

    The brief's rule is that discovery never surfaces someone who is already in
    the book, so a row counts as a match whatever its status: a row with status
    `not_contacted` is a target somebody already queued, and surfacing it again
    produces the duplicate the rule exists to prevent. The caller decides what to
    do with the row; this only answers whether it is there.

    Company matching goes through `company_key`, so a contact recorded under
    an employer's initials is found by a search for its legal name. A name given without a
    company matches across employers, because someone who changed jobs since the
    first message is still someone who has been messaged.
    """
    if contact_id:
        want = str(contact_id).strip()
        for row in contacts:
            if str(row.get("contact_id") or "").strip() == want:
                return row
        return None
    # The profile URL first: it finds the same person under a nickname, a new
    # employer or a reordered name, none of which the name test can.
    same = _by_handle(contacts, linkedin_url)
    if same is not None:
        return same
    if not name and not company:
        if linkedin_url:
            return None
        raise ValueError("already_contacted needs a name, a company, a contact_id or a URL")
    want_name = _match_name(name) if name else ""
    if name and not want_name:
        # A name that reduces to nothing matches nobody; it never means "anyone".
        return None
    want_key = company_key(company) if company else ""
    for row in contacts:
        if want_key and row_company_key(row) != want_key:
            continue
        if want_name and _match_name(row.get("name")) != want_name:
            continue
        return row
    return None


def contacts_at(contacts, company) -> list[dict]:
    """Every contact at one employer, matched by company key."""
    want = company_key(company)
    if not want:
        return []
    return [row for row in contacts if row_company_key(row) == want]


# ---------------------------------------------------------------- threads

# Direction and channel are typed by hand into a spreadsheet, so the obvious
# synonyms have to resolve. An unrecognized value is left unresolved rather than
# guessed at, and `reconcile` reports it.
_OUT = {"out", "outbound", "sent", "o", "us", "me"}
_IN = {"in", "inbound", "received", "reply", "them", "i"}

_CHANNEL_ALIASES = {
    "connection request": "connection", "connection_request": "connection",
    "connect": "connection", "invite": "connection", "invitation": "connection",
    "linkedin": "connection",
    "in-mail": "inmail", "in mail": "inmail", "in_mail": "inmail",
    "linkedin inmail": "inmail",
    "e-mail": "email", "mail": "email",
    "introduction": "intro", "warm intro": "intro", "warm_intro": "intro",
}


def _direction(row) -> str:
    d = str(row.get("direction") or "").strip().lower()
    if d in _OUT:
        return "out"
    if d in _IN:
        return "in"
    return ""


def channel_of(row) -> str:
    raw = row if isinstance(row, str) else row.get("channel")
    c = str(raw or "").strip().lower()
    return _CHANNEL_ALIASES.get(c, c)


# An inbound row that records something they did rather than something they
# said. The log keeps an accepted connection request as `direction=in`, with
# this scenario and no text, for example a row reading "Accepted the connection
# request. No message." Read by direction alone it was a reply, so the contact
# came out `replied_needs_response`, a warm route in `throttle.RESPONDED` on the
# strength of a click, and `reply.nudge_due` refused the nudge because "they
# answered". The status name is accepted as the scenario too, because that is
# the word a person reaches for when logging it by hand.
ACCEPTED_SCENARIOS = frozenset({"accepted_no_reply", "connected_no_reply", "connection_accepted"})


def is_acceptance(row) -> bool:
    """Is this row an accepted connection request rather than a message?"""
    scenario = re.sub(r"[\s-]+", "_", str(row.get("scenario") or "").strip().lower())
    return _direction(row) == "in" and scenario in ACCEPTED_SCENARIOS


def said_something(row) -> bool:
    """An inbound row that is a message: the only kind that makes a route warm."""
    return _direction(row) == "in" and not is_acceptance(row)


def threads_for(threads, contact_id_value) -> list[dict]:
    """Every message row for one contact, in the order they happened."""
    want = str(contact_id_value or "").strip()
    return _ordered([r for r in threads
                     if str(r.get("contact_id") or "").strip() == want])


def _ordered(rows) -> list[dict]:
    """Message rows oldest first.

    Ties break on file order, which is the only tiebreak available: THREAD_COLUMNS
    carries a date and no time, and a same-day send-and-reply is common. A row
    whose date will not parse sorts as the oldest rather than the newest, so a
    typo cannot decide a contact's status on its own; `reconcile` reports it.
    """
    return [r for _, r in sorted(enumerate(rows),
                                 key=lambda p: (as_date(p[1].get("date")) or datetime.date.min,
                                                p[0]))]


def derive_status(threads_for_contact) -> str:
    """Status from the message history: the source of truth the contact row copies.

    Nothing to send means nothing has happened; our message last means they owe
    us; their message last means we owe them. Anything the log cannot see stays
    on the contact row and is handled by `effective_status`.

    An acceptance is neither. It moves a thread that is waiting on them to
    `connected_no_reply`, which stays until they actually write, and it answers
    nothing: accepting after writing leaves the reply owed where it was.
    """
    status = "not_contacted"
    for row in _ordered(threads_for_contact):
        if not _direction(row):
            continue
        if is_acceptance(row):
            if status != "replied_needs_response":
                status = "connected_no_reply"
        elif _direction(row) == "in":
            status = "replied_needs_response"
        elif status != "connected_no_reply":
            status = "awaiting_reply"
    return status


def effective_status(contact, thread_rows) -> str:
    """What the thread is actually at, reading the log and the row together.

    A terminal row wins outright: a thread the user closed must never come back
    as a nudge because the last message in it happens to be outbound. An inbound
    last message wins over any non-terminal stored status, because a reply is
    owed whether the row says `call_booked` or nothing at all. Otherwise the
    stored value is kept when it holds something the log cannot derive.

    An empty log against a row that claims a thread means the log is behind, not
    that nothing was sent. Discovery writes the contact row the moment the
    request goes out and the thread row lands afterwards, which is the same
    ordering `platform_budget` already accounts for; reading `not_contacted` off
    the empty log kept a whole batch of sent requests out of the nudge queue.
    `reconcile` still reports the missing rows as `no_messages_logged`.
    """
    stored = str(contact.get("status") or "").strip()
    derived = derive_status(thread_rows)
    if stored in schema.TERMINAL:
        return stored
    if derived == "replied_needs_response":
        return derived
    if stored not in schema.THREAD_STATUSES:
        return derived
    if not thread_rows and stored != "not_contacted":
        return stored
    if stored not in DERIVABLE:
        return stored
    return derived


# Findings that are a note rather than a job. `history_not_logged` is a
# relationship that predates the message log, and a book imported from earlier
# notes can arrive with a great many of them; reporting those as errors puts
# dozens of rows in front of a reader and buries the few that need answering.
NOTE_ONLY = frozenset({"history_not_logged"})


def reconcile(contacts, threads) -> list[dict]:
    """Every place the stored state and the message log disagree.

    Only the three statuses in `DERIVABLE` are checked against the log. Flagging
    `call_booked` for disagreeing with `awaiting_reply` would report every healthy
    thread in the book and train the user to skip the output.
    """
    problems = []

    def flag(cid, name, stored, derived, reason, detail=""):
        problems.append({"contact_id": cid, "name": name, "stored": stored,
                         "derived": derived, "reason": reason, "detail": detail})

    known = set()
    for contact in contacts:
        cid = str(contact.get("contact_id") or "").strip()
        known.add(cid)
        name = contact.get("name", "")
        stored = str(contact.get("status") or "").strip()
        rows = threads_for(threads, cid)
        derived = derive_status(rows)
        if stored and stored not in schema.THREAD_STATUSES:
            flag(cid, name, stored, derived, "unknown_status",
                 "not one of schema.THREAD_STATUSES")
        for row in rows:
            if as_date(row.get("date")) is None:
                flag(cid, name, stored, derived, "unparseable_date",
                     f"thread row date {row.get('date')!r}")
            if not _direction(row):
                flag(cid, name, stored, derived, "unknown_direction",
                     f"thread row direction {row.get('direction')!r}")
        if not rows and stored and stored != "not_contacted":
            # Two different situations wear the same shape. A status the log
            # CAN derive (awaiting_reply, replied_needs_response) with no
            # messages is a contradiction: the evidence should be there. A
            # status it cannot derive (in_conversation, call_booked,
            # referral_in_progress, closed) never had message-level evidence to
            # begin with, and a book imported from earlier notes can arrive
            # that way: many relationships that predate the message log
            # entirely. Reporting those as errors puts dozens of rows in front
            # of the user and buries the few real ones, which is how a
            # reconcile report gets ignored.
            flag(cid, name, stored, derived,
                 "no_messages_logged" if stored in DERIVABLE else "history_not_logged",
                 "status claims a thread that has no messages"
                 if stored in DERIVABLE else
                 "relationship predates the message log; the status is not "
                 "derivable from messages, so this is a note, not an error")
        elif stored in DERIVABLE and stored != derived:
            flag(cid, name, stored, derived, "contradicts_log",
                 "the log says the status is " + derived)
        elif stored in schema.TERMINAL and derived == "replied_needs_response":
            flag(cid, name, stored, derived, "reopened",
                 "thread was closed and they have since replied")

    seen = set()
    for row in threads:
        cid = str(row.get("contact_id") or "").strip()
        if cid in known or cid in seen:
            continue
        seen.add(cid)
        flag(cid, "", "", "", "orphan_thread", "messages with no contact row")

    # A message logged twice is not a cosmetic duplicate. `_trailing_outbound`
    # counts consecutive outbound rows to decide whether a nudge is owed and
    # whether MAX_NUDGES is spent, so two copies of one InMail read as two
    # messages sent and suppress the nudge that was actually due. It is also how
    # a duplicate arises in practice: a contact renamed from `firstname_surname`
    # to `firstname_employer_surname` has its thread rows copied to the new id
    # while the originals are left behind. That shows up as `orphan_thread`, and
    # the obvious repair - repoint the orphans at the renamed contact - would
    # produce identical rows and a silent bug where there had been a loud one.
    # Checked per contact, because two contacts can legitimately be sent the
    # same sentence on the same day.
    per_contact = {}
    for row in threads:
        cid = str(row.get("contact_id") or "").strip()
        sig = tuple(str(row.get(k) or "").strip()
                    for k in ("date", "direction", "channel", "scenario", "summary"))
        per_contact.setdefault(cid, []).append(sig)
    for cid, sigs in per_contact.items():
        for sig, n in Counter(sigs).items():
            if n > 1:
                flag(cid, _name_of(contacts, cid), "", "", "duplicate_message",
                     "%d identical rows for %s on %s" % (n, sig[1] or "a message", sig[0]))
    return problems


def _name_of(contacts, cid):
    for contact in contacts:
        if str(contact.get("contact_id") or "").strip() == cid:
            return contact.get("name", "")
    return ""


def _trailing_outbound(msgs) -> int:
    """Our messages since they last wrote. An acceptance answers nothing, so the
    run carries on through it: a DM sat after the acceptance, and
    stopping there counted it as the first message after a reply and offered a
    second nudge."""
    n = 0
    for row in reversed(msgs):
        if is_acceptance(row):
            continue
        if _direction(row) != "out":
            break
        n += 1
    return n


# A next_action that opens by saying nothing is owed. Anchored to the start, the
# way the rows are written, so "no action until they reply" in the middle of a
# longer instruction is not read as one.
NO_REPLY_OWED = re.compile(r"\s*(?:nothing owed|no action|keep warm,? no action)\b", re.I)


def owed(contacts, threads, today) -> list[dict]:
    """What the user owes right now: every reply first, then nudges, each oldest first.

    Two kinds, and they are not the same job. A reply is owed the moment they
    answer. A nudge is owed only after `schema.FOLLOWUP_BUSINESS_DAYS` business
    days of silence and only while fewer than `schema.MAX_NUDGES` have gone out,
    because a second nudge on an unanswered thread is the message that costs the
    relationship rather than the one that saves it.

    Replies outrank nudges outright rather than being sorted against them on the
    day count, which `.claude/commands/threads.md` asks for and a single
    `business_days` sort does not give: those are two different clocks, and a
    six-day nudge was landing above somebody who answered this morning and is
    sitting there waiting.
    """
    today = _need_date(today, "today")
    items = []
    for contact in contacts:
        cid = str(contact.get("contact_id") or "").strip()
        msgs = [r for r in threads_for(threads, cid) if _direction(r)]
        status = effective_status(contact, msgs)
        base = {
            "contact_id": cid,
            "name": contact.get("name", ""),
            "company": contact.get("company", ""),
            "company_key": row_company_key(contact),
            "status": status,
            "tier": contact.get("tier", ""),
        }
        # A date the user set on themselves is owed as much as a reply is.
        #
        # owed() read the message log only, so a contact with a due
        # next_action was invisible whenever the log said nothing was
        # outstanding. call_booked is in NO_NUDGE, so a booked call with a
        # self-imposed date dropped out entirely: a "confirm the call" action
        # that was due appeared nowhere.
        due = as_date(contact.get("next_action_due"))
        action = (contact.get("next_action") or "").strip()
        overdue = (due is not None and action
                   and status not in schema.TERMINAL and due <= today)
        # The action rides on whichever row this contact produces, so a person
        # never appears twice. Listing one contact once as a reply and again as
        # an action puts duplicate rows on the list.
        base["next_action"] = action if overdue else ""
        base["next_action_due"] = due.isoformat() if overdue else ""

        if status in schema.OWED_BY_US and NO_REPLY_OWED.match(action) and not overdue:
            # The person's own row says no reply is owed, written after reading
            # their last message, such as "NOTHING OWED. Ball is in their court". The inbound-last rule listed such
            # contacts among the most overdue replies, which is the one list a
            # follow-up pack is built from.
            continue
        if status in schema.OWED_BY_US:
            last_in = next((r for r in reversed(msgs) if said_something(r)), None)
            since = as_date(last_in.get("date")) if last_in else None
            items.append(dict(base,
                              kind="reply",
                              channel=channel_of(last_in) if last_in else channel_of(contact),
                              since=since.isoformat() if since else "",
                              business_days=business_days_between(since, today) if since else 0,
                              due=since.isoformat() if since else "",
                              nudges_sent=0))
            continue
        # A contact this far down owes no reply. Whether they owe a nudge is
        # decided below; either way a date the user set on themselves is still
        # owed, and `_action_row` is what emits it on every path that does not
        # produce a nudge. call_booked sits in NO_NUDGE, which is why a booked
        # call with a "confirm the call" action due appeared nowhere at all.
        # The four parameters bind this iteration's values rather than
        # capturing the loop variables. Every call today is immediate, so the
        # capture happened to be correct; binding makes it correct by
        # construction instead of by inspection, which is what stops the next
        # person who defers one of these calls from getting the last contact's
        # data on every row.
        def _action_row(overdue=overdue, base=base, contact=contact, due=due):
            if not overdue:
                return
            items.append(dict(base,
                              kind="action_due",
                              channel=channel_of(contact),
                              since=due.isoformat(),
                              business_days=business_days_between(due, today),
                              due=due.isoformat(),
                              nudges_sent=0))

        if status in NO_NUDGE:
            _action_row()
            continue
        # Everything left here is waiting on them, not only `awaiting_reply`.
        # Reading that one status left `/threads` silent on a referral that had
        # sat for weeks while `reply.nudge_due` on the same rows reported
        # the nudge as due, which is the disagreement both are written to avoid.
        # The send date falls back to `first_contacted` for the same reason
        # `effective_status` does: the contact row is written before the thread
        # row exists. When the last row is an acceptance, its date is the one
        # the clock runs from: the networking skill waits "from the acceptance,
        # not from the send".
        last_out = msgs[-1] if msgs else None
        sent = (as_date(last_out.get("date")) if last_out
                else as_date(contact.get("first_contacted")))
        if sent is None:
            _action_row()
            continue
        nudges = max(_trailing_outbound(msgs) - 1, 0)
        if nudges >= schema.MAX_NUDGES:
            _action_row()
            continue
        waited = business_days_between(sent, today)
        if waited < schema.FOLLOWUP_BUSINESS_DAYS:
            _action_row()
            continue
        items.append(dict(base,
                          kind="nudge",
                          channel=channel_of(last_out) if last_out else channel_of(contact),
                          since=sent.isoformat(),
                          business_days=waited,
                          due=add_business_days(sent, schema.FOLLOWUP_BUSINESS_DAYS).isoformat(),
                          nudges_sent=nudges))
    # Replies first, then anything the user put a date on, then nudges. A
    # self-imposed date outranks a nudge because the user chose it; it does not
    # outrank somebody sitting waiting for an answer.
    order = {"reply": 0, "action_due": 1, "nudge": 2}
    items.sort(key=lambda i: (order.get(i["kind"], 9), -i["business_days"],
                              i["contact_id"]))
    return items


# ---------------------------------------------------------------- holds

# A next_action that opens on HOLD or FREEZE is an instruction not to act yet,
# and the due date beside it is when to look again, not when to send. Both are
# written into a contact's next_action: "HOLD until <date>", and "FREEZE ... No
# further outreach at <employer> until it resolves". A due list that read only
# the date would put the freeze in front of the user as a message to send.
_HOLD = re.compile(r"^\W*(?:on\s+)?(?:hold|freeze|frozen)\b", re.I)

# Where a hold written in prose ends. "until <date>" and "no nudge before
# <date>" lift on the day named; "goes silent past <date>" lifts the day
# after. Only a date introduced by one of these words is read: a freeze that
# quotes an event date in brackets would otherwise lift on the morning of that
# event. A hold with no end holds until somebody edits it.
_LIFTS = re.compile(r"\b(until|till|before|past|after)\s+(\d{4}-\d{2}-\d{2})\b", re.I)


def hold_lifts(text) -> datetime.date | None:
    """The first day a hold written in `text` no longer applies, or None when it names none."""
    m = _LIFTS.search(str(text or ""))
    if not m:
        return None
    day = as_date(m.group(2))
    if day is not None and m.group(1).lower() in ("past", "after"):
        day += datetime.timedelta(days=1)
    return day


def action_hold(next_action, today) -> str:
    """Why this next_action is held today, or "" when it is not a hold or has lifted."""
    text = str(next_action or "").strip()
    if not _HOLD.match(text):
        return ""
    lifts = hold_lifts(text)
    if lifts is None:
        return "on hold, no end date"
    if lifts <= _need_date(today, "today"):
        return ""
    return "on hold until %s" % lifts.isoformat()


# ---------------------------------------------------------------- tracker join


def link_to_applications(contacts, tracker_rows) -> list[dict]:
    """Contacts that have an application at the same employer, and which one.

    This is the integration the brief asks for: a thread and an application at
    one company are two views of the same pursuit, and the contact row's
    `linked_application` column is what carries it. Matching on `company_key`
    rather than the company string is what makes a contact recorded under an
    employer's legal name find the application filed under its initials.
    """
    by_key: dict[str, list[dict]] = {}
    for row in tracker_rows:
        by_key.setdefault(company_key(row.get("company")), []).append(row)
    for rows in by_key.values():
        # Most recent first. The sort is stable, so same-date applications keep
        # their tracker order instead of shuffling between runs.
        rows.sort(key=lambda r: as_date(r.get("date")) or datetime.date.min, reverse=True)

    out = []
    for contact in contacts:
        ck = row_company_key(contact)
        apps = by_key.get(ck, []) if ck else []
        if not apps:
            continue
        cv_files = [str(a.get("cv_file") or "").strip() for a in apps]
        stored = str(contact.get("linked_application") or "").strip()
        out.append({
            "contact_id": str(contact.get("contact_id") or "").strip(),
            "name": contact.get("name", ""),
            "company": contact.get("company", ""),
            "company_key": ck,
            "applications": apps,
            "roles": [a.get("role", "") for a in apps],
            "open_applications": [a for a in apps
                                  if str(a.get("status") or "").strip().lower()
                                  not in TRACKER_FINAL],
            "linked_application": stored,
            "suggested_link": next((c for c in cv_files if c), ""),
            "link_disagrees": bool(stored) and stored not in cv_files,
        })
    return out


# ---------------------------------------------------------------- platform limits


def _month_end(day: datetime.date) -> datetime.date:
    if day.month == 12:
        return day.replace(day=31)
    return day.replace(month=day.month + 1, day=1) - datetime.timedelta(days=1)


# A scenario that says the row was the request itself, which settles it
# whatever came before: an email reply is not a LinkedIn connection.
_REQUEST_SCENARIOS = frozenset({"connection_request", "connection_note", "invite", "invitation"})


def connection_requests(contacts, threads) -> set:
    """(contact_id, date) for every message that spent a connection request.

    The log writes a request and a direct message alike as channel `linkedin`,
    and `channel_of` maps both to `connection`, so counting the channel counted
    every DM to somebody already connected as a request. A warm intro and a
    thank-you DM inside a running referral both read as requests that way.

    A person holds one request at a time, so only the first LinkedIn message to
    someone who has not already written or accepted can be one. Everything after
    it went down a channel that was already open.

    The contact row stands in for a request the log has not caught up with,
    which is the order a discovery run writes them in. It no longer stands in
    once the log reaches back to `first_contacted`: that date is when contact
    began, and for a contact who wrote first it is the day THEY wrote.
    """
    by_contact: dict[str, list[dict]] = {}
    for row in threads:
        by_contact.setdefault(str(row.get("contact_id") or "").strip(), []).append(row)

    requests = set()
    for cid, rows in by_contact.items():
        connected = asked = False
        for row in _ordered(rows):
            if channel_of(row) != "connection":
                continue
            if _direction(row) == "in":
                connected = True
                continue
            if _direction(row) != "out":
                continue
            scenario = re.sub(r"[\s-]+", "_", str(row.get("scenario") or "").strip().lower())
            day = as_date(row.get("date"))
            if day and (scenario in _REQUEST_SCENARIOS or not (connected or asked)):
                requests.add((cid, day))
            asked = True

    for contact in contacts:
        cid = str(contact.get("contact_id") or "").strip()
        day = as_date(contact.get("first_contacted"))
        if not day or channel_of(contact) != "connection":
            continue
        logged = [d for d in (as_date(r.get("date")) for r in by_contact.get(cid, ())) if d]
        if not logged or min(logged) > day:
            requests.add((cid, day))
    return requests


def platform_budget(contacts, threads, today) -> dict:
    """Connection requests and InMail credits left, against `schema.LIMITS`.

    Counted from the contact rows as well as the message log, deduplicated on
    person, channel and date. A discovery run writes the contact row with its
    `first_contacted` date at the moment the request goes out and the thread row
    lands afterwards, so counting only the log reports a budget the user has
    already spent. Connections are what `connection_requests` says went out as
    a request; a message to somebody already connected spends nothing.
    """
    today = _need_date(today, "today")
    week_start = today - datetime.timedelta(days=today.weekday())
    week_end = week_start + datetime.timedelta(days=6)
    month_start = today.replace(day=1)
    month_end = _month_end(today)

    sends = set()
    for row in threads:
        if _direction(row) != "out":
            continue
        day, channel = as_date(row.get("date")), channel_of(row)
        if day and channel:
            sends.add((str(row.get("contact_id") or "").strip(), channel, day))
    for contact in contacts:
        day, channel = as_date(contact.get("first_contacted")), channel_of(contact)
        if day and channel:
            sends.add((str(contact.get("contact_id") or "").strip(), channel, day))

    requests = connection_requests(contacts, threads)
    connections = sum(1 for _, d in requests if week_start <= d <= week_end)
    inmails = sum(1 for _, ch, d in sends
                  if ch == "inmail" and month_start <= d <= month_end)
    conn_limit = schema.LIMITS["connections_per_week"]
    inmail_limit = schema.LIMITS["inmail_credits_per_month"]
    conn_left = max(conn_limit - connections, 0)
    # Drafts queued and not yet sent spend the same budget the moment they go,
    # and a second /network in the same week sized itself as though they did not
    # exist. Reported beside the budget rather than taken off it: a row queued
    # months ago and never sent should not hold the budget down for ever.
    queued = {"connection": 0, "inmail": 0}
    for contact in contacts:
        if (str(contact.get("status") or "").strip() == "not_contacted"
                and channel_of(contact) in queued):
            queued[channel_of(contact)] += 1
    # A free account's personalised notes run out within the month; after that a
    # request goes without a note and the message follows the acceptance.
    notes_limit = schema.LIMITS.get("personal_notes_per_month")
    notes_sent = sum(1 for _, d in requests if month_start <= d <= month_end)
    notes_left = None if notes_limit is None else max(notes_limit - notes_sent, 0)
    note = CAPPED_NOTE if conn_left == 0 else ""
    if notes_left == 0 and conn_left:
        note = NO_NOTES_LEFT
    return {
        "plan": schema.PLAN,
        "queued_unsent": queued,
        "personal_notes_limit": notes_limit,
        "personal_notes_left": notes_left,
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "month_start": month_start.isoformat(),
        "month_end": month_end.isoformat(),
        "connections_sent": connections,
        "connections_limit": conn_limit,
        "connections_left": conn_left,
        "inmails_sent": inmails,
        "inmails_limit": inmail_limit,
        "inmails_left": max(inmail_limit - inmails, 0),
        "connection_note_chars": schema.LIMITS["connection_note_chars"],
        "inmail_words": schema.LIMITS["inmail_words"],
        "note": note,
        "inmail_note": "" if inmail_limit else NO_INMAIL,
    }


# ---------------------------------------------------------------- CLI


def main() -> int:
    ap = argparse.ArgumentParser(description="Networking pipeline state.")
    ap.add_argument("--contacts", default=CONTACTS_CSV)
    ap.add_argument("--threads", default=THREADS_CSV)
    ap.add_argument("--tracker", default=TRACKER_CSV)
    ap.add_argument("--today", default=datetime.date.today().isoformat())
    a = ap.parse_args()

    contacts = load_contacts(a.contacts)
    threads = load_threads(a.threads)
    print(f"{len(contacts)} contacts, {len(threads)} messages\n")

    items = owed(contacts, threads, a.today)
    print("OWED" if items else "OWED: nothing due")
    for i in items:
        print(f"  [{i['kind']:5}] {i['name'] or i['contact_id']} ({i['company']}) "
              f"{i['business_days']}bd since {i['since'] or 'unknown'}")

    b = platform_budget(contacts, threads, a.today)
    print(f"\nBUDGET  connections {b['connections_left']}/{b['connections_limit']} left "
          f"this week, InMail {b['inmails_left']}/{b['inmails_limit']} left this month")
    if b["note"]:
        print("  " + b["note"])

    if os.path.exists(a.tracker):
        links = link_to_applications(contacts, load_tracker(a.tracker))
        print(f"\nLINKED  {len(links)} contacts sit at a company already in the tracker")
        for link in links:
            print(f"  {link['name'] or link['contact_id']} -> {', '.join(link['roles'])}")

    # `reconcile` already separates a contradiction from a note, and a printer
    # that threw that away would put every finding in one flat list, most of them
    # `history_not_logged`, with the few that need a person buried in the middle.
    # That is the failure `reconcile`'s own docstring describes, and the display
    # must not reintroduce it: an `orphan_thread` would sit unnoticed.
    problems = reconcile(contacts, threads)
    actionable = [p for p in problems if p["reason"] not in NOTE_ONLY]
    notes = len(problems) - len(actionable)
    if actionable:
        print(f"\nRECONCILE  {len(actionable)} need a person")
        for p in actionable:
            who = p["name"] or p["contact_id"]
            print(f"  {who} ({p['contact_id']}): {p['reason']} - {p['detail']}")
    elif problems:
        print("\nRECONCILE  nothing needs a person")
    if notes:
        print(f"           {notes} relationship(s) predate the message log; "
              f"not errors, and not repeated here")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
