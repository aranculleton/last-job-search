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
import os
import re
import subprocess
import sys
import urllib.parse

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.join(_HERE, "network"), _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import person  # noqa: E402

MODEL = 1
# Clock fields: true of the moment the model was made, not of the state it shows.
# Fields that say when, not what: left out of every rev, so the same state has the same rev
# whatever the clock says (`seen_at` and `seen_recently` are when a chat last saw the
# page's listener answer).
CLOCK_KEYS = frozenset({"made_at", "updated", "seen_at", "seen_recently"})
SECTIONS = ("app", "person", "needs_you", "jobs", "ready", "messages", "due", "people",
            "interviews", "done", "settings", "brief", "setup", "updates", "applications",
            "referrals", "message_budget", "linkedin", "learned", "help", "resume",
            "search", "where", "listener", "schedule", "you", "upcoming")
# The page shows every live contact, then the rest by recency up to a size budget
# (tools/app_lists.py PEOPLE_BYTES); the whole book is in the page's database for "Show".
DUE_MAX = 100
FILTERED_PER_GROUP = 20
# An application sent this recently stays under Drafts, ticked, so the tick can
# be seen and undone where it was made.
RECENT_APPLIED_DAYS = 14
# At most three facts to confirm at a time (RUNBOOK.md, "Start of a session", step 5).
CONFIRM_MAX = 3

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
    given alone is that day at noon UTC, so a fixed clock gives one model."""
    fixed = now or today or os.environ.get("LJS_TODAY") or ""
    t = parse_time(fixed) if fixed else None
    if t is None:
        t = dt.datetime.now(dt.timezone.utc)
        return (dt.date.fromisoformat(today) if today else dt.date.today()), t
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
        for alt in alts:
            words = _WORDS.findall(alt)
            if not words:
                self.always = True
            elif len(words) == 1:
                self.ones.add(words[0])
            else:
                self.pairs.add((words[0], words[1]))
        # What each text came out as, for this build: a contact's next step is cut down for
        # their row and again for To do, and one title is on many rows.
        self.done: dict = {}
        self.scrubbed: dict = {}

    def could(self, text: str) -> bool:
        """Can a full name be in `text`? False only where none can."""
        if self.always:
            return True
        words = _WORDS.findall(text.casefold())
        if self.ones and not self.ones.isdisjoint(words):
            return True
        return any(p in self.pairs for p in zip(words, words[1:]))

    def sub(self, text: str) -> str:
        if self.rx is None:
            return text
        got = self.done.get(text)
        if got is None:
            got = self.done[text] = self.rx.sub(
                lambda m: self.first.get(m.group(0).casefold(), m.group(0)), text) \
                if self.could(text) else text
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


def saved_at(path: str) -> dt.datetime | None:
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
                                              index=self.by_contact)
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
            "not_saved": _not_saved()}


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
        computer = place.works_on() in ("computer", "both")
    except Exception:  # noqa: BLE001
        pass
    return {"first_name": first, "doc_noun": noun, "time_zone": zone, "repo": repo,
            "computer": computer}


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
        sent = _sent_questions(ctx, targets)
        ctx._got["sent_questions"] = sent
        out += sent
        out += _own_profile_card(ctx, targets)
        out += _tweak_offers(ctx, targets)
    except person.NoProfile:
        pass
    ups = app_setup.upgrade_questions(targets)
    if any(x["id"] == "q-own-profile" for x in out):
        ups = [x for x in ups if x["id"] != "q-upgrade-own-profile-review"]
    return out + ups


TWEAK_OFFERS_MAX = 2
UNCONFIRMED = "UNCONFIRMED"


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


def _profile_questions(ctx: Ctx, targets: dict) -> list:
    import confirm
    out = []
    rows = ctx.tracker
    ids = ctx.tracker_ids
    said = confirm.check(rows, ctx.today).get("notes say sent, tracker says drafted", [])
    if said:
        for row, rid in zip(rows, ids):
            label = confirm.label(row)
            if not any(line.startswith(label + ":") for line in said):
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
    plus, minus = [], []
    for w in fit_why or ():
        m = re.match(r"^\s*([+-])\s*(\d+)\s+(.*)$", str(w))
        if not m:
            continue
        (plus if m.group(1) == "+" else minus).append((int(m.group(2)), m.group(3).strip()))
    out = []
    for group in (plus, minus):
        if group:
            text = max(group)[1]
            text = re.split(r";", text)[0].strip()
            for rx, plain in _WHY_PLAIN:
                text = rx.sub(plain, text)
            out.append(text[:1].upper() + text[1:120])
    return out


# The score's reasons as the card says them: the scorer writes for the chat ("core match",
# "live contact at this employer (...), so this is not a cold application").
_WHY_PLAIN = [
    (re.compile(r"^core match: ", re.I), "matches your skills: "),
    (re.compile(r"^live contact at this employer \(([^)]*)\).*$", re.I), r"you know \1 there"),
    (re.compile(r"^they interviewed you before \(([^)]*)\)$", re.I), r"they interviewed you before, for \1"),
    (re.compile(r"^graduate degree stated without an equivalence route.*$", re.I),
     "asks for a graduate degree, with no other way in"),
    (re.compile(r"^(senior|mid|junior)[^,]*, the band the profile holds$", re.I),
     r"\1, the level you are at"),
]


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
    window = run_round._job_age_days()
    import added_jobs
    found = ([("added", n, r) for n, r in enumerate(added_jobs.load(), 1)]
             + [(name, rank, r) for rank, r in enumerate(raw, 1)] + _earlier_rows(ctx, path))
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
        tracked = _tracker_match(ctx, company, title)
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
                and entry.get("basis") in ("person", "rules"):
            status = "dismissed"
        elif tracked and st not in throttle.UNSENT and st:
            status = "applied"
        elif tracked and str(tracked.get("cv_file") or "").strip():
            status = "ready"
        else:
            status = "new"
        place = str(r.get("location") or "")
        pay = str(r.get("salary") or r.get("pay") or "").strip()
        notes = []
        if (earlier or added) and status not in ("new", "ready"):
            continue               # decided since: an earlier search's row stays there
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
        if r.get("outreach_pending_note"):
            notes.append("Someone here has your message and has not replied: applying is "
                         "fine, a second message is not.")
        jid = f"{rname}-{rank}"
        top, at_target = _pay_top(pay)
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
        # Past the person's own search window, a posting nobody has decided on leaves the list
        # by itself, counted to today from its own date: the week rule hung on a chat
        # remembering to clear it, measured from the day it was found (2026-11-03).
        if status == "new" and not added and posted is not None and posted > window \
                and not (url and norm(url) in kept):
            continue
        item = {"id": jid, "rank": rank, "score": score, "band": _band(score),
                "company": company, "title": title, "place": place, "remote": _remote(place),
                "pay": {"text": pay or "not stated", "stated": bool(pay), "top": top,
                        "at_target": at_target},
                "posted_days": posted,
                # The tools it asks for that the person holds one of the same kind for (fit.py
                # near_matches, kept by the round), for "Asked for Tableau, you have Power BI".
                "near": [{"asked": str(x.get("asked") or ""), "have": str(x.get("have") or "")}
                         for x in (r.get("near") or []) if isinstance(x, dict)][:5],
                "deadline": r.get("deadline") or None, "warm": _warm(ctx, company),
                "draft_work": {"kind": "draft", "id": draft_work_id(url, company, title),
                               "args": {"round": rname, "rank": rank, "url": url,
                                        "company": company, "title": title}},
                "why": [scrub(w, ctx.names) for w in why_of(r.get("fit_why"))],
                "from_round": rname if earlier else None,
                "added": added,
                "kept": norm(url) in kept if url else False,
                "apply": apply_link(r), "notes": notes, "status": status,
                "questions": (["Have you already applied?"] if status == "new" else [])
                + [str(q) for q in (r.get("questions") if isinstance(r.get("questions"), list)
                                    else []) if str(q).strip()],
                "rev": job_rev(url, company, title, status)}
        _card(ctx, targets, item, "for_job")
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
    filtered = _filtered(name, targets)
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


def _filtered(name: str, targets: dict) -> dict:
    data = _json(person.state("documents", "rounds", "filtered", f"{name}.json"), {})
    found = (data.get("filtered") if isinstance(data, dict) else data) or []
    found = [e for e in found if isinstance(e, dict)]
    groups: dict = {}
    for n, e in enumerate(found, 1):
        rule = str(e.get("rule") or e.get("stage") or "other")
        g = groups.setdefault(rule, {"reason": rule, "count": 0, "items": []})
        g["count"] += 1
        if len(g["items"]) < FILTERED_PER_GROUP:
            fid = f"{name}-f{n}"
            item = {"id": fid, "company": str(e.get("company") or ""),
                    "title": str(e.get("title") or ""), "place": str(e.get("location") or ""),
                    "url": str(e.get("url") or ""), "reason": str(e.get("reason") or rule),
                    "rev": rev_of(e.get("url"), e.get("company"), e.get("title"), rule)}
            g["items"].append(item)
            targets[fid] = {"kind": "filtered", "round": name, "n": n,
                            "url": item["url"], "company": item["company"],
                            "title": item["title"], "rev": item["rev"]}
    ordered = sorted(groups.values(), key=lambda g: (-g["count"], g["reason"]))
    # A whole group brought back at once: the page names it filtered~<reason> (its seg()).
    for g in ordered:
        gid = "filtered~" + seg(g["reason"])
        ns = [n for n, e in enumerate(found, 1)
              if str(e.get("rule") or e.get("stage") or "other") == g["reason"]]
        g["id"] = gid
        g["rev"] = rev_of(gid, [(found[n - 1].get("url"), found[n - 1].get("title")) for n in ns])
        targets[gid] = {"kind": "filtered_group", "round": name, "reason": g["reason"],
                        "ns": ns, "rev": g["rev"]}
    return {"count": len(found), "groups": ordered}


def seg(text) -> str:
    """An id part as the page makes one (app.js seg): every other character a hyphen."""
    out = re.sub(r"[^A-Za-z0-9_\-.~:@+]", "-", str(text or ""))[:150]
    return "x" if out in ("", ".", "..") else out


# ------------------------------------------------------------------ ready to send


def _pages(path: str) -> int | None:
    import pdftext
    return pdftext.pages(path)


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


def _files(row) -> list:
    out = []
    for kind, col in (("resume", "cv_file"), ("letter", "cover_letter_file")):
        tex = str(row.get(col) or "").strip()
        if not tex:
            continue
        pdf = os.path.splitext(tex)[0] + ".pdf"
        full = person.state(*pdf.split("/"))
        there = os.path.isfile(full)
        out.append({"kind": kind, "name": os.path.basename(pdf),
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
    return {"passed": True, "line": "Made, right length: " + ", ".join(
        f"{said[f['kind']]} {f['pages']} page{'s' if f['pages'] != 1 else ''}" for f in files)}


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
    "CONTACT": "your contact details are not all in the text",
    "CONTACT_LETTER": "the letter's header is missing your email or phone",
    "ROUNDTRIP": "a line of the draft is missing from the PDF's text",
    "NO_PINNED_SKILL": "the skill you always show is missing", "SKILLPARENS":
    "the skills line has brackets", "DUPBULLET": "a bullet is there twice",
    "UNAUDITED": "a sentence was changed after the checks read it",
    "CLAIMS": "something on it breaks your own rules or is not in your profile",
    "NUMBERS": "a number on it is not in your profile",
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
                "files": [{k: f[k] for k in ("kind", "name", "asset", "path", "pages", "made")}
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


def count_of(chars: int, limit, mtype: str) -> dict:
    """The character count the page shows: always on a first note, where the limit is that
    type's hard rule, and on the rest only near or over it (LAYOUT_SPEC 4.15)."""
    warn = bool(limit) and chars >= 0.9 * limit
    over = bool(limit) and chars > limit
    return {"chars": chars, "limit": limit, "show": mtype == "first_note" or warn,
            "warn": warn, "over": over, "label": (f"{chars} of {limit} characters" if limit
                                                  else f"{chars} characters")}


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
                               name=first_name(contact.get("name")) or None,
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
        found = compose.validate(text, COMPOSE_KIND.get(mtype, "reply"),
                                 name=first_name(contact.get("name")) or None,
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


def _messages(ctx: Ctx, targets: dict) -> list:
    files = sorted(glob.glob(person.state("documents", "network", "*", "draft.md")))
    ctx._got["message_by_contact"] = {}
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
        channel = _channel(c, kind)
        hold = None
        if kind == "first_note" and raw.startswith(reading.WAITS_ON_A_READ):
            hold = "Written before their profile was read: read it first"
        mid = f"msg-{cid}"
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
                "where_unknown": kind != "reply" and not str(c.get("location") or "").strip(),
                "open": open_target(c, channel),
                "application": None,
                "text": text, "chars": len(body), "limit": limit,
                "why": ROUTE_WHY.get(str(c.get("route") or "").strip().lower(),
                                     f"They work at {c.get('company') or 'an employer you want'}"),
                "due": str(c.get("next_action_due") or "") or None, "hold": hold,
                "rev": rev_of(cid, text, kind, channel, live)}
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
        item["paste"] = _paste(cid, item["first_name"], raw) if kind == "first_note" else None
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


