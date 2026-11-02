#!/usr/bin/env python3
"""The brief, gathered by code in one command, so a scheduled run reads it once.

Everything the morning brief says comes from the state files: what is due today and
overdue (both halves of `open_actions.py --due`), the replies owed, the application nudges
with who they go to, the follow-ups drafted by code (`tools/followup_drafts.py`, through
compose's gate), the counts since the last brief, where the search is, three things to do
before the next one, the LinkedIn download and own-profile reminders, an update waiting,
and the news searches to run. The model's part of a run is the news and the message.

    python3 tools/brief.py                     # the brief, as text for a chat (its message under 2,500 characters)
    python3 tools/brief.py --write             # also the day's upkeep and records (below)
    python3 tools/brief.py --start --on "<model>" --write   # a scheduled run's whole start
    python3 tools/brief.py --write --page-applied           # after the page's ticks are applied
    python3 tools/brief.py news < items.txt    # the news reader's items, into today's record

--write does what the brief has always done to the state: closes the applications gone
quiet (`followups.py --close-quiet`), rebuilds the call preps gone stale (`prep.py
--stale-only`), writes the follow-up pack (documents/network/followup_pack_<today>.md) and
the brief's own record (documents/briefs/<today>.md), and takes the tip line. Without it,
nothing is written.

--start is a scheduled run's first step, so the model makes one call where it made four:
the day's update check (`sync_app.py --if-stale`), the container's Python side
(`setup_env.sh --python`) and the earlier runs' unsaved work, all run here with their
output kept in a file; then the brief is gathered by a fresh process, so an update the
sync just took is the code that runs. What the sync printed reaches the brief as lines
already decided: an update waiting (said once: left out when the last brief said it),
job sites blocked, upgrades to run, questions for the end. Nothing is pasted twice.

Where the person has a page (profile/app.json `url`), the brief is the page's too. What
they ticked there changes what is owed, so `--start` stops before gathering and prints the
steps that apply those ticks first (`app.py apply`, code alone); `--page-applied` then
gathers. The message links the page's To do rather than a file on GitHub, its questions are
on the page as To do cards, and the run brings the page up to date (`app.py view`) after it
lands. It runs in the chat that answers the page (tools/app_listen.py), so it never
publishes the page again and never starts a watch: `app.py view` is all it sends. A break the person took (`routines.py pause`) holds the brief: a run
during it says so in one line, and the run on the day it ends lifts it.

Plain Python, standard library, no network of its own (the sync in --start fetches). The
same state files and --today always print the same text.
"""

from __future__ import annotations

