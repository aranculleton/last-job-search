#!/usr/bin/env python3
"""How fast browser reads go, every limit in one place, and the record that holds them.

A browser read is the person's own signed-in account loading a LinkedIn page. LinkedIn's
terms forbid automated access at any pace, and LinkedIn publishes no thresholds, so no pace
here is safe: each lowers the risk and none removes it. What this file adds is a way to
react to what actually happens instead of guessing a number once and making every run slow:

- **One dial**, PROFILE_READ_RISK in profile/networking.py: "careful" (the default, and the
  pace before the dial existed), "normal" or "fast". Every limit below takes its value from
  the preset, and a setting the person writes for one limit beats the preset. No preset
  but careful applies unless the person writes it.
- **Signals, not guesses.** Every page load is recorded with what it showed. A sign-in wall
  after signing in, a security check or CAPTCHA, an "unusual activity" banner or an HTTP 999
  page stops reads for the day at once (a hard signal). A page that does not render, or one
  that takes far longer to load than the person's own recent pages, is a soft signal: the
  next pause doubles, and a second soft signal within the hour stops the day. The friction
  log keeps every signal, dated, across days.
- **A ramp on clean history.** The pages-an-hour ceiling starts low and rises one step for
  each clean day of reading since the last signal (5, then the preset's next steps), never
  above the preset or the person's own setting.
- **Pages counted by kind.** A list page (the sent-invitations list, an employer's people,
  a people search) screens ten people in one load and is not the footprint of a profile
  page, so each kind has its own caps, and all loads together have one more.

Known and assumed, said plainly. Known: LinkedIn's terms; that LinkedIn shows the friction
above when it suspects automation; when this person's account saw it (the friction log).
Assumed: that a varied, human pace and fewer pages lower the chance of seeing it, and the
numbers in each preset, which are a judgement of how fast a person reads and writes, not a
measured safe rate.

The record (the ledger) is one per computer and repository, outside any one working folder,
so two chats in two worktrees on one machine share one count, one stop and one sign-in. The
same loads are also written beside the readings in documents/network, which a cloud session
commits, so the count survives a new container. Two cloud chats on two containers cannot
share a count while both run; their files merge afterwards.

    python3 tools/network/reading.py limits     # every limit, its value, where it came from
    python3 tools/network/reading.py friction   # the signals seen, and the ramp
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

PRESET_NAMES = ("careful", "normal", "fast")
DEFAULT_PRESET = "careful"

# Every limit: (what it controls, why, careful, normal, fast). The profile setting that
# overrides it is SETTING[name]. Careful is the pace of the release before the dial, value
# for value, so a person who never touches the dial reads exactly as fast as before.
LIMITS = {
    "reads_per_hour": (
        "profile pages read in any rolling hour",
        "the pace of someone reading a few profiles and writing each note by hand",
        8, 12, 20),
    "reads_per_day": (
        "profile pages read in a day, before the requests left today bind it lower",
        "a profile is read only for someone written to that day",
        15, 25, 40),
    "pages_per_hour": (
        "list pages (sent invitations, an employer's people, a people search) in an hour",
        "one list page screens about ten people, so few are needed",
        4, 6, 10),
    "pages_per_day": (
        "list pages in a day", "the same, over a day", 8, 12, 20),
    "loads_per_hour": (
        "all page loads together in an hour, profiles and list pages",
        "what LinkedIn sees is pages loaded, whatever they held; careful keeps the one shared "
        "cap there was before page kinds were counted apart",
        8, 16, 26),
    "loads_per_day": (
        "all page loads together in a day", "the same, over a day", 15, 30, 52),
    "gap_seconds": (
        "the pause between two pages, shortest and longest",
        "a steady machine rhythm is what automation checks look for, so the gap varies",
        (45, 240), (35, 200), (25, 150)),
    "gap_median": (
        "where most pauses sit, in seconds",
        "most gaps near a minute and a half at careful, as a person reads",
        90, 70, 55),
    "break_after": (
        "a longer break after this many pages, drawn again each time",
        "never on a fixed count, which a machine has and a person does not",
        (3, 7), (4, 8), (5, 10)),
    "break_minutes": (
        "the longer break, shortest and longest, in minutes",
        "a person stops to write or think", (5, 12), (4, 10), (3, 8)),
    "dwell_seconds": (
        "time on a profile read in full (deep), scrolled to the end at reading pace",
        "scrolling is also what makes LinkedIn fill in Experience and Activity",
        (20, 60), (15, 50), (12, 40)),
    "card_dwell_seconds": (
        "time on a profile read as its card only (top card and About, no scrolling)",
        "a card holds what most keep or skip decisions need, and nothing is scrolled",
        (20, 60), (10, 30), (8, 20)),
    "reads_per_run": (
        "the most people on one day's short list for profile reads",
        "it was 10, then 5 since 3.7.0: in one session five of seven profile reads went on "
        "facts a cheaper check had already shown (a request pending, a city elsewhere, a role "
        "outside their function), so the day's list is sized to the requests left today and "
        "this is only its ceiling",
        5, 10, 15),
    "unplaced": (
        "of those, the most nothing has placed in the person's city yet",
        "a place rules many out, and a list page places a dozen at once",
        2, 3, 4),
    "paste_top": (
        "how many profiles a paste is offered for, with no browser",
        "the best few, never everyone", 3, 5, 8),
    "fresh_days": (
        "how long a reading of someone stands before it is read again",
        "a profile is opened once; a month later it may have changed",
        30, 30, 45),
    "skip_spare": (
        "profile reads allowed beyond the requests left today",
        "for the people a read rules out", 3, 3, 4),
    "ramp": (
        "pages an hour allowed on each clean day of reading since the last signal",
        "start low and rise on clean history, never above the preset or the person's setting",
        (5, 8), (5, 10, 12), (5, 10, 20)),
}
# The profile/networking.py name for each limit. Three are older than the dial and keep
# their names; the rest are new and optional.
SETTING = {
    "reads_per_hour": "PROFILE_READS_PER_HOUR",
    "reads_per_day": "PROFILE_READS_PER_DAY",
    "pages_per_hour": "PROFILE_PAGES_PER_HOUR",
    "pages_per_day": "PROFILE_PAGES_PER_DAY",
    "loads_per_hour": "PROFILE_LOADS_PER_HOUR",
    "loads_per_day": "PROFILE_LOADS_PER_DAY",
    "gap_seconds": "PROFILE_READ_GAP_SECONDS",
    "gap_median": "PROFILE_READ_GAP_MEDIAN",
    "break_after": "PROFILE_READ_BREAK_AFTER",
    "break_minutes": "PROFILE_READ_BREAK_MINUTES",
    "dwell_seconds": "PROFILE_READ_DWELL_SECONDS",
    "card_dwell_seconds": "PROFILE_READ_CARD_DWELL_SECONDS",
    "reads_per_run": "PROFILE_READS_PER_RUN",
    "unplaced": "PROFILE_READ_UNPLACED",
    "paste_top": "PROFILE_PASTE_TOP",
    "fresh_days": "PROFILE_READ_FRESH_DAYS",
    "skip_spare": "PROFILE_READ_SKIP_SPARE",
    "ramp": "PROFILE_READ_RAMP",
}
_PAIRS = {"gap_seconds", "break_after", "break_minutes", "dwell_seconds", "card_dwell_seconds"}
# Each read written out, so tools/profile_names.py lists every one of them.
_MINE = {
    "reads_per_hour": lambda: getattr(_NET, "PROFILE_READS_PER_HOUR", None),
    "reads_per_day": lambda: getattr(_NET, "PROFILE_READS_PER_DAY", None),
    "pages_per_hour": lambda: getattr(_NET, "PROFILE_PAGES_PER_HOUR", None),
    "pages_per_day": lambda: getattr(_NET, "PROFILE_PAGES_PER_DAY", None),
    "loads_per_hour": lambda: getattr(_NET, "PROFILE_LOADS_PER_HOUR", None),
    "loads_per_day": lambda: getattr(_NET, "PROFILE_LOADS_PER_DAY", None),
    "gap_seconds": lambda: getattr(_NET, "PROFILE_READ_GAP_SECONDS", None),
    "gap_median": lambda: getattr(_NET, "PROFILE_READ_GAP_MEDIAN", None),
    "break_after": lambda: getattr(_NET, "PROFILE_READ_BREAK_AFTER", None),
    "break_minutes": lambda: getattr(_NET, "PROFILE_READ_BREAK_MINUTES", None),
    "dwell_seconds": lambda: getattr(_NET, "PROFILE_READ_DWELL_SECONDS", None),
    "card_dwell_seconds": lambda: getattr(_NET, "PROFILE_READ_CARD_DWELL_SECONDS", None),
    "reads_per_run": lambda: getattr(_NET, "PROFILE_READS_PER_RUN", None),
    "unplaced": lambda: getattr(_NET, "PROFILE_READ_UNPLACED", None),
    "paste_top": lambda: getattr(_NET, "PROFILE_PASTE_TOP", None),
    "fresh_days": lambda: getattr(_NET, "PROFILE_READ_FRESH_DAYS", None),
    "skip_spare": lambda: getattr(_NET, "PROFILE_READ_SKIP_SPARE", None),
    "ramp": lambda: getattr(_NET, "PROFILE_READ_RAMP", None),
}


def preset() -> str:
    """The person's dial, PROFILE_READ_RISK: careful unless they wrote another."""
    got = str(getattr(_NET, "PROFILE_READ_RISK", DEFAULT_PRESET) or DEFAULT_PRESET).strip().lower()
    return got if got in PRESET_NAMES else DEFAULT_PRESET


