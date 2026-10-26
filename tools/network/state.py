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
    python3 tools/network/state.py withdraw <contact_id>... [--all-due] [--reason "..."]
    python3 tools/network/state.py text <contact_id> --date YYYY-MM-DD --text-file <file>
    python3 tools/network/state.py message <contact_id> --text-file <file> [--attached <file>]
    python3 tools/network/state.py received <contact_id> --text-file <file> [--date YYYY-MM-DD] [--channel C]
    python3 tools/network/state.py attach <contact_id> <file | unknown> [--date YYYY-MM-DD]
    python3 tools/network/state.py no-reply <contact_id> --why "<what they said>" [--look-again YYYY-MM-DD]
    python3 tools/network/state.py sent <contact_id>... (--text-file <file> | --draft | --no-note |
        --outside) [--channel inmail --subject "..."] [--date YYYY-MM-DD]
    python3 tools/network/state.py resent <contact_id> [--text-file <file>] [--date ...] [--subject ...]
    python3 tools/network/state.py unsend <contact_id>
    python3 tools/network/state.py inmail-credits [<the balance LinkedIn shows>]
"""

from __future__ import annotations

import argparse
from collections import Counter
import datetime
import functools
import json
import os
import re
import shlex
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (_HERE, os.path.dirname(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import dates  # noqa: E402
import schema  # noqa: E402
from company_key import key as company_key, fold as _ck_fold, row_key as _ck_row_key  # noqa: E402
from throttle import (FINAL as _THROTTLE_FINAL, SILENCE_DAYS as _THROTTLE_SILENCE_DAYS,  # noqa: E402
                      UNSENT as _THROTTLE_UNSENT)
import person  # noqa: E402
from safe_name import windows_safe  # noqa: E402

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

# What a free account does when its personalised notes for the month are spent,
# and why it has no InMail. LinkedIn lets a request go without a note, and a
# 1st-degree connection can be messaged without limit.
NO_NOTES_LEFT = ("This month's personalised notes are used up: send the connection request "
                 "without a note, and send the drafted note as a message once they accept.")
NO_INMAIL = ("No InMail on a free account, except to an Open Profile (their profile shows a "
             "Message button). Use a connection request instead.")
# What to say when LinkedIn itself says its weekly invitation limit is reached: the app sets
# no cap of its own (2026-10-22), so this is only ever LinkedIn's.
CAPPED_NOTE = ("LinkedIn says its weekly invitation limit is reached. Following someone costs "
               "nothing and lets the request go out warm the week after; the rest stay queued.")


# ---------------------------------------------------------------- dates

def as_date(value) -> datetime.date | None:
    """A date from a date, a datetime, or text. None when there is nothing usable.

    Thread rows are hand-edited, so a date arrives as a bare `2030-01-15`, as a
    timestamp a mail client pasted in, or as a blank. The first ISO date in the
    text handles all three, which is `dates.as_date` with `anywhere`; a month or
    a "15 January 2030" is not read as a day here, as it never was.
    """
    return dates.as_date(value, iso_only=True, anywhere=True)


def _need_date(value, what: str) -> datetime.date:
    d = as_date(value)
    if d is None:
        raise ValueError(f"{what} must be a date or an ISO date string, got {value!r}")
    return d


def _holidays(first: datetime.date, last: datetime.date) -> set:
    """The person's public holidays from `first` to `last` that fall on a working day
    (tools/holidays.py): a follow-up counted Thanksgiving as a business day."""
    try:
        import holidays
        # A year's table can hold a day of the year before: the US New Year's Day of a
        # Saturday is kept on Friday 31 December, in the next year's table, so a range
        # ending in December reads the next year too (networking audit, 2026-10-25).
        return {d for y in range(first.year, last.year + 2) for d in holidays.for_year(y)
                if first <= d <= last and d.weekday() not in WEEKEND}
    except Exception:  # no profile, or no rules for the country: weekends alone, as before
        return set()


def business_days_between(a, b) -> int:
    """Working days strictly after `a` up to and including `b`. Negative if `b` precedes
    `a`. A public holiday is not a working day (tools/holidays.py).

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
    return days - len(_holidays(a + datetime.timedelta(days=1), b))


def add_business_days(start, count: int) -> datetime.date:
    """The date `count` weekdays after `start`. A count of zero returns `start` unchanged.

    The inverse of `business_days_between`, so a due date can be shown as a day
    the user recognizes instead of "six business days from whenever you sent it".
    """
    d = _need_date(start, "start date")
    off = _holidays(d, d + datetime.timedelta(days=max(count, 0) * 2 + 14))
    for _ in range(max(count, 0)):
        d += datetime.timedelta(days=1)
        while d.weekday() in WEEKEND or d in off:
            d += datetime.timedelta(days=1)
    return d


# ---------------------------------------------------------------- CSV store


def _write_csv(path: str, rows, columns) -> None:
    # The file's own header order, a schema column it lacks on the END, columns
    # added by hand kept, and the file's own line ending: tools/csv_store.py,
    # which the tracker's writers share, says why each matters.
    import csv_store
    csv_store.write_rows(path, rows, columns)


def _read_csv(path: str, columns) -> list[dict]:
    """Rows as dicts, with every schema column present and every extra column kept.

    A missing file is no rows, and stays missing: the first save writes it, header and
    all. Created on a read, a look (profile_upgrades --all, the sync's own --after-sync)
    left two new files in a copy without them, and then refused the instant upgrades
    because the folder had uncommitted changes (2026-10-25).
    """
    import csv_store
    return csv_store.read_rows(path, columns)


def load_contacts(path: str = CONTACTS_CSV) -> list[dict]:
    return _read_csv(path, schema.CONTACT_COLUMNS)


def save_contacts(rows, path: str = CONTACTS_CSV) -> None:
    _write_csv(path, rows, schema.CONTACT_COLUMNS)


def load_threads(path: str = THREADS_CSV) -> list[dict]:
    return _read_csv(path, schema.THREAD_COLUMNS)


def save_threads(rows, path: str = THREADS_CSV) -> None:
    _write_csv(path, rows, schema.THREAD_COLUMNS)


def load_tracker(path: str = TRACKER_CSV) -> list[dict]:
    """The application tracker, read only. Nothing here ever writes it (read the way a
    spreadsheet saved it: csv_store.read_text)."""
    import csv_store
    return csv_store.tracker(path, refuse=False)


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


# A post-nominal no list can hold: a professional body's letters in capitals ("FIRP",
# "GMS", "CHRL"). LinkedIn's export writes a name as the person typed it, letters and
# all, and "<Given> <Surname>, FIRP, GMS" became the surname "GMS", the id "<employer>_gms"
# and a name that matched nobody in the contact book.
_ABBREVIATION = re.compile(r"[A-Z][A-Z0-9&./-]{1,9}")


def _post_nominals(chunk_tokens, head_tokens, head) -> bool:
    """Is a chunk after a comma letters after a name, not the given name of a reversed one?

    Credentials always are. Capitals are too, but only after a full name ("Wren
    Halloway, FIRP"): "Halloway, Wren" and "HALLOWAY, WREN" keep both halves."""
    if not chunk_tokens:
        return False
    if all(_bare(t) in _CREDENTIALS for t in chunk_tokens):
        return True
    return (len(head_tokens) >= 2 and any(ch.islower() for ch in head)
            and all(_ABBREVIATION.fullmatch(t.strip(".,;")) for t in chunk_tokens))


def person_name(name: str | None) -> str:
    """The bare first-and-last name: pronouns, honorifics and credentials removed."""
    s = _PAREN.sub(" ", str(name or ""))
    s = _TRAILER.split(s)[0]
    chunks = [c.strip() for c in s.split(",")]
    tokens = chunks[0].split()
    head = list(tokens)
    for chunk in chunks[1:]:
        extra = chunk.split()
        # "Wren Halloway, MSc, CFA" and "Wren Halloway, FIRP, GMS" drop the letters after
        # the name. "Halloway, Wren" is a name written back to front and keeps both halves.
        if _post_nominals(extra, head, chunks[0]):
            continue
        tokens.extend(extra)
    # A word with no letter or digit in it is no part of a name: a first name and four dots
    # is how LinkedIn's export writes some people, and the dots were taken for the surname,
    # which slugged to nothing and stopped contact_id (2026-10-23).
    tokens = [t for t in tokens if _bare(t) not in _HONORIFICS and any(ch.isalnum() for ch in t)]
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
# married name, a reversed "Halloway, Wren" and a change of employer. Any host
# (www., ca., uk., none), the phone site's /m/in/ and /mwlite/in/, a trailing slash,
# a query and either spelling of an accented letter (%C3%A9 or é, composed or not) all
# give one handle: the forms other readers of these addresses accept too (2026-10-23).
_PROFILE_HANDLE = re.compile(r"linkedin\.com/(?:(?:m|mwlite)/)?in/([^/?#\s]+)", re.I)


def profile_handle(url: str | None) -> str:
    """The /in/<handle> of a LinkedIn profile URL, lowercased and decoded, or ""."""
    import unicodedata
    from urllib.parse import unquote
    m = _PROFILE_HANDLE.search(str(url or ""))
    return unicodedata.normalize("NFC", unquote(m.group(1))).strip().lower() if m else ""


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

    The id names the person's folder in documents/network/, so it is a name Windows
    accepts too: with no employer, "Wren Con" was `con`, a folder Windows refuses, and a
    repo holding it could not be checked out there (`safe_name.windows_safe`).
    """
    sn = _slug(surname(name))
    if not sn:
        raise ValueError(f"contact_id needs a name with a surname in it, got {name!r}")
    ck = _slug(company_key(company))
    if ck:
        return windows_safe(f"{ck}_{sn}")
    # With no employer the surname is the whole id, and a one-letter surname
    # makes it useless: "Robin S" and "Quinn S" both became "s". Recruiter
    # contacts can arrive this way, initial only and no company named. Fall back to
    # the full name so the id still identifies somebody.
    if len(sn) < 2:
        full = _slug(name)
        if full:
            return windows_safe(full)
    return windows_safe(sn)


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
    """The employer identity of a contact row: `company_key.row_key`, shared with the throttle."""
    return _ck_row_key(row)


def _match_name(name: str | None) -> str:
    return _slug(person_name(name))


def first_degree(path=None) -> list:
    """The person's own LinkedIn connections, from LinkedIn's data export, or [].

    LinkedIn's data export (tools/claude_surfaces.json, linkedin-connections) writes
    Connections.csv with a few lines of notes above the header, so the header is found
    rather than assumed to be line one. Saved into documents/linkedin/ by `sources.py
    import-connections`, it is the one source of who the person is already connected
    with, which no search can see. Read through `export.read()`, the one reader for every
    export file, so a header in another case or spacing is read too.
    """
    import zipfile
    import export
    path = path or person.local_state("documents", "linkedin", "Connections.csv")
    try:
        got = export.read("connections", path)
    except (OSError, ValueError, zipfile.BadZipFile):
        return []
    if not got["usable"]:
        return []
    out = []
    for row in got["rows"]:
        name = " ".join(x for x in (row.get("First Name"), row.get("Last Name")) if x).strip()
        if not name:
            continue
        out.append({"name": name, "linkedin_url": row.get("URL") or "",
                    "company": row.get("Company") or "", "title": row.get("Position") or "",
                    "connected_on": row.get("Connected On") or ""})
    return out


def connections_at(connections, company) -> list:
    """The person's 1st-degree connections at one employer: the first people to message.

    The employer under any of its names: a connection whose export says "<Name>
    Ratings" works for <Name> (discovery.same_employer)."""
    import discovery
    if not company_key(company):
        return []
    return [c for c in connections or () if discovery.same_employer(c.get("company"), company)]


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


# ---------------------------------------------------------------- possible duplicates

# One person, two rows. `already_contacted` matches the name exactly, so beside "Robert
# Smith" at one employer a nickname ("Bob"), an initial ("R."), a surname-first listing,
# a middle initial and a one-letter typo of the surname were five strangers, and the
# rule that nobody already contacted is
# surfaced again rested on how a search snippet happened to spell them. The rows from a
# web search carry no LinkedIn address, which is the one thing that would have told.
#
# A warning, never a merge: the message log hangs off contact_id, and a wrong merge
# would give one person's thread to another in the one file that must not be lost.
#
# Surnames this close are one letter apart ("Smyth", "Smith"). Short ones are left out:
# "Chen" and "Cheng" are two families, not a typo.
TYPO_RATIO = 0.8
TYPO_MIN_LETTERS = 5
# Written in either row's notes, a pair somebody has checked is never raised again.
_NOT_SAME = re.compile(r"\bnot the same (?:person|one) as\s+([\w.-]+)|\bdifferent (?:person|people) "
                       r"(?:from|to|than)\s+([\w.-]+)", re.I)
_GENERATION = re.compile(r"\b(jr|sr|ii|iii)\b\.?", re.I)


def same_given_name(a: str, b: str) -> bool:
    """Is one given name the other, or a short form of it (Bob and Robert)? tone's table."""
    import tone
    return tone.same_given_name(_bare(a), _bare(b))


def _name_parts(name) -> tuple:
    """(given, middles, surname, generation) of a name, a "Smith, Robert" listing turned round."""
    raw = _TRAILER.split(_PAREN.sub(" ", str(name or "")))[0]
    head, comma, tail = raw.partition(",")
    tail_tokens = [t for t in tail.split(",")[0].split() if _bare(t)]
    if (comma and len(head.split()) == 1 and 1 <= len(tail_tokens) <= 2
            and not any(_bare(t) in _SUFFIXES | _HONORIFICS for t in tail_tokens)):
        raw = " ".join(tail_tokens + head.split())
    gen = {m.group(1).lower() for m in _GENERATION.finditer(raw)}
    tokens = [_bare(t) for t in person_name(raw).split()]
    tokens = [t for t in tokens if t and t not in _SUFFIXES]
    if len(tokens) < 2:
        return ("", (), tokens[0] if tokens else "", gen)
    return (tokens[0], tuple(tokens[1:-1]), tokens[-1], gen)


def _why_same(a, b) -> tuple:
    """(how sure, the reason) two names at one employer may be one person, or ("", "")."""
    import difflib
    (fa, ma, la, ga), (fb, mb, lb, gb) = _name_parts(a), _name_parts(b)
    if not fa or not fb or not la or not lb:
        return "", ""                    # a single name is too little to call anybody
    if ga != gb and ga and gb:
        return "", ""                    # a Jr and a Sr: two people, likely related
    initial = (len(fa) == 1 or len(fb) == 1) and fa[0] == fb[0]
    given = same_given_name(fa, fb)
    if la == lb:
        if fa == fb and ma != mb:
            return "likely", "a middle name is the only difference"
        if fa == fb:
            turned = ("," in str(a or "")) != ("," in str(b or ""))
            return "likely", ("the same name, one written surname first" if turned
                              else "the same name twice")
        if given:
            return "likely", f"{fa.title()} and {fb.title()} are one given name"
        if initial:
            return "likely", f"{(fa if len(fa) == 1 else fb).upper()}. could be " \
                             f"{(fb if len(fa) == 1 else fa).title()}"
        return "", ""
    if (given or initial) and min(len(la), len(lb)) >= TYPO_MIN_LETTERS \
            and difflib.SequenceMatcher(None, la, lb).ratio() >= TYPO_RATIO:
        return "possible", f"{la.title()} and {lb.title()} differ by about a letter"
    return "", ""


def _checked_apart(x, y) -> bool:
    """Does either row's notes say it is not the same person as the other?"""
    for row, other in ((x, y), (y, x)):
        theirs = str(other.get("contact_id") or "").strip().lower()
        for m in _NOT_SAME.finditer(" ".join(str(row.get(k) or "") for k in ("notes", "outcome"))):
            if theirs and (m.group(1) or m.group(2) or "").strip(".").lower() == theirs:
                return True
    return False


def possible_duplicates(contacts) -> list[dict]:
    """Rows at one employer that may be one person, each with its reason. Never merged.

    [{"contact_ids": (...), "names": (...), "company": ..., "sure": "likely" | "possible"
    | "check", "reason": "..."}]. "likely": the same surname and a nickname ("Bob" for
    "Robert"), an initial ("R."), a middle name or a name written back to front;
    "possible": the same given name and a surname about a letter off ("Smyth"). Three or
    more rows that may be one person come back once, as "check", to look at by hand.
    Two different LinkedIn addresses are two people, whatever the names say, and a pair
    whose notes say "not the same person as <id>" is never raised again.
    """
    by_key: dict = {}
    for row in contacts or ():
        if isinstance(row, dict) and row_company_key(row):
            by_key.setdefault(row_company_key(row), []).append(row)
    out = []
    for rows in by_key.values():
        pairs = []
        for i, x in enumerate(rows):
            for y in rows[i + 1:]:
                hx, hy = profile_handle(x.get("linkedin_url")), profile_handle(y.get("linkedin_url"))
                if hx and hy and hx != hy:
                    continue
                if hx and hx == hy:
                    sure, why = "likely", "the same LinkedIn profile"
                else:
                    sure, why = _why_same(x.get("name"), y.get("name"))
                if sure and not _checked_apart(x, y):
                    pairs.append((x, y, sure, why))
        # A person in three rows, or three people one rule cannot tell apart: by hand.
        root = {id(r): id(r) for r in rows}

        def top(k, root=root):
            while root[k] != k:
                k = root[k]
            return k
        for x, y, _s, _w in pairs:
            root[top(id(x))] = top(id(y))
        groups: dict = {}
        for r in rows:
            groups.setdefault(top(id(r)), []).append(r)
        seen = set()
        for x, y, sure, why in pairs:
            group = groups[top(id(x))]
            if len(group) > 2:
                if top(id(x)) in seen:
                    continue
                seen.add(top(id(x)))
                out.append({"contact_ids": tuple(r.get("contact_id", "") for r in group),
                            "names": tuple(r.get("name", "") for r in group),
                            "company": group[0].get("company", ""), "sure": "check",
                            "reason": "%d rows here may be one person; check them by hand"
                                      % len(group)})
                continue
            out.append({"contact_ids": (x.get("contact_id", ""), y.get("contact_id", "")),
                        "names": (x.get("name", ""), y.get("name", "")),
                        "company": x.get("company", ""), "sure": sure, "reason": why})
    return out


def possible_match(contacts, name, company, linkedin_url=None) -> dict | None:
    """Before a row is added: the row already in the book that may be this person, or None.

    `already_contacted` answers for the same name; this answers for a nickname, an
    initial, a middle name, a reversed listing or a letter's typo at the same employer,
    so discovery asks "is this the Robert Smith already in the book?" instead of adding a
    second row. {"row": <the row>, "sure": ..., "reason": ...}. Never a merge.
    """
    if already_contacted(contacts, name=name, company=company, linkedin_url=linkedin_url):
        return None
    want = profile_handle(linkedin_url)
    for row in contacts_at(contacts, company):
        theirs = profile_handle(row.get("linkedin_url"))
        if want and theirs and want != theirs:
            continue
        sure, why = _why_same(name, row.get("name"))
        if sure:
            return {"row": row, "sure": sure, "reason": why}
    return None


def duplicate_line(found, this_id="") -> str:
    """What `possible_duplicates` or `possible_match` found, said plainly, with what to do.

    `this_id` is the row the line is written against, left out of the people it names.
    """
    row = found.get("row") or {}
    ids = list(found.get("contact_ids") or (str(row.get("contact_id") or ""),))
    names = list(found.get("names") or (str(row.get("name") or ""),))
    others = [(n, i) for n, i in zip(names, ids) if i and i != this_id] or [("", this_id)]
    who = ", ".join("%s (%s)" % (n, i) if n else i for n, i in others)
    return ("may be the same person as %s: %s. Never merged. If it is one person, close the "
            "newer row (state.py set <its id> --status closed --note \"the same person\") "
            "and keep the one that holds the messages; if not, write "
            "\"not the same person as %s\" in this row's notes."
            % (who, found.get("reason", ""), others[0][1]))


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
    "open profile": "open_profile", "open-profile": "open_profile", "openprofile": "open_profile",
    "e-mail": "email", "mail": "email",
    "introduction": "intro", "warm intro": "intro", "warm_intro": "intro",
}


def direction(row) -> str:
    d = str(row.get("direction") or "").strip().lower()
    if d in _OUT:
        return "out"
    if d in _IN:
        return "in"
    return ""


_direction = direction  # the module's own name for it; other modules call direction


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


def _scenario(row) -> str:
    return re.sub(r"[\s-]+", "_", str(row.get("scenario") or "").strip().lower())


def is_acceptance(row) -> bool:
    """Is this row an accepted connection request rather than a message?"""
    return _direction(row) == "in" and _scenario(row) in ACCEPTED_SCENARIOS


# A connection request is not a message that can be followed up. Until it is
# accepted there is no channel to write in: ten contacts with one unaccepted
# request each showed "[nudge] 21bd" in a real contact book, a message nobody
# could send. Read from the scenario, or from a channel typed as a request.
REQUEST_SCENARIOS = frozenset({"connection_request", "connection_requested", "connection_note",
                               "invite", "invitation", "connect_request", "request_outside"})
# A request the person sent from LinkedIn itself, seen later as Pending: whether it
# carried a note is not known, so it is never taken for a bare request (which would
# owe a first message on acceptance, perhaps a second one).
OUTSIDE_SCENARIO = "request_outside"
# A pending request is worth withdrawing after this long: LinkedIn caps how many
# can be outstanding, and one nobody accepted in three weeks rarely is.
REQUEST_WITHDRAW_DAYS = 21
# Owed this long with nothing done, a thread has ended: the throttle's 45 days of silence,
# where the reading queue also stops counting an unanswered note. A LinkedIn download
# brings in years of conversations, and every one where the other side wrote last read as
# a reply owed today: one person's due list went from 24 overdue to 655 the day their
# history came in (2026-10-23), a five-year-old message at the top. Such an item is still
# in `owed`, marked `old`, and /threads still lists it; the due list counts it in one line
# instead. A date the person put on the row themselves keeps it live.
OLD_OWED_DAYS = _THROTTLE_SILENCE_DAYS