import argparse
import datetime as dt
import glob
import hashlib
import json
import os
import re
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (_HERE, os.path.join(_HERE, "network")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import person                                         # noqa: E402
import local_path  # noqa: E402
from company_key import key as company_key            # noqa: E402

ROOT = os.path.dirname(_HERE)
BRIEFS = ("documents", "briefs")
TEXT_MAX = 2500
RECORD_OWED = 30       # the record lists this many owed; the pack holds every one
NEWS_MAX = 5           # in the record; the message carries at most three
MESSAGE_NEWS = 3
QUERIES_MAX = 6
# The news is never empty (the maintainer, 2026-11-02, after a brief said "Quiet week": "it
# should never say nothing new or some random useless placeholder"). A thin day widens inside
# the one reader call: the wider searches below, back a week and then a month, never a link
# sent before, up to SEARCHES_MAX searches in all; a reader that brought nothing carries the
# last items forward with their day, so the page's News panel is always drawn.
SEARCHES_MAX = 8
NEWS_MIN = 3
WIDEN_DAYS = (7, 28)
CARRY_DAYS = 28
IN_PLAY_MAX = 6
# The person's own settings for the brief (person.json `brief`, set from the page's Edit the
# brief panel): how many owed items the message lists (B1), how many news items (B2), what its
# news watches (`watch`: B3 takes one off, B6 and B7 add one), and which parts it shows (B5,
# never Owed). The employers in play are searched first unless `leave_out` names them.
LENGTHS = {"short": 2, "standard": 4, "long": 6}
NEWS_CHOICES = (0, 1, 3, 5)
NEWS_GROUPS = ("employers",)
PARTS = ("since", "next_three", "tip")
# How often a watched thing is searched: as often as it changes, in days since it was last
# searched. A brief that missed a day, or had no room for it, searches it at the next.
EVERY = {"day": 1, "week": 7, "month": 28}
WATCH_MAX = 8            # what the list holds; a brief runs at most QUERIES_MAX searches
WATCH_LEN = 80
WATCHED = ("documents", "briefs", "watched.json")   # when each was last searched


def setting(name: str):
    """One of the person's brief settings, checked; the app's default when unset or unknown."""
    got = person.get(f"brief.{name}", None)
    if name == "length":
        return got if got in LENGTHS else "standard"
    if name == "news":
        return got if got in NEWS_CHOICES else MESSAGE_NEWS
    if name == "leave_out":
        return [g for g in (got or []) if g in NEWS_GROUPS]
    if name == "hide":
        return [p for p in (got or []) if p in PARTS]
    return got
QUIET_DAYS = 14        # nothing sent for this long: "little going out" leads
UNCONFIRMED_DAYS = (7, 45)   # drafted this long and not marked sent: ask whether it went
DEFAULT_SINCE_DAYS = 7
SYNC_LOG = "ljs-brief-sync.txt"
NEWS_HOLD = re.compile(r"\b(?:lay ?offs?|laid off|job cuts|cuts? \d+|hiring freeze|freez\w*|"
                       r"restructur\w*|redundanc\w*|shut\w* down|closing|closure)\b", re.I)
_LINK = re.compile(r"https?://[^\s)>\]]+")
_DATE_IN = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")

WHAT_COUNTS = ("employers the person is in process with or has a live thread at, first; then "
               "what they asked the brief to watch, in the order they gave")


# ---------------------------------------------------------------- reading the state

def _today(value=None) -> dt.date:
    return dt.date.fromisoformat(value) if value else dt.date.today()


def _d(value):
    m = _DATE_IN.search(str(value or ""))
    try:
        return dt.date.fromisoformat(m.group(1)) if m else None
    except ValueError:
        return None


def brief_path(day: str) -> str:
    return person.state(*BRIEFS, "%s.md" % day)


def earlier_briefs(today: dt.date) -> list[str]:
    """The brief records before today, oldest first."""
    out = []
    for p in glob.glob(person.state(*BRIEFS, "*.md")):
        d = _d(os.path.basename(p))
        if d and d < today and os.path.basename(p) == "%s.md" % d.isoformat():
            out.append(p)
    return sorted(out)


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def first_name(name) -> str:
    try:
        import tone
        return tone.greeting_name(name) or str(name or "")
    except Exception:
        return str(name or "").split(" ")[0]


def _status(row) -> str:
    return str(row.get("status") or "").strip().lower()


def counts_since(tracker, threads, since: dt.date, today: dt.date) -> dict:
    """What happened between the last brief and today, from the tracker and the message log."""
    import open_actions
    import throttle
    from network import state

    def inside(d):
        return d is not None and since < d <= today

    sent = sum(1 for r in tracker if _status(r) and _status(r) not in throttle.UNSENT
               and not throttle.is_process(r) and inside(_d(throttle.applied_on(r))))
    replies = sum(1 for r in threads if state._direction(r) == "in" and state.said_something(r)
                  and not state.is_auto_reply(r) and inside(_d(r.get("date"))))
    interviews = 0
    for r in tracker:
        if _status(r) in throttle.FINAL and _status(r) != "rejected" or _status(r) in throttle.UNSENT:
            continue
        _f, _files, stages = open_actions._stages(r)
        interviews += sum(1 for st in stages if inside(_d(st.get("date"))))

    def last_word(r):
        days = [d for d in (_d(x) for x in _DATE_IN.findall(str(r.get("notes") or "")))
                if d and d <= today]
        days.append(_d(throttle.applied_on(r)))
        days = [d for d in days if d]
        return max(days) if days else None

    offers = sum(1 for r in tracker if "offer" in _status(r) and inside(last_word(r)))
    rejections = sum(1 for r in tracker if _status(r) == "rejected" and inside(last_word(r)))
    return {"sent": sent, "replies": replies, "interviews": interviews, "offers": offers,
            "rejections": rejections}


def live_counts(tracker) -> dict:
    import throttle
    live = set(throttle.LIVE_PROCESS)
    processes = [r for r in tracker if _status(r) in live]
    apps = [r for r in tracker if (_status(r) == "applied" or _status(r) in live)
            and not throttle.is_process(r)]
    return {"applications": len(apps), "interviews": len(processes), "processes": processes}


def next_stage(row, today: dt.date) -> dict:
    import open_actions
    _f, _files, stages = open_actions._stages(row)
    ahead = [st for st in stages if not st.get("done") and _d(st.get("date"))
             and _d(st.get("date")) >= today]
    return min(ahead, key=lambda st: st["date"]) if ahead else {}


def unconfirmed(tracker, today: dt.date) -> list[dict]:
    """Drafted between 7 and 45 days ago and never marked sent or not sent."""
    import throttle
    lo, hi = UNCONFIRMED_DAYS
    out = []
    for r in tracker:
        if _status(r) not in throttle.UNSENT or str(r.get("confirmed_by") or "").strip():
            continue
        d = _d(r.get("date"))
        if d and lo < (today - d).days <= hi:
            out.append(r)
    return sorted(out, key=lambda r: r.get("date") or "")


# ---------------------------------------------------------------- the news searches

def _section(text: str, heading: str) -> str:
    """The body of the markdown section whose heading contains `heading`, or ""."""
    m = re.search(r"^(#{2,4})\s+[^\n]*" + re.escape(heading) + r"[^\n]*\n", text, re.M | re.I)
    if not m:
        return ""
    level = len(m.group(1))
    rest = text[m.end():]
    end = re.search(r"^#{2,%d}\s" % level, rest, re.M)
    return rest[:end.start()] if end else rest


def what_counts(claude_md: str, watch: list[dict] | None = None) -> str:
    """For the news reader: the person's own "what counts" line where their profile has one,
    else the app's, naming what they watch in their own words."""
    body = _section(claude_md, "This search's automation")
    for line in body.splitlines():
        if re.search(r"what counts", line, re.I):
            return re.sub(r"\*\*", "", line.lstrip("- ")).strip()[:600]
    whats = [w["what"] for w in (watch or [])]
    return WHAT_COUNTS + (": " + "; ".join(whats) if whats else "")


def _profile_text(name: str) -> str:
    try:
        return person.text(name)
    except Exception:
        return ""


def _net(attr: str, default=""):
    try:
        return getattr(person.module("networking"), attr, default) or default
    except Exception:
        return default


def _market(code: str) -> dict:
    """The person's country's market table (tools/markets/<cc>.json), or {}."""
    try:
        import markets
        return markets.countries().get(str(code or "").lower()) or {}
    except Exception:  # noqa: BLE001  no table for that country: the search goes without
        return {}


def news_language(code: str) -> str:
    """The language the person's market reads its news in, as its code ("fr"), where it is
    not English: "". The news reader knows the codes, so no table of names is kept here."""
    langs = [str(x) for x in (_market(code).get("languages") or [])]
    return "" if not langs or "en" in langs[:1] else langs[0]


# ---------------------------------------------------------------- what the news watches

def _clean_what(text) -> str:
    return " ".join(str(text or "").split())[:WATCH_LEN].strip(" .;,")


def watch_list(raw=None) -> list[dict]:
    """What the person's brief watches, in their order, each {what, every} and "by": "you"
    where they added it themselves: person.json `brief.watch`, written by Claude from their
    profile (`brief.py watch write`) and changed on their page. Checked, never guessed: an
    item with no words is dropped, an unknown "every" is a week."""
    got = person.get("brief.watch", None) if raw is None else raw
    out, seen = [], set()
    for x in got if isinstance(got, list) else []:
        x = {"what": x} if isinstance(x, str) else x
        if not isinstance(x, dict):
            continue
        what = _clean_what(x.get("what"))
        if not what or what.lower() in seen:
            continue
        seen.add(what.lower())
        item = {"what": what, "every": x.get("every") if x.get("every") in EVERY else "week"}
        if x.get("by") == "you":
            item["by"] = "you"
        out.append(item)
    return out[:WATCH_MAX]


def dropped() -> list[str]:
    """What the person took off their watch list: Claude never writes it back."""
    got = person.get("brief.watch_dropped", None)
    return [_clean_what(x) for x in got if _clean_what(x)] if isinstance(got, list) else []


def watch_basis(claude_md: str | None = None) -> str:
    """A fingerprint of what the watch list is written from: the person's place, their right
    to work and the rest of Identity, and what they are after (Target Sectors). When it moves,
    the list is written again; the person's own items and what they took off stay as they are."""
    md = _profile_text("CLAUDE.md") if claude_md is None else claude_md
    parts = [str(person.country() or ""), str(person.get("identity.location", "") or ""),
             _section(md, "Identity"), _section(md, "Target Sectors")]
    return hashlib.md5("\n".join(" ".join(p.split()) for p in parts).encode("utf-8")).hexdigest()[:12]


# What 4.6's fixed kinds the person turned off (person.json brief.leave_out), in words: a list
# written for them leaves these out, as they asked then.
OLD_KINDS = {"market": "hiring and layoffs near them", "bank": "interest rate decisions",
             "targets": "news of their target employers"}


def turned_off_before() -> list[str]:
    got = person.get("brief.leave_out", None)
    return [OLD_KINDS[g] for g in (got if isinstance(got, list) else []) if g in OLD_KINDS]


def watch_needs_writing(claude_md: str | None = None) -> str:
    """Why the watch list should be written now, or "": never written, or written from a
    profile that has changed since."""
    if not person.exists():
        return ""
    stamp = person.get("brief.watch_from", None)
    if not stamp:
        # Claude's own list was never written, whatever the person added themselves first.
        return "none written yet"
    if stamp != watch_basis(claude_md):
        return "the profile changed since it was written"
    return ""


def write_watch(items: list, by_person: bool = False) -> list[dict]:
    """Claude's list, from the profile: it replaces Claude's earlier items, keeps every one the
    person added, and leaves out whatever they took off. With `by_person`, the items are the
    person's own (said in a chat), added to the list as it is."""
    import profile_set
    off = {x.lower() for x in dropped()}
    now = watch_list()
    mine = [w for w in now if w.get("by") == "you"]
    if by_person:
        # Their own word wins over a stop they gave before: it is watched again.
        new = [dict(w, by="you") for w in watch_list(items)]
        have = {x["what"].lower() for x in now}
        add = [w for w in new if w["what"].lower() not in have]
        if len(now) + len(add) > WATCH_MAX:
            raise ValueError("the brief watches %d things already: stop one first" % WATCH_MAX)
        kept = now + add
        back = {w["what"].lower() for w in new}
        if back & off:
            profile_set.set_json("brief.watch_dropped", [x for x in dropped() if x.lower() not in back])
    else:
        new = [w for w in watch_list(items) if w["what"].lower() not in off]
        kept = mine + [w for w in new if w["what"].lower() not in {x["what"].lower() for x in mine}]
    kept = watch_list(kept)
    profile_set.set_json("brief.watch", kept)
    if not by_person:
        profile_set.set_json("brief.watch_from", watch_basis())
    person.reset()
    return kept


def drop_watch(what: str) -> bool:
    """One item off the list, by its words, and remembered as taken off."""
    import profile_set
    want = _clean_what(what).lower()
    now = watch_list()
    left = [w for w in now if w["what"].lower() != want]
    if len(left) == len(now):
        return False
    profile_set.set_json("brief.watch", left)
    profile_set.set_json("brief.watch_dropped", list(dict.fromkeys(dropped() + [_clean_what(what)])))
    person.reset()
    return True


def _watched_path() -> str:
    return person.state(*WATCHED)


def _watched_file() -> dict:
    try:
        with open(_watched_path(), encoding="utf-8") as fh:
            got = json.load(fh)
    except (OSError, ValueError):
        return {}
    return got if isinstance(got, dict) else {}


def _save_watched(got: dict) -> None:
    path = _watched_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(dict(sorted(got.items())), fh, indent=1, ensure_ascii=False)
        fh.write("\n")


def last_searched() -> dict:
    """{what (lower case): the day it was last searched}, from the brief's own record."""
    return {str(k).lower(): _d(v) for k, v in _watched_file().items()
            if not str(k).startswith("_") and _d(v)}


def plan_searched(whats: list[str], today: dt.date) -> None:
    """The watched things today's searches carry, kept until the news step says they ran
    (`brief.py news`): marked searched at the gather, a search the run never made, or one a
    rewritten list replaced, waited a week or a month for nothing."""
    got = _watched_file()
    got["_planned"] = {"day": today.isoformat(), "whats": list(whats)}
    _save_watched(got)


def note_searched(whats: list[str] | None, today: dt.date) -> None:
    """The day each watched thing was searched, so the next brief knows what is due: those
    given, or (None) today's planned ones, once the news reader has run them."""
    got = _watched_file()
    plan = got.pop("_planned", None) or {}
    if whats is None:
        whats = plan.get("whats") or [] if plan.get("day") == today.isoformat() else []
    for w in whats:
        got[str(w).lower()] = today.isoformat()
    _save_watched(got)


def due_watch(today: dt.date, watch: list[dict] | None = None,
              searched: dict | None = None) -> list[dict]:
    """The watched things this brief searches, in the person's order: each whose days since it
    was last searched have reached how often it changes, or that was never searched."""
    watch = watch_list() if watch is None else watch
    searched = last_searched() if searched is None else searched
    out = []
    for n, w in enumerate(watch):
        last = searched.get(w["what"].lower())
        if last is None or (today - last).days >= EVERY[w["every"]]:
            out.append((last or dt.date.min, n, w))
    # The longest waiting first, the person's order between equals: a brief with no room for
    # one leaves it the oldest, so the next brief takes it (the release review: a daily item
    # early in the list took every slot, and a monthly one later in it never ran).
    return [w for _l, _n, w in sorted(out, key=lambda x: (x[0], x[1]))]


def home_place() -> str:
    """Where the person's employer news is placed, in their own words: the last part of their
    location ("Toronto, ON, Canada" gives "Canada"), so a common name finds its local news."""
    loc = str(person.get("identity.location", "") or "")
    return loc.split(",")[-1].strip()[:40] if "," in loc else ""


def queries(today: dt.date, live_employers: list[str], watch: list[dict] | None = None,
            searched: dict | None = None) -> list[str]:
    """At most six searches: the employers in play (two at most), then what the person's brief
    watches that is due today, in their own words and their order. Nothing else: no kind of
    news is decided here for anyone, and what matters to a nurse, a lawyer or a student on a
    visa is what their own list says (person.json `brief.watch`)."""
    month = today.strftime("%B %Y")
    off = set(setting("leave_out"))
    where = home_place()
    out = ["%s%s news %s" % (n, " " + where if where else "", month)
           for n in live_employers[:2]] if "employers" not in off else []
    for w in due_watch(today, watch, searched):
        out.append("%s %s" % (w["what"], month))
    return list(dict.fromkeys(out))[:QUERIES_MAX]


def wider(today: dt.date, live_employers: list[str], watch: list[dict] | None = None,
          qs: list[str] | None = None) -> list[str]:
    """The searches the news reader widens with when today's bring fewer than NEWS_MIN items
    not sent before, each with no month, so last week's and last month's news is found (a
    "November 2026" search on the 2nd finds almost nothing): what the person's list watches
    that today's searches leave out first, as a new subject brings new items, then the
    employers in play, then the rest of the list. Only as many as keep the reader within
    SEARCHES_MAX."""
    watch = watch_list() if watch is None else watch
    qs = list(qs or [])
    room = SEARCHES_MAX - len(qs)
    if room <= 0 or not qs:
        return []
    month = today.strftime("%B %Y")
    due = {w["what"] for w in watch if "%s %s" % (w["what"], month) in qs}
    where = home_place()
    out = [w["what"] for w in watch if w["what"] not in due]
    if "employers" not in set(setting("leave_out")):
        out += ["%s%s news" % (n, " " + where if where else "") for n in live_employers[:2]]
    out += [w["what"] for w in watch if w["what"] in due]
    return [q for q in dict.fromkeys(out) if q not in qs][:room]


def in_play(tracker, contacts, threads, live_employers: list[str]) -> list[str]:
    """How the person is in touch with each employer in play, so each news item can say how to
    use it (a talking point for a call, a question for an interview, a reason to write): the
    stage and the first names of the people they talk to there. For the reader's use lines
    only, never searched (its own file says so)."""
    import throttle
    stage, names = {}, {}
    for r in tracker:
        k, st = company_key(r.get("company") or ""), _status(r)
        if k and st in set(throttle.LIVE_PROCESS) and k not in stage:
            stage[k] = "interviewing" if "interview" in st else st.replace("_", " ")
        elif k and st == "applied" and k not in stage:
            stage[k] = "applied"
    for w in _warm_routes(contacts, threads):
        k, first = company_key(w["company"]), first_name(w["name"])
        if k and first and first not in names.setdefault(k, []):
            names[k].append(first)
    out = []
    for n in live_employers[:IN_PLAY_MAX]:
        k = company_key(n)
        bits = ([stage[k]] if k in stage else []) + (
            ["talking to " + " and ".join(names[k][:2])] if names.get(k) else [])
        out.append("%s (%s)" % (n, ", ".join(bits)) if bits else n)
    return out


def searched_whats(qs: list[str], watch: list[dict], today: dt.date) -> list[str]:
    """Which watched things the searches handed on carry, to note them as searched."""
    month = today.strftime("%B %Y")
    return [w["what"] for w in watch if "%s %s" % (w["what"], month) in qs]


def links_sent(paths: list[str]) -> list[str]:
    """Every link the news sections of the last two briefs carried, so none is sent twice."""
    out = []
    for p in paths[-2:]:
        out += _LINK.findall(_section(_read(p), "News"))
    return list(dict.fromkeys(u.rstrip(".,;") for u in out))


# ---------------------------------------------------------------- the sync's output

def _git_dir() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "--absolute-git-dir"], cwd=ROOT, text=True,
                           capture_output=True, timeout=10, encoding="utf-8", errors="replace")
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    import tempfile
    return tempfile.gettempdir()


