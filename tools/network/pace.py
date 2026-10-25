#!/usr/bin/env python3
"""LinkedIn's own signals, and the record that keeps them.

A browser read is the person's own signed-in account loading a LinkedIn page. LinkedIn's
terms forbid automated access at any pace and LinkedIn publishes no thresholds, so no pace
is safe, and none is imposed: since 2026-10-22 the app sets no limit of its own (no pages an
hour or a day, no pause between pages, no break, no slow start after a signal, no log of a
page loaded "early"). The maintainer's word: the waiting was most of a networking run, at
one page every two minutes, and only LinkedIn's real limits should stop a read.

What stops a read is LinkedIn itself, as soon as it shows it:

- **Hard signals** stop the day's reads at once: a security check or CAPTCHA, an "unusual
  activity" banner, an HTTP 999 page, or LinkedIn's sign-in page within `EXPIRY_HOURS` of the
  last page or sign-in (or a second sign-out in a day). A sign-in page on the first page of
  the day, or that long after the last, is a session that expired: a sign-in, no stop. A
  sign-out stop is the one the person may lift, once a day, after a clean sign-in
  (`reading.py resume`); the signal stays in the log, marked as they said.
- **A page that comes back nearly empty** is said, and a second within the hour stops the
  day: LinkedIn not serving the page is how a limit shows before a check does.
- **A slow load** is said and nothing more: far more often the person's own connection.

The record (the ledger) is one per computer and repository, outside any one working folder,
so two chats in two worktrees on one machine share one stop and one sign-in. The same loads
are also written beside the readings in documents/network, which a cloud session commits.

    python3 tools/network/reading.py friction   # the signals seen
"""

from __future__ import annotations