def _clean(name, value):
    """A setting the person wrote, in the shape its limit takes, or None when it cannot be
    read: a pair (shortest, longest), a ramp of steps, or a positive number."""
    try:
        if name in _PAIRS:
            lo, hi = (value, value) if isinstance(value, (int, float)) else tuple(value)[:2]
            lo, hi = float(lo), float(hi)
            if lo < 0 or hi < 0:
                return None
            lo, hi = min(lo, hi), max(lo, hi)
            return (lo, hi) if name == "break_minutes" else (int(lo), int(hi))
        if name == "ramp":
            steps = tuple(int(x) for x in value)
            return steps if steps and all(x > 0 for x in steps) else None
        n = int(value)
        return n if n > 0 else None
    except (TypeError, ValueError):
        return None


def value(name: str, risk: str | None = None):
    """The limit's value: the person's own setting, else the dial's preset."""
    what = LIMITS[name]
    risk = risk or preset()
    mine = _MINE[name]()
    got = _clean(name, mine) if mine is not None else None
    if got is not None:
        return got
    return what[2 + PRESET_NAMES.index(risk)]


def source(name: str) -> str:
    """Where a limit's value came from, said plainly."""
    mine = _MINE[name]()
    if mine is not None and _clean(name, mine) is not None:
        return "your setting, %s in profile/networking.py" % SETTING[name]
    if mine is not None:
        return "the %s preset (%s could not be read)" % (preset(), SETTING[name])
    return "the %s preset" % preset()