def owed_too_long(since, today) -> bool:
    """Owed since `since` for more than OLD_OWED_DAYS: a thread that has ended."""
    since, today = as_date(since), as_date(today)
    return since is not None and today is not None and (today - since).days > OLD_OWED_DAYS


def dated_by_person(contact, msgs=None) -> bool:
    """A date the person put on the row themselves: a next_action_due beside words of their
    own, beside no words at all (`state.py set <id> --due <date>`), or beside the app's own
    follow-up wording but on a day the app would not have written on this thread (`_app_dates`,
    from `msgs`; without them, the app's words are taken as the app's date)."""
    due = as_date(contact.get("next_action_due"))
    if due is None:
        return False
    action = (contact.get("next_action") or "").strip()
    if not action or not _APP_ACTION.fullmatch(action):
        return True
    return msgs is not None and due.isoformat() not in _app_dates(msgs, action)


def is_request(row) -> bool:
    """An outbound connection request, with or without a note."""
    if _direction(row) != "out":
        return False
    raw = str(row.get("channel") or "").lower()
    return _scenario(row) in REQUEST_SCENARIOS or "request" in raw or "invit" in raw


def is_bare_request(row) -> bool:
    """A connection request that carried no note: it said nothing."""
    return (is_request(row) and not str(row.get("full_text") or "").strip()
            and _scenario(row) != OUTSIDE_SCENARIO)


# A connection request taken back (`withdraw`). Not a message: nothing reached them,
# so it is never a reply to wait on, a nudge, a request spent or an opener to learn
# from. It closes what was waiting on them, and the log says so where the contact row
# has not caught up. Without it the withdrawal was nowhere: the request stayed listed
# as one to withdraw, and the person could be found and written to again.
WITHDRAWN_SCENARIOS = frozenset({"request_withdrawn", "withdrawn_request", "withdrew_request"})


def is_withdrawal(row) -> bool:
    """Is this row a connection request taken back, rather than a message?"""
    return _direction(row) == "out" and _scenario(row) in WITHDRAWN_SCENARIOS


# A call is not a message either. Logged as `channel=call` with `scenario=call_held`
# after a reply, it read as our message last, so the thread came out
# `awaiting_reply` and the nudge clock said "30 business days of silence" about a
# conversation that had just happened. A held call is an exchange; a missed or
# cancelled one is nothing.
CALL_CHANNELS = frozenset({"call", "phone", "video", "teams", "zoom", "meet", "calendly",
                           "meeting", "coffee", "in_person", "in person"})
CALL_EVENTS = frozenset({"call_held", "call_completed", "call_missed", "call_cancelled",
                         "meeting_held", "met"})
CALL_NOT_HELD = frozenset({"call_missed", "call_cancelled"})


def is_call(row) -> bool:
    """A call or meeting logged in the thread, held or not: never a message."""
    return channel_of(row) in CALL_CHANNELS or _scenario(row) in CALL_EVENTS


def call_held(row) -> bool:
    return is_call(row) and _scenario(row) not in CALL_NOT_HELD


# ---------------------------------------------------------------- automatic replies

# An out-of-office or other automatic reply is logged inbound like a message, and read
# by direction alone it was one. "I am out of the office until 20 October" derived
# `replied_needs_response`: a warm route in `throttle.RESPONDED`, so the employer read
# "DO NOT APPLY COLD", a reply was owed to a mailbox nobody was reading, and the nudge
# the thread did need was refused because "they answered". Nobody has said anything:
# status, warmth, what is owed and what drew a reply all read past it. Logged with one of
# these scenarios, or recognised from its words, it is never a reply.
AUTO_REPLY_SCENARIOS = frozenset({"auto_reply", "autoreply", "automatic_reply",
                                  "out_of_office", "ooo"})

# The message says a machine sent it. Enough on its own. A few languages, kept small:
# the subject prefix mail programs write and the phrase their bodies open with.
_AUTO_SAYS = re.compile(
    r"\bautomatic(?:ally generated)? (?:reply|response|message)\b|\bauto[- ]?(?:reply|response)\b"
    r"|\bautomated (?:reply|response|message)\b|^\s*(?:out of (?:the )?office|ooo)\s*:"
    r"|\bthis (?:mailbox|inbox|e-?mail address) is (?:not|no longer) (?:monitored|in use|checked)\b"
    r"|\babwesenheitsnotiz\b|\bautomatische antwort\b"          # German
    r"|\br[ée]ponse automatique\b|\bmessage d'absence\b"         # French
    r"|\brespuesta autom[áa]tica\b|\bresposta autom[áa]tica\b"  # Spanish, Portuguese
    r"|\brisposta automatica\b"                                  # Italian
    r"|\bautomatisch antwoord\b|\bafwezigheidsmelding\b"         # Dutch
    r"|\bautomatiskt svar\b|\bautosvar\b",                       # Swedish, Norwegian, Danish
    re.I | re.M)

# "I am out of the office". A person writes the same words in a real reply ("I'm out of
# the office until Monday, but happy to chat then"), so this counts only beside a second
# sign of the template (a return date, limited access, "on my return", urgent matters to
# someone else) and only in a message that asks and offers nothing.
_AWAY = re.compile(
    r"\b(?:i am|i'm|i will be|i'll be)\s+(?:currently\s+|now\s+)?(?:out of (?:the )?office"
    r"|away from (?:the|my) (?:office|desk|e-?mail)|away|on (?:annual |parental |maternity |"
    r"paternity |sick |study )?leave|on holiday|on vacation|out of office)\b"
    r"|\bich bin\b[^.\n]{0,30}\b(?:nicht im b[üu]ro|abwesend)\b|\bje suis absente?\b"
    r"|\bestoy fuera de la oficina\b|\bsono fuori (?:ufficio|sede)\b|\bik ben\b[^.\n]{0,25}\bafwezig\b",
    re.I)
_TEMPLATE = re.compile(
    r"\b(?:until|till|returning|return(?:ing)? on|back (?:in the office )?on|back on)\b"
    r"|\bwith (?:limited|no|intermittent) access to\b|\b(?:on|upon) my return\b"
    r"|\bwhen i (?:am back|return|get back)\b|\bfor (?:urgent|anything urgent)\b|\burgent (?:matters|queries|requests)\b"
    r"|\bbis\b|\bjusqu'au\b|\bhasta el\b|\bfino al\b|\btot en met\b", re.I)
# A message with these in it is a person talking, whatever else it says. An offer made
# for later counts ("I'll pass your profile to our recruiter"): out of the office with a
# promise in it was read as an automatic reply, so nobody thanked the person advocating
# (2026-10-21).
#
# So does an answer to what was asked, beside a mention of leave (networking audit,
# 2026-10-25): "Thanks Morgan, I'm on parental leave until January, so not the best person
# to ask. Try Bo Venn" was read as an out-of-office, the reply was hidden and a nudge was
# offered. A template knows neither the reader's name nor what they asked, so these count:
# a greeting by a first name, a no ("isn't hiring", "not interested"), a person to try by
# name, and a promise about what was sent ("I'll take a look at your profile"). A template's
# own redirect ("for urgent matters please contact ...") and its promise to answer email on
# return ("I will respond when I am back") are not among them.
_NAME = r"(?-i:[A-Z][a-z]+(?:[ -][A-Z][a-z'-]+)?)"
_NOT_A_NAME = (r"(?!(?-i:Sender|Sir|Madam|Customer|Colleagues?|All|Team|Everyone|There|Valued|"
               r"Recipient|Thanks?|Thank|Hiring|Candidate|Friend|Again|Later|Back)\b)")
_ENGAGED = re.compile(
    r"\?|\b(?:happy|glad|keen|love|delighted) to\b|\blet'?s\b|\bworks for me\b|\bsounds good\b"
    r"|\bsend (?:me|over|it|your)\b|\bi(?:'ve| have) (?:passed|shared|forwarded|sent)\b"
    r"|\bi(?:'ll| will| can| could)(?: happily| gladly| certainly| definitely)? (?:pass|forward|"
    r"share|introduce|ask|send|connect you|put you in touch|flag|mention|refer)\b"
    # a greeting by name, the way a person opens and a template cannot
    r"|\A\W*(?:hi|hey|hello|dear|thanks|thank you|cheers)[ ,!-]+" + _NOT_A_NAME + _NAME + r"\b"
    # a no
    r"|\b(?:(?:is|are|am)n'?t|(?:is|are|am)\s+not|not)\s+(?:currently\s+|really\s+|actively\s+)?"
    r"(?:hiring|recruiting|interested)\b|\bnot the (?:best|right) (?:person|contact|one)\b"
    r"|\bno thanks\b|\bno,? thank you\b|\b(?:can'?t|cannot|won'?t be able to) help\b"
    r"|\b(?:no|nothing)\s+(?:open|available|suitable|coming up|roles?|openings?|vacanc(?:y|ies)|"
    r"positions?|headcount)\b|\bgood luck\b"
    # a person to try, by name
    r"|\btry\s+" + _NOT_A_NAME + _NAME + r"\b|\b(?:speak|talk|chat)\s+(?:to|with)\s+" + _NOT_A_NAME
    + _NAME + r"\b|" + _NAME + r"\s+(?:runs|leads|heads|manages|handles|owns|does|is (?:running|"
    r"leading|handling|doing|in charge of))\s+(?:the\s+|our\s+|their\s+)?(?:hiring|recruit\w*)\b"
    r"|\b(?:she|he|they)(?:'s| is| are|'re)\s+(?:the one\s+)?(?:hiring|recruiting)\b"
    # a promise about what was sent, not about answering email
    r"|\b(?:take|have) a (?:look|read)\b|\blook (?:at|over|through) your\b"
    r"|\bi(?:'ll| will) (?:think about|consider|keep (?:you|an eye))\b", re.I)
# Gone: the address no longer reaches them. Third person only, the way the template
# writes it, and about a person: a name, a pronoun or "this person" as the subject. "I am
# no longer at Acme" is them, writing, and reply.py reads that; "our team is no longer part
# of the Manchester office" is a person explaining, and was read as the template.
_SUBJECT_OF_LEFT = (r"(?:\b(?:[Hh]e|[Ss]he|[Tt]hey)\s+"
                    r"|\b(?P<who>(?!(?:We|I|You|It|Our|My|Your|This|That|There|The)\b)[A-Z][\w'-]+"
                    r"(?: [A-Z][\w'-]+){0,2})\s+"
                    # "The person you are trying to reach is no longer with ...": a person
                    # named by their place in the template, anywhere in the sentence.
                    r"|(?i:\b(?:person|employee|individual|recipient|colleague|team member|"
                    r"staff member|user|addressee)\b)[^.!?\n]{0,60}?\s)")
_LEFT = re.compile(_SUBJECT_OF_LEFT + r"(?i:(?:is|are) no longer (?P<how>with|at|employed (?:by|at)|"
                   r"working (?:for|at)|part of)\b|has left (?:the (?:company|firm|business|"
                   r"organi[sz]ation|team)))")
# A capitalised subject that is an organisation, not a person: "Fernhill Freight is no
# longer part of the Brindle group, so I'm not sure I can help" is a person explaining,
# and was read as the "no longer with us" template, so nothing was drafted and the decline
# was never counted (2026-10-21). An organisation by a word in its name, by the group it
# is "no longer part of", or by being an employer in the contact book.
_ORG_WORD = re.compile(
    r"\b(?:group|holdings|ltd|limited|inc|llc|llp|plc|corp|corporation|company|co|gmbh|bank|"
    r"partners|partnership|team|office|department|division|unit|business|firm|agency|fund|"
    r"trust|foundation|council|authority|ministry|university|college|school|hospital|"
    r"services|solutions|technologies|technology|software|insurance|international|global|"
    r"labs?|systems)\b", re.I)
_ORG_OBJECT = re.compile(r"\s*(?:the|a|an|our|its)\s+[^.!?\n]{0,40}?\b(?:group|family|portfolio|"
                         r"network|alliance|business|brand|parent|company)\b", re.I)
_BOOK_EMPLOYERS: dict = {}


def _book_employers() -> set:
    """The employer keys in the contact book, read once per change to it; never raises."""
    p = person.state("network_contacts.csv")
    try:
        stamp = os.path.getmtime(p)
    except OSError:
        return set()
    if _BOOK_EMPLOYERS.get("key") != (p, stamp):
        try:
            import csv_store
            rows = csv_store.read_rows(p)
        except Exception:  # noqa: BLE001  an unreadable book: judged on the words alone
            rows = []
        _BOOK_EMPLOYERS.update(key=(p, stamp), keys={k for k in (row_company_key(r)
                                                                 for r in rows) if k})
    return _BOOK_EMPLOYERS.get("keys") or set()


def _an_organisation(m, words) -> bool:
    """Is the capitalised subject of this "no longer with" match an organisation?"""
    who = m.group("who")
    if not who:
        return False
    if _ORG_WORD.search(who):
        return True
    if (m.group("how") or "").lower() == "part of" and _ORG_OBJECT.match(words, m.end()):
        return True
    k = company_key(who)
    return bool(k) and k in _book_employers()


def _left(words):
    """The "no longer with" template's sentence about a person, or None."""
    for m in _LEFT.finditer(words):
        if not _an_organisation(m, words):
            return m
    return None

_MONTHS = {m: i for i, names in enumerate((
    ("jan", "january"), ("feb", "february"), ("mar", "march"), ("apr", "april"), ("may",),
    ("jun", "june"), ("jul", "july"), ("aug", "august"), ("sep", "sept", "september"),
    ("oct", "october"), ("nov", "november"), ("dec", "december")), 1) for m in names}
_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_MONTH_RX = "|".join(sorted(_MONTHS, key=len, reverse=True))
_BACK_ON = re.compile(
    r"\b(?:until|till|returning(?: on)?|return(?:ing)? on|back(?: in the office)?(?: on)?"
    r"|will (?:be )?(?:back|return)(?: on)?|from)\s+(?:the\s+)?"
    r"(?:(?P<iso>\d{4}-\d{2}-\d{2})"
    r"|(?:(?P<wd>" + "|".join(_WEEKDAYS) + r")\b,?\s*)?"
    r"(?:(?P<d1>\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?(?P<m1>" + _MONTH_RX + r")\b\.?"
    r"|(?P<m2>" + _MONTH_RX + r")\b\.?\s+(?P<d2>\d{1,2})(?:st|nd|rd|th)?\b)?"
    r"(?:,?\s*(?P<y>\d{4}))?)", re.I)


def _back_on(text: str, sent_on) -> datetime.date | None:
    """The day an away message says they are back, or None when it says none it can read.

    ISO dates, "20 October", "October 20th", a weekday ("until Monday", the first one
    after the message). A day and month with no year is the first such day on or after
    the message. Numeric 20/10 is read as nothing: it is 20 October or a typo for 10/20.
    """
    sent_on = as_date(sent_on)
    for m in _BACK_ON.finditer(str(text or "")):
        if m.group("iso"):
            got = as_date(m.group("iso"))
            if got:
                return got
            continue
        month = (m.group("m1") or m.group("m2") or "").lower()
        day = m.group("d1") or m.group("d2")
        if month and day:
            year = int(m.group("y")) if m.group("y") else (sent_on.year if sent_on
                                                             else datetime.date.today().year)
            try:
                got = datetime.date(year, _MONTHS[month], int(day))
            except ValueError:
                continue
            if not m.group("y") and sent_on and got < sent_on - datetime.timedelta(days=7):
                got = got.replace(year=got.year + 1)
            return got
        if m.group("wd") and sent_on:
            ahead = (_WEEKDAYS.index(m.group("wd").lower()) - sent_on.weekday()) % 7 or 7
            return sent_on + datetime.timedelta(days=ahead)
    return None


def auto_reply(text, subject="", sent_on=None) -> dict | None:
    """What an inbound message is, when no person wrote it: None for a message from a person.

    {"kind": "automatic" | "away" | "left", "back_on": date or None, "evidence": "..."}.
    "left" is a template saying they are no longer there; "away" an out-of-office;
    "automatic" any other message that says a machine sent it.
    """
    args = (str(text or ""), str(subject or ""), sent_on)
    try:
        # Without a send date the year comes from today, so that reading is never kept.
        got = _auto_reply(*args) if sent_on is not None else _auto_reply.__wrapped__(*args)
    except TypeError:                      # a sent_on that cannot be a cache key
        got = _auto_reply.__wrapped__(*args)
    return dict(got) if got else None


@functools.lru_cache(maxsize=16384)
def _auto_reply(body, subject, sent_on):
    """auto_reply's reading, kept per message: one run reads the same message for the
    status, the owed list and the resume list."""
    words = "%s\n%s" % (subject or "", body)
    left = _left(words)
    said = _AUTO_SAYS.search(words)
    away = _AWAY.search(words)
    if left and (said or not _ENGAGED.search(body)):
        return {"kind": "left", "back_on": None, "evidence": left.group(0).strip()}
    if said:
        return {"kind": "away" if away else "automatic",
                "back_on": _back_on(words, sent_on), "evidence": said.group(0).strip()}
    if away and _TEMPLATE.search(words) and not _ENGAGED.search(body):
        return {"kind": "away", "back_on": _back_on(words, sent_on),
                "evidence": away.group(0).strip()}
    return None


@functools.lru_cache(maxsize=1)
def _person_scenarios() -> frozenset:
    """The scenarios /reply reads a person's message as (reply.SCENARIOS), automatic replies
    left out. A row logged as one of them was read as a person, and that wins over its
    words: "referral_offered" on a message that also mentions leave is a referral offered."""
    try:
        import reply
    except ImportError:  # the reader is beside this file; never without it in the app
        return frozenset()
    return frozenset(reply.SCENARIOS) - AUTO_REPLY_SCENARIOS - {"gone_quiet"}


def is_auto_reply(row) -> bool:
    """Is this inbound row an automatic reply (an out-of-office, a "no longer here") and not them?"""
    if _direction(row) != "in":
        return False
    if _scenario(row) in AUTO_REPLY_SCENARIOS:
        return True
    if _scenario(row) in _person_scenarios():
        return False
    return auto_reply(row.get("full_text") or row.get("summary"), row.get("subject"),
                      row.get("date")) is not None


def away_until(rows) -> datetime.date | None:
    """The return date of an away message that came after our last message, or None.

    The nudge waits for it: one sent into an inbox nobody reads until the 20th is the
    one nudge the thread gets, spent.
    """
    back = None
    for row in _ordered([r for r in rows if _direction(r)]):
        if is_auto_reply(row):
            got = auto_reply(row.get("full_text") or row.get("summary"), row.get("subject"),
                             row.get("date"))
            back = (got or {}).get("back_on") or back
        elif _direction(row) == "out" or said_something(row):
            back = None
    return back


# Two working days after they are back before the nudge, for the inbox they come back to.
AWAY_GRACE_BUSINESS_DAYS = 2


def said_something(row) -> bool:
    """An inbound row that is a message: the only kind that makes a route warm."""
    return (_direction(row) == "in" and not is_acceptance(row) and not is_call(row)
            and not is_auto_reply(row))


def they_spoke_last(rows) -> bool:
    """Is the last word on this thread theirs? The one answer /reply and the follow-up log
    share. Acceptances and automatic replies say nothing either way; anything else,
    a message out, a call, is the last word when it comes last. Reading "they ever
    replied" as "they spoke last" refused a due nudge, and the chase it sent the person
    to log another way set up a second one (2026-10-21)."""
    spoken = [r for r in _ordered([r for r in rows if _direction(r)])
              if not is_acceptance(r) and not is_auto_reply(r)]
    return bool(spoken) and said_something(spoken[-1])


def request_pending(rows) -> datetime.date | None:
    """The date of a connection request still waiting to be accepted, or None.

    The latest thing on the thread decides: an acceptance, anything they said,
    a call, or a message sent after the request (an InMail or an email reaches
    them without one) all mean the request is no longer what is waiting.
    """
    for row in reversed(_ordered([r for r in rows if _direction(r) and not is_auto_reply(r)])):
        if is_request(row):
            return as_date(row.get("date")) or datetime.date.min
        return None
    return None


def accepted_never_messaged(rows) -> datetime.date | None:
    """The acceptance date when only bare requests went before it and nothing after.

    Somebody who accepted a request that carried no note has been told nothing,
    so what is owed is a first message, written as one, not a nudge on a note
    that was never sent.
    """
    ordered = _ordered([r for r in rows if _direction(r) and not is_call(r)
                        and not is_auto_reply(r)])
    if not ordered or not is_acceptance(ordered[-1]):
        return None
    before = ordered[:-1]
    if any(_direction(r) == "in" and not is_acceptance(r) for r in before):
        return None
    sent = [r for r in before if _direction(r) == "out"]
    if sent and all(is_bare_request(r) for r in sent):
        return as_date(ordered[-1].get("date")) or datetime.date.min
    return None


def threads_for(threads, contact_id_value) -> list[dict]:
    """Every message row for one contact, in the order they happened."""
    want = str(contact_id_value or "").strip()
    return _ordered([r for r in threads
                     if str(r.get("contact_id") or "").strip() == want])