import contextlib
import datetime
import hashlib
import json
import os
import statistics
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (_HERE, os.path.dirname(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import person  # noqa: E402

_NET = person.module("networking") if person.exists("networking.py") else None


def _setting(value, default: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return n if n > 0 else default


# Not limits on pace: what the reading tools need to know, each the person's to set.
# Hours after the last page load from which LinkedIn's sign-in page is a session that expired,
# not a sign-out: a sign-in page the next morning, signed back into with no check, is how an
# expired session looks; one within minutes of a page is a signal and stops the day.
EXPIRY_HOURS = _setting(getattr(_NET, "PROFILE_SESSION_EXPIRY_HOURS", None), 4)
# How long a reading of someone stands before it is read again: a profile is opened once, and
# a month later it may have changed.
FRESH_DAYS = _setting(getattr(_NET, "PROFILE_READ_FRESH_DAYS", None), 30)
# With no browser, a paste is offered for the best few, never for everyone.
PASTE_TOP = _setting(getattr(_NET, "PROFILE_PASTE_TOP", None), 3)
# Of the people on a day's short list, the most that nothing has placed in the person's city
# yet: a place rules many out, and a list page places a dozen at once.
UNPLACED = _setting(getattr(_NET, "PROFILE_READ_UNPLACED", None), 10)

# The settings of the limits removed on 2026-10-22, read by nothing since. A profile that
# still holds one has them taken out (`reading.py retired-settings --apply`, the
# reading-limits-gone upgrade), unless the person's own recorded choice keeps it.
RETIRED = ("PROFILE_READ_RISK", "PROFILE_READS_PER_HOUR", "PROFILE_READS_PER_DAY",
           "PROFILE_PAGES_PER_HOUR", "PROFILE_PAGES_PER_DAY", "PROFILE_LOADS_PER_HOUR",
           "PROFILE_LOADS_PER_DAY", "PROFILE_READ_GAP_SECONDS", "PROFILE_READ_GAP_MEDIAN",
           "PROFILE_READ_BREAK_AFTER", "PROFILE_READ_BREAK_MINUTES",
           "PROFILE_READ_DWELL_SECONDS", "PROFILE_READ_CARD_DWELL_SECONDS",
           "PROFILE_READS_PER_RUN", "PROFILE_READ_SKIP_SPARE", "PROFILE_READ_RAMP",
           "CONNECTIONS_PER_WEEK")


# ------------------------------------------------------------------ the ledger

def _repo_key() -> str:
    """One key per repository, the same from every worktree of it: its origin's address,
    else its shared git directory."""
    root = os.path.dirname(os.path.dirname(_HERE))
    for args in (("config", "--get", "remote.origin.url"), ("rev-parse", "--git-common-dir")):
        try:
            r = subprocess.run(["git", "-C", root, *args], capture_output=True, text=True,
                               timeout=10, encoding="utf-8", errors="replace")
        except (OSError, subprocess.TimeoutExpired):
            continue
        got = r.stdout.strip()
        if r.returncode == 0 and got:
            if args[0] == "rev-parse":
                got = os.path.realpath(os.path.join(root, got))
            else:
                got = got.split("@")[-1].rstrip("/").lower()
                got = got[:-4] if got.endswith(".git") else got
            return hashlib.sha1(got.encode("utf-8")).hexdigest()[:12]
    return hashlib.sha1(os.path.realpath(root).encode("utf-8")).hexdigest()[:12]


def _cache_root() -> str:
    if sys.platform == "darwin":
        return os.path.expanduser("~/Library/Caches")
    if os.name == "nt":
        return os.environ.get("LOCALAPPDATA") or os.path.expanduser("~\\AppData\\Local")
    return os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")


def ledger_dir() -> str:
    """Where this computer keeps the reading ledger for this repository. LJS_LEDGER moves it;
    a run pointed at its own state (LJS_STATE, which is how the app's tests run) keeps it
    there, so a test never touches a real ledger."""
    if os.environ.get("LJS_LEDGER"):
        return os.environ["LJS_LEDGER"]
    if os.environ.get(person.STATE_ENV):
        return person.state(".ledger")
    return os.path.join(_cache_root(), "last-job-search", _repo_key())


def _path() -> str:
    return os.path.join(ledger_dir(), "reading-ledger.json")


@contextlib.contextmanager
def _locked():
    """Hold the ledger while it is read and written, so two chats on one computer never
    lose each other's records."""
    os.makedirs(ledger_dir(), exist_ok=True)
    fh = open(os.path.join(ledger_dir(), ".lock"), "a+", encoding="utf-8")
    try:
        try:
            import fcntl
            fcntl.flock(fh, fcntl.LOCK_EX)
        except ImportError:                      # Windows
            try:
                import msvcrt
                msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
            except (ImportError, OSError):
                pass
        yield
    finally:
        fh.close()


def load() -> dict:
    try:
        with open(_path(), encoding="utf-8") as fh:
            got = json.load(fh)
    except (OSError, ValueError):
        return {}
    return got if isinstance(got, dict) else {}


def _save(data: dict) -> None:
    tmp = _path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1)
        fh.write("\n")
    os.replace(tmp, _path())


KEEP_DAYS = 45


def update(fn) -> dict:
    """Apply fn(data) to the ledger under its lock, drop what is too old to count, save,
    and return it. A ledger that cannot be written is said once and skipped: the files
    beside the readings still hold the count."""
    try:
        with _locked():
            data = load()
            fn(data)
            cut = (datetime.date.today() - datetime.timedelta(days=KEEP_DAYS)).isoformat()
            data["loads"] = [x for x in data.get("loads") or [] if str(x.get("at", ""))[:10] >= cut]
            data["friction"] = [x for x in data.get("friction") or []
                                if str(x.get("at", ""))[:10] >= cut]
            data.pop("breaches", None)     # the pace breaches of an older version
            _save(data)
            return data
    except OSError as e:
        print("reading: the pace ledger in %s could not be written (%s); the count beside the "
              "readings still holds" % (ledger_dir(), e), file=sys.stderr)
        return {}


def add_load(kind: str, at: str, gap: float, brk: bool, ident: str = "",
             load_seconds: float | None = None) -> None:
    rec = {"kind": kind, "at": at, "next_gap": gap, "break": bool(brk), "id": ident}
    if load_seconds is not None:
        rec["load_seconds"] = float(load_seconds)
    update(lambda d: d.setdefault("loads", []).append(rec))


def put(key: str, value_) -> bool:
    """Set one key; False when the ledger could not be written."""
    return bool(update(lambda d: d.__setitem__(key, value_)))


# ------------------------------------------------------------------ friction

# A signal that ends the day's reads at once, and one that slows them first.
HARD = ("check", "signed_out", "unusual_activity", "http_999", "other")
SOFT = ("not_rendering", "slow")
SOFT_STOPS = 2                  # pages that did not render, within the hour, that end the day
# A slow load is said and does nothing more: it never ends the day.
SOFT_STOP_KINDS = ("not_rendering",)
SOFT_WINDOW_MINUTES = 60
SLOW_FLOOR_SECONDS = 15         # never "slow" below this, however quick the rest were
SLOW_FACTOR = 3                 # a load this many times the person's own median is slow
SLOW_SAMPLE = 10


def confirm_benign(kind: str, day: str, why: str, now: datetime.datetime | None = None) -> bool:
    """The person's word that the day's last signal of this kind was benign: it stays in the
    log, marked. True when one was found."""
    found = []

    def mark(d):
        rows = [x for x in d.get("friction") or [] if isinstance(x, dict)
                and x.get("kind") == kind and str(x.get("at", ""))[:10] == day]
        if rows:
            rows[-1]["benign"] = "person confirmed benign: " + " ".join(str(why).split())[:200]
            rows[-1]["confirmed_at"] = (now or datetime.datetime.now()).isoformat(timespec="seconds")
            found.append(rows[-1])
    update(mark)
    return bool(found)


def record_friction(kind: str, words: str = "", now: datetime.datetime | None = None) -> dict:
    """Keep one signal, dated, in the friction log."""
    if kind not in HARD + SOFT:
        raise ValueError("a signal is one of %s, not %r" % (", ".join(HARD + SOFT), kind))
    rec = {"at": (now or datetime.datetime.now()).isoformat(timespec="seconds"), "kind": kind,
           "words": " ".join(str(words or "").split())[:200]}
    update(lambda d: d.setdefault("friction", []).append(rec))
    return rec


def friction(data: dict | None = None) -> list:
    return [x for x in (load() if data is None else data).get("friction") or []
            if isinstance(x, dict) and x.get("kind")]


SAID = {"check": "a security check", "signed_out": "a sign-in page", "other": "a stop",
        "unusual_activity": "an unusual-activity notice", "http_999": "an HTTP 999 page",
        "not_rendering": "a page that came back nearly empty", "slow": "a slow page load"}
# A stop whose words name none of the kinds above ("other") is said in those words.
OTHER_SAID_CHARS = 80


def said(rec: dict) -> str:
    """One friction record as what happened, with its day: "a sign-in page on 20 Oct"."""
    day = str(rec.get("at") or "")[:10]
    try:
        when = datetime.date.fromisoformat(day).strftime("%d %b").lstrip("0")
    except ValueError:
        when = day or "an unknown day"
    if rec.get("kind") == "other" and str(rec.get("words") or "").strip():
        words = " ".join(str(rec["words"]).split())
        words = words if len(words) <= OTHER_SAID_CHARS else \
            words[:OTHER_SAID_CHARS - 3].rstrip() + "..."
        return f"\"{words}\" on {when}"
    return f"{SAID.get(rec.get('kind'), str(rec.get('kind') or 'something'))} on {when}"


def soft_recent(now: datetime.datetime, data: dict | None = None, kinds=SOFT) -> int:
    since = (now - datetime.timedelta(minutes=SOFT_WINDOW_MINUTES)).isoformat(timespec="seconds")
    return sum(1 for x in friction(data) if x["kind"] in kinds and str(x.get("at")) >= since)


def slow(load_seconds: float, history: list) -> bool:
    """Is this load far slower than the person's own recent ones? Rising load times are one
    of the signals that come before a check."""
    past = [float(x) for x in history[-SLOW_SAMPLE:] if x is not None]
    if load_seconds < SLOW_FLOOR_SECONDS or len(past) < 3:
        return False
    return load_seconds > SLOW_FACTOR * statistics.median(past)