def report() -> list:
    """Every limit as one line: its value, where it came from, what it controls and why."""
    out = ["Reading pace: the %s preset (PROFILE_READ_RISK in profile/networking.py; one of %s)."
           % (preset(), ", ".join(PRESET_NAMES)),
           "No pace is safe: LinkedIn's terms forbid automated access and it publishes no "
           "thresholds. The numbers are a judgement of a person's pace, not a measured limit."]
    for name, (what, why, *_v) in LIMITS.items():
        out.append("- %s = %s (%s): %s. Why: %s." % (SETTING[name], value(name), source(name),
                                                     what, why))
    return out


# ------------------------------------------------------------------ the ledger

def _repo_key() -> str:
    """One key per repository, the same from every worktree of it: its origin's address,
    else its shared git directory."""
    root = os.path.dirname(os.path.dirname(_HERE))
    for args in (("config", "--get", "remote.origin.url"), ("rev-parse", "--git-common-dir")):
        try:
            r = subprocess.run(["git", "-C", root, *args], capture_output=True, text=True,
                               timeout=10)
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
    fh = open(os.path.join(ledger_dir(), ".lock"), "a+")
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


def put(key: str, value_) -> None:
    update(lambda d: d.__setitem__(key, value_))


# ------------------------------------------------------------------ friction

# A signal that ends the day's reads at once, and one that slows them first.
HARD = ("check", "signed_out", "unusual_activity", "http_999")
SOFT = ("not_rendering", "slow")
SOFT_STOPS = 2                  # soft signals within the hour that end the day
SOFT_WINDOW_MINUTES = 60
SLOW_FLOOR_SECONDS = 15         # never "slow" below this, however quick the rest were
SLOW_FACTOR = 3                 # a load this many times the person's own median is slow
SLOW_SAMPLE = 10


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


def soft_recent(now: datetime.datetime, data: dict | None = None) -> int:
    since = (now - datetime.timedelta(minutes=SOFT_WINDOW_MINUTES)).isoformat(timespec="seconds")
    return sum(1 for x in friction(data) if x["kind"] in SOFT and str(x.get("at")) >= since)


def slow(load_seconds: float, history: list) -> bool:
    """Is this load far slower than the person's own recent ones? Rising load times are one
    of the signals that come before a check."""
    past = [float(x) for x in history[-SLOW_SAMPLE:] if x is not None]
    if load_seconds < SLOW_FLOOR_SECONDS or len(past) < 3:
        return False
    return load_seconds > SLOW_FACTOR * statistics.median(past)


def clean_days(today: datetime.date, loads: list, data: dict | None = None) -> int:
    """Days with at least one page load and no signal, since the last day that had one. The
    ramp's step. `loads` are datetimes of every load on file."""
    signal_days = {str(x.get("at", ""))[:10] for x in friction(data)}
    days = sorted({d.date().isoformat() for d in loads if d.date() < today}, reverse=True)
    n = 0
    for day in days:
        if day in signal_days:
            break
        n += 1
    return n


def hourly_ceiling(today: datetime.date, loads: list, data: dict | None = None) -> tuple:
    """(pages an hour allowed now, why): the ramp's step for the clean days so far, never
    above loads_per_hour. A signal today puts the ramp back to its first step tomorrow."""
    steps = value("ramp")
    top = value("loads_per_hour")
    n = clean_days(today, loads, data)
    step = steps[min(n, len(steps) - 1)]
    if step >= top:
        return top, "loads_per_hour"
    return step, ("the ramp: %d clean day(s) of reading since the last signal, step %d of %d "
                  "(PROFILE_READ_RAMP %s)" % (n, min(n, len(steps) - 1) + 1, len(steps), steps))