def _paste(cid: str, first: str, raw) -> dict | None:
    """"Paste their profile" (profile.pasted, CAPABILITY_MAP G14) on a note that rests on
    nothing read about them: one waiting on a read, or written from their card alone. The
    page offers it under More on a phone or the web, where it cannot read LinkedIn itself."""
    import app_alerts
    import reading
    if raw is None:
        rests = reading.waits_on_read(cid) or reading.card_only_draft(cid)
    else:
        rests = str(raw).startswith(reading.MARKERS)
    return app_alerts.paste_profile(f"msg-{cid}" if raw is not None else cid, first) \
        if rests else None


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
    return {"day": (due or None) if status == "call_booked" else None,
            **({"time": clock} if clock else {}),
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
    text = scrub_names(_redact(re.sub(r"<!--.*?-->", "", read_text(path), flags=re.S)), names)
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
#   leave    their limit of unanswered messages reached: Close, never another message
#   waiting  written to, nothing owed yet
#   new      not written to yet
#   talking  a conversation going, nothing owed now
#   held     the person's own rules stop anything going (surface.held)
#   done     closed, set aside, gone quiet, now an application
GROUPS = ("now", "follow", "leave", "waiting", "new", "talking", "held", "done")
CALL_SOON_DAYS = 7
THANKS_DAYS = 14


def owed_button(cid: str, status: str, due: str, today: dt.date, has_draft: bool,
                action: str = "") -> dict | None:
    """The one button a contact row showed from its status alone, before the engine said
    where each person stands. Kept for a person's own tests (tools/public_names.json): the
    page's button is `standing`'s now, which reads their messages and their own rules too
    (the audit, contacts 14)."""
    if status == "replied_needs_response":
        return {"label": "Draft a reply", "kind": "reply", "id": f"reply~{cid}",
                "args": {"contact": cid}, "ask": "Paste what they said, if it is not logged"}
    if status == "call_booked":
        return {"label": "Prepare for the call", "kind": "prep", "id": f"prep~call~{cid}",
                "args": {"contact": cid, "call": True}}
    late = _date(due)
    if status in ("awaiting_reply", "connected_no_reply") and late and late <= today \
            and not has_draft and not stopped(action):
        return {"label": "Draft the follow-up", "kind": "follow_up", "id": f"follow_up~{cid}",
                "args": {"contact": cid}}
    return None


def standing(ctx: Ctx, c: dict, cid: str, status: str, msgs: list, due_rows: list,
             message: dict | None, hold: dict | None, call: dict | None) -> dict:
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
    leave_row = next((d for d in due_rows if d.get("leave")), None)
    if hold and hold["why"] != "limit":
        out.update(group="held", next=hold["said"])
        return out
    if hold or leave_row:
        said = (hold or {}).get("said") or leave_row.get("step") or ""
        out.update(group="leave", next=said, owed={
            "kind": "close", "label": "Close", "due": leave_row["id"] if leave_row else None,
            "action": "due.done" if leave_row else "person.status",
            "value": None if leave_row else {"status": "gone_cold",
                                             "why": "no reply to your limit of messages"}})
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
    fold = app_lists.FOLD_DAYS["people"]
    # The same first name at the same employer (or with none) more than once: each is told
    # apart by their surname's first letter, never more of it.
    seen_as: dict = {}
    for c in ctx.contacts:
        k = (first_name(c.get("name")).lower(), str(c.get("company") or "").strip().lower())
        seen_as[k] = seen_as.get(k, 0) + 1
    rows, full = [], {}
    counts = dict.fromkeys(GROUPS, 0)
    for c in ctx.contacts:
        cid = str(c.get("contact_id") or "").strip()
        if not cid or cid in full:
            continue
        status = ctx.live.get(cid) or str(c.get("status") or "")
        due = str(c.get("next_action_due") or "").strip()
        msgs = ctx.by_contact.get(cid) or []
        last = max((str(m.get("date") or "")[:10] for m in msgs), default="") or None
        days = app_lists.ago(last, ctx.today)
        hold = surface.held(c, msgs, status, replying=status in schema.OWED_BY_US,
                            memo=ctx._got.setdefault("held_memo", {}))
        call = _call_of(cid, "call_booked" if str(c.get("status") or "") == "call_booked"
                        else status, due, c.get("next_action"), ctx.zone, ctx.names, folders)
        where = standing(ctx, c, cid, status, msgs, due_by.get(cid) or [], shown.get(cid),
                         hold, call)
        group = where["group"]
        counts[group] += 1
        finished = group in ("done", "held")
        live = group in ("now", "follow", "leave") or cid in shown or (
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
    live_rows.sort(key=lambda x: (order[x[8]["group"]], -x[8]["late"],
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
                "stopped": where["group"] == "leave",
                # Whether the person has written to them: someone who wrote first has not
                # been "written to" until a message of theirs went back.
                "wrote": any(state.direction(t) == "out" and not state.is_withdrawal(t)
                             for t in msgs),
                "last": last, "title": title or None,
                "next_action": action, "link": link, "due": due or None,
                "route": full[cid]["route"],
                # Who they came through (the book's referred_by: a contact id or a name), so the
                # page says "Came through Alex" on someone Alex passed them to (2026-10-30).
                "came_through": _came_through(c.get("referred_by"), full) or None,
                "who": who_they_are(c, status),
                "replied": full[cid]["replied"], "live": full[cid]["live"], "call": call,
                "paste": _paste(cid, full[cid]["first_name"], None)
                if (shown.get(cid) or {}).get("kind") == "first_note" else None,
                # Where they live is not on record: the person's rule about where people are
                # cannot be checked, which the page says before anything goes to them.
                "where_unknown": not str(c.get("location") or "").strip(),
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
    ctx._got["people_count"] = {"shown": len(out), "all": len(full), "live": len(live_rows),
                                "rest": len(full) - len(out), "need": counts["now"],
                                "replies": replies, "follow": counts["follow"],
                                "leave": counts["leave"], "waiting": counts["waiting"],
                                "held": counts["held"]}
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


def _due(ctx: Ctx, targets: dict) -> list:
    import open_actions
    items = [i for i in ctx.due_items if not i.get("quiet") and not i.get("old")
             and not str(i.get("what") or "").startswith(UNCONFIRMED)]
    # The person's own surface rules (open_actions._hold_by_rule, surface.held): a thread at
    # its limit of unanswered messages stays, as one to close; anyone else they stop is not
    # shown, counted by why in one quiet line.
    ruled = {}
    for i in items:
        rule = i.get("rule") or {}
        if rule and rule.get("why") != "limit" and len(i.get("held") or []) == 1:
            ruled[rule["why"]] = ruled.get(rule["why"], 0) + 1
    items = [i for i in items if not i.get("held")
             or ((i.get("rule") or {}).get("why") == "limit" and len(i["held"]) == 1)]
    # Requests nobody accepted are never nudged: nothing can be sent to them. They are one
    # row, withdraw them on LinkedIn, then tick (FUNCTIONS_SPEC G8; state.py withdraw).
    pending = [i for i in items if i.get("half") == "contact" and i.get("kind") == "request_pending"]
    items = [i for i in items if i not in pending]
    items.sort(key=open_actions.urgency)
    book = {str(c.get("contact_id") or "").strip(): c for c in ctx.contacts}
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
            limit = (i.get("rule") or {}).get("why") == "limit"
            leave = limit or (raw == "action_due" and stopped(c.get("next_action")))
            if limit:
                # Their limit reached: one to close, never a follow-up, whatever the row said
                # to do next ("Send the short nudge" sat under a third unanswered message).
                step = i["rule"]["said"]
                title = f"{who}{where}: {step}"
            key = i.get("contact_id") or ""
            action = "work:resume_for_contact" if raw == "resume" else _DUE_WORK[kind]
            about = key
            wkind = action.split(":", 1)[1]
            work = {"kind": wkind, "id": f"{wkind}~{key}", "args": {"contact": key}}
            # Named after the person, never after their step: a step written as a note named
            # the work "<who> at <where>: One follow-up sent 2026-10-21. No more after this" in
            # Claude's work (the maintainer, 2026-11-04). Past their limit it is a close, as
            # the title says.
            if wkind == "follow_up" and not limit:
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
        # row had no Done, and sorted to the bottom (the audit, 2026-11-03). A thread at its
        # limit is one to close: its Done is the Close (app_actions, `leave`).
        doable = (i["half"] == "contact" and (raw == "action_due" or leave)) or (
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
        # A contact's: what is due said without who, and whether it is only to leave.
        own = ({"step": step, **({"leave": True} if leave else {})}
               if i["half"] == "contact" else {})
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
                if leave:
                    t["leave"] = True        # its Close closes the thread (app_actions)
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
    more = len({_who(d) for d in cut} - {_who(d) for d in shown
                                         if halves.get(d["id"]) == "contact"})
    if ruled or more:
        # Said once, quietly, so a shorter list is never a mystery: who the person's own rules
        # keep off it, by why, and how many more are in Contacts. One row.
        hidden = sum(ruled.values())
        words = {"employer": "at employers you turned down", "place": "outside where you look",
                 "request": "whose connection request nobody accepted", "closed": "closed"}
        parts = [f"{n} {'person' if n == 1 else 'people'} {words.get(w, w)}"
                 for w, n in sorted(ruled.items(), key=lambda x: -x[1])]
        said = [", ".join(parts) + " not shown"] if parts else []
        if more:
            said.append(f"{more} more {'person who needs' if more == 1 else 'people who need'} "
                        f"you {'is' if more == 1 else 'are'} in Contacts")
        out.append({"id": "due-hidden", "kind": "hidden", "sub": "hidden",
                    "title": ". ".join(said), "context": "", "due": None,
                    "company": "", "overdue_days": 0, "action": None, "item": None,
                    "work": None, "done": None, "snooze": None,
                    "rev": rev_of("due-hidden", hidden, more) if more else
                    rev_of("due-hidden", hidden)})
    return out


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
                "next_stage": upcoming.label(stage.get("label")) or None,
                "offered": offered or None,
                "reply_by": (stage.get("reply_by") or None) if offered else None,
                "when": interview_when(stage.get("date"), clock, stage.get("zone"), ctx.zone),
                "prep": ({"path": rel(prep), "updated": _mtime(prep),
                          **({"stale": True} if _prep_stale(folder, text, stage) else {})}
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
                "sent_files": _sent_files(ctx, row),
                "referrer": referrer_of(ctx, row),
                "past": not live,
                "rev": rev_of(iid, st, stage.get("label"), stage.get("date"), clock,
                              stage.get("with"), bool(text), live, offered)}
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
    return out


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
    import interview_pack
    label = str(stage.get("label") or "")
    m = interview_pack._STAGES_MARK.search(text or "")
    built = [x for x in (m.group(1).split("; ") if m else []) if x]
    if not label or not built or any(interview_pack._same_round(b, label) or (
            interview_pack._round_key(b) and interview_pack._round_key(b) ==
            interview_pack._round_key(label)) for b in built):
        return False
    try:
        return os.path.getmtime(os.path.join(folder, "outcome.md")) > \
            os.path.getmtime(os.path.join(folder, "interview_prep.md"))
    except OSError:
        return False


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
        if e.get("status") == "retired":
            continue
        lid = f"learned-{n}"
        item = {"id": lid, "n": n, "area": str(e.get("area") or "other"),
                "rule": " ".join(str(e.get("rule") or "").split())[:300],
                "say": to_person(" ".join(str(e.get("rule") or "").split())[:300], first),
                "said": " ".join(str(e.get("said") or "").split())[:200],
                "on": str(e.get("date") or e.get("recorded") or "")[:10] or None,
                "via": str(e.get("via") or "") or None,
                "rev": rev_of(lid, e.get("rule"), e.get("status"))}
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
    item["rev"] = rev_of("resume-current", rel_path, item["made_on"], stale, breaks)
    targets["resume-current"] = {"kind": "resume", "path": rel_path, "rev": item["rev"]}
    return item


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


# A job site's name as people write it: "linkedin-search" is LinkedIn, never "Linkedin".
_BRANDS = {"linkedin": "LinkedIn", "freehire": "Freehire", "jobbank": "Job Bank",
           "indeed": "Indeed", "glassdoor": "Glassdoor"}


def portal_label(name: str) -> str:
    """A job site's name as the person knows it: the brand, else the address it lives at
    ("builtintoronto.com"), never a name made from its folder ("Builtintoronto", the 3
    November audit)."""
    base = re.sub(r"-search$", "", str(name or ""))
    if base.lower() in _BRANDS:
        return _BRANDS[base.lower()]
    try:
        import portals as portals_mod
        host = re.sub(r"^www\.", "", urllib.parse.urlparse(portals_mod.url(name)).netloc.lower())
    except Exception:  # noqa: BLE001  no frontmatter: the folder's name below
        host = ""
    if host:
        return host
    words = re.split(r"[-_]+", base)
    return " ".join(w if w.isupper() else w[:1].upper() + w[1:] for w in words if w)


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
    why = {"linkedin-search": "LinkedIn's own job search.",
           "freehire-search": "A free board that lists jobs from many sites."}
    seen = ctx.seen
    mine = [e for e in seen.values() if str(e.get("status") or "").lower() == "excluded"
            and e.get("basis") == "person"]
    import exclude
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
    rules = []
    for words, n in groups.most_common(20):
        rid = f"rule-{seg(words)[:60]}"
        rules.append({"id": rid, "words": words, "label": said_as.get(words) or words[:1].upper() + words[1:],
                      "count": n, "basis": "person",
                      "examples": seen_by.get(words, []), "rev": rev_of(rid, n)})
        targets[rid] = {"kind": "rule", "words": words, "rev": rules[-1]["rev"]}
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
            "portals": [{"name": k, "label": portal_label(k), "on": bool(v), "why": why.get(k, "")}
                        for k, v in sorted(sites.items())],
            "boards": [{"employer": k, "system": (v[0] if isinstance(v, (list, tuple)) and v
                                                   else str(v))} for k, v in sorted(followed.items())],
            "boards_left_out": len(boards) - len(followed),
            "rules": rules, "pause": pause, "rev": ""}
    item["rev"] = rev_of({k: v for k, v in item.items() if k != "rev"})
    targets["search-settings"] = {"kind": "search", "rev": item["rev"]}
    return item


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
                   if reading.gate_state()["kind"] != "go" else
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
    the fortnightly rule, what the last held and what changed since the one before; the
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
        "every_days": export.EXPORT_EVERY_DAYS,
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
    pr = place.page_reads_record()
    book = ctx._once("book", lambda: {str(c.get("contact_id") or "").strip(): c
                                      for c in ctx.contacts})
    queue = []
    for q in reading.page_queue():
        cid = q["contact"]
        c = book.get(cid)
        if c is None:
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
    paused = reading.gate_state()["kind"] != "go"
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
    grouped = getattr(ctx, "by_contact", None)
    grouped = state.by_contact(ctx.threads) if grouped is None else grouped
    for cid, rows_ in grouped.items():
        if cid not in book:
            continue
        wrote = False
        for t in rows_:
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
              "replies": len(replied)}
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
                                     "replies": sum(1 for d in replied.values() if d and d >= since)},
              "funnel": [{"stage": "applied", "n": len(recent)}, {"stage": "interview", "n": r_iv},
                         {"stage": "offer", "n": r_of}]}
    weeks = []
    start = ctx.today - dt.timedelta(days=ctx.today.weekday())
    for k in range(7, -1, -1):
        lo = start - dt.timedelta(weeks=k)
        hi = lo + dt.timedelta(days=7)
        weeks.append({"week": _week(lo), "applied": sum(1 for _, d in sent if lo <= d < hi),
                      "replies": sum(1 for d in replied_on if lo <= d < hi)})
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
    return {"counts": counts, "funnel": funnel, "weeks": weeks, "applications": apps,
            "recent": window}


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
    ("prep_days", "Your next interview on the Brief", [["2", "From 2 days before"],
                                                        ["7", "From a week before"],
                                                        ["14", "From two weeks before"]]),
    ("calendar_reminder", "Calendar reminders", [["15", "15 minutes before"],
                                                 ["60", "An hour before"],
                                                 ["1440", "The day before"], ["off", "None"]]),
    # The brief's headline sent to the phone (tools/brief.py push_due): off unless the person
    # chose it, when the brief is set up or asked once after (profile_upgrades brief-push)
    # (the maintainer, 2026-11-04: "make it off by default but maybe part of the setup").
    ("brief_push", "Phone notification", [["off", "Off"], ["on", "On"]]),
)
SETTING_DEFAULTS = {"prep_days": "7", "calendar_reminder": "60", "brief_push": "off"}