def by_contact(threads) -> dict[str, list[dict]]:
    """Every contact's message rows, in the order they happened: `threads_for` for all of
    them in one pass over the log. A loop over the book reads `by_contact(threads).get(cid,
    [])` once instead of `threads_for` per contact, which read the whole log once a
    contact: 3,900 passes over 8,500 messages, most of `open_actions.py --due`'s 5 seconds
    on 1,300 contacts (2026-10-23). The same rows in the same order, as copies, so a caller
    that changes its list changes nobody else's."""
    grouped: dict[str, list] = {}
    for r in threads or ():
        grouped.setdefault(str(r.get("contact_id") or "").strip(), []).append(r)
    return {cid: _ordered(rows) for cid, rows in grouped.items()}


def _rows_of(index, cid) -> list[dict]:
    return list(index.get(str(cid or "").strip(), ()))


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

    An automatic reply (`is_auto_reply`: an out-of-office, a "no longer here") is
    nothing at all: nobody read the message, so the thread waits exactly as before.

    An acceptance is neither. It moves a thread that is waiting on them to
    `connected_no_reply`, which stays until they actually write, and it answers
    nothing: accepting after writing leaves the reply owed where it was.

    A withdrawn request (`withdraw`) closes a thread that was waiting on them:
    `closed`, which the log can say only this way. Anything they say after it
    reopens the thread as a reply owed.
    """
    status = "not_contacted"
    for row in _ordered(threads_for_contact):
        if not _direction(row) or is_auto_reply(row):
            continue
        if is_withdrawal(row):
            # The request they never accepted is gone, and with it the thread.
            if status in ("not_contacted", "awaiting_reply"):
                status = "closed"
            continue
        if is_call(row):
            if call_held(row):
                status = "in_conversation"
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
        if stored in REOPENED_BY_A_REPLY and reopened(contact, thread_rows, derived):
            return derived
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


# A close the person chose, written into the row. Without it, a thread closed
# after reading their last reply was reported as "reopened" on every run. A close
# a session made by mistake carries no such words, so it is still reported.
CLOSED_ON_PURPOSE = re.compile(r"\b(?:closed on purpose|closed deliberately|deliberately "
                               r"closed|do not reopen|don'?t reopen)\b", re.I)


_DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_NEAR_CLOSE = re.compile(r"(?:closed|deprioriti[sz]ed|not answered|dead end)[^\n|]{0,80}?"
                         r"(\d{4}-\d{2}-\d{2})|(\d{4}-\d{2}-\d{2})[^\n|]{0,40}?"
                         r"(?:closed|deprioriti[sz]ed|dead end)", re.I)


def closed_on(contact) -> datetime.date | None:
    """When the thread was closed, from the row: a date in `outcome`, or beside "closed"."""
    dates = [as_date(d) for d in _DATE.findall(str(contact.get("outcome") or ""))]
    for k in ("notes", "next_action"):
        for m in _NEAR_CLOSE.finditer(str(contact.get(k) or "")):
            dates.append(as_date(m.group(1) or m.group(2)))
    dates = [d for d in dates if d]
    return max(dates) if dates else None


# The one closed status a message from them undoes by itself: gone_cold says nobody
# answered, and an answer makes it untrue. A late reply to a thread gone cold was never owed:
# the status was terminal whatever the log said, so the due list read "0 replies owed" while
# they waited for an answer (networking audit, 2026-10-25). `received` reopened it; a reply
# the LinkedIn download brought, or a row logged by hand, did not. closed, dropped and
# converted_to_application are the person's decisions, and a late message there is reported
# by reconcile ("reopened") for them to judge.
REOPENED_BY_A_REPLY = frozenset({"gone_cold"})


def reopened(contact, rows, derived=None) -> bool:
    """Have they written since this thread was closed? Their message is the last word, the
    close was not marked on purpose, and it is not dated on or after their last message."""
    if derived is None:
        derived = derive_status(rows)
    return (derived == "replied_needs_response"
            and not CLOSED_ON_PURPOSE.search(" ".join(
                str(contact.get(k) or "") for k in ("next_action", "notes")))
            and not _closed_after_last_reply(contact, rows))


def _closed_after_last_reply(contact, rows) -> bool:
    """Was the thread closed on or after their last message? Then nothing reopened it.

    Every "reopened" finding on a real contact book was a thread the person closed
    after reading the reply: the close is dated in `outcome` ("... by the candidate
    2026-10-13") and the reply before it. Only a reply after the close reopens.
    """
    closed = closed_on(contact)
    last_in = max((as_date(r.get("date")) for r in rows if said_something(r)
                   and as_date(r.get("date"))), default=None)
    return bool(closed and last_in and last_in <= closed)


def reconcile(contacts, threads, tracker=None) -> list[dict]:
    """Every place the stored state and the message log disagree.

    Only the three statuses in `DERIVABLE` are checked against the log. Flagging
    `call_booked` for disagreeing with `awaiting_reply` would report every healthy
    thread in the book and train the user to skip the output.

    The resume a contact asked for is checked too (`resume_findings`): a message saying
    one went with no file named, a resume the tracker says went to a contact with nothing
    in their thread saying so (only with `tracker`), and a request nothing has answered
    that their row does not record.
    """
    problems = []

    def flag(cid, name, stored, derived, reason, detail=""):
        problems.append({"contact_id": cid, "name": name, "stored": stored,
                         "derived": derived, "reason": reason, "detail": detail})

    known = set()
    index = by_contact(threads)
    for contact in contacts:
        cid = str(contact.get("contact_id") or "").strip()
        known.add(cid)
        name = contact.get("name", "")
        stored = str(contact.get("status") or "").strip()
        rows = _rows_of(index, cid)
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
        elif stored in schema.TERMINAL and reopened(contact, rows, derived):
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
    # same sentence on the same day. The words count too: messages imported from
    # LinkedIn's export carry one summary for a whole day's batch, and two different
    # messages to one person that day read as one logged twice (2026-10-22).
    per_contact = {}
    for row in threads:
        cid = str(row.get("contact_id") or "").strip()
        sig = tuple(str(row.get(k) or "").strip()
                    for k in ("date", "direction", "channel", "scenario", "summary",
                              "full_text"))
        per_contact.setdefault(cid, []).append(sig)
    for cid, sigs in per_contact.items():
        for sig, n in Counter(sigs).items():
            if n > 1:
                flag(cid, _name_of(contacts, cid), "", "", "duplicate_message",
                     "%d identical rows for %s on %s" % (n, sig[1] or "a message", sig[0]))

    # Two rows that may be one person, from a nickname, an initial or a typo: the
    # warning `already_contacted` cannot give, raised on the newer row. Never merged.
    for found in possible_duplicates(contacts):
        newer = found["contact_ids"][-1]
        flag(newer, found["names"][-1], "", "", "possible_duplicate",
             duplicate_line(found, newer))
    problems += resume_findings(contacts, threads, tracker)
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
        if is_acceptance(row) or is_bare_request(row) or is_withdrawal(row) \
                or is_auto_reply(row) or (is_call(row) and not call_held(row)):
            continue
        if _direction(row) != "out" or call_held(row):
            break
        n += 1
    return n


# A next_action that opens by saying nothing is owed. Anchored to the start, the
# way the rows are written, so "no action until they reply" in the middle of a
# longer instruction is not read as one.
NO_REPLY_OWED = re.compile(r"\s*(?:nothing owed|no action|keep warm,? no action)\b"
                           r"(?![^.]*\b(?:unless|until|till|if)\b)", re.I)
# A row that says leave them alone: no nudge, whatever the clock says. "No action
# unless they reply" is the commonest, and it did the opposite twice over: once
# they replied it hid the reply (the condition was met), and while they had not,
# the nudge it was written to stop was offered anyway.
LEAVE_ALONE = re.compile(r"\s*(?:nothing owed|no action|keep warm|background channel|do not "
                         r"(?:chase|nudge|follow up)|don'?t (?:chase|nudge|follow up))\b", re.I)


def _written_since(action, msgs) -> bool:
    """Have they written again since the day a "nothing owed" row was written? The row is
    dated by its first date (`no_reply` writes it so); one with no date is read as before.
    Without this, a row that said nothing was owed hid their next message too."""
    m = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", action or "")
    marked = as_date(m.group(1)) if m else None
    if marked is None:
        return False
    last_in = next((r for r in reversed(_ordered(msgs)) if said_something(r)), None)
    when = as_date(last_in.get("date")) if last_in else None
    return when is not None and when > marked


def no_reply(contacts, threads, who, why, today, look_again=None) -> tuple[dict, str]:
    """Their last message needs no answer ("I'll get back to you next week"): their row says
    so, dated, and gives the day to look again, by the person's own follow-up rule unless
    `look_again` says. The reply owed was never cleared, so the brief asked for one every
    day (2026-10-24). Only until they write again: a later message from them is owed as
    any other. Returns the row and the line to show; raises ValueError where nothing of
    theirs is waiting."""
    day = _need_date(today, "today")
    row = already_contacted(contacts, contact_id=str(who or "").strip()) \
        or already_contacted(contacts, name=who)
    if not row:
        raise ValueError(f"no contact matching {who!r}")
    cid = str(row.get("contact_id") or "").strip()
    msgs = [r for r in threads_for(threads, cid) if _direction(r)]
    if not they_spoke_last(msgs):
        raise ValueError(f"nothing from {row.get('name') or cid} is waiting for an answer: "
                         "the last word on the thread is ours")
    why = " ".join(str(why or "").split()).rstrip(".")
    if not why:
        raise ValueError("say why no answer is needed, in their words or yours (--why)")
    back = _need_date(look_again, "look again") if look_again else follow_up_on(day)
    row["next_action"] = (f"Nothing owed ({day.isoformat()}). {why[:1].upper() + why[1:]}. "
                          f"Look again on {back.isoformat()}.")
    row["next_action_due"] = back.isoformat()
    return row, (f"{cid} ({row.get('name')}): no answer owed; looked at again on "
                 f"{back.isoformat()}, or as soon as they write")


def owed(contacts, threads, today) -> list[dict]:
    """What the user owes right now: every reply first, then nudges, each oldest first.

    Two kinds, and they are not the same job. A reply is owed the moment they
    answer. A nudge is owed only once `follow_up_on` says (the person's own
    FOLLOW_UP_DAYS, else `schema.FOLLOWUP_BUSINESS_DAYS` business days of silence) and
    only while fewer than `schema.MAX_NUDGES` have gone out (their MAX_UNANSWERED less
    the first message), because one nudge too many on an unanswered thread is the
    message that costs the relationship rather than the one that saves it.

    Replies outrank nudges outright rather than being sorted against them on the
    day count, which `.claude/commands/threads.md` asks for and a single
    `business_days` sort does not give: those are two different clocks, and a
    six-day nudge was landing above somebody who answered this morning and is
    sitting there waiting.

    Each item carries `old`: owed more than OLD_OWED_DAYS with nothing done and no date
    of the person's own on the row, which the due list counts instead of listing.
    """
    today = _need_date(today, "today")
    items = []
    own_dated = set()
    index = by_contact(threads)
    for contact in contacts:
        cid = str(contact.get("contact_id") or "").strip()
        msgs = [r for r in _rows_of(index, cid) if _direction(r)]
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
        if dated_by_person(contact, msgs):
            own_dated.add(cid)                  # theirs, never set aside as old
        # The action rides on whichever row this contact produces, so a person
        # never appears twice. Listing one contact once as a reply and again as
        # an action puts duplicate rows on the list.
        base["next_action"] = action if overdue else ""
        base["next_action_due"] = due.isoformat() if overdue else ""

        if (status in schema.OWED_BY_US and NO_REPLY_OWED.match(action) and not overdue
                and not _written_since(action, msgs)):
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
        def _action_row(overdue=overdue, base=base, contact=contact, due=due, msgs=msgs,
                        status=status, action=action):
            if not overdue:
                return
            items.append(dict(base,
                              kind="action_due",
                              channel=channel_of(contact),
                              since=due.isoformat(),
                              business_days=business_days_between(due, today),
                              due=due.isoformat(),
                              nudges_sent=0,
                              # A send past its day with nothing in the log: it may well
                              # have gone, from the LinkedIn app, where the log never
                              # hears. Listed as unconfirmed, never as "send now".
                              unconfirmed=(status == "not_contacted" and not msgs
                                           and due < today and bool(SEND_ACTION.search(action)))))

        if status in NO_NUDGE:
            _action_row()
            continue
        # A request nobody has accepted cannot be nudged: there is nowhere to
        # write. It is worth withdrawing once it has sat REQUEST_WITHDRAW_DAYS.
        pending = request_pending(msgs)
        if pending is not None:
            if (today - pending).days < REQUEST_WITHDRAW_DAYS:
                # The app's own "Once they accept: ..." line is no job while nobody has: it
                # was listed overdue six working days after every request, with nothing to
                # send (networking audit, 2026-10-25). A date of the person's own is owed.
                if not (_APP_ACTION.fullmatch(" ".join(action.split()))
                        and base["next_action_due"] in _app_dates(msgs, action)):
                    _action_row()
                continue
            items.append(dict(base, kind="request_pending", channel="connection",
                              since=pending.isoformat(),
                              business_days=business_days_between(pending, today),
                              due=(pending + datetime.timedelta(days=REQUEST_WITHDRAW_DAYS)).isoformat(),
                              nudges_sent=0))
            continue
        # Accepted a request that said nothing, and has heard nothing since: a
        # first message is owed, written as one (compose.first_note), never a nudge.
        accepted = accepted_never_messaged(msgs)
        if accepted is not None:
            items.append(dict(base, kind="first_message", channel="message",
                              since=accepted.isoformat(),
                              business_days=business_days_between(accepted, today),
                              due=accepted.isoformat(), nudges_sent=0))
            continue
        # A held call is the last thing that happened: what follows it (the
        # thank-you, the referral ask) is in next_action, never a nudge.
        if msgs and call_held(msgs[-1]):
            _action_row()
            continue
        if LEAVE_ALONE.match(action):
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
        # An automatic reply is not the last thing that happened: the clock runs from our
        # message, and an away message's return date holds the nudge until they are back.
        real = [r for r in msgs if not is_auto_reply(r)]
        last_out = real[-1] if real else None
        sent, due_on, nudges = follow_up_due(contact, msgs)
        if sent is None or due_on is None:
            _action_row()
            continue
        waited = business_days_between(sent, today)
        if today < due_on:
            _action_row()
            continue
        items.append(dict(base,
                          kind="nudge",
                          channel=channel_of(last_out) if last_out else channel_of(contact),
                          since=sent.isoformat(),
                          business_days=waited,
                          due=due_on.isoformat(),
                          nudges_sent=nudges))
    # Replies first, then anything the user put a date on, then nudges. A
    # self-imposed date outranks a nudge because the user chose it; it does not
    # outrank somebody sitting waiting for an answer.
    # A request nobody accepted is never old: it still counts against LinkedIn's limit on
    # pending invitations, and the oldest are the ones most worth withdrawing.
    for i in items:
        i["old"] = (i["kind"] != "request_pending" and i["contact_id"] not in own_dated
                    and owed_too_long(i.get("due"), today))
    order = {"reply": 0, "action_due": 1, "first_message": 2, "nudge": 3, "request_pending": 4}
    items.sort(key=lambda i: (order.get(i["kind"], 9), -i["business_days"],
                              i["contact_id"]))
    return items


def follow_up_on(sent) -> datetime.date:
    """The day a follow-up falls due after a message on `sent` that drew no reply (or an
    acceptance that day): the person's FOLLOW_UP_DAYS calendar days where profile/
    networking.py sets them, else the app's FOLLOWUP_BUSINESS_DAYS business days. The one
    clock `owed`, `reply.nudge_due` and every date written onto a contact read."""
    sent = _need_date(sent, "sent")
    if schema.FOLLOW_UP_DAYS:
        return sent + datetime.timedelta(days=schema.FOLLOW_UP_DAYS)
    return add_business_days(sent, schema.FOLLOWUP_BUSINESS_DAYS)


def follow_up_due(contact, msgs) -> tuple:
    """(the day the clock runs from, the day a follow-up falls due or None, nudges sent)
    for a thread waiting on them. The clock runs from our last message, or from their
    acceptance when that is the last thing that happened, never from an automatic reply,
    and an away message's return date holds it. None when the person's cap on unanswered
    messages is reached (`schema.MAX_UNANSWERED`), or nothing has a date."""
    real = [r for r in msgs if not is_auto_reply(r)]
    sent = (as_date(real[-1].get("date")) if real
            else as_date((contact or {}).get("first_contacted")))
    nudges = max(_trailing_outbound(msgs) - 1, 0)
    if sent is None or nudges >= schema.MAX_NUDGES:
        return sent, None, nudges
    due_on = follow_up_on(sent)
    back = away_until(msgs)
    if back is not None:
        due_on = max(due_on, add_business_days(back, AWAY_GRACE_BUSINESS_DAYS))
    return sent, due_on, nudges


# What the app writes in next_action for a thread's follow-up; a row saying anything
# else is the person's own, and nothing is ever written over it.
FOLLOW_UP_ACTION = "Follow up if no reply ({n} of {cap} sent; your rule: {rule})"
FOLLOW_UP_STOP = "No more follow-ups: {n} messages with no reply, your rule's limit ({rule})"
CLOSE_IT = "If still silent by the date, close it: state.py set {cid} --status gone_cold"
_APP_ACTION = re.compile(
    r"one nudge if no reply"
    r"|once they accept: .+\. withdraw the request if nobody accepts in \d+ days"
    r"|nudged: nothing more unless they reply\. if still silent by the date, close it: "
    r"state\.py set \S+ --status gone_cold"
    r"|follow up if no reply \(\d+ of \d+ sent; your rule: [^)]*\)"
    r"|no more follow-ups: \d+ messages with no reply, your rule's limit \([^)]*\)"
    r"(?:\. if still silent by the date, close it: state\.py set \S+ --status gone_cold)?"
    r"|\S+ sent \d{4}-\d{2}-\d{2} \([^)]*\): (?:one nudge if no reply|follow up if no reply "
    r"\(\d+ of \d+ sent; your rule: [^)]*\)|no more follow-ups: .+)", re.I)


def waiting_action(sent: int, contact_id: str = "") -> str:
    """What a row waiting on a reply says after `sent` messages in a row with none back:
    "One nudge if no reply" under the app's own rule, the person's rule where they set
    one, and, once their limit is reached, that no more go and when to close it."""
    rule = schema.follow_up_rule()
    # The app's own words under its own rule; under the person's, the words name their
    # rule, which is how a later run tells a date the app wrote from one they set.
    own = not schema.FOLLOW_UP_DAYS and schema.MAX_UNANSWERED == 2
    if sent >= schema.MAX_UNANSWERED:
        close = CLOSE_IT.format(cid=contact_id or "<contact_id>")
        if own and sent == 2:
            return "Nudged: nothing more unless they reply. " + close
        return FOLLOW_UP_STOP.format(n=sent, rule=rule) + ". " + close
    if own and sent == 1:
        return "One nudge if no reply"
    return FOLLOW_UP_ACTION.format(n=sent, cap=schema.MAX_UNANSWERED, rule=rule)


def follow_up_plan(contact, msgs) -> tuple | None:
    """(next_action, next_action_due) for a thread waiting on them, by the person's rule:
    the follow-up and its day, or, once their limit is reached, that no more go and the
    day to close it. None when nothing in the thread has a date. The one answer every
    message logged and `write_follow_ups` write onto the row."""
    sent, due_on, nudges = follow_up_due(contact, msgs)
    if sent is None:
        return None
    cid = str((contact or {}).get("contact_id") or "").strip()
    return (waiting_action(nudges + 1, cid),
            (due_on or follow_up_on(sent)).isoformat())


_RULE_DAYS = re.compile(r"your rule(?:'s limit)?:? \(?(\d+) days\b", re.I)


def _app_dates(msgs, action: str = "") -> set:
    """Every day the app could have written as a follow-up date on this thread: under the
    person's rule now, under the rule its own words name (a rule they have changed since),
    or under its own six business days. A date among these is the app's, any other the
    person's."""
    out = set()
    named = _RULE_DAYS.search(str(action or ""))
    for r in msgs:
        d = as_date(r.get("date"))
        if d:
            out |= {follow_up_on(d).isoformat(),
                    add_business_days(d, schema.FOLLOWUP_BUSINESS_DAYS).isoformat()}
            if named:
                out.add((d + datetime.timedelta(days=int(named.group(1)))).isoformat())
    back = away_until(msgs)
    if back is not None:
        out.add(add_business_days(back, AWAY_GRACE_BUSINESS_DAYS).isoformat())
    return out


def write_follow_ups(contacts, threads, today, only_undated: bool = False) -> list[str]:
    """Write onto every contact waiting on a reply what follows by the person's rule
    (`follow_up_plan`): the day a follow-up falls due, or, once their limit is reached,
    that no more go and the day to close it. Returns a line for each row changed. The
    brief and `open_actions.py --due` read the date from the row, so a follow-up is
    remembered by the date itself. Only a row the app wrote is touched: one with no next
    action, or the app's own words (`_APP_ACTION`, whole) with no date or a date the app
    would have written (`_app_dates`). A date the person set, a hold or a note of their own
    is theirs. A thread whose date would be more than OLD_OWED_DAYS past has ended, and is
    left undated. `only_undated` touches only rows with no date at all. Running it twice
    changes nothing the second time. The lists are changed in place; the caller saves."""
    _need_date(today, "today")
    index = by_contact(threads)
    said = []
    for contact in contacts:
        cid = str(contact.get("contact_id") or "").strip()
        action = str(contact.get("next_action") or "").strip()
        due = str(contact.get("next_action_due") or "").strip()
        if (action and not _APP_ACTION.fullmatch(action)) or (only_undated and due):
            continue
        msgs = [r for r in _rows_of(index, cid) if _direction(r)]
        status = effective_status(contact, msgs)
        if (action and status in schema.OWED_BY_US and not only_undated
                and (not due or due in _app_dates(msgs, action))):
            # The app's own follow-up line on someone who has written since: worked out from
            # a log that did not have their message yet (a background upgrade's older copy,
            # 2026-10-24). It is taken off, and their reply is owed as any other.
            contact["next_action"], contact["next_action_due"] = "", ""
            said.append(f"{contact.get('name') or cid} ({cid}): the follow-up line is off: "
                        "they have written since, so a reply is owed")
            continue
        if (not msgs or status in NO_NUDGE or status in schema.OWED_BY_US
                or request_pending(msgs) is not None or accepted_never_messaged(msgs) is not None
                or call_held(msgs[-1])):
            continue
        if due and due not in _app_dates(msgs, action):
            continue
        new = follow_up_plan(contact, msgs)
        if new is None or (action, due) == new:
            continue
        if owed_too_long(new[1], today):
            continue                  # a thread that ended long ago is not dated (OLD_OWED_DAYS)
        contact["next_action"], contact["next_action_due"] = new
        said.append(f"{contact.get('name') or cid} ({cid}): "
                    + (f"follow up on {new[1]}" if not new[0].startswith(("Nudged", "No more"))
                       else f"no more follow-ups; close it on {new[1]} if still silent"))
    return said


# ---------------------------------------------------------------- withdrawing a request

def withdraw(contacts, threads, contact_id, today, reason="") -> dict:
    """Record a connection request the person took back: a thread row, and the contact closed.

    `owed` lists a request nobody accepted in REQUEST_WITHDRAW_DAYS as one to
    withdraw, and nothing recorded the withdrawal, so it stayed on that list and the
    person could be surfaced and written to again. The row is outbound, channel
    `connection`, scenario `request_withdrawn`, which `derive_status` reads as
    closed; the contact is closed with the date and the reason in `outcome`, and
    its next action emptied. Both lists are changed in place; the caller saves them.

    Raises ValueError for a contact not in the book, or with no request waiting on
    them: one accepted, answered or already withdrawn has nothing to withdraw.
    """
    today = _need_date(today, "today")
    cid = str(contact_id or "").strip()
    contact = already_contacted(contacts, contact_id=cid) if cid else None
    if contact is None:
        raise ValueError(f"no contact {cid!r} in the contact book")
    rows = [r for r in threads_for(threads, cid) if _direction(r)]
    pending = request_pending(rows)
    if pending is None and not rows and channel_of(contact) == "connection" \
            and str(contact.get("status") or "").strip() == "awaiting_reply":
        # The request went and its row did not: the contact row is written first.
        pending = as_date(contact.get("first_contacted")) or datetime.date.min
    if pending is None:
        raise ValueError(f"{contact.get('name') or cid} has no connection request waiting to "
                         "be accepted: nothing to withdraw")
    waited = (today - pending).days if pending != datetime.date.min else None
    why = " ".join(str(reason or "").split()) or (
        f"not accepted in {waited} days" if waited is not None else "not accepted")
    row = {"contact_id": cid, "date": today.isoformat(), "direction": "out",
           "channel": "connection", "scenario": "request_withdrawn",
           "summary": f"Withdrew the connection request: {why}", "full_text": ""}
    threads.append(row)
    contact["status"] = "closed"
    contact["next_action"] = ""
    contact["next_action_due"] = ""
    note = f"request withdrawn {today.isoformat()}: {why}"
    contact["outcome"] = "; ".join(x for x in (str(contact.get("outcome") or "").strip(), note) if x)
    return row


def _cli_withdraw(argv) -> int:
    ap = argparse.ArgumentParser(
        prog="state.py withdraw",
        description="Record connection requests the person has withdrawn on LinkedIn.")
    ap.add_argument("contact_ids", nargs="*")
    ap.add_argument("--all-due", action="store_true",
                    help="every request /threads lists as one to withdraw")
    ap.add_argument("--reason", default="")
    ap.add_argument("--contacts", default=CONTACTS_CSV)
    ap.add_argument("--threads", default=THREADS_CSV)
    ap.add_argument("--today", default=datetime.date.today().isoformat())
    a = ap.parse_args(argv)
    contacts, threads = load_contacts(a.contacts), load_threads(a.threads)
    ids = list(a.contact_ids)
    if a.all_due:
        # The requests the due list shows to withdraw: a hold the person put on one (an
        # introduction they are waiting on) keeps it out, as it keeps it off that list.
        notes = {str(c.get("contact_id") or "").strip(): c.get("next_action") for c in contacts}
        ids += [i["contact_id"] for i in owed(contacts, threads, a.today)
                if i["kind"] == "request_pending" and i["contact_id"] not in ids
                and not action_hold(notes.get(i["contact_id"]), a.today)]
    if not ids:
        print("withdraw: name the contact ids, or --all-due for every request to withdraw")
        return 2
    done, failed = 0, 0
    for cid in ids:
        try:
            row = withdraw(contacts, threads, cid, a.today, a.reason)
        except ValueError as e:
            print(f"  not recorded: {e}")
            failed += 1
            continue
        done += 1
        print(f"  {cid}: {row['summary'].lower()}; closed, and never surfaced again")
    if done:
        save_threads(threads, a.threads)
        save_contacts(contacts, a.contacts)
    print(f"withdraw: {done} recorded" + (f", {failed} not" if failed else ""))
    return 1 if failed and not done else 0


# ---------------------------------------------------------------- sent, dropped, reopened

# A next action that is a send: "Send now: connection note", "send the request".
SEND_ACTION = re.compile(r"\b(?:send|sent|connection (?:note|request)|request|inmail|"
                         r"first note|message)\b", re.I)


# Why the words are required. The message that drew a reply from a senior reader within
# three hours reached the log days later, pasted in by the person, and every earlier one
# that drew a reply was logged as "approach" with no text: what_works.py can learn
# nothing from a message it cannot read.
NEEDS_TEXT = ("the words that went are needed, so this message can teach what works: "
              "--text-file <file> with the message as sent (edits included), or --draft if it "
              "went exactly as drafted; a request with no note: --no-note")
NEEDS_SUBJECT = "an InMail's subject is needed too: --subject \"<the subject as sent>\""


def sent(contacts, threads, contact_id, today, date=None, channel="connection", text="",
         outside=False, note=True, subject="", preview=False, attached="") -> dict:
    """Record that a note or a request went: the message row, the contact row, and the
    unsent draft gone. One command for the three steps /network lists, which a person
    sending from the LinkedIn app left undone: the queue then said "send now" to two
    people whose profiles already showed Pending.

    `text` is the message as sent, required unless it is a request with no note
    (`note=False`); an InMail needs its `subject` too. `outside` is a request sent from
    LinkedIn itself: logged with the note the invitations page showed when there was one
    (`preview` when the page cut it at "show more"), and with no text when its words were
    not seen, so it is never an example of what works. An answer to someone who wrote
    first is a reply, and is logged as one (`followed_up`), never as a first note. Both
    lists change in place; the caller saves them. Raises ValueError for a contact not in
    the book, one already written to, or a send with its words missing. `attached` is a
    file that went with it (`resolve_attachment`), named on the row (`attachment_note`).
    """
    day = _need_date(date or today, "date")
    attached = resolve_attachment(attached) if str(attached or "").strip() else ""
    cid = str(contact_id or "").strip()
    contact = already_contacted(contacts, contact_id=cid) if cid else None
    channel = str(channel or "connection").strip().lower()
    body = _paragraphs(text)
    subject = " ".join(str(subject or "").split())

    def words_needed():
        if not outside:
            if not body and (channel != "connection" or note):
                raise ValueError(NEEDS_TEXT)
            if channel == "inmail" and not subject:
                raise ValueError(NEEDS_SUBJECT)

    if contact is None and cid:
        # Read but never written to the book: the row comes from their reading, or is the
        # same person's row under another id. A send is never lost for a missing row, and
        # no row is added for a send refused for its words.
        words_needed()
        contact, _how = from_reading(contacts, cid, _need_date(today, "today"))
        if contact is not None and contact.get("contact_id") != cid:
            _drop_draft(cid)
            cid = str(contact.get("contact_id") or "").strip()
    if contact is None:
        raise ValueError(f"no contact {cid!r} in the contact book, and nothing read about them "
                         "names who they are: read them first (reading.py read <id> <file> "
                         "--name \"<name>\" --company \"<employer>\"), or add their row")
    rows = [r for r in threads_for(threads, cid) if _direction(r) == "out"]
    if rows:
        raise ValueError(f"{contact.get('name') or cid} already has a message logged on "
                         f"{rows[-1].get('date')}: a later message is logged with "
                         f"state.py nudge {cid} (a chase after silence) or state.py message "
                         f"{cid} (a reply, or anything else), with its words")
    if not outside and (body or channel != "connection" or note) \
            and any(said_something(r) for r in threads_for(threads, cid)):
        # They wrote first, so what goes back is a reply, whichever command logs it. Logged
        # here as a first note, an answer to a recruiter became a connection request: a
        # weekly request spent, and "not accepted, withdraw it" three weeks on (2026-10-21).
        return followed_up(contacts, threads, cid, today, text=text, date=date,
                           channel="" if channel == "connection" else channel,
                           subject=subject, kind="message", attached=attached)["row"]
    words_needed()
    if channel == "connection" and outside and body:
        scenario = "connection_note"
        summary = ("Connection request with a note, sent from LinkedIn itself; the note as the "
                   "invitations page showed it" + (", cut where the page folds it" if preview
                                                    else ""))
    elif channel == "connection" and outside:
        scenario = OUTSIDE_SCENARIO
        summary = "Connection request sent from LinkedIn itself; its words were not seen"
    elif channel == "connection":
        scenario = "connection_note" if (note and body) else "connection_request"
        summary = "First note sent"
    else:
        scenario = "first_message"
        summary = f"First {channel} sent"
    if attached:
        summary = f"{summary}; {attachment_note(attached)}"
    row = {"contact_id": cid, "date": day.isoformat(), "direction": "out", "channel": channel,
           "scenario": scenario, "summary": summary, "full_text": body, "subject": subject}
    threads.append(row)
    if not str(contact.get("first_contacted") or "").strip():
        contact["first_contacted"] = day.isoformat()
    contact["channel"] = channel
    contact["status"] = "awaiting_reply"
    if channel == "connection":
        contact["next_action"] = (f"Once they accept: {waiting_action(1)[:1].lower()}"
                                  f"{waiting_action(1)[1:]}. Withdraw the request if nobody "
                                  f"accepts in {REQUEST_WITHDRAW_DAYS} days")
        contact["next_action_due"] = follow_up_on(day).isoformat()
    else:
        plan = follow_up_plan(contact, [r for r in threads_for(threads, cid) if _direction(r)])
        contact["next_action"], contact["next_action_due"] = plan or (
            waiting_action(1, cid), follow_up_on(day).isoformat())
    _drop_draft(cid)
    return row


def _same_words_sent(a: str, b: str) -> bool:
    return " ".join(str(a or "").lower().split()) == " ".join(str(b or "").lower().split())


FOLLOW_UP_KINDS = ("nudge", "message")


def followed_up(contacts, threads, contact_id, today, text="", date=None, channel="",
                subject="", kind="message", attached="", also=False) -> dict:
    """Record a later message to someone already written to: a nudge after silence
    (`kind="nudge"`), or any other message in the thread (`kind="message"`: a reply to them,
    a thank-you, the first words after they accepted a request that carried none). The
    words are required, as for `sent`. `state.py sent` refused every one of these ("already
    has a message logged"), and a day's 62 follow-ups were added to the threads file by hand
    (2026-10-21).

    Returns {"row", "said"}: the message row, and a line for anything worth telling the
    person (a second nudge, which the rules say never to send, is logged and said). Raises
    ValueError for a contact not in the book, one nothing has been logged to yet (that is
    `sent`), a nudge where they spoke last (a reply is owed, not a nudge), a message with no
    words, and a true duplicate: the same words to the same person on the same day.
    Also refused: a second message to them on a day one of ours already went since they
    last wrote, in other words, unless `also` says both really went. Two chats answering
    one message each logged a reply in their own words, and the second was relabelled a
    chase (2026-10-24, twice). A resume going with it is its own step and is let through.
    Both lists change in place; the caller saves them.

    `attached` is a file that went with it (`resolve_attachment`). A resume sent while one
    they asked for is owed is logged as `send_resume`, the scenario /reply reads as
    something they now hold, and a next action that was the resume itself is done."""
    if kind not in FOLLOW_UP_KINDS:
        raise ValueError(f"kind is one of {', '.join(FOLLOW_UP_KINDS)}, not {kind!r}")
    day = _need_date(date or today, "date")
    attached = resolve_attachment(attached) if str(attached or "").strip() else ""
    cid = str(contact_id or "").strip()
    contact = already_contacted(contacts, contact_id=cid) if cid else None
    if contact is None:
        raise ValueError(f"no contact {cid!r} in the contact book")
    name = contact.get("name") or cid
    body = _paragraphs(text)
    if not body:
        raise ValueError("the words that went are needed, so this message can teach what "
                         "works: --text-file <file> with the message as sent, or --draft")
    rows = [r for r in threads_for(threads, cid) if _direction(r)]
    outs = [r for r in rows if _direction(r) == "out" and not is_withdrawal(r)]
    said = [r for r in rows if said_something(r)]
    if not outs and not said:
        raise ValueError(f"nothing is logged as sent to {name} yet: the first message is "
                         f"state.py sent {cid}")
    for r in outs:
        if (str(r.get("date") or "") == day.isoformat()
                and _same_words_sent(r.get("full_text"), body)):
            raise ValueError(f"already logged: the same words to {name} on {day.isoformat()}")
    # Who spoke last, the one answer /reply reads too: "they ever replied" refused a due
    # nudge after our own answer to them, and set up a second one (2026-10-21).
    they_last = they_spoke_last(rows)
    if not they_last and not also and not (attached and is_resume_file(attached)):
        ordered = _ordered(rows)
        last_word = max((i for i, r in enumerate(ordered) if said_something(r)), default=-1)
        # Only a message counts: a call held, an acceptance or a connection request (its
        # note included) is not an answer to them, and the first message after a request
        # accepted the same day is the ordinary next step.
        today_out = [r for r in ordered[last_word + 1:]
                     if _is_message_out(r) and not is_request(r)
                     and str(r.get("date") or "") == day.isoformat()]
        if today_out:
            there = " ".join(str(today_out[-1].get("full_text")
                                 or today_out[-1].get("summary") or "").split())
            there = there if len(there) <= 160 else there[:157].rstrip() + "..."
            raise ValueError(
                f"a message to {name} is already logged for {day.isoformat()}"
                + (" since they last wrote" if last_word >= 0 else "")
                + f": \"{there}\". Another chat may have answered them already: check "
                "before anything else goes. If both really went, log this one with --also")
    spoke = [r for r in outs if not is_bare_request(r)]
    if kind == "nudge" and they_last:
        raise ValueError(f"{name} wrote last ({said[-1].get('date')}): a reply is owed, not a "
                         f"nudge. Log it with state.py message {cid}")
    if they_last:
        scenario = "reply"
    elif not spoke:
        scenario = "first_message"       # after a request that said nothing
    else:
        # A second message with no reply between is a chase, whatever the command: the
        # nudge count (owed, what_works) reads it as one.
        scenario = "nudge"
    accepted = any(is_acceptance(r) for r in rows)
    chan = str(channel or "").strip().lower()
    if not chan and not outs:
        # They wrote first: the answer goes back the way they came, and an answer on
        # LinkedIn is a message, never a request or a paid InMail.
        chan = channel_of(said[-1]) or "message"
        chan = "message" if chan in ("connection", "inmail", "open_profile") else chan
    elif not chan:
        chan = channel_of(outs[-1]) or channel_of(contact) or "message"
        if chan == "connection" and (accepted or scenario != "first_message"):
            chan = "message"             # once connected, a message, never another request
    note = ""
    if scenario == "nudge":
        before = max(_trailing_outbound(rows), 1) - 1
        if before >= schema.MAX_NUDGES:
            note = (f"that is nudge {before + 1} to {name}; the rule is {schema.MAX_NUDGES}. "
                    "Logged because it went; nothing more goes until they reply")
    resume = bool(attached) and is_resume_file(attached)
    owed_one = resume and kind == "message" and any(
        o["contact_id"] == cid for o in resumes_owed([contact], threads))
    if owed_one:
        scenario, note = "send_resume", ""
    summary = {"nudge": f"Nudge sent ({chan})", "reply": f"Reply sent ({chan})",
               "first_message": f"First {chan} sent, after they accepted",
               "send_resume": f"{noun()[:1].upper() + noun()[1:]} sent ({chan}), as asked"
               }[scenario]
    if attached:
        summary = f"{summary}; {attachment_note(attached)}"
    row = {"contact_id": cid, "date": day.isoformat(), "direction": "out", "channel": chan,
           "scenario": scenario, "summary": summary, "full_text": body,
           "subject": " ".join(str(subject or "").split())}
    threads.append(row)
    stored = str(contact.get("status") or "").strip()
    if stored in DERIVABLE or stored in ("", "connected_no_reply", "gone_cold"):
        contact["status"] = derive_status(threads_for(threads, cid))
    if not str(contact.get("first_contacted") or "").strip():
        contact["first_contacted"] = day.isoformat()
    # What follows, by the person's rule: the next follow-up and its day, or that no more
    # go and the day to close it (follow_up_plan), the same answer write_follow_ups gives.
    plan = follow_up_plan(contact, [r for r in threads_for(threads, cid) if _direction(r)])
    then, due = plan or (waiting_action(1, cid), follow_up_on(day).isoformat())
    if scenario == "nudge":
        contact["next_action"] = then
    waiting = DERIVABLE | {"connected_no_reply"}
    done = (scenario != "nudge" and resume
            and (str(contact.get("status") or "") in waiting or _row_records_resume(contact)
                 or not str(contact.get("next_action") or "").strip()))
    if done:
        # The resume was the thing owed: the row stops asking for it, and its date with it.
        contact["next_action"] = (f"{noun()[:1].upper() + noun()[1:]} sent {day.isoformat()} "
                                  f"({attached}): {then[:1].lower()}{then[1:]}")
    elif scenario != "nudge" and str(contact.get("status") or "") in waiting:
        # Connected and now written to: "once they accept" is over, so the request's
        # withdraw-in-21-days line no longer stands beside the nudge (2026-10-21).
        contact["next_action"] = then
    contact["next_action_due"] = due if (done or str(contact.get("status") or "") in waiting) \
        else contact.get("next_action_due", "")
    _drop_draft(cid)
    return {"row": row, "said": note}


RECEIVED_CHANNELS = ("message", "inmail", "email", "connection", "intro")


def received(contacts, threads, contact_id, today, text="", date=None, channel="",
             scenario="", subject="") -> dict:
    """Record their message: what they wrote, the day it came, the way it came.

    /reply step 6 says their message goes into the log at once, and there was no command
    for it: every chat wrote the row into network_threads.csv by hand, some without its
    words, so the message could never be read again or count as a reply that worked
    (networking audit, 2026-10-25). This writes the row the export writes for a message
    in: direction `in`, the channel, the scenario `reply.classify` reads (given, or read
    here), a one-line summary and the full text.

    The words are required. Raises ValueError for a contact not in the book, a message
    with no words, an unknown scenario, and the same words from them on the same day
    already logged (another chat logged it first). The contact's status follows the log
    where the log decides it; an app-written follow-up line comes off, because a reply is
    owed now, not a nudge. Returns {"row", "said"}; both lists change in place and the
    caller saves them."""
    day = _need_date(date or today, "date")
    cid = str(contact_id or "").strip()
    contact = already_contacted(contacts, contact_id=cid) if cid else None
    if contact is None:
        raise ValueError(f"no contact {cid!r} in the contact book")
    name = contact.get("name") or cid
    body = _paragraphs(text)
    if not body:
        raise ValueError("their words are needed, so the reply can be read again later: "
                         "--text-file <file> with their message as it came")
    rows = [r for r in threads_for(threads, cid) if _direction(r)]
    for r in rows:
        if (_direction(r) == "in" and str(r.get("date") or "") == day.isoformat()
                and _same_words_sent(r.get("full_text"), body)):
            raise ValueError(f"already logged: the same words from {name} on {day.isoformat()}")
    chan = channel_of(str(channel or ""))
    if chan and chan not in RECEIVED_CHANNELS:
        raise ValueError(f"channel is one of {', '.join(RECEIVED_CHANNELS)}, not {channel!r}")
    if not chan:
        outs = [r for r in rows if _direction(r) == "out" and not is_withdrawal(r)]
        chan = channel_of(outs[-1]) if outs else channel_of(contact)
        # An answer on LinkedIn to a request or an InMail arrives as a message.
        chan = "message" if chan in ("", "connection", "open_profile") else chan
    scen = re.sub(r"[\s-]+", "_", str(scenario or "").strip().lower())
    try:
        import reply as _reply
    except ImportError:  # the reader is beside this file; never without it in the app
        _reply = None
    # A scenario that says it was not a message (an acceptance, a request) would log their
    # words as a click, and the thread would read as nobody having written.
    if scen in ACCEPTED_SCENARIOS or scen in REQUEST_SCENARIOS:
        raise ValueError(f"{scenario!r} records something they did, not a message: log a "
                         "message with the scenario /reply read, or none")
    if _reply is not None:
        if not scen:
            try:
                scen = str(_reply.classify(body, rows, day).get("scenario") or "")
            except (ValueError, TypeError):
                scen = ""
    machine = scen in AUTO_REPLY_SCENARIOS or auto_reply(body, subject, day) is not None
    summary = ("Automatic reply" if machine else "They replied") + f" ({chan})"
    row = {"contact_id": cid, "date": day.isoformat(), "direction": "in", "channel": chan,
           "scenario": scen, "summary": summary, "full_text": body,
           "subject": " ".join(str(subject or "").split())}
    threads.append(row)
    said = ""
    stored = str(contact.get("status") or "").strip()
    if stored in DERIVABLE or stored in ("", "connected_no_reply", "gone_cold"):
        contact["status"] = derive_status(threads_for(threads, cid))
    elif not machine:
        said = (f"{name} is at {stored}, which the log does not decide: if this message "
                f"changes that, state.py set {cid} --status <status>")
    action = str(contact.get("next_action") or "").strip()
    if (not machine and str(contact.get("status") or "") in schema.OWED_BY_US
            and action and _APP_ACTION.fullmatch(action)):
        contact["next_action"], contact["next_action_due"] = "", ""
    return {"row": row, "said": said}


def _words_from(path: str, prog: str):
    """A message's words from the file named, or None with one plain line said: a missing
    file ended `sent`, `text`, `nudge`, `message` and `resent` in a traceback (networking
    audit, 2026-10-25), where `received` already said it plainly."""
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except (OSError, UnicodeDecodeError) as e:
        print(f"{prog}: cannot read {path}: {getattr(e, 'strerror', None) or e}")
        return None


def _cli_received(argv) -> int:
    ap = argparse.ArgumentParser(
        prog="state.py received",
        description="Record a message they sent, with their words as it came.")
    ap.add_argument("contact_id", help="who wrote")
    ap.add_argument("--text-file", required=True, help="their message, as it came")
    ap.add_argument("--date", default="", help="the day it came (default today)")
    ap.add_argument("--channel", default="", choices=("",) + RECEIVED_CHANNELS,
                    help="default: the way the thread runs (a message on LinkedIn)")
    ap.add_argument("--scenario", default="",
                    help="what /reply read it as (default: read here, the same way)")
    ap.add_argument("--subject", default="")
    ap.add_argument("--contacts", default=CONTACTS_CSV)
    ap.add_argument("--threads", default=THREADS_CSV)
    ap.add_argument("--today", default=datetime.date.today().isoformat())
    a = ap.parse_args(argv)
    text = _words_from(a.text_file, "received")
    if text is None:
        return 1
    contacts, threads = load_contacts(a.contacts), load_threads(a.threads)
    try:
        got = received(contacts, threads, a.contact_id, a.today, text=text,
                       date=a.date or None, channel=a.channel, scenario=a.scenario,
                       subject=a.subject)
    except ValueError as e:
        print(f"received: not recorded: {a.contact_id}: {e}")
        return 1
    save_threads(threads, a.threads)
    save_contacts(contacts, a.contacts)
    row = got["row"]
    status = (already_contacted(contacts, contact_id=a.contact_id) or {}).get("status", "")
    print(f"received: {a.contact_id}: {row['summary']} on {row['date']}"
          + (f", read as {row['scenario']}" if row["scenario"] else "")
          + (f"; now {status}" if status else ""))
    if got["said"]:
        print(f"  {got['said']}")
    return 0


def _drop_draft(contact_id: str) -> bool:
    """Delete documents/network/<id>/draft.md, the unsent copy, when there is one."""
    try:
        import reading
        path = reading.draft_path(contact_id)
    except (ImportError, ValueError):
        return False
    if os.path.isfile(path):
        os.remove(path)
        return True
    return False


def _paragraphs(text) -> str:
    """The words as sent, spacing tidied inside each paragraph and the paragraphs kept:
    an InMail's shape is its paragraphs, and a note put back by unsend keeps them."""
    parts = [" ".join(p.split()) for p in re.split(r"\n\s*\n", str(text or ""))]
    return "\n\n".join(p for p in parts if p)


SUBJECT_LINE = "Subject:"


def split_subject(text: str) -> tuple[str, str]:
    """(subject, body) of a draft written as compose.InMail writes one: a first line
    "Subject: ...", a blank line, then the body. ("", text) for anything else."""
    t = str(text or "").lstrip()
    if not t.startswith(SUBJECT_LINE):
        return "", str(text or "")
    first, _, rest = t.partition("\n")
    return first[len(SUBJECT_LINE):].strip(), rest.strip()


def _first_out(threads, cid) -> int | None:
    """The index in `threads` of the latest message logged to them: by date, file order
    only for a tie. By file position alone, an older message the export import appended at
    the end was the one unsend took off the log, its words put back as their draft, while
    the message that did not go stayed logged (2026-10-21)."""
    rows = [r for r in threads_for(threads, cid) if _direction(r) == "out"]
    if not rows:
        return None
    return next(i for i, r in enumerate(threads) if r is rows[-1])


def _later_in(threads, i, cid) -> list:
    """Their inbound rows dated after row `i` (or on its day and after it in the file)."""
    ordered = threads_for(threads, cid)
    at = next(n for n, r in enumerate(ordered) if r is threads[i])
    return [r for r in ordered[at + 1:] if _direction(r) == "in"]


def resent(contacts, threads, contact_id, today, text="", date=None, subject="") -> dict:
    """Correct the last message logged to them: it went on another day, or with other words.
    A chat that recorded a batch as sent, then heard one went later or with edits, had to
    edit the thread and contact rows by hand (date, text, first contact, follow-up due).
    Returns {"row", "before"} (the row as it is now, the text it replaced)."""
    cid = str(contact_id or "").strip()
    contact = already_contacted(contacts, contact_id=cid) if cid else None
    if contact is None:
        raise ValueError(f"no contact {cid!r} in the contact book")
    i = _first_out(threads, cid)
    if i is None:
        raise ValueError(f"nothing is logged as sent to {contact.get('name') or cid}: "
                         "record it with state.py sent")
    if not str(text or "").strip() and not date and not subject:
        raise ValueError("name what changed: --text-file, --date or --subject")
    row = threads[i]
    before = row.get("full_text") or ""
    old_day = row.get("date")
    if str(text or "").strip():
        row["full_text"] = _paragraphs(text)
        if row.get("scenario") == OUTSIDE_SCENARIO:
            row["scenario"] = "connection_note"
    if subject:
        row["subject"] = " ".join(str(subject).split())
    if date:
        day = _need_date(date, "date")
        row["date"] = day.isoformat()
        firsts = [r for r in threads if str(r.get("contact_id") or "").strip() == cid
                  and _direction(r) == "out"]
        if str(contact.get("first_contacted") or "") in ("", old_day) or len(firsts) == 1:
            contact["first_contacted"] = min(as_date(r.get("date")) or day
                                             for r in firsts).isoformat()
        if str(contact.get("status") or "") == "awaiting_reply":
            contact["next_action_due"] = follow_up_on(day).isoformat()
    return {"row": row, "before": before}


def unsend(contacts, threads, contact_id, today) -> dict:
    """The person says it did not go: the last message logged to them comes off the log,
    and the note goes back to their draft so the queue offers it again. Only a message
    nothing came back to: a reply after it means it went."""
    cid = str(contact_id or "").strip()
    contact = already_contacted(contacts, contact_id=cid) if cid else None
    if contact is None:
        raise ValueError(f"no contact {cid!r} in the contact book")
    i = _first_out(threads, cid)
    if i is None:
        raise ValueError(f"nothing is logged as sent to {contact.get('name') or cid}")
    row = threads[i]
    later = _later_in(threads, i, cid)
    if later:
        raise ValueError(f"{contact.get('name') or cid} replied after it ({later[0].get('date')}),"
                         " so it went: correct it with state.py resent instead")
    del threads[i]
    theirs = threads_for(threads, cid)           # by date: left[-1] is the latest still logged
    left = [r for r in theirs if _direction(r) == "out"]
    if not left:
        contact["first_contacted"] = ""
        # Someone who wrote first still has a thread: what it says, not "never contacted".
        contact["status"] = derive_status(theirs) if theirs else "not_contacted"
        contact["next_action"] = ("Send: the note in their draft" if not theirs else
                                  "Reply: the note in their draft answers their message")
        contact["next_action_due"] = ""
    else:
        contact["next_action_due"] = follow_up_on(
            as_date(left[-1].get("date")) or _need_date(today, "today")).isoformat()
    restored = ""
    if row.get("full_text"):
        words = row["full_text"]
        if str(row.get("subject") or "").strip():
            words = f"{SUBJECT_LINE} {row['subject']}\n\n{words}"   # as compose writes one
        try:
            import reading
            restored = reading.write_draft(cid, words, contact.get("name") or "")
        except (ImportError, OSError, ValueError):
            restored = ""
    return {"row": row, "draft": restored}


def never_messaged(contact, threads) -> bool:
    """Nothing has gone to them: no message or request in the log, none on the row."""
    cid = str(contact.get("contact_id") or "").strip()
    if any(_direction(r) == "out" for r in threads_for(threads, cid)):
        return False
    return not str(contact.get("first_contacted") or "").strip()


def _note(contact, field, text):
    contact[field] = "; ".join(x for x in (str(contact.get(field) or "").strip(), text) if x)


def drop(contacts, threads, contact_id, today, reason) -> dict:
    """Set a never-messaged contact aside: status `dropped`, reversible with `reopen`."""
    today = _need_date(today, "today")
    contact = already_contacted(contacts, contact_id=str(contact_id or "").strip())
    if contact is None:
        raise ValueError(f"no contact {contact_id!r} in the contact book")
    if not never_messaged(contact, threads):
        raise ValueError(f"{contact.get('name') or contact_id} has been written to: close the "
                         "thread with its outcome instead, it is not a draft set aside")
    why = " ".join(str(reason or "").split()) or "set aside by the person"
    contact["status"] = "dropped"
    contact["next_action"], contact["next_action_due"] = "", ""
    _note(contact, "outcome", f"dropped {today.isoformat()}: {why}")
    return contact


def reopen(contacts, threads, contact_id, today, reason) -> dict:
    """Bring back a contact nobody has written to: status `not_contacted` again.

    Only someone never messaged. A dropped draft, or one closed before anything went,
    is a person still worth writing to; anyone who has had a message is not reopened
    here, because "never surface someone already contacted" holds."""
    today = _need_date(today, "today")
    contact = already_contacted(contacts, contact_id=str(contact_id or "").strip())
    if contact is None:
        raise ValueError(f"no contact {contact_id!r} in the contact book")
    if not never_messaged(contact, threads):
        raise ValueError(f"{contact.get('name') or contact_id} has been written to, so is "
                         "never surfaced again: reopen is for people nothing went to")
    why = " ".join(str(reason or "").split())
    if not why:
        raise ValueError("reopen needs --reason: why they are worth writing to again")
    was = contact.get("status") or "not_contacted"
    contact["status"] = "not_contacted"
    _note(contact, "notes", f"reopened {today.isoformat()} from {was}: {why}")
    return contact


def close(contacts, contact_id, today, reason, row=None) -> dict:
    """Close a contact a read ruled out, with the reason, and delete their unsent draft.
    `row` writes a new closed row for a candidate not in the book yet, so a later run
    never spends another read on them."""
    today = _need_date(today, "today")
    cid = str(contact_id or "").strip()
    contact = already_contacted(contacts, contact_id=cid) if cid else None
    if contact is None:
        if not row:
            raise ValueError(f"no contact {cid!r} in the contact book")
        contact = {k: "" for k in schema.CONTACT_COLUMNS}
        contact.update({k: v for k, v in row.items() if k in schema.CONTACT_COLUMNS})
        contact["contact_id"] = cid
        contact["company_key"] = contact.get("company_key") or company_key(contact.get("company"))
        contacts.append(contact)
    why = " ".join(str(reason or "").split())
    if not why:
        raise ValueError("a close needs its reason")
    contact["status"] = "closed"
    contact["next_action"], contact["next_action_due"] = "", ""
    _note(contact, "outcome", f"skipped after a read {today.isoformat()}: {why}")
    _drop_draft(cid)
    return contact


def add_row(contacts, contact_id, fields) -> dict:
    """Append one contact row in the schema's shape, at `not_contacted` unless `fields`
    says otherwise, and return it. The caller saves the book."""
    row = {k: "" for k in schema.CONTACT_COLUMNS}
    row.update({k: str(v or "") for k, v in (fields or {}).items() if k in schema.CONTACT_COLUMNS})
    row["contact_id"] = str(contact_id or "").strip()
    row["company_key"] = row.get("company_key") or company_key(row.get("company"))
    row["status"] = row.get("status") or "not_contacted"
    contacts.append(row)
    return row


def _reading_url(got: dict) -> str:
    for src in (got or {}).get("sources") or []:
        url = str((src or {}).get("url") or "")
        if profile_handle(url):
            return url
    return ""


def from_reading(contacts, contact_id, today) -> tuple:
    """(the contact row, how it was found) for someone read but never written to the book.

    `reading.py read --name --company` keeps what was read under documents/network/<id>/,
    and nothing put the person in network_contacts.csv: three InMails that went to people
    read that way were refused by `sent` ("no contact in the contact book") and logged only
    once rows were added by hand (2026-10-20). So a send, or a draft, finds them here.

    The same person already in the book, under any id, by their LinkedIn address or by
    their name at that employer, is that row ("existing"): never a second one. Otherwise a
    new row from the reading ("added"). (None, "") when nothing was read about them, or the
    reading lacks their name or their employer."""
    try:
        import reading
        got = reading.load(str(contact_id or "").strip()) or {}
    except (ImportError, ValueError):
        return None, ""
    name, company = str(got.get("name") or "").strip(), str(got.get("company") or "").strip()
    if not name or not company:
        return None, ""
    url = _reading_url(got)
    same = already_contacted(contacts, name=name, company=company, linkedin_url=url or None)
    if same is not None:
        return same, "existing"
    day = _need_date(today, "today")
    try:
        import reading
        channel = reading.channel_for(got)
    except ImportError:
        channel = ""
    row = add_row(contacts, contact_id, {
        "name": name, "company": company, "title": got.get("headline", ""),
        "location": got.get("location", ""), "linkedin_url": url,
        "channel": channel or "connection",
        "notes": f"added {day.isoformat()} from the reading of them, which never reached the book"})
    return row, "added"


def book_at(contacts, threads, company) -> dict:
    """Who the book already holds at one employer: {"in_book", "never_messaged", "ids"}.
    Discovery leaves them out, and said nothing; a run then told a person their top
    employers were covered when nobody there had been written to."""
    rows = contacts_at(contacts, company)
    never = [c for c in rows if never_messaged(c, threads)]
    return {"in_book": len(rows), "never_messaged": len(never),
            "ids": [c.get("contact_id", "") for c in never]}


def where(contacts, terms) -> list:
    """The contacts matching every term: FIELD=VALUE (equal, ignoring case) or
    FIELD~WORDS (contains, ignoring case)."""
    out = list(contacts)
    for t in terms or ():
        m = re.match(r"^\s*(\w+)\s*([=~])\s*(.*?)\s*$", str(t))
        if not m:
            raise ValueError(f"a --where term is FIELD=VALUE or FIELD~WORDS, not {t!r}")
        field, op, value = m.group(1), m.group(2), m.group(3).lower()
        if field == "company":
            key = company_key(value)
            out = [c for c in out if (row_company_key(c) == key if op == "=" else
                                      value in str(c.get("company") or "").lower())]
            continue
        out = [c for c in out if (str(c.get(field) or "").strip().lower() == value if op == "="
                                  else value in str(c.get(field) or "").lower())]
    return out


# Closed rows that were really a queue set aside: never messaged, and the outcome says
# the note never went. Only those words: a dead end (left, unreachable, declined) stays
# closed. The upgrade that moves them to `dropped` reads this.
_DROPPED_WORDS = re.compile(r"\b(?:never sent|not sent|queue dropped|dropped by the candidate|"
                            r"dropped from the queue|set aside|not sending|unsent)\b", re.I)


def closed_but_dropped(contacts, threads) -> list:
    """Closed contacts nothing went to whose outcome says the note was never sent."""
    return [c for c in contacts if str(c.get("status") or "").strip() == "closed"
            and never_messaged(c, threads)
            and _DROPPED_WORDS.search(" ".join(str(c.get(k) or "") for k in ("outcome", "notes")))]


def fill_text(threads, contact_id, date, text) -> dict:
    """Put the words of a message already logged with no text into its row: the one
    outbound row to this contact on this date that has none. An interview pack could not
    say what a referrer had been told, because the message was logged as a summary."""
    text = str(text or "").strip()
    if not text:
        raise ValueError("no text to add")
    rows = [r for r in threads if str(r.get("contact_id") or "").strip() == contact_id
            and _direction(r) == "out" and str(r.get("date") or "").strip() == date]
    empty = [r for r in rows if not str(r.get("full_text") or "").strip()]
    if not rows:
        raise ValueError(f"no message to {contact_id} on {date} is logged")
    if not empty:
        raise ValueError(f"the message to {contact_id} on {date} already has its text")
    if len(empty) > 1:
        raise ValueError(f"{len(empty)} messages to {contact_id} on {date} have no text: "
                         "add it to the right one by hand")
    empty[0]["full_text"] = text
    return empty[0]


def _cli_text(argv) -> int:
    ap = argparse.ArgumentParser(
        prog="state.py text",
        description="Add the words of a message logged with no text (its summary only).")
    ap.add_argument("contact_id")
    ap.add_argument("--date", required=True, help="the day it went, as logged")
    ap.add_argument("--text-file", required=True, help="the message as it was sent")
    ap.add_argument("--threads", default="")
    a = ap.parse_args(argv)
    path = a.threads or person.state("network_threads.csv")
    text = _words_from(a.text_file, "text")
    if text is None:
        return 1
    threads = load_threads(path)
    try:
        fill_text(threads, a.contact_id, a.date, text)
    except ValueError as e:
        print(f"text: not added: {e}")
        return 1
    save_threads(threads, path)
    print(f"text: added to the message to {a.contact_id} on {a.date}")
    return 0


BATCH_SENT_CHECK = (
    "sent: not recorded. Several requests at once are logged from LinkedIn's sent list, which "
    "shows what actually went: open it (python3 tools/claude_surfaces.py show "
    "linkedin-sent-invitations) and read it with python3 tools/network/reading.py "
    "invitations <the page> --record, which logs only the requests it shows, with the words "
    "each went with. Where the person named each one as sent, run this again with --each-went.")


def _cli_sent(argv) -> int:
    ap = argparse.ArgumentParser(
        prog="state.py sent",
        description="Record that a note or request went: the message, the contact, the draft.")
    ap.add_argument("contact_ids", nargs="+")
    ap.add_argument("--date", default="", help="the day it went (default today)")
    ap.add_argument("--channel", default="connection",
                    choices=("connection", "inmail", "open_profile", "email", "intro", "message"),
                    help="open_profile: a free message to an Open Profile (only Message showed "
                         "and LinkedIn used no InMail credit), kept apart from the credits")
    ap.add_argument("--text-file", default="", help="the message as sent, with any edits")
    ap.add_argument("--draft", action="store_true",
                    help="it went exactly as drafted: log the draft's words")
    ap.add_argument("--outside", action="store_true",
                    help="sent from LinkedIn itself, words not seen (a request seen as Pending)")
    ap.add_argument("--no-note", action="store_true", help="a connection request with no note")
    ap.add_argument("--each-went", action="store_true",
                    help="several requests at once: the person named each one as sent (else "
                         "LinkedIn's sent list is read first, and only what it shows is logged)")
    ap.add_argument("--subject", default="", help="an InMail's subject as sent")
    ap.add_argument("--attached", default="", metavar="FILE",
                    help="a file that went with it, as it sits in the repo (a resume: "
                         "cv/<name>.pdf or documents/cv/<name>.pdf)")
    ap.add_argument("--contacts", default=CONTACTS_CSV)
    ap.add_argument("--threads", default=THREADS_CSV)
    ap.add_argument("--today", default=datetime.date.today().isoformat())
    a = ap.parse_args(argv)
    if a.text_file and len(a.contact_ids) > 1:
        print("sent: --text-file is one person's message; name one contact")
        return 1
    if a.attached and len(a.contact_ids) > 1:
        print("sent: --attached is one person's file; name one contact")
        return 1
    if len(a.contact_ids) > 1 and a.channel == "connection" and not a.outside and not a.each_went:
        # "Sent to all of those" logged 14 where 7 went (2026-10-22). The sent list shows what
        # went, with the words each carried.
        print(BATCH_SENT_CHECK)
        return 1
    given = _words_from(a.text_file, "sent") if a.text_file else ""
    if given is None:
        return 1
    contacts, threads = load_contacts(a.contacts), load_threads(a.threads)
    done = 0
    for cid in a.contact_ids:
        text, before, subject, placeholder = "", None, a.subject, False
        if a.text_file:
            text = given
            before = _draft_of(cid)
        elif a.draft:
            text = _draft_of(cid)
            if text is None:
                print(f"  not recorded: {cid} has no draft to log")
                continue
            placeholder = _waits_on_read(cid)
        drafted_subject, body = split_subject(text)
        if drafted_subject:                      # an InMail draft carries its subject line
            text, subject = body, subject or drafted_subject
        if before is not None:                   # the edit is to the words, not the subject
            before = split_subject(before)[1]
        in_book = already_contacted(contacts, contact_id=cid) is not None
        try:
            row = sent(contacts, threads, cid, a.today, date=a.date or None, channel=a.channel,
                       text=text, outside=a.outside, note=not a.no_note, subject=subject,
                       attached=a.attached)
        except ValueError as e:
            print(f"  not recorded: {e}")
            continue
        if before is not None:                   # recorded once the send is, never twice
            _learn_edit(cid, text, draft=before)
        done += 1
        logged = row["contact_id"]
        if logged != cid:
            print(f"  {cid}: the same person is in the contact book as {logged} (their LinkedIn "
                  "address, or their name at that employer): recorded there, no second row")
        elif not in_book:
            print(f"  {cid}: was not in the contact book; added from what was read about them")
        print(f"  {logged}: {shown_summary(row)} on {row['date']}; awaiting their reply, "
              "draft removed")
        if placeholder:
            # A placeholder written before anyone was read is never sent as it stands: logged
            # because the person says it went, and said, so other words can be put right.
            print(f"    that draft was a placeholder waiting on a read, never meant to go as it "
                  "stood. If other words went, put them on the log: python3 "
                  f"tools/network/state.py resent {logged} --text-file <the message as sent>")
    if done:
        save_threads(threads, a.threads)
        save_contacts(contacts, a.contacts)
    print(f"sent: {done} recorded")
    if done and a.draft and len(a.contact_ids) > 1:
        print("Ask the person once: did any of these go with edits, or on another day? For "
              "each that did: python3 tools/network/state.py resent <id> --text-file <the "
              "words as sent> [--date YYYY-MM-DD]. The edit is recorded as their preference.")
    if done and a.channel == "open_profile":
        print("Open Profile: free, so no InMail credit is counted for it")
    if done and a.channel == "inmail":
        b = platform_budget(contacts, threads, a.today)
        print(f"InMail credits: {b['inmails_left']} left this month ({b['inmails_source']})")
    return 0 if done else 1


def _cli_followed_up(argv, kind) -> int:
    ap = argparse.ArgumentParser(
        prog=f"state.py {kind}",
        description=("Record a nudge that went: a chase after silence, with its words."
                     if kind == "nudge" else
                     "Record a later message that went (a reply, a thank-you, the first words "
                     "after they accepted), with its words."))
    ap.add_argument("contact_ids", nargs="*",
                    help="who it went to; with --texts, the ids in the file when none are named")
    ap.add_argument("--text-file", default="", help="the message as sent, with any edits")
    ap.add_argument("--texts", default="", metavar="FILE.json",
                    help="several at once: {\"<contact_id>\": \"<the words as sent>\", ...}")
    ap.add_argument("--draft", action="store_true",
                    help="it went exactly as drafted: log each one's draft.md")
    ap.add_argument("--date", default="", help="the day it went (default today)")
    ap.add_argument("--channel", default="",
                    choices=("", "message", "connection", "inmail", "open_profile", "email",
                             "intro"),
                    help="default: the thread's own; a message once they are connected")
    ap.add_argument("--subject", default="")
    ap.add_argument("--attached", default="", metavar="FILE",
                    help="a file that went with it, as it sits in the repo (a resume: "
                         "cv/<name>.pdf or documents/cv/<name>.pdf)")
    ap.add_argument("--also", action="store_true",
                    help="it went as well as the message already logged to them that day: "
                         "two different messages, both sent")
    ap.add_argument("--contacts", default=CONTACTS_CSV)
    ap.add_argument("--threads", default=THREADS_CSV)
    ap.add_argument("--today", default=datetime.date.today().isoformat())
    a = ap.parse_args(argv)
    if a.text_file and len(a.contact_ids) > 1:
        print(f"{kind}: --text-file is one person's message; name one contact, or use --texts")
        return 1
    if a.attached and len(a.contact_ids) > 1:
        print(f"{kind}: --attached is one person's file; name one contact")
        return 1
    texts = {}
    if a.texts:
        import json
        raw = _words_from(a.texts, kind)
        if raw is None:
            return 1
        try:
            texts = {str(k): str(v) for k, v in (json.loads(raw) or {}).items()}
        except (ValueError, AttributeError):
            print(f"{kind}: {a.texts} is not a file of {{contact id: message}} pairs (JSON)")
            return 1
    given = _words_from(a.text_file, kind) if a.text_file else ""
    if given is None:
        return 1
    if not a.contact_ids:
        # --texts is how several are logged at once: its ids are the ones it names.
        a.contact_ids = list(texts)
    if not a.contact_ids:
        print(f"{kind}: name who it went to (their contact ids), or give --texts <file.json>")
        return 1
    contacts, threads = load_contacts(a.contacts), load_threads(a.threads)
    done = 0
    for cid in a.contact_ids:
        before = None
        if a.text_file:
            text = given
            before = _draft_of(cid)
        elif cid in texts:
            text, before = texts[cid], _draft_of(cid)
        elif a.draft:
            text = _draft_of(cid)
            if text is None:
                print(f"  not recorded: {cid} has no draft to log")
                continue
        else:
            text = ""
        try:
            got = followed_up(contacts, threads, cid, a.today, text=text, date=a.date or None,
                              channel=a.channel, subject=a.subject, kind=kind,
                              attached=a.attached, also=a.also)
        except ValueError as e:
            print(f"  not recorded: {cid}: {e}")
            continue
        if before is not None:
            _learn_edit(cid, text, draft=before)
        done += 1
        row = got["row"]
        after = (already_contacted(contacts, contact_id=cid) or {}).get("next_action", "")
        print(f"  {cid}: {shown_summary(row)} on {row['date']}"
              + (f"; next: {after}" if after else ""))
        if got["said"]:
            print(f"    {got['said']}")
    if done:
        save_threads(threads, a.threads)
        save_contacts(contacts, a.contacts)
    print(f"{kind}: {done} recorded")
    return 0 if done else 1


def _cli_inmail_credits(argv) -> int:
    ap = argparse.ArgumentParser(
        prog="state.py inmail-credits",
        description="Keep the InMail balance LinkedIn shows (used until the month turns), or "
                    "with no number, say what is left and where that number came from.")
    ap.add_argument("balance", nargs="?", type=int, default=None,
                    help="the InMail credits LinkedIn shows now")
    ap.add_argument("--contacts", default=CONTACTS_CSV)
    ap.add_argument("--threads", default=THREADS_CSV)
    ap.add_argument("--today", default=datetime.date.today().isoformat())
    a = ap.parse_args(argv)
    contacts, threads = load_contacts(a.contacts), load_threads(a.threads)
    if a.balance is not None:
        try:
            record_inmails(a.balance, contacts, threads, a.today)
        except ValueError as e:
            print(f"inmail-credits: not kept: {e}")
            return 1
        print(f"inmail-credits: kept {a.balance} as LinkedIn shows it on {a.today}. InMails "
              "sent from now take one each and a reply within "
              f"{INMAIL_REFUND_DAYS} days gives one back; the count from the log takes over "
              "again when the month turns")
    b = platform_budget(contacts, threads, a.today)
    print(f"InMail credits: {b['inmails_left']} left this month ({b['inmails_source']})")
    return 0


def _draft_of(cid: str) -> str | None:
    """Their queued draft's words, or None when there is none."""
    try:
        import reading
        with open(reading.draft_path(cid), encoding="utf-8") as fh:
            draft = fh.read()
    except (ImportError, OSError, ValueError):
        return None
    return reading.note_body(draft)


def _waits_on_read(cid: str) -> bool:
    """Is their queued draft the WAITS ON A READ placeholder?"""
    try:
        import reading
        return reading.waits_on_read(cid)
    except (ImportError, ValueError):
        return False


def _learn_edit(cid: str, sent_text: str, draft: str | None = None) -> None:
    """The person's own edit to a draft, recorded as a reaction by itself."""
    if draft is None:
        draft = _draft_of(cid)
        if draft is None:
            return
    try:
        import learned
        e = learned.record_edit(draft, sent_text, where=f"to {cid}")
    except (ImportError, SystemExit, OSError):
        return
    if e:
        print(f"  learned from the edit: {e['rule'][:200]}")


def _cli_resent(argv) -> int:
    ap = argparse.ArgumentParser(
        prog="state.py resent",
        description="Correct the message logged to them: another day, other words, a subject.")
    ap.add_argument("contact_id")
    ap.add_argument("--text-file", default="", help="the words as they went")
    ap.add_argument("--date", default="", help="the day it went")
    ap.add_argument("--subject", default="")
    ap.add_argument("--contacts", default=CONTACTS_CSV)
    ap.add_argument("--threads", default=THREADS_CSV)
    ap.add_argument("--today", default=datetime.date.today().isoformat())
    a = ap.parse_args(argv)
    text = _words_from(a.text_file, "resent") if a.text_file else ""
    if text is None:
        return 1
    contacts, threads = load_contacts(a.contacts), load_threads(a.threads)
    try:
        got = resent(contacts, threads, a.contact_id, a.today, text=text, date=a.date or None,
                     subject=a.subject)
    except ValueError as e:
        print(f"resent: not changed: {e}")
        return 1
    save_threads(threads, a.threads)
    save_contacts(contacts, a.contacts)
    if text and got["before"]:
        _learn_edit(a.contact_id, text, draft=got["before"])
    print(f"resent: {a.contact_id}: the message of {got['row']['date']} now holds what went")
    return 0


def _cli_unsend(argv) -> int:
    ap = argparse.ArgumentParser(
        prog="state.py unsend",
        description="It did not go: take the last message to them off the log, note back to draft.")
    ap.add_argument("contact_id")
    ap.add_argument("--contacts", default=CONTACTS_CSV)
    ap.add_argument("--threads", default=THREADS_CSV)
    ap.add_argument("--today", default=datetime.date.today().isoformat())
    a = ap.parse_args(argv)
    contacts, threads = load_contacts(a.contacts), load_threads(a.threads)
    try:
        got = unsend(contacts, threads, a.contact_id, a.today)
    except ValueError as e:
        print(f"unsend: not changed: {e}")
        return 1
    save_threads(threads, a.threads)
    save_contacts(contacts, a.contacts)
    print(f"unsend: {a.contact_id}: the message of {got['row'].get('date')} is off the log"
          + ("; its words are back in their draft" if got["draft"] else ""))
    return 0


def _cli_reopen_or_drop(argv, verb) -> int:
    ap = argparse.ArgumentParser(
        prog=f"state.py {verb}",
        description=("Bring back contacts nobody has written to." if verb == "reopen" else
                     "Set never-messaged contacts aside, reversibly."))
    ap.add_argument("contact_ids", nargs="*")
    ap.add_argument("--where", action="append", default=[],
                    help="FIELD=VALUE or FIELD~WORDS, as many as needed (company=<employer>, "
                         "outcome~never sent, status=dropped)")
    ap.add_argument("--reason", default="")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--contacts", default=CONTACTS_CSV)
    ap.add_argument("--threads", default=THREADS_CSV)
    ap.add_argument("--today", default=datetime.date.today().isoformat())
    a = ap.parse_args(argv)
    contacts, threads = load_contacts(a.contacts), load_threads(a.threads)
    ids = list(a.contact_ids)
    if a.where:
        try:
            ids += [c["contact_id"] for c in where(contacts, a.where) if c["contact_id"] not in ids]
        except ValueError as e:
            print(f"{verb}: {e}")
            return 1
    if not ids:
        print(f"{verb}: name the contact ids, or --where FIELD=VALUE")
        return 1
    fn = reopen if verb == "reopen" else drop
    done, failed = 0, 0
    for cid in ids:
        try:
            c = fn(contacts, threads, cid, a.today, a.reason)
        except ValueError as e:
            print(f"  not {verb}ed: {e}" if verb == "reopen" else f"  not dropped: {e}")
            failed += 1
            continue
        done += 1
        print(f"  {cid} ({c.get('name')}, {c.get('company')}): "
              + ("not_contacted again" if verb == "reopen" else "dropped, reversible with reopen"))
    if done and not a.dry_run:
        save_contacts(contacts, a.contacts)
    print(f"{verb}: {done} {'would change' if a.dry_run else 'changed'}"
          + (f", {failed} not" if failed else ""))
    return 0 if done else 1


def set_contact(contacts, threads, who, status=None, next_action=None, due=None, note="",
                today="") -> tuple[dict, list[str]]:
    """Change one contact's status, next action, its date, or add a dated note; returns the
    row and a line for each change. The book was edited by hand for want of this, and a note
    with line breaks in it broke the file (2026-10-21). A note stays on one line."""
    row = already_contacted(contacts, contact_id=who)
    if row is None:
        # A name two rows share names neither: the first one was changed, and it was the
        # wrong person as often as not (2026-10-21).
        want = _match_name(who)
        same = [c for c in contacts if want and _match_name(c.get("name")) == want]
        if len(same) > 1:
            raise ValueError(f"{len(same)} contacts are called {who!r}: name one by its id ("
                             + ", ".join(f"{c.get('contact_id')} at {c.get('company') or '?'}"
                                         for c in same) + ")")
        row = already_contacted(contacts, name=who)
    if not row:
        raise ValueError(f"no contact matching {who!r}")
    said = []
    if status is not None:
        status = status.strip()
        if status not in schema.THREAD_STATUSES:
            raise ValueError(f"{status!r} is not a status; one of: "
                             f"{', '.join(schema.THREAD_STATUSES)}")
        row["status"] = status
        shown = effective_status(row, threads_for(threads, row.get("contact_id", "")))
        said.append(f"status {status}" + ("" if shown == status else
                                          f" (the message log still shows {shown}: a reply "
                                          "owed, or a later message, outranks it)"))
    if next_action is not None:
        row["next_action"] = " ".join(next_action.split())
        said.append(f"next action: {row['next_action'] or '(none)'}")
    if due is not None:
        due = due.strip()
        if due and as_date(due) is None:
            raise ValueError(f"{due!r} is not a date: YYYY-MM-DD, or \"\" to clear it")
        row["next_action_due"] = due
        said.append(f"due {due or '(none)'}")
    if note.strip():
        line = f"{today or datetime.date.today().isoformat()}: {' '.join(note.split())}"
        _note(row, "notes", line)
        said.append(f"note added: {line}")
    if not said:
        raise ValueError("say what to change: --status, --next-action, --due or --note")
    return row, said


def _cli_set(argv) -> int:
    ap = argparse.ArgumentParser(prog="state.py set",
                                 description="Change one contact's status, next action, its "
                                             "date, or add a note, without editing the file.")
    ap.add_argument("contact", help="their contact_id, or their name")
    ap.add_argument("--status")
    ap.add_argument("--next-action", dest="next_action")
    ap.add_argument("--due", help="YYYY-MM-DD, or \"\" to clear it")
    ap.add_argument("--note", default="", help="added to their notes with today's date")
    ap.add_argument("--contacts", default=CONTACTS_CSV)
    ap.add_argument("--threads", default=THREADS_CSV)
    ap.add_argument("--today", default=datetime.date.today().isoformat())
    a = ap.parse_args(argv)
    contacts = load_contacts(a.contacts)
    threads = load_threads(a.threads) if os.path.exists(a.threads) else []
    try:
        row, said = set_contact(contacts, threads, a.contact, a.status, a.next_action, a.due,
                                a.note, a.today)
    except ValueError as e:
        print(f"set: {e}")
        return 1
    save_contacts(contacts, a.contacts)
    print(f"{row.get('contact_id')} ({row.get('name')}, {row.get('company')}): "
          + "; ".join(said))
    return 0


def _cli_no_reply(argv) -> int:
    ap = argparse.ArgumentParser(
        prog="state.py no-reply",
        description="Their last message needs no answer (they will come back to you): "
                    "nothing is owed until they write again or the day to look again.")
    ap.add_argument("contact", help="their contact_id, or their name")
    ap.add_argument("--why", required=True, help="why not, e.g. what they said")
    ap.add_argument("--look-again", dest="look_again", default="",
                    help="YYYY-MM-DD (default: the person's own follow-up rule)")
    ap.add_argument("--contacts", default=CONTACTS_CSV)
    ap.add_argument("--threads", default=THREADS_CSV)
    ap.add_argument("--today", default=datetime.date.today().isoformat())
    a = ap.parse_args(argv)
    contacts, threads = load_contacts(a.contacts), load_threads(a.threads)
    try:
        _row, said = no_reply(contacts, threads, a.contact, a.why, a.today,
                              a.look_again or None)
    except ValueError as e:
        print(f"no-reply: not changed: {e}")
        return 1
    save_contacts(contacts, a.contacts)
    print(said)
    return 0


def _cli_dropped_rows(argv) -> int:
    """`state.py dropped-rows [--apply]`: closed rows that were a queue set aside."""
    contacts, threads = load_contacts(), load_threads()
    rows = closed_but_dropped(contacts, threads)
    print(f"{len(rows)} closed contact(s) were never written to and say the note never went")
    for c in rows[:20]:
        print(f"  {c.get('contact_id')} ({c.get('company')}): {str(c.get('outcome'))[:90]}")
    if "--apply" in argv and rows:
        for c in rows:
            c["status"] = "dropped"
        save_contacts(contacts)
        print(f"dropped-rows: {len(rows)} moved from closed to dropped (reversible: "
              "state.py reopen <id> --reason ...)")
    return 0


# ---------------------------------------------------------------- a resume, asked for and sent

# A networking chat logged a contact's "can you send me your CV?", a drafting chat made
# the resume, the person emailed it, and the log said "Resume sent as asked": no file, no
# tracker row, no folder. Which resume a contact holds is the first thing an interview
# with them turns on, and the two chats had no shared word for it. The word is this
# marker, in a message row's summary, worded exactly as tools/network/export.py words an
# attachment LinkedIn's export records: "a resume attached (<file>)", or "an attachment
# attached (<file>)" for anything that is not a resume. The file is the path inside the
# repo (cv/<Prefix>_Resume_<ABBR>.pdf), so every chat finds the same one. No column: the
# summary is the row's own account of what went, and every reader already has it.
_ATTACHED = re.compile(r"\b(a (?:resume|r[eé]sum[eé]|cv)|an attachment) attached"
                       r"(?: \(([^()]*)\))?", re.I)
# What `attach --file unknown` writes: the person says a resume went and nobody kept which.
NOT_KEPT = "file not kept"
_DOC = r"(?:r[eé]sum[eé]|cv|curriculum vitae)"
_COVER = re.compile(r"cover[ _-]?letter", re.I)
# Where a sendable resume can sit: the app's own (cv/) and the person's own (documents/cv/).
RESUME_DIRS = ("cv/", "documents/cv/")
PERSON_ROUTES = frozenset({"referral", "recruiter", "contact"})


def noun() -> str:
    """The person's word for the document (person.json documents.noun): every line said
    to them uses it. "resume" with no profile."""
    try:
        return str(person.get("documents.noun", "resume") or "resume")
    except Exception:  # no profile: the app's word
        return "resume"


def _doc_rx() -> str:
    own = noun().lower()
    return _DOC if re.fullmatch(_DOC, own, re.I) else rf"(?:{_DOC}|{re.escape(own)})"


def is_resume_file(path) -> bool:
    """Is this file a resume (a CV), rather than a letter or anything else?

    By its name ("<Prefix>_Resume_Acme.pdf", "Morgan_Ellis_CV.pdf", "resume-2026.pdf"),
    or by where it sits (cv/, documents/cv/). A cover letter never is, wherever it sits."""
    p = str(path or "").replace("\\", "/").strip()
    base = os.path.basename(p)
    if not base or _COVER.search(base):
        return False
    words = re.compile(r"(?:^|[^a-z])" + _doc_rx().replace(" ", "[ _-]?") + r"(?:[^a-z]|$)", re.I)
    return bool(words.search(base)) or p.lstrip("./").startswith(RESUME_DIRS)


def attachment_note(path) -> str:
    """The marker a message row carries for a file that went with it."""
    what = "a resume" if is_resume_file(path) else "an attachment"
    return f"{what} attached ({path})"


def attached(row) -> list[str]:
    """The files a message row says went with it, from its marker. [] when none is named."""
    out = []
    for m in _ATTACHED.finditer(str((row or {}).get("summary") or "")):
        out += [f.strip() for f in str(m.group(2) or "").split(",") if f.strip()
                and not re.match(r"sent at \d{1,2}:\d{2}$", f.strip())]   # a repeat's time
    return out


def shown_summary(row) -> str:
    """A row's summary as a line says it, mid-sentence: its first word in lower case unless
    it is written in capitals ("CV sent", never "cv sent"), every other word as it is
    spelled ("LinkedIn's export"), and a resume it carries called by the person's own word
    ("a CV attached"). The stored marker stays the one word every reader shares (_ATTACHED):
    shown whole in lower case, a CV person read "cv sent (message), as asked; a resume
    attached" (2026-10-21)."""
    summary = str((row or {}).get("summary") or "")
    own = noun()
    first = re.match(r"[^\W\d_][\w'\u2019-]*", summary)
    word = first.group(0) if first else ""
    if word.lower() == own.lower():
        summary = own + summary[len(word):]            # their word, as they spell it
    elif word and not word.isupper() and word[1:] == word[1:].lower():
        summary = summary[:1].lower() + summary[1:]

    def said(m):
        if m.group(1).lower() == "an attachment":
            return m.group(0)
        return f"a {own} attached" + (f" ({m.group(2)})" if m.group(2) is not None else "")
    return _ATTACHED.sub(said, summary)


def _marked(row) -> list:
    return list(_ATTACHED.finditer(str((row or {}).get("summary") or "")))


def _is_message_out(row) -> bool:
    return (_direction(row) == "out" and not is_bare_request(row) and not is_withdrawal(row)
            and not is_call(row) and not is_acceptance(row))


def _sentences(text) -> list:
    """Its clauses: "Please find my CV attached, thank you for passing it on" is a CV sent
    and a thank-you, and read whole the thank-you hid the CV."""
    return [s for s in re.split(r"[.!?\n;,]+", str(text or "")) if s.strip()]


def _sent_rx():
    d = _doc_rx()
    return re.compile(
        rf"\b{d}\b[^.!?\n]{{0,40}}?\b(?:sent|emailed|e-mailed|attached|forwarded|shared|went)\b"
        r"|\b(?:sent|emailed|e-mailed|attached|attaching|forwarded|enclosed|enclosing|"
        rf"here(?:'s| is)|please find)\b[^.!?\n]{{0,30}}?\b{d}\b", re.I)


# A sentence about a resume that went earlier, or one that is only offered: "following up
# on the resume I sent", "thanks for passing my CV on", "I'll send my CV tonight".
_NOT_THIS_ONE = re.compile(
    r"\bfollow(?:ing|ed)?[ -]?up on\b|\bthank(?:s| you)\b[^.!?\n]{0,30}\b(?:pass|passing|"
    r"forward|forwarding|sharing|for)\b|\b(?:will|I'?ll|can|happy to|shall I|should I|"
    r"want me to)\s+(?:send|share|email|forward)\b"
    r"|\b(?:not|never|haven'?t|hasn'?t|didn'?t|without)\b"
    # A resume that went to the employer, or sits on their profile, never reached the
    # contact: "my CV went through the portal this morning", "I applied with my CV", "my
    # CV is attached to my LinkedIn profile" each closed a resume owed (2026-10-21).
    r"|\bthrough\s+(?:the|your|their|its)\s+(?:[\w'-]+\s+)?(?:portal|careers?\s+(?:site|"
    r"page|portal)|website|site|system|ats|application\s+form)\b"
    r"|\bapplied\b(?!\s+(?:the|your|their|those|these|all|some)\s+(?:[\w'-]+\s+)?"
    r"(?:changes|edits|feedback|suggestions|tips|comments|notes)\b)"
    r"|\b(?:to|on)\s+my\s+(?:linkedin\s+)?profile\b", re.I)


def says_resume_went(row) -> bool:
    """Does this message row of ours say a resume went with it, by its marker, its
    scenario or its words?

    A message about a resume that went before ("following up on the CV I sent") is not one,
    and nor is an offer of one ("happy to send my CV")."""
    if not _is_message_out(row):
        return False
    if any(m.group(1).lower() != "an attachment" for m in _marked(row)):
        return True
    if _scenario(row) == "send_resume":
        return True
    sent = _sent_rx()
    for field in ("summary", "full_text"):
        for s in _sentences(row.get(field)):
            if sent.search(s) and not _NOT_THIS_ONE.search(s):
                return True
    return False


def names_a_file(row) -> bool:
    """Does the row name the file that went (or say nobody kept it)?"""
    return bool(attached(row))


def asks_for_resume(row) -> bool:
    """Is this message of theirs a request for the resume itself (not a profile, not their
    address in a signature)? The reply classifier's own cue, `reply.asks_for_resume`."""
    if not said_something(row):
        return False
    if _scenario(row) == "send_resume":
        return True
    try:
        import reply
    except Exception:  # noqa: BLE001  the scenario alone, without the classifier
        return False
    return reply.asks_for_resume(str(row.get("full_text") or row.get("summary") or ""))


# The person saying a resume will not go: "CV not sent: applied through the portal".
# `state.py set <id> --note "<noun> not sent: <why>"` writes it with the day in front. The
# colon is part of it: "CV not sent yet" in a next action is a reminder, not a decision.
def _settled_rx():
    return re.compile(rf"\b{_doc_rx()}\s+not\s+(?:sent|going|needed|owed)\s*:", re.I)


def resume_settled_on(contact):
    """When the person said a resume will not go to them, from the row's notes or outcome:
    the day written in front of it, True for an undated one, None when never."""
    rx, when = _settled_rx(), None
    for field in ("notes", "outcome"):
        for chunk in re.split(r"[;|]", str((contact or {}).get(field) or "")):
            if rx.search(chunk):
                d = as_date(chunk)
                if d is None:
                    return True
                when = max(when, d) if when else d
    return when


def _settled_since(contact, day) -> bool:
    got = resume_settled_on(contact)
    return got is True or (got is not None and (day is None or got >= day))


def resumes_sent(threads, contact_id) -> list[dict]:
    """Every message to them that says a resume went: {date, files, row}, oldest first."""
    return [{"date": str(r.get("date") or ""), "files": attached(r), "row": r}
            for r in threads_for(threads, contact_id) if says_resume_went(r)]


def _owed_note_file(contact) -> str:
    """The file a "<noun> to send: <path>" note on the row names (stage_picks.py single
    --for-contact writes one when no role was named), or ""."""
    m = re.search(rf"\b{_doc_rx()} to send:\s*(\S+)", str((contact or {}).get("notes") or ""),
                  re.I)
    return m.group(1).rstrip(".,;") if m else ""


def _row_records_resume(contact) -> bool:
    """Does the contact row already say a resume is owed: its next action names one, or a
    "<noun> to send" note does? Then the book and the log agree, and it is on the to-do list."""
    return bool(re.search(rf"\b{_doc_rx()}\b", str(contact.get("next_action") or ""), re.I)
                or _owed_note_file(contact))


# The two routes a resume made for a contact takes, said one way everywhere: staging,
# the tracker row's notes (record_drafts.made_for_note), outreach.md and RECONCILE.
# "Apply through the careers site and put me down as your referrer" is the portal route:
# the resume goes in through the portal with their name in its referral field and never
# to them, so no message of the person's ever logs it, and RECONCILE asked for one that
# never happens (2026-10-21). Any other ask is the route to them.
ROUTE_PORTAL, ROUTE_TO_THEM = "portal", "them"
ROUTE_WORDS = {
    ROUTE_PORTAL: "it goes in through the portal, with their name where it asks for a "
                  "referrer, not to them",
    ROUTE_TO_THEM: "it goes to them, not through the portal",
}


def route_words(route) -> str:
    """How a resume made for a contact goes, in the words every place says it in."""
    return ROUTE_WORDS[ROUTE_PORTAL if route == ROUTE_PORTAL else ROUTE_TO_THEM]


def through_portal(row) -> bool:
    """Does this tracker row say its resume goes in through the portal under the contact's
    name (the portal route's words, the later of the two when a redraft added both)?"""
    notes = " ".join(str((row or {}).get("notes") or "").split()).lower()
    portal = notes.rfind(ROUTE_WORDS[ROUTE_PORTAL].lower())
    return portal >= 0 and portal > notes.rfind(ROUTE_WORDS[ROUTE_TO_THEM].lower())


def resume_route(threads, contact_id) -> str:
    """How a resume for this contact goes, from what they said last about it: the portal
    route when their latest message that asks for the resume or names a referral field
    names the field, else the route to them."""
    try:
        import reply
    except Exception:  # noqa: BLE001  the classifier unavailable: the route to them
        return ROUTE_TO_THEM
    for r in reversed(threads_for(threads, contact_id)):
        if not said_something(r):
            continue
        text = str(r.get("full_text") or r.get("summary") or "")
        if reply.REFERRAL_FIELD.search(text):
            return ROUTE_PORTAL
        if asks_for_resume(r):
            return ROUTE_TO_THEM
    return ROUTE_TO_THEM


def made_for(row, contacts) -> dict | None:
    """The contact a tracker row's documents were made for, or who leads its process.

    Read from the row's own words: "made for <name> (<contact_id>)" in its notes
    (record_drafts.py writes it for a resume drafted with --for-contact), a `contact:<id>`
    source (a process with no application), or, on a row filed under a person's route
    (channel referral, recruiter or contact), its contact_person at that employer."""
    row = row or {}
    notes = str(row.get("notes") or "")
    m = re.search(r"\bmade for [^;|()]*\(([^()\s]+)\)", notes, re.I)
    src = str(row.get("source") or "").strip()
    cid = m.group(1) if m else (src.split(":", 1)[1].strip() if src.startswith("contact:") else "")
    if cid:
        return already_contacted(contacts, contact_id=cid)
    channel = str(row.get("channel") or "").strip().lower()
    who = _match_name(row.get("contact_person"))
    if channel not in PERSON_ROUTES or not who:
        return None
    k = company_key(row.get("company"))
    for c in contacts:
        if row_company_key(c) == k and _match_name(c.get("name")) == who:
            return c
    return None


def _resume_stem(path) -> str:
    return os.path.splitext(os.path.basename(str(path or "").strip()))[0].lower()


def made_for_rows(tracker, contacts, contact_id) -> list[dict]:
    """The tracker rows with a resume made for this contact, newest first."""
    return list(made_for_index(tracker, contacts).get(contact_id, ()))


def made_for_index(tracker, contacts) -> dict[str, list[dict]]:
    """`made_for_rows` for every contact at once: contact_id -> the tracker rows with a
    resume made for them, newest first. Each row is matched to its contact once, where a
    loop over the book calling `made_for_rows` matched every row once a contact (66,000
    matches on 1,300 contacts, 2026-10-23)."""
    out: dict[str, list] = {}
    for r in tracker or ():
        if not str(r.get("cv_file") or "").strip():
            continue
        cid = (made_for(r, contacts) or {}).get("contact_id")
        if cid is not None:
            out.setdefault(cid, []).append(r)
    for rows in out.values():
        rows.sort(key=lambda r: as_date(r.get("date")) or datetime.date.min, reverse=True)
    return out


def _pdf(path) -> str:
    return os.path.splitext(str(path or "").strip())[0] + ".pdf"


def resumes_owed(contacts, threads, tracker=None) -> list[dict]:
    """Every contact owed a resume: their last request for it has had none since, or one
    was drafted for them (a tracker row not yet past drafted) and none has gone since.

    Owed from their request (`asks_for_resume`), or the day it was made, until a message
    of ours says a resume went (`says_resume_went`), or the person says one will not
    (`resume_settled_on`). A thread the person closed owes nothing. Each: {contact_id,
    name, company, company_key, asked, made, role, words, file, recorded}: `file` is the
    one to send where the repo knows it (a resume made for them, or the "<noun> to send"
    note), `recorded` whether the book already says it is owed (their row, or the
    tracker's row for the one made for them)."""
    out = []
    index, made_index = by_contact(threads), made_for_index(tracker, contacts)
    for contact in contacts:
        cid = str(contact.get("contact_id") or "").strip()
        if str(contact.get("status") or "").strip() in ("closed", "gone_cold", "dropped"):
            continue
        rows = _rows_of(index, cid)
        made_rows = list(made_index.get(cid, ()))
        sent_on = [as_date(r.get("date")) or datetime.date.min
                   for r in rows if says_resume_went(r)]
        base = {"contact_id": cid, "name": contact.get("name", ""),
                "company": contact.get("company", ""), "company_key": row_company_key(contact),
                "asked": "", "made": "", "role": "", "words": ""}
        ask_at = next((i for i in range(len(rows) - 1, -1, -1) if asks_for_resume(rows[i])),
                      None)
        asked = as_date(rows[ask_at].get("date")) if ask_at is not None else None
        # "Send me your CV", then "apply and put me down as your referrer": the later word
        # sends it through the portal, so nothing is owed to them.
        if (ask_at is not None and not any(says_resume_went(r) for r in rows[ask_at + 1:])
                and not _settled_since(contact, asked)
                and resume_route(rows, cid) != ROUTE_PORTAL):
            made = [r for r in made_rows
                    if (as_date(r.get("date")) or datetime.date.min) >= (asked or datetime.date.min)]
            words = " ".join(str(rows[ask_at].get("full_text") or rows[ask_at].get("summary")
                                 or "").split())
            out.append(dict(base, asked=asked.isoformat() if asked else "",
                            words=words if len(words) <= 120 else words[:117].rstrip() + "...",
                            file=_pdf(made[0]["cv_file"]) if made else _owed_note_file(contact),
                            recorded=_row_records_resume(contact),
                            made_on=max((str(r.get("date") or "") for r in made), default="")))
            continue
        for r in made_rows:
            day = as_date(r.get("date"))
            # Made for them to go in through the portal under their name: owed to nobody.
            if (str(r.get("status") or "").strip().lower() not in _THROTTLE_UNSENT
                    or any(d >= (day or datetime.date.min) for d in sent_on)
                    or _settled_since(contact, day) or through_portal(r)):
                continue
            out.append(dict(base, made=day.isoformat() if day else "",
                            role=str(r.get("role") or "").strip(), file=_pdf(r["cv_file"]),
                            recorded=True))
            break
    return out


def log_resume_command(contact_id, file="", channel="") -> str:
    """The one command that logs a resume that went, with its file."""
    return (f"python3 tools/network/state.py message {contact_id} --attached "
            f"{file or '<the file that went>'} --text-file <the message as sent>"
            + (f" --channel {channel}" if channel else ""))


def resume_owed_line(item, mark="") -> str:
    """"a resume owed to <name> (asked <date>): ..." for the due list and the employer view;
    `mark` ("**") wraps the part that says who is owed what."""
    made = (f" (made {item['made']} for {item.get('role') or 'their role'})"
            if item.get("made") else "")
    return (f"{mark}a {noun()} owed to {item['name'] or item['contact_id']}{mark}"
            + (f" (asked {item['asked']})" if item.get("asked") else made)
            + ": send it, then log it with the file: "
            + log_resume_command(item["contact_id"], item.get("file")))


@functools.lru_cache(maxsize=4)
def _general_resume_dates(root: str) -> tuple:
    """((path now, the day it first arrived, the day it went or "", on disk), ...) for each
    general resume documents/cv/ has ever held: the ones not made for one employer. A file
    renamed keeps the day it arrived, under its name now; a file deleted is kept, with the
    day it went, so it is never passed over for an older one."""
    try:
        log = subprocess.run(["git", "-C", root, "log", "--reverse", "-M", "--diff-filter=ADR",
                              "--format=%x00%ad", "--date=short", "--name-status", "--",
                              RESUME_DIRS[1]],
                             capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=20).stdout
    except (OSError, subprocess.SubprocessError):
        return ()
    arrived: dict = {}
    gone: dict = {}
    day = ""
    for line in log.splitlines():
        if line.startswith("\0"):
            day = line[1:].strip()
            continue
        f = line.split("\t")
        if len(f) < 2:
            continue
        kind, paths = f[0][:1], [x.strip() for x in f[1:]]
        if kind == "A":
            arrived[paths[0]] = day
            gone.pop(paths[0], None)
        elif kind == "R" and len(paths) == 2:
            arrived[paths[1]] = arrived.pop(paths[0], day)
            gone.pop(paths[1], None)
        elif kind == "D" and paths[0] in arrived:
            gone[paths[0]] = day
    return tuple((p, d, gone.get(p, ""), os.path.isfile(os.path.join(root, p)))
                 for p, d in arrived.items() if is_resume_file(p))


def general_resumes_on(day: str, root: str | None = None) -> list[str]:
    """The person's general resumes that were newest on `day`, by when each arrived, under
    the names they have now. A message that says one went, to somebody nothing was made
    for, carried one of these. [] when there is no history to read (no git, or a copy of the
    state outside it), and when the newest they had then is no longer there: an older one
    is never offered in its place."""
    day = str(day or "")
    held = [(d, p, here) for p, d, went, here in
            _general_resume_dates(os.path.normpath(root or person.state()))
            if d and d <= day and not (went and went <= day)]
    if not held:
        return []
    newest = max(d for d, _, _ in held)
    top = [(p, here) for d, p, here in held if d == newest]
    return sorted(p for p, _ in top) if all(here for _, here in top) else []


def resume_findings(contacts, threads, tracker=None, reasons=None) -> list[dict]:
    """The three places a resume and the log disagree, each with the command that settles it.

    `resume_file_not_named`: a message says a resume went and names no file.
    `resume_not_logged`: a tracker row says a resume made for a contact went (its status is
    past drafted), and no message to them since says it reached them.
    `resume_owed`: they asked for it, none has gone since, and their row does not say so.
    Each is settled for good by what it asks for: the file named, the message logged, the
    row saying it is owed, or the person's "<noun> not sent: <why>" note. `reasons` keeps
    only those."""
    word = noun()
    found = []

    def add(contact, reason, detail):
        found.append({"contact_id": str(contact.get("contact_id") or "").strip(),
                      "name": contact.get("name", ""), "stored": "", "derived": "",
                      "reason": reason, "detail": detail})

    by_id = {str(c.get("contact_id") or "").strip(): c for c in contacts}
    # One pass over the log for the book: threads_for per contact read the whole log once a
    # contact, 25 of state.py's 29 seconds on 2,000 contacts (networking audit, 2026-10-25).
    index = by_contact(threads)
    for cid, contact in by_id.items():
        made = None
        for r in _rows_of(index, cid):
            if says_resume_went(r) and not names_a_file(r):
                if made is None:
                    made = [str(row.get("cv_file") or "").strip() for row in tracker or ()
                            if str(row.get("cv_file") or "").strip() and made_for(row, [contact])]
                day = str(r.get("date") or "").strip()
                attach_cmd = f"python3 tools/network/state.py attach {cid} --date {day} --file"
                likely = [] if made else general_resumes_on(day)
                if len(likely) == 1:
                    say = (f"nothing was made for them, so it was most likely your general "
                           f"{word}, the newest you had then: {attach_cmd} "
                           f"{shlex.quote(likely[0])} (or "
                           "the file that went; --file unknown if nobody kept it)")
                elif likely:
                    say = (f"nothing was made for them, so it was most likely one of the "
                           f"general {word}s you had then ({', '.join(likely)}): "
                           f"{attach_cmd} <the one that went> (--file unknown if nobody "
                           "kept it)")
                else:
                    say = (f"name it: {attach_cmd} <the file that went> (--file unknown if "
                           "nobody kept it)")
                add(contact, "resume_file_not_named",
                    f"the message of {day} says a {word} went but not which file: {say}")
    for row in tracker or ():
        status = str(row.get("status") or "").strip().lower()
        cv = str(row.get("cv_file") or "").strip()
        if not cv or not status or status in _THROTTLE_UNSENT or status in TRACKER_FINAL:
            continue
        contact = made_for(row, contacts)
        if contact is None:
            continue
        cid = str(contact.get("contact_id") or "").strip()
        # The portal route: it went in through the portal under their name, never to them,
        # so there is no message to log. Said by the row, or by what they asked for last.
        mine = _rows_of(index, cid)
        if through_portal(row) or resume_route(mine, cid) == ROUTE_PORTAL:
            continue
        day = as_date(row.get("date"))
        stem = _resume_stem(cv)
        went = [s for s in resumes_sent(mine, cid)
                if (as_date(s["date"]) or datetime.date.min) >= (day or datetime.date.min)
                or stem in {_resume_stem(f) for f in s["files"]}]
        if went or _settled_since(contact, day):
            continue
        add(contact, "resume_not_logged",
            f"the {word} for {row.get('role') or 'the role'} at {row.get('company')} was made "
            f"for them and the tracker says it went ({status}), but nothing in their thread "
            f"says it reached them: log it: {log_resume_command(cid, _pdf(cv))}. If it did not "
            f"go to them: state.py set {cid} --note \"{word} not sent: <why>\"")
    for item in resumes_owed(contacts, threads, tracker):
        if item["recorded"]:
            continue
        cid = item["contact_id"]
        add(by_id.get(cid, item), "resume_owed",
            f"they asked for your {word} on {item['asked'] or 'an unknown date'} and none has "
            f"gone since, and their row does not say it is owed: send it, then log it: "
            f"{log_resume_command(cid, item['file'])}. Not sending it: state.py set {cid} "
            f"--note \"{word} not sent: <why>\"")
    return [f for f in found if reasons is None or f["reason"] in reasons]


def resolve_attachment(path, root=None) -> str:
    """The file that went, as a path inside the repo, or ValueError saying what to do.

    It must be in this copy of the repo, named by a kept application (a draft.json in
    documents/applications/ names its resume and letter), or carry the name the app gives
    this person's resume or letter (cv/<Prefix>_<Noun>_<ABBR>.pdf): a drafting chat
    working at the same time may have made it, and it arrives when both chats' work is
    merged. A file outside the repo is refused: no other chat could ever find it."""
    root = os.path.normpath(root or person.state())
    raw = str(path or "").strip()
    if not raw:
        raise ValueError("name the file that went: --attached <file>")
    raw = os.path.expanduser(raw)
    tries = [raw] if os.path.isabs(raw) else [os.path.join(root, raw), os.path.abspath(raw)]
    for full in tries:
        full = os.path.normpath(full)
        if os.path.isfile(full):
            rel = os.path.relpath(full, root)
            if rel.startswith(".."):
                raise ValueError(f"{raw} is outside this repo, so no other chat could find it: "
                                 f"copy it into documents/cv/ and name that")
            return rel.replace(os.sep, "/")
    rel = raw.replace("\\", "/").lstrip("./") if not os.path.isabs(raw) else raw
    if rel in _kept_outputs(root):
        return rel
    try:
        import docpaths
        made = (docpaths.resume_name_rx().search(os.path.basename(rel))
                or re.search(re.escape(docpaths.prefix()) + r"_Cover_Letter_", rel))
    except Exception:  # noqa: BLE001  no profile: only a file that is there
        made = None
    if made and rel.startswith(("cv/", "cover_letters/")):
        return rel
    raise ValueError(f"no file {raw} in this repo, and no kept application names it: give "
                     "the path as it sits here (cv/<name>.pdf, documents/cv/<name>.pdf)")


def _kept_outputs(root) -> set:
    """Every resume and letter a kept application in documents/applications/ names."""
    out = set()
    base = os.path.join(root, "documents", "applications")
    try:
        folders = sorted(os.listdir(base))
    except OSError:
        return out
    try:
        import docpaths
    except Exception:  # noqa: BLE001
        return out
    for d in folders:
        try:
            with open(os.path.join(base, d, "draft.json"), encoding="utf-8") as fh:
                got = json.load(fh)
        except (OSError, ValueError):
            continue
        for draft in got if isinstance(got, list) else [got]:
            abbr = str((draft or {}).get("abbr") or "").strip() if isinstance(draft, dict) else ""
            if abbr:
                for ext in (".pdf", ".tex"):
                    out.add(docpaths.resume_rel(abbr, ext))
                    out.add(docpaths.letter_rel(abbr, ext))
    return out


def attach(threads, contact_id, date, path, root=None) -> dict:
    """Name the file that went with a message already logged: the one message of ours to
    them on that day that says a resume went and names none (or the only one that day).
    With no `date`, the newest day one of ours went to them: the file is most often named
    just after the message was logged, and needing its date sent a chat to a note instead
    (2026-10-24). `path` "unknown" says nobody kept it. The row is changed in place; the
    caller saves."""
    cid = str(contact_id or "").strip()
    if not date:
        days = [as_date(r.get("date")) for r in threads
                if str(r.get("contact_id") or "").strip() == cid and _is_message_out(r)]
        days = [d for d in days if d is not None]
        if not days:
            raise ValueError(f"no message to {cid} is logged: log the one that carried it, "
                             f"with its words: {log_resume_command(cid, path)}")
        date = max(days)
    day = _need_date(date, "date").isoformat()
    rows = [r for r in threads if str(r.get("contact_id") or "").strip() == cid
            and _is_message_out(r) and str(r.get("date") or "").strip() == day]
    if not rows:
        raise ValueError(f"no message to {cid} on {day} is logged: log the one that carried it, "
                         f"with its words: {log_resume_command(cid, path)} --date {day}")
    open_ = [r for r in rows if not names_a_file(r)]
    if not open_:
        raise ValueError(f"the message to {cid} on {day} already names "
                         f"{', '.join(attached(rows[0]))}")
    pick = [r for r in open_ if says_resume_went(r)] or open_
    if len(pick) > 1:
        raise ValueError(f"{len(pick)} messages to {cid} on {day} could be the one: name the "
                         "file in the right one's summary by hand")
    row = pick[0]
    unknown = str(path or "").strip().lower() in ("unknown", "not kept", NOT_KEPT)
    rel = NOT_KEPT if unknown else resolve_attachment(path, root)
    what = "a resume" if (unknown or is_resume_file(rel)) else "an attachment"
    note = f"{what} attached ({rel})"
    summary = str(row.get("summary") or "").strip()
    bare = [m for m in _marked(row) if not m.group(2)]
    if bare:
        m = bare[0]
        summary = summary[:m.start()] + note + summary[m.end():]
    else:
        summary = "; ".join(x for x in (summary, note) if x)
    row["summary"] = summary
    if what == "a resume" and _scenario(row) in ("", "reply"):
        row["scenario"] = "send_resume"
    return row


def _cli_attach(argv) -> int:
    ap = argparse.ArgumentParser(
        prog="state.py attach",
        description="Name the file that went with a message already logged.")
    ap.add_argument("contact_id")
    ap.add_argument("file", nargs="?", default="",
                    help="the file as it sits in the repo, or unknown if nobody kept it")
    ap.add_argument("--date", default="",
                    help="the day it went, as logged (default: the newest message of ours to them)")
    ap.add_argument("--file", dest="file_opt", default="", help="the same as the file above")
    ap.add_argument("--threads", default=THREADS_CSV)
    a = ap.parse_args(argv)
    path = a.file or a.file_opt
    if not path:
        print("attach: not changed: name the file that went (or unknown if nobody kept it)")
        return 1
    threads = load_threads(a.threads)
    try:
        row = attach(threads, a.contact_id, a.date or None, path)
    except ValueError as e:
        print(f"attach: not changed: {e}")
        return 1
    save_threads(threads, a.threads)
    print(f"attach: the message to {a.contact_id} on {row['date']} now says: {row['summary']}")
    return 0


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


def link_to_applications(contacts, tracker_rows, threads=None) -> list[dict]:
    """Contacts that have an application at the same employer, and which one.

    This is the integration the brief asks for: a thread and an application at
    one company are two views of the same pursuit, and the contact row's
    `linked_application` column is what carries it. Matching on `company_key`
    rather than the company string is what makes a contact recorded under an
    employer's legal name find the application filed under its initials.

    With `threads`, each link also carries `resumes_sent` (`resumes_sent`): which resume
    went to them and when, read from the message that carried it.
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
            "resumes_sent": ([{"date": s["date"], "files": s["files"]} for s in
                              resumes_sent(threads, contact.get("contact_id"))]
                             if threads is not None else []),
        })
    return out


# ---------------------------------------------------------------- platform limits


def _month_end(day: datetime.date) -> datetime.date:
    if day.month == 12:
        return day.replace(day=31)
    return day.replace(month=day.month + 1, day=1) - datetime.timedelta(days=1)


# A scenario that says the row was the request itself, which settles it
# whatever came before: an email reply is not a LinkedIn connection.
_REQUEST_SCENARIOS = frozenset({"connection_request", "connection_note", "invite", "invitation",
                                "request_outside"})


# Scenarios that only happen inside a conversation already under way. Such a
# message is never a connection request and never an opener.
MID_CONVERSATION = frozenset({"reply", "send_resume", "thank_you", "scheduling", "accept_call",
                              "follow_up", "referral_ask", "ask_referral", "call_held",
                              "call_missed", "intro_connection", "warm_intro_reply"})


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
            if channel_of(row) != "connection" or is_withdrawal(row):
                continue
            if _direction(row) == "in":
                connected = True
                continue
            if _direction(row) != "out":
                continue
            scenario = re.sub(r"[\s-]+", "_", str(row.get("scenario") or "").strip().lower())
            day = as_date(row.get("date"))
            # A reply, a thank-you or a scheduling note goes down a channel that
            # is already open: a catch-up message to a relationship older than
            # the log was counted as a request and spent the week's budget.
            if day and (scenario in _REQUEST_SCENARIOS
                        or not (connected or asked or scenario in MID_CONVERSATION)):
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


# InMail credits come back. LinkedIn's own help, read through a web search on 2026-10-20
# (linkedin.com is never fetched from a session): "Every InMail message that is
# accepted/declined or responded to directly within 90 days of it being sent is credited
# back", and "A pending InMail message isn't counted as either accepted or declined"
# ("InMail message credits and renewal process", linkedin.com/help/linkedin/answer/a541643;
# the Sales Navigator page, answer/57013, says the same of its credits). The same page says
# a new allotment comes "every month, on the first day of your billing cycle", which need
# not be the first of the calendar month. Whether unused Premium credits carry into the
# next month could NOT be confirmed (third-party guides disagree), and a message to an Open
# Profile spends no credit at all, which the log cannot see. So the count from the log is
# a floor: after five InMails it said "0 of 5 left" while LinkedIn showed 3. The balance
# LinkedIn shows, kept with `state.py inmail-credits <n>`, wins until the month turns.
INMAIL_REFUND_DAYS = 90
INMAIL_FILE = ("documents", "network", ".inmail_credits.json")
_LINKEDIN_CHANNELS = frozenset({"inmail", "open_profile", "connection", "message", ""})


def _inmail_sends(contacts, threads) -> set:
    """(contact_id, day) for every InMail that went, from the log and the contact rows."""
    out = set()
    for row in threads:
        if _direction(row) == "out" and channel_of(row) == "inmail" and as_date(row.get("date")):
            out.add((str(row.get("contact_id") or "").strip(), as_date(row.get("date"))))
    for contact in contacts:
        if channel_of(contact) == "inmail" and as_date(contact.get("first_contacted")):
            out.add((str(contact.get("contact_id") or "").strip(),
                     as_date(contact.get("first_contacted"))))
    return out


def inmail_refunds(threads) -> list:
    """[(contact_id, the day the InMail went, the day the reply credited it back)]: every
    InMail answered on LinkedIn within INMAIL_REFUND_DAYS of going. An acceptance of a
    connection request or a call is not an answer to it; an email reply is not on LinkedIn."""
    by: dict[str, list] = {}
    for row in threads:
        by.setdefault(str(row.get("contact_id") or "").strip(), []).append(row)
    out = []
    for cid, rows in by.items():
        rows = _ordered(rows)
        for i, row in enumerate(rows):
            day = as_date(row.get("date"))
            if _direction(row) != "out" or channel_of(row) != "inmail" or not day:
                continue
            for later in rows[i + 1:]:
                back = as_date(later.get("date"))
                if (said_something(later) and channel_of(later) in _LINKEDIN_CHANNELS and back
                        and day <= back <= day + datetime.timedelta(days=INMAIL_REFUND_DAYS)):
                    out.append((cid, day, back))
                    break
    return out


def _inmail_path() -> str:
    return person.state(*INMAIL_FILE)


def recorded_inmails(today) -> dict:
    """The InMail balance the person read off LinkedIn this month, or {} (none, or the month
    has turned since: a new allotment came, and the count from the log takes over again)."""
    today = _need_date(today, "today")
    try:
        with open(_inmail_path(), encoding="utf-8") as fh:
            got = json.load(fh)
    except (OSError, ValueError):
        return {}
    day = as_date((got or {}).get("date")) if isinstance(got, dict) else None
    if not day or (day.year, day.month) != (today.year, today.month) or day > today:
        return {}
    try:
        int(got.get("balance"))
    except (TypeError, ValueError):
        return {}
    return got


def record_inmails(balance, contacts, threads, today) -> dict:
    """Keep the InMail balance LinkedIn shows, with the day and what the log held then, so
    only InMails sent and credits returned after it move it. Used until the month turns."""
    today = _need_date(today, "today")
    n = int(balance)
    if n < 0:
        raise ValueError("an InMail balance is a count, 0 or more")
    rec = {"balance": n, "date": today.isoformat(),
           "inmails": sorted(f"{c}|{d.isoformat()}" for c, d in _inmail_sends(contacts, threads)),
           "refunds": sorted(f"{c}|{s.isoformat()}|{r.isoformat()}"
                             for c, s, r in inmail_refunds(threads))}
    path = _inmail_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(rec, fh, indent=1)
        fh.write("\n")
    return rec


def _inmails_left(contacts, threads, today, month_start, month_end, limit, recorded) -> dict:
    sends = _inmail_sends(contacts, threads)
    refunds = inmail_refunds(threads)
    sent_month = sum(1 for _, d in sends if month_start <= d <= month_end)
    back_month = sum(1 for _, _, r in refunds if month_start <= r <= min(month_end, today))
    if recorded:
        since = as_date(recorded.get("date")) or today
        had_sends, had_back = set(recorded.get("inmails") or ()), set(recorded.get("refunds") or ())
        new = sum(1 for c, d in sends if d >= since and f"{c}|{d.isoformat()}" not in had_sends)
        back = sum(1 for c, s, r in refunds if since <= r <= today
                   and f"{c}|{s.isoformat()}|{r.isoformat()}" not in had_back)
        left = max(int(recorded["balance"]) - new + back, 0)
        source = (f"the {recorded['balance']} LinkedIn showed on {since.isoformat()}"
                  + (f", less {new} sent since" if new else "")
                  + (f", plus {back} credited back since" if back else ""))
    else:
        left = max(min(limit, limit - sent_month + back_month), 0)
        source = (f"counted from the log: {sent_month} sent this month"
                  + (f", {back_month} credited back for a reply within {INMAIL_REFUND_DAYS} days"
                     if back_month else "")
                  + "; if LinkedIn shows another number, keep it: state.py inmail-credits <n>")
    return {"inmails_sent": sent_month, "inmails_refunded": back_month, "inmails_left": left,
            "inmails_source": source}


def platform_budget(contacts, threads, today, inmail_balance=None) -> dict:
    """Connection requests sent, and InMail credits left, against `schema.LIMITS`. The app
    sets no cap on connection requests (2026-10-22): LinkedIn says when its own is reached.

    Counted from the contact rows as well as the message log, deduplicated on
    person, channel and date. A discovery run writes the contact row with its
    `first_contacted` date at the moment the request goes out and the thread row
    lands afterwards, so counting only the log reports a budget the user has
    already spent. Connections are what `connection_requests` says went out as
    a request; a message to somebody already connected spends nothing.

    InMail credits: an InMail answered within INMAIL_REFUND_DAYS gives its credit back,
    and the balance the person read off LinkedIn this month (`record_inmails`) wins over
    the count. `inmail_balance` is that record ({} for none); None reads it from file.
    """
    today = _need_date(today, "today")
    week_start = today - datetime.timedelta(days=today.weekday())
    week_end = week_start + datetime.timedelta(days=6)
    month_start = today.replace(day=1)
    month_end = _month_end(today)

    requests = connection_requests(contacts, threads)
    connections = sum(1 for _, d in requests if week_start <= d <= week_end)
    connections_today = sum(1 for _, d in requests if d == today)
    inmail_limit = schema.LIMITS["inmail_credits_per_month"]
    inmail = _inmails_left(contacts, threads, today, month_start, month_end, inmail_limit,
                           recorded_inmails(today) if inmail_balance is None else inmail_balance)
    # Drafts queued and not yet sent, reported beside the counts.
    queued = {"connection": 0, "inmail": 0}
    for contact in contacts:
        if (str(contact.get("status") or "").strip() == "not_contacted"
                and channel_of(contact) in queued):
            queued[channel_of(contact)] += 1
    # A free account's personalised notes run out within the month; after that a
    # request goes without a note and the message follows the acceptance.
    notes_limit = schema.LIMITS.get("personal_notes_per_month")
    # Only a request that carried a note spends one: five requests sent with no note said
    # "this month's personalised notes are used up" (2026-10-21). A request whose words were
    # not seen, or whose row the log has not reached yet, may have had one and counts.
    bare = {(str(r.get("contact_id") or "").strip(), as_date(r.get("date")))
            for r in threads if is_bare_request(r)}
    noted = {(str(r.get("contact_id") or "").strip(), as_date(r.get("date")))
             for r in threads if is_request(r) and not is_bare_request(r)}
    notes_sent = sum(1 for cid, d in requests if month_start <= d <= month_end
                     and ((cid, d) in noted or (cid, d) not in bare))
    notes_left = None if notes_limit is None else max(notes_limit - notes_sent, 0)
    note = NO_NOTES_LEFT if notes_left == 0 else ""
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
        "connections_today": connections_today,
        "inmails_sent": inmail["inmails_sent"],
        "inmails_limit": inmail_limit,
        "inmails_left": inmail["inmails_left"],
        "inmails_refunded": inmail["inmails_refunded"],
        "inmails_source": inmail["inmails_source"],
        "connection_note_chars": schema.LIMITS["connection_note_chars"],
        "inmail_words": schema.LIMITS["inmail_words"],
        "note": note,
        "inmail_note": "" if inmail_limit else NO_INMAIL,
    }


def budget_line(b: dict) -> str:
    """The BUDGET line `state.py` prints: the requests sent this week and today, with no cap
    of the app's own, and the InMail credits left. A planning cap printed as "50 left" read as
    LinkedIn's own limit and misled a person (2026-10-22): no number is printed that LinkedIn
    did not give."""
    return (f"\nBUDGET  connection requests sent: {b['connections_sent']} this week, "
            f"{b['connections_today']} today (no cap of the app's own; LinkedIn says when its "
            f"own limit is reached). InMail {b['inmails_left']} left this month "
            f"({b['inmails_source']})")


# ---------------------------------------------------------------- CLI


def _cli_follow_ups(argv) -> int:
    """`state.py follow-ups [--write]`: the day each thread waiting on a reply is due a
    follow-up, by the person's rule; --write puts it on their rows."""
    ap = argparse.ArgumentParser(prog="state.py follow-ups",
                                 description="Write each follow-up's due date onto its contact.")
    ap.add_argument("--write", action="store_true", help="write the dates (default: show them)")
    ap.add_argument("--today", default=datetime.date.today().isoformat())
    a = ap.parse_args(argv)
    contacts, threads = load_contacts(), load_threads()
    said = write_follow_ups(contacts, threads, a.today)
    print(f"follow-ups ({schema.follow_up_rule()}): {len(said)} row(s) "
          + ("written" if a.write else "to write; --write writes them"))
    for line in said[:40]:
        print("  " + line)
    if len(said) > 40:
        print(f"  ... and {len(said) - 40} more")
    if a.write and said:
        save_contacts(contacts)
    return 0


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv[:1] == ["withdraw"]:
        return _cli_withdraw(argv[1:])
    if argv[:1] == ["sent"]:
        return _cli_sent(argv[1:])
    if argv[:1] == ["text"]:
        return _cli_text(argv[1:])
    if argv[:1] == ["attach"]:
        return _cli_attach(argv[1:])
    if argv[:1] in (["nudge"], ["message"]):
        return _cli_followed_up(argv[1:], argv[0])
    if argv[:1] == ["received"]:
        return _cli_received(argv[1:])
    if argv[:1] == ["resent"]:
        return _cli_resent(argv[1:])
    if argv[:1] == ["unsend"]:
        return _cli_unsend(argv[1:])
    if argv[:1] in (["reopen"], ["drop"]):
        return _cli_reopen_or_drop(argv[1:], argv[0])
    if argv[:1] == ["dropped-rows"]:
        return _cli_dropped_rows(argv[1:])
    if argv[:1] == ["inmail-credits"]:
        return _cli_inmail_credits(argv[1:])
    if argv[:1] == ["set"]:
        return _cli_set(argv[1:])
    if argv[:1] == ["no-reply"]:
        return _cli_no_reply(argv[1:])
    if argv[:1] == ["follow-ups"]:
        return _cli_follow_ups(argv[1:])
    try:  # a chat that carried on into a new day has not checked the app since
        import sync_app
        sync_app.nudge()
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Networking pipeline state.")
    ap.add_argument("--contacts", default=CONTACTS_CSV)
    ap.add_argument("--threads", default=THREADS_CSV)
    ap.add_argument("--tracker", default=TRACKER_CSV)
    ap.add_argument("--today", default=datetime.date.today().isoformat())
    a = ap.parse_args(argv)

    contacts = load_contacts(a.contacts)
    threads = load_threads(a.threads)
    print(f"{len(contacts)} contacts, {len(threads)} messages\n")

    items = owed(contacts, threads, a.today)
    tracked = load_tracker(a.tracker) if os.path.exists(a.tracker) else None
    resumes = {r["contact_id"]: r for r in resumes_owed(contacts, threads, tracked)}
    print("OWED" if items or resumes else "OWED: nothing due")
    for i in items:
        where = f" ({i['company']})" if i["company"] else ""
        owed_cv = resumes.pop(i["contact_id"], None)
        print(f"  [{i['kind']:5}] {i['name'] or i['contact_id']}{where} "
              f"{i['business_days']}bd since {i['since'] or 'unknown'}"
              + {"request_pending": "; not accepted, so nothing can be sent: withdraw it, "
                                    f"then record it: state.py withdraw {i['contact_id']}",
                 "first_message": "; accepted, nothing said yet: a first message, not a nudge",
                 }.get(i["kind"], "")
              + (f"; owed over {OLD_OWED_DAYS} days, so the due list counts it rather than "
                 "listing it (a date on the row brings it back)" if i.get("old") else "")
              + (f"; {resume_owed_line(owed_cv)}" if owed_cv else ""))
    for r in resumes.values():
        print(f"  [{noun()}] {resume_owed_line(r)}")
    import zipfile
    import export
    if any(i["kind"] == "request_pending" for i in items):
        print("  Withdrawing is done on LinkedIn, by you; the steps: " + export.WITHDRAW_STEPS)
    # Invitations sent from LinkedIn itself and never accepted, from the export: the log
    # knows only the requests it recorded, and the backlog counts against how many
    # LinkedIn lets the person send. A broken export never stops this view.
    try:
        waiting = export.pending_lines(export.pending(contacts, threads, a.today))
    except (OSError, ValueError, KeyError, zipfile.BadZipFile):
        waiting = []
    if waiting:
        print("\n" + "\n".join(waiting))

    b = platform_budget(contacts, threads, a.today)
    print(budget_line(b))
    if b["note"]:
        print("  " + b["note"])

    if tracked is not None:
        links = link_to_applications(contacts, tracked, threads)
        print(f"\nLINKED  {len(links)} contacts sit at a company already in the tracker")
        for link in links:
            sent_line = "; ".join(
                f"{noun()} sent {s['date']}" + (f" ({', '.join(s['files'])})" if s["files"] else "")
                for s in link.get("resumes_sent") or [])
            print(f"  {link['name'] or link['contact_id']} -> {', '.join(link['roles'])}"
                  + (f"; {sent_line}" if sent_line else ""))
        import company_key
        misses = company_key.near_misses({c.get("company") for c in contacts if c.get("company")},
                                         {r.get("company") for r in tracked if r.get("company")})
        if misses:
            print(f"\nJOINS  {len(misses)} contact employer(s) may be an application's under "
                  "another name; if so, add the pair to COMPANY_ALIASES in profile/employers.py")
            for contact_side, tracker_side in misses[:15]:
                print(f"  {contact_side}  /  {tracker_side}")

    # `reconcile` already separates a contradiction from a note, and a printer
    # that threw that away would put every finding in one flat list, most of them
    # `history_not_logged`, with the few that need a person buried in the middle.
    # That is the failure `reconcile`'s own docstring describes, and the display
    # must not reintroduce it: an `orphan_thread` would sit unnoticed.
    # The tracker's half is added beside the call, so the line stays the one a person's
    # own test finds the printer by.
    problems = reconcile(contacts, threads) + resume_findings(
        contacts, threads, tracked, reasons=("resume_not_logged",))
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
    import csv_store
    try:
        raise SystemExit(main())
    except csv_store.Conflicted as e:  # a merge left markers: say which file, read nothing
        print(f"state: {e}", file=sys.stderr)
        raise SystemExit(1) from None
