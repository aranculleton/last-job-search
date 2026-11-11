#!/usr/bin/env python3
"""The page's view model: one JSON object built from the repo, the same way every time.

The page shows the search; it holds no truth of its own. Everything on it is derived here
from the files the chat commands already read and write (the tracker, the newest round and
its filtered list, the application folders, the contact book and the message log, the
interview folders, the profile's settings), through the functions those commands own:
`open_actions.due_items` for what is owed, `throttle` for which routes are warm,
`network/state.py` for each contact's status, `what_works.outcome_stages` and
`interview_pack.next_stage` for interviews, `confirm.check` for what does not add up,
`learned.offers` for a choice the person still has to make. Nothing is stored, so nothing
here can go stale; the idea is a selector's (Reselect, MIT: "compute derived data, allowing
Redux to store the minimal possible state"), and like Taskwarrior's export (MIT), the
derived fields ride along with the stored ones and are never written back.

`rev` is a hash of the model without its clock fields (`made_at`, `updated`), so the same
state gives the same rev on any computer. Every item carries its own `rev`, a hash of only
the fields an action on it could act on: an action that arrives with a `rev_seen` that no
longer matches was made on something that has changed since, and is refused, never applied
over the change (tools/app_actions.py).

Nothing about another person reaches it but a first name and an employer: never an email
address, a phone number, a LinkedIn address or the words of their messages. What the person
wrote themselves (their drafts, their screening answers) is theirs, and shown.

    python3 tools/app.py model [--out FILE] [--today YYYY-MM-DD] [--now ISO]

It reads no network and makes no model call. `LJS_TODAY` (a date, or a date and a time)
fixes the clock for a test, as `--today` does for every other tool.
"""
from __future__ import annotations

import datetime as dt
import glob
import hashlib
import html
import json
import math
import os
import re
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.join(_HERE, "network"), _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import person  # noqa: E402
from docpaths import FILE_NAME_PRESETS  # noqa: E402

MODEL = 1
# Clock fields: true of the moment the model was made, not of the state it shows.
# Fields that say when, not what: left out of every rev, so the same state has the same rev
# whatever the clock says (`seen_at` and `seen_recently` are when a chat last saw the
# page's listener answer).
CLOCK_KEYS = frozenset({"made_at", "updated", "seen_at", "seen_recently"})
SECTIONS = ("app", "person", "needs_you", "jobs", "ready", "messages", "due", "people",
            "interviews", "done", "settings", "brief", "setup", "updates", "applications",
            "referrals", "message_budget", "linkedin", "learned", "help", "resume",
            "search", "where", "listener", "schedule", "you", "upcoming", "rules")
# The page shows every live contact, then the rest by recency up to a size budget
# (tools/app_lists.py PEOPLE_BYTES); the whole book is in the page's database for "Show".
DUE_MAX = 100
# The rows a left-out group shows before "See them" (tools/rules_view.py FIRST): kept under
# its old name for a person's own tests.
FILTERED_PER_GROUP = 20
# An application sent this recently stays under Drafts, ticked, so the tick can
# be seen and undone where it was made.
RECENT_APPLIED_DAYS = 14
# At most three facts to confirm at a time (RUNBOOK.md, "Start of a session", step 5).
CONFIRM_MAX = 3
# What a job card says of a posting with words written to an AI tool reading it.
AIMED_AT_AI_WORDS = "This posting has text aimed at AI tools; Claude ignored it."

# ------------------------------------------------------------------ the clock


def _utc(x: dt.datetime) -> dt.datetime:
    return x.replace(tzinfo=dt.timezone.utc) if x.tzinfo is None else x.astimezone(dt.timezone.utc)


def parse_time(value) -> dt.datetime | None:
    """An ISO time ("2026-10-25T18:00:00Z", with or without the Z), a date, or epoch
    milliseconds (what a page's Date.now() writes), as an aware UTC datetime."""
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return dt.datetime.fromtimestamp(value / 1000.0, tz=dt.timezone.utc)
    text = str(value).strip()
    if re.fullmatch(r"\d{12,}", text):
        return parse_time(int(text))
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        return _utc(dt.datetime.fromisoformat(text))
    except ValueError:
        pass
    try:
        d = dt.date.fromisoformat(text[:10])
    except ValueError:
        return None
    return dt.datetime(d.year, d.month, d.day, 12, 0, tzinfo=dt.timezone.utc)


def stamp(t: dt.datetime) -> str:
    return _utc(t).strftime("%Y-%m-%dT%H:%M:%SZ")


def clock(today: str | None = None, now: str | None = None) -> tuple[dt.date, dt.datetime]:
    """(today, now): `--today`/`--now`, else `LJS_TODAY`, else the computer's clock. A date
    given alone is that day at noon UTC, so a fixed clock gives one model. With none given the
    day is the person's own (person.today()), never the computer's: Held back for now, the
    ends of what was set aside and Jobs counted the computer's day while the search counted
    theirs, a day apart on a computer set to another zone (the rules review, 2026-11-11)."""
    fixed = now or today or os.environ.get("LJS_TODAY") or ""
    t = parse_time(fixed) if fixed else None
    if t is None:
        t = dt.datetime.now(dt.timezone.utc)
        return (dt.date.fromisoformat(today) if today else person.today(t)), t
    day = dt.date.fromisoformat(today) if today else t.date()
    return day, t


# The zones an invite writes beside a time (outcome.md keeps them as written: what_works,
# _STAGE_WHEN), read as the place they name. One a place does not settle is left out: an
# interview at a time in a zone not known here keeps its day alone, never a wrong hour.
_ZONE_WORDS = person.ZONE_WORDS


def interview_when(day, clock="", written="", home="UTC") -> str | None:
    """An interview's `when` for the page: the moment, as "YYYY-MM-DDTHH:MM:00Z", where its
    time is known (the page shows it in the person's own zone, and in this device's where
    that differs); its calendar day alone where it is not, which the page shows as "time not
    set". A day with its time sent as a day alone read "time not set" with the time on
    record (2026-10-29). `written` is a zone the invite gave beside the time (a word in
    `_ZONE_WORDS`, or a name like "America/Chicago"); else `home`."""
    day = str(day or "").strip()
    if not day:
        return None
    clock = str(clock or "").strip()
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", clock)
    if not m:
        return day
    written = str(written or "").strip()
    # One reader of a zone's words, the person's (person.zone_in): "Toronto time" and "ET"
    # alike; a word it cannot place gives the day alone, never a time in the wrong zone.
    name = (_ZONE_WORDS.get(written.upper()) or person.zone_in(written, home)) if written \
        else (str(home or "") or "UTC")
    if not name:
        return day
    try:
        import zoneinfo
        at = dt.datetime.combine(dt.date.fromisoformat(day),
                                 dt.time(int(m.group(1)), int(m.group(2))),
                                 tzinfo=zoneinfo.ZoneInfo(name))
    except Exception:  # noqa: BLE001  no zone data here, or a day that is not one
        return day
    return _utc(at).strftime("%Y-%m-%dT%H:%M:00Z")


def when_day(when, zone: str) -> str:
    """The person's own day of an interview's `when`: a moment late in the evening west of
    London is the next day in UTC."""
    when = str(when or "")
    if "T" not in when:
        return when[:10]
    t = parse_time(when)
    return local_day(t, zone).isoformat() if t else when[:10]


def local_day(t: dt.datetime, zone: str) -> dt.date:
    """The person's own date at time `t`: a tick at half past midnight in their zone is
    that day, though it is still yesterday in UTC."""
    try:
        import zoneinfo
        return t.astimezone(zoneinfo.ZoneInfo(zone)).date()
    except Exception:  # noqa: BLE001  no zone data here: the UTC day
        return _utc(t).date()


# ------------------------------------------------------------------ hashing


def _canon(obj) -> str:
    return _CANON.encode(obj)


# json.dumps with these settings, made once: dumps builds an encoder a call, and a big page
# asks for some 4,500 revs.
_CANON = json.JSONEncoder(sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                          default=str)


def rev_of(*parts) -> str:
    """A short, stable hash of `parts`: the same values, the same rev, on any computer."""
    return hashlib.sha256(_canon(list(parts)).encode("utf-8")).hexdigest()[:12]


def _without_clock(obj):
    """`obj` without any CLOCK_KEYS, at any depth. Only what holds one is copied: the rest is
    `obj`'s own, so what this returns is read, never changed. A copy of all of a big model
    was most of the time its rev took (2026-11-03)."""
    if isinstance(obj, dict):
        new = None
        for k, v in obj.items():
            if isinstance(v, (dict, list)):
                w = _without_clock(v)
                if w is not v:
                    if new is None:
                        new = dict(obj)
                    new[k] = w
        if not CLOCK_KEYS.isdisjoint(obj):
            new = dict(obj) if new is None else new
            for k in CLOCK_KEYS:
                new.pop(k, None)
        return obj if new is None else new
    if isinstance(obj, list):
        new = None
        for i, v in enumerate(obj):
            if isinstance(v, (dict, list)):
                w = _without_clock(v)
                if w is not v:
                    if new is None:
                        new = list(obj)
                    new[i] = w
        return obj if new is None else new
    return obj


def model_rev(model: dict) -> str:
    return rev_of(_without_clock({k: v for k, v in model.items() if k != "rev"}))


# ------------------------------------------------------------------ privacy

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
LINKEDIN_IN = re.compile(r"(?:https?://)?(?:[\w-]+\.)*linkedin\.com/(?:m/|mwlite/)?in/[^\s)\]>,;\"']*",
                         re.I)
_URL = re.compile(r"https?://\S+", re.I)
PHONE = re.compile(r"(?<![\w/.+-])(?:\+\d[\d ().-]{7,}\d|\(?0\d{2,4}\)?[ .-]?\d{3,4}[ .-]?\d{3,4}"
                   r"|\d{3}[ .-]\d{3}[ .-]\d{4})(?![\w/])")


class Names:
    """Every full name in the contact book, cut to its first name in one pass of one pattern
    (a pattern a name, run over every line of a big contact book, took seconds)."""

    def __init__(self, pairs):
        self.first = {}
        for full, first in pairs:
            if full and first and full != first:
                self.first.setdefault(full.casefold(), first)
        alts = sorted(self.first, key=len, reverse=True)
        self.rx = (re.compile(r"(?<!\w)(?:" + "|".join(re.escape(a) for a in alts) + r")(?!\w)",
                              re.I) if alts else None)
        # A line holds a full name only where the name's first two words stand side by side
        # in it, so a set says first whether the pattern of every name can match at all: run
        # on every line of a book of 2,000, it made each build half a second slower once the
        # engine said where every person stands (2026-11-03).
        self.pairs, self.ones, self.always = set(), set(), False
        # Which names each word, or each two words side by side, could begin: a text is cut
        # by a pattern of only the names it could hold. One pattern of every name in a book of
        # 700, run over each call prep whole, took 4.1 to 4.4 s of a build (the second audit,
        # D8).
        self.by_pair: dict = {}
        self.by_one: dict = {}
        self.anywhere: list = []
        for alt in alts:
            words = _WORDS.findall(alt)
            if not words:
                self.always = True
                self.anywhere.append(alt)
            elif len(words) == 1:
                self.ones.add(words[0])
                self.by_one.setdefault(words[0], []).append(alt)
            else:
                self.pairs.add((words[0], words[1]))
                self.by_pair.setdefault((words[0], words[1]), []).append(alt)
        # What each text came out as, for this build: a contact's next step is cut down for
        # their row and again for To do, and one title is on many rows.
        self.done: dict = {}
        self.scrubbed: dict = {}
        # {the names looked for, longest first: their pattern}, made once each.
        self.patterns: dict = {}

    def could(self, text: str) -> bool:
        """Can a full name be in `text`? False only where none can."""
        if self.always:
            return True
        words = _WORDS.findall(text.casefold())
        if self.ones and not self.ones.isdisjoint(words):
            return True
        return any(p in self.pairs for p in zip(words, words[1:]))

    def could_be(self, text: str) -> tuple:
        """The full names `text` could hold, longest first, as the one pattern of them all
        would try them: those whose first two words stand side by side in it."""
        words = _WORDS.findall(text.casefold())
        got = set(self.anywhere)
        for w in words:
            got.update(self.by_one.get(w, ()))
        for p in zip(words, words[1:]):
            got.update(self.by_pair.get(p, ()))
        return tuple(sorted(got, key=lambda a: (-len(a), a)))

    def sub(self, text: str) -> str:
        if self.rx is None:
            return text
        got = self.done.get(text)
        if got is None:
            alts = self.could_be(text)
            rx = self.patterns.get(alts) if alts else None
            if alts and rx is None:
                rx = self.patterns[alts] = re.compile(
                    r"(?<!\w)(?:" + "|".join(re.escape(a) for a in alts) + r")(?!\w)", re.I)
            got = self.done[text] = rx.sub(
                lambda m: self.first.get(m.group(0).casefold(), m.group(0)), text) \
                if rx is not None else text
        return got


_WORDS = re.compile(r"\w+")


def _phones(text: str) -> list[str]:
    bare = _URL.sub(" ", text) if "://" in text else text      # no address without "://"
    return [m.group(0) for m in PHONE.finditer(bare)
            if 9 <= len(_NON_DIGIT.sub("", m.group(0))) <= 15]


_NON_DIGIT = re.compile(r"\D")


def private_in(text) -> list[str]:
    """What kinds of contact detail `text` holds: "an email address", "a LinkedIn
    profile address", "a phone number". Never the detail itself."""
    text = str(text or "")
    return ((["an email address"] if EMAIL.search(text) else [])
            + (["a LinkedIn profile address"] if LINKEDIN_IN.search(text) else [])
            + (["a phone number"] if _phones(text) else []))


# The words the app writes into a contact's next step are also its own markers
# (tools/network/state.py FOLLOW_UP_*), so they stay as written there; the page says them
# plainly. "No more follow-ups: 2 messages with no reply, your rule's limit (14 days, at most 2
# with no reply). If still silent by the date, close it: state.py set ..." was a To do title,
# cut off mid-word (the maintainer, 2026-10-26).
_STOPPED = re.compile(r"^(?:no more follow-ups: (\d+) messages with no reply\b.*|nudged: nothing more unless they reply\b.*)$", re.I | re.S)
_FOLLOW = re.compile(r"^follow up if no reply \((\d+) of (\d+) sent\b.*$", re.I | re.S)
_COMMAND = re.compile(r"[.:]?\s*(?:if still silent by the date, close it:\s*)?(?:python3 )?(?:tools/)?(?:network/)?state\.py\b.*$", re.I | re.S)


_ROUTE_WORDS = {"alumni": "alumni", "referral": "referral", "recruiter": "recruiter",
                "warm": "warm introduction", "intro": "introduction"}


_ISO_DAY = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")


def _day_words(m) -> str:
    try:
        d = dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return m.group(0)
    return f"{d.strftime('%a')} {d.day} {d.strftime('%b')}"


def plain_action(text) -> str:
    """A contact's next step in plain words: the app's own wording turned into a short line,
    never a command; anything the person wrote is shown as they wrote it, with a date read as
    a date ("Thu 29 Oct", never 2026-10-29) and no full stop the page would follow with a
    comma (2026-10-30)."""
    s = _ISO_DAY.sub(_day_words, " ".join(str(text or "").split())).rstrip(" .")
    m = _STOPPED.match(s)
    if m:
        n = m.group(1) or "2"
        return f"No reply to {n} messages: leave it unless they write back"
    m = _FOLLOW.match(s)
    if m:
        return f"Follow up if they don't reply ({m.group(1)} of {m.group(2)} sent)"
    return _COMMAND.sub("", s).strip()


def short(text: str, limit: int = 120) -> str:
    """Cut at a word, with an ellipsis, never mid-word."""
    s = str(text or "")
    if len(s) <= limit:
        return s
    return s[:limit].rsplit(" ", 1)[0].rstrip(",;:") + "\u2026"


def scrub(text, names=()) -> str:
    """`text` with every contact detail taken out, and each full name in `names` (pairs of
    (full name, first name)) cut to the first name."""
    out = str(text or "")
    kept = getattr(names, "scrubbed", None)
    if kept is not None and out in kept:
        return kept[out]
    raw = out
    # A profile address holds a "/" and an email address an "@": a line with neither is left
    # alone without a search for either.
    if "/" in out:
        out = LINKEDIN_IN.sub("", out)
    if "@" in out:
        out = EMAIL.sub("", out)
    for p in sorted(set(_phones(out)), key=len, reverse=True):
        out = out.replace(p, "")
    if hasattr(names, "sub"):
        out = names.sub(out)
    else:
        for full, first in names:
            if full and first and full != first:
                out = re.sub(re.escape(full), first, out, flags=re.I)
    out = _SPACE_BEFORE.sub(r"\1", _SPACES.sub(" ", out))
    out = _LOOSE_COMMA.sub("", out).strip(" ,;")
    if kept is not None:
        kept[raw] = out
    return out


_SPACES = re.compile(r"[ \t]{2,}")
_SPACE_BEFORE = re.compile(r"\s+([,.;:)])")
_LOOSE_COMMA = re.compile(r"[,;]\s*(?=[,;.]|$)")


# ------------------------------------------------------------------ small readers