# The person's own time zone (person.json `time_zone`), said in their words ("Toronto",
# "Eastern", "Mississauga") and read by person.zone_in: every time on the page, "today", and
# every calendar link use it. Never the brief's schedule zone (the audit, 2026-11-03).
TIME_ZONE = ("time_zone", "Your time zone")


def _settings(ctx: Ctx, targets: dict) -> list:
    values = setting_values()
    out = []
    for key, label, choices in SETTINGS:
        sid = f"setting-{key}"
        item = {"id": sid, "key": key, "label": label, "kind": "choice",
                "value": values[key], "choices": choices, "rev": rev_of(key, values[key])}
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
           "sections": sections, "watch": _watch(), "watch_again": _watch_again()}
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


def news_parts(line: str) -> dict:
    """A news point in its parts, so the page sets what happened, how to use it and where it
    is from apart: {what, use, src, date, url}, or {} for a line in another shape, shown as
    it is."""
    m = _NEWS_LINE.match(str(line or "").strip())
    if not m:
        return {}
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
    for row, rid in rows:
        if named(row.get("company")):
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


BUILDERS = {"app": _app, "person": _person, "needs_you": _needs_you, "jobs": _jobs,
            "ready": _ready, "messages": _messages, "due": _due, "people": _people,
            "interviews": _interviews, "done": _done, "settings": _settings, "brief": _brief,
            "setup": _setup, "updates": _updates, "applications": _applications,
            "referrals": _referrals, "message_budget": _message_budget,
            "linkedin": _linkedin, "learned": _learned, "help": _help, "resume": _resume,
            "search": _search, "where": _where, "listener": _listener,
            "schedule": _schedule, "you": _you, "upcoming": _upcoming}

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
                             "queue": [], "rev": "none"}},
    "learned": [], "help": {"tip": None, "tour": [], "off": False}, "resume": None,
    "search": None, "where": None, "schedule": None, "upcoming": [],
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
          only=None, shown: dict | None = None, full: dict | None = None) -> tuple[dict, dict]:
    """(the model, what each item id stands for in the repo). `only` builds just those
    sections, for an applier that needs one item's rev and not the whole page. `shown` is
    {suggestion id: the day it first showed} from the page's database, so at most three new
    suggestions reach the page a day (tools/app_alerts.py). `full`, a dict, is filled with
    every whole list (tools/app_lists.py) for `app.py view` to write to the database."""
    if today is None or now is None:
        t, n = clock()
        today, now = today or t, now or n
    ctx = Ctx(today, now)
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
        # Whether the page offers to pin itself now (app_listen.pin_due: never once pinned,
        # and a Not now is asked again a month later, three times at most).
        try:
            import app_listen
            model["pin"] = {"due": app_listen.pin_due(today)}
        except Exception:  # noqa: BLE001  no profile yet: nothing to offer
            model["pin"] = {"due": False}
        model["rev"] = model_rev(model)
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