def sync_log_path() -> str:
    return os.environ.get("LJS_BRIEF_SYNC") or os.path.join(_git_dir(), SYNC_LOG)


def read_sync(today: dt.date, path: str | None = None) -> dict:
    """What today's start printed, decided into lines: {} when it did not run today."""
    text = _read(path or sync_log_path())
    if not text.startswith("date: %s\n" % today.isoformat()):
        return {}
    head, _, out = text.partition("\n---\n")
    meta = dict(ln.split(": ", 1) for ln in head.splitlines() if ": " in ln)
    lines = out.splitlines()
    got = {"exit": int(meta.get("exit", "0") or 0), "earlier": [b for b in meta.get("earlier", "").split() if b],
           "setup": meta.get("setup", ""), "update": "", "blocked": [], "changed": [],
           "upgrades": [], "questions": [], "first": "", "for_claude": []}
    for i, ln in enumerate(lines):
        s = ln.strip()
        if s.startswith("An update is waiting:"):
            got["update"] = s
        elif s.startswith("Job sites blocked"):
            for nxt in lines[i + 1:]:
                if not nxt.startswith("  "):
                    break
                got["blocked"].append(nxt.strip())
        elif s.startswith("What changed"):
            for nxt in lines[i + 1:]:
                if not nxt.startswith("  - "):
                    break
                got["changed"].append(nxt[4:].strip())
    for i, ln in enumerate(lines):
        # What the sync says to Claude alone: their own tests an update broke (bringing them
        # in line is this run's job), and a CLAUDE.md that changed under a chat kept open.
        if ln.startswith("Claude, not for the person:"):
            more = [x.strip() for x in lines[i + 1:i + 6] if x.startswith("  ")]
            got["for_claude"].append(" ".join([ln.split(":", 1)[1].strip()] + more)[:400])
        elif ln.startswith("Claude: ") and " changed. " in ln:
            got["for_claude"].append(ln[len("Claude: "):].split(". ", 1)[0] + ": read it again "
                                     "before any work beyond this brief in this chat")
    mode = ""
    for ln in lines:
        s = ln.strip()
        if s.startswith("Claude applies these itself"):
            mode = "alone"
        elif s.startswith("These need you"):
            mode = "you"
        elif s.startswith("- ") and mode:
            got["upgrades" if mode == "alone" else "questions"].append(s[2:])
        elif mode and not s.startswith("(asked again"):
            mode = ""
    if got["exit"]:
        got["first"] = next((ln.strip() for ln in lines if ln.strip()
                             and not ln.startswith("note:")), "")
    return got