def read_text(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except (OSError, UnicodeDecodeError):
        return ""


_read = read_text  # the module's own name for it; other modules call read_text


def read_json(path: str, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


_json = read_json  # the module's own name for it; other modules call read_json


def rel(path: str) -> str:
    """A path as the repo writes it: relative to the state root, with forward slashes.
    Never a relpath across two Windows drives (local_path.rel)."""
    import local_path
    return local_path.rel(path, person.state()).replace(os.sep, "/")


def _mtime(path: str) -> str:
    try:
        return stamp(dt.datetime.fromtimestamp(os.path.getmtime(path), tz=dt.timezone.utc))
    except OSError:
        return ""


_SAVED_AT: dict = {}


def saved_at(path: str) -> dt.datetime | None:
    """Kept per file as it is on disk (its time and size), so a model build asks git once a
    file however often it is asked: every interview with a prep asked four to six times (the
    review of 2026-11-11)."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    key = (os.path.abspath(path), st.st_mtime_ns, st.st_size)
    if key not in _SAVED_AT:
        if len(_SAVED_AT) > 4096:
            _SAVED_AT.clear()
        _SAVED_AT[key] = _saved_at(path)
    return _SAVED_AT[key]


def _saved_at(path: str) -> dt.datetime | None:
    """When a file's content was last written: the commit that last changed it where the file
    is as committed, else (changed since, or never committed) the file's own time. The file's
    own time alone is when it was checked out: a round run at 15:51 read "searched 2 hours
    ago" at 18:00 off a fresh copy, and a resume committed in September read "Made Sat 31
    Oct", so "Out of date" flipped with the order the files were written (2026-11-03)."""
    try:
        own = dt.datetime.fromtimestamp(os.path.getmtime(path), tz=dt.timezone.utc)
    except OSError:
        return None
    where = os.path.dirname(path) or "."
    try:
        same = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", os.path.basename(path)],
                              cwd=where, capture_output=True, timeout=10,
                              stdin=subprocess.DEVNULL).returncode == 0
        got = subprocess.run(["git", "log", "-1", "--format=%cI", "--",
                              os.path.basename(path)], cwd=where, capture_output=True,
                             text=True, encoding="utf-8", errors="replace", timeout=10,
                             stdin=subprocess.DEVNULL) if same else None
    except (OSError, subprocess.TimeoutExpired):
        return own
    # A newer git writes UTC as "Z", which Python before 3.11 (a Mac's own python3 is 3.9)
    # cannot read: every file then took its checkout time again (CI on 3.9, 2026-11-03).
    when = got.stdout.strip() if got is not None and got.returncode == 0 else ""
    if when.endswith("Z"):
        when = when[:-1] + "+00:00"
    try:
        return dt.datetime.fromisoformat(when).astimezone(dt.timezone.utc) if when else own
    except ValueError:
        return own


def _status(row) -> str:
    import throttle
    st = str(row.get("status") or "").strip().lower()
    return throttle.LEGACY_SPELLINGS.get(st, st)


def first_name(name) -> str:
    """The name a message greets them by: the greeting rule every composer uses."""
    try:
        import tone
        return tone.greeting_name(name) or ""
    except Exception:  # noqa: BLE001  an odd name greets nobody, never breaks the model
        return ""


def row_slug(company, role) -> str:
    import outreach
    try:
        return outreach.slug(company or "", role or "")
    except ValueError:
        return ""


# ------------------------------------------------------------------ the sources


class Ctx:
    """Every source the sections read, each read once, when first asked for."""

    def __init__(self, today: dt.date, now: dt.datetime):
        self.today, self.now = today, now
        self._got: dict = {}

    def _once(self, key, make):
        if key not in self._got:
            self._got[key] = make()
        return self._got[key]

    @property
    def repo(self) -> tuple:
        """(owner, folder) of this copy: one git call a build, not one per section that
        names it (each starts a process, which Windows is slow to do)."""
        def make():
            import place
            return place.repo()
        return self._once("repo", make)

    @property
    def tracker(self) -> list[dict]:
        def make():
            import csv_store
            return csv_store.tracker(person.state("job_search_tracker.csv"))
        return self._once("tracker", make)

    @property
    def tracker_ids(self) -> list[str]:
        """tracker_ids(self.tracker), worked out once: every section that names an
        application asked for all of them again. Read, never changed."""
        return self._once("tracker_ids", lambda: tracker_ids(self.tracker))

    @property
    def contacts(self) -> list[dict]:
        def make():
            path = person.state("network_contacts.csv")
            if not os.path.exists(path):
                return []
            from network import state
            return state.load_contacts(path)
        return self._once("contacts", make)

    @property
    def threads(self) -> list[dict]:
        def make():
            path = person.state("network_threads.csv")
            if not os.path.exists(path):
                return []
            from network import state
            return state.load_threads(path)
        return self._once("threads", make)

    @property
    def by_contact(self) -> dict:
        from network import state
        return self._once("by_contact", lambda: state.by_contact(self.threads))

    @property
    def contacts_by_key(self) -> dict:
        """{employer key: the contacts there, in the book's order}: keyed once a build, where
        each card that looked for someone at its employer keyed the whole book again."""
        def make():
            from company_key import key
            got: dict = {}
            for c in self.contacts:
                got.setdefault(key(c.get("company")), []).append(c)
            return got
        return self._once("contacts_by_key", make)

    @property
    def network(self) -> tuple:
        """(live status by contact id, warm routes, referral holds), as open_actions reads them."""
        def make():
            import open_actions
            return open_actions.network_views(self.contacts, self.threads,
                                              index=self.by_contact, today=self.today)
        return self._once("network", make)

    @property
    def live(self) -> dict:
        return self.network[0]

    @property
    def due_items(self) -> list:
        """open_actions.due_items, both halves, read once for Due, Applied and the rest."""
        def make():
            import open_actions
            return open_actions.due_items(self.contacts, self.threads, self.tracker, self.today,
                                          network=self.network, now=self.now,
                                          index=self.by_contact, read_stages=self.stages)
        return self._once("due_items", make)

    def stages(self, row: dict) -> tuple:
        """open_actions.stages for one application, found and read once a build: Interviews,
        Applications, Coming up and the due list each looked for every application's folder
        again. Each caller gets lists of its own."""
        memo = self._got.setdefault("stages", {})
        k = (row.get("company"), row.get("role") or "")
        if k not in memo:
            import open_actions
            memo[k] = open_actions.stages(row)
        folder, files, stages = memo[k]
        return folder, list(files), [dict(s) for s in stages]

    @property
    def names(self) -> "Names":
        """Every full name in the contact book, and the first name each is cut to."""
        def make():
            out = []
            for c in self.contacts:
                full = " ".join(str(c.get("name") or "").split())
                if full:
                    out.append((full, first_name(full) or full.split()[0]))
            return Names(out)
        return self._once("names", make)

    @property
    def seen(self) -> dict:
        """{posting key: seen_jobs.json entry}, keyed the way exclude.py keys them."""
        def make():
            import exclude
            from lookup_score import norm
            data = exclude.load_seen(person.state("job_scraper", "seen_jobs.json"))
            out = {}
            for k, e in (data.get("seen") or {}).items():
                if isinstance(e, dict):
                    out[norm(e.get("url") or k) or k] = e
            return out
        return self._once("seen", make)

    @property
    def zone(self) -> str:
        """The person's own zone, for working out days and times: UTC only while they have
        named none, which the page shows in the device's own zone and asks them for."""
        return self.zone_named or "UTC"

    @property
    def zone_named(self) -> str:
        """The person's own zone as they said it (person.home_zone_named), or ""."""
        def make():
            try:
                return person.home_zone_named(person.directory())
            except person.NoProfile:
                return ""
        return self._once("zone_named", make)


# ------------------------------------------------------------------ app and person


def _app(ctx: Ctx, targets: dict) -> dict:
    """The version and its news, read from the one updates section (app_setup), never
    worked out a second time."""
    u = _updates(ctx, targets)
    waiting = u.get("waiting") or None
    news = ((u.get("changed") or [{}])[0].get("lines") or [])[:3]
    try:
        import app_setup
        owner, name = app_setup.origin()
    except Exception:  # noqa: BLE001
        owner, name = "", ""
    try:
        import app_setup
        url = str(app_setup.page_record().get("url") or "") or None
    except Exception:  # noqa: BLE001  no profile yet: no page yet
        url = None
    return {"version": u.get("version") or "",
            # The page's own address, for Settings' "Open on another device": nothing gave it
            # the page, which said "The link arrives with the next update" for ever (the 3
            # November audit).
            "url": url,
            "update_waiting": waiting["line"] if waiting and u.get("mode") == "when_asked"
            else None, "news": news, "privacy": _privacy_line(),
            # The copy the page belongs to, so the page can start its helper chat itself.
            "repo": f"https://github.com/{owner}/{name}" if owner and name else None,
            # The page's own code version, built into it when it is published: an open page
            # older than the one published since reloads itself (meta/now `page`, app.py view).
            "page": _page_version(),
            # How many pieces of the person's work have waited a day or more without being
            # saved (land.stranded, read offline): the page says so, so work that never
            # reached their copy is never silent (the stranger audit, X-30).
            "not_saved": _not_saved(),
            # In the app maker's own copy only: complaints about how the app behaves, kept as
            # app bugs rather than rules (learned.route_about_app), for Settings' Something
            # looks wrong. Everyone else's is always empty.
            "app_bugs": _app_bugs()}


def _app_bugs() -> list:
    try:
        import learned
        rows = learned.app_bugs()
        if not rows or not learned._maintainers():
            return []
    except Exception:  # noqa: BLE001  no profile yet: nothing kept
        return []
    return [{"said": " ".join(str(r.get("said") or "").split())[:200],
             "on": str(r.get("date") or "")[:10] or None, "link": r.get("link") or None}
            for r in rows][-20:]


def _not_saved() -> int:
    try:
        import land
        if not hasattr(land, "stranded") or land._the_app(land.ROOT):
            return 0
        return len(land.stranded(land.ROOT, fetch=False))
    except Exception:  # noqa: BLE001  no git here, or no copy: nothing to say
        return 0


def _page_version() -> int:
    try:
        import build_versions
        return int(build_versions.current("page"))
    except Exception:  # noqa: BLE001
        return 0


def _privacy_line() -> str:
    """The footer line the page shows (tools/app_listen.privacy: claude_surfaces page-share)."""
    try:
        import app_listen
        return app_listen.privacy()
    except Exception:  # noqa: BLE001  the registry is the app's; never break the page on it
        return ""


def _person(ctx: Ctx, targets: dict) -> dict:
    try:
        name = str(person.get("identity.name", "") or "")
        first = str(person.get("identity.first", "") or "") or (name.split() or [""])[0]
        # "" while they have named no zone: the page then shows its device's own and asks
        # (q-time-zone), never the zone their brief happens to be scheduled in.
        noun, zone = str(person.get("documents.noun", "resume")), ctx.zone_named
    except person.NoProfile:
        name, first, noun, zone = "", "", "resume", ""
    repo, computer = "", False
    try:
        import place
        owner, folder = ctx.repo
        repo = f"{owner}/{folder}" if owner else ""
        # Known ready, never only said: "Find people" goes to the computer on this (the page's
        # peopleTo), and sent there with no computer that could take it, it waited for good
        # (the release review, 2026-11-09).
        import computer as _computer
        computer = _computer.reads_there(place.place_record(), ctx._got.get("computer") or {},
                                         ctx.now)
    except Exception:  # noqa: BLE001
        pass
    return {"first_name": first, "doc_noun": noun, "time_zone": zone, "repo": repo,
            "computer": computer}


def computer_reads(ctx: Ctx) -> bool:
    """Is the person's computer known ready to read LinkedIn (tools/computer.py reads_there),
    so a LinkedIn read is sent there as work and done there by itself? Once a build."""
    def make() -> bool:
        try:
            import place
            import computer as _computer
            return bool(_computer.reads_there(place.place_record(),
                                              ctx._got.get("computer") or {}, ctx.now))
        except Exception:  # noqa: BLE001  no record: not known ready
            return False
    return ctx._once("computer_reads", make)


def employer_held(ctx: Ctx, company: str, cid: str) -> str:
    """"On hold: ..." for a first note whose employer already has as many people waiting on a
    reply as the person allows there (reading.employer_full_line), or "". Once an employer."""
    if not company:
        return ""
    memo = ctx._got.setdefault("employer_held", {})
    if company not in memo:
        said = ""
        try:
            import reading
            limit, _theirs = reading.employer_limit(company)
            waiting, _there = reading.at_employer(company, ctx.contacts, today=ctx.today,
                                                  threads=ctx.threads) if limit else ([], [])
            if limit and len(waiting) >= limit:
                n = len(waiting)
                said = (f"On hold: you already have {n} {'person' if n == 1 else 'people'} "
                        f"waiting on a reply at {company}")
        except Exception as e:  # noqa: BLE001  no limit known: nothing held for it
            # A log that cannot be read is said, and holds the note: read as "not held", every
            # note at the employer looked ready (the review, 2026-11-11).
            said = (f"On hold: {e}" if type(e).__name__ == "LogUnreadable" else "")
        memo[company] = said
    return memo[company]


def read_hold(ctx: Ctx) -> str:
    """The line on a first note waiting for its person's profile, by the person's setting. With
    their computer known ready, the read is sent there as work by itself (tools/app.py
    computer_reads), and the line says so on every device: "press Read them in To do" with no
    such card there was the line before (the maintainer, 2026-11-10)."""
    import reading
    setting = ctx._once("reads_now", reading.reads_now)
    if setting == "browser" and computer_reads(ctx):
        return READ_HOLD["computer"]
    return READ_HOLD.get(setting, READ_HOLD["browser"])


# A hold's own words, as Claude's finish or a contact's next action says them: "Held: no message
# to Kit until a fitting role appears", "Hold until 2026-11-23: Fernhill Freight posts a role".
_HOLD_LEAD = re.compile(r"^\W*(?:(?:on\s+)?hold(?:ing)?|held)\b(?:\s+until\s+(\d{4}-\d{2}-\d{2}))?"
                        r"[\s:,.-]*", re.I)


def hold_words(why, until: dt.date | None = None) -> str:
    """A draft on hold, in a line for its card: "On hold until Fernhill Freight posts a
    fitting role. Claude checks again on Mon 23 Nov." Never the draft offered as ready under a
    line saying it was held (the maintainer, 2026-11-10)."""
    why = re.sub(r"\s*\(since \d{4}-\d{2}-\d{2}(?:, after \d+ from them)?\)", "", " ".join(str(why or "").split()))
    why = _HOLD_LEAD.sub("", why, count=1).strip().rstrip(" .;")
    if until is not None:
        # The day is said once, from the record: never a second "I check again 23 Nov".
        why = re.split(r"\s*;\s*", why)[0].rstrip(" .;")
    why = re.sub(r",?\s*(?:or\s+)?until\s+\d{4}-\d{2}-\d{2}\b", "", why).rstrip(" .;,")
    why = re.sub(r"\bI (check|look)\b", r"Claude \1s", why)
    head = "On hold" + ((" " + why) if why.lower().startswith(("until ", "while ", "till "))
                        else (": " + why) if why else "")
    return head + "." + (f" Claude checks again on {holds_day(until)}." if until else "")


def _set_aside_holds(entry, today) -> bool:
    import exclude
    return exclude.set_aside_holds(entry, today)


def holds_day(d: dt.date) -> str:
    return f"{d.strftime('%a')} {d.day} {d.strftime('%b')}"


def person_hold(c: dict, today: dt.date) -> str:
    """The hold their contact record carries (its next action "Hold ...", state.action_hold),
    in a line for the draft to them, or "" when there is none or it has lifted: Settings and
    the due lists held them while their draft was offered as ready to send."""
    from network import state
    text = " ".join(str(c.get("next_action") or "").split())
    if not state.action_hold(text, today, c.get("next_action_due")):
        return ""
    return hold_words(text, state.hold_end(text, c.get("next_action_due")))


# What a hold that waits for a role says after its reason: nothing is drafted until then.
ROLE_HOLD_NOTE = "Claude writes this when a role is posted."
# The reason a group of people on hold shares, where they all wait for a role.
ROLE_WAIT = "waiting for a role to be posted"


def role_posted(ctx: "Ctx", c: dict, msgs=()) -> dict:
    """The posting the search found at their employer since the last message with them, worth
    a look and not applied to, else the person's own open application or interview there
    (followup_drafts.role_for_offer), or {}: what lifts a hold that waits for a role, by
    itself."""
    import followup_drafts
    rows = ctx._once("newest_round_rows", lambda: followup_drafts.newest_round_rows(ctx.today))
    since = max((str(m.get("date") or "")[:10] for m in msgs or ()), default="")
    try:
        return followup_drafts.role_for_offer(c, since, rows, ctx.tracker) or {}
    except Exception:  # noqa: BLE001  no round to read: nothing has been posted
        return {}


def _role_words(text) -> bool:
    from network import state
    return bool(state._ROLE_WORDS.search(str(text or "")))


def on_hold(ctx: "Ctx", c: dict, msgs=()) -> dict | None:
    """The hold on their record (a next action "Hold ...") as the page says it: {"said", "role"
    (it waits for a role to be posted), "until" (its day, or None)}. None when there is none,
    its day has come, or it waited for a role and one is on the list at their employer now
    (role_posted): they come back to the list by themselves."""
    from network import state
    text = " ".join(str(c.get("next_action") or "").split())
    if not state.action_hold(text, ctx.today, c.get("next_action_due")):
        return None
    role = state.role_hold(text)
    if role and role_posted(ctx, c, msgs):
        return None
    until = state.hold_end(text, c.get("next_action_due"))
    return {"said": hold_words(text, until) + (" " + ROLE_HOLD_NOTE if role else ""),
            "role": role, "until": until.isoformat() if until else None}


def note_hold(hold, hold_why, mine: dict | None) -> tuple:
    """(the line, why) a note waits under: held back on purpose before a read that is coming.
    A hold on the person's record or Claude's own decision (`mine`) says itself over the line
    that their profile is read "by itself", which promised work nothing would do while the note
    was held; only the employer's own hold (`employer_full`) comes before it (the audit of
    2026-11-10, DW-2)."""
    if mine and hold_why is None:
        return mine["said"], "decided" if mine.get("decided") else "person_hold"
    return hold, hold_why


def held_by_work(work: dict | None) -> dict:
    """{message id: {"rev", "said", "at"}} from the page's work items: the newest change Claude
    finished on each message, where it held it (`done --outcome held`, or a summary beginning
    "Held" from before the outcome was kept), with the version of the message it was asked
    about. While the message is still that version it is on hold (app.py view passes these)."""
    out: dict = {}
    for _wid, doc in sorted((work or {}).items()):
        w = (doc or {}).get("data") if isinstance(doc, dict) else None
        if not isinstance(w, dict) or str(w.get("status") or "") != "done" \
                or str(w.get("kind") or "") != "tweak":
            continue
        args = w.get("args") if isinstance(w.get("args"), dict) else {}
        target = args.get("target") if isinstance(args.get("target"), dict) else {}
        mid, rev = str(target.get("id") or ""), str(target.get("rev") or "")
        res = w.get("result") if isinstance(w.get("result"), dict) else {}
        said = " ".join(str(res.get("summary") or "").split())
        outcome = str(res.get("outcome") or "")
        if not mid.startswith("msg-") or not rev or args.get("back"):
            continue
        at = str(w.get("finished_at") or w.get("done_at") or w.get("asked_at") or "")
        if mid in out and out[mid]["at"] > at:
            continue
        held = outcome == "held" or (not outcome and bool(re.match(r"^\W*held\b", said, re.I)))
        out[mid] = {"rev": rev, "said": said, "at": at, "held": held}
    return {k: {x: y for x, y in v.items() if x != "held"} for k, v in out.items() if v["held"]}


# ------------------------------------------------------------------ needs you


def _tracker_id(row, seen_ids: set) -> str:
    base = "app-" + (row_slug(row.get("company"), row.get("role")) or "row")
    rid = base
    if rid in seen_ids:
        rid = f"{base}-{row.get('date') or len(seen_ids)}"
    n = 2
    while rid in seen_ids:
        rid, n = f"{base}-{n}", n + 1
    seen_ids.add(rid)
    return rid


def tracker_ids(rows) -> list[str]:
    """One id per tracker row, in file order: app-<employer>_<role>, dated where two share it."""
    seen: set = set()
    return [_tracker_id(r, seen) for r in rows]


def _row_target(row, rid) -> dict:
    return {"kind": "tracker", "id": rid, "date": row.get("date") or "",
            "company": row.get("company") or "", "role": row.get("role") or "",
            "abbr": _abbr(row)}


def _abbr(row) -> str:
    import confirm
    try:
        return confirm.abbr(row)
    except Exception:  # noqa: BLE001
        return ""


def row_rev(row) -> str:
    return rev_of(row.get("date"), row.get("company"), row.get("role"), _status(row),
                  row.get("applied_on"), row.get("confirmed_by"))


def _needs_you(ctx: Ctx, targets: dict) -> list:
    """What only the person can answer: first what only they can do outside the page (their
    private copy, the job sites, the chat on their computer), then the rest."""
    import app_setup
    out = app_setup.outside_items(targets, app_setup.repo_kind_offline())
    try:
        out += _zone_question(ctx, targets)
        out += _profile_questions(ctx, targets)
        out += _skill_questions(ctx, targets)
        sent = _sent_questions(ctx, targets)
        ctx._got["sent_questions"] = sent
        out += sent
        out += _own_profile_card(ctx, targets)
        out += _inmail_ask(ctx, targets)
        out += _tweak_offers(ctx, targets)
        out += _remade_cards(ctx, targets)
        out += _computer_card(ctx, targets)
        out += _unsaved_cards(ctx, targets)
    except person.NoProfile:
        pass
    ups = app_setup.upgrade_questions(targets)
    if any(x["id"] == "q-own-profile" for x in out):
        ups = [x for x in ups if x["id"] != "q-upgrade-own-profile-review"]
    return out + ups


def _unsaved_cards(ctx: Ctx, targets: dict) -> list:
    """One card for each save a chat that handed the page on gave up on (app.py retired,
    after two tries that never reached GitHub; audit HC-3), with no button: it goes by itself
    once that work is on GitHub, or after a fortnight (app.unsaved_saves)."""
    out = []
    for rec in ctx._got.get("unsaved") or []:
        chat = str(rec.get("chat") or "")
        if not chat:
            continue
        when = parse_time(rec.get("since"))
        day = f"{when.day} {when.strftime('%B')}" if when else "lately"
        title = str(rec.get("title") or "Job search page")
        cid = "q-unsaved-" + chat[-12:]
        # The chat's own name (app.py UNSAVED_TITLE, set when it gave up), so the person finds
        # the one chat; an older record names it by its day as well.
        where = (f"the chat \"{title}\"" if day in title else
                 f"the chat \"{title}\" from {day}")
        body = (f"Your last changes in {where} could not be saved. Say \"save your work\" in that "
                "chat and they are saved; this goes by itself then.")
        item = {"id": cid, "kind": "setup", "title": "Some changes are not saved yet",
                "body": body, "steps": [], "options": [], "about": {"step": "unsaved"},
                "rev": rev_of("unsaved", chat, rec.get("since"))}
        targets[cid] = {"kind": "outside", "key": "unsaved", "rev": item["rev"]}
        out.append(item)
    return out


def _computer_card(ctx: Ctx, targets: dict) -> list:
    """One card, only while work for the computer waits and only the person can move it
    (tools/computer.py state, `card`): the computer off, LinkedIn signed out there, or the
    computer not yet switched on for Claude. Nothing else about the computer reaches To do."""
    import computer
    item = computer.card(ctx._got.get("computer") or {})
    if not item:
        return []
    targets[item["id"]] = {"kind": "outside", "key": "computer", "rev": item["rev"]}
    return [item]


TWEAK_OFFERS_MAX = 2
UNCONFIRMED = "UNCONFIRMED"
SKILL_ASKS_MAX = 5


def _skill_questions(ctx: Ctx, targets: dict) -> list:
    """Each skill postings asked about that the person has not answered yet
    (tools/skill_answers.py), asked once for every application that asks it, oldest first:
    drafting chats each asked their own and answered "no" for them (2026-11-04). Yes and No
    weigh the same, and the answer is theirs for every application at once."""
    try:
        import skill_answers
        asks = skill_answers.open_questions()
    except Exception:  # noqa: BLE001  nothing asked yet
        return []
    out = []
    for q in asks[:SKILL_ASKS_MAX]:
        names = list(dict.fromkeys(str(x.get("company") or "").strip() for x in q["for"]
                                   if str(x.get("company") or "").strip()))
        if len(names) <= 2:
            who = " and ".join(names)
        else:
            who = ", ".join(names[:2]) + " and " + (names[2] if len(names) == 3
                                                    else f"{len(names) - 2} more")
        qid = "q-skill-" + q["key"][:40]
        # "Just for this role" (skill_answers.ROLE): a yes for the roles asking, and no other.
        roles = [{"company": str(x.get("company") or "").strip(), "role": str(x.get("role") or "").strip()}
                 for x in q["for"] if str(x.get("company") or "").strip()]
        one = "Just for this role" if len(roles) == 1 else "Just for these roles"
        only = ("" if not roles else f"{one} puts it on this role's resume only, never your "
                "profile. " if len(roles) == 1 else f"{one} puts it on their resumes only, never "
                "your profile. ")
        item = {"id": qid, "kind": "consent",
                "title": f"Can you claim {q['skill']} and back it up in an interview?",
                "body": ((f"{who} {'asks' if len(names) == 1 else 'ask'} for it, and your "
                          "profile doesn't list it. " if who else "A posting asks for it, and "
                          "your profile doesn't list it. ")
                         + "Resumes leave it off until you say. Yes adds it to your profile, "
                           "for every resume. " + only + "No keeps it off them all."),
                "options": [{"label": "Yes, add it to my profile", "action": "needs.answer", "value": "yes"}]
                + ([{"label": one, "action": "needs.answer", "value": "role"}] if roles else [])
                + [{"label": "No", "action": "needs.answer", "value": "no"}],
                "about": {"company": names[0]} if len(names) == 1 else {},
                "rev": rev_of(qid, q["skill"], q.get("asked"), names, roles)}
        out.append(item)
        targets[qid] = {"kind": "skill_ask", "skill": q["skill"], "roles": roles,
                        "rev": item["rev"]}
    return out


def _own_profile_card(ctx: Ctx, targets: dict) -> list:
    """A look at their own LinkedIn profile, when tools/network/own_profile.py says one is
    worth it (never looked, a fact changed, a run of notes unanswered): a To do card, at most
    once in its 30 days, with No thanks writing the same "no" the chat writes."""
    try:
        import own_profile
        kind, reasons = own_profile.due_reasons(ctx.today, ctx.contacts, ctx.threads)
    except Exception:  # noqa: BLE001
        return []
    if not kind:
        return []
    qid = "q-own-profile"
    why = "; ".join(reasons)
    item = {"id": qid, "kind": "suggest", "title": "Look over your LinkedIn profile",
            "body": (why[:1].upper() + why[1:] + ".") if why else "",
            "options": [{"label": "Check it", "work": {"kind": "own_profile",
                                                      "id": "own_profile~check", "args": {}}},
                        {"label": "No thanks", "action": "needs.answer", "value": "no"}],
            "about": {}, "rev": rev_of(qid, kind, reasons)}
    targets[qid] = {"kind": "upgrade_ask", "upgrade": own_profile.UID,
                    "ask": item["title"], "rev": item["rev"]}
    return [item]


def _inmail_ask(ctx: Ctx, targets: dict) -> list:
    """Once a week on a plan with InMail credits: how many LinkedIn shows are left, a number
    kept as `state.py inmail-credits` keeps it, so the people a run picks for an InMail
    (tools/network/inmail_pick.py) are picked against the real balance. Not when it was
    answered, or put off, in the last week (the maintainer, 2026-11-05)."""
    try:
        import claude_surfaces
        import inmail_pick
        if not inmail_pick.ask_due(ctx.today):
            return []
        lines = [re.sub(r"^\s*\d+[.)]\s*", "", x) for x in
                 claude_surfaces.steps(inmail_pick.ASK_STEPS) if re.match(r"^\s*\d+[.)]", x)]
    except Exception:  # noqa: BLE001  no plan or no registry: nothing asked
        return []
    qid = inmail_pick.ASK_ID
    last = inmail_pick.last_asked(ctx.today)
    item = {"id": qid, "kind": "question", "title": inmail_pick.ASK_TITLE,
            "body": "Claude spends them only on people worth one, and keeps one back.",
            "options": [{"label": "InMails left", "action": "inmail.credits", "input": "number"},
                        {"label": "Not this week", "action": "inmail.credits", "value": "later"}],
            "steps": {"label": "Where do I find it?", "lines": lines},
            "about": {}, "rev": rev_of(qid, last.isoformat() if last else "never")}
    targets[qid] = {"kind": "inmail_ask", "rev": item["rev"]}
    return [item]


def _draft_text(cid: str) -> str:
    try:
        import reading
        return reading.note_body(_read(person.state("documents", "network", cid,
                                                    "draft.md"))).strip()
    except Exception:  # noqa: BLE001
        return ""


def _sent_questions(ctx: Ctx, targets: dict) -> list:
    """A send past its day with nothing logged may have gone from LinkedIn itself, where the
    log never hears: asked as a question with answers of equal weight, never shown as a
    row telling them to send again (open_actions UNCONFIRMED; FUNCTIONS_SPEC 1.10)."""
    book = ctx._once("book", lambda: {str(c.get("contact_id") or "").strip(): c
                                      for c in ctx.contacts})
    out = []
    for i in ctx.due_items:
        if i.get("half") != "contact" or not str(i.get("what") or "").startswith(UNCONFIRMED):
            continue
        if (i.get("rule") or {}).get("why") in ("employer", "place", "closed"):
            continue            # their own rules stop anything going to them
        cid = str(i.get("contact_id") or "")
        c = book.get(cid) or {}
        who = first_name(c.get("name")) or "them"
        text = _draft_text(cid)
        kind = _message_kind(ctx.live.get(cid) or str(c.get("status") or ""))
        channel = _channel(c, kind)
        qid = f"q-sent-{cid}"
        tomorrow = (ctx.today + dt.timedelta(days=1)).isoformat()
        item = {"id": qid, "kind": "confirm",
                "title": f"Did your note to {who} go?",
                "body": f"It was due on {i['due']} and nothing is logged yet. LinkedIn does not "
                        "tell the app when one goes from its own pages.",
                # It went on or about the day it was due, not on the day it was asked: logged
                # as sent today, the 14-day follow-up counted from the wrong day (journeys
                # audit 14). The page offers another day.
                "options": [{"label": "Yes, it went", "action": "msg.sent",
                             "value": dict({"draft": True} if text else {"outside": True},
                                           **({"on": i["due"]} if str(i.get("due") or "")
                                              and str(i["due"]) <= ctx.today.isoformat()
                                              else {}))},
                            {"label": "Not yet", "action": "due.snooze",
                             "value": {"until": tomorrow}}],
                "edit": {"label": "It went with other words", "action": "msg.sent",
                         "field": "text"} if text else None,
                "about": {"company": str(c.get("company") or ""), "contact": cid},
                "rev": rev_of(qid, i["due"], text)}
        out.append(item)
        targets[qid] = {"kind": "message", "contact": cid, "text": text, "msg_kind": kind,
                        "channel": channel, "rev": item["rev"]}
    return out


def _tweak_offers(ctx: Ctx, targets: dict) -> list:
    """What the person asked of the Tweak box three times, offered once as a usual or a
    button of their own (tools/tweak.py promote); a Not now comes back after 30 days."""
    import tweak
    out = []
    for o in tweak.promote(ctx.today)[:TWEAK_OFFERS_MAX]:
        qid = f"q-tweak-{o['id']}"
        item = {"id": qid, "kind": "question", "title": o["line"],
                "body": "From what you asked for on your " + o["output"] + "s.",
                "options": [{"label": "Yes", "action": "tweak.offer", "value": "yes"},
                            {"label": "Not now", "action": "tweak.offer", "value": "no"}],
                "about": {"tweak_offer": o["id"]}, "rev": rev_of(qid, o["line"], o["times"])}
        out.append(item)
        targets[qid] = {"kind": "tweak_offer", "id": o["id"], "rev": item["rev"]}
    return out


def _remade_cards(ctx: Ctx, targets: dict) -> list:
    """An unsent application the drafts rerun made again that failed in a way only the
    person can settle (tools/remake_drafts.py, its remake.json): one To do card naming it,
    with the app's own way forward, until it passes. One that a redraft can put right is
    queued instead, and has no card (remake_drafts.page_work)."""
    try:
        import remake_drafts
        cards = remake_drafts.todo_cards()
    except Exception:  # noqa: BLE001  nothing remade to read: no card
        return []
    rows = {rid: row for row, rid in zip(ctx.tracker, ctx.tracker_ids)}
    out = []
    for c in cards:
        row = rows.get(c["app"])
        if row is None:
            continue
        why = c["why"][:1].upper() + c["why"][1:] if c["why"] else "A check did not pass"
        item = {"id": c["id"], "kind": "suggest",
                "title": f"{c['company']}: made again with the newest checks, and it did "
                         "not pass",
                "body": f"{why}. It is not sent until it passes.",
                "options": [{"label": "Make it again",
                             "work": {"kind": "draft", "id": f"draft~{c['app']}",
                                      "args": {"company": c["company"], "role": c["role"],
                                               "application": c["app"], "redo": True}}},
                            {"label": "Not applying", "action": "ready.not_applying"}],
                "about": {"company": c["company"], "role": c["role"]},
                "rev": rev_of(c["id"], c["why"], c["version"])}
        out.append(item)
        targets[c["id"]] = dict(_row_target(row, c["app"]), rev=item["rev"])
    return out


def _profile_questions(ctx: Ctx, targets: dict) -> list:
    import confirm
    out = []
    rows = ctx.tracker
    ids = ctx.tracker_ids
    said = confirm.check(rows, ctx.today).get("notes say sent, tracker says drafted", [])
    if said:
        import throttle
        from company_key import key as _ckey

        def same(r):
            return (_ckey(r.get("company") or ""), " ".join(str(r.get("role") or "").lower().split()))
        # The role at that employer already recorded as sent on or after this draft's day is
        # in Applied: "Did you apply to Fernhill Freight?" stood over Applied listing it (the
        # screen review, 2026-11-11), and a second row of the same role was asked about too,
        # applied as it was. Only a draft, never a row already sent, is asked.
        sent_on: dict = {}
        for r in rows:
            on = str(throttle.applied_on(r) or "")[:10]
            if on and _status(r) not in throttle.UNSENT:
                sent_on[same(r)] = max(sent_on.get(same(r), ""), on)
        for row, rid in zip(rows, ids):
            label = confirm.label(row)
            if not any(line.startswith(label + ":") for line in said):
                continue
            if _status(row) not in throttle.UNSENT or \
                    sent_on.get(same(row), "") >= str(row.get("date") or "")[:10] > "":
                continue
            nid = "q-" + rid
            company, role = row.get("company") or "", row.get("role") or "role not recorded"
            item = {"id": nid, "kind": "confirm", "title": f"Did you apply to {company}?",
                    "body": f"The notes for {role} say it went, but it is still marked as "
                            "not sent.",
                    "options": [{"label": "Yes, I applied", "action": "ready.applied"},
                                {"label": "Not yet", "action": "ready.not_applied"}],
                    "about": {"company": company, "role": role}, "rev": row_rev(row)}
            out.append(item)
            targets[nid] = dict(_row_target(row, rid), rev=item["rev"])
    try:
        import learned
        for n, o in learned.offers(ctx.today):
            nid = f"q-choice-{n}"
            body = " ".join(x for x in (o.get("new"), o.get("why")) if x).strip()
            if o.get("again"):
                body += f" (Asked again: {o['again']}.)"
            item = {"id": nid, "kind": "question",
                    "title": "The app does this differently now. Keep your way, or try the "
                             "new one?",
                    "body": body,
                    "options": [{"label": "Keep mine", "action": "needs.answer", "value": "keep"},
                                {"label": "Try the new way", "action": "needs.answer",
                                 "value": "switch"}],
                    "about": {"setting": o.get("setting", "")},
                    "rev": rev_of(n, o.get("setting"), o.get("version"), o.get("decision"),
                                  o.get("decided"))}
            out.append(item)
            targets[nid] = {"kind": "offer", "n": n, "rev": item["rev"]}
    except Exception:  # noqa: BLE001  no learned.json: no choice waiting
        pass
    # The one question about the rules they taught, when a chat could not tell which of two
    # stands (learned.ask): one at most, and seldom.
    try:
        import learned
        q = learned.asked()
        if q:
            o, l = q["older_rule"], q["later_rule"]
            nid = f"q-rule-{q['older']}-{q['later']}"
            item = {"id": nid, "kind": "question",
                    "title": "Two things you told Claude may not fit together. Which stands?",
                    "body": f"Earlier ({o.get('date')}): {o.get('rule')} Later ({l.get('date')}): "
                            f"{l.get('rule')}",
                    "options": [{"label": "The later one", "action": "needs.answer", "value": "later"},
                                {"label": "Both", "action": "needs.answer", "value": "both"},
                                {"label": "The earlier one", "action": "needs.answer", "value": "older"}],
                    "about": {}, "rev": rev_of(nid, q.get("asked"))}
            out.append(item)
            targets[nid] = {"kind": "rule_ask", "rev": item["rev"]}
    except Exception:  # noqa: BLE001  no learned.json: nothing asked
        pass
    try:
        import profile_upgrades
        found = profile_upgrades.unconfirmed()
    except Exception:  # noqa: BLE001
        found = []
    for where, what in found[:CONFIRM_MAX]:
        nid = "q-fact-" + rev_of(where, what)[:8]
        item = {"id": nid, "kind": "question", "title": what[:1].upper() + what[1:] + "?",
                "body": "Your profile has this marked to confirm. Your answer is written "
                        "where the mark is.",
                "options": [{"label": "Answer", "action": "needs.answer", "input": "text"}],
                "about": {}, "rev": rev_of(where, what)}
        out.append(item)
        targets[nid] = {"kind": "fact", "file": where, "what": what, "rev": item["rev"]}
    return out


# ------------------------------------------------------------------ jobs


_ROUND_DAY: dict = {}


def round_day(path: str) -> dt.date | None:
    """The day a saved search ran: the latest day a posting in it was first seen, else the
    day the file was last saved to git, else the file's own time. Round numbers restart, so
    the highest number is not the newest: r29 from mid October sat over r11 from the 24th
    (the maintainer's copy, 2026-10-29)."""
    if path in _ROUND_DAY:
        return _ROUND_DAY[path]
    rows = _json(path, [])
    days = [_date(str(r.get("first_seen") or "")[:10]) for r in rows if isinstance(r, dict)] \
        if isinstance(rows, list) else []
    day = max((d for d in days if d), default=None)
    if day is None:
        try:
            got = subprocess.run(["git", "log", "-1", "--format=%cs", "--", path],
                                 cwd=os.path.dirname(path) or ".", capture_output=True,
                                 text=True, encoding="utf-8", errors="replace", timeout=10,
                                 stdin=subprocess.DEVNULL)
            day = _date(got.stdout.strip()) if got.returncode == 0 else None
        except (OSError, subprocess.TimeoutExpired):
            day = None
    if day is None and _mtime(path):
        day = _date(_mtime(path)[:10])
    _ROUND_DAY[path] = day
    return day


def rounds_dir(name: str) -> str:
    return person.state("documents", "rounds", name + ".json")


def _round_key(path: str) -> tuple:
    import run_round
    return (round_day(path) or dt.date.min,) + run_round.round_order(path)


def newest_round() -> str:
    files = [p for p in glob.glob(person.state("documents", "rounds", "*.json"))
             if os.path.isfile(p)]
    return max(files, key=_round_key) if files else ""


def _band(score) -> str:
    if score is None:
        return ""
    return "strong" if score >= 75 else "good" if score >= 60 else "fair"


def _remote(place: str) -> str:
    low = place.lower()
    if "remote" in low:
        return "remote"
    if "hybrid" in low:
        return "hybrid"
    if re.search(r"on[- ]?site|in[- ]office", low):
        return "on-site"
    return ""


def apply_link(row: dict) -> dict:
    import apply_link as al
    url = row.get("apply_url") or al.clean(row.get("url") or row.get("source") or "") or ""
    kind = {"linkedin": "linkedin", "aggregator": "aggregator", "login wall": "board",
            "board": "employer", "employer": "employer"}.get(al.kind(url) if url else "", "")
    check = str(row.get("link_check") or "")
    m = re.search(r"(\d{4}-\d{2}-\d{2})(?:[ T](\d{2}:\d{2})(\s*UTC)?)?", check)
    # apply_link.py's own words: "open on <employer>'s own board, checked <when>", "closed:
    # no longer on ...", or "not checked: ..."; `link_status` where the row kept it.
    said = str(row.get("link_status") or "").strip().lower()
    low = check.lower()
    status = ("closed" if said == "closed" or low.startswith("closed") else
              "open" if said == "open" or low.startswith(("open", "checked")) else
              "not_checked")
    # apply_link.py stamps its checks in UTC ("checked 2026-10-25 09:30 UTC"). A stamp from
    # before that carries the checking chat's own clock with no zone, so for one of those the
    # model says the day only and no time it cannot place.
    checked = m.group(1) if m and status != "not_checked" else None
    at = (f"{m.group(1)}T{m.group(2)}:00Z" if checked and m.group(2) and m.group(3) else None)
    return {"url": url, "kind": kind, "checked_on": checked, "checked_at": at,
            "status": status}


def _company_rows(rows) -> dict:
    from company_key import key
    out: dict = {}
    for i, r in enumerate(rows):
        out.setdefault(key(r.get("company")), []).append(i)
    return out


def tracker_match(ctx: Ctx, company, title) -> dict | None:
    """The tracker's row for this posting: the same employer key and the same title."""
    import throttle
    from company_key import key
    by = ctx._once("tracker_by_company", lambda: _company_rows(ctx.tracker))
    hit = None
    for i in by.get(key(company), ()):
        r = ctx.tracker[i]
        if throttle.same_title(r.get("role"), title):
            hit = r
    return hit


_tracker_match = tracker_match  # the module's own name for it; other modules call tracker_match


def _tracker_by_link(ctx: Ctx, url) -> dict | None:
    """The tracker's row whose posting link (`source`) is this one, or None."""
    from lookup_score import norm
    u = norm(str(url or ""))
    if not u:
        return None
    by = ctx._once("tracker_by_link", lambda: {
        norm(str(r.get("source") or "")): r for r in ctx.tracker
        if str(r.get("source") or "").startswith("http")})
    return by.get(u)


def _warm(ctx: Ctx, company) -> str | None:
    from company_key import key
    _, warm, holds = ctx.network
    k = key(company)
    if k in holds:
        who = next((c for c in ctx.contacts if c.get("contact_id") and
                    ctx.live.get(c["contact_id"]) == "referral_in_progress"
                    and key(c.get("company")) == k), {})
        name = first_name(who.get("name")) or "someone there"
        return f"{name} has put your name forward here: do not apply cold."
    people = warm.get(k) or []
    if people:
        name = first_name(people[0].get("name")) or "someone there"
        return f"{name} at {company} has replied to you: ask them first."
    return None


def _list(ctx: Ctx, name: str, full: list, shown: int, folded=None, doc: bool = True) -> None:
    """Keep a list's whole, cut-down form for `lists` and the database (tools/app_lists.py)."""
    ctx._got.setdefault("lists", {})[name] = (full, shown, folded, doc)


def _pay_top(pay: str):
    """(the top of a stated range, whether it reaches the profile's target) or (None, None)."""
    if not pay:
        return None, None
    try:
        import text_screen
        _, hi, _ = text_screen.salary_range(f"Salary: {pay}.")
        target = getattr(person.module("search"), "SALARY_TARGET", None)
    except Exception:  # noqa: BLE001  a pay line nothing reads is shown as it is
        return None, None
    return hi, (None if hi is None or not target else hi >= target)


def _card(ctx: Ctx, targets: dict, item: dict, how: str, *more) -> None:
    """A card's `alerts` and `suggest` (tools/app_alerts.py), and the suggestion's target
    for `suggest.dismiss`. One the person said No thanks to is never built again."""
    import app_alerts
    alerts, sug = getattr(app_alerts, how)(ctx, item, *more)
    if sug and sug["id"] in ctx._once("suggest_no", app_alerts.dismissed):
        sug = None
    item["alerts"], item["suggest"] = alerts, sug
    # A button on the card's alert or suggestion acts on the card: it carries the card's rev
    # for the page to send as rev_seen, as the card's own buttons do (FUNCTIONS_SPEC 4.2).
    for a in alerts + ([sug] if sug else []):
        act = a.get("action") if isinstance(a, dict) else None
        if isinstance(act, dict) and act.get("type") == "act" and act.get("item") in (
                None, "", item.get("id")):
            act["rev"] = item.get("rev")
    if sug:
        targets[sug["id"]] = {"kind": "suggest", "id": sug["id"], "item": item["id"],
                              "sug_kind": sug["kind"], "rev": sug["rev"]}


CARRY_DAYS = 14
KEPT_FILE = ("documents", "rounds", "kept", "jobs.json")


def kept_jobs() -> dict:
    """{posting link: {round, rank, title, company, kept_on}}: the jobs the person said to
    keep for later, which stay on the list past any number of searches until decided."""
    got = _json(person.state(*KEPT_FILE), {})
    return got if isinstance(got, dict) else {}


def why_of(fit_why) -> list[str]:
    """Two short reasons for a score, from the round's own fit reasons: the strongest match
    and the strongest gap, each without its points."""
    r = reasons_of(fit_why)
    return [x.rstrip(".") for x in (r["good"], r["watch"]) if x]


def reasons_of(fit_why) -> dict:
    """The score's reasons as More says them, apart: `good`, the strongest match, and
    `watch`, the strongest gap, each one plain sentence or "". Run together ("Why 100:
    Matches your skills ... Asks for a graduate degree") a gap read as a contradiction of
    the 100 (the maintainer, 2026-11-04)."""
    plus, minus = [], []
    for w in fit_why or ():
        m = re.match(r"^\s*([+-])\s*(\d+)\s+(.*)$", str(w))
        if not m:
            continue
        (plus if m.group(1) == "+" else minus).append((int(m.group(2)), m.group(3).strip()))
    out = {"good": "", "watch": ""}
    for key, group in (("good", plus), ("watch", minus)):
        if group:
            text = max(group)[1]
            text = re.split(r";", text)[0].strip()
            for rx, plain in _WHY_PLAIN:
                text = rx.sub(plain, text)
            text = " ".join(text.split()).strip(" ,")
            if text:
                out[key] = (text[:1].upper() + text[1:120]).rstrip(".") + "."
    return out


# The score's reasons as the card says them: the scorer writes for the chat ("core match",
# "live contact at this employer (...), so this is not a cold application").
_WHY_PLAIN = [
    (re.compile(r"\s*\(softened from [^)]*\)", re.I), ""),
    (re.compile(r"^core match: ", re.I), "matches your skills: "),
    (re.compile(r"^live contact at this employer \(([^)]*)\).*$", re.I), r"you know \1 there"),
    (re.compile(r"^they interviewed you before \(([^)]*)\)$", re.I), r"they interviewed you before, for \1"),
    # "with no other way in" read as a riddle (2026-11-04).
    (re.compile(r"^graduate degree stated without an equivalence route.*$", re.I),
     "asks for a graduate degree, and does not say experience can stand in for one"),
    (re.compile(r"^(senior|mid|junior)[^,]*, the band the profile holds$", re.I),
     r"\1, the level you are at"),
    (re.compile(r"^stated (\d+)\+ years(?:, a [^,]*)?(?: against (\d+) held)?.*$", re.I),
     lambda m: f"asks for {m.group(1)}+ years" + (f"; you have {m.group(2)}" if m.group(2) else "")),
    (re.compile(r"^(\d+)\+ years (?:wanted|demanded) in a domain not worked \(([^)]*)\).*$", re.I),
     r"asks for \1+ years in \2, which you have not worked in"),
    (re.compile(r"^junior, new-grad or student posting.*$", re.I), "a junior or graduate role, below your level"),
    (re.compile(r"^location flagged: ", re.I), ""),
]


def short_place(place) -> str:
    """A posting's place as a card's one line of facts says it: the town alone where the
    posting adds its region and country ("Toronto, Ontario, Canada" is "Toronto", the
    maintainer, 2026-11-04), and a place that starts with how it is worked ("Remote, UK")
    kept whole."""
    s = " ".join(str(place or "").split())
    parts = [x.strip() for x in s.split(",") if x.strip()]
    if len(parts) < 2 or re.fullmatch(r"(?i)remote|hybrid|on[- ]?site|anywhere|various", parts[0]):
        return s
    how = re.search(r"\(([^)]*)\)\s*$", parts[-1])
    head = parts[0]
    return head + (f" ({how.group(1)})" if how and how.group(1).lower() not in head.lower() else "")


def near_words(item: dict, noun: str = "resume") -> str:
    """The near matches on a job or a draft in one plain sentence for its More, or "" when
    there are none, or when the card's own suggestion already offers the one there is."""
    sg = item.get("suggest") or {}
    offered = str(sg.get("text") or "").lower() if sg.get("kind") == "near" else ""
    near = [n for n in item.get("near") or [] if isinstance(n, dict) and n.get("asked") and n.get("have")
            and not (offered and str(n["asked"]).lower() in offered)]
    if not near:
        return ""
    if len(near) > 1:
        return (f"It asks for {len(near)} tools you have close matches for; your {noun} "
                "names yours.")
    one = near[0]
    if one.get("yes"):
        return f"It asks for {one['asked']}, which you said you have used."
    return f"It asks for {one['asked']}. You have {one['have']}, so your {noun} names {one['have']}."


def job_rev(url: str, company: str, title: str, status: str) -> str:
    """A job row's rev: what an action on it acts on, the posting and where it stands. Never
    its score, rank or wording, which a search run again or a newer build redraws: a tap made
    before that was refused as "changed since you saw it" (2026-11-04). A round reads the
    page's waiting taps by it (run_round.page_set_asides)."""
    return rev_of(url or (company, title), status)


def draft_work_id(url: str, company: str = "", title: str = "") -> str:
    """The one id of the work that drafts a posting, for the page and the engine alike:
    the posting's own link, so the same posting found in two rounds is one draft."""
    from lookup_score import norm
    return "draft~" + rev_of(norm(url or "") or (company, title))[:10]


def _earlier_rows(ctx: Ctx, newest: str) -> list[tuple[str, int, dict]]:
    """(round, rank, row) for each posting from an earlier search the person has not
    decided on: found in the last CARRY_DAYS days, or kept for later, and not in the newest
    round (FUNCTIONS_SPEC 1.1)."""
    return carried(ctx.today, newest)


def carried(today: dt.date, newest: str = "", but=()) -> list[tuple[str, int, dict]]:
    """(round, rank, row) for each posting Jobs carries from a saved search other than
    `newest` (its file) and the rounds named in `but`: found in the last CARRY_DAYS days, or
    kept for later, once each. The one answer to "is it on the list already": the page lists
    these as from an earlier search, and a search passes them over (run_round.already_had)."""
    from lookup_score import norm
    skip = set(but)
    files = sorted((p for p in glob.glob(person.state("documents", "rounds", "*.json"))
                    if os.path.isfile(p) and p != newest
                    and os.path.splitext(os.path.basename(p))[0] not in skip),
                   key=_round_key, reverse=True)
    kept = {norm(u): k for u, k in kept_jobs().items()}
    have = {norm(r.get("url") or "") for r in ((_json(newest, []) or []) if newest else [])
            if isinstance(r, dict)}
    out, seen = [], set(have)
    for p in files:
        name = os.path.splitext(os.path.basename(p))[0]
        made = round_day(p)
        recent = made is not None and 0 <= (today - made).days <= CARRY_DAYS
        rows = _json(p, [])
        rows = rows if isinstance(rows, list) else []
        for rank, r in enumerate(rows, 1):
            if not isinstance(r, dict):
                continue
            u = norm(r.get("url") or "")
            if not u or u in seen:
                continue
            if recent or u in kept:
                seen.add(u)
                out.append((name, rank, r))
    return out


def _jobs(ctx: Ctx, targets: dict) -> dict:
    import app_lists
    import run_round
    import throttle
    from lookup_score import norm
    path = newest_round()
    if not path:
        return {"round": "", "made_at": None, "met": False,
                "summary": "No search has run yet.", "rows": [],
                "filtered": {"count": 0, "groups": []}}
    name = os.path.splitext(os.path.basename(path))[0]
    raw = _json(path, [])
    raw = raw if isinstance(raw, list) else list(raw.values()) if isinstance(raw, dict) else []
    rows = []
    kept = {norm(u) for u in kept_jobs()}
    # A posting's title, pay or place as the person corrected it on its card (job.edit), kept
    # with the posting in the kept list: what the search read was wrong (2026-11-05).
    corrected = {norm(u): k.get("edit") for u, k in kept_jobs().items()
                 if isinstance(k, dict) and isinstance(k.get("edit"), dict)}
    window = run_round._job_age_days()
    import added_jobs
    found = ([("added", n, r) for n, r in enumerate(added_jobs.load(), 1)]
             + [(name, rank, r) for rank, r in enumerate(raw, 1)] + _earlier_rows(ctx, path))
    try:
        cut = run_round.page_rules(ctx.today, rulings=ctx.seen)
    except Exception as e:  # noqa: BLE001  the rules unreadable: the list as the search left it
        print(f"app: Jobs is shown without its rules read again ({e})", file=sys.stderr)
        cut = _no_rules
    left = ctx._got.setdefault("jobs_left_out", [])
    staged: list[list] = []
    for rname, rank, r in found:
        if not isinstance(r, dict):
            continue
        added = rname == "added"
        earlier = rname != name and not added
        score = r.get("fit") if r.get("fit") is not None else r.get("priority")
        score = round(score) if isinstance(score, (int, float)) else None
        url = r.get("url") or ""
        company, title = str(r.get("company") or ""), str(r.get("title") or "")
        entry = ctx.seen.get(norm(url) or url) if url else None
        # By the employer and the role, else by the posting's own link: the role applied to
        # under a title the board has changed since read "Draft this" (2026-11-05).
        tracked = _tracker_match(ctx, company, title) or _tracker_by_link(ctx, url)
        st = _status(tracked) if tracked else ""
        # Ruled out by the person, or by a chat that found it is not one they can take (a draft
        # stopped on where the job is open): either way it leaves the list and its counts. One
        # stopped for that stayed in "10 jobs to look at" (2026-10-30).
        # Sent first: a role the tracker holds as applied is Applied whatever a ruling on its
        # posting says. One applied in September and ruled out since read "Set aside" with
        # "Bring back", offering a second application (2026-11-03). Sent is a day it went: a
        # draft set aside ("they chose not to send it") has none, and stays set aside.
        sent = bool(tracked) and bool(st) and st not in throttle.UNSENT \
            and bool(throttle.applied_on(tracked))
        if sent:
            status = "applied"
        elif entry and str(entry.get("status") or "").lower() == "excluded" \
                and entry.get("basis") == "person" and _set_aside_holds(entry, ctx.today):
            # A role the person set aside holds until its own end (about six months, or for
            # good where their words said so: exclude.set_aside_until), never for ever. One a
            # search's rules left out (basis rules) is the rule's, asked below (`cut`) whether
            # that rule still holds: read here as set aside, it stayed set aside for good.
            status = "dismissed"
        elif tracked and st not in throttle.UNSENT and st:
            status = "applied"
        elif tracked and str(tracked.get("cv_file") or "").strip():
            status = "ready"
        else:
            status = "new"
        place = str(r.get("location") or "")
        pay = str(r.get("salary") or r.get("pay") or "").strip()
        fixed = corrected.get(norm(url)) if url else None
        if fixed:
            title = str(fixed.get("title") or title)
            place = str(fixed.get("place") or place)
            pay = str(fixed.get("pay") or pay)
        notes = []
        if (earlier or added) and status not in ("new", "ready"):
            continue               # decided since: an earlier search's row stays there
        if status == "dismissed" and entry and entry.get("by") == "chat":
            # A draft a chat stopped (app.py done --left-out): its reason, on the row.
            notes.append(left_words(str(entry.get("exclusion_reason") or "")))
        if earlier:
            notes.append("From an earlier search.")
        if added:
            notes.append("You added this one.")
        if r.get("brought_back"):
            notes.append("You brought this back after it was filtered out.")
        if r.get("bar_reason"):
            said = bar_words(r.get("bar"), scrub(r["bar_reason"], ctx.names))
            if said:
                notes.append(said)
        if r.get("silent_application_note"):
            notes.append("You applied here before and never heard back: check before "
                         "applying again.")
        if r.get("set_aside_note"):
            notes.append(str(r["set_aside_note"]).rstrip(".") + ".")
        if r.get("aimed_at_ai"):
            # Words in the posting written to an AI tool reading it (hydrate.aimed_at_ai).
            # Said, and never a reason to leave the job off the list.
            notes.append(AIMED_AT_AI_WORDS)
        if r.get("outreach_pending_note"):
            notes.append(_pending_words(_waiting_at(ctx, company)))
        if r.get("referral_note"):
            # Kept, never dropped, for a referral in progress here (throttle.employer_stops).
            notes.append("Someone is referring you here: apply through them, never on your own.")
        # Counted to today: the posting's own date where the search read one, else its age
        # on the day the search ran plus the days since. A search's own count stays as it
        # was, so a row found on the 21st said "posted 1 day ago" a week on (2026-10-29).
        # The older of the two, as the search window reads it (prefilter.age_days): a relisted
        # posting's portal date said "posted 3 days ago" of one the gate knew was 4 days old,
        # and "new" of one months old (2026-11-03).
        posted = app_lists.ago(r.get("date"), ctx.today) if _date(str(r.get("date") or "")[:10]) \
            else None
        if isinstance(r.get("age_days"), int):
            ran = round_day(rounds_dir(rname)) if not added else None
            gate = r["age_days"] + max(0, (ctx.today - ran).days) if ran else r["age_days"]
            posted = gate if posted is None else max(posted, gate)
        if posted is None:
            posted = app_lists.ago(r.get("first_seen"), ctx.today)
        # Never the search file's own time, which a fresh copy of the files moves.
        found_day = found_on(r, entry)
        found_day = min(found_day, ctx.today) if found_day else None   # never after today
        # Past the person's own search window, a posting nobody has decided on leaves the list
        # by itself, counted to today from its own date: the week rule hung on a chat
        # remembering to clear it, measured from the day it was found (2026-11-03).
        if status == "new" and not added and posted is not None and posted > window \
                and not (url and norm(url) in kept):
            continue
        # The search's own hard rules, read down the list (run_round.page_rules, the one
        # function its shortlist is cut by): a row failing one now is never a fresh find. A
        # "find 20 more" left 18 of 37 to clear by hand, US-based, failing the bar, or a copy
        # of a role drafted or applied for (2026-11-05). What the person chose stays: a job
        # they added, kept or brought back, and one they took off a ruling.
        mine = added or (url and norm(url) in kept) or bool(r.get("brought_back")) \
            or (entry is not None and str(entry.get("status") or "").lower() == "lifted")
        why = cut(r) if status == "new" and not mine else ""
        if not why and status == "ready" and not mine and entry \
                and entry.get("basis") == "rules" \
                and str(entry.get("status") or "").lower() == "excluded":
            # A draft a chat stopped, ruling the role out by the rules (one they cannot take):
            # it leaves the list while that rule holds, as an undrafted one does (`standing`).
            why = cut.standing(r)
        # A posting the employer's own board no longer lists is set aside by itself, with its
        # way back under Set aside: a card asking to set it aside was one more thing to do
        # about nothing (the UX review, 2026-11-05). Brought back, it stays (lifted).
        if not why and status == "new" and not mine and apply_link(r).get("status") == "closed":
            why = CLOSED_WHY
        if why:
            # A ruling already recorded (a search's rules left it out before, basis rules) is
            # on that search's left-out list: never put on another's again.
            if not (entry and entry.get("basis") == "rules"
                    and str(entry.get("status") or "").lower() == "excluded"):
                left.append((rname, rank, r, why))
            if earlier:
                continue               # an earlier search's row: it stays with that search
            status = "dismissed"
            notes.append(left_words(why))
        elif status in ("new", "ready", "applied"):
            cut.note(r, "you added it" if added else f"from search {rname}" if earlier
                     else "from this search")
        staged.append({"rname": rname, "rank": rank, "r": r, "added": added, "earlier": earlier,
                       "score": score, "url": url, "company": company, "title": title,
                       "status": status, "place": place, "pay": pay, "notes": notes,
                       "posted": posted, "found_day": found_day,
                       "open": status == "new" and not mine and not why})
    # One open role per employer across the whole list, whichever search found it: of the
    # roles nobody has decided on, the one that fits best stays and each other is set aside
    # with its reason and its way back (Bring back marks it lifted, so it stays). Only one
    # search's own shortlist kept to one, so three roles at one employer from three searches
    # all reached Jobs (the maintainer, 2026-11-05). A role the person added, kept, brought
    # back, drafted or applied for is never one of them.
    contending = [c for c in staged if c["open"]]
    for at, why in run_round.extra_roles([c["r"] for c in contending]).items():
        c = contending[at]
        left.append((c["rname"], c["rank"], c["r"], why))
        c["status"] = "dismissed"
        c["notes"].append(left_words(why))
    for c in staged:
        rname, rank, r, added, earlier = c["rname"], c["rank"], c["r"], c["added"], c["earlier"]
        score, url, company, title, status = (c["score"], c["url"], c["company"], c["title"],
                                              c["status"])
        place, pay, notes, posted, found_day = (c["place"], c["pay"], c["notes"], c["posted"],
                                                c["found_day"])
        jid = f"{rname}-{rank}"
        top, at_target = _pay_top(pay)
        item = {"id": jid, "rank": rank, "score": score, "band": _band(score),
                "company": company, "title": title, "place": place, "remote": _remote(place),
                "place_short": short_place(place),
                "pay": {"text": pay or "not stated", "stated": bool(pay), "top": top,
                        "at_target": at_target},
                "posted_days": posted,
                # The day it was first found, for "found today" on its card: searches run more
                # than once, and one surfaced weeks ago may be one to put away (the
                # maintainer, 2026-11-05).
                "found_on": found_day.isoformat() if found_day else None,
                "found_days": (ctx.today - found_day).days if found_day else None,
                # The tools it asks for that the person holds one of the same kind for (fit.py
                # near_matches, kept by the round), for "Asked for Tableau, you have Power BI".
                "near": [{"asked": str(x.get("asked") or ""), "have": str(x.get("have") or "")}
                         for x in (r.get("near") or []) if isinstance(x, dict)][:5],
                "deadline": r.get("deadline") or None, "warm": _warm(ctx, company),
                "draft_work": {"kind": "draft", "id": draft_work_id(url, company, title),
                               "args": {"round": rname, "rank": rank, "url": url,
                                        "company": company, "title": title}},
                "why": [scrub(w, ctx.names) for w in why_of(r.get("fit_why"))],
                "reasons": {k: scrub(v, ctx.names) for k, v in reasons_of(r.get("fit_why")).items()},
                "from_round": rname if earlier else None,
                "added": added,
                "kept": norm(url) in kept if url else False,
                "apply": apply_link(r), "notes": notes, "status": status,
                "questions": (["Have you already applied?"] if status == "new" else [])
                + [str(q) for q in (r.get("questions") if isinstance(r.get("questions"), list)
                                    else []) if str(q).strip()],
                "rev": job_rev(url, company, title, status)}
        _card(ctx, targets, item, "for_job")
        item["near_words"] = near_words(item, _noun())
        rows.append(item)
        targets[jid] = {"kind": "job", "round": rname, "rank": rank, "url": url,
                        "company": company, "title": title, "place": place,
                        "rev": item["rev"]}
    _list(ctx, "jobs", [{"id": r["id"], "status": r["status"], "remote": r["remote"] or "not said",
                         "band": r["band"] or "none", "company": r["company"],
                         "pay": ("at_target" if r["pay"]["at_target"] else "stated"
                                 if r["pay"]["stated"] else "not_stated"),
                         "posted": app_lists.bucket(r["posted_days"], app_lists.POSTED)}
                        for r in rows], len(rows), 0, doc=False)
    good, strong = run_round.yield_of(path)
    met = good >= run_round.YIELD_60 and strong >= run_round.YIELD_75
    filtered = _filtered(name, targets, ctx)
    # What Jobs lists to look at, counted once here: a role not applied for, not set aside,
    # not closed and not drafted. "10 roles on the shortlist" counted the one applied for
    # and the one set aside beside a page that said 4 (2026-11-03).
    look = [r for r in rows if to_look_at(r)]
    now = [r for r in look if not r["from_round"] and not r["added"]]
    n75 = sum(1 for r in now if (r["score"] or 0) >= 75)
    summary = (f"{len(now)} {'role' if len(now) == 1 else 'roles'} from the last search to look "
               f"at, {n75} of them scoring 75 or more.")
    if len(look) > len(now):
        summary += f" {len(look) - len(now)} more from earlier searches, not decided yet."
    if filtered["count"]:
        summary += f" {filtered['count']} left out, each with its reason."
    made = saved_at(path)
    return {"round": name, "made_at": stamp(made) if made else None, "met": met,
            "summary": summary,
            "rows": rows, "filtered": filtered}


def found_on(row: dict, seen: dict | None = None, ran: dt.date | None = None) -> dt.date | None:
    """The day a job was first found: the earliest of the day the searches first saw its
    posting (the round's `first_seen`, the seen list's own) and the day the person added it,
    else `ran`, a day its search is known to have run, or None."""
    days = [_date(str(x or "")[:10]) for x in (row.get("first_seen"), (seen or {}).get("first_seen"),
                                               row.get("added_on"))]
    days = [d for d in days if d]
    return min(days) if days else ran


def _noun() -> str:
    """What the person calls the document: resume, or CV (person.json `documents.noun`)."""
    try:
        return str(person.get("documents.noun", "resume") or "resume")
    except person.NoProfile:
        return "resume"


def _waiting_at(ctx: Ctx, company: str) -> list:
    """The people at `company` who have the person's message and have not replied, from
    the contact book as it stands (throttle.pending_outreach, the round's own reading of
    it), less anyone who has replied since."""
    from company_key import key
    import throttle

    def make():
        try:
            return throttle.pending_outreach(rows=ctx.contacts, live=ctx.live)
        except Exception:  # noqa: BLE001  no book, no names: the note says "someone"
            return {}
    return ctx._once("pending_outreach", make).get(key(company)) or []


def _pending_words(waiting) -> str:
    """Who has the person's message and has not replied, by first name, for a job at their
    employer: "Someone here" sat beside a box saying someone there had replied, and the two
    read as one person said two ways (the maintainer, 2026-11-04)."""
    names = []
    for q in waiting if isinstance(waiting, list) else []:
        n = first_name(q.get("name")) if isinstance(q, dict) else ""
        if n and n not in names:
            names.append(n)
    if not names:
        return ("Someone here has your message and has not replied: applying is fine, a "
                "second message is not.")
    if len(names) == 1:
        return (f"{names[0]} has your message and has not replied: applying is fine, a "
                "second message is not.")
    who = (" and ".join(names) if len(names) == 2 else ", ".join(names[:2])
           + (f" and {names[2]}" if len(names) == 3 else f" and {len(names) - 2} more"))
    return f"{who} have your message and have not replied: applying is fine, a second message is not."


def _no_rules(row) -> str:
    """No rule read: every row as the search left it."""
    return ""


_no_rules.note = lambda row, where="": None
_no_rules.standing = lambda row: ""


def left_out(today: dt.date, now: dt.datetime | None = None) -> list[tuple[str, int, dict, str]]:
    """(round, rank, row, why) for every row a search found that the page's Found list leaves
    out by the search's own hard rules (run_round.page_rules), as _jobs reads them: the one
    answer a round takes off the list with (run_round.leave_out)."""
    ctx = Ctx(today, now or dt.datetime.now(dt.timezone.utc))
    _jobs(ctx, {})
    return list(ctx._got.get("jobs_left_out") or [])


# A hard rule's reason as a job's card says it: the rule in the person's words, then why.
# A posting found closed is left out like a rule's cut, its note in plain words.
CLOSED_WHY = "closed: the employer's own board no longer lists it"
_LEFT_WORDS = (("closed: ", "The posting has closed: "),
               ("candidate's bar: ", "It does not clear your employer bar: "),
               ("do not target: ", "No team for you there: "),
               ("place: ", "Not where you can work: "), ("location: ", "Not where you can work: "),
               ("screen: ", "The posting rules you out: "))


def left_words(why: str) -> str:
    """The note on a job the search's own rules left out, in plain words."""
    text = " ".join(str(why or "").split())
    for head, said in _LEFT_WORDS:
        if text.startswith(head):
            text = said + text[len(head):]
            break
    else:
        text = text[:1].upper() + text[1:]
    return "Left out: " + text.rstrip(".")[:240] + "."


def to_look_at(r: dict) -> bool:
    """A job row still to look at: new, scoring 60 or more, not closed; the page's own count
    (jobToLook) is this one, less what was tapped since."""
    return (r.get("status") == "new" and (r.get("score") or 0) >= 60
            and (r.get("apply") or {}).get("status") != "closed")


# What the bar's verdict says, in the person's words (audit 17): its reasons were copied onto
# the card as written for the chat, "tier 2 employer (rogers): major brand, strong pay band",
# with a command in one.
_TIER_WORDS = {"1": "A top employer, with top-of-market pay.",
               "2": "A major brand with a strong pay band.",
               "3": "A solid employer of its size."}


def bar_words(verdict, reason: str) -> str:
    """One plain sentence for a bar verdict and its reason, or "" when it says nothing a
    person can use."""
    why = " ".join(str(reason or "").split())
    if not why:
        return ""
    low = why.lower()
    m = re.match(r"tier (\d) employer \([^)]*\)", low)
    if m:
        return _TIER_WORDS.get(m.group(1), "")
    if low.startswith("public body, but"):
        return "A public body, but even the bottom of its stated pay reaches your target."
    if "reaches the" in low and "target" in low:
        return "Its stated pay reaches your target."
    if low.startswith("frontier ai"):
        return "A frontier AI company."
    if low.startswith("yc or top-tier backed"):
        return "Backed by a top investor."
    if low.startswith("established technology company"):
        return "An established technology company."
    if low.startswith("staffing agency"):
        return "A staffing agency: the employer it hires for is not named."
    if low.startswith("judged"):
        said = why.split(":", 1)[1].strip() if ":" in why else ""
        return f"Your call on this employer: {said.rstrip('.')}." if said else ""
    if "not on your employer lists" in low:
        pay = (" Its stated pay is under your target." if "is under the" in low
               else " It states no pay." if low.startswith("no stated range") else "")
        return "Not on your employer lists yet." + pay
    # Anything else: the reason as said, without a command or a code in it.
    why = re.sub(r"\s*\([^)]*`[^)]*\)", "", re.sub(r"`[^`]*`", "", why)).strip(" ;:,")
    return (why[:1].upper() + why[1:]).rstrip(".") + "." if why else ""


def _filtered(name: str, targets: dict, ctx: Ctx | None = None) -> dict:
    """What the newest search left out, grouped by the person's rule that cut each row, in
    plain words (tools/rules_view.py left_view): its count, the day it last cut, three
    examples, its first rows, a few across the whole of it to check, the pencil's setting.
    The rows the page holds for each rule's search box go to the database as the `filtered`
    list, never all of them: a search left out 13,168 (2026-11-05)."""
    import rules_view
    path = person.state("documents", "rounds", "filtered", f"{name}.json")
    data = _json(path, {})
    found = (data.get("filtered") if isinstance(data, dict) else data) or []
    found = [e for e in found if isinstance(e, dict)]

    def item_of(n: int, e: dict) -> dict:
        fid = f"{name}-f{n}"
        item = {"id": fid, "company": str(e.get("company") or ""),
                "title": str(e.get("title") or ""), "place": str(e.get("location") or ""),
                "url": str(e.get("url") or ""), "reason": str(e.get("reason") or e.get("rule") or ""),
                "rev": rev_of(e.get("url"), e.get("company"), e.get("title"),
                              str(e.get("rule") or e.get("stage") or "other"))}
        targets[fid] = {"kind": "filtered", "round": name, "n": n, "url": item["url"],
                        "company": item["company"], "title": item["title"], "rev": item["rev"]}
        return item

    # A whole rule comes back by its id, as before: filtered~<its kind>.
    got = rules_view.left_view(found, name, rules_view.content_day(rounds_dir(name)), targets,
                               item_of)
    held = got.pop("held")
    if ctx is not None:
        _list(ctx, "filtered", held, sum(len(g["items"]) for g in got["groups"]), 0)
    return got


def seg(text) -> str:
    """An id part as the page makes one (app.js seg): every other character a hyphen."""
    out = re.sub(r"[^A-Za-z0-9_\-.~:@+]", "-", str(text or ""))[:150]
    return "x" if out in ("", ".", "..") else out


# ------------------------------------------------------------------ ready to send


# A PDF's page count, kept by its path, time and size (MAINTAINING.md: a cache is keyed on what
# it reads) in the copy's git folder, never committed: every build counted all of them again,
# 264 PDFs and 3.8 seconds of each page update in a person's copy (the second audit, D8).
PDF_PAGES = "ljs-pdf-pages.json"
_PDF_PAGES: dict = {}


def _pdf_pages_path() -> str:
    try:
        r = subprocess.run(["git", "-C", person.state(), "rev-parse", "--absolute-git-dir"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=10, stdin=subprocess.DEVNULL)
        d = r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        d = ""
    return os.path.join(d, PDF_PAGES) if d else ""


def _pdf_pages() -> dict:
    if "rows" not in _PDF_PAGES:
        path = _pdf_pages_path()
        got = _json(path, {}) if path else {}
        _PDF_PAGES.update(path=path, rows=got if isinstance(got, dict) else {}, dirty=False)
    return _PDF_PAGES


def save_pdf_pages() -> None:
    """Keep the counts this build made, for the next one (in the copy's git folder)."""
    got = _PDF_PAGES
    if not got.get("dirty") or not got.get("path"):
        return
    try:
        tmp = got["path"] + f".{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(got["rows"], fh)
        os.replace(tmp, got["path"])
        got["dirty"] = False
    except OSError:
        pass


def _pages(path: str) -> int | None:
    import pdftext
    try:
        st = os.stat(path)
    except OSError:
        return None
    cache = _pdf_pages()
    key = os.path.abspath(path)
    stamp = [st.st_mtime_ns, st.st_size]
    hit = cache["rows"].get(key)
    if isinstance(hit, list) and len(hit) == 3 and hit[:2] == stamp and isinstance(hit[2], int):
        return hit[2]
    n = pdftext.pages(path)
    if isinstance(n, int):              # never a file no reader here could count
        cache["rows"][key] = stamp + [n]
        cache["dirty"] = True
    return n


ASSETS_FILE = ("documents", "page_assets.json")


def _md5(path: str) -> str:
    import hashlib
    try:
        with open(path, "rb") as fh:
            return hashlib.md5(fh.read()).hexdigest()
    except OSError:
        return ""


def page_assets() -> dict:
    """{repo path: {asset, md5, at}}: the documents put in the page's own file store."""
    got = _json(person.state(*ASSETS_FILE), {})
    return got if isinstance(got, dict) else {}


def asset_for(rel_path: str) -> str | None:
    """The page's asset id for this file, while the file is the one uploaded."""
    rec = page_assets().get(rel_path)
    if not isinstance(rec, dict) or not rec.get("asset"):
        return None
    return rec["asset"] if rec.get("md5") == _md5(person.state(*rel_path.split("/"))) else None


def record_assets(pairs) -> list:
    """Keep (repo path, asset id) for each document uploaded to the page's store."""
    got = page_assets()
    done = []
    for path, aid in pairs:
        rel_path = str(path).replace("\\", "/").lstrip("./")
        full = person.state(*rel_path.split("/"))
        if not os.path.isfile(full):
            raise ValueError(f"there is no file at {rel_path}")
        if not re.match(r"^[0-9a-f]{32}$", str(aid)):
            raise ValueError(f"{aid} is not an asset id (32 hex digits)")
        got[rel_path] = {"asset": str(aid), "md5": _md5(full), "at": stamp(dt.datetime.now(
            dt.timezone.utc))}
        done.append(os.path.basename(rel_path))
    p = person.state(*ASSETS_FILE)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(got, fh, indent=1, sort_keys=True)
        fh.write("\n")
    return done


def files_missing(ctx=None) -> list:
    """Drafted applications whose made PDFs the page's own file store lacks, in tracker order:
    [{id, company, files: [names], paths: [repo paths]}]. A job's own chat cannot upload them
    (Artifact is not among the tools it carries), so its finish queues one `files` item for
    the chat that answers the page with all of these (page_db.queue_files)."""
    import throttle
    if ctx is None:
        today, now = clock(None, None)
        ctx = Ctx(today, now)
    out = []
    for row, rid in zip(ctx.tracker, ctx.tracker_ids):
        if _status(row) not in throttle.UNSENT:
            continue
        names, paths = [], []
        for col in ("cv_file", "cover_letter_file"):
            tex = str(row.get(col) or "").strip()
            if not tex:
                continue
            pdf = os.path.splitext(tex)[0] + ".pdf"
            if os.path.isfile(person.state(*pdf.split("/"))) and not asset_for(pdf):
                names.append(os.path.basename(pdf))
                paths.append(pdf)
        if names:
            out.append({"id": rid, "company": str(row.get("company") or ""), "files": names,
                        "paths": paths})
    # A resume made for a contact with no job named (general_resume.py --for-contact keeps it
    # in their folder, not on the tracker): put in the store as it is made, like an
    # application's, so its Get it downloads at once. Missed here, it was never uploaded, and
    # Get it started a new piece of work to fetch it (the maintainer, 2026-11-10).
    try:
        recs = sorted(glob.glob(person.state("documents", "network", "*", "resume.json")))
    except Exception:  # noqa: BLE001  no copy: nothing made for anyone
        recs = []
    if recs:
        book = {str(c.get("contact_id") or "").strip(): c for c in ctx.contacts}
        noun = _noun()
        for rec in recs:
            cid = os.path.basename(os.path.dirname(rec))
            got = resume_made_for(cid)
            if not got or got.get("asset"):
                continue
            who = first_name((book.get(cid) or {}).get("name")) or "them"
            out.append({"id": RESUME_FOR_PREFIX + cid, "company": "",
                        "what": f"the {noun} for {who}", "files": [got["name"]],
                        "paths": [got["path"]]})
    return out


# The id a contact's own resume goes under in the `files` work that puts it in the page's store.
RESUME_FOR_PREFIX = "resfor-"


def _files(row) -> list:
    import docpaths
    out = []
    for kind, col in (("resume", "cv_file"), ("letter", "cover_letter_file")):
        tex = str(row.get(col) or "").strip()
        if not tex:
            continue
        pdf = os.path.splitext(tex)[0] + ".pdf"
        full = person.state(*pdf.split("/"))
        there = os.path.isfile(full)
        out.append({"kind": kind, "name": os.path.basename(pdf),
                    # Downloaded under the name the person chose in Settings > File names
                    # (the person, the employer, then the document, unless they chose
                    # otherwise), whichever order the kept file was made in
                    # (docpaths.send_name).
                    "send": docpaths.send_name(pdf, row.get("company") or "",
                                               row.get("role") or ""),
                    "asset": asset_for(pdf) if there else None,
                    "path": pdf, "pages": _pages(full) if there else None,
                    "made": there})
    return out


def _outreach(folder: str, names) -> dict | None:
    text = _read(os.path.join(folder, "outreach.md"))
    if not text:
        return None
    parts = re.split(r"^---\s*$", text, flags=re.M)
    note = parts[1].strip() if len(parts) >= 3 else ""
    if not note:
        return None
    to = ("the person who asked for it" if text.startswith("## This goes") else
          "the hiring manager or the recruiter")
    return {"to": to, "text": scrub(note, names) if private_in(note) else note}


def _screening(folder: str) -> list:
    text = _read(os.path.join(folder, "screening_answers.md"))
    out = []
    for m in re.finditer(r"^###\s+(.+?)\s*$\n+\*\*(.+?)\*\*[ \t]*\n?((?:(?!^###|^---).*\n?)*)",
                         text, re.M):
        q = re.sub(r"\s*\*\*\(decide per application\)\*\*", "", m.group(1)).strip()
        a = m.group(2).strip()
        # A gap left for the person ("[check the tracker row]", "[FILL IN]") is theirs to
        # answer, never a Copy button: one tap pasted the brackets into an employer's form
        # (2026-11-03).
        if PLACEHOLDER.search(a):
            out.append({"q": q, "a": "", "fill": True})
            continue
        # Why the answer says what it says, the note the drafting wrote under it, so the
        # person can judge an answer before copying it.
        why = " ".join(re.sub(r"[*_`]", "", m.group(3) or "").split())
        out.append(dict({"q": q, "a": a}, **({"why": why[:300]} if why else {})))
    return out


# A gap a draft leaves for the person to fill: words in square brackets, or a FILL IN / TBC.
PLACEHOLDER = re.compile(r"\[[^\]\n]{2,80}\]|\bFILL\s*IN\b|\bTBC\b|\bTODO\b")


def _checks(files, expect_resume: int, noun: str = "resume") -> dict:
    if not files:
        return {"passed": False, "line": "Not made yet"}
    missing = [{"resume": noun}.get(f["kind"], f["kind"]) for f in files if not f["made"]]
    if missing:
        return {"passed": False, "line": "Not made yet: the " + " and the ".join(missing)}
    said = {"resume": noun, "letter": "letter"}
    wrong = [f for f in files if f["pages"] is not None and f["pages"] != (
        expect_resume if f["kind"] == "resume" else 1)]
    if wrong:
        return {"passed": False, "line": "; ".join(
            f"the {said[f['kind']]} is {f['pages']} pages" for f in wrong)}
    unread = [f["kind"] for f in files if f["pages"] is None]
    if unread:
        return {"passed": True, "line": "Made; page count not read here"}
    # Each document's own words as well as the line, so the page sets the pencil for the resume
    # beside "CV 1 page" and the letter's beside "letter 1 page": two pencils side by side at the
    # end of the line said nothing of which was which (2026-11-05).
    parts = [{"kind": f["kind"], "words": f"{said[f['kind']]} {f['pages']} page{'s' if f['pages'] != 1 else ''}"}
             for f in files]
    # Said only as the documents and their length, each with its pencil: "Made, right length:"
    # on every card read as a message the person had to do something about (the maintainer,
    # 2026-11-05: "why do these all say made right length resume 1 page").
    lead = ""
    return {"passed": True, "line": ", ".join(p["words"] for p in parts), "lead": lead, "parts": parts}


# verify_batch.py's flags, said plainly; anything else is said as "a check failed".
VERIFY_WORDS = {
    "CHRONO": "the jobs are not in date order", "COMPETENCIES": "it has a Core Competencies "
    "section", "DASH": "a long dash is on the page",
    "TEXTLAYER": "an applicant tracking system would misread some characters",
    "TEXTLAYER_LETTER": "the letter has characters a reader would misread",
    "SPACING_RESUME": "words run together in the resume's text",
    "SPACING_LETTER": "words run together in the letter's text",
    "DESIGN_RESUME": "the resume may not read cleanly in an employer's system",
    "DESIGN_LETTER": "the letter may not read cleanly in an employer's system",
    "LAYOUT_RESUME": "its last page is nearly empty, or a heading sits alone at the foot of "
                     "a page",
    "CONTACT": "your contact details are not all in the text",
    "CONTACT_LETTER": "the letter's header is missing your email or phone",
    "SPLIT_LETTER": "a word in the letter reads as two in an employer's system",
    "ROUNDTRIP": "a line of the draft is missing from the PDF's text",
    "NO_PINNED_SKILL": "the skill you always show is missing", "SKILLPARENS":
    "the skills line has brackets", "DUPBULLET": "a bullet is there twice",
    # Said as a person would: "a sentence was changed after the checks read it" asked them
    # to picture the pipeline (2026-11-05).
    "UNAUDITED": "it was changed after it was last checked",
    "CLAIMS": "something on it breaks your own rules or is not in your profile",
    "NUMBERS": "a number on it is not in your profile",
    "LETTERS": "the cover letter breaks one of the letter's rules",
    "VOICE": "the cover letter has wording it must never carry",
}
VERIFY_PASSED = ("one page each", "jobs in date order", "text an applicant tracking system "
                 "reads cleanly", "your contact details in the text", "every line of the "
                 "draft on the page")


def _with_verify(checks: dict, verify: dict | None) -> dict:
    out = dict(checks, verify=verify)
    if verify and not verify["passed"] and checks.get("passed"):
        said = str(verify["items"][0]["said"] or "")
        out.update(passed=False, line=said[:1].upper() + said[1:] + ".")
    return out


def verify_items(folder: str) -> dict | None:
    """What verify_batch.py found on this application's last run (its verify.json), in
    plain words: the checks that passed, or each that did not."""
    got = _json(os.path.join(folder, "verify.json"), None)
    if not isinstance(got, dict):
        return None
    flags = [str(f) for f in got.get("flags") or []]
    bad = []
    for f in flags:
        base = re.sub(r"\(\d+\)$", "", f)
        if base.startswith("RESUME_") and base.endswith("p"):
            bad.append(f"the resume is {base[7:-1] or 'not'} pages")
        elif base.startswith("LETTER_") and base.endswith("p"):
            bad.append(f"the letter is {base[7:-1] or 'not'} pages")
        elif base.startswith("SHARED_PHRASE"):
            bad.append("two bullets share a phrase")
        elif "_LT_" in base:
            bad.append("a job has fewer bullets than its minimum")
        elif "_GT_" in base:
            bad.append("a job has more bullets than your rules allow for this role")
        else:
            bad.append(VERIFY_WORDS.get(base, "a check failed"))
    return {"at": got.get("at"), "passed": not flags,
            "items": [{"ok": True, "said": x} for x in VERIFY_PASSED] if not flags else
            [{"ok": False, "said": x} for x in dict.fromkeys(bad)]}


# What record_drafts.py wrote on the row from the link check staging ran: the employer's own
# listing where it differs from where the posting was found, or that it had closed.
_APPLY_AT = re.compile(r"Apply at (\S+) \(([^)]*)\)\.")
_LINK_CLOSED = re.compile(r"\bLink (closed: .*?checked \d{4}-\d{2}-\d{2} \d{2}:\d{2}(?: UTC)?)")


def _near(folder: str, draft: dict) -> list:
    """The near matches on a draft's posting (fit.near_matches), each with whether the
    person already said yes to the tool asked for, so the page can say "shown as Power BI"
    or offer "I've used Tableau too"."""
    text = _read(os.path.join(folder, "job_posting.md"))
    if not text:
        return []
    try:
        import fit
        import untrusted
        found = fit.near_matches(untrusted.unfence(text))
    except Exception:  # noqa: BLE001
        return []
    yes = {str(x).lower() for x in draft.get("consented_skills") or []}
    return [dict(x, yes=x["asked"].lower() in yes) for x in found]


def _tweaks_done(folder: str, current: str) -> list:
    """The tweaks made to this output, newest first (tools/tweak.py tweaks.json); the newest
    can be taken back while the output is still as it left it."""
    data = _json(os.path.join(folder, "tweaks.json"), {}) or {}
    if not isinstance(data, dict):
        return []
    import tweak
    now = tweak.md5_file(current)
    rows = sorted(((k, v) for k, v in data.items() if isinstance(v, dict)),
                  key=lambda kv: str(kv[1].get("at") or ""), reverse=True)[:5]
    return [{"key": k, "at": v.get("at"), "said": [str(x) for x in v.get("said") or []][:4],
             "undo": i == 0 and v.get("result_md5") == now}
            for i, (k, v) in enumerate(rows)]


def _link_on_row(row: dict, draft: dict) -> dict:
    notes = str(row.get("notes") or "")
    got = {"url": row.get("source") or draft.get("url") or ""}
    m = _APPLY_AT.search(notes)
    if m:
        got.update(apply_url=m.group(1), link_check=m.group(2))
    m = _LINK_CLOSED.search(notes)
    if m:
        got.update(link_check=m.group(1), link_status="closed")
    return got


def _ready(ctx: Ctx, targets: dict) -> list:
    import outreach
    import throttle
    out, folded = [], 0
    expect = int(person.get("documents.resume_pages", 1) or 1)
    noun = str(person.get("documents.noun", "resume"))
    for row, rid in zip(ctx.tracker, ctx.tracker_ids):
        st = _status(row)
        on = throttle.applied_on(row) if st not in throttle.UNSENT else ""
        if st in throttle.UNSENT:
            status = "drafted"
        elif st == "applied" and on and 0 <= (ctx.today - (_date(on) or ctx.today)).days \
                <= RECENT_APPLIED_DAYS:
            status = "applied"
        else:
            if on and (str(row.get("cv_file") or "").strip()
                       or str(row.get("cover_letter_file") or "").strip()):
                folded += 1          # sent, and past its window: under Applications
            continue
        if not (str(row.get("cv_file") or "").strip() or str(row.get("cover_letter_file") or "")):
            continue
        folder = outreach.app_folder(row.get("company"), row.get("role") or "")
        draft = _json(os.path.join(folder, "draft.json"), [])
        draft = draft[0] if isinstance(draft, list) and draft and isinstance(draft[0], dict) \
            else draft if isinstance(draft, dict) else {}
        files = _files(row)
        pay = str(draft.get("salary") or draft.get("pay") or "").strip() or "not stated"
        names = ctx.names
        item = {"id": rid, "slug": os.path.basename(folder) if os.path.isdir(folder) else "",
                "company": row.get("company") or "", "role": row.get("role") or "",
                "pay": pay, "place": str(draft.get("location") or ""),
                "apply": apply_link(_link_on_row(row, draft)),
                "files": [{k: f[k] for k in ("kind", "name", "send", "asset", "path", "pages",
                                             "made")}
                          for f in files],
                "checks": _with_verify(_checks(files, expect, noun), verify_items(folder)),
                "outreach": _outreach(folder, names),
                "screening": _screening(folder), "status": status,
                "applied_on": on or None, "rev": ""}
        item["rev"] = rev_of(rid, row_rev(row), [(f["path"], f["pages"], f["asset"])
                                                 for f in item["files"]],
                             (item["outreach"] or {}).get("text"))
        # A resume made for a contact (stage_picks.py --for-contact): who, by first name only,
        # and whether it goes to them or through a portal naming them.
        fc = str(draft.get("for_contact") or "").strip()
        if fc:
            item["for_contact"] = {"id": fc, "first_name": first_name(draft.get("for_contact_name"))}
            item["route"] = str(draft.get("for_contact_route") or "")
        item["near"] = _near(folder, draft)
        item["tweaks_done"] = _tweaks_done(folder, os.path.join(folder, "draft.json"))
        _card(ctx, targets, item, "for_ready", row, folder)
        item["near_words"] = near_words(item, _noun())
        item["place_short"] = short_place(item.get("place"))
        out.append(item)
        targets[rid] = dict(_row_target(row, rid), rev=item["rev"])
    out.sort(key=lambda i: (i["status"] != "drafted", i["company"].lower(), i["role"].lower()))
    _list(ctx, "ready", [{"id": i["id"], "status": i["status"]} for i in out], len(out), folded,
          doc=False)
    return out


def as_day(value) -> dt.date | None:
    from dates import as_date
    return as_date(value, iso_only=True)


_date = as_day  # the module's own name for it; other modules call as_day


# ------------------------------------------------------------------ messages and people


ROUTE_WHY = {
    "alumni_school": "You studied at the same place",
    "alumni_employer": "You both worked at the same employer",
    "alumni": "You have a past in common",
    "referral": "Someone you know put you in touch",
    "mutual": "You know someone in common",
    "hiring_team": "They are on the hiring team",
    "connection": "You are already connected",
}


def _message_kind(status: str) -> str:
    """What a draft to someone at this status is. A referral already in flight is past its
    ask: a message then is a reply (an update, a thank-you), never the ask again."""
    if status in ("not_contacted", "dropped", ""):
        return "first_note"
    if status in ("awaiting_reply", "connected_no_reply"):
        return "follow_up"
    return "reply"


# The seven kinds of message the person sends by hand (FUNCTIONS_SPEC 1.5), each with the
# composer's own kind its checks run as.
MESSAGE_TYPES = ("first_note", "inmail", "email", "reply", "follow_up", "referral_ask",
                 "thank_you")
COMPOSE_KIND = {"first_note": "connection", "inmail": "inmail", "email": "email",
                "reply": "reply", "follow_up": "nudge", "referral_ask": "referral_ask",
                "thank_you": "reply"}
_THANKS = re.compile(r"\bthank(?:s|\s*-?\s*you)\b", re.I)
_ASKS_REFERRAL = re.compile(r"\b(?:refer(?:ral)?|put (?:my|your) name forward|"
                            r"pass (?:my|it) (?:name|resume|cv) on)\b", re.I)


def message_type(kind: str, channel: str, contact: dict, text: str = "") -> str:
    """first_note, inmail, email, reply, follow_up, referral_ask or thank_you."""
    if kind == "first_note":
        return {"inmail": "inmail", "email": "email"}.get(channel, "first_note")
    if kind == "reply":
        nxt = str(contact.get("next_action") or "")
        if _THANKS.search(nxt) or (text and _THANKS.search(text.split("\n")[0] + " "
                                                            + text[:200])
                                   and str(contact.get("status") or "") == "call_booked"):
            return "thank_you"
        if _ASKS_REFERRAL.search(nxt) and str(contact.get("status") or "") != \
                "referral_in_progress":
            return "referral_ask"
    return kind


# Within this share of the limit a count is "near": an edit could take it over. Said in amber
# only while the person is changing the words (the page's pencil and "I changed it first");
# at rest a count within the limit is the quiet grey, and red only over it. 291 of 300 in amber
# read as a warning about a note that was fine (the maintainer, 2026-11-07).
COUNT_NEAR = 0.05


def count_of(chars: int, limit, mtype: str) -> dict:
    """The character count the page shows: always on a first note, where the limit is that
    type's hard rule, and on the rest only near or over it (LAYOUT_SPEC 4.15). `tone` is its
    colour at rest ("bad" over the limit, else "muted"); `near_at` is the count from which the
    page says it in amber while the words are being changed, by the same rule (COUNT_NEAR)."""
    near_at = math.ceil(limit * (1 - COUNT_NEAR)) if limit else None
    over = bool(limit) and chars > limit
    near = bool(limit) and not over and chars >= near_at
    return {"chars": chars, "limit": limit, "near_at": near_at,
            "show": mtype == "first_note" or near or over, "near": near, "over": over,
            "tone": "bad" if over else "muted",
            "label": f"{chars} of {limit} characters" if limit else f"{chars} characters"}


# advise()'s rules, said the way the person would say them. Any other is said as its fix.
_WARN_WORDS = {
    "ignores_your_last_message": "it was written as if your last message to them never went: follow that one up instead",
    "repeats_your_last_message": "it repeats news your last message already gave them",
    "employer_late": "it names their employer late",
    "buried_employer": "it names their employer late",
    "stacked_hedge": "it hedges twice in one sentence",
    "soft_exit": "it offers them a way out before they have said anything",
    "ai_tell": "a phrase in it can read as written by a machine",
    "three_credentials": "it lists three things where one would land better",
    "repeated_word": "a word comes twice close together",
    "metric_dump": "it piles up numbers",
    "your_rule_outranks": "your own rule says to keep it this way",
}


def plain_warnings(found) -> list[dict]:
    """compose.advise's warnings left standing, each in plain words beside the words it
    is about: shown under the message, never in its place (FUNCTIONS_SPEC 1.5 item 5)."""
    out, seen = [], set()
    for a in found or ():
        rule = str(getattr(a, "rule", "") or "")
        quote = " ".join(str(getattr(a, "text", "") or "").split())[:120]
        fix = " ".join(str(getattr(a, "fix", "") or "").split())
        said = _WARN_WORDS.get(rule) or (fix[:1].lower() + fix[1:] if fix else
                                         "it may read worse than it could")
        line = f"Claude left this as it is: {said}."
        if line in seen:
            continue
        seen.add(line)
        out.append({"rule": rule, "words": quote, "said": line})
    return out[:4]


def message_warnings(text: str, mtype: str, contact: dict) -> list[dict]:
    try:
        import compose
        found = compose.advise(text, COMPOSE_KIND.get(mtype, "reply"),
                               name=str(contact.get("name") or "") or None,
                               title=str(contact.get("title") or ""),
                               their=(str(contact.get("company") or ""),)
                               if contact.get("company") else (),
                               company=str(contact.get("company") or ""))
    except Exception:  # noqa: BLE001  a check that cannot run warns of nothing, never stops
        return []
    # A draft written before the person's latest message, or one that repeats it, says so on
    # the card (compose.thread_findings): a note made before this check is still caught.
    cid = str(contact.get("contact_id") or "").strip()
    if cid:
        try:
            found = list(found or ()) + list(compose.thread_findings(text, cid))
        except Exception:  # noqa: BLE001
            pass
    return plain_warnings(found)


def open_target(contact: dict, channel: str) -> dict | None:
    """Where the message is pasted, as a pointer only: the address itself is in the page's
    owner-only database document reach/<contact> (CONTRACT 1), never in the model."""
    cid = str(contact.get("contact_id") or "").strip()
    if channel == "email" and EMAIL.search(str(contact.get("email") or "")):
        return {"kind": "mailto", "doc": f"reach/{cid}", "label": "Open in email"}
    if LINKEDIN_IN.search(str(contact.get("linkedin_url") or "")):
        return {"kind": "profile", "doc": f"reach/{cid}", "label": "Open their profile"}
    return None


def last_words(ctx, ids) -> dict:
    """{contact id: the last thing they said, in a line} for `ids`, so Today says what a
    reply is to rather than only when it was due (the maintainer, 2026-11-03: "not
    informative at all"). Their own words, so only ever in the owner-only documents with
    their address (`reach`), never in the page's data: nothing about another person reaches
    that but a first name and an employer (the release review)."""
    from network import state as net_state
    out = {}
    for cid in set(ids):
        theirs = [r for r in ctx.by_contact.get(cid) or [] if net_state.said_something(r)]
        if not theirs:
            continue
        # Their own words first: a summary is often one word ("replied").
        words = " ".join(str(theirs[-1].get("full_text") or theirs[-1].get("summary") or "")
                         .split())
        if len(words.split()) >= 3:
            out[cid] = words if len(words) <= 140 else words[:139].rsplit(" ", 1)[0] + "\u2026"
    return out


def reach_docs(contacts, ids) -> dict:
    """{contact id: {linkedin, email}} for the people the page has a message or a row for:
    the owner-only documents `app.py view` writes, read by the page only for its owner."""
    out = {}
    want = set(ids)
    for c in contacts:
        cid = str(c.get("contact_id") or "").strip()
        if cid not in want:
            continue
        li = LINKEDIN_IN.search(str(c.get("linkedin_url") or ""))
        em = EMAIL.search(str(c.get("email") or ""))
        if li or em:
            out[cid] = {"linkedin": li.group(0) if li else None,
                        "email": em.group(0) if em else None}
    return out


def _channel(contact, kind: str) -> str:
    ch = str(contact.get("channel") or "").strip().lower()
    if ch == "inmail":
        return "inmail"
    if ch == "email":
        return "email"
    if kind == "first_note" and ch in ("", "connection", "linkedin"):
        return "linkedin_note"
    return "linkedin_message"


def _limit(channel: str, kind: str):
    from network import schema
    if channel == "linkedin_note":
        return schema.LIMITS.get("connection_note_chars")
    if kind == "follow_up" and channel != "email":
        return schema.LIMITS.get("nudge_chars")
    if channel == "linkedin_message":
        return schema.LIMITS.get("message_chars")
    return None


def turned_down(company) -> bool:
    """Has the person's bar (tools/bar.py) turned this employer down, by a rule, by name, or
    by a judgement on record, so nobody there is chased? The one check, surface.turned_down;
    an employer with no name, or one nobody has judged yet, is never."""
    from network import surface
    return bool(surface.turned_down(company))


# Every reason the composer would refuse a draft (compose.validate), in plain words. A draft
# that breaks one is never offered as ready to send: its card says what is wrong and offers
# to fix it, with no Copy and no "I sent it" (2026-11-03: a first note naming sponsorship and
# a follow-up 7 characters over its limit had Copy and I sent it like any other).
_BLOCK_WORDS = {
    "too_long": "it is longer than this kind of message may be",
    "work_auth_in_first_note": "it brings up your right to work in a first note",
    "casual_work_auth": "it says your right to work in passing",
    "asks_for_the_job": "it asks them for a job",
    "person_dislikes": "it uses words you asked never to use",
    "banned_phrase": "it uses a phrase you asked never to use",
    "unfilled_placeholder": "it still has a gap to fill in",
    "greeting_wrong_name": "it greets them by the wrong name",
    "check_in": "it only checks in, with nothing for them to answer",
    "flattery": "it praises them before you know them",
    "unsupported_claim": "it says something about you that your profile does not hold",
    "example_facts": "it says something about you that is not on record",
    "lowercase_name": "a name in it starts with a small letter",
    "reads_as_generated": "a phrase in it reads as written by a machine",
    "ignores_your_last_message": "it was written as if your last message to them never went",
    "repeats_your_last_message": "it repeats news your last message already gave them",
    "referral_ask_too_soon": "it asks for a referral before they have engaged",
    "manufactured_connection": "it claims a connection you do not have",
    "gatekeeping": "it asks them to pass you to someone else",
}
# Checks shown elsewhere on the card: a first note with nothing read about them has its own
# line and its own button (Paste their profile).
_NOT_BLOCKING = frozenset({"no_reading"})


def message_blocks(text: str, mtype: str, contact: dict, today=None) -> list[dict]:
    """Every reason the composer refuses this draft now, each {"rule", "said"}: what
    `reading.py draft` refuses at saving, read again on the draft as it stands (a rule the
    person recorded since, a message of theirs logged since, a limit for what it now is)."""
    try:
        import compose
        # Their whole name, never the one name a greeting would pick: the check passes a
        # greeting by any name they go by, and "Odile (Lee) Smith" read as "Lee" alone
        # refused "Hi Odile" (a person's copy, 2026-11-11).
        found = compose.validate(text, COMPOSE_KIND.get(mtype, "reply"),
                                 name=str(contact.get("name") or "") or None,
                                 title=str(contact.get("title") or ""),
                                 employers=(str(contact.get("company") or ""),)
                                 if contact.get("company") else (),
                                 contact=str(contact.get("contact_id") or ""), today=today)
    except Exception:  # noqa: BLE001  a check that cannot run blocks nothing
        return []
    out, seen = [], set()
    for v in found or ():
        rule = str(getattr(v, "rule", "") or "")
        if rule in _NOT_BLOCKING:
            continue
        said = _BLOCK_WORDS.get(rule) or ("it breaks a rule: " + short(" ".join(str(
            getattr(v, "text", "") or "").split()), 90))
        if said not in seen:
            seen.add(said)
            out.append({"rule": rule, "said": said})
    return out[:4]


# How many times Claude fixes a draft by itself before the card says it could not: twice for
# a draft that breaks the person's rules (never offered as ready until it passes), once for
# one that only reads better changed (offered as it is after).
FIX_TRIES = {"must": 2, "may": 1}


def message_fix(item: dict) -> dict | None:
    """What Claude fixes in a draft by itself, the moment the check finds it, with no tap (the
    maintainer, 2026-11-04: "if there is clearly a recommended option ... we just do it
    autonomously"): {"work" (the tweak's own id), "reasons", "text" (what to change), "must"
    (it breaks the person's rules, so it is not ready until fixed)}. None when it passes, or
    when it waits for their profile to be read, which no rewrite fixes. `app.py view` queues
    it; a fact only the person knows is asked through the work's one question (`needs`)."""
    if item.get("hold"):
        return None
    must = [b["said"] for b in item.get("blocked") or [] if b.get("said")]
    may = []
    for w in item.get("warnings") or []:
        said = str((w.get("said") or w.get("words") or w.get("text") or "") if isinstance(w, dict) else w)
        # What Claude already judged and kept is never rewritten again.
        if said and not said.lower().startswith("claude left this as it is"):
            may.append(said.rstrip("."))
    reasons = must + [x for x in may if x not in must]
    if not reasons:
        return None
    import page_db
    key = rev_of(reasons, item.get("rev"))[:10]
    return {"work": page_db.safe_id(f"tweak~{item['id']}~fix~{key}"), "reasons": reasons,
            "must": bool(must),
            "text": ("Rewrite it so it keeps my rules: " if must else
                     "Rewrite it so it reads as I would write it: ") + "; ".join(reasons) + "."}


def to_send(messages: list) -> dict:
    """The messages drafted and waiting for the person to send, counted once: one a person
    (each has one draft at a time) and one for each message with nobody on the list (an
    application's follow-up). {"n", "ids"}: Contacts' header ("4 to send") and To do's one
    card ("Messages to send (4)") both draw it, and say the same number (the UX review,
    2026-11-05: Contacts counted every draft, To do the drafted rows and a wave card apart).
    The ids are every message in order, so a page can leave out one sent there before a chat
    has caught up. A note waiting for their profile (`hold`) is not ready to send: it is on
    To do's one reading card (`to_read`), never a row here as well (2026-11-07)."""
    ready = [m for m in messages or [] if not m.get("hold")]
    seen: set = set()
    for m in ready:
        seen.add(str(m.get("contact") or "") or "msg:" + str(m.get("id") or ""))
    return {"n": len(seen), "ids": [str(m.get("id") or "") for m in ready]}


def to_read(messages: list) -> dict:
    """The notes waiting for their profile, one a person: {"n", "ids", "contacts"}. To do says
    them on one card, where and how they are read (the page's readQueueCard), never one card or
    one row each (the maintainer, 2026-11-07)."""
    held = [m for m in messages or [] if m.get("hold")]
    contacts = list(dict.fromkeys(str(m.get("contact") or "") for m in held if m.get("contact")))
    return {"n": len(contacts), "ids": [str(m.get("id") or "") for m in held],
            "contacts": contacts}


def draft_limit(contact: dict, status: str, text: str = "") -> tuple[str, str, int | None]:
    """(what a draft waiting for this contact is, the composer's kind it is checked as, the
    most characters it may run to), read from their status now: the one answer the page
    counts by and `reading.py draft` refuses by. A note to someone already written to is a
    follow-up, held to the nudge's limit below the first note's: a 287-character follow-up
    was saved against a first note's 300 and shown as "287 of 280 characters" (2026-10-26)."""
    kind = _message_kind(status)
    channel = _channel(contact or {}, kind)
    mtype = message_type(kind, channel, contact or {}, text)
    return mtype, COMPOSE_KIND.get(mtype, "reply"), _limit(channel, kind)


# A message whose words send the resume ("resume attached", "here's my resume", "my CV as
# promised"): its card carries the document, ready to attach, so nobody hunts for the file
# (the maintainer, 2026-11-05: "it would be great if the actual document was linked there").
_SENDS_RESUME = re.compile(
    r"\b(?:resume|r[ée]sum[ée]|cv)\b(?:\s+is)?\s+(?:attached|enclosed|as promised)"
    r"|\bhere(?:'|\u2019)?s\s+(?:my|the)\s+(?:resume|r[ée]sum[ée]|cv)\b"
    r"|\b(?:attached|attaching|enclosed)\s+(?:is\s+)?(?:my|the)\s+(?:resume|r[ée]sum[ée]|cv)\b", re.I)


def sends_of(text) -> str | None:
    """"resume" where a message's words send the resume with it, else None."""
    return "resume" if _SENDS_RESUME.search(str(text or "")) else None


def _owed_by_us() -> tuple:
    from network import schema
    return tuple(schema.OWED_BY_US)


def _messages(ctx: Ctx, targets: dict) -> list:
    files = sorted(glob.glob(person.state("documents", "network", "*", "draft.md")))
    ctx._got["message_by_contact"] = {}
    ctx._got["decided_hold"] = {}
    # No draft waiting for anyone still lists an application's follow-up: returning early
    # here left every one out until some person had a draft too (2026-11-04).
    import reading
    from network import surface
    book = {str(c.get("contact_id") or "").strip(): c for c in ctx.contacts}
    out = []
    for f in files:
        cid = os.path.basename(os.path.dirname(f))
        c = book.get(cid)
        if c is None:
            continue
        raw = _read(f)
        text = reading.note_body(raw).strip()
        if not text:
            continue
        live = ctx.live.get(cid) or str(c.get("status") or "")
        kind = _message_kind(live)
        # The person's own surface rules (surface.held): a thread closed or at its limit of
        # unanswered messages, an employer their bar turns down, somewhere outside where
        # they look, a request nobody accepted. A draft to such a person is never offered.
        if surface.held(c, ctx.by_contact.get(cid) or [], live,
                        replying=live == "replied_needs_response",
                        memo=ctx._got.setdefault("held_memo", {})):
            continue
        # A draft written before their newest message answers an older one (times offered
        # that have passed, a request it never saw): never offered, and their message is
        # owed a reply drafted afresh (2026-11-05).
        from network import state as _st
        if _st.draft_predates(cid, ctx.by_contact.get(cid) or []):
            continue
        channel = _channel(c, kind)
        hold, hold_why = None, None
        if kind == "first_note" and raw.startswith(reading.WAITS_ON_A_READ):
            # Why it waits and where the reading happens, in a line: "Written before their
            # profile was read: read it first" on every note drafted in the cloud said neither
            # (2026-11-06).
            hold = read_hold(ctx)
            # Held back on purpose, because people at their employer already wait on a reply
            # (reading.employer_full_line): said as that, never as a read that is coming. A
            # note skipped by the read for that reason said "Claude reads it on your computer
            # by itself" when nothing would (the maintainer, 2026-11-10).
            full = employer_held(ctx, str(c.get("company") or ""), cid)
            if full:
                hold, hold_why = full, "employer_full"
        mid = f"msg-{cid}"
        rev = rev_of(cid, text, kind, channel, live)
        # Held on their record (a next action "Hold ..."), or by Claude's own finish on this
        # very version of the draft: on hold, with why and when, and one way to send it
        # anyway on the page. It was offered as ready under "Finished: held ..." (the
        # maintainer, 2026-11-10). Never over a reply they are owed.
        owed = live in _owed_by_us() and not _st.hold_stands(
            c.get("next_action"), ctx.by_contact.get(cid) or [])
        mine = None if owed else on_hold(ctx, c, ctx.by_contact.get(cid) or [])
        work = (ctx._got.get("held_work") or {}).get(mid)
        if not mine and not owed and work and work.get("rev") == rev:
            said = hold_words(work.get("said"))
            role = _role_words(said)
            mine = {"said": said + (" " + ROLE_HOLD_NOTE if role else ""), "role": role,
                    "until": None, "decided": True}
            ctx._got.setdefault("decided_hold", {})[cid] = mine
        if mine and mine["role"]:
            # A hold that waits for a role carries no draft at all: what was written before
            # the role exists is one template with the name and the employer swapped, and
            # the message is written for that role, and that person, once it is posted (the
            # maintainer, 2026-11-10).
            continue
        hold, hold_why = note_hold(hold, hold_why, mine)
        from network import state as _st
        subject, body = _st.split_subject(text)
        body = body.strip()
        mtype, _ck, limit = draft_limit(c, live, body)
        item = {"id": mid, "contact": cid, "first_name": first_name(c.get("name")),
                "employer": str(c.get("company") or ""), "channel": channel, "kind": kind,
                "type": mtype, "subject": subject or None, "body": body,
                "count": count_of(len(body), limit, mtype),
                "warnings": message_warnings(body, mtype, c),
                "blocked": message_blocks(text, mtype, c, ctx.today),
                # Where they live is not on record, so the person's rule about where people
                # are cannot be checked: said on the card before a new message goes.
                "where_unknown": kind != "reply" and not surface.where_they_live(c),
                "open": open_target(c, channel),
                "application": None,
                "text": text, "chars": len(body), "limit": limit,
                "why": ROUTE_WHY.get(str(c.get("route") or "").strip().lower(),
                                     f"They work at {c.get('company') or 'an employer you want'}"),
                "due": str(c.get("next_action_due") or "") or None, "hold": hold,
                "hold_why": hold_why,
                "rev": rev}
        if mtype == "first_note" and channel == "linkedin_note" and hold is None \
                and not item["blocked"]:
            # First notes waiting to go are one wave: one To do card ("4 first notes ready to
            # send") and one list by employer in Messages. The page had both and the engine
            # never said which notes were a wave, so a networking run's notes reached To do
            # nowhere (2026-11-03).
            year, week, _ = ctx.today.isocalendar()
            item["wave"], item["wave_label"] = f"w{year}-{week:02d}", "First notes to send"
        import parts
        # Code-only tweaks need the parts the note was made from (tools/network/parts.py).
        item["parts"] = parts.load(cid, text) is not None
        item["tweaks_done"] = _tweaks_done(os.path.dirname(f), f)
        item["paste"] = _paste(cid, item["first_name"], raw, ctx._got.get("work_time")) \
            if kind == "first_note" else None
        item["fix"] = message_fix(item)
        item["sends"] = sends_of(body)
        item["inmail"] = _inmail_card(ctx, cid, channel) if kind == "first_note" else None
        _card(ctx, targets, item, "for_message")
        out.append(item)
        targets[mid] = {"kind": "message", "contact": cid, "text": body, "subject": subject,
                        "msg_kind": kind, "type": mtype, "channel": channel, "status": live,
                        "rev": item["rev"]}
    out += _app_followups(ctx, targets)
    # Replies first (someone is waiting on them), then follow-ups, then first notes; within
    # each the longest owed first. Sorted by due date alone, a follow-up a month stale led and
    # the one reply someone was waiting on sat eighteenth of nineteen (2026-11-03).
    rank = {"reply": 0, "thank_you": 0, "referral_ask": 1, "follow_up": 2}
    out.sort(key=lambda m: (m["hold"] is not None, rank.get(m["type"], 3), m["due"] or "9999",
                            m["first_name"].lower()))
    ctx._got["message_by_contact"] = {m["contact"]: m for m in out if m.get("contact")}
    return out


def _inmail_card(ctx: Ctx, cid: str, channel: str) -> dict | None:
    """What a first note's card says of InMail (tools/network/inmail_pick.py): why the run
    chose one ("InMail (suggested): a recruiter at a target employer, and a request would
    wait"), the credit it spends ("uses 1 of your 4 InMails"), and the one switch to the
    other message kept beside it: a connection note instead, or back to the InMail while a
    credit is left."""
    try:
        import inmail_pick
        from network import state as net_state
        b = ctx._once("inmail_budget", lambda: net_state.platform_budget(
            ctx.contacts, ctx.threads, ctx.today, index=ctx.by_contact))
    except Exception:  # noqa: BLE001  no budget to read: the card says nothing of InMail
        return None
    rec = inmail_pick.load(cid)
    left = int(b.get("inmails_left") or 0)
    if channel == "inmail":
        out = {"line": inmail_pick.card_line(rec["why"]) if rec.get("why") else None,
               "credit": inmail_pick.credit_line(left), "switch": None}
        if inmail_pick.can_switch(cid, "inmail") == "connection":
            out["switch"] = {"to": "connection", "label": "Write a connection note instead"}
        return out
    spare = left - int((b.get("queued_unsent") or {}).get("inmail") or 0)
    if inmail_pick.can_switch(cid, "connection") == "inmail" and spare >= 1 \
            and inmail_pick.plan_has_credits():
        return {"line": None, "credit": inmail_pick.credit_line(left),
                "switch": {"to": "inmail", "label": "Send an InMail instead"}}
    return None


def _app_followups(ctx: Ctx, targets: dict) -> list:
    """An application's follow-up, drafted by code (tools/followup_drafts.py, in the newest
    pack), as a message of its own with the application it is about: Copy, then "I sent it"
    logs "followed up <day>" on its row as /outcome does (FUNCTIONS_SPEC 1.2)."""
    try:
        import followup_drafts
        drafts = followup_drafts.earlier_drafts(ctx.today.isoformat())
    except Exception:  # noqa: BLE001
        return []
    if not drafts:
        return []
    ids = {(str(r.get("company") or ""), str(r.get("role") or "role not recorded")): rid
           for r, rid in zip(ctx.tracker, ctx.tracker_ids)}
    out = []
    for i in ctx.due_items:
        if i.get("half") != "application" or i.get("kind") == "interview" or i.get("held"):
            continue
        d = drafts.get(followup_drafts.item_id(i))
        if not d or not str(d.get("text") or "").strip():
            continue
        company, _, role = i["who"].partition(" - ")
        rid = ids.get((company, role)) or ""
        text = str(d["text"]).strip()
        from network import state as _st
        subject, body = _st.split_subject(text)
        body = body.strip()
        channel = "email" if d.get("kind") == "email" or subject else "linkedin_message"
        limit = None if channel == "email" else _limit(channel, "follow_up")
        mid = f"msg-{rid or row_slug(company, role)}"
        who = scrub(i.get("to") or "", ctx.names)
        item = {"id": mid, "contact": "", "first_name": first_name(who) or "the employer",
                "employer": company, "channel": channel, "kind": "follow_up",
                "type": "follow_up", "subject": subject or None, "body": body,
                "count": count_of(len(body), limit, "follow_up"), "warnings": [],
                "open": None, "application": rid or None, "text": text, "chars": len(body),
                "limit": limit, "why": f"Your application for {role} went quiet",
                "due": i.get("due") or None, "hold": None, "parts": False, "tweaks_done": [],
                "alerts": [], "suggest": None, "rev": rev_of(mid, text, i.get("due"))}
        out.append(item)
        targets[mid] = {"kind": "app_message", "half": "application", "company": company,
                        "role": role, "text": body, "subject": subject, "msg_kind": "follow_up",
                        "type": "follow_up", "channel": channel, "rev": item["rev"]}
    return out


# A first note written before their profile was read, said on its card in one line: why it
# waits, and when the reading happens (networking.py PROFILE_READS). The reading is the page's
# own (tools/network/reading.py: never a chat's since 4.3): it runs by itself only while the
# page is open in the Claude app on a computer, in Claude's own browser, signed in to LinkedIn
# there, in the tab the page keeps for it (opened once by Read them, never by itself: 4.13).
# The message's `hold` is the line by the person's setting; the page, which knows where it is
# open, says the line for where reading stands there (linkedin.reading.hold): "When exactly is
# this waiting for Claude thing going to happen?" (the maintainer, 2026-11-07).
READ_HOLD = {
    # The setting's own line, and the page's where it cannot read (a phone, the web).
    "browser": "Waiting for their profile: Claude reads it next time this page is open in the "
               "Claude app on your computer, then rewrites this note",
    "paste": "Waiting for their profile: paste it here and Claude rewrites this note",
    # Their computer is set up and ready (tools/computer.py reads_there): the read is sent
    # there as work by itself (tools/app.py self_fixes), nothing pressed.
    "computer": "Waiting for their profile: Claude reads it on your computer by itself, then "
                "rewrites this note",
    # Open in the Claude app on a computer, where the page reads by itself:
    "tab": "Waiting for their profile: press Read them in To do once, and Claude reads it by "
           "itself from then on",
    "sign_in": "Waiting for their profile: sign in to LinkedIn in Claude's browser and Claude "
               "reads it by itself",
    "paused": "Waiting for their profile: LinkedIn asked Claude to slow down, so it reads it "
              "tomorrow, by itself",
    "next": "Waiting its turn: Claude reads their profile here by itself, then rewrites this note",
    "reading": "Reading their profile…",
    "read": "Profile read: Claude rewrites this note next",
    "again": "Claude could not read their profile just now: it tries again later, by itself",
}


# One plain word for each status, and what the row offers when something is owed by the
# person (FUNCTIONS_SPEC 1.4): a reply owed has its own word and its own button.
STATUS_WORDS = {
    "not_contacted": "Not written to", "awaiting_reply": "Waiting for a reply",
    "connected_no_reply": "Connected", "replied_needs_response": "Replied: your turn",
    "in_conversation": "Talking", "call_booked": "Call booked",
    "referral_in_progress": "Referral", "converted_to_application": "Applied",
    "gone_cold": "Gone quiet", "closed": "Closed", "dropped": "Set aside",
}
# One word for each status, on every card, filter and person page: the page's own map
# (templates/app/app.js PERSON_STATUS) says the same words, which a test holds. A row said
# "Sent" where the person's page said "Waiting for a reply" (2026-11-03).


# A person's conversation on their page: the newest few messages, each cut at a word. The
# sheet's "Your conversation" read `thread` and the engine never wrote it, so every real
# page showed "Last in touch ..." and nothing said, and "Draft a reply" asked for words
# already in the log, which logged them a second time (2026-11-03).
THREAD_KEEP = 4
THREAD_CHARS = 600


def _redact(text: str) -> str:
    """Their words with any contact detail said as what it was, never the detail: the page
    reads an address from the owner-only reach documents (CONTRACT 1)."""
    out = str(text or "")
    if "/" in out:                    # a profile address holds a "/", an email an "@" (scrub)
        out = LINKEDIN_IN.sub("(their profile address)", out)
    if "@" in out:
        out = EMAIL.sub("(an email address)", out)
    for p in sorted(set(_phones(out)), key=len, reverse=True):
        out = out.replace(p, "(a phone number)")
    return out


_LINE_END = re.compile(r"\r\n|\r|\n")
_BLANK_LINES = re.compile(r"\n{3,}")


def thread_of(msgs, names=()) -> tuple[list, int]:
    """(the newest THREAD_KEEP things that happened in a conversation, how many earlier
    ones are not shown): {"from": "you"|"them", "on": day, "text": ...}, with "event": True
    on what was not a message (a request accepted or withdrawn, a call)."""
    from network import state
    out = []
    for m in msgs:
        d = state.direction(m)
        if not d or state.is_auto_reply(m):
            continue
        # Their lines kept, each one's spacing tidied: a file saved on Windows says \r\n.
        lines = _LINE_END.split(str(m.get("full_text") or ""))
        words = _BLANK_LINES.sub("\n\n", "\n".join(" ".join(x.split()) for x in lines)).strip()
        event = None
        if state.is_acceptance(m):
            event = "Accepted your connection request."
        elif state.is_withdrawal(m):
            event = "You withdrew the connection request."
        elif state.is_call(m):
            event = "A call." if state.call_held(m) else "A call that did not happen."
        elif not words:
            event = ("A connection request with no note." if state.is_bare_request(m)
                     else short(str(m.get("summary") or ""), 120) or None)
        if event is None and not words:
            continue
        out.append((d, m, event, words))
    # Only the lines shown are made safe to show: redacting and cutting the names of every
    # message of 716 people took more than a second of each page build (engine audit 24).
    shown = []
    for d, m, event, words in out[-THREAD_KEEP:]:
        item = {"from": "you" if d == "out" else "them", "on": str(m.get("date") or "")[:10]
                or None, "text": event or short(scrub_names(_redact(words), names), THREAD_CHARS)}
        if event:
            item["event"] = True
        shown.append(item)
    return shown, max(len(out) - THREAD_KEEP, 0)


def scrub_names(text: str, names=()) -> str:
    """`text` with each full name in the book cut to its first name (`scrub`'s names)."""
    if hasattr(names, "sub"):
        return names.sub(text)
    return text


def who_they_are(c: dict, status: str) -> str:
    """recruiter, referrer, hiring (an interviewer, a hiring manager or HR) or peer: what the
    Contacts filter sorts people by (the maintainer, 2026-10-28)."""
    from network import compose
    title = str(c.get("title") or "")
    route = str(c.get("route") or "").strip().lower()
    if status == "referral_in_progress" or route == "referral":
        return "referrer"
    if compose.is_recruiter(title):
        return "recruiter"
    if route == "hiring_team" or re.search(r"\b(hiring manager|head of|director|manager|lead|vp|chief|hr|human resources|people partner|talent)\b", title, re.I):
        return "hiring"
    return "peer"


def stopped(next_action) -> bool:
    """Has this thread reached the person's limit of unanswered messages (the app's own
    "No more follow-ups" or "Nudged: nothing more" line on the row)? Then nothing more is
    drafted to them: the row offered "Draft the follow-up" under a line saying to leave it,
    a third message the person's rule forbids (2026-11-03)."""
    return bool(_STOPPED.match(" ".join(str(next_action or "").split())))


def _is_process_stage(ctx: Ctx, c: dict, status: str) -> bool:
    """Is this contact's call an interview stage (FUNCTIONS_SPEC 1.9, as network/prep.py
    says it): a call booked or a referral reaching one, with a recruiter or someone on the
    hiring team, at an employer with no live application or process on record yet. The page
    then offers "Make it an interview" (process.register) in place of a call prep."""
    import throttle
    from company_key import key
    if status not in ("call_booked", "referral_in_progress") and \
            str(c.get("status") or "") not in ("call_booked", "referral_in_progress"):
        return False
    from network import compose
    if not (compose.is_recruiter(c.get("title")) or
            str(c.get("route") or "").strip().lower() == "hiring_team"):
        return False
    k = key(c.get("company"))
    return not any(key(r.get("company")) == k and _status(r) not in throttle.FINAL
                   and _status(r) not in throttle.UNSENT for r in ctx.tracker)


def _paste(cid: str, first: str, raw, work_time: dict | None = None) -> dict | None:
    """"Paste their profile" (profile.pasted, CAPABILITY_MAP G14) on a note that rests on
    nothing read about them: one waiting on a read, or written from their card alone. The
    page offers it under More on a phone or the web, where it cannot read LinkedIn itself."""
    import app_alerts
    import reading
    if raw is None:
        rests = reading.waits_on_read(cid) or reading.card_only_draft(cid)
    else:
        rests = str(raw).startswith(reading.MARKERS)
    return app_alerts.paste_profile(f"msg-{cid}" if raw is not None else cid, first,
                                    work_time) if rests else None


def _call_of(cid: str, status: str, due: str, said: str = "", home: str = "",
             names=(), folders=None) -> dict | None:
    """A networking call booked (on the row: a reply owed since does not unbook it), its
    time in the person's own zone where its next action writes one ("2pm ET": the page said
    "Call Thursday" with no time, 2026-11-02), and its prep (tools/network/prep.py) where it
    is made. `folders` is `_folder_names` of documents/network, read once for a whole book:
    an id of plain letters, digits, "_" and "-" with no folder there has no prep, and its
    prep is not looked for on disk one person at a time."""
    path = person.state("documents", "network", cid, "prep.md")
    have = (folders is None or not _PLAIN_ID.fullmatch(cid) or cid.lower() in folders) \
        and os.path.isfile(path)
    if status != "call_booked" and not have:
        return None
    clock = None
    if status == "call_booked" and due and said:
        import upcoming
        w = upcoming.call_time(said, home or "UTC")
        at = upcoming._moment(str(due)[:10], w["time"], w["zone"]) if w else None
        if at:
            try:
                import zoneinfo
                local = at.astimezone(zoneinfo.ZoneInfo(home or "UTC"))
                clock, due = local.strftime("%H:%M"), local.date().isoformat()
            except Exception:  # noqa: BLE001  no zone data: the time as written
                clock = w["time"]
    import upcoming
    return {"day": (due or None) if status == "call_booked" else None,
            **({"time": clock} if clock else {}),
            # Asked for and not confirmed by them yet, as the call's own line says it.
            **({"tentative": True} if status == "call_booked" and upcoming.call_tentative(said) else {}),
            "prep": {"path": rel(path), "updated": _mtime(path), "text": _prep_text(path, names)}
            if have else None}


CALL_PREP_CHARS = 12000
# A name every file system reads one way, give or take its case.
_PLAIN_ID = re.compile(r"[A-Za-z0-9_-]+")


def _folder_names(path: str) -> set:
    """The names in a folder, in lower case: none where there is no folder."""
    try:
        return {n.lower() for n in os.listdir(path)}
    except OSError:
        return set()


def _prep_text(path: str, names=()) -> str:
    """A call prep as the person reads it on that person's page: plain paragraphs, no
    contact details, cut at a paragraph (never mid-word) with a line saying so. A prep on
    file nobody could open from the person's row was no use before the call (2026-11-03)."""
    import interview_pack
    text = scrub_names(_redact(re.sub(r"<!--.*?-->", "", read_text(path), flags=re.S)), names)
    # A label on a line of its own above the words to say ("SAY.") is never a line of its own
    # here either (2026-11-07): the words under it are.
    text = "\n".join(ln for ln in text.split("\n") if interview_pack.prep.cue(ln) != "say")
    text = re.sub(r"^#+\s*", "", text, flags=re.M)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) <= CALL_PREP_CHARS:
        return text
    cut = text[:CALL_PREP_CHARS].rsplit("\n\n", 1)[0]
    return cut + "\n\nThe rest of this prep is in your files."


def _came_through(value, book: dict) -> str:
    """The first name of whoever the person came through: another contact by id, else the
    name written there."""
    v = str(value or "").strip()
    if not v:
        return ""
    other = book.get(v)
    if isinstance(other, dict) and other.get("first_name"):
        return str(other["first_name"])
    return first_name(v)


_NONE_SAID = re.compile(r"^\s*(?:none|n/?a|nothing|-+|tbc|tbd)\s*\.?\s*$", re.I)
_ANY_URL = re.compile(r"https?://[^\s)\]>,;\"']+", re.I)
# A note to Claude about the person, kept on the row ("waiting for him to send", "HOLD until
# the app's nudge wording is updated", "at his request"): never shown as their next step.
_NOTE_TO_CLAUDE = re.compile(
    r"\b(?:the candidate|claude|hold until|(?:his|her|their) rule|at (?:his|her) request|"
    r"(?:for|on) (?:him|her) to\b|waiting for (?:him|her)\b|batch \d+|draft in notes)", re.I)
# An aside in brackets that only the engine reads: a job or posting number, a batch, a file.
_NOTE_ASIDE = re.compile(r"\s*\((?=[^()]*(?:\d{5,}|\bjob\b|\bbatch\b|\bfile\b|\bnotes?\b|"
                         r"\bid\b|\bchat\b))[^()]*\)", re.I)
# A dated step that is only to wait: nothing to do but see whether it happened.
_WAIT_STEP = re.compile(r"^\s*(?:wait(?:ing)?\b|none owed|nothing owed|no action|no chase|"
                        r"leave it|keep warm|do not (?:chase|nudge|follow up)|let (?:it|them) )",
                        re.I)
# A dated step that is a message to write: its button drafts it.
_MESSAGE_STEP = re.compile(r"\b(?:send|reply|write|message|follow(?:[- ]up)?|nudge|ask|thank|"
                           r"chase|answer|email|introduce|check in)\b", re.I)


_RUN_OF_SPACE = re.compile(r"\s{2,}")
_VIA_LINK = re.compile(r"\s+(?:through|via|at|from)\s+(?:his|her|their|the|this)?\s*"
                       r"(?:referral\s+)?link$", re.I)


def next_words(text, names=()) -> tuple[str, str | None]:
    """(a contact's next step as the person reads it, the first link it names, or None).

    `plain_action`'s words with nothing only the engine reads: no "None", no job or posting
    number, no link (given apart, to open on their page), and nothing written as a note to
    Claude about the person ("Follow-up drafted ... (batch 6), waiting for him to send";
    "HOLD until the app's nudge wording is updated"). Such a line says nothing to them, and
    the row says what its status does instead (2026-11-03)."""
    raw = scrub(text, names)
    m = _ANY_URL.search(raw)
    link = m.group(0).rstrip(".") if m else None
    s = plain_action(_ANY_URL.sub("", raw))
    s = _NOTE_ASIDE.sub("", s)
    s = _SPACE_BEFORE.sub(r"\1", _RUN_OF_SPACE.sub(" ", s)).strip(" ,;:")
    s = _VIA_LINK.sub("", s) if not link else s
    if _NONE_SAID.match(s) or _NOTE_TO_CLAUDE.search(s):
        return "", link
    return s, link


# Where each person stands, decided once here and shown the same way on every screen: the
# page used to work out "needs you", "follow-ups you could send" and who to leave alone
# again from dates of its own, and its counts, buttons and To do disagreed (2026-11-03).
#   now      something to do: a reply owed, a call to prepare for or thank them after, a
#            dated step of the person's own, a reply or thank-you drafted
#   follow   a follow-up To do lists, or one drafted
#   leave    their limit of unanswered messages reached: left alone, never in To do, with
#            Close here and never another message
#   waiting  written to, nothing owed yet
#   new      not written to yet
#   talking  a conversation going, nothing owed now
#   held     the person's own rules stop anything going (surface.held)
#   done     closed, set aside, gone quiet, now an application
GROUPS = ("now", "follow", "leave", "waiting", "new", "talking", "held", "done")
CALL_SOON_DAYS = 7
THANKS_DAYS = 14


def standing(ctx: Ctx, c: dict, cid: str, status: str, msgs: list, due_rows: list,
             message: dict | None, hold: dict | None, call: dict | None,
             on_hold: dict | None = None, role: dict | None = None) -> dict:
    """{"group", "owed" (the one button, or None), "next" (the line under their name), "late"}
    for one person: the engine's one answer, which the page renders and never works out."""
    from network import schema
    import throttle
    out = {"group": "", "owed": None, "next": "", "late": 0}
    late = max([int(d.get("overdue_days") or 0) for d in due_rows] or [0])
    out["late"] = late
    if status in schema.TERMINAL:
        out["group"] = "done"
        return out
    if hold and hold["why"] != "limit":
        out.update(group="held", next=hold["said"])
        return out
    if hold:
        # Their limit of unanswered messages: left alone, never a To do item (_due), with
        # Close here for when the person is done waiting.
        out.update(group="leave", next=hold.get("said") or "", owed={
            "kind": "close", "label": "Close", "due": None, "action": "person.status",
            "value": {"status": "gone_cold", "why": "no reply to your limit of messages"}})
        return out
    if on_hold:
        # On hold (their record's, or Claude's own decision on the draft): nothing is owed,
        # nothing counts as to send or as needing the person, until it lifts.
        out.update(group="held", next=on_hold["said"])
        return out
    if message:
        mt = message.get("type") or message.get("kind")
        word = "See the note" if message.get("kind") == "first_note" else "See the draft"
        out["owed"] = {"kind": "draft", "label": word, "message": message["id"],
                       # A reply drafted is still a reply owed until it goes: counted as one.
                       "reply": mt in ("reply", "thank_you", "referral_ask")}
        out["group"] = ("new" if message.get("kind") == "first_note" else
                        "follow" if mt == "follow_up" else "now")
        out["next"] = {"first_note": "Your note to them is written: send it",
                       "follow_up": "Your follow-up is written: send it"}.get(
            mt, "Your reply is written: send it")
        return out
    reply = next((d for d in due_rows if d.get("kind") == "reply"), None)
    if reply:
        theirs = [m for m in msgs if _said(m)]
        logged = bool(theirs) and bool(" ".join(str(theirs[-1].get("full_text") or "").split()))
        out["group"] = "now"
        out["owed"] = {"label": "Draft a reply", "kind": "reply", "id": f"reply~{cid}",
                       "args": {"contact": cid}, "logged": logged, "due": reply["id"],
                       "reply": True}
        if reply.get("sub") == "resume":
            out["owed"]["resume"] = True
        out["next"] = reply.get("step") or "Reply"
        return out
    if role:
        # The role their hold waited for is posted: back on the list by themselves, with the
        # referral ask for that one role as the step, written then from what they offered.
        import followup_drafts
        title = " ".join(str(role.get("title") or "a role").split())
        company = str(c.get("company") or role.get("company") or "Their employer").strip()
        said = followup_drafts.role_said(role, company)
        ask = "ask them to refer you" if said.endswith(f"has posted {title}") \
            else "ask them to put in a word"
        out.update(group="now", next=f"{said}: {ask}",
                   owed={"kind": "referral", "label": "Draft the referral ask",
                         "id": f"reply~{cid}~ref",
                         "args": {"contact": cid, "kind": "referral_ask", "role": title,
                                  "url": str(role.get("url") or role.get("link") or "") or None}})
        return out
    day = _date((call or {}).get("day"))
    # A call that has happened (state.move_past_calls moved the row on, keeping its day in
    # the next action): the thank-you is owed for THANKS_DAYS, until a message of ours went.
    from network import state as _state
    over = _state.call_over_day(c) if status == "in_conversation" else None
    if over and 0 < (ctx.today - over).days <= THANKS_DAYS and \
            not any(str(m.get("date") or "")[:10] > over.isoformat()
                    and _state._direction(m) == "out" for m in msgs):
        out.update(group="now", next="How did it go? Thank them while it is fresh", owed={
            "kind": "thanks", "label": "Draft the thank-you", "id": f"reply~{cid}~thanks",
            "args": {"contact": cid, "kind": "thank_you"}})
        return out
    if status == "call_booked" and day:
        diff = (day - ctx.today).days
        if diff < 0 and -diff <= THANKS_DAYS:
            out.update(group="now", next="How did it go? Thank them while it is fresh", owed={
                "kind": "thanks", "label": "Draft the thank-you", "id": f"reply~{cid}~thanks",
                "args": {"contact": cid, "kind": "thank_you"}})
            return out
        if 0 <= diff <= CALL_SOON_DAYS:
            out.update(group="now", owed={"label": "Prepare for the call", "kind": "prep",
                                          "id": f"prep~call~{cid}",
                                          "args": {"contact": cid, "call": True}})
            return out
    follow = next((d for d in due_rows if d.get("kind") == "nudge"
                   or (d.get("step") or "").lower().startswith("follow up")), None)
    if follow:
        out.update(group="follow", next=follow.get("step") or "Follow up", owed={
            "label": "Draft the follow-up", "kind": "follow_up",
            "id": (follow.get("work") or {}).get("id") or f"follow_up~{cid}",
            "args": dict((follow.get("work") or {}).get("args") or {"contact": cid}),
            "due": follow["id"]})
        return out
    own = next((d for d in due_rows if d.get("kind") == "follow_up"), None)
    if own:
        step = own.get("step") or ""
        out["next"] = step
        if _WAIT_STEP.match(step):
            out["group"] = "waiting"
            return out
        out["group"] = "now"
        if _MESSAGE_STEP.search(step):
            out["owed"] = {"label": "Draft it", "kind": "follow_up",
                           "id": (own.get("work") or {}).get("id") or f"follow_up~{cid}",
                           "args": dict((own.get("work") or {}).get("args") or {"contact": cid},
                                        step=step), "due": own["id"]}
        elif (own.get("done") or {}).get("action"):
            out["owed"] = {"label": "Done", "kind": "done", "due": own["id"],
                           "action": own["done"]["action"]}
        return out
    if status in throttle.SENT_NO_REPLY:
        out["group"] = "waiting"
    elif status in ("not_contacted", ""):
        out["group"] = "new"
    elif status == "call_booked" and not day:
        out.update(group="now", owed={"label": "Prepare for the call", "kind": "prep",
                                      "id": f"prep~call~{cid}",
                                      "args": {"contact": cid, "call": True}})
    else:
        out["group"] = "talking"
    return out


def _said(m) -> bool:
    from network import state
    return state.said_something(m)


def exchange_of(msgs: list) -> dict | None:
    """The latest exchange with someone and how it began, for their card (the latest only)
    and its More (when you first wrote, how many each way): worked out once here, never on the
    page. A message of ours (never a request taken back) and a message of theirs with words
    (never an acceptance, a call or an auto-reply) count; nothing else does. None with neither."""
    from network import state
    said = []
    for m in msgs:
        day = str(m.get("date") or "")[:10]
        if not _date(day):
            continue
        if state.direction(m) == "out" and not state.is_withdrawal(m) and not state.is_call(m):
            said.append((day, "you"))
        elif state.said_something(m):
            said.append((day, "them"))
    if not said:
        return None
    said.sort(key=lambda x: x[0])
    last_day, last_who = said[-1]
    first_day, first_who = said[0]
    return {"last": last_who, "last_on": last_day,
            # Their message after one of ours is a reply; one with nothing of ours before it
            # is them writing first.
            "replied": last_who == "them" and any(w == "you" for _d, w in said[:-1]),
            "first": first_who, "first_on": first_day,
            "out": sum(1 for _d, w in said if w == "you"),
            "in": sum(1 for _d, w in said if w == "them")}


def _people(ctx: Ctx, targets: dict) -> list:
    """Every live contact (a conversation going, a reply or anything else owed, a note
    waiting to go, a message out in the last 60 days), then the rest by recency until the
    list reaches its size budget; the whole book, cut down, goes to the page's database.
    Each carries where it stands (`standing`), worked out once here with the person's own
    surface rules (surface.held), so no screen shows anyone those rules stop."""
    import app_lists
    import open_actions
    from network import schema, state, surface
    from what_works import route_group
    drafts = {os.path.basename(os.path.dirname(f)) for f in
              glob.glob(person.state("documents", "network", "*", "draft.md"))}
    folders = _folder_names(person.state("documents", "network"))     # for _call_of
    # What a person's standing reads, made here when this build did not make it first (a
    # build of some sections only, as `app.py apply` makes to check a tap): the same answer
    # either way, so a tap is never refused as stale for a section not built.
    if "message_by_contact" not in ctx._got:
        _messages(ctx, {})
    if "due_by_contact" not in ctx._got:
        _due(ctx, {})
    if "sent_questions" not in ctx._got:
        ctx._got["sent_questions"] = _sent_questions(ctx, {})
    shown = ctx._got.get("message_by_contact") or {}
    due_by = ctx._got.get("due_by_contact") or {}
    asked = {str((n.get("about") or {}).get("contact") or ""): n["id"]
             for n in ctx._got.get("sent_questions") or ()}
    decided = ctx._got.get("decided_hold") or {}
    holds: dict = {}
    fold = app_lists.FOLD_DAYS["people"]
    # The same first name at the same employer (or with none) more than once: each is told
    # apart by their surname's first letter, never more of it.
    seen_as: dict = {}
    for c in ctx.contacts:
        k = (first_name(c.get("name")).lower(), str(c.get("company") or "").strip().lower())
        seen_as[k] = seen_as.get(k, 0) + 1
    rows, full = [], {}
    counts = dict.fromkeys(GROUPS, 0)
    # A row closed as the same person as another is never listed beside it: its messages are
    # shown on the row kept (2026-11-05: one recruiter was two cards, one with no employer).
    closed_as = state.duplicate_of(ctx.contacts)
    theirs: dict = {}
    for gone, kept in closed_as.items():
        theirs.setdefault(kept, []).extend(ctx.by_contact.get(gone) or [])
    for c in ctx.contacts:
        cid = str(c.get("contact_id") or "").strip()
        if not cid or cid in full or cid in closed_as:
            continue
        status = ctx.live.get(cid) or str(c.get("status") or "")
        due = str(c.get("next_action_due") or "").strip()
        msgs = ctx.by_contact.get(cid) or []
        if theirs.get(cid):
            # The message both rows logged, which is how the two were found to be one
            # person, is shown once.
            def said(m):
                return (str(m.get("date") or "")[:10], state.direction(m),
                        " ".join(str(m.get("full_text") or "").split()).lower())
            have = {said(m) for m in msgs if str(m.get("full_text") or "").strip()}
            more = [m for m in theirs[cid] if not str(m.get("full_text") or "").strip()
                    or said(m) not in have]
            msgs = sorted(list(msgs) + more, key=lambda m: str(m.get("date") or ""))
        last = max((str(m.get("date") or "")[:10] for m in msgs), default="") or None
        days = app_lists.ago(last, ctx.today)
        hold = surface.held(c, msgs, status, replying=status in schema.OWED_BY_US,
                            memo=ctx._got.setdefault("held_memo", {}))
        call = _call_of(cid, "call_booked" if str(c.get("status") or "") == "call_booked"
                        else status, due, c.get("next_action"), ctx.zone, ctx.names, folders)
        # On hold: their record's (on_hold), or Claude's own decision on the draft to them
        # (_messages). Never over a reply they are owed. A hold that waited for a role and
        # found one posted is lifted, and the referral ask for it is their step.
        waits, posted = None, {}
        if status not in schema.TERMINAL and (status not in schema.OWED_BY_US or
                                               state.hold_stands(c.get("next_action"), msgs)):
            waits = on_hold(ctx, c, msgs) or decided.get(cid)
            text = str(c.get("next_action") or "")
            if waits is None and state.role_hold(text) and state.action_hold(
                    text, ctx.today, c.get("next_action_due")):
                posted = role_posted(ctx, c, msgs)
        where = standing(ctx, c, cid, status, msgs, due_by.get(cid) or [], shown.get(cid),
                         hold, call, on_hold=waits, role=posted)
        group = where["group"]
        counts[group] += 1
        waiting_on = bool(waits) and group == "held"
        if waiting_on:
            holds[cid] = waits
        finished = group in ("done", "held")
        live = group in ("now", "follow", "leave") or cid in shown or waiting_on or (
            not finished and (bool(due) or status in throttle_responded()
                              or (status in schema.NEVER_SENT and cid in drafts)
                              or (status in throttle_sent() and days is not None
                                  and days <= fold)))
        first = first_name(c.get("name"))
        light = {"id": cid, "first_name": first, "employer": str(c.get("company") or ""),
                 "status": status, "status_word": STATUS_WORDS.get(status, status.replace("_", " ")),
                 "group": group, "route": route_group(c.get("route")), "last": last,
                 "contacted": app_lists.bucket(days), "due": due or None,
                 "replied": any(state.said_something(t) for t in msgs), "live": live}
        if seen_as.get((first.lower(), light["employer"].strip().lower()), 0) > 1:
            parts = str(c.get("name") or "").split()
            if len(parts) > 1 and parts[-1][:1].isalpha():
                light["initial"] = parts[-1][:1].upper()
        title = short(scrub(c.get("title"), ctx.names), 60)
        if title and not light["employer"]:
            light["title"] = title
        full[cid] = light
        rows.append((c, cid, status, due, last, msgs, hold, call, where, title))
    live_rows = [r for r in rows if full[r[1]]["live"]]
    rest = [r for r in rows if not full[r[1]]["live"] and (
        (app_lists.ago(r[4], ctx.today) is not None and app_lists.ago(r[4], ctx.today) <= fold)
        or (not r[5] and r[2] in schema.NEVER_SENT and r[8]["group"] == "new"))]
    order = {g: n for n, g in enumerate(GROUPS)}
    # Someone with a message already drafted first, then who needs you: Contacts is one page,
    # each person with what to send them, and what is written is the quickest thing to finish
    # (the maintainer, 2026-11-04).
    # Anyone on hold last: nothing is owed to them until it lifts.
    live_rows.sort(key=lambda x: (x[1] in holds, x[1] not in shown, order[x[8]["group"]],
                                  -x[8]["late"],
                                  -open_actions.HEAT.get(x[2], 0), x[3] or "9999", x[1]))
    rest.sort(key=lambda x: (x[4] or "", x[1]), reverse=True)
    out, used = [], 2
    for n, (c, cid, status, due, last, msgs, hold, call, where, title) in enumerate(live_rows + rest):
        action, link = next_words(c.get("next_action"), ctx.names)
        thread, earlier = thread_of(msgs, ctx.names)
        item = {"id": cid, "first_name": full[cid]["first_name"],
                "employer": full[cid]["employer"], "status": status,
                "status_word": full[cid]["status_word"], "group": where["group"],
                "owed": where["owed"], "next": where["next"], "late": where["late"],
                # Why nothing is offered, in their words, where their rules stop it.
                "hold": hold["said"] if hold and hold.get("said") else None,
                # On hold until something happens (a role posted, a day): why and until
                # when, for their card in the page's own On hold group, with no draft where
                # it waits for a role. Gone by itself once the hold lifts.
                "on_hold": ({"said": holds[cid]["said"], "role": bool(holds[cid].get("role")),
                             "until": holds[cid].get("until")} if cid in holds else None),
                "stopped": where["group"] == "leave",
                # Whether the person has written to them: someone who wrote first has not
                # been "written to" until a message of theirs went back.
                "wrote": any(state.direction(t) == "out" and not state.is_withdrawal(t)
                             for t in msgs),
                "last": last, "title": title or None,
                # The latest exchange, for the card's line; how it began, for its More.
                "exchange": exchange_of(msgs),
                "next_action": action, "link": link, "due": due or None,
                "route": full[cid]["route"],
                # Who they came through (the book's referred_by: a contact id or a name), so the
                # page says "Came through Alex" on someone Alex passed them to (2026-10-30).
                "came_through": _came_through(c.get("referred_by"), full) or None,
                # A resume made for them when they asked for one: on their card, to get, and
                # found by their name; never in place of the person's own (2026-11-05).
                "resume_for_them": resume_made_for(cid),
                "who": who_they_are(c, status),
                "replied": full[cid]["replied"], "live": full[cid]["live"], "call": call,
                "paste": _paste(cid, full[cid]["first_name"], None, ctx._got.get("work_time"))
                if (shown.get(cid) or {}).get("kind") == "first_note" else None,
                # Where they live is not on record: the person's rule about where people are
                # cannot be checked, which the page says before anything goes to them.
                "where_unknown": not surface.where_they_live(c),
                "asked_sent": asked.get(cid),
                "is_process_stage": _is_process_stage(ctx, c, status),
                # Their conversation, newest last, so their page shows what was said and a
                # reply is drafted from words already kept (thread_of).
                "thread": thread, "thread_more": earlier,
                "related": {},        # filled by app_lists.link; counted in the budget
                # What an action on them acts on: their record and their messages, never the
                # group the day puts them in, which moves with the clock while nothing about
                # them changed: a Stop made the day before was refused (2026-11-04).
                "rev": rev_of(cid, status, str(c.get("next_action") or ""), due, last)}
        if full[cid].get("initial"):
            item["initial"] = full[cid]["initial"]
        _card(ctx, targets, item, "for_person")
        used += app_lists.size(item) + 1
        if n >= len(live_rows) and used > app_lists.PEOPLE_BYTES:
            break
        out.append(item)
        targets[cid] = {"kind": "person", "contact": cid, "status": status, "rev": item["rev"]}
    first = [full[r[1]] for r in live_rows + rest]
    seen = {x["id"] for x in first}
    whole = first + sorted((x for x in full.values() if x["id"] not in seen),
                           key=lambda x: (x["last"] or "", x["id"]), reverse=True)
    replies = sum(1 for r in rows if r[8]["group"] == "now" and (r[8]["owed"] or {}).get("reply"))
    need = {r[1] for r in rows if r[8]["group"] in NEEDS_YOU}
    could = {r[1] for r in rows if r[8]["group"] == "follow"}
    # To do's row for who needs the person and is not on its list (neither a row of its own nor
    # a message on its "Messages to send" card), and the follow-ups it left off, said apart.
    dh = ctx._got.get("due_hidden")
    if dh is not None:
        kept = [d for d in dh["rows"] if d.get("kind") != "hidden"]
        off = dh["listed"] | set(shown)
        row = _hidden_row(dh["ruled"], len(need - off), len(could - off))
        dh["rows"][:] = kept + ([row] if row else [])
    ctx._got["people_count"] = {"shown": len(out), "all": len(full), "live": len(live_rows),
                                "rest": len(full) - len(out), "need": len(need),
                                "replies": replies, "follow": counts["follow"],
                                "leave": counts["leave"], "waiting": counts["waiting"],
                                "held": counts["held"],
                                # People with a message drafted to them, on the list's top.
                                "drafted": sum(1 for r in live_rows
                                               if r[1] in shown and r[1] not in holds),
                                # Who is on hold, and the one reason where they share it.
                                "on_hold": {"n": len(holds), "why": ROLE_WAIT if holds and all(
                                    h.get("role") for h in holds.values()) else None}}
    _list(ctx, "people", whole, len(out))
    return out


def throttle_responded() -> set:
    import throttle
    return throttle.RESPONDED


def throttle_sent() -> set:
    import throttle
    return throttle.SENT_NO_REPLY


# ------------------------------------------------------------------ due


_DUE_KIND = {"reply": "reply", "resume": "reply", "nudge": "nudge", "action_due": "follow_up",
             "first_message": "follow_up", "request_pending": "nudge", "interview": "interview"}
_DUE_WORK = {"reply": "work:reply", "nudge": "work:follow_up", "follow_up": "work:follow_up",
             "interview": "work:prep"}


def _own_step(c: dict, today: dt.date) -> bool:
    """Does the row carry a dated next step of the person's own (not the app's follow-up
    wording, state._APP_ACTION), due by now?"""
    from network import state
    action = " ".join(str(c.get("next_action") or "").split())
    due = _date(c.get("next_action_due"))
    # A step that is only to wait ("Wait for them to book a call") stays a follow-up once its
    # day has gone: the wait is over, and following up is what is due.
    return bool(action) and due is not None and due <= today and \
        not state._APP_ACTION.fullmatch(action) and not stopped(action) and \
        not _WAIT_STEP.match(action)


# The kinds of row owed to a contact that _due says in its own words, never the person's step.
_DUE_SAID = frozenset({"reply", "resume", "nudge", "request_pending", "first_message"})


def _left_alone(i: dict, book: dict) -> bool:
    """A contact's dated row that says only to leave them: the app's own line at their limit
    of unanswered messages ("Nudged: nothing more unless they reply"), dated before such a
    line was never dated, or dated since by hand. Nothing to do, so never a To do item."""
    return i.get("half") == "contact" and i.get("kind") == "action_due" and stopped(
        (book.get(i.get("contact_id") or "") or {}).get("next_action"))


def _due(ctx: Ctx, targets: dict) -> list:
    import open_actions
    items = [i for i in ctx.due_items if not i.get("quiet") and not i.get("old")
             and not str(i.get("what") or "").startswith(UNCONFIRMED)]
    book = {str(c.get("contact_id") or "").strip(): c for c in ctx.contacts}
    # The person's own surface rules (open_actions._hold_by_rule, surface.held): anyone they
    # stop is not shown, counted by why in one quiet line. A thread at its limit of
    # unanswered messages is neither shown nor counted: there is nothing to do but leave it,
    # and nothing to do is not a To do (the maintainer, 2026-11-04: six "leave it" cards,
    # closed that morning, came back once an update dated every contact). Their row in
    # Contacts says so and keeps Close (standing, group "leave").
    ruled = {}
    for i in items:
        rule = i.get("rule") or {}
        if rule and rule.get("why") != "limit" and len(i.get("held") or []) == 1:
            ruled[rule["why"]] = ruled.get(rule["why"], 0) + 1
    items = [i for i in items if not i.get("held") and not _left_alone(i, book)]
    # A draft Claude decided to hold (not yet on their record) owes nothing either: its
    # person is on hold in Contacts, never a To do row, nor in the Brief's lists.
    if "decided_hold" not in ctx._got:
        _messages(ctx, {})
    waits = ctx._got.get("decided_hold") or {}
    items = [i for i in items if not (i.get("half") == "contact" and i.get("contact_id") in waits
                                      and i.get("kind") != "reply")]
    # Requests nobody accepted are never nudged: nothing can be sent to them. They are one
    # row, withdraw them on LinkedIn, then tick (FUNCTIONS_SPEC G8; state.py withdraw).
    pending = [i for i in items if i.get("half") == "contact" and i.get("kind") == "request_pending"]
    items = [i for i in items if i not in pending]
    items.sort(key=open_actions.urgency)
    app_ids = {(str(r.get("company") or ""), str(r.get("role") or "role not recorded")): rid
               for r, rid in zip(ctx.tracker, ctx.tracker_ids)}
    noun = str(person.get("documents.noun", "resume"))
    out, seen, halves = [], set(), {}
    for i in items:
        raw = i.get("kind") or ("follow_up" if i["half"] == "application" else "follow_up")
        if raw == "nudge" and i["half"] == "contact" and _own_step(
                book.get(i.get("contact_id") or "", {}), ctx.today):
            # A step the person dated on the row ("Send the referral ask for ...") rides on the
            # nudge: it is that step that is due, never a generic follow-up (2026-11-03: the
            # row said one thing and its button drafted another).
            raw = "action_due"
        kind = _DUE_KIND.get(raw, "follow_up")
        if i["half"] == "contact":
            c = book.get(i.get("contact_id") or "", {})
            who = first_name(c.get("name")) or "someone"
            where = f" at {c.get('company')}" if c.get("company") else ""
            # Their own step, read only where it is the one said: worked out for every row
            # owed, as a default argument it scrubbed every contact's step twice (2026-11-03).
            own_step = (short(plain_action(scrub(c.get("next_action"), ctx.names)))
                        if raw not in _DUE_SAID else "")
            title = {"reply": f"Reply to {who}{where}",
                     "resume": f"Send your {noun} to {who}{where}",
                     "nudge": f"Follow up with {who}{where}",
                     "request_pending": f"Your request to {who}{where} was not accepted",
                     "first_message": f"Write to {who}{where}: they accepted"}.get(
                raw, f"{who}{where}: " + own_step)
            # What is due, said without who: their own row in Contacts names them already
            # ("Next: reply to Juno at Larkspur Retail" sat under "Juno at Larkspur Retail").
            step = {"reply": "Reply", "resume": f"Send your {noun}", "nudge": "Follow up",
                    "request_pending": "Your request has not been accepted yet",
                    "first_message": "Write to them: they accepted"}.get(raw, own_step)
            key = i.get("contact_id") or ""
            action = "work:resume_for_contact" if raw == "resume" else _DUE_WORK[kind]
            about = key
            wkind = action.split(":", 1)[1]
            work = {"kind": wkind, "id": f"{wkind}~{key}", "args": {"contact": key}}
            # Named after the person, never after their step: a step written as a note named
            # the work "<who> at <where>: One follow-up sent 2026-10-21. No more after this" in
            # Claude's work (the maintainer, 2026-11-04).
            if wkind == "follow_up":
                work["title"] = f"Follow up with {who}{where}"
            if raw == "resume":
                work["ask"] = "role"       # which role: asked on the page at tap time
            sub = raw
        else:
            company, _, role = i["who"].partition(" - ")
            rid = app_ids.get((company, role)) or ""
            about = rid
            if raw == "interview":
                w = i.get("what") or ""
                iid = "int-" + rid[4:] if rid else ""
                sub = i.get("sub") or ("prep" if "no pack" in w else "thank_you"
                                       if "thank-you" in w else "status_note")
                # Quiet since a round that was held, or since the last word with none held yet
                # (a round named and never given a day): "since your interview" was said of a
                # panel interview that had not happened (2026-11-03).
                held = sub != "status_note" or _round_held(ctx, company, role)
                title = {"prep": f"Prepare for your {company} interview",
                         "thank_you": f"Thank-you note after your {company} interview",
                         # The invitation's choice and a test due, each said as what it is
                         # (the audit, 2026-11-03).
                         "choose": f"{company}: choose your interview day and tell them",
                         "test": f"{company}: " + short(w[:1].upper() + w[1:].split(" (")[0]),
                         "status_note": f"No word from {company} since your interview" if held
                         else f"No word from {company} since your last update"}[sub]
                # One work id per prep: the interview card's own (prep~<interview>), so a
                # tap here and a tap there are one piece of work. A thank-you and a status
                # note are follow-ups, never a prep (FUNCTIONS_SPEC 1.8).
                if sub == "prep":
                    action = "work:prep"
                    work = {"kind": "prep", "id": f"prep~{iid}", "args": {"interview": iid}}
                elif sub in ("choose", "test"):
                    # The person's to do: a day to choose on the interview's own card, a test
                    # to sit. Nothing for Claude to draft.
                    action = "go:interviews"
                    work = None
                else:
                    action = "work:follow_up"
                    work = {"kind": "follow_up", "id": f"follow_up~{iid}~{sub}",
                            "args": {"interview": iid, "kind": sub, "company": company,
                                     "role": role}}
                about = iid or rid
            else:
                title = f"Follow up on {role or 'your application'} at {company}"
                action = _DUE_WORK[kind]
                sub = "follow_up"
                work = {"kind": "follow_up", "id": f"follow_up~{rid or row_slug(company, role)}",
                        "args": {"application": rid, "company": company, "role": role}}
            key = row_slug(company, role) or company
        did = f"due-{kind}-{key}"
        n = 2
        while did in seen:
            did, n = f"due-{kind}-{key}-{n}", n + 1
        seen.add(did)
        halves[did] = i["half"]
        # "Done" only where a writer takes it (app_actions.py due.done): a dated next action
        # the person set on a contact, or an application's follow-up, which is logged the
        # way /outcome logs it. A reply, a nudge or a resume owed is done when it is logged
        # with its words, and an interview by /outcome: those rows offer their work instead.
        # A thank-you and a status note sent some other way are Done here too: a thank-you
        # row had no Done, and sorted to the bottom (the audit, 2026-11-03).
        doable = (i["half"] == "contact" and raw == "action_due") or (
            i["half"] == "application" and (raw != "interview" or sub in (
                "thank_you", "status_note", "test")))
        context = ""
        if i["half"] == "contact":
            # One line on who they are, so a follow-up says which person it is (the maintainer,
            # 2026-10-26): their role, how they were found, when you first wrote.
            c = book.get(i.get("contact_id") or "", {})
            co, role = str(c.get("company") or "").strip(), str(c.get("title") or "").strip()
            bits = [role + (f" at {co}" if co and co not in title else "")] if role else (
                [co] if co and co not in title else [])
            how = str(c.get("route_detail") or "").strip() or _ROUTE_WORDS.get(
                str(c.get("route") or "").strip().lower(), "")
            # "Recruiter · recruiter": their route said again after a title that already says it.
            if how and how.lower() not in role.lower():
                bits.append(how)
            import dates
            first = dates.as_date(c.get("first_contacted"), iso_only=True)
            if first:
                bits.append("first wrote " + first.strftime("%-d %b") if os.name != "nt"
                            else "first wrote " + first.strftime("%d %b").lstrip("0"))
            context = scrub(" \u00b7 ".join(b for b in bits if b), ctx.names)
        # A contact's: what is due said without who.
        own = {"step": step} if i["half"] == "contact" else {}
        item = {"id": did, "kind": kind, "title": title, "context": context, "due": i["due"],
                **own,
                "company": (str(book.get(i.get("contact_id") or "", {}).get("company") or "")
                            if i["half"] == "contact" else i["who"].partition(" - ")[0]),
                "overdue_days": max(int(i.get("late") or 0), 0), "action": action,
                "sub": sub, "item": about or None, "work": work,
                "done": {"action": "due.done", "label": "Done"} if doable else None,
                "snooze": {"action": "due.snooze", "label": "Not today"} if doable or
                i["half"] == "contact" else None,
                "rev": rev_of(did, i["due"], title)}
        out.append(item)
        if doable or i["half"] == "contact":
            t = {"kind": "due", "half": i["half"], "due": i["due"], "rev": item["rev"]}
            if i["half"] == "contact":
                t["contact"] = i.get("contact_id") or ""
            else:
                company, _, role = i["who"].partition(" - ")
                t.update(company=company, role=role, sub=sub, stage=i.get("stage") or "")
            targets[did] = t
    if pending:
        book = {str(c.get("contact_id") or "").strip(): c for c in ctx.contacts}
        ids = sorted({str(i.get("contact_id") or "") for i in pending})
        did = "due-withdraw"
        who = [{"contact": cid, "first_name": first_name(book.get(cid, {}).get("name")),
                "employer": str(book.get(cid, {}).get("company") or "")} for cid in ids]
        n = len(ids)
        item = {"id": did, "kind": "withdraw", "sub": "withdraw",
                "title": f"{n} connection request{'s' if n != 1 else ''} nobody accepted",
                # Every due item carries `context` (the contract, _ITEM_KEYS): this one was the
                # only one without, and `app.py check` failed every real model that had it.
                "context": "Withdrawing them keeps your request count clear for new notes.",
                "due": min(i["due"] for i in pending), "company": "",
                "overdue_days": max(int(i.get("late") or 0) for i in pending),
                "action": "requests.withdrawn", "item": None, "work": None,
                "who": who, "steps": "linkedin-withdraw-invitation",
                "done": {"action": "requests.withdrawn", "label": "I withdrew them"},
                "snooze": None, "rev": rev_of(did, ids)}
        out.insert(0, item)
        targets[did] = {"kind": "due", "half": "requests", "contacts": ids, "rev": item["rev"]}
    by_contact: dict = {}
    for d in out:
        cid = (targets.get(d["id"]) or {}).get("contact")
        if cid:
            by_contact.setdefault(cid, []).append(d)
    ctx._got["due_by_contact"] = by_contact
    # Where each person stands reads every row owed (above), so a count of replies owed is
    # never the cut's (140 owed read as 100). The list the page shows cuts people only: an
    # application's, an interview's or a thank-you's row is one per process and always kept,
    # in order (journeys audit 5: cut at 100 behind 550 people).
    rest = [d for d in out if d.get("kind") != "withdraw"]
    room = max(0, DUE_MAX - sum(1 for d in rest if halves.get(d["id"]) != "contact"))
    shown, cut = [], []
    for d in rest:
        if halves.get(d["id"]) == "contact":
            if room <= 0:
                cut.append(d)
                continue
            room -= 1
        shown.append(d)
    out = [d for d in out if d.get("kind") == "withdraw"] + shown
    # The people the cut left off, each once (one person may owe two rows) and never one
    # shown: at 716 people To do listed 93 and said nothing of the rest (the re-audit of
    # 4 November).
    def _who(d: dict) -> str:
        return (targets.get(d["id"]) or {}).get("contact") or d["id"]
    listed = {_who(d) for d in shown if halves.get(d["id"]) == "contact"}
    hidden_row = _hidden_row(ruled, len({_who(d) for d in cut} - listed))
    if hidden_row:
        out.append(hidden_row)
    # Who needs the person is where each stands (standing), worked out with the people: the
    # row is said again there, counting those To do does not list, so To do's "N more people
    # who need you are in Contacts" and Contacts' "N need you" mean one thing, and a follow-up
    # you could send is said apart (the review, 2026-11-05: 1284 beside 1279, the follow-ups
    # counted in one and not the other).
    ctx._got["due_hidden"] = {"rows": out, "ruled": dict(ruled), "listed": listed}
    return out


# Who needs the person, on every screen that says it: someone whose reply, thank-you or call is
# theirs to do (standing's "now"). A follow-up they could send is said apart, as "Follow-up you
# could send" (the maintainer, 2026-11-04: the follow-ups are never counted as people who need
# you). Contacts' "N need you", its Needs you filter and To do's "N more people who need you are
# in Contacts" all count this one group.
NEEDS_YOU = ("now",)


def _hidden_row(ruled: dict, more: int, follow: int = 0) -> dict | None:
    """The one quiet row under To do's list, so a shorter list is never a mystery: who the
    person's own rules keep off it, by why, how many more people who need the person are in
    Contacts, and how many follow-ups they could send are there too; None when there is none."""
    if not ruled and not more and not follow:
        return None
    hidden = sum(ruled.values())
    words = {"employer": "at employers you turned down", "place": "outside where you look",
             "request": "whose connection request nobody accepted", "closed": "closed",
             # surface.held "recent": the person's own quiet days after a message (NW-16)
             "recent": "written to in the last few days"}
    parts = [f"{n} {'person' if n == 1 else 'people'} {words.get(w, w)}"
             for w, n in sorted(ruled.items(), key=lambda x: -x[1])]
    said = [", ".join(parts) + " not shown"] if parts else []
    if more:
        said.append(f"{more} more {'person who needs' if more == 1 else 'people who need'} "
                    f"you {'is' if more == 1 else 'are'} in Contacts")
    if follow:
        said.append(f"{follow} {'follow-up' if follow == 1 else 'follow-ups'} you could send "
                    f"{'is' if follow == 1 else 'are'} there too" if more else
                    f"{follow} more {'follow-up' if follow == 1 else 'follow-ups'} you could send "
                    f"{'is' if follow == 1 else 'are'} in Contacts")
    return {"id": "due-hidden", "kind": "hidden", "sub": "hidden",
            "title": ". ".join(said), "context": "", "due": None,
            "company": "", "overdue_days": 0, "action": None, "item": None,
            "work": None, "done": None, "snooze": None,
            "rev": rev_of("due-hidden", hidden, more, follow) if follow else
            rev_of("due-hidden", hidden, more) if more else rev_of("due-hidden", hidden)}


# ------------------------------------------------------------------ interviews and done


def _scrubbed(value, names):
    """Every string in `value` (a dict, a list, a string) with contact details out (scrub);
    a link the reader kept is a page of the employer's, kept whole, and never a person's
    profile."""
    if isinstance(value, dict):
        return {k: (("" if LINKEDIN_IN.search(str(v or "")) else v) if k == "link"
                    else _scrubbed(v, names)) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrubbed(v, names) for v in value]
    return scrub(value, names) if isinstance(value, str) else value


def _round_held(ctx: Ctx, company: str, role: str) -> bool:
    """Has any round of this application been held: ticked, or booked for a day now gone?"""
    today = ctx.today.isoformat()
    for row in ctx.tracker:
        if (row.get("company") or "").strip() == company and \
                ((row.get("role") or "").strip() or "role not recorded") == role:
            _folder, _files, stages = ctx.stages(row)
            return any(s["done"] or (s["date"] and s["date"] < today) for s in stages)
    return True


def _interviews(ctx: Ctx, targets: dict) -> list:
    import followups
    import throttle
    import app_lists
    out, full, folded, order = [], [], 0, {}
    today = ctx.today.isoformat()
    for row, rid in zip(ctx.tracker, ctx.tracker_ids):
        st = _status(row)
        if st in throttle.UNSENT or not st:
            continue
        folder, files, stages = ctx.stages(row)
        ahead = any(s["date"] and not s["done"] and s["date"] >= today for s in stages)
        live = st not in throttle.FINAL and (st in followups.LIVE_PROCESS or ahead)
        past = None
        if not live:
            # A process that has ended: its interviews stay for 14 days after the last one.
            held = [s for s in stages if s["date"] and s["date"] <= today]
            if not held:
                continue
            past = max(held, key=lambda s: s["date"])
            days = app_lists.ago(past["date"], ctx.today)
            full.append({"id": "int-" + rid[4:], "company": row.get("company") or "",
                         "role": row.get("role") or "", "status": st,
                         "when": interview_when(past["date"], past.get("time"),
                                                past.get("zone"), ctx.zone),
                         "past": True})
            if days is None or days > app_lists.FOLD_DAYS["interviews"]:
                folded += 1
                continue
        import interview_pack
        nxt = (interview_pack.next_stage(stages, today) if stages else {}) if live else {}
        stage = nxt if live else past
        if live and nxt and nxt.get("label") not in {s_["label"] for s_ in stages}:
            # Nothing on record after the last round: next_stage names the next one for a
            # pack ("Round 3"), and the page showed it as an interview with no day and an
            # offer as "Round 4" (2026-11-03). An offer is the offer; otherwise the card is
            # the round last held, waiting to hear, whose prep asks for what comes next.
            held = [s_ for s_ in stages if s_["date"] and s_["date"] <= today]
            if st == "offer":
                stage = {"label": "Offer", "date": "", "time": "", "with": ""}
            elif held:
                stage = max(held, key=lambda s_: (s_["date"], s_.get("time") or ""))
            else:
                stage = dict(nxt, label="Next round")
        prep = os.path.join(folder, "interview_prep.md")
        text = _read(prep)
        iid = "int-" + rid[4:]
        clock = str(stage.get("time") or "")
        import upcoming
        # The days an invitation offers, still to come, and the day to answer by: the card
        # asks which one, a tap books it (the audit, 2026-11-03).
        offered = [d for d in (stage.get("offered") or []) if d >= today] \
            if not stage.get("date") else []
        item = {"id": iid, "company": row.get("company") or "", "role": row.get("role") or "",
                "status": st,
                # The round as it was written (what an action names it by), and its name for
                # a title: "Initial round" where the employer's whole paragraph was stored,
                # the paragraph kept as its details (the maintainer, 2026-11-07).
                "next_stage": upcoming.label(stage.get("label")) or None,
                "stage_title": upcoming.short_label(stage.get("label")) or None,
                "stage_details": upcoming.label_details(stage.get("label")) or None,
                "offered": offered or None,
                "reply_by": (stage.get("reply_by") or None) if offered else None,
                "when": interview_when(stage.get("date"), clock, stage.get("zone"), ctx.zone),
                # Asked for and not confirmed by them yet (the maintainer, 2026-11-05).
                **({"tentative": True} if stage.get("tentative") and stage.get("date") else {}),
                "prep": ({"path": rel(prep), "updated": _mtime(prep),
                          **({"stale": True, "stale_since": _saved_stamp(os.path.join(folder, "outcome.md"))}
                             if _prep_stale(folder, text, stage) else {})}
                         if text else None),
                "questions": len(re.findall(r"^- \*\*Q\.\*\* ", text, re.M)),
                # A stage's day is a whole day in the person's own zone; a time shows only
                # where outcome.md gives one, with the zone written beside it or theirs.
                "all_day": not clock, "time": clock or None,
                "zone": (str(stage.get("zone") or "") or ctx.zone) if clock else None,
                "with": _third_party(stage.get("with"), ctx.names) or None,
                # The rounds: an offer still to come is not one of them ("Offer received" sat
                # among the interview stages, the audit, 2026-11-03).
                "stages": [{"label": upcoming.label(s_["label"]), "date": s_["date"] or None,
                            "time": s_.get("time") or None, "done": s_["done"],
                            "scheduled": s_["scheduled"],
                            "with": _third_party(s_.get("with"), ctx.names) or None}
                           for s_ in stages if s_["done"] or s_["step"] != "offer"],
                "format": _format_of(text, stage.get("label")),
                "one_screen": _one_screen(text, ctx.names),
                # The prep itself, so it is read on the page, never only from a chat (the
                # maintainer, 2026-10-28), as parts in plain words: the few things for the
                # minutes before, each question with its answer, the rest to fold. The
                # document as written was shown whole, a wall of headings, file paths and
                # commands (2026-11-03). Contact details out, as everywhere on the page.
                # Read first, then each line scrubbed: scrubbed first, a source's path lost its
                # space and its digits, and the reader could no longer take it out (2026-11-03).
                "prep_read": _scrubbed(interview_pack.reading(text, row.get("company") or ""),
                                       ctx.names) if text else None,
                "practice": interview_pack.practice(text) if text else None,
                # The live prep, the interview in the order it runs (tools/interview_live.py):
                # only for a round still ahead and only the one it was built for; any other
                # interview draws its prep as before, until /interview makes it again.
                "live": _live_prep(folder, stage, ctx.names) if live and text else None,
                "sent_files": _sent_files(ctx, row),
                "referrer": referrer_of(ctx, row),
                "past": not live,
                # Held and waiting to hear: a live process whose round's day has gone, below
                # what is ahead and never counted as coming up (the maintainer, 2026-11-07: a
                # recruiter screen had on Mon 2 Nov read as if it were still to come).
                "had": live and _round_gone(stage.get("date"), clock, stage.get("zone"), ctx),
                "rev": rev_of(iid, st, stage.get("label"), stage.get("date"), clock,
                              stage.get("with"), bool(text), live, offered,
                              bool(stage.get("tentative")))}
        order[iid] = (str(stage.get("date") or min(offered or ["9999"])), clock)
        _card(ctx, targets, item, "for_interview")
        targets[iid] = dict(_row_target(row, rid), kind="interview", stage=item["next_stage"]
                            or "", rev=item["rev"])
        out.append(item)
        if live:
            full.append({k: item[k] for k in ("id", "company", "role", "status", "when", "past")})
    # By the day and the time each was booked for, as outcome.md gives them: a moment in UTC
    # can fall on the next day.
    ahead = sorted((i for i in out if not i["past"]),
                   key=lambda i: (order[i["id"]], i["company"].lower()))
    done = sorted((i for i in out if i["past"]), key=lambda i: (order[i["id"]], i["company"]),
                  reverse=True)
    out = ahead + done
    _list(ctx, "interviews", full, len(out), folded)
    ctx._got["coming_up"] = coming_up(out)
    return out


def _live_prep(folder: str, stage: dict, names) -> dict | None:
    """The live prep saved for this round, as the page draws it, or None: none saved, one
    no longer fit to show, or one built for another round."""
    import interview_live
    import interview_pack
    doc = interview_live.for_page(interview_live.load(folder))
    if not doc:
        return None
    label = str(stage.get("label") or "")
    if label and doc.get("stage") and not interview_pack._same_round(doc["stage"], label):
        return None
    return _scrubbed(doc, names)


def _round_gone(day, clock, zone, ctx: Ctx) -> bool:
    """Has a round's day gone: a day before today, or today three hours past its time (as
    the page reads an interview as over, isPast)."""
    day = str(day or "")
    if not _ISO_DAY_ONLY.match(day):
        return False
    if day < ctx.today.isoformat():
        return True
    if day > ctx.today.isoformat() or not clock:
        return False
    when = interview_when(day, clock, zone, ctx.zone)
    at = parse_time(when) if when and "T" in when else None
    return bool(at and at + dt.timedelta(hours=3) <= ctx.now)


def coming_up(interviews: list) -> dict:
    """The interviews counted once, for Coming up's summary and the Brief (the page draws
    these, never works them out): ahead (to come, a day or not), of those with no day yet and
    with no prep yet, and waiting (held, waiting to hear). Ids, so a page can leave out one
    ended there before a chat has caught up."""
    ahead = [i for i in interviews if not i.get("past") and not i.get("had")]
    return {"ahead": [i["id"] for i in ahead],
            "undated": [i["id"] for i in ahead if not i.get("when") and not i.get("offered")],
            "unprepped": [i["id"] for i in ahead if str(i.get("status") or "") != "offer"
                          and (not i.get("prep") or i["prep"].get("stale"))],
            "waiting": [i["id"] for i in interviews if not i.get("past") and i.get("had")]}


# Words that make the second of two capitalised words a job title, not a surname:
# "Hiring Manager" stays whole, "Jane Smith" is cut to "Jane".
_TITLE_WORDS = frozenset("""manager lead director recruiter head partner analyst engineer
scientist officer president vp chief team panel talent acquisition people hr senior principal
staff associate consultant specialist coordinator owner founder ceo cto cfo coo interviewer
interviewers""".split())
_TWO_NAMES = re.compile(r"\b([A-Z][a-z]+(?:-[A-Z][a-z]+)?)\s+([A-Z][a-zA-Z'’-]+)\b")


def _third_party(text, names=()) -> str:
    """Who an interview is with, as the page may hold it: contact details out, a contact's
    full name cut to the first (scrub), and anyone else's "First Last" cut to the first
    name, a title ("Hiring Manager") kept whole."""
    out = scrub(text, names)

    def cut(m):
        if m.group(1).lower() in _TITLE_WORDS or m.group(2).lower() in _TITLE_WORDS:
            return m.group(0)
        return m.group(1)
    return _TWO_NAMES.sub(cut, out)


def _one_screen(text, names) -> dict | None:
    import interview_pack
    got = interview_pack.one_screen(text)
    if not got:
        return None
    for k in ("assessing", "hear", "money"):
        if got[k]:
            got[k] = scrub(got[k], names)
    for part in ("questions", "hooks", "do_not_say", "say", "ask"):
        for e in got[part]:
            for k in ("question", "answer", "text"):
                if e.get(k):
                    e[k] = scrub(e[k], names)
    return got


def _format_of(text, label) -> dict | None:
    """The round's kind: as the document says it, else as the stage's own name says it."""
    import interview_pack
    got = interview_pack.format_of(text) if text else None
    if got:
        return got
    found = [interview_pack.FORMAT_NAMES[f] for f, rx in interview_pack.FORMATS
             if rx.search(str(label or ""))]
    return {"names": found, "assumed": False, "told": []} if found else None


def _prep_stale(folder: str, text: str, stage: dict) -> bool:
    """Is the prep for an older plan of rounds? It names the rounds it was built for (its
    `<!-- stages: -->` line); a round booked since, under none of those names, after the prep
    was written, is not one it prepares. A new invitation left "Prep ready" on a prep for
    three rounds that had been replaced (the audit, 2026-11-03)."""
    import interview_live
    import interview_pack
    label = str(stage.get("label") or "")
    # Made for another kind of round than the record now says: out of date too.
    if label and interview_live.kind_changed(folder, label):
        return True
    m = interview_pack._STAGES_MARK.search(text or "")
    built = [x for x in (m.group(1).split("; ") if m else []) if x]
    if not label or not built or any(interview_pack._same_round(b, label) or (
            interview_pack._round_key(b) and interview_pack._round_key(b) ==
            interview_pack._round_key(label)) for b in built):
        return False
    # When each was written, by its commit (saved_at), never the file's own time: git writes a
    # checkout's files in name order, so outcome.md read as a moment newer than the prep after
    # every merge, and a redraw queued the prep again, a stopped one too (the audit of
    # 2026-11-10, PE-3).
    outcome = saved_at(os.path.join(folder, "outcome.md"))
    made = saved_at(os.path.join(folder, "interview_prep.md"))
    return outcome is not None and made is not None and outcome > made


def _saved_stamp(path: str) -> str:
    """When a file's content was written (saved_at), as a stamp; "" for no file."""
    got = saved_at(path)
    return stamp(got) if got else ""


def _sent_files(ctx: Ctx, row: dict) -> list:
    """What they hold of the person's: the resume and letter that went with the application
    (none for a process with no application), and every resume the message log says went to
    someone there, by first name and day."""
    import throttle
    from company_key import key
    from network import state
    out = []
    if not throttle.is_process(row):
        on = throttle.applied_on(row) or None
        out += [{"kind": f["kind"], "name": f["name"], "path": f["path"], "asset": f["asset"],
                 "to": None, "on": on} for f in _files(row)]
    for c in ctx.contacts_by_key.get(key(row.get("company")), []):
        cid = str(c.get("contact_id") or "").strip()
        if not cid:
            continue
        held = ctx._once("resumes_sent", dict)
        if cid not in held:
            held[cid] = state.resumes_sent(ctx.by_contact.get(cid) or [], cid)
        for sent in held[cid]:
            for f in sent["files"] or [""]:
                rp = str(f or "").strip()
                there = bool(rp) and os.path.isfile(person.state(*rp.split("/")))
                got = {"kind": "resume", "name": os.path.basename(rp) or None,
                       "path": rp or None, "asset": asset_for(rp) if there else None,
                       "to": first_name(c.get("name")) or None,
                       "on": sent["date"][:10] or None}
                # Once each: one resume logged twice to one person was listed twice.
                if got not in out:
                    out.append(got)
    return out


# ------------------------------------------------------------------ applications


APP_WORDS = {"applied": "Applied", "interview": "Interviewing", "offer": "Offer",
             "hired": "Hired", "rejected": "Not this time", "withdrawn": "Withdrawn",
             "no_response": "No reply", "no response": "No reply",
             "offer_declined": "Offer declined", "offer declined": "Offer declined"}
# What "I heard back" offers on an application at each status: the writers /outcome uses.
HEARD = {"applied": ("outcome.interview", "outcome.rejected", "outcome.offer",
                     "outcome.withdrawn", "outcome.no_response"),
         "interview": ("outcome.interview", "outcome.rejected", "outcome.offer",
                       "outcome.withdrawn"),
         "offer": ("outcome.rejected", "outcome.withdrawn")}


def referrer_of(ctx: Ctx, row: dict) -> dict | None:
    """Who put the person forward for this application, from the process row's source
    (interview_pack.register_process) or a referral in flight at that employer."""
    from company_key import key
    src = str(row.get("source") or "")
    cid = src[len("contact:"):] if src.startswith("contact:") else ""
    book = ctx._once("book", lambda: {str(c.get("contact_id") or "").strip(): c
                                      for c in ctx.contacts})
    c = book.get(cid)
    # The process's contact is its referrer only when they put the person forward: a recruiting
    # coordinator who booked the call showed as "Referred by" (the night-before run,
    # 2026-11-10). One reading of a referral, the one the process's channel was set by.
    if c is not None:
        import interview_pack
        if interview_pack.process_channel(c) != "referral":
            c = None
    if c is None and str(row.get("channel") or "").lower() == "referral":
        k = key(row.get("company"))
        c = next((x for x in ctx.contacts if key(x.get("company")) == k and
                  (ctx.live.get(str(x.get("contact_id") or "")) or x.get("status"))
                  == "referral_in_progress"), None)
    if c is None:
        return None
    return {"contact": str(c.get("contact_id") or ""), "first_name": first_name(c.get("name"))}


def _applications(ctx: Ctx, targets: dict) -> list:
    """Every application that went, from every round and from outside the app, one record
    each from the day it went to its outcome, with the draft's own id (app-<...>), so one
    item runs from Drafts to Applied (FUNCTIONS_SPEC 1.2)."""
    import app_lists
    import throttle
    due = {}
    for i in ctx.due_items:
        if i.get("half") == "application" and not i.get("held"):
            due.setdefault(i["who"], i)
    out = []
    fold = app_lists.FOLD_DAYS["applications"]
    today = ctx.today.isoformat()
    for row, rid in zip(ctx.tracker, ctx.tracker_ids):
        st = _status(row)
        if st in throttle.UNSENT or not st:
            continue
        on = throttle.applied_on(row) or str(row.get("date") or "")
        folder, files, stages = ctx.stages(row)
        company, role = row.get("company") or "", row.get("role") or "role not recorded"
        dates = [x for x in re.findall(r"\b\d{4}-\d{2}-\d{2}\b", str(row.get("notes") or ""))
                 if x <= today]
        last = max(dates + [on] + [s_["date"] for s_ in stages if s_["date"] and
                                   s_["date"] <= today]) if (dates or on) else None
        live = st not in throttle.FINAL
        ahead = sorted((s_ for s_ in stages if s_["date"] and not s_["done"]
                        and s_["date"] >= today), key=lambda s_: s_["date"])
        nxt = None
        if live and ahead:
            nxt = {"kind": "interview", "label": ahead[0]["label"], "date": ahead[0]["date"]}
        elif live and f"{company} - {role}" in due:
            d = due[f"{company} - {role}"]
            nxt = {"kind": "follow_up", "label": "Follow up", "date": d["due"]}
        item = {"id": rid, "company": company, "role": row.get("role") or "",
                "status": st, "status_word": APP_WORDS.get(st, st.replace("_", " ")),
                "applied_on": on or None, "last": last, "live": live, "next": nxt,
                "stages": [{"label": s_["label"], "date": s_["date"] or None,
                            "done": s_["done"], "scheduled": s_["scheduled"]} for s_ in stages],
                "channel": str(row.get("channel") or ""),
                "referrer": referrer_of(ctx, row),
                "sent_files": [f["name"] for f in _files(row)],
                "followed_up": len(re.findall(r"followed up \d{4}-\d{2}-\d{2}",
                                              str(row.get("notes") or ""))),
                "heard": list(HEARD.get(st, ())), "rev": ""}
        # Its folder's answers to the form, as on its draft: an applied card says what the
        # form was told, and a form's own questions asked after it went land there too
        # (form_answers, 2026-11-05).
        import outreach
        folder = outreach.app_folder(row.get("company"), row.get("role") or "")
        if os.path.isdir(folder):
            item["slug"] = os.path.basename(folder)
            item["screening"] = _screening(folder)
        # The posting it went to, so an applied card links to it with no job row left.
        link = _link_on_row(row, {})
        if link.get("url") or link.get("apply_url"):
            item["apply"] = apply_link(link)
        item["rev"] = rev_of(rid, row_rev(row), item["stages"], nxt)
        quiet = app_lists.ago(last, ctx.today)
        if live or (quiet is not None and quiet <= fold):
            out.append(item)
            targets[rid] = dict(_row_target(row, rid), kind="application", rev=item["rev"])
    out.sort(key=lambda i: (not i["live"], (i["next"] or {}).get("date") or "9999",
                            -(int((i["applied_on"] or "0000-00-00").replace("-", "")[:8]
                                  or 0))))
    # The whole list, cut down, is done.applications' (lists.applications).
    return out


# ------------------------------------------------------------------ referrals


REFERRAL_STAGES = ("asked", "agreed", "put_forward", "interviewing", "ended")


def _referrals(ctx: Ctx, targets: dict) -> list:
    """A referral as a link between a person, a role and a process (FUNCTIONS_SPEC 1.6),
    read from the contact's status, the message log and the tracker: asked (a referral ask
    logged), agreed or put forward (referral_in_progress), interviewing (a process or an
    application there at interview), ended (the application closed)."""
    import throttle
    from network import state
    out = []
    for c in ctx.contacts:
        cid = str(c.get("contact_id") or "").strip()
        if not cid:
            continue
        status = ctx.live.get(cid) or str(c.get("status") or "")
        msgs = ctx.by_contact.get(cid) or []
        asked = [m for m in msgs if state.direction(m) == "out" and "referral" in
                 str(m.get("scenario") or "").lower()]
        if status != "referral_in_progress" and not asked:
            continue
        rows = referred_rows(ctx, c)
        row = max(rows, key=lambda r: str(r.get("date") or "")) if rows else None
        st = _status(row) if row else ""
        stage = ("ended" if st in throttle.FINAL else
                 "interviewing" if st in throttle.LIVE_PROCESS else
                 "put_forward" if status == "referral_in_progress" and row else
                 "agreed" if status == "referral_in_progress" else "asked")
        if stage == "ended" and status != "referral_in_progress":
            pass
        role = (row.get("role") if row else "") or role_in(c.get("next_action"))
        since = max([str(m.get("date") or "")[:10] for m in asked] +
                    ([str(row.get("date") or "")] if row else []), default="") or None
        rid = f"ref-{cid}"
        app_id = None
        if row is not None:
            ids = dict(zip([id(r) for r in ctx.tracker], ctx.tracker_ids))
            app_id = ids.get(id(row))
        item = {"id": rid, "contact": cid, "first_name": first_name(c.get("name")),
                "company": str(c.get("company") or ""), "role": role or None,
                "application": app_id, "stage": stage,
                "route": "portal" if row is not None and "referrer field" in
                str(row.get("notes") or "").lower() else "to_them",
                "since": since, "files_sent": [f["name"] for f in _files(row)] if row else [],
                "process": app_id if row is not None and str(row.get("source") or "")
                .startswith("contact:") else None,
                "rev": rev_of(rid, status, stage, role, since)}
        out.append(item)
        targets[rid] = {"kind": "referral", "contact": cid, "rev": item["rev"]}
    out.sort(key=lambda r: (REFERRAL_STAGES.index(r["stage"]) == 4, r["since"] or ""),
             reverse=False)
    return out


def referred_rows(ctx: Ctx, c: dict) -> list:
    """The tracker rows a contact's referral stands behind: a process filed under them, a
    referral application at their employer, or a row whose notes name them."""
    from company_key import key
    cid = str(c.get("contact_id") or "").strip()
    k = key(c.get("company"))
    return [r for r in ctx.tracker if key(r.get("company")) == k and
            (str(r.get("source") or "") == f"contact:{cid}" or
             str(r.get("channel") or "").lower() == "referral" or
             (cid and cid in str(r.get("notes") or "")))]


_NOTE_DAY = re.compile(r"(?:^|\|)\s*(\d{4}-\d{2}-\d{2}):\s*([^|]+)")


def process_news(ctx: Ctx, cid: str) -> dict | None:
    """{on, what}: the latest thing that happened in the process a contact's referral
    started, from the tracker row's dated notes (an outcome, a stage booked) and the stages
    held on outcome.md; None when nothing is on record. What the referrer is owed word of."""
    import throttle
    c = next((x for x in ctx.contacts if str(x.get("contact_id") or "").strip() == cid), None)
    if c is None:
        return None
    today = ctx.today.isoformat()
    best = None
    for row in referred_rows(ctx, c):
        if _status(row) in throttle.UNSENT:
            continue
        events = []
        for m in _NOTE_DAY.finditer(str(row.get("notes") or "")):
            what = re.sub(r"\s*\((?:page|chat|said in a chat|[a-z ]+)\)\s*$", "",
                          m.group(2)).strip(" .")
            if m.group(1) <= today and re.search(r"\b(?:interview|booked|offer|rejected|"
                                                 r"withdrew|no response)\b", what, re.I):
                events.append((m.group(1), what))
        _folder, _files_, stages = ctx.stages(row)
        events += [(s_["date"], f"the {s_['label'].lower()} is done") for s_ in stages
                   if s_["done"] and s_["date"] and s_["date"] <= today]
        for on, what in events:
            if best is None or on > best["on"]:
                best = {"on": on, "what": scrub(what, ctx.names)}
    return best


def role_in(text) -> str:
    """The role a next step names ("Send the referral ask for the Planning Analyst role"), or
    "": never a sentence about someone ("Wait for Juno to say whether she passed it on"
    read as a role, 2026-11-03)."""
    m = re.search(r"\bfor (?:the )?([A-Z][\w &/-]{2,60}?)(?: role| position|[.,;]|$)",
                  str(text or ""))
    got = m.group(1).strip() if m else ""
    if re.search(r"\b(?:to|whether|if|when|he|she|they|his|her|their|him|them)\b", got):
        return ""
    return got


# ------------------------------------------------------------------ the sending budget


def _message_budget(ctx: Ctx, targets: dict) -> dict:
    """How much has gone this week and today, and the InMail credits left, against the
    person's LinkedIn plan (schema.LIMITS): the line above a wave of first notes. The app
    sets no cap on requests of its own, so no limit is given that LinkedIn did not."""
    from network import schema, state
    b = state.platform_budget(ctx.contacts, ctx.threads, ctx.today, index=ctx.by_contact)
    plan = setting_values().get("linkedin_plan", "free")
    ready = 0
    for f in glob.glob(person.state("documents", "network", "*", "draft.md")):
        cid = os.path.basename(os.path.dirname(f))
        if (ctx.live.get(cid) or "") in schema.NEVER_SENT or not ctx.live.get(cid):
            ready += 1
    line = (f"{ready} note{'s' if ready != 1 else ''} ready. " if ready else "") + \
        f"{b['connections_sent']} sent this week."
    return {"plan": plan, "ready": ready,
            "week": {"sent": b["connections_sent"], "limit": None},
            "day": {"sent": b["connections_today"], "limit": None},
            "notes_left": b["personal_notes_left"],
            "inmail_credits": {"left": b["inmails_left"], "limit": b["inmails_limit"]},
            "note_chars": PLANS_NOTE_CHARS.get(plan),
            "line": line}


PLANS_NOTE_CHARS = {"free": 200, "premium": 300}


# ------------------------------------------------------------------ what it learned


# A rule as the chats wrote it speaks of the person ("Answer the question he actually asked",
# "the candidate prefers"); on their own page it speaks to them (the 3 November audit: 77 of
# 173 rules read as notes about him). Only the words that can mean nobody but the person are
# turned: "the candidate", their own first name, and he, his, him where no one else in the
# rule could be meant by them. What a chat reads is the rule as written.
_HE_VERB = {"is": "are", "was": "were", "has": "have", "does": "do", "doesn't": "don't",
            "isn't": "aren't", "wasn't": "weren't", "hasn't": "haven't"}
_NOT_VERB = {"always", "is", "was", "has", "does", "this", "thus", "us", "yes", "less", "his"}
_SOMEONE_ELSE = re.compile(r"\b(?:contacts?|recruiters?|managers?|interviewers?|founders?|"
                           r"referrers?|someone|they|their|them|she|her|hers)\b", re.I)
_ADVERB = r"(?:always|also|never|often|still|just|only|usually|actually|really|already)"


def _you_verb(word: str) -> str:
    low = word.lower()
    if low in _HE_VERB:
        return _HE_VERB[low]
    if low in _NOT_VERB or not low.isalpha():
        return word
    if low.endswith("ies") and len(low) > 4:
        return word[:-3] + "y"
    if re.search(r"(?:ch|sh|ss|x|o)es$", low):
        return word[:-2]
    if low.endswith("s") and not low.endswith("ss"):
        return word[:-1]
    return word


def to_person(rule: str, first: str = "") -> str:
    """A learned rule said to the person: "Answer the question you actually asked"."""
    text = str(rule or "")

    def cased(src: str, word: str) -> str:
        return word[:1].upper() + word[1:] if src[:1].isupper() else word

    def you(m) -> str:
        # The one who is meant, then the verb after it agreeing: "you want", never "you wants".
        # A capital only where a sentence starts: a name always has one.
        starts = not m.string[:m.start()].strip() or m.string[:m.start()].rstrip()[-1:] in ".!?"
        who = "You" if starts else "you"
        rest = m.group(2)
        if not rest:
            return who
        if rest == "'s":
            return who + "'re"
        words = rest.split()
        return " ".join([who] + words[:-1] + [_you_verb(words[-1])])
    after = rf"('s|(?:\s+{_ADVERB})?\s+[A-Za-z']+)?"
    text = re.sub(r"\bthe candidate's\b", lambda m: cased(m.group(0), "your"), text, flags=re.I)
    text = re.sub(rf"\b([Tt]he candidate)\b{after}", you, text)
    if first and len(first) > 1:
        f = re.escape(first)
        text = re.sub(rf"\b{f}'s\b", lambda m: "Your" if not m.string[:m.start()].strip() or m.string[:m.start()].rstrip()[-1:] in ".!?" else "your", text)
        text = re.sub(rf"\b({f})\b{after}", you, text)
    if _SOMEONE_ELSE.search(text):
        return text
    text = re.sub(rf"\b([Hh]e)\b{after}", you, text)
    text = re.sub(r"\bhimself\b", lambda m: cased(m.group(0), "yourself"), text, flags=re.I)
    text = re.sub(r"\bhis\b", lambda m: cased(m.group(0), "your"), text, flags=re.I)
    text = re.sub(r"\bhim\b", lambda m: cased(m.group(0), "you"), text, flags=re.I)
    return text


def _learned(ctx: Ctx, targets: dict) -> list:
    """What the person taught it (profile/learned.json), each rule with their own words and
    its day, for Settings' "What you have taught it" with Remove (learned.retire)."""
    import learned
    try:
        first = str(person.get("identity.first", "") or "") or \
            (str(person.get("identity.name", "") or "").split() or [""])[0]
    except Exception:  # noqa: BLE001  no profile: no name to turn
        first = ""
    out = []
    for n, e in enumerate(learned.load(), 1):
        # A rule put away because the app now does it by itself stays on the page, folded
        # with the earlier rules, saying so (learned.NOW_PART); every other retired rule
        # leaves it.
        part = e.get("status") == "retired" and bool(e.get("built_in"))
        if e.get("status") == "retired" and not part:
            continue
        lid = f"learned-{n}"
        item = {"id": lid, "n": n, "area": str(e.get("area") or "other"),
                "rule": " ".join(str(e.get("rule") or "").split())[:300],
                "say": to_person(" ".join(str(e.get("rule") or "").split())[:300], first),
                "said": " ".join(str(e.get("said") or "").split())[:200],
                "on": str(e.get("date") or e.get("recorded") or "")[:10] or None,
                "via": str(e.get("via") or "") or None,
                "rev": rev_of(lid, e.get("rule"), e.get("status"))}
        if part:
            b = learned._BUILT_IN.get(str(e.get("built_in"))) or {}
            item.update({"retired": True, "why": learned.NOW_PART,
                         "app_does": b.get("does") or None,
                         "retired_on": str(e.get("retired_on") or "")[:10] or None})
        out.append(item)
        targets[lid] = {"kind": "learned", "n": n, "rev": item["rev"]}
    return out[::-1]


# ------------------------------------------------------------------ help: a tip and the tour


# Where on the page each kind of work's tip belongs, and its tab.
TIP_AREAS = (("search", "jobs"), ("apply", "ready"), ("networking", "messages"),
             ("interview", "interviews"), ("brief", "todo"))


def _help(ctx: Ctx, targets: dict) -> dict:
    """The one tip the page may show now (tools/tips.py line, by its own rules, previewed
    here and only marked shown by tip.seen), and the tour in the page's words."""
    import copy
    import tips
    state = tips.load()
    out = {"tip": None, "tour": [dict(t) for t in tips.PAGE_TOUR], "off": bool(state.get("off"))}
    if state.get("off"):
        return out
    have = {"search": bool(newest_round()), "apply": any(_status(r) for r in ctx.tracker),
            "networking": bool(glob.glob(person.state("documents", "network", "*",
                                                     "draft.md"))),
            "interview": any(_status(r) in ("interview", "offer") for r in ctx.tracker),
            "brief": bool(glob.glob(person.state("documents", "briefs", "*.md")))}
    for area, tab in TIP_AREAS:
        if not have.get(area):
            continue
        text = tips.line(area, ctx.today, copy.deepcopy(state))
        said = tips.for_page(text) if text else ""
        if said:
            tid = f"tip-{area}"
            out["tip"] = {"id": tid, "area": area, "tab": tab, "text": said,
                          "rev": rev_of(tid, text)}
            targets[tid] = {"kind": "tip", "area": area, "rev": out["tip"]["rev"]}
            break
    return out


# ------------------------------------------------------------------ your resume


def resume_made_for(cid: str) -> dict | None:
    """The resume made for a contact who asked for one (general_resume.py --for-contact keeps
    documents/network/<id>/resume.json beside it): {name, path, made_on, asset, get}, or
    None. Only while the file it names is there."""
    try:
        rec_path = person.state("documents", "network", cid, "resume.json")
    except Exception:  # noqa: BLE001  no copy: nothing made
        return None
    if not os.path.isfile(rec_path):
        return None
    try:
        with open(rec_path, encoding="utf-8") as fh:
            rec = json.load(fh)
    except (OSError, ValueError):
        return None
    rel_path = str((rec or {}).get("file") or "").replace("\\", "/") if isinstance(rec, dict) else ""
    if not rel_path or not os.path.isfile(person.state(*rel_path.split("/"))):
        return None
    name = os.path.basename(rel_path)
    return {"name": name, "path": rel_path, "made_on": rec.get("made_on") or None,
            "asset": asset_for(rel_path),
            "get": {"kind": "files", "id": "files~resume-" + cid,
                    "args": {"paths": [rel_path], "resume": rel_path, "files": [name]}}}


def _resume(ctx: Ctx, targets: dict) -> dict | None:
    """The general resume (documents/cv/, docpaths.current_resume): the one sent when nobody
    named a role, free to get, and whether the profile moved since it was made."""
    import docpaths
    rel_path = docpaths.current_resume()
    regen = {"kind": "general_resume", "id": "general_resume~current", "args": {}}
    if not rel_path:
        return {"id": "resume-current", "file": None, "made_on": None, "stale": False, "breaks": [],
                "work": regen, "rev": rev_of("resume-current", None)}
    path = person.state(*rel_path.split("/"))
    made = saved_at(path)
    try:
        prof = saved_at(person.path("01-candidate-profile.md"))
    except person.NoProfile:
        prof = None
    stale = bool(made and prof and prof > made)
    # A file that breaks the person's own document rules is never offered, whatever it is
    # named: not to download, not to a contact, not from the page's file store. A hand-made
    # resume spelling "standardising" with dashes in its dates was one tap away as "Get this
    # one anyway", and offered to contacts as "Free, instant" (2026-11-03). The card says why
    # and the one thing to do with it: make a fresh one, made and checked by the app. Both
    # checks hold it: the drafting pipeline's own (resume_breaks, in plain words) and the
    # claim checker's (docpaths.resume_problems, which stage_picks reads too), so a file
    # either would refuse is never handed out.
    breaks = resume_breaks(path)
    problems = docpaths.resume_problems(rel_path)
    breaks = breaks + [p for p in problems if not (breaks and _SAID_BY_BREAKS.match(p))]
    item = {"id": "resume-current", "file": {"name": os.path.basename(rel_path),
                                             "path": rel_path,
                                             "asset": None if breaks else asset_for(rel_path),
                                             "pages": _pages(path) if rel_path.endswith(".pdf")
                                             else None},
            "made_on": made.date().isoformat() if made else None, "stale": stale,
            "breaks": breaks,
            # Free and instant once it is in the page's own file store: `files` work puts it
            # there once, as an application's documents are put.
            "get": None if breaks else {
                "kind": "files", "id": "files~resume-current",
                "args": {"resume": rel_path, "files": [os.path.basename(rel_path)]}},
            "work": regen, "rev": ""}
    # Its bullets, where it was made with its draft kept (general_resume.keep_draft): the
    # pencil's Tweak panel changes them, its look and its summary, as an application's
    # (the maintainer, 2026-11-06: "you can't choose which bullets go on a general resume").
    item["bullets"] = _general_bullets() if not breaks else []
    item["rev"] = rev_of("resume-current", rel_path, item["made_on"], stale, breaks,
                         [b["id"] for b in item["bullets"]])
    targets["resume-current"] = {"kind": "resume", "path": rel_path, "rev": item["rev"]}
    return item


def _general_draft() -> str:
    import general_resume
    return general_resume.draft_file()


def _general_bullets() -> list[dict]:
    """The bullets on the general resume's kept draft, {id, employer, text}; [] when it was
    made before its draft was kept, or the draft cannot be read."""
    import general_resume
    path = _general_draft()
    try:
        with open(path, encoding="utf-8") as fh:
            got = json.load(fh)
        a = got[0] if isinstance(got, list) and got else {}
        return general_resume.bullets_on(a) if isinstance(a, dict) else []
    except (OSError, ValueError, KeyError, TypeError):
        return []


_BREAKS: dict = {}
# The claim checker's words for what resume_breaks already says plainly: a dash, a spelling,
# the document's noun (docpaths._PLAIN_RULE), never said twice.
_SAID_BY_BREAKS = re.compile(r"^(?:a dash\b|(?:british|american) spelling\b|the word\b)", re.I)


def resume_breaks(path: str) -> list[str]:
    """What in a resume file breaks the person's own document rules (their spelling, the
    dashes they never use, a word they never call it), each in plain words, or [] when it
    keeps them or cannot be read. The checks are the drafting pipeline's own
    (tools/locale_rules.py), so a file the pipeline would refuse is never handed out."""
    try:
        st = os.stat(path)
    except OSError:
        return []
    key = (path, st.st_mtime_ns, st.st_size)
    if key in _BREAKS:
        return _BREAKS[key]
    out: list[str] = []
    try:
        import locale_rules
        import pdftext
        text = pdftext.text(path) if path.lower().endswith(".pdf") else ""
        rules = locale_rules._from_profile()
    except Exception:  # noqa: BLE001  nothing here reads it: nothing to say about it
        text, rules = "", None
    if text and rules is not None:
        words = list(dict.fromkeys(m.group(0) for _, m in rules.wrong_spellings(text)))
        if words:
            out.append("it spells " + ", ".join(f"\u201c{w}\u201d" for w in words[:3])
                       + " another way from your documents")
        if rules.dashes(text):
            out.append("it has dashes your documents never use")
        said = [n.word for n in rules.nouns if n.document.search(text)]
        if said:
            out.append(f"it says \u201c{said[0]}\u201d, a word your documents never use")
    _BREAKS[key] = out
    return out


# ------------------------------------------------------------------ you: what the profile holds

_TEX_WRAP = re.compile(r"\\(?:textbf|textit|emph|mbox)\{([^{}]*)\}")
_TEX_SEP = re.compile(r"\s*(?:\\textbullet\{\}|\\textbullet\b|\\\\|\n|;)\s*")


def tex_plain(text) -> str:
    """A profile's LaTeX string as the words it shows: braces, kerns and escapes gone."""
    s = str(text or "")
    for _ in range(3):
        s = _TEX_WRAP.sub(r"\1", s)
    s = re.sub(r"\\kern\S*\s*", "", s)
    s = re.sub(r"\\([&%$#_])", r"\1", s).replace("--", "-").replace("~", " ")
    s = re.sub(r"\\[a-zA-Z]+\{\}|\\[a-zA-Z]+\b|[{}]", "", s)
    return re.sub(r"\s+", " ", s).strip(" .")


def _plain_list(value) -> list:
    parts = value if isinstance(value, (list, tuple)) else _TEX_SEP.split(str(value or ""))
    return [x for x in (tex_plain(p) for p in parts) if x]


def _upcoming(ctx: Ctx, targets: dict) -> list:
    """Everything booked or due ahead, by day (tools/upcoming.py): interview stages, tests
    due, calls booked, closing days of drafted applications, and what the person added,
    each with the ways to put it in a calendar. Never a follow-up. `upcoming-add` is the
    target of the page's "Add something"; each added one is its own, to take away."""
    import upcoming
    try:
        import app_setup
        url = str(app_setup.page_record().get("url") or "")
    except Exception:  # noqa: BLE001  no page yet: no link in the calendar entry
        url = ""
    targets["upcoming-add"] = {"kind": "upcoming", "rev": "add"}
    try:
        out = upcoming.build(ctx, url)
    except person.NoProfile:
        raise                     # no profile yet: the section is empty, as every other is
    except Exception as e:  # noqa: BLE001  the rest of the page still comes; the chat sees why
        print(f"upcoming: Coming up could not be built ({type(e).__name__}: {e})", file=sys.stderr)
        return []
    for i in out:
        if i.get("own"):
            targets[i["id"]] = {"kind": "upcoming", "own": i["own"], "rev": i["rev"]}
    return out


def _you(ctx: Ctx, targets: dict) -> dict | None:
    """What the profile holds, as the person would list it: their jobs (with how many lines
    each has to choose from), skills, education and certificates, and what is still missing.
    Every change is work for a chat (`profile`), made in 01-candidate-profile.md first."""
    if not person.exists("roles.py"):
        return None
    try:
        roles = person.module("roles")
        lib = getattr(person.module("bullets"), "LIB", {}) if person.exists("bullets.py") else {}
        sk = person.module("skills") if person.exists("skills.py") else None
    except Exception:  # noqa: BLE001
        return None
    jobs = []
    for r in getattr(roles, "ROLES", []) or []:
        employer = str(r.get("employer") or "")
        lines = [k for k in (lib.get(employer) or {}) if not str(k).endswith("_SHORT")]
        jobs.append({"id": "you-job-" + seg(employer + "-" + str(r.get("title") or "")),
                     "employer": employer, "title": str(r.get("title") or ""),
                     "dates": str(r.get("dates") or "").replace("--", "-"),
                     "place": str(r.get("loc") or ""), "lines": len(lines)})
    skills = []
    for it in (getattr(sk, "ITEMS", None) or []) if sk else []:
        name = str(it[1]) if len(it) > 1 else ""
        if name and name not in skills:
            skills.append(name)
    education = _plain_list(getattr(roles, "EDUCATION", ""))
    certs = _plain_list(getattr(roles, "CERTIFICATIONS", ""))
    try:
        text = read_text(person.path("01-candidate-profile.md"))
    except person.NoProfile:
        text = ""
    confirm = len(re.findall(r"\[CONFIRM:", text))
    missing = []
    if not jobs:
        missing.append({"part": "jobs", "say": "The jobs you have had"})
    for j in jobs:
        if not j["lines"]:
            missing.append({"part": "lines", "job": j["id"],
                            "say": f"What you did as {j['title']} at {j['employer']}".strip()})
    if not skills:
        missing.append({"part": "skills", "say": "Your skills"})
    if confirm:
        missing.append({"part": "confirm", "say": f"{confirm} detail{'s' if confirm != 1 else ''} "
                                                  "to check"})
    out = {"id": "you", "jobs": jobs, "skills": skills, "education": education,
           "certificates": certs, "missing": missing, "rev": ""}
    out["rev"] = rev_of("you", {k: v for k, v in out.items() if k != "rev"})
    targets["you"] = {"kind": "you", "rev": out["rev"]}
    return out


# ------------------------------------------------------------------ your search


def portal_label(name: str) -> str:
    """A job site's plain name as the person knows it ("Adzuna", never "api.adzuna.com", the
    maintainer, 2026-11-06): tools/portals.py holds every site's name and note in one place."""
    import portals as portals_mod
    try:
        return portals_mod.label(name)
    except Exception:  # noqa: BLE001  a name must never break the page
        return portals_mod.short(str(name or ""))


def _sites(sites: dict, targets: dict) -> list[dict]:
    """Settings, Job sites: each site's plain name, its one line, whether it is on, and for a
    site that needs a key this computer does not hold, `key` (free, steps) in place of a tick
    that could be ticked. Each site is its own item, so a tap on one is never refused because
    another changed, and a refusal is said on its own row (the maintainer, 2026-11-06: a tick
    that "unticks itself after I leave")."""
    import portals as portals_mod
    out = []
    for name, on in sorted(sites.items()):
        try:
            help_ = {} if portals_mod.has_key(name) else portals_mod.key_help(name)
            words = portals_mod.note(name)
        except Exception:  # noqa: BLE001  one odd portal never hides the rest
            help_, words = {}, portals_mod.DEFAULT_NOTE
        sid = f"site-{seg(portals_mod.short(name))[:60]}"
        row = {"id": sid, "name": name, "label": portal_label(name), "note": words,
               "on": bool(on), "key": help_ or None}
        row["rev"] = rev_of(row)
        targets[sid] = {"kind": "search", "site": name, "rev": row["rev"]}
        out.append(row)
    return out


# A hidden job's reason as the person would say it, first match wins: the trash's own words
# ("pay", "employer", "old"), a closed posting, the week's automatic clear-out, and anything
# cleared by hand, never "at the person's request" (the maintainer, 4.12).
HID_LABELS = (
    (r"^(?:the )?pay\b|salary", "The pay"),
    (r"^(?:the )?place\b|location|commute", "The place"),
    (r"^(?:not my )?field\b", "Not my field"),
    (r"^(?:role|not this role|not this one)\b", "Not this one"),
    (r"^(?:employer|no more roles from|no more from)\b", "Not this employer"),
    (r"^(?:old|too old|posted too long ago)\b", "Posted too long ago"),
    (r"\bclosed\b|no longer open|expired|been filled", "The job closed"),
    (r"automatic|after a week|after 7 days|unpicked|not picked|stale", "Cleared automatically after a week"),
    (r"request|\bcleared\b|said on the page|not for me|taken back|by hand|on the page",
     "You cleared these"),
)


def hid_label(words: str) -> str:
    """The plain label of a reason the person hid jobs for (Settings, Jobs you hid)."""
    said = " ".join(str(words or "").split()).strip()
    low = said.lower()
    for rx, label in HID_LABELS:
        if re.search(rx, low):
            return label
    said = re.sub(r"\bthe (?:person|candidate)'s\b", "your", said, flags=re.I)
    said = re.sub(r"\bthe (?:person|candidate)\b", "you", said, flags=re.I)
    return (said[:1].upper() + said[1:]) if said else "Hidden by you"


def _search(ctx: Ctx, targets: dict) -> dict:
    """The search as the person's own setting files hold it (profile/search.py, boards.py,
    the rulings that hide a kind of job), for Settings' "Your search": each changed through
    the writers the chat uses (search.set, portal.set, rule.lift)."""
    import profile_set
    import portals as portals_mod
    from collections import Counter

    def got(key, default=None):
        v = profile_set.get("search.py", key)
        return default if v in (profile_set.MISSING, None) else v
    try:
        boards = profile_set.get("boards.py", "BOARDS")
    except profile_set.Refused:
        boards = {}
    boards = boards if isinstance(boards, dict) else {}
    try:
        sites = portals_mod.enabled()
    except Exception:  # noqa: BLE001
        sites = {}
    seen = ctx.seen
    import exclude
    # The person's own: a draft a chat stopped (`by` chat) is under Held back for now.
    mine = [e for e in seen.values() if str(e.get("status") or "").lower() == "excluded"
            and e.get("basis") == "person" and e.get("by") != exclude.CHAT
            and exclude.set_aside_holds(e, ctx.today)]
    groups = Counter(exclude.reason_group(str(e.get("exclusion_reason") or "")) for e in mine)
    # A few of what each rule left out, newest first, so "cleared from the list · 141" says what
    # it cleared (the maintainer, 2026-10-30: "surely u should be able to dive into this").
    seen_by: dict = {}
    # Each rule's name as it was written, its capitals kept ("ZQ Bank", never "zq bank"): the
    # group itself is lower case for counting (the 3 November audit).
    said_as: dict = {}
    for e in sorted(mine, key=lambda e: str(e.get("date") or e.get("first_seen") or ""), reverse=True):
        g = exclude.reason_group(str(e.get("exclusion_reason") or ""))
        said = re.split(r"[:;.(,]", html.unescape(str(e.get("exclusion_reason") or "")).strip())[0].strip()[:60]
        if said and g not in said_as:
            said_as[g] = said[:1].upper() + said[1:]
        # A title as a job site sent it, entities and all: "Credit Risk &amp; Collections" was
        # shown with its "&amp;" (the 3 November audit).
        title = html.unescape(str(e.get("title") or "")).strip()
        company = html.unescape(str(e.get("company") or "")).strip()
        if title and len(seen_by.setdefault(g, [])) < 5:
            seen_by[g].append(f"{title} at {company}" if company else title)
    # One row a plain reason, in the person's words: the trash's "employer" read "Employer: 1
    # job" and a chat's ruling "at the person's request" (the maintainer, 4.12). Reasons that
    # say the same thing are one row, and Bring back lifts all of them.
    by_label: dict = {}
    for words, n in groups.most_common():
        label = hid_label(said_as.get(words) or words)
        row = by_label.setdefault(label, {"groups": [], "count": 0, "examples": []})
        row["groups"].append(words)
        row["count"] += n
        row["examples"] += [x for x in seen_by.get(words, []) if len(row["examples"]) < 5]
    rules = []
    for label, row in sorted(by_label.items(), key=lambda kv: -kv[1]["count"])[:20]:
        rid = f"rule-{seg(label)[:60]}"
        rules.append({"id": rid, "words": row["groups"][0], "label": label, "count": row["count"],
                      "basis": "person", "examples": row["examples"][:5],
                      "rev": rev_of(rid, row["count"], row["groups"])})
        targets[rid] = {"kind": "rule", "words": row["groups"][0], "groups": row["groups"],
                        "rev": rules[-1]["rev"]}
    dnt = _json(person.state("job_scraper", "do_not_target.json"), {})
    dnt = dnt.get("entries") if isinstance(dnt, dict) and "entries" in dnt else dnt
    for e in (dnt if isinstance(dnt, list) else []):
        if isinstance(e, dict) and e.get("company"):
            rid = f"rule-dnt-{seg(e['company'])[:60]}"
            said = e.get("reason") or "no team for your work there"
            rules.append({"id": rid, "words": f"{e['company']}: {said}",
                          "count": 1, "basis": "employer", "rev": rev_of(rid, e)})
            targets[rid] = {"kind": "rule", "company": e["company"], "rev": rules[-1]["rev"]}
    pause = paused(ctx.today)
    # Employers the person has ruled out are not "followed", whatever boards.py still lists:
    # the page listed pension funds and a declined bank among them (the 3 November audit).
    out_names = {str(e.get("company") or "").strip().lower() for e in (dnt if isinstance(dnt, list) else [])
                 if isinstance(e, dict)}
    try:
        import bar
        ruled_out = bar.excluded_by_name
    except Exception:  # noqa: BLE001  no bar for this person: nothing ruled out by it
        ruled_out = lambda _name: ""  # noqa: E731
    followed = {k: v for k, v in boards.items()
                if str(k).strip().lower() not in out_names and not ruled_out(str(k))}
    item = {"id": "search-settings",
            "roles": [str(x) for x in got("SCRAPE_QUERIES", []) or []],
            "places": [str(x) for x in got("SCRAPE_LOCATIONS", []) or []],
            "pay": {"floor": got("SALARY_FLOOR"), "target": got("SALARY_TARGET"),
                    "cut": got("SALARY_CUT_BELOW"), "currency": got("CURRENCY_CODE")},
            "window_days": got("JOB_AGE_DAYS", 14),
            "employers": [str(x) for x in got("SCRAPE_EMPLOYERS", []) or []],
            "portals": _sites(sites, targets),
            "boards": [{"employer": k, "system": (v[0] if isinstance(v, (list, tuple)) and v
                                                   else str(v))} for k, v in sorted(followed.items())],
            "boards_left_out": len(boards) - len(followed),
            "rules": rules, "pause": pause, "rev": ""}
    item["rev"] = rev_of({k: v for k, v in item.items() if k != "rev"})
    targets["search-settings"] = {"kind": "search", "rev": item["rev"]}
    return item


def _computer_stopped(ctx) -> bool:
    """Did LinkedIn stop the reads on the person's computer today (its heartbeat's `stop`,
    tools/computer.py stopped_today, as `app.py view` hands it in)?"""
    return bool((ctx._got.get("computer") or {}).get("stopped"))


def paused(today: dt.date) -> dict | None:
    """The break in force on `today`, {until, since}, or None: the one pause, kept by
    tools/routines.py (pause, resume) with the brief it rests. What the brief, the page and
    every reminder ask when they need to know whether the person is away."""
    try:
        import routines
        p = routines.paused(today.isoformat())
    except Exception:  # noqa: BLE001  no profile, no registry: no break
        return None
    until = _date(p.get("until")) if p else None
    return {"until": p["until"], "since": p.get("since") or None} \
        if until and until > today else None


# ------------------------------------------------------------------ where Claude works


def _where(ctx: Ctx, targets: dict) -> dict:
    """Where Claude works, one row each with its state and the next step in page words
    (CAPABILITY_MAP G3): the helper chat in the cloud, reading LinkedIn, a chat on the
    computer (optional) and the brief, from profile/app.json, place.py and routines.py."""
    import place
    import routines
    # The chat that answers the page, as this copy last saw it (tools/app_listen.py): the
    # helper is the small cloud chat the listener hands the page to once setup is done.
    helper = _listener_seen(ctx)
    import app_listen
    import tidy
    # Any chat in the cloud that answers the page is the helper, whoever started it: a
    # second one is never offered beside it. The cloud does the work (4.3), so it is
    # recommended even where a chat on the computer answers the page today.
    helper_row = ({"state": "ready", "title": helper.get("title") or app_listen.HELPER_CHAT_TITLE,
                   "say": "The one chat that does what you ask for here, even with your "
                          "computer off. If it is ever closed, this page offers a new one."}
                  if helper.get("helper") or helper.get("kind") == "cloud" else
                  {"state": "not_set_up", "title": None,
                   "say": "Recommended: Claude's helper in the cloud works when your computer "
                          "is off. Set it up once."})
    reads = place.page_reads(ctx.today)
    import reading
    # The same order the page judges it in (app.js readingState): their choice to paste,
    # then LinkedIn's pause for the day, then whether a read worked lately.
    reading_row = ({"state": "paste", "say": "Off: you paste someone's profile when you write "
                                             "to them."}
                   if reading.reads_now() != "browser" else
                   {"state": "paused", "say": "LinkedIn asked Claude to slow down: reading "
                                              "starts again tomorrow, by itself."}
                   if reading.gate_state()["kind"] != "go" or _computer_stopped(ctx) else
                   {"state": "ready", "say": "Your page reads LinkedIn profiles in the Claude "
                                            "desktop app."} if reads else
                   {"state": "open_in_app", "say": "Open this page in the Claude app on your "
                                                   "computer: it asks once to use Claude's "
                                                   "browser, and reads LinkedIn profiles there."})
    computer = place.place_record().get("computer_chat")
    computer_row = ({"state": "ready", "since": computer, "say": "Your chat on your computer "
                                                                "is set up."} if computer else
                    {"state": "optional", "since": None,
                     "say": "Only if you keep files on your computer for Claude."})
    seen = ctx._got.get("computer") or {}
    if seen.get("state"):
        # Its heartbeat in the page's database (tools/computer.py): one line, at most one
        # action, worked out once in the engine and only drawn by the page.
        # On an older version of the app than this copy: one plain line, never a setting to
        # change (its next chat takes the update by itself). It was worked out and never
        # shown (the builder audit, 2026-11-10, CC-23).
        older = (" It runs an older version of the app, and takes the update by itself the "
                 "next time Claude starts there." if seen.get("behind") else "")
        computer_row = {"state": "ready" if seen["state"] in ("ready", "working") else
                        seen["state"], "since": computer, "say": seen["line"] + older,
                        "name": seen.get("computer") or None,
                        # The registry's page steps end "tap Done", the To do card's own
                        # button: Settings' row has no Done, so that step is not said there
                        # (the screen review, 2026-11-09).
                        "steps": [s for s in (seen.get("action") or {}).get("steps") or []
                                  if "tap Done" not in s],
                        "action": (seen.get("action") or {}).get("label") or None}
    try:
        reg = routines.load()
    except Exception:  # noqa: BLE001
        reg = {}
    brief = next((r for r in (reg.get("routines") or []) if isinstance(r, dict)
                  and r.get("key") == "morning_brief"), None)
    if brief and brief.get("cron"):
        when = (routines.read_cron(brief["cron"]).get("when") or "").strip() or \
            cron_words(brief["cron"])
        brief_row = ({"state": "off", "when": when, "say": "Your brief is off."}
                     if brief.get("off") else
                     {"state": "ready", "when": when,
                      "say": f"Your brief comes {routines.in_sentence(when)}."})
    else:
        brief_row = {"state": "not_set_up", "when": None,
                     "say": "A short message each morning, if you want one: what is due, and "
                            "news that matters."}
    gone = tidy.archived()
    out = {"id": "where", "helper": helper_row, "reading": reading_row,
           "computer": computer_row, "brief": brief_row, "rev": "",
           # The app's own old chats it tidied away (tools/tidy.py), said once in Settings.
           "tidied": {"count": len(gone), "on": max((str(g.get("on") or "") for g in gone),
                                                    default="") or None}}
    out["rev"] = rev_of({k: v for k, v in out.items() if k != "rev"})
    return out


_DAY_NAMES = ("Sundays", "Mondays", "Tuesdays", "Wednesdays", "Thursdays", "Fridays",
              "Saturdays", "Sundays")


def cron_words(cron: str) -> str:
    """"every day at 7:56" or "Mondays and Thursdays at 7:56" from a five-field cron (with
    its CRON_TZ)."""
    parts = str(cron or "").split()
    if parts and parts[0].startswith("CRON_TZ="):
        parts = parts[1:]
    if len(parts) != 5:
        return "on its days"
    mm, hh, _dom, _mon, dow = parts
    try:
        at = f"{int(hh)}:{int(mm):02d}"
    except ValueError:
        at = ""
    if dow == "*":
        days = "every day"
    else:
        try:
            names = [_DAY_NAMES[int(d)] for d in dow.split(",")]
        except (ValueError, IndexError):
            names = []
        days = (", ".join(names[:-1]) + " and " + names[-1]) if len(names) > 1 else \
            (names[0] if names else "on its days")
    return f"{days} at {at}" if at else days


# ------------------------------------------------------------------ LinkedIn: the download and reading


EXPORT_STATES = ("missing", "requested", "fresh", "due")


def _linkedin(ctx: Ctx, targets: dict) -> dict:
    """The LinkedIn data download (tools/network/export.py: asked for, taken, how old, due by
    export.every_days, how often the person wants it asked for, what the last held and what changed since the one before; the
    steps and the files the page lets the person add) and the page's own reading of
    LinkedIn (place.page_reads: read a page lately; the profiles queued for it)."""
    import claude_surfaces
    import export
    import place
    import reading
    st = export.status(ctx.today.isoformat(), tools=(), found=[], threads=ctx.threads)
    rec = export.load_record()
    taken = _date(st["taken_on"])
    asked = st["requested_on"] or None
    state = ("requested" if st["state"] == "waiting" else "fresh" if st["state"] == "fresh"
             else "due" if taken else "requested" if asked else "missing")
    e = claude_surfaces.entry("linkedin-export-files")
    export_block = {
        "id": "linkedin-export", "state": state, "requested_at": asked,
        "taken_on": st["taken_on"] or None,
        "age_days": (ctx.today - taken).days if taken else None,
        "due_on": st["due_on"] or None, "due": state in ("missing", "due"),
        "every_days": st["every_days"],
        "counts": rec.get("counts") or rec.get("rows") or {},
        # What a chat reads from the export, said for the person: never a tool's name
        # ("(export.py pending lists them)" was the card's last words, 2026-11-03).
        "changed": [re.sub(r"\s*\([^()]*\b[\w-]+\.py\b[^()]*\)", "", scrub(x, ctx.names))
                    for x in rec.get("changed") or []],
        "steps": {"lines": claude_surfaces.steps("linkedin-export-files"),
                  "checked": e.get("verified_on"), "link": claude_surfaces.official(e)},
        "files": export.file_names(),
        "rev": ""}
    export_block["rev"] = rev_of("linkedin-export", state, asked, st["taken_on"],
                                 export_block["counts"])
    targets["linkedin-export"] = {"kind": "linkedin", "id": "linkedin-export",
                                  "rev": export_block["rev"]}
    # How often it is asked for (export.every_days), as a setting: its row is in Settings >
    # LinkedIn beside the download, and the reminder's trash sets the same item, so the two
    # never disagree.
    key, label, choices = EXPORT_REMIND
    choice = export.remind_choice()
    sid = f"setting-{key}"
    export_block["reminder"] = {"id": sid, "key": key, "label": label, "kind": "choice",
                                "value": choice, "choices": choices, "help": EXPORT_REMIND_HELP,
                                "rev": rev_of(key, choice)}
    targets[sid] = {"kind": "setting", "key": key, "value": choice,
                    "rev": export_block["reminder"]["rev"]}
    pr = place.page_reads_record()
    from network import schema as _net_schema
    book = ctx._once("book", lambda: {str(c.get("contact_id") or "").strip(): c
                                      for c in ctx.contacts})
    queue = []
    for q in reading.page_queue():
        cid = q["contact"]
        c = book.get(cid)
        # Someone the person dropped or closed is never read: the page opened the profiles
        # of people already turned away (reported from a person's copy, 2026-11-06).
        if c is None or str(c.get("status") or "").strip() in _net_schema.TERMINAL:
            continue
        rid = f"read-{cid}"
        item = {"id": rid, "contact": cid, "first_name": first_name(c.get("name")),
                "employer": str(c.get("company") or ""), "mode": q.get("mode") or "deep",
                "asked_on": q.get("asked_on"), "reach": f"reach/{cid}",
                "rev": rev_of(rid, q.get("asked_on"), q.get("mode"))}
        queue.append(item)
        targets[rid] = {"kind": "page_read", "contact": cid, "mode": item["mode"],
                        "rev": item["rev"]}
    # LinkedIn stopped the day (a check, a sign-out out of turn): the page reads nothing more
    # until tomorrow, and says so in one line. The person's choice to paste holds everywhere.
    setting = "browser" if reading.reads_now() == "browser" else "paste"
    # Stopped here, or on the person's computer as its heartbeat says: the ledger is a cache on
    # each machine, so the cloud's own was empty and it never showed a pause the computer met
    # (the builder audit, 2026-11-10, CC-9).
    paused = reading.gate_state()["kind"] != "go" or _computer_stopped(ctx)
    # The page compares this with its own day, so a pause ends at midnight even when no chat
    # has run since to make the model again.
    paused_until = (ctx.today + dt.timedelta(days=1)).isoformat() if paused else None
    reading_block = {"id": "linkedin-reader", "page_reads": place.page_reads(ctx.today),
                     "ok": bool(pr.get("ok")) if pr else None,
                     "checked_at": pr.get("checked_at") or None,
                     "last_read_at": pr.get("last_read_at") or None,
                     "reads": int(pr.get("reads") or 0),
                     "queue": queue if setting == "browser" else [],
                     "setting": setting, "paused": paused, "paused_until": paused_until,
                     # A waiting note's one line, for where reading stands where the page is
                     # open (READ_HOLD): the page picks it, never writes its own.
                     "hold": dict(READ_HOLD),
                     # The day's sign-in check (reading.linkedin_check): passed today, the page
                     # opens nothing to check again; it compares `on` with its own day.
                     "check": {k: got for k, got in reading.linkedin_check(ctx.now).items()
                               if k in ("state", "on", "at")},
                     "rev": rev_of("linkedin-reader", pr.get("checked_at"), pr.get("ok"),
                                   setting, paused)}
    targets["linkedin-reader"] = {"kind": "linkedin", "id": "linkedin-reader",
                                  "rev": reading_block["rev"]}
    return {"export": export_block, "reading": reading_block}


def _week(d: dt.date) -> str:
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def _done(ctx: Ctx, targets: dict) -> dict:
    import throttle
    from network import state
    rows = ctx.tracker
    # Each application under the tracker id its live record has (_applications), so the page
    # joins the two as one card: the history had no id, every card showed twice and every
    # one took the first interview (journeys audit 1).
    # The build's own ids and grouped log (Ctx), or worked out here for a ctx without them.
    ids = getattr(ctx, "tracker_ids", None)
    row_ids = {id(r): rid for r, rid in zip(rows, tracker_ids(rows) if ids is None else ids)}
    offers = throttle.spellings("offer", "hired", "offer_declined")
    sent = [(r, _date(throttle.applied_on(r))) for r in rows]
    sent = [(r, d) for r, d in sent if d]
    # One application is one row, however many times the tracker holds it (the maintainer,
    # 2026-10-28: the same role at one employer, sent the same day, was listed twice).
    from company_key import key as _ckey
    once, kept = set(), []
    for r, d in sent:
        k = (_ckey(r.get("company") or ""), " ".join(str(r.get("role") or "").lower().split()), d)
        if k not in once:
            once.add(k)
            kept.append((r, d))
    sent = kept
    interviews = sum(1 for r in rows if _status(r) in throttle.REACHED_INTERVIEW)
    n_offers = sum(1 for r in rows if _status(r) in offers)
    # A reply is a message back after one of theirs: a LinkedIn history imported whole holds
    # years of other conversations, and counting every inbound message said 359 replies
    # (the maintainer, 2026-10-26).
    book = {str(c.get("contact_id") or "").strip() for c in ctx.contacts}
    replied_on = []
    replied: dict = {}
    # The people side, for the glance (_glance): every note, message or request the person
    # sent, each acceptance and each call, by day, read in the same pass as the replies.
    people = {"sent": [], "accepted": {}, "calls": {}}
    grouped = getattr(ctx, "by_contact", None)
    grouped = state.by_contact(ctx.threads) if grouped is None else grouped
    for cid, rows_ in grouped.items():
        if cid not in book:
            continue
        wrote = False
        for t in rows_:
            if state.is_call(t):
                d = _date(t.get("date"))
                if d and state.call_held(t):
                    people["calls"][cid] = max(people["calls"].get(cid, d), d)
            elif state.is_acceptance(t):
                d = _date(t.get("date"))
                if d:
                    people["accepted"][cid] = max(people["accepted"].get(cid, d), d)
            elif state.direction(t) == "out" and not state.is_withdrawal(t):
                d = _date(t.get("date"))
                if d:
                    people["sent"].append(d)
            if state.direction(t) == "out":
                wrote = True
            elif wrote and state.said_something(t):
                d = _date(t.get("date"))
                if d:
                    replied_on.append(d)
                    replied.setdefault(cid, d)
                    replied[cid] = max(replied[cid], d)
                elif cid not in replied:
                    replied[cid] = None
    counts = {"applied": len(sent), "interviews": interviews, "offers": n_offers,
              "replies": len(replied), "sent": len(people["sent"])}
    funnel = [{"stage": "applied", "n": len(sent)},
              {"stage": "interview", "n": interviews}, {"stage": "offer", "n": n_offers}]
    # The last 30 days, the page's first view: what was sent in them, how far those got, and
    # the people who answered in them.
    since = ctx.today - dt.timedelta(days=30)
    recent = [r for r, d in sent if d >= since]
    # An application with no date sent that is at interview or offer now is live, so it
    # counts in the window too: one with no date was left out, and the Brief said "1
    # interview" beside an Interviews tab of 2 (the maintainer, 2026-10-31).
    undated = [r for r in rows if not _date(throttle.applied_on(r))]
    r_iv = sum(1 for r in recent + undated if _status(r) in throttle.REACHED_INTERVIEW)
    r_of = sum(1 for r in recent + undated if _status(r) in offers)
    window = {"days": 30, "counts": {"applied": len(recent), "interviews": r_iv, "offers": r_of,
                                     "replies": sum(1 for d in replied.values() if d and d >= since),
                                     "sent": sum(1 for d in people["sent"] if d >= since)},
              "funnel": [{"stage": "applied", "n": len(recent)}, {"stage": "interview", "n": r_iv},
                         {"stage": "offer", "n": r_of}]}
    weeks = []
    start = ctx.today - dt.timedelta(days=ctx.today.weekday())
    for k in range(7, -1, -1):
        lo = start - dt.timedelta(weeks=k)
        hi = lo + dt.timedelta(days=7)
        weeks.append({"week": _week(lo), "applied": sum(1 for _, d in sent if lo <= d < hi),
                      "replies": sum(1 for d in replied_on if lo <= d < hi),
                      "sent": sum(1 for d in people["sent"] if lo <= d < hi)})
    # Every application still open, whatever its age; a closed one for 30 days after its
    # last word (tools/app_lists.py); all of them, cut down, in the page's database.
    import app_lists
    fold = app_lists.FOLD_DAYS["applications"]
    apps, full = [], []
    for r, d in sorted(sent, key=lambda x: (x[1], x[0].get("company") or ""), reverse=True):
        dates = [x for x in re.findall(r"\b\d{4}-\d{2}-\d{2}\b", str(r.get("notes") or ""))
                 if x <= ctx.today.isoformat()]
        st = _status(r)
        item = {"id": row_ids.get(id(r), ""), "company": r.get("company") or "",
                "role": r.get("role") or "",
                "applied_on": d.isoformat(), "status": st, "last": max(dates + [d.isoformat()]),
                "live": st not in throttle.FINAL}
        full.append(dict(item, employer=item["company"],
                         applied=app_lists.bucket(app_lists.ago(item["applied_on"], ctx.today))))
        quiet = app_lists.ago(item["last"], ctx.today)
        if item["live"] or (quiet is not None and quiet <= fold):
            apps.append(item)
    _list(ctx, "applications", full, len(apps))
    glance = _glance(ctx, sent, window, replied, people,
                     [t for cid in book for t in grouped.get(cid, ())])
    return {"counts": counts, "funnel": funnel, "weeks": weeks, "applications": apps,
            "recent": window, "glance": glance}


# ------------------------------------------------------------------ the progress glance

# The most tiles the Brief's Your progress shows: a glance, never a dashboard.
GLANCE_TILES = 4
# A share is said only past these: "100% of applied" from one application read as a boast
# (the page's SHARE_FROM), and a reply rate from three notes is luck.
GLANCE_SHARE_FROM = 5
GLANCE_RATE_FROM = 10
# The "what's working" line compares two groups only when each holds this many, and the
# better one has at least GLANCE_HITS: a line from two applications is an anecdote.
GLANCE_GROUP_FROM = 5
GLANCE_KIND_FROM = 8
GLANCE_HITS = 2
# How much each tile matters when there is more than room for: what has moved furthest (an
# offer, an interview, a referral) before what was done (applied, written to).
_GLANCE_RANK = {"offers": 120, "interviews": 110, "warm": 100, "referrals": 95, "calls": 90,
                "replies": 80, "applied": 50, "sent": 50, "accepted": 45}
# The order the tiles are drawn in, whichever are chosen: jobs, then both, then people.
_GLANCE_ORDER = ("applied", "interviews", "offers", "warm", "sent", "accepted", "replies",
                 "calls", "referrals")
_GLANCE_SIDE = {"applied": "jobs", "interviews": "jobs", "offers": "jobs", "warm": "both",
                "sent": "people", "accepted": "people", "replies": "people", "calls": "people",
                "referrals": "people"}
# Each tile's words: (one, many) under its number, and (one, many) for the one-line form
# under the greeting on a short window.
_GLANCE_WORDS = {
    "applied": (("applied", "applied"), ("applied", "applied")),
    "interviews": (("interview", "interviews"), ("interview", "interviews")),
    "offers": (("offer", "offers"), ("offer", "offers")),
    "warm": (("interview or referral through people", "interviews or referrals through people"),
             ("through people", "through people")),
    "sent": (("message sent", "messages sent"), ("message sent", "messages sent")),
    "accepted": (("accepted your request", "accepted your requests"), ("accepted", "accepted")),
    "replies": (("person replied", "people replied"), ("replied", "replied")),
    "calls": (("call", "calls"), ("call", "calls")),
    "referrals": (("referral in progress", "referrals in progress"),
                  ("referral", "referrals")),
}
# The kinds of reader (network/candidates.kind_of), in plain words for the working line.
_KIND_WORDS = {"recruiter": "Recruiters", "founder": "Founders",
               "hiring_leader": "Hiring managers", "senior_peer": "Senior people",
               "peer": "People in roles like yours"}


def _glance(ctx: Ctx, sent: list, window: dict, replied: dict, people: dict,
            threads: list) -> dict:
    """Your progress at a glance: at most four tiles chosen for this person from what is true
    now, jobs and people both, and one "what's working" line their own numbers support.

    Counted from what `_done` already read (the tracker, the contact book and its messages):
    no run, no model call. A tile with nothing in it is never shown beside one with
    something, so a month of notes and no applications reads as the notes, never "0
    applied" (the maintainer, 2026-11-10: "not make it look like im doing nothing"). Only
    a search with nothing at all done shows its noughts, and says how they fill.
    """
    import throttle
    from company_key import key as _ckey
    days = int(window.get("days") or 30)
    since = ctx.today - dt.timedelta(days=days)
    wc = window.get("counts") or {}
    status = {str(c.get("contact_id") or "").strip(): str(c.get("status") or "").strip()
              for c in ctx.contacts}
    company = {str(c.get("contact_id") or "").strip(): _ckey(c.get("company") or "")
               for c in ctx.contacts}
    referrals = {cid for cid, st in status.items() if st == "referral_in_progress"}
    calls = {cid for cid, d in people["calls"].items() if d >= since} | \
        {cid for cid, st in status.items() if st == "call_booked"}
    # Who answered at each employer, ever: a conversation there is what "through people" and
    # the working line's comparison count.
    talked: set = {company[cid] for cid in set(replied) | referrals | set(people["calls"])
                   if company.get(cid)}
    # Applications live now at an employer where someone talked to the person, that reached an
    # interview; and each referral at an employer applied to. One a employer, however counted.
    applied_at = {_ckey(r.get("company") or ""): r for r, _d in sent}
    warm = {k for k, r in applied_at.items()
            if k and k in talked and _status(r) in throttle.REACHED_INTERVIEW
            and _status(r) not in throttle.FINAL}
    warm |= {company[cid] for cid in referrals if company.get(cid) in applied_at}
    n = {"applied": int(wc.get("applied") or 0), "interviews": int(wc.get("interviews") or 0),
         "offers": int(wc.get("offers") or 0), "sent": int(wc.get("sent") or 0),
         "replies": int(wc.get("replies") or 0),
         "accepted": sum(1 for d in people["accepted"].values() if d >= since),
         "calls": len(calls), "referrals": len(referrals), "warm": len(warm)}
    # The person's own reply rate: first notes answered, of those decided (answered, or two
    # weeks without), from what_works, the one place it is counted.
    cases = []
    try:
        import what_works
        cases = [c for c in what_works.message_cases(ctx.contacts, threads, ctx.today)
                 if c["attempt"] == "opener"]
    except Exception:  # noqa: BLE001  a log it cannot read: no rate, nothing claimed
        cases = []
    won = sum(1 for c in cases if c["won"])
    share = {}
    # How many applications the interviews came from, as a count: "13% of applied" beside
    # "5 applied this week" made the eye divide one by the other, and the 24 it was of was
    # nowhere on the panel (the screen review, 2026-11-11).
    if n["applied"] >= GLANCE_SHARE_FROM and n["interviews"]:
        share["interviews"] = f"from {n['applied']} applied"
    if len(cases) >= GLANCE_RATE_FROM and won:
        share["replies"] = f"{round(100 * won / len(cases))}% answered"

    moving = [k for k in _GLANCE_ORDER if n[k] > 0]
    if moving:
        rank = lambda k: _GLANCE_RANK[k] + (min(n[k], 30) if k in ("applied", "sent") else 0)  # noqa: E731
        pick: list = []
        # Both sides where both moved: the best of jobs and the best of people first.
        for side in ("jobs", "people"):
            mine = [k for k in moving if _GLANCE_SIDE[k] in (side, "both")]
            if mine and not any(_GLANCE_SIDE[k] in (side, "both") for k in pick):
                pick.append(max(mine, key=rank))
        for k in sorted(moving, key=rank, reverse=True):
            if len(pick) >= GLANCE_TILES:
                break
            if k not in pick:
                pick.append(k)
        chosen = [k for k in _GLANCE_ORDER if k in pick]
    else:
        # Nothing done yet: the two things that start a search, at nought, and nothing else.
        chosen = ["applied", "sent"]
    tiles = []
    for k in chosen:
        (one, many), (s_one, s_many) = _GLANCE_WORDS[k]
        v = n[k]
        tiles.append({"k": k, "n": v, "label": one if v == 1 else many,
                      "short": s_one if v == 1 else s_many, "side": _GLANCE_SIDE[k],
                      "share": share.get(k)})
    return {"days": days, "tiles": tiles, "working": _working(ctx, sent, talked, cases)}


def _working(ctx: Ctx, sent: list, talked: set, cases: list) -> str | None:
    """One plain line on what is working, from the person's own numbers, or None.

    Each line is a count said as it stands ("3 of 6"), never a cause, and only past a
    minimum: two groups of GLANCE_GROUP_FROM or more, the better with GLANCE_HITS hits
    and at least twice the other's rate.
    """
    import throttle
    from company_key import key as _ckey

    def better(a_hit, a_n, b_hit, b_n):
        return (a_n >= GLANCE_GROUP_FROM and b_n >= GLANCE_GROUP_FROM and a_hit >= GLANCE_HITS
                and a_hit * b_n >= 2 * b_hit * a_n)
    # Applications that had time to hear back: a week sent, or already answered.
    old = [r for r, d in sent
           if (ctx.today - d).days >= 7 or _status(r) in throttle.REACHED_INTERVIEW]
    warm = [r for r in old if _ckey(r.get("company") or "") in talked]
    cold = [r for r in old if _ckey(r.get("company") or "") not in talked]
    w_hit = sum(1 for r in warm if _status(r) in throttle.REACHED_INTERVIEW)
    c_hit = sum(1 for r in cold if _status(r) in throttle.REACHED_INTERVIEW)
    if better(w_hit, len(warm), c_hit, len(cold)):
        return (f"Where you'd talked to someone there, {w_hit} of {len(warm)} applications "
                f"got an interview; elsewhere {c_hit} of {len(cold)}.")
    # Which kind of person answers first notes most.
    if cases:
        import candidates
        title = {str(c.get("contact_id") or "").strip(): c.get("title", "") for c in ctx.contacts}
        kinds: dict = {}
        for c in cases:
            k = candidates.kind_of(title.get(c["contact_id"], ""))
            h, m = kinds.get(k, (0, 0))
            kinds[k] = (h + int(bool(c["won"])), m + 1)
        won, total = sum(h for h, _m in kinds.values()), sum(m for _h, m in kinds.values())
        big = [(k, h, m) for k, (h, m) in kinds.items() if m >= GLANCE_KIND_FROM]
        if big:
            k, h, m = max(big, key=lambda x: (x[1] / x[2], x[2]))
            rest_h, rest_m = won - h, total - m
            if better(h, m, rest_h, rest_m):
                return (f"{_KIND_WORDS.get(k, k)} answer most: {h} of {m} first notes; "
                        f"everyone else {rest_h} of {rest_m}.")
    return None


# ------------------------------------------------------------------ settings and brief


def setting_values() -> dict:
    """The settings the page can change, each as it stands now."""
    out = {"app_updates": "when_asked" if str(person.get("app_updates", "") or "").strip()
           .lower() == "when_asked" else "auto"}
    try:
        import tips
        out["tips"] = "off" if tips.local().get("off") else "on"
    except Exception:  # noqa: BLE001
        out["tips"] = "on"
    # Read from the file each time, not from network/schema.py, which reads it once at
    # import: a change made on the page shows in the same run. The same rule: no plan, or
    # one the app does not know, is a free account.
    try:
        from network import schema
        out["linkedin_plan"] = schema.plan(fresh=True)
    except Exception:  # noqa: BLE001
        out["linkedin_plan"] = "free"
    import app_alerts
    out["suggestions"] = app_alerts.setting()
    import docpaths
    out["file_names"] = docpaths.file_names()
    for key, default in SETTING_DEFAULTS.items():
        got = str(person.get(key, default) or default)
        allowed = [c[0] for k, _, ch in SETTINGS if k == key for c in ch]
        out[key] = got if got in allowed else default
    # "off" is shown as paste: either way Claude's browser reads nothing, and the page offers
    # only the two (the bin's "Never", or Settings).
    try:
        import reading
        out["profile_reads"] = "browser" if reading.reads_now() == "browser" else "paste"
    except Exception:  # noqa: BLE001  no networking settings: the default
        out["profile_reads"] = "browser"
    try:
        import export
        out["export_remind"] = export.remind_choice()
    except Exception:  # noqa: BLE001  no networking tools here: the rule
        out["export_remind"] = "auto"
    try:
        out["time_zone"] = zone_words(person.home_zone_named(person.directory()))
    except person.NoProfile:
        out["time_zone"] = ""
    return out


def zone_words(zone: str) -> str:
    """A zone as the person says it: "Toronto", "New York", "UTC"; "" for none."""
    zone = str(zone or "")
    if zone in ("UTC", "Etc/UTC"):
        return "UTC"
    if zone == "Etc/GMT":
        return "GMT"
    return zone.rsplit("/", 1)[-1].replace("_", " ")


SETTINGS = (
    ("app_updates", "How updates arrive", [["auto", "By themselves"], ["when_asked", "When I say"]]),
    ("tips", "Tips now and then", [["on", "On"], ["off", "Off"]]),
    ("linkedin_plan", "Your LinkedIn plan", [["free", "Free"], ["premium", "Premium"]]),
    # tools/app_alerts.py: alerts about something wrong stay whatever this says.
    ("suggestions", "Suggestions", [["on", "On"], ["urgent", "Only urgent"], ["off", "Off"]]),
    # networking.py PROFILE_READS: Claude's browser in the desktop app, or the person pastes.
    ("profile_reads", "Reading LinkedIn profiles", [["browser", "Claude reads them"],
                                                    ["paste", "I paste them"]]),
    # The person's, not the app's (4.7): how early the Brief puts the next interview first,
    # and when the calendar events the page makes remind them. The values 4.6 fixed are the
    # defaults.
    # The day before is the shortest (the maintainer, 4.12: "From the day before").
    ("prep_days", "Your next interview on the Brief", [["1", "From the day before"],
                                                        ["2", "From 2 days before"],
                                                        ["7", "From a week before"],
                                                        ["14", "From two weeks before"]]),
    ("calendar_reminder", "Calendar reminders", [["15", "15 minutes before"],
                                                 ["60", "An hour before"],
                                                 ["120", "Two hours before"],
                                                 ["1440", "The day before"], ["off", "None"]]),
    # The brief's headline sent to the phone (tools/brief.py push_due): off unless the person
    # chose it, when the brief is set up or asked once after (profile_upgrades brief-push)
    # (the maintainer, 2026-11-04: "make it off by default but maybe part of the setup").
    ("brief_push", "Phone notification", [["off", "Off"], ["on", "On"]]),
    # What the PDFs the person downloads and uploads are called (docpaths.FILE_NAME_PRESETS,
    # person.json documents.file_names): the person, the employer, then the document unless
    # they choose otherwise. Each choice's own example is the item's `examples`.
    ("file_names", "File names", [[k, label] for k, label, _parts in FILE_NAME_PRESETS]),
)
SETTING_DEFAULTS = {"prep_days": "7", "calendar_reminder": "60", "brief_push": "off"}

# How often the LinkedIn download is asked for (export.REMIND_CHOICES, networking.py
# EXPORT_REMIND). Not in SETTINGS: its one home is the download's own place in Settings >
# LinkedIn, drawn from model.linkedin.export.reminder, and the reminder's trash offers the
# last three (the maintainer, 2026-11-06).
EXPORT_REMIND = ("export_remind", "Reminder to download it",
                 [["auto", "Weekly while messaging"], ["fortnightly", "Every 2 weeks"],
                  ["monthly", "Every month"], ["off", "Off"]])
EXPORT_REMIND_HELP = ("Weekly while you have sent notes or messages in the last two weeks, "
                      "every two weeks otherwise.")


def setting_choices() -> tuple:
    """Every setting the page can set by setting.set, with its choices: SETTINGS and the
    LinkedIn download's reminder."""
    return SETTINGS + (EXPORT_REMIND,)


# The person's own time zone (person.json `time_zone`), said in their words ("Toronto",
# "Eastern", "Mississauga") and read by person.zone_in: every time on the page, "today", and
# every calendar link use it. Never the brief's schedule zone (the audit, 2026-11-03).
TIME_ZONE = ("time_zone", "Your time zone")


def file_name_examples(ctx: Ctx | None = None) -> dict:
    """The File names setting's examples: each choice as a resume of theirs would leave, from
    their own name and the employer and role of their latest application ("Employer" and
    "Analyst" before there is one), and which choice is recommended for their market."""
    import docpaths
    employer = role = ""
    for row in reversed(list(getattr(ctx, "tracker", None) or [])):
        if str(row.get("company") or "").strip():
            employer, role = str(row.get("company")).strip(), str(row.get("role") or "")
            break
    try:
        examples = {k: docpaths.example_file_name(k, employer, role)
                    for k, _label, _parts in docpaths.FILE_NAME_PRESETS}
        country = str(person.get("identity.country", "") or "")
    except person.NoProfile:
        return {}
    return {"examples": examples, "recommended": docpaths.recommended_file_names(country)}


def _settings(ctx: Ctx, targets: dict) -> list:
    values = setting_values()
    out = []
    for key, label, choices in SETTINGS:
        sid = f"setting-{key}"
        item = {"id": sid, "key": key, "label": label, "kind": "choice",
                "value": values[key], "choices": choices, "rev": rev_of(key, values[key])}
        if key == "file_names":
            item.update(file_name_examples(ctx))
        out.append(item)
        targets[sid] = {"kind": "setting", "key": key, "value": values[key], "rev": item["rev"]}
    key, label = TIME_ZONE
    item = {"id": "setting-time_zone", "key": key, "label": label, "kind": "text",
            "value": values[key], "choices": None, "rev": rev_of(key, values[key])}
    out.append(item)
    targets[item["id"]] = {"kind": "setting", "key": key, "value": values[key],
                           "rev": item["rev"]}
    return out


def _zone_question(ctx: Ctx, targets: dict) -> list:
    """Which time zone they are in, asked once nothing they wrote names one: the page shows
    times in the device's own zone meanwhile, and a calendar link made from a guess is hours
    out. Answered in their own words, read by person.zone_in."""
    if ctx.zone_named:
        return []
    qid = "q-time-zone"
    item = {"id": qid, "kind": "question", "title": "Which time zone are you in?",
            "body": "Your interviews, calls and calendar links use it. Say your city, or the "
                    "zone (Eastern, UK time).",
            "options": [{"label": "Say where you are", "action": "setting.set",
                         "input": "text"}],
            "about": {}, "rev": rev_of(qid, "ask")}
    targets[qid] = {"kind": "setting", "key": TIME_ZONE[0], "value": "", "rev": item["rev"]}
    return [item]


def _brief(ctx: Ctx, targets: dict) -> dict | None:
    files = sorted(p for p in glob.glob(person.state("documents", "briefs", "*.md"))
                   if re.match(r"\d{4}-\d{2}-\d{2}", os.path.basename(p)))
    if not files:
        return None
    path = files[-1]
    sections = brief_sections(_read(path), ctx.today)
    # Today's brief searched the news when it has a News part of its own, items or none: its
    # carried points then say the search found nothing newer, never only "Gathered" five days
    # back, which read as no search since (2026-11-03).
    searched = any(sec["kind"] == "news" for sec in sections)
    news_date = _news_fallback(ctx, sections, files[:-1])
    lines = [i["text"] for sec in sections for i in sec["items"]][:8]
    for sec in sections:
        sec["items"] = [dict(i, **brief_link(ctx, i["text"])) for i in sec["items"]]
        # The opening sentences, each with what it is about, so the page can leave out one
        # that a panel beside it already shows (the same interview read four times on one
        # screen, 2026-11-02). A sentence about nothing in particular always stays.
        if sec["kind"] == "lead" and sec.get("text"):
            sec["parts"] = [dict(text=t, **brief_link(ctx, t))
                            for t in re.split(r"(?<=[.!?])\s+(?=[A-Z*])", sec["text"]) if t.strip()]
    out = {"date": os.path.basename(path)[:10], "lines": lines,
           "items": [dict(text=x, **brief_link(ctx, x)) for x in lines],
           "sections": sections, "watch": _watch(), "watch_again": _watch_again(),
           # How many news points the page shows: the person's own choice under Edit the
           # brief (News items), 3 when unset. The page showed up to five whatever it said,
           # four long paragraphs a morning (the maintainer, 2026-11-06: "3 bullets max").
           "news_max": _news_max()}
    if news_date:
        out["news_date"] = news_date
        if searched and news_date < out["date"]:
            out["news_searched"] = out["date"]
    return out


def _news_fallback(ctx: Ctx, sections: list[dict], earlier: list[str]) -> str:
    """The News panel is never empty while a brief of the last four weeks had news (the
    maintainer, 2026-11-02: "it should never say nothing new"): a brief whose search is still
    running, or an older one that said "Quiet week", shows the newest earlier brief's items,
    and the day they were gathered. Returns that day, or "" when today's brief has its own."""
    news = [s for s in sections if s["kind"] == "news"]
    if any(s["items"] for s in news):
        # Carried by a brief whose search brought nothing: the day they were gathered, never
        # "this morning" (the release review, 2026-11-02).
        was = re.search(r"Carried from the brief of (\d{4}-\d{2}-\d{2})", " ".join(s["text"] for s in news))
        return was.group(1) if was else ""
    import brief
    # From as many earlier briefs as it takes to fill the panel, never one point alone.
    lines, day = brief.carry_news(ctx.today, brief.NEWS_MAX, paths=earlier)
    items = [dict({"text": brief_line(x)}, **news_parts(x)) for x in lines if brief_line(x)]
    if not items:
        return ""
    if news:
        news[0]["items"], news[0]["text"] = items, ""
    else:
        sections.append({"title": "News", "kind": "news", "text": "", "items": items})
    return day


def _watch_again() -> list[dict]:
    """What the person stopped watching, to bring back from Edit the brief: each thing they
    took off, and the employers they are in touch with where they turned those off."""
    try:
        import brief
        out = [{"v": x, "label": x} for x in brief.dropped()]
        if "employers" in brief.setting("leave_out"):
            out.insert(0, {"v": "employers", "label": "The employers you are in touch with"})
        return out
    except Exception:  # noqa: BLE001
        return []


def _watch() -> list[dict]:
    """What the brief's news watches, the person's own list, for Edit the brief."""
    try:
        import brief
        return brief.watch_list()
    except Exception:  # noqa: BLE001  an unreadable profile: the panel shows no list
        return []


# Which panel each of the brief's headings is (automation/prompts/brief.md writes them).
BRIEF_KINDS = (("lead", r"lead|today|headline|summary|where the search"), ("owed", r"owed|to send|due"),
               ("next", r"next"), ("news", r"news|market|world"),
               ("since", r"since|numbers|week|so far"))


def brief_line(text: str) -> str:
    """One line of the brief as the person reads it: no file path, no command, a source
    named as a link. The brief is written for a chat too, and a page line saying "run
    `/prep Tamsin`" or "The pack is `documents/network/...`" asked the person to do what
    the page's own buttons do (the maintainer, 2026-10-29)."""
    t = str(text or "").strip()
    t = re.sub(r"\b(?:run|use|do)\s+`/prep\s+([^`]+)`", r"read the prep for \1", t)
    t = re.sub(r"`/prep\s+([^`]+)`", r"the prep for \1", t)
    t = re.sub(r"\b(?:with|using|via)\s+`/outcome[^`]*`", "on your page", t)
    t = re.sub(r"`/(?:outcome)[^`]*`", "your page", t)
    t = re.sub(r"`/(?:interview)\s+([^`]+)`", r"interview prep for \1", t)
    t = re.sub(r"`/[a-z-]+[^`]*`", "", t)
    # "(Bank of Canada, https://...)" reads as a named source: [Bank of Canada](https://...).
    t = re.sub(r"\(([^(),]{2,60}),\s*(https?://[^\s)]+)\)", r"([\1](\2))", t)
    t = re.sub(r"(?<!\()(?<!\]\()\b(https?://[^\s)]+)", r"[source](\1)", t)
    t = t.replace("`", "")
    t = re.sub(r"\s{2,}", " ", t).strip()
    return scrub(t, ())


# A news line as the news reader writes it: what happened (publisher, date, link). How to use it.
# The day is left out of lines written before 4.8 ("(Bank of Canada, https://...)"), which
# then showed as one paragraph (the maintainer, 2026-11-03: "wall of text-y").
_NEWS_LINE = re.compile(r"^(?P<what>.+?)\s*\((?P<src>[^()]{2,80}?),\s*(?:(?P<date>\d{4}-\d{2}-\d{2}),\s*)?"
                        r"(?P<url>https?://[^\s()]+)\)\.?\s*(?P<use>.*)$")


def _news_max() -> int:
    try:
        import brief
        return int(brief.setting("news"))
    except Exception:  # noqa: BLE001  no profile: the app's own default
        return 3


# The same point written "<what happened>. Use it: <how>. [source](<link>)": shown as one
# paragraph, its use and its link inside the words (the maintainer's page, 2026-11-06: "too
# much of a wall of text").
_NEWS_USE = re.compile(r"^(?P<what>.+?[.!?])\s+Use it:\s*(?P<use>.+?)\s*"
                       r"(?:\[(?P<src>[^\]]{1,80})\]\((?P<url>https?://[^\s()]+)\))?\.?$")


def news_parts(line: str) -> dict:
    """A news point in its parts, so the page sets what happened, how to use it and where it
    is from apart: {what, use, src, date, url}, or {} for a line in another shape, shown as
    it is."""
    m = _NEWS_LINE.match(str(line or "").strip())
    if not m:
        u = _NEWS_USE.match(str(line or "").strip())
        if not u:
            return {}
        what, use = brief_line(u.group("what")).rstrip(" ."), brief_line(u.group("use")).rstrip(" .")
        if not what:
            return {}
        src = (u.group("src") or "").strip()
        return {"what": what + ".", "use": (use[:1].upper() + use[1:] + ".") if use else "",
                "src": scrub(src, ()) if src.lower() != "source" else "", "date": None,
                "url": (u.group("url") or "").rstrip(".,;") or None}
    what, use = brief_line(m.group("what")).rstrip(" ."), brief_line(m.group("use")).rstrip(" .")
    if not what:
        return {}
    return {"what": what + ".", "use": (use[:1].upper() + use[1:] + ".") if use else "",
            "src": scrub(m.group("src").strip(), ()), "date": m.group("date"),
            "url": m.group("url").rstrip(".,;")}


def brief_sections(text: str, today: dt.date | None = None) -> list[dict]:
    """The brief in its parts, each {title, kind, text, items: [{text}]}: a heading's own
    sentences as `text`, its bullets or numbered steps as items. A line about a file or a
    folder is left out: nothing on the page opens a path. With `today`, a news item's time
    words are read against its own date (brief.news_as_of): a brief from days before still
    shows, and its "tomorrow" had come."""
    out: list[dict] = []
    cur = None
    for raw in str(text or "").splitlines():
        ln = raw.strip()
        if ln.startswith("# "):
            continue
        m = re.match(r"#{2,3}\s+(.*)", ln)
        if m:
            title = m.group(1).strip()
            kind = next((k for k, rx in BRIEF_KINDS if re.search(r"\b(?:%s)\b" % rx, title, re.I)),
                        "other")
            cur = {"title": title, "kind": kind, "text": "", "items": []}
            out.append(cur)
            continue
        if not ln:
            continue
        if cur is None:
            cur = {"title": "", "kind": "lead", "text": "", "items": []}
            out.append(cur)
        if re.search(r"(?:^|[\s`(])(?:documents|profile|tools|company_research)/\S+", ln):
            continue
        item = re.match(r"(?:[-*]|\d+[.)])\s+(.*)", ln)
        if item:
            raw = item.group(1)
            if cur["kind"] == "news" and today is not None:
                import brief
                raw = brief.news_as_of(raw, today)
            said = brief_line(raw)
            if said:
                cur["items"].append(dict({"text": said}, **(
                    news_parts(raw) if cur["kind"] == "news" else {})))
        else:
            said = brief_line(ln)
            if said:
                # One sentence ends before the next begins: the headline has no full stop of
                # its own, and ran into the lead as one sentence (the audit, 2026-11-03).
                was = cur["text"]
                cur["text"] = (was + ("" if not was or was[-1] in ".!?:" else ".") + " " + said).strip()
    # A part with nothing left in it, a "Read from your main chat's ..." note before the
    # first heading included, is not shown.
    return [sec for sec in out if (sec["items"] or sec["text"])
            and not (not sec["title"] and not sec["items"] and len(out) > 1)]


def brief_link(ctx: Ctx, line: str) -> dict:
    """The item a brief line is about, so a tap opens it (FUNCTIONS_SPEC 2.1): an employer
    it names (its application, its draft, then someone there), or the section a count is
    about ("2 replies owed" is Due)."""
    low = line.lower()

    def word(ch: str) -> bool:
        return ch.isalnum() or ch == "_"

    def named(name) -> bool:
        # A whole name as words, never inside another: "AB" is not in "Crabtree" or "lab", nor
        # "Ada" in "Canada", nor "Freelance" in "Freelancer" (the audit, 2026-11-03). Found
        # with str.find, never a pattern a name: thousands of contacts' names each made a new
        # one, and the brief's lines took a tenth of a second (2026-11-03).
        n = " ".join(str(name or "").lower().split())
        i = low.find(n) if n else -1
        while i >= 0:
            j = i + len(n)
            if not (i and word(low[i - 1])) and not (j < len(low) and word(low[j])):
                return True
            i = low.find(n, i + 1)
        return False
    # A person the line names by their full name is who the line is about, before any
    # employer: a line about one person linked to another (2026-11-03).
    for c in ctx.contacts:
        if " " in str(c.get("name") or "").strip() and named(c.get("name")):
            return {"item": str(c.get("contact_id") or ""), "section": "people"}
    # The longest employer name first, so one name inside another links to the one meant.
    ids = getattr(ctx, "tracker_ids", None)          # the build's own (Ctx), else worked out
    rows = sorted(zip(ctx.tracker, tracker_ids(ctx.tracker) if ids is None else ids),
                  key=lambda x: -len(str(x[0].get("company") or "")))
    def someone_there(company) -> str:
        """The contact at `company` the line names by first name ("Follow up with Wren at
        <employer>"): a line about a person opens them in Contacts, never the employer's
        application in Jobs (a person's copy, 2026-11-05)."""
        from company_key import key as company_key
        k = company_key(company)
        for c in ctx.contacts:
            first = str(c.get("name") or "").split()
            if first and company_key(c.get("company")) == k and len(first[0]) > 1 \
                    and named(first[0]):
                return str(c.get("contact_id") or "")
        return ""
    for row, rid in rows:
        if named(row.get("company")):
            who = someone_there(row.get("company"))
            if who:
                return {"item": who, "section": "people"}
            return {"item": rid, "section": "applications" if _status(row) not in (
                "drafted", "") else "ready"}
    for c in sorted(ctx.contacts, key=lambda c: -len(str(c.get("company") or ""))):
        if named(c.get("company")):
            return {"item": str(c.get("contact_id") or ""), "section": "people"}
    if re.search(r"\b(?:repl(?:y|ies)|nudge|owed|follow)", low):
        return {"item": None, "section": "due"}
    if re.search(r"\binterview", low):
        return {"item": None, "section": "interviews"}
    if re.search(r"\b(?:job|role|posting|search)", low):
        return {"item": None, "section": "jobs"}
    return {"item": None, "section": None}


# ------------------------------------------------------------------ the whole model

def _setup(ctx: Ctx, targets: dict) -> dict:
    import app_setup
    return app_setup.setup_section(ctx.today, targets, now=ctx.now)


def _updates(ctx: Ctx, targets: dict) -> dict:
    import app_setup
    return ctx._once("updates", lambda: app_setup.updates_section(ctx.today, targets))


# ------------------------------------------------------------------ who answers, and when


def _listener_seen(ctx: Ctx) -> dict:
    """What this checkout last saw of the page's listener (app_listen.seen), read once."""
    def make():
        try:
            import app_listen
            got = app_listen.seen().get("listener") or {}
        except Exception:  # noqa: BLE001  no checkout to read: nothing seen
            got = {}
        return got if isinstance(got, dict) else {}
    return ctx._once("listener_seen", make)


def _listener(ctx: Ctx, targets: dict) -> dict:
    """Who answers the page (tools/app_listen.py model_part: where its live record is, read
    by the page itself, and the link that wakes one when nobody answers), and `seen`: what
    this copy last saw of it, the chat's title, cloud or computer, whether it is the helper,
    since when, and whether it answered within the last `quiet_after_s` seconds."""
    import app_listen
    repo = ""
    try:
        owner, folder = ctx.repo
        repo = f"{owner}/{folder}" if owner else ""
    except Exception:  # noqa: BLE001
        pass
    part = app_listen.model_part(repo)
    last = _listener_seen(ctx)
    at = parse_time(last.get("seen_at"))
    part["seen"] = {"title": str(last.get("title") or "") or None,
                    "kind": str(last.get("kind") or "") or None,
                    "helper": bool(last.get("helper")),
                    "since": str(last.get("since") or "") or None,
                    "seen_at": stamp(at) if at else None,
                    "seen_recently": bool(at and 0 <= (ctx.now - at).total_seconds()
                                          <= app_listen.LAPSE_S)}
    return part


def _schedule(ctx: Ctx, targets: dict) -> dict:
    """The brief's days, time and zone, any break in force, and how many changes still wait
    for a chat to make (tools/routines.py page_part), for Settings' "Your brief", with the
    id and rev brief.move, brief.pause and brief.resume act on."""
    import routines
    part = routines.page_part(now=ctx.now, today=ctx.today)
    if part.get("paused") and _date(part["paused"].get("until")) and \
            _date(part["paused"]["until"]) <= ctx.today:
        part["paused"] = dict(part["paused"], over=True)   # its day came: resume lifts it
    part["id"] = "schedule"
    part["rev"] = rev_of("schedule", {k: v for k, v in part.items() if k != "id"})
    targets["schedule"] = {"kind": "schedule", "rev": part["rev"]}
    return part


def _rules(ctx: Ctx, targets: dict) -> dict:
    """Your rules (tools/rules_view.py your_rules): every rule that shapes the search and the
    messages, each one plain sentence with the day it was set, the person's words, what it
    left out of the search Jobs shows, the pencil's setting and the trash's writer, and a quiet
    "Still right?" where it is old and busy; `brief_line`, the Brief's one line about them,
    at most once a month. The person: "how easy is it to change the rules ... which might be
    permanent despite someone's preferences changing over time?" (2026-11-05)."""
    import rules_view
    rows = rules_view.your_rules(ctx.today, ctx.seen)
    for r in rows:
        # Its day too: a rule set again (an employer turned down again) is a new row, which
        # the page shows though a bin on the old one still stands.
        r["rev"] = rev_of(r["id"], r["sentence"], r.get("drop"), r.get("edit"), r["still_right"],
                          r.get("set_on"))
        targets[r["id"]] = {"kind": "your_rule", "id": r["id"], "drop": r.get("drop"),
                            "label": r["sentence"], "rev": r["rev"]}
    line = rules_view.review_line(rows, ctx.today)
    # A learned rule is on the page once, in `learned` ("What you have taught it"): Your rules
    # never draws one (it links to that list), and each was the same words again, 140 KB for
    # 232 rules read on every read of the page (the second audit, 2026-11-10, D7). They still
    # count towards the Brief's line about rules to look at again.
    # One said "for now" whose day has come is drawn here too, with Still right? and Keep it:
    # asked about nowhere else, it held for good (the rules review, 2026-11-11).
    out = {"id": "your-rules", "rows": [r for r in rows if r.get("kind") != "learned"
                                        or r["still_right"]],
           "brief_line": line, "still_right": sum(1 for r in rows if r["still_right"])}
    # What is held back today and every rule that holds anything, each one plain line with
    # its day or its reason and its override (tools/holds.py): an employer was shut 45 days
    # and nothing said so or when it would open (the maintainer, 2026-11-09).
    import holds
    out["held"] = [{k: h[k] for k in ("id", "rule", "what", "until", "line", "say", "lift")}
                   for h in holds.live(ctx.today)]
    out["every_hold"] = [{"id": r["id"], "area": r["area"], "line": r["line"]}
                         for r in holds.rules() if holds.applies(r["id"])]
    out["rev"] = rev_of(out["id"], line, out["still_right"])
    targets["your-rules"] = {"kind": "your_rules", "rev": out["rev"]}
    return out


BUILDERS = {"app": _app, "person": _person, "needs_you": _needs_you, "jobs": _jobs,
            "ready": _ready, "messages": _messages, "due": _due, "people": _people,
            "interviews": _interviews, "done": _done, "settings": _settings, "brief": _brief,
            "setup": _setup, "updates": _updates, "applications": _applications,
            "referrals": _referrals, "message_budget": _message_budget,
            "linkedin": _linkedin, "learned": _learned, "help": _help, "resume": _resume,
            "search": _search, "where": _where, "listener": _listener,
            "schedule": _schedule, "you": _you, "upcoming": _upcoming, "rules": _rules}

# What a section is before there is a profile to build it from: a setup still running, or
# none started. The page shows the setup then, and every other section empty.
EMPTY = {
    "needs_you": [], "ready": [], "messages": [], "due": [], "people": [], "interviews": [],
    "settings": [], "brief": None, "applications": [], "referrals": [],
    "message_budget": {"plan": "free", "ready": 0, "week": {"sent": 0, "limit": None},
                       "day": {"sent": 0, "limit": None}, "notes_left": None,
                       "inmail_credits": {"left": 0, "limit": 0}, "note_chars": 200,
                       "line": "0 sent this week."},
    "linkedin": {"export": {"id": "linkedin-export", "state": "missing", "requested_at": None,
                            "taken_on": None, "age_days": None, "due_on": None, "due": True,
                            "every_days": 14, "counts": {}, "changed": [], "steps": {},
                            "files": [], "rev": "none"},
                 "reading": {"id": "linkedin-reader", "page_reads": False, "ok": None,
                             "checked_at": None, "last_read_at": None, "reads": 0,
                             "queue": [], "check": {"state": "due", "on": None, "at": None},
                             "rev": "none"}},
    "learned": [], "help": {"tip": None, "tour": [], "off": False}, "resume": None,
    "search": None, "where": None, "schedule": None, "upcoming": [],
    "rules": {"id": "your-rules", "rows": [], "brief_line": None, "still_right": 0, "held": [],
              "every_hold": [], "rev": "none"},
    "jobs": {"round": "", "made_at": None, "met": False, "summary": "No search has run yet.",
             "rows": [], "filtered": {"count": 0, "groups": []}},
    "done": {"counts": {"applied": 0, "interviews": 0, "offers": 0, "replies": 0},
             "funnel": [{"stage": "applied", "n": 0}, {"stage": "interview", "n": 0},
                        {"stage": "offer", "n": 0}], "weeks": [], "applications": [],
             "recent": {"days": 30, "counts": {"applied": 0, "interviews": 0, "offers": 0,
                                               "replies": 0},
                        "funnel": [{"stage": "applied", "n": 0}, {"stage": "interview", "n": 0},
                                   {"stage": "offer", "n": 0}]}},
}


def build(today: dt.date | None = None, now: dt.datetime | None = None,
          only=None, shown: dict | None = None, full: dict | None = None,
          work_time: dict | None = None, computer: dict | None = None,
          held_work: dict | None = None, unsaved: list | None = None) -> tuple[dict, dict]:
    """(the model, what each item id stands for in the repo). `only` builds just those
    sections, for an applier that needs one item's rev and not the whole page. `shown` is
    {suggestion id: the day it first showed} from the page's database, so at most three new
    suggestions reach the page a day (tools/app_alerts.py). `full`, a dict, is filled with
    every whole list (tools/app_lists.py) for `app.py view` to write to the database.

    Each employer's tier and verdict and each posting's pay are worked out once for the build
    (tools/remembered.py; the second audit, D8)."""
    import remembered
    _SAVED_AT.clear()             # what git says is asked once a build, never kept past it
    with remembered.build():
        return _make_model(today, now, only, shown, full, work_time, computer, held_work,
                           unsaved)


def _make_model(today, now, only, shown, full, work_time, computer, held_work,
                unsaved) -> tuple[dict, dict]:
    if today is None or now is None:
        t, n = clock()
        today, now = today or t, now or n
    ctx = Ctx(today, now)
    # This copy's own work times, for a cost said on an item (a pasted profile's rewrite).
    ctx._got["work_time"] = dict(work_time or {})
    # The messages Claude's own finished changes held (held_by_work), from `app.py view`.
    ctx._got["held_work"] = dict(held_work or {})
    # The computer as the page's database says it (tools/computer.py state), from `app.py
    # view`: its row in Settings and, while computer work waits on the person, one card.
    ctx._got["computer"] = dict(computer or {})
    # A save a retired chat gave up on, from the page's records (app.unsaved_saves): one card.
    ctx._got["unsaved"] = list(unsaved or [])
    targets: dict = {}
    model = {"model": MODEL, "made_at": stamp(now), "rev": ""}
    for name in SECTIONS:
        if only is not None and name not in only:
            continue
        try:
            model[name] = BUILDERS[name](ctx, targets)
        except person.NoProfile:
            # No profile yet, or one setup is still writing: the section is empty, the
            # setup section says where it stands.
            model[name] = json.loads(json.dumps(EMPTY.get(name)))
    if "people_count" in ctx._got:
        model["people_count"] = ctx._got["people_count"]
    if "coming_up" in ctx._got:
        model["coming_up"] = ctx._got["coming_up"]
    if isinstance(model.get("messages"), list):
        model["to_send"] = to_send(model["messages"])
        model["to_read"] = to_read(model["messages"])
    if only is None and ctx._got.get("lists"):
        import app_lists
        model["lists"] = {}
        for name, (whole, n_shown, folded, doc) in sorted(ctx._got["lists"].items()):
            got = app_lists.summary(name, whole, n_shown, folded)
            if not doc:
                got.update(total=n_shown + int(got["folded"]["count"] or 0), parts=0, doc=None)
            model["lists"][name] = got
            if doc and full is not None:
                full[name] = whole
    if only is None:
        import app_alerts
        import app_lists
        import tweak
        app_alerts.offer(model, today, shown)
        app_lists.link(model)
        # The one table every Tweak panel is built from, and the person's own buttons.
        try:
            model["tweaks"] = {"rows": tweak.table(), "buttons": tweak.buttons(),
                               "usual": tweak.usual(), "rules": tweak.rules()}
        except Exception:  # noqa: BLE001  no profile yet: no buttons, no usual
            model["tweaks"] = {"rows": tweak.table(), "buttons": [], "usual": {}, "rules": {}}
        model["hints"] = tweak.hints()
        # The answer an older refusal (one with none of its own) asks for, by its action:
        # the page draws that control under it, never "Say it in Chat" (2026-11-05).
        import app_actions
        model["refusal_asks"] = app_actions.OLD_REFUSAL_ASKS
        # How long each kind of work takes this copy's Claude, from its own finished work
        # (page_db.work_times, read from the page's database by `app.py view`): the gauge's
        # minutes, the app's defaults only where there is no history yet.
        model["work_time"] = dict(work_time or {})
        # Whether the page offers to pin itself now (app_listen.pin_due: never once pinned,
        # and a Not now is asked again a month later, three times at most).
        try:
            import app_listen
            model["pin"] = {"due": app_listen.pin_due(today)}
        except Exception:  # noqa: BLE001  no profile yet: nothing to offer
            model["pin"] = {"due": False}
        model["rev"] = model_rev(model)
    save_pdf_pages()
    return model, targets


# ------------------------------------------------------------------ check

_REQUIRED = {
    "model": int, "made_at": str, "rev": str, "app": dict, "person": dict, "needs_you": list,
    "jobs": dict, "ready": list, "messages": list, "due": list, "people": list,
    "interviews": list, "done": dict, "settings": list, "setup": dict, "updates": dict,
    "upcoming": list,
}
_ITEM_KEYS = {
    "needs_you": ("id", "kind", "title", "body", "options", "about", "rev"),
    "ready": ("id", "slug", "company", "role", "pay", "place", "apply", "files", "checks",
              "outreach", "screening", "status", "alerts", "suggest", "rev"),
    "messages": ("id", "contact", "first_name", "employer", "channel", "kind", "text", "chars",
                 "limit", "why", "due", "alerts", "suggest", "rev"),
    "due": ("id", "kind", "title", "context", "due", "company", "overdue_days", "action", "done",
            "rev"),
    "people": ("id", "first_name", "employer", "status", "last", "next_action", "due", "rev"),
    "interviews": ("id", "company", "role", "next_stage", "when", "prep", "questions",
                   "alerts", "suggest", "rev"),
    "settings": ("id", "key", "label", "kind", "value", "choices", "rev"),
    "upcoming": ("id", "kind", "title", "day", "time", "start", "end", "all_day", "place",
                 "go", "note", "cal", "rev"),
}
_JOB_KEYS = ("id", "rank", "score", "band", "company", "title", "place", "remote", "pay",
             "deadline", "warm", "apply", "notes", "status", "questions", "alerts", "suggest",
             "rev")
_ENUMS = {
    ("needs_you", "kind"): {"question", "confirm", "consent", "conflict", "setup", "suggest"},
    ("ready", "status"): {"drafted", "applied"},
    ("messages", "channel"): {"linkedin_note", "linkedin_message", "inmail", "email"},
    ("messages", "kind"): {"first_note", "follow_up", "reply", "referral_ask"},
    # "hidden": the one row saying who is not shown (_due's due-hidden), with no day of its own.
    ("due", "kind"): {"follow_up", "reply", "interview", "nudge", "withdraw", "hidden"},
    ("upcoming", "kind"): {"interview", "test", "call", "deadline", "event"},
}
_JOB_STATUS = {"new", "drafting", "ready", "applied", "dismissed"}
_ISO_DAY_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ISO_TIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
# Where the person's own words are shown: their drafts and their own answers.
OWN_TEXT = (("messages", "text"), ("ready", "outreach", "text"), ("ready", "screening"))


def _strings(obj, path=()):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _strings(v, path + (k,))
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings(v, path)
    elif isinstance(obj, str):
        yield path, obj


_ACTION_TYPES = {"work": ("label", "kind", "id", "title", "args"),
                 "act": ("label", "action", "item", "value"), "go": ("label", "to", "item")}


def _check_alerts(item: dict) -> list[str]:
    """A card's alerts (level 1) and its one suggestion (level 2), as app_alerts makes them."""
    import app_alerts
    import page_db
    bad, where = [], f"{item.get('id')}"
    alerts = item.get("alerts")
    if not isinstance(alerts, list):
        return [f"{where}: alerts is not a list"]
    sug = item.get("suggest")
    if sug is not None and not isinstance(sug, dict):
        return [f"{where}: suggest is not an object or null"]
    for a, level in [(a, 1) for a in alerts] + ([(sug, 2)] if sug else []):
        if not isinstance(a, dict) or a.get("level") != level:
            bad.append(f"{where}: an alert or suggestion has the wrong level")
            continue
        for k in ("id", "kind", "text", "why", "action", "cost") + (("since", "rev")
                                                                     if level == 2 else ()):
            if k not in a:
                bad.append(f"{where} {a.get('id')}: missing {k}")
        act = a.get("action")
        if act is not None:
            need = _ACTION_TYPES.get(act.get("type") if isinstance(act, dict) else None)
            if need is None:
                bad.append(f"{where} {a.get('id')}: action type {act!r}")
            elif any(k not in act for k in need):
                bad.append(f"{where} {a.get('id')}: action missing a field")
            elif act["type"] == "work" and act["kind"] not in page_db.WORK_KINDS:
                bad.append(f"{where} {a.get('id')}: no kind of work {act['kind']!r}")
            if not isinstance(a.get("cost"), dict) or a["cost"].get("label") not in \
                    app_alerts.COSTS.values():
                bad.append(f"{where} {a.get('id')}: an action needs its cost in words")
    return bad


def check(model: dict) -> list[str]:
    """What in `model` breaks the contract (CONTRACT.md section 1), one line each."""
    bad = []
    if not isinstance(model, dict):
        return ["the model is not a JSON object"]
    for key, kind in _REQUIRED.items():
        if not isinstance(model.get(key), kind):
            bad.append(f"{key}: missing or not a {kind.__name__}")
    if bad:
        return bad
    if model["model"] != MODEL:
        bad.append(f"model: version {model['model']}, this contract is {MODEL}")
    if not _ISO_TIME.match(model["made_at"]):
        bad.append("made_at: not an ISO time in UTC with Z")
    if model["rev"] != model_rev(model):
        bad.append("rev: does not match the model")
    for key in ("version", "update_waiting", "news"):
        if key not in model["app"]:
            bad.append(f"app.{key}: missing")
    for key in ("first_name", "doc_noun", "time_zone", "repo", "computer"):
        if key not in model["person"]:
            bad.append(f"person.{key}: missing")
    jobs = model["jobs"]
    for key in ("round", "made_at", "met", "summary", "rows", "filtered"):
        if key not in jobs:
            bad.append(f"jobs.{key}: missing")
    for r in jobs.get("rows") or []:
        miss = [k for k in _JOB_KEYS if k not in r]
        if miss:
            bad.append(f"jobs.rows {r.get('id')}: missing {', '.join(miss)}")
        if r.get("status") not in _JOB_STATUS:
            bad.append(f"jobs.rows {r.get('id')}: status {r.get('status')!r}")
    filtered = jobs.get("filtered") or {}
    if not isinstance(filtered.get("count"), int) or not isinstance(filtered.get("groups"), list):
        bad.append("jobs.filtered: needs count and groups")
    ids: dict = {}
    for section, keys in _ITEM_KEYS.items():
        for item in model.get(section) or []:
            if not isinstance(item, dict):
                bad.append(f"{section}: an item is not an object")
                continue
            miss = [k for k in keys if k not in item]
            if miss:
                bad.append(f"{section} {item.get('id')}: missing {', '.join(miss)}")
            for (sec, field), allowed in _ENUMS.items():
                if sec == section and item.get(field) not in allowed:
                    bad.append(f"{section} {item.get('id')}: {field} {item.get(field)!r}")
            if not isinstance(item.get("rev"), str) or not item.get("rev"):
                bad.append(f"{section} {item.get('id')}: no rev")
            if item.get("id") in ids:
                bad.append(f"{section} {item.get('id')}: the id is also in {ids[item['id']]}")
            ids[item.get("id")] = section
    import app_alerts
    for _name, rows in app_alerts.CARDS:
        for item in rows(model):
            bad += _check_alerts(item)
    for name, got in (model.get("lists") or {}).items():
        miss = [k for k in ("total", "shown", "folded", "parts", "doc", "counts") if k not in got]
        if miss:
            bad.append(f"lists.{name}: missing {', '.join(miss)}")
        elif got["shown"] > got["total"] or not isinstance(got["counts"], dict):
            bad.append(f"lists.{name}: shows more than it holds")
    for item in model.get("due") or []:
        if item.get("kind") == "hidden" and item.get("due") is None:
            continue
        if not _ISO_DAY_ONLY.match(str(item.get("due") or "")):
            bad.append(f"due {item.get('id')}: due is not a date")
    for item in model.get("upcoming") or []:
        if not _ISO_DAY_ONLY.match(str(item.get("day") or "")):
            bad.append(f"upcoming {item.get('id')}: day is not a date")
        if bool(item.get("start")) == bool(item.get("all_day")) or any(
                item.get(k) and not _ISO_TIME.match(str(item[k])) for k in ("start", "end")):
            bad.append(f"upcoming {item.get('id')}: a time with no start, or a start not in UTC")
        if sorted(item.get("cal") or {}) != ["google", "ics", "outlook"]:
            bad.append(f"upcoming {item.get('id')}: cal needs google, outlook and ics")
    done = model["done"]
    for key in ("counts", "funnel", "weeks", "applications"):
        if key not in done:
            bad.append(f"done.{key}: missing")
    # Nothing that identifies another person, outside the person's own words.
    for section in ("people", "messages", "due", "needs_you", "jobs", "interviews", "brief",
                    "ready", "done"):
        for path, text in _strings(model.get(section), (section,)):
            if any(path[:len(own)] == own for own in OWN_TEXT):
                continue
            if path and path[-1] == "rev":
                continue            # a hash: twelve hex digits can look like a phone number
            found = private_in(text)
            if found:
                bad.append(f"{'.'.join(path)}: holds {found[0]}")
    return bad