def start(argv: list[str], model: str) -> int:
    """The scheduled run's start: the update check, the Python side, the earlier runs' work,
    all kept in one file; then the brief, gathered by a fresh process."""
    today = dt.date.today()
    py = sys.executable
    r = subprocess.run([py, os.path.join(_HERE, "sync_app.py"), "--if-stale", "--on", model],
                       cwd=ROOT, text=True, capture_output=True, encoding="utf-8",
                       errors="replace")
    setup = ""
    script = os.path.join(_HERE, "setup_env.sh")
    if os.name == "posix" and os.path.isfile(script):
        s = subprocess.run(["bash", script, "--python"], cwd=ROOT, text=True,
                           capture_output=True, encoding="utf-8", errors="replace")
        if s.returncode:
            setup = ((s.stderr or s.stdout or "").strip().splitlines() or ["failed"])[-1][:200]
    earlier = subprocess.run(["git", "branch", "-r", "--no-merged", "origin/master", "--list",
                              "origin/claude/ops-*"], cwd=ROOT, text=True, capture_output=True,
                             encoding="utf-8", errors="replace")
    branches = " ".join(b.strip() for b in (earlier.stdout or "").splitlines() if b.strip())
    with open(sync_log_path(), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("date: %s\nexit: %d\nearlier: %s\nsetup: %s\n---\n%s%s"
                 % (today.isoformat(), r.returncode, branches, setup, r.stdout or "",
                    r.stderr or ""))
    url = page_url()
    if url and "--page-applied" not in argv:
        sys.stdout.write(page_first(url, argv))
        return 0
    return subprocess.run([py, os.path.abspath(__file__)] + argv, cwd=ROOT).returncode


def page_url() -> str:
    """The person's page (profile/app.json `url`), or "" when none is published."""
    try:
        with open(person.path("app.json"), encoding="utf-8") as fh:
            got = json.load(fh)
    except (person.NoProfile, OSError, ValueError):
        return ""
    url = str(got.get("url") or "") if isinstance(got, dict) else ""
    return url if url.startswith("https://claude.ai/") else ""


def page_first(url: str, argv: list[str]) -> str:
    """What a run with a page does before the brief is gathered: the ticks made on the page
    are applied (code, exactly once, with receipts), so the brief never lists as owed what
    the person already marked done there. Then the brief itself."""
    keep = []
    for flag in ("--write", "--today"):
        if flag in argv:
            i = argv.index(flag)
            keep += argv[i:i + (2 if flag == "--today" else 1)]
    rest = " ".join(keep + ["--page-applied"])
    return "\n".join([
        "PAGE FIRST, FOR CLAUDE (the person's ticks on their page change what is owed):",
        "1. ArtifactData query, url %s, collection actions, then collection receipts, each "
        "with out_dir <D> (a new folder in your scratchpad) and query.limit 1000." % url,
        "2. python3 tools/app.py apply <D> --chat brief --claim, then send the batch it names "
        "(ArtifactData batch). Refused: another chat is applying them; go to 4.",
        "3. python3 tools/app.py apply <D> --chat brief, then send every batch it prints.",
        "4. python3 tools/brief.py %s (the brief itself), and carry on with the prompt's "
        "step 1 from what it prints. Keep <D> for the page's refresh in step 4." % rest,
        ""])


# ---------------------------------------------------------------- the brief

def gather(today: dt.date, write: bool = False) -> dict:
    """Everything the brief says, as one dict. With `write`, the day's upkeep is done and
    recorded (closing the quiet applications, the stale preps, the pack, the tip)."""
    import followup_drafts
    with followup_drafts.FoldersOnce():
        return _gather(today, write)


def _gather(today: dt.date, write: bool) -> dict:
    import followup_drafts
    import followups
    import open_actions
    import throttle
    from network import state

    iso = today.isoformat()
    contacts, threads = state.load_contacts(), state.load_threads()
    tracker = open_actions._tracker()
    earlier = earlier_briefs(today)
    since = _d(os.path.basename(earlier[-1])) if earlier else today - dt.timedelta(days=DEFAULT_SINCE_DAYS)
    last_text = _read(earlier[-1]) if earlier else ""

    # The day's upkeep first, so everything below reads the state it leaves.
    closed = followups.close_quiet(today=today, write=write)
    staged = stages_into_tracker(today) if write else []
    if (closed or staged) and write:
        tracker = open_actions._tracker()
    preps = _preps(iso) if write else {"line": "", "rebuilt": 0, "research": []}

    items = open_actions.due_items(contacts, threads, tracker, today)
    got = followup_drafts.drafts(items, contacts, threads, tracker, iso)
    pack = followup_drafts.write_pack(iso, got, contacts) if write else ""

    live = [i for i in got if not i.get("held") and not i.get("quiet") and not i.get("old")
            and i.get("kind") != "request_pending"]
    asks = [i for i in got if i.get("kind") == "request_pending" and not i.get("held")]
    old = [i for i in got if i.get("old")]
    held = [i for i in got if i.get("held") and not i.get("quiet")]
    replies = [i for i in live if i.get("half") == "contact" and i.get("kind") in ("reply", "resume")]
    nudges_due = [i for i in live if i.get("half") == "application" and i.get("kind") != "interview"]
    counts = live_counts(tracker)
    since_counts = counts_since(tracker, threads, since, today)

    # Where the search is.
    sent_lately = any(_d(throttle.applied_on(r)) and (today - _d(throttle.applied_on(r))).days <= QUIET_DAYS
                      for r in tracker if _status(r) and _status(r) not in throttle.UNSENT
                      and not throttle.is_process(r))
    warm = _warm_routes(contacts, threads)
    owned = open_actions.campaigns(tracker)
    lead = _lead(counts, replies, nudges_due, sent_lately, warm, owned, today)

    sync = read_sync(today)
    brk = _break(today, write)
    update = sync.get("update", "")
    if update and update in last_text:
        update = ""                         # said in the last brief: once is enough
    lines = []
    if sync.get("blocked"):
        lines.append(" ".join(sync["blocked"]))
    if sync.get("exit"):
        lines.append("Today's check for app updates did not finish; the next run tries again.")
    if sync.get("changed"):
        more = len(sync["changed"]) - 1
        lines.append("Updated: %s%s." % (sync["changed"][0].rstrip(". "),
                                         ", and %d more" % more if more > 0 else ""))
    if brk.get("over"):
        lines.append(brk["over"])
    if closed:
        lines.append("%s as no reply: %s. Say if any is still open." % (
            "Closing" if write else "Would close", "; ".join(
                "%s (%s)" % (it["company"], it["role"] or "role not recorded") for it in closed[:3])
            + (" and %d more" % (len(closed) - 3) if len(closed) > 3 else "")))
    ww = _what_works(tracker, today)
    if ww:
        lines.append(ww)
    if update:
        lines.append(update)

    export_line, profile_line = _export_due(today, threads), _own_profile_due(today, contacts, threads)
    three = _next_three(got, counts, replies, unconfirmed(tracker, today), preps, export_line,
                        profile_line, sent_lately, warm, today)

    live_names = _live_employers(tracker, contacts, threads, today)
    claude_md = _profile_text("CLAUDE.md")
    watch = watch_list()
    qs = queries(today, live_names, watch)
    wide = wider(today, live_names, watch, qs)
    b = {
        "date": iso, "weekday": today.strftime("%A"), "since": since.isoformat(),
        "counts": {"owed": len(live), **{k: v for k, v in counts.items() if k != "processes"}},
        "since_counts": since_counts, "lead": lead,
        "owed": [_owed_line(i) for i in live],
        "set_aside": _set_aside(asks, old, held),
        "lines": lines, "next_three": three,
        "drafts": got, "pack": pack, "closed": closed, "preps": preps,
        "queries": qs, "wider": wide, "watch": watch,
        "in_play": in_play(tracker, contacts, threads, live_names), "watch_due": watch_needs_writing(claude_md),
        "language": news_language(person.country()),
        "what_counts": what_counts(claude_md, watch), "skip_links": links_sent(earlier),
        "sync": sync, "export_line": export_line, "profile_line": profile_line,
        "write_here": followup_drafts.to_write_here(got),
        "url": _brief_url(iso), "page": page_url(), "tip": "", "written": write,
        "paused": brk.get("until", "") if brk and brk.get("until", "") > iso else "",
    }
    if write:
        b["tip"] = _tip(today)
        write_record(b)
        if setting("news") and not b["paused"]:
            plan_searched(searched_whats(qs, watch, today), today)
    return b


_NOTE_DAY = re.compile(r"(?:^|[|;]\s*)(\d{4}-\d{2}-\d{2}):")


def stages_into_tracker(today: dt.date) -> list[str]:
    """Each stage a live process's record (its outcome.md) marks done after the row's last
    dated note goes onto that tracker row's notes too, once, with its day. The page and the
    brief read the record; a chat reading the row by hand read a test as still due five days
    after it was taken, because only the record said so (2 November: a test taken on 29
    October, the row's last note still its invite and deadline). Returns the employers."""
    import csv_store
    import open_actions
    import throttle
    path = person.state("job_search_tracker.csv")
    if not os.path.exists(path):
        return []
    rows = csv_store.read_rows(path)
    live = set(throttle.LIVE_PROCESS)
    added = []
    for r in rows:
        if _status(r) not in live:
            continue
        notes = str(r.get("notes") or "")
        written = max(_NOTE_DAY.findall(notes) or [""])
        for st in open_actions.stages(r)[2]:
            day = st.get("date") or ""
            if not st.get("done") or not _d(day) or day <= written or _d(day) > today:
                continue
            line = "%s: %s done (from the application's record)" % (day, st["label"].rstrip(" :"))
            if line not in notes:
                notes = (notes.rstrip() + " | " + line).strip(" |")
                added.append(str(r.get("company") or ""))
        r["notes"] = notes
    if added:
        csv_store.write_rows(path, rows, csv_store.header(path))
    return list(dict.fromkeys(added))


def _break(today: dt.date, write: bool) -> dict:
    """A break the person took on the page (routines.py pause): {"until"} while it runs; on
    or after its last day, with `write`, it is lifted here ("over" says so) and the calls
    that turn the brief back on are left for the run to make."""
    try:
        import routines
        got = routines.paused()
    except Exception:  # noqa: BLE001  no profile or no registry: no break
        return {}
    if not got:
        return {}
    if got["until"] > today.isoformat() or not write:
        return got
    try:
        routines.resume(today.isoformat())
    except Exception:  # noqa: BLE001  the next run tries again
        return got
    return {"over": "Welcome back: your break is over, and everything below is what is "
                    "waiting for you."}


def _preps(iso: str) -> dict:
    """The call preps gone stale, rebuilt: {"line", "rebuilt", "research": [...]}."""
    import contextlib
    import io
    try:
        import prep
    except Exception:
        return {"line": "", "research": []}
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
            prep.main(["--stale-only", "--today", iso])
    except (Exception, SystemExit):
        return {"line": "", "research": []}
    out = buf.getvalue().splitlines()
    head = next((ln for ln in out if "prep documents" in ln), "")
    n = re.match(r"(\d+)", head)
    research = [ln for ln in out if "RESEARCH NEXT" in ln or ln.split(":", 1)[-1].strip().startswith("RESEARCH")]
    return {"line": head, "rebuilt": int(n.group(1)) if n else 0, "research": research}


def _warm_routes(contacts, threads) -> list[dict]:
    import throttle
    from network import state
    index = state.by_contact(threads) if threads else {}
    out = []
    for c in contacts:
        st = state.effective_status(c, index.get(str(c.get("contact_id") or "").strip(), ()))
        if st in throttle.RESPONDED and st not in ("closed", "gone_cold"):
            out.append({"name": c.get("name") or "", "company": c.get("company") or "", "status": st})
    return out


def _live_employers(tracker, contacts, threads, today) -> list[str]:
    """The employers in play, nearest an outcome first: a live process, a live thread, an
    application out and not gone quiet."""
    import throttle
    seen, out = set(), []

    def add(name):
        k = company_key(name)
        if name and k and k not in seen:
            seen.add(k)
            out.append(name.strip())

    for r in tracker:
        if _status(r) in set(throttle.LIVE_PROCESS):
            add(r.get("company"))
    for w in _warm_routes(contacts, threads):
        add(w["company"])
    for r in tracker:
        d = _d(throttle.applied_on(r))
        if _status(r) == "applied" and d and (today - d).days <= throttle.SILENCE_DAYS:
            add(r.get("company"))
    return out


def _lead(counts, replies, nudges_due, sent_lately, warm, owned, today) -> str:
    procs = counts["processes"]
    if procs:
        r = procs[0]
        company = (r.get("company") or "").strip()
        k = company_key(company)
        if k in owned:
            return "%s is live, and its own chat (%s) has the prep." % (company, owned[k])
        st = next_stage(r, today)
        more = " (and %d more)" % (len(procs) - 1) if len(procs) > 1 else ""
        nxt = (": the %s is on %s" % (st.get("label") or "next stage", st["date"])) if st else ""
        return "Your %s process is live%s%s. /interview %s prepares it." % (
            company, more, nxt, company)
    if replies:
        i = replies[0]
        who = first_name(i.get("name", "").split(" (")[0])
        n = len(replies)
        return ("%s %s waiting on you: %s%s has waited %d days." % (
            n, "person is" if n == 1 else "people are", who,
            " (%s)" % i["name"].split(" (", 1)[1].rstrip(")") if " (" in i.get("name", "") else "",
            max(i.get("late") or 0, 0)))
    if nudges_due or (counts["applications"] and sent_lately):
        return ("%d application%s out and waiting%s." % (
            counts["applications"], " is" if counts["applications"] == 1 else "s are",
            "; %d follow-up%s due" % (len(nudges_due), "" if len(nudges_due) == 1 else "s")
            if nudges_due else ""))
    if not sent_lately:
        routes = ", ".join("%s (%s)" % (first_name(w["name"]), w["company"]) for w in warm[:2])
        return ("Nothing has gone out in %d days.%s A fresh shortlist is one \"find me jobs\" away."
                % (QUIET_DAYS, " Warm routes already in your contacts: %s." % routes if routes else ""))
    return "Nothing is owed today."


def _owed_line(i: dict) -> dict:
    """One owed item, as the brief says it: who, what, and where its draft stands."""
    d = i["draft"]
    late = max(i.get("late") or 0, 0)
    if i.get("half") == "contact":
        what = {"reply": "reply owed", "resume": "%s owed" % _noun(), "nudge": "nudge due",
                "first_message": "first message owed", "action_due": "your date"}.get(i.get("kind"), "owed")
        if i.get("kind") == "reply" and "owed to" in (i.get("what") or "") and _noun() in i.get("what", ""):
            what = "%s owed" % _noun()
    elif i.get("kind") == "interview":
        what = i.get("what") or "interview"
        what = what.split(":")[0]
    else:
        what = "follow-up %s" % ((i.get("what") or "").split(",")[0].replace("nudge ", "")) \
            + (" %s" % i["to"].replace("to: ", "to ").split(" (")[0] if i.get("to") else "")
    status = {"ready": "draft ready", "check": "draft ready, check it first",
              "write": ("%s to write" % ("reply" if d.get("kind") == "reply" else "draft"))
              if d.get("who") == "here" else "needs you",
              "none": ""}[d["status"]]
    return {"text": "%s: %s%s%s" % (i.get("name"), what, ", %dd" % late if late else "",
                                     "; " + status if status else ""),
            "id": i.get("id"), "status": d["status"], "kind": i.get("kind"),
            "half": i.get("half")}


def _noun() -> str:
    return str(person.get("documents.noun", "resume") or "resume")


def _set_aside(asks, old, held) -> list[str]:
    out = []
    if asks:
        out.append("%d connection request%s nobody accepted: withdraw them on LinkedIn"
                   % (len(asks), "" if len(asks) == 1 else "s"))
    if old:
        out.append("%d owed over 45 days with nothing done, set aside" % len(old))
    if held:
        out.append("%d held for now (an interview, a referral or your own note)" % len(held))
    return out


def _what_works(tracker, today) -> str:
    try:
        import what_works
        got = what_works.brief_search(tracker, today)
    except Exception:
        return ""
    diffs = [ln[2:] for ln in got.splitlines() if ln.startswith("- ")]
    return ("What works: " + diffs[0]) if diffs else ""


def _export_due(today, threads) -> str:
    try:
        import export
        return export.due(today, threads) or export.waiting_line(
            today, [_read(p) for p in earlier_briefs(today)
                    if os.path.basename(p)[:10] >= str(export.load_record().get(
                        "requested_on") or "")]) or ""
    except Exception:
        return ""


def _own_profile_due(today, contacts, threads) -> str:
    try:
        import own_profile
        return own_profile.due(today, contacts, threads) or ""
    except Exception:
        return ""


def _next_three(got, counts, replies, drafted, preps, export_line, profile_line, sent_lately,
                warm, today) -> list[str]:
    """Exactly three things to do before the next brief, most valuable first, each one line
    and under half an hour."""
    out: list[str] = []
    seen: set = set()

    def add(key, text):
        if key not in seen and len(out) < 3:
            seen.add(key)
            out.append(text)

    live = [i for i in got if not i.get("held") and not i.get("quiet") and not i.get("old")]
    for i in live:
        if i.get("kind") == "interview" and "no pack yet" in (i.get("what") or ""):
            add(i.get("key"), "Prepare for your interview at %s, %s." % (
                i["name"].split(" (")[0], i["what"].split(" (")[0].replace("interview ", "", 1)))
    for i in replies:
        who = i.get("name", "")
        if _noun() + " owed" in (i.get("what") or "") or i.get("kind") == "resume":
            add(i.get("key"), "Send %s the %s they asked for." % (who, _noun()))
        elif i["draft"]["status"] in ("ready", "check"):
            add(i.get("key"), "Send your reply to %s: it is drafted for you." % who)
        else:
            add(i.get("key"), "Reply to %s." % who)
    for i in live:
        if i.get("kind") == "interview" and "thank-you" in (i.get("what") or ""):
            add(i.get("key"), "Send the thank-you after your interview at %s."
                % i["name"].split(" (")[0])
    for i in live:
        if i["draft"]["status"] in ("ready", "check") and i.get("kind") in ("nudge", "first_message") \
                and i.get("half") == "contact":
            add(i.get("key"), "Send the nudge to %s: it is drafted for you." % i.get("name"))
    for i in live:
        if i.get("half") == "application" and i["draft"]["status"] in ("ready", "check"):
            add(i.get("key"), "Send the follow-up on %s: it is drafted for you." % i.get("name"))
    if drafted:
        names = "; ".join("%s, %s" % (r.get("company"), r.get("role") or "role not recorded")
                          for r in drafted[:3])
        add("unconfirmed", "Did these go? %s. Mark each one applied or not." % names)
    for ln in (preps or {}).get("research", [])[:1]:
        name = ln.split(":", 1)[0].strip()
        add("research:" + name, "Read the prep before your call with %s." % name)
    if profile_line:
        m = re.search(r"\"([^\"]+)\"", profile_line)
        if m:
            add("own_profile", m.group(1))
    if export_line and export_line.startswith("Your LinkedIn download was asked for on"):
        add("export_wait", export_line)
    elif export_line and "asked for on" not in export_line:
        m = re.search(r"(\d+) days old", export_line)
        add("export", "Ask LinkedIn for a new copy of your data%s; ask Claude for the steps."
            % (" (yours is %s days old)" % m.group(1) if m else ""))
    for i in live:
        if i.get("kind") == "nudge" and i["draft"]["status"] == "write":
            add(i.get("key"), "Tell me one new thing to say to %s and I'll draft the nudge."
                % i.get("name"))
    if not sent_lately:
        for w in warm[:1]:
            add("warm", "Ask %s (%s) about the team there: a warm route you already have."
                % (first_name(w["name"]), w["company"]))
        add("search", "Find new jobs: Jobs, Find jobs.")
    if counts.get("applications"):
        add("outcome", "Heard back from anyone? Mark it on the application.")
    add("search", "Find new jobs: Jobs, Find jobs.")
    add("network", "Find people at an employer you want: Contacts, Find people.")
    add("targets", "Watch an employer you would love to work at (Jobs, Change the search), and "
        "Claude reads its own jobs every search.")
    return out


def _tip(today) -> str:
    try:
        import tips
        state_ = tips.load()
        said = tips.line("brief", today, state_)
        if said:
            tips.save(state_)
        return said or ""
    except Exception:
        return ""


def _brief_url(iso: str) -> str:
    """Where the message sends the person: their page's To do, else the day's record."""
    url = page_url()
    if url:
        return url + "#todo"
    try:
        r = subprocess.run(["git", "remote", "get-url", "origin"], cwd=ROOT, text=True,
                           capture_output=True, timeout=10, encoding="utf-8", errors="replace")
    except (OSError, subprocess.TimeoutExpired):
        return ""
    m = re.search(r"github\.com[:/]([^/\s]+)/([^/\s]+?)(?:\.git)?/?$", (r.stdout or "").strip())
    if r.returncode or not m:
        return ""
    return "https://github.com/%s/%s/blob/master/documents/briefs/%s.md" % (m.group(1), m.group(2), iso)


# ---------------------------------------------------------------- what it says

def headline(b: dict) -> str:
    c = b["counts"]
    return "%s brief: %d owed · %d application%s live · %d interview%s" % (
        b["weekday"], c["owed"], c["applications"], "" if c["applications"] == 1 else "s",
        c["interviews"], "" if c["interviews"] == 1 else "s")


def since_line(b: dict) -> str:
    s = b["since_counts"]
    extra = "".join(", %d %s" % (s[k], w) for k, w in (("offers", "offers"), ("rejections", "rejections"))
                    if s[k])
    return "Since %s: %d sent, %d replies, %d interviews%s" % (
        _short_date(b["since"]), s["sent"], s["replies"], s["interviews"], extra)


def _short_date(iso: str) -> str:
    d = _d(iso)
    return "%d %s" % (d.day, d.strftime("%b")) if d else iso


def message_lines(b: dict, owed_max: int = 4) -> list[str]:
    """The message as a phone shows it, news left for the model to put in."""
    if b.get("paused"):
        return ["Your search is paused until %s. Nothing is chased meanwhile." % _short_date(
            b["paused"])] + (["Your page: " + b["url"]] if b.get("page") else [])
    out = [headline(b), b["lead"], "", "Owed"]
    owed = b["owed"]
    out += ["- " + o["text"] for o in owed[:owed_max]] or ["Nothing owed"]
    if len(owed) > owed_max:
        out.append("- and %d more in the full brief" % (len(owed) - owed_max))
    out += ["- " + s for s in b["set_aside"]]
    hide = set(setting("hide"))
    if "since" not in hide:
        out += ["", since_line(b)]
    out += b["lines"]
    if "next_three" not in hide:
        out += ["", "Next three"] + ["%d. %s" % (n, t) for n, t in enumerate(b["next_three"], 1)]
    if setting("news"):
        out += ["", "News", "<NEWS>"]
    asks = len((b.get("sync") or {}).get("questions") or [])
    if b.get("page") and asks:
        out += ["", "%d question%s wait%s for you on your page." % (
            asks, "" if asks == 1 else "s", "s" if asks == 1 else "")]
    if b["url"]:
        out += ["", ("Your page: " if b.get("page") else "Full brief: ") + b["url"]]
    if b["tip"] and "tip" not in hide:
        out += [b["tip"]]
    return out


def _tidy_due() -> str:
    """The day's tidy of the app's own old chats, done in the brief's run when the brief runs
    in the chat that answers the page and nothing has done it yet today: one daily pass, not
    two (tools/tidy.py)."""
    try:
        import app_listen
        import tidy
        here = app_listen.this_chat()
        if app_listen.chat_kind() != "cloud" or not here.startswith("session_"):
            return ""
        if (app_listen.seen().get("listener") or {}).get("chat") != here or not tidy.due():
            return ""
    except Exception:  # noqa: BLE001  no git folder, no record: nothing to tidy from here
        return ""
    return ("tidy, before the final reply (the message is the last thing this run says): "
            "list_sessions (mine: true) and list_triggers, "
            "every page, each saved to a file; python3 tools/tidy.py plan --sessions <each> "
            "--triggers <each>; do what it prints (the app skill, \"Once a day\")")


def claude_lines(b: dict) -> list[str]:
    """For the model only: what it acts on. Never in the message."""
    s = b["sync"] or {}
    out = []
    if b.get("paused"):
        return ["paused until %s: the message is the line above, as it is; no news search, no "
                "drafts, nothing else to do or save" % b["paused"]]
    if not s and b.get("written"):
        out.append("the start did not run today: run python3 tools/brief.py --start --on "
                   "\"<model>\" --write")
    if s.get("blocked"):
        out.append("job sites are blocked: the message opens with the line above about it")
    if s.get("exit"):
        out.append("the update check stopped (exit %d): %s" % (s["exit"], s.get("first", "")[:160]))
    if s.get("setup"):
        out.append("setting up the Python side failed: %s" % s["setup"])
    for br in s.get("earlier", []):
        out.append("an earlier run's work is not saved (%s): land it as _common.md step 3 says" % br)
    out += s.get("for_claude", [])
    if s.get("upgrades"):
        out.append("run /upgrade 20 now (%d waiting); one plain line per change it made goes at "
                   "the end of the message" % len(s["upgrades"]))
    if s.get("questions") and b.get("page"):
        out.append("the questions are on the page as To do cards: ask none in the message, "
                   "which says how many wait there")
    elif s.get("questions"):
        out.append("at most three questions at the end of the message, each as written: "
                   + " | ".join(q for q in s["questions"][:3]))
    if b["write_here"]:
        import followup_drafts
        n, most = len(b["write_here"]), followup_drafts.WRITE_HERE_MAX
        out.append("%d draft%s this run can write or rewrite from the thread%s: python3 "
                   "tools/followup_drafts.py context --due, write them, then "
                   "followup_drafts.py check - --pack" % (
                       n, "" if n == 1 else "s",
                       " (the first %d; the rest wait in the pack)" % most if n > most else ""))
    if b["profile_line"]:
        out.append("own profile question: a yes runs python3 tools/network/own_profile.py check")
    tidy_line = _tidy_due()
    if tidy_line:
        out.append(tidy_line)
    n = setting("news")
    if b.get("watch_due") and n:
        out.append("what the news watches needs writing (%s): read the person's profile, then "
                   "write the few things that move their own search, in their terms, each with "
                   "how often it changes, with python3 tools/brief.py watch write (its --help "
                   "says how); then python3 tools/brief.py watch searches prints today's "
                   "searches, which replace the ones below%s" % (
                       b["watch_due"], "; they turned off before, so leave out: " +
                       "; ".join(turned_off_before()) if turned_off_before() else ""))
    if n and b["queries"]:
        out.append("news: the news-reader agent, given these searches: %s; at most %d item%s in the "
                   "message (the person's setting)%s" % (
                       " | ".join(b["queries"]), n, "" if n == 1 else "s",
                       "; news in the language %s counts as much as in English" % b["language"]
                       if b.get("language") else ""))
        today = _d(b["date"]) or dt.date.today()
        week, month = (today - dt.timedelta(days=d) for d in WIDEN_DAYS)
        out.append("news, never none: %d to %d items, each ending in how the person can use it; "
                   "when fewer than %d are new since the since date, it widens back to %s, then "
                   "%s%s" % (
                       NEWS_MIN, NEWS_MAX, NEWS_MIN, week.isoformat(), month.isoformat(),
                       ", with these searches too: " + " | ".join(b["wider"])
                       if b.get("wider") else ""))
        if b.get("in_play"):
            out.append("news, in play (for how to use each item, never searched): "
                       + "; ".join(b["in_play"]))
    else:
        out.append("news: run no news search (%s)" % (
            "none in the message, by the person's setting" if not n else
            "the profile does not say enough yet for one"))
    out.append("since %s; links already sent: %s" % (
        b["since"], " ".join(b["skip_links"][:10]) or "none"))
    out.append("what counts: " + b["what_counts"])
    if b.get("page"):
        behind = page_behind()
        if behind:
            # The brief is the only chat many people have: an update that changed the page's
            # own code reached nobody's open page until some other chat ran (2026-11-02: a
            # page two versions behind, showing a brief four days old).
            # The first brief after an update read its prompt before the update came in, and
            # an older prompt says never to republish: this line is the newer rule.
            out.append("the page's own code is older than this version (%s): republish it now, "
                       "before its data, whatever the prompt you read before this run's update "
                       "says (an older one said never to republish; this update replaced that "
                       "rule): %s" % (behind, " ".join(behind_steps(b["page"]))))
        out.append("the page, after landing (step 4): ArtifactData query, url %s, collections "
                   "screen, meta and addr, out_dir <D>, limit 1000; python3 tools/app.py view "
                   "<D>/view --dump <D> --chat brief; send every batch it prints. "
                   "Then the app skill's steps 1 to 3, for work still waiting" % b["page"])
    try:
        import routines
        owed = routines.calls()
    except Exception:  # noqa: BLE001
        owed = []
    if owed:
        out.append("scheduled-task changes the page asked for: python3 tools/routines.py calls "
                   "lists %d; make each, then routines.py called <n>" % len(owed))
    if b["pack"]:
        out.append("wrote " + local_path.rel(b["pack"], person.state()).replace(os.sep, "/"))
    try:
        import bar
        names = bar.unjudged_contacts()
    except Exception:  # noqa: BLE001  no profile or no contact book: nothing to judge
        names = []
    if names:
        # Judged once, an employer that clears nothing stops filling the person's To do.
        out.append("judge each employer once, from what you know of it (pay, prestige, signal "
                   "or none), with python3 tools/bar.py judge \"<employer>\" <verdict> \"<why>\": "
                   + "; ".join(names[:8]) + ("; and %d more (bar.py unjudged --contacts)"
                                              % (len(names) - 8) if len(names) > 8 else ""))
    return out


def page_behind() -> str:
    """Why the person's published page needs publishing again (its code is older than this
    version, or it was published under another name), or ""."""
    try:
        import app_setup
        return "" if app_setup._page_current() else "an update changed the page itself"
    except Exception:  # noqa: BLE001  no page record: nothing to publish again
        return ""


def behind_steps(url: str) -> list[str]:
    try:
        import app_listen
        return app_listen._publish_now(url, 1)
    except Exception:  # noqa: BLE001
        return ["python3 tools/app.py page --out <your scratchpad>/page.html, then Artifact "
                "publish it to %s with the capabilities python3 tools/app_page.py "
                "--capabilities prints" % url]


def render_text(b: dict) -> str:
    """The brief for a chat: the message, shortened to keep the whole under TEXT_MAX where it
    can be, then the lines for Claude, whole. Those were cut with the rest at TEXT_MAX, and on
    a real state (2026-11-02: a page behind, six employers in play) the cut fell on the
    republish and the page's update, so the brief did neither and nothing said so."""
    start = LENGTHS[setting("length")]
    tail = "\n".join(["", "FOR CLAUDE, never in the message:"] + ["- " + x for x in claude_lines(b)])
    for owed_max in [n for n in (6, 4, 3, 2) if n <= start] or [2]:
        body = "\n".join(message_lines(b, owed_max))
        text = body + "\n" + tail + "\n"
        if len(text) <= TEXT_MAX:
            return text
    return text


# ---------------------------------------------------------------- the record

NEWS_HOLDER = "Searching: the news is added when the search is back."
# Said once above the items: the news reader searches and opens no page, so a line is only
# ever what its search result said, and the record says so.
NEWS_SOURCE = "From search results; no page was opened, so each line says only what its result said."


def record_text(b: dict, news: list[str] | None = None) -> str:
    """documents/briefs/<date>.md: the same layout every time, so the briefs read as one record."""
    out = ["# Brief, %s (%s)" % (b["date"], b["weekday"]), "",
           "Since %s. Gathered by tools/brief.py; the news by the news reader." % b["since"], "",
           "## Where the search is", "", headline(b), "", b["lead"], "", "## Owed", ""]
    owed = b["owed"]
    if not owed:
        out.append("Nothing owed.")
    by_id = {i["id"]: i for i in b["drafts"]}
    for o in owed[:RECORD_OWED]:
        out.append("- " + o["text"])
        d = (by_id.get(o["id"]) or {}).get("draft") or {}
        if d.get("status") in ("ready", "check"):
            out.append("")
            out += ["  > " + ln for ln in d["text"].splitlines()]
            out += ["  Check: " + w for w in d.get("warnings") or []]
            out.append("")
    if len(owed) > RECORD_OWED:
        out.append("- and %d more, each in today's follow-up pack" % (len(owed) - RECORD_OWED))
    out += ["- " + s for s in b["set_aside"]]
    out += ["", "## Since the last brief", "", since_line(b) + "."]
    out += ["- " + ln for ln in b["lines"]]
    if b["preps"].get("rebuilt"):
        out.append("- Call preps rebuilt: %d, each for a conversation that changed since it was "
                   "written." % b["preps"]["rebuilt"])
    out += ["", "## Next three", ""] + ["%d. %s" % (n, t) for n, t in enumerate(b["next_three"], 1)]
    out += ["", "## News", ""]
    out += (news if news is not None else [NEWS_HOLDER])
    return "\n".join(out).rstrip() + "\n"


def write_record(b: dict, news: list[str] | None = None) -> str:
    path = brief_path(b["date"])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(record_text(b, news))
    return path


def take_news(text: str, today: dt.date) -> dict:
    """The news reader's items into today's record: at most NEWS_MAX, none whose link an
    earlier brief carried, and a dated note on a live application's row for a freeze or
    layoffs at that employer. {"kept", "dropped", "noted", "path"}."""
    # The news reader ran today's searches, whatever it found: what they carried is searched.
    note_searched(None, today)
    items = []
    for ln in text.splitlines():
        s = ln.strip()
        if not s or s.lower().startswith(("quiet week", "nothing new", "none", "no news")):
            continue
        s = s.lstrip("-*• ").strip()
        if s:
            items.append(s)
    seen = set(links_sent(earlier_briefs(today) + [brief_path(today.isoformat())]))
    kept, dropped = [], []
    for s in items:
        links = [u.rstrip(".,;") for u in _LINK.findall(s)]
        if links and any(u in seen for u in links):
            dropped.append(s)
            continue
        if len(kept) < NEWS_MAX:
            kept.append(s)
    path = brief_path(today.isoformat())
    body = _read(path)
    carried, day = ([], "") if kept else carry_news(today)
    if kept:
        news = [NEWS_SOURCE, ""] + ["- " + s for s in kept]
    elif carried:
        news = ["Carried from the brief of %s. %s" % (day, NEWS_SOURCE), ""] + [
            "- " + s for s in carried]
    else:
        # Nothing found and nothing to carry (a first brief whose search did not run): the
        # section is left out rather than filled with a line saying so.
        news = []
    if body:
        head = body.split("\n## News", 1)[0].rstrip()
        new = head + ("\n\n## News\n\n" + "\n".join(news) if news else "") + "\n"
    else:
        new = "# Brief, %s\n%s" % (today.isoformat(), "\n## News\n\n%s\n" % "\n".join(news)
                                     if news else "")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(new)
    noted = _note_news(kept, today)
    return {"kept": kept, "dropped": dropped, "noted": noted, "path": path,
            "carried": carried, "carried_from": day}


def news_items(text: str) -> list[str]:
    """A brief record's news lines, as written, without their bullets."""
    return [ln[2:].strip() for ln in _section(text, "News").splitlines()
            if ln.startswith("- ") and ln[2:].strip()]


def carry_news(today: dt.date) -> tuple[list[str], str]:
    """The newest earlier brief's news, within CARRY_DAYS, and its day: what a brief whose
    reader brought nothing new shows instead of an empty panel."""
    for p in reversed(earlier_briefs(today)):
        d = _d(os.path.basename(p)[:10])
        if not d or (today - d).days > CARRY_DAYS:
            break
        got = news_items(_read(p))
        if got:
            return got[:NEWS_MAX], d.isoformat()
    return [], ""


def _note_news(kept: list[str], today: dt.date) -> list[str]:
    """A dated line on each live application's row whose employer a freeze or layoffs item names."""
    import csv_store
    import throttle
    path = person.state("job_search_tracker.csv")
    if not kept or not os.path.exists(path):
        return []
    rows = csv_store.read_rows(path)
    live = set(throttle.LIVE_PROCESS) | {"applied"}
    noted = []
    for r in rows:
        company = str(r.get("company") or "").strip()
        if _status(r) not in live or not company:
            continue
        rx = re.compile(r"\b" + re.escape(company) + r"\b", re.I)
        for s in kept:
            if rx.search(s) and NEWS_HOLD.search(s):
                note = "%s: news: %s (the brief, from a search result)" % (
                    today.isoformat(), " ".join(s.split())[:180])
                if note not in str(r.get("notes") or ""):
                    r["notes"] = ((r.get("notes") or "").rstrip() + " | " + note).strip(" |")
                    noted.append(company)
    if noted:
        csv_store.write_rows(path, rows, csv_store.header(path))
    return list(dict.fromkeys(noted))


# ---------------------------------------------------------------- the command

def _utf8() -> None:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass


WATCH_HELP = """What the person's brief watches, in their own terms (person.json brief.watch).

  watch                  the list, and whether it needs writing
  watch write            Claude's list from the profile, as JSON on stdin:
                         [{"what": "<words to search>", "every": "day|week|month"}, ...]
                         A few things (at most %d) that move THIS person's search, most
                         important first, each as often as it really changes: their right to
                         work where it can change, the pay talks, rules or exams of their
                         field, their local market for their roles, an employer group they
                         follow. Never a kind of news because others watch it. It replaces
                         Claude's earlier items; the person's own and what they took off stay.
  watch add "<what>" [--every week]   one the person asked for in a chat (theirs)
  watch drop "<what>"    one off, and never written back
  watch searches         today's searches, for the news reader; noted as searched when
                         brief.py news takes what it found""" % WATCH_MAX


def watch_main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="brief.py watch", description=WATCH_HELP,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("do", nargs="?", default="show",
                    choices=("show", "write", "add", "drop", "searches"))
    ap.add_argument("what", nargs="?", default="")
    ap.add_argument("--every", default="week", choices=tuple(EVERY))
    ap.add_argument("--today", default="")
    a = ap.parse_args(argv)
    if not person.exists():
        print("No profile yet, so there is nothing to watch: set the search up first.")
        return 1
    if a.do == "write":
        try:
            items = json.loads(sys.stdin.read() or "[]")
        except ValueError as e:
            print("watch write: not JSON (%s)" % e, file=sys.stderr)
            return 2
        if not isinstance(items, list) or not watch_list(items):
            print("watch write: give a list of {\"what\", \"every\"}, at least one", file=sys.stderr)
            return 2
        kept = write_watch(items)
    elif a.do == "add":
        if not _clean_what(a.what):
            print("watch add: say what to watch", file=sys.stderr)
            return 2
        try:
            kept = write_watch([{"what": a.what, "every": a.every}], by_person=True)
        except ValueError as e:
            print("watch add: %s" % e, file=sys.stderr)
            return 2
    elif a.do == "drop":
        if not drop_watch(a.what):
            print("watch drop: %r is not on the list" % a.what, file=sys.stderr)
            return 2
        kept = watch_list()
    elif a.do == "searches":
        today = _today(a.today)
        import open_actions
        from network import state
        contacts, threads = state.load_contacts(), state.load_threads()
        tracker = open_actions._tracker()
        watch = watch_list()
        qs = queries(today, _live_employers(tracker, contacts, threads, today), watch)
        plan_searched(searched_whats(qs, watch, today), today)
        for q in qs:
            print(q)
        return 0
    else:
        kept = watch_list()
        why = watch_needs_writing()
        if why:
            print("needs writing: %s (python3 tools/brief.py watch --help)" % why)
        if turned_off_before():
            print("they turned off before, so leave out: " + "; ".join(turned_off_before()))
    for w in kept:
        print("- %s (every %s)%s" % (w["what"], w["every"], ", theirs" if w.get("by") else ""))
    if not kept:
        print("Nothing watched yet.")
    return 0


def main(argv=None) -> int:
    _utf8()
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv[:1] == ["news"]:
        ap = argparse.ArgumentParser(prog="brief.py news")
        ap.add_argument("--file", help="the items, one a line; stdin without it")
        ap.add_argument("--today", default="")
        a = ap.parse_args(argv[1:])
        text = _read(a.file) if a.file else sys.stdin.read()
        got = take_news(text, _today(a.today))
        print("news: %d kept%s%s%s" % (
            len(got["kept"]),
            "; %d left out, already sent in an earlier brief" % len(got["dropped"]) if got["dropped"] else "",
            "; noted on the tracker for %s" % ", ".join(got["noted"]) if got["noted"] else "",
            "; carried %d from the brief of %s" % (len(got["carried"]), got["carried_from"])
            if got["carried"] else ""))
        lines = got["kept"] or got["carried"]
        if lines:
            print("for the message, the first %d without their links:" % setting("news"))
            for ln in lines[:setting("news")]:
                print("- " + ln)
        return 0
    if argv[:1] == ["watch"]:
        return watch_main(argv[1:])
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--write", action="store_true", help="do the day's upkeep and write the records")
    ap.add_argument("--start", action="store_true", help="a scheduled run's start, then the brief")
    ap.add_argument("--on", default="", help="with --start: the model this run is on")
    ap.add_argument("--today", default="")
    ap.add_argument("--page-applied", dest="page_applied", action="store_true",
                    help="the page's ticks are applied: gather the brief")
    a = ap.parse_args(argv)
    if a.start:
        rest = [x for x in argv if x != "--start"]
        return start(rest, a.on)
    if not person.exists():
        print("No profile yet, so there is no brief: set the search up first.")
        return 1
    today = _today(a.today)
    b = gather(today, write=a.write)
    sys.stdout.write(render_text(b))
    return 0


if __name__ == "__main__":
    import csv_store
    try:
        raise SystemExit(main())
    except csv_store.Conflicted as e:       # a merge left markers: say which file, read nothing
        print("brief: %s" % e, file=sys.stderr)
        raise SystemExit(1) from None
