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
# A watched thing whose search found nothing new this many runs in a row rests for REST_DAYS,
# then is tried again; the dates are kept in watched.json and expire (`_rest`, `_empty`).
EMPTY_RUNS = 3
REST_DAYS = 7
EMPTY_KEEP_DAYS = 30
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
        # Held since the last brief: on its day or after, and before today's. A morning brief
        # counted the evening's interview before it happened, and never after (the audit,
        # 2026-11-03).
        interviews += sum(1 for st in stages if _d(st.get("date"))
                          and since <= _d(st.get("date")) < today)

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
    # Live is the page's own rule (app_model._applications `live`): sent, and not over. The
    # brief left out a hiring process with no application of its own and said 65 beside
    # the page's 66 (2026-11-03).
    apps = [r for r in tracker if _status(r) and _status(r) not in throttle.UNSENT
            and _status(r) not in throttle.FINAL]
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


def plan_searched(whats: list[str], today: dt.date, searches: list[dict] | None = None) -> None:
    """The watched things today's searches carry, kept until the news step says they ran
    (`brief.py news`): marked searched at the gather, a search the run never made, or one a
    rewritten list replaced, waited a week or a month for nothing. `searches` is the numbered
    list the reader is handed (`numbered`), so the news step knows which watched thing each
    item came from."""
    got = _watched_file()
    got["_planned"] = {"day": today.isoformat(), "whats": list(whats),
                       **({"searches": searches} if searches else {})}
    _save_watched(got)


def resting(today: dt.date, got: dict | None = None) -> set[str]:
    """The watched things (lower case) resting today: each found nothing new on its last
    EMPTY_RUNS runs, so it is left out until its day comes (`note_found`). A rest whose day
    has come is over."""
    got = _watched_file() if got is None else got
    rest = got.get("_rest") if isinstance(got.get("_rest"), dict) else {}
    return {str(k).lower() for k, v in rest.items() if _d(v) and _d(v) > today}


def note_found(found: dict, today: dt.date) -> list[str]:
    """After a round whose items say which search found them: each watched thing searched
    today that brought nothing new gets today's date (`_empty`), and one with EMPTY_RUNS such
    dates in a row rests for REST_DAYS (`_rest`); one that found something starts again from
    none. `found` is {what: count of items kept}. Dates older than EMPTY_KEEP_DAYS, and rests
    whose day has come, are dropped. Returns the things that now rest."""
    got = _watched_file()
    empty = got.get("_empty") if isinstance(got.get("_empty"), dict) else {}
    rest = got.get("_rest") if isinstance(got.get("_rest"), dict) else {}
    cut = today - dt.timedelta(days=EMPTY_KEEP_DAYS)
    empty = {k: [d for d in v if _d(d) and _d(d) >= cut] for k, v in empty.items()
             if isinstance(v, list)}
    rest = {k: v for k, v in rest.items() if _d(v) and _d(v) > today}
    now_rest = []
    for what, n in found.items():
        k = str(what).lower()
        if not k:
            continue
        if n:
            empty.pop(k, None)
            continue
        days = sorted(set(empty.get(k, []) + [today.isoformat()]))[-EMPTY_RUNS:]
        if len(days) >= EMPTY_RUNS:
            rest[k] = (today + dt.timedelta(days=REST_DAYS)).isoformat()
            empty.pop(k, None)
            now_rest.append(what)
        else:
            empty[k] = days
    got["_empty"] = {k: v for k, v in empty.items() if v}
    got["_rest"] = rest
    if not got["_empty"]:
        got.pop("_empty")
    if not got["_rest"]:
        got.pop("_rest")
    _save_watched(got)
    return now_rest


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
              searched: dict | None = None, rest: set | None = None) -> list[dict]:
    """The watched things this brief searches, in the person's order: each whose days since it
    was last searched have reached how often it changes, or that was never searched, and that
    is not resting after three runs that found nothing new (`resting`)."""
    watch = watch_list() if watch is None else watch
    searched = last_searched() if searched is None else searched
    rest = resting(today) if rest is None else rest
    out = []
    for n, w in enumerate(watch):
        if w["what"].lower() in rest:
            continue
        last = searched.get(w["what"].lower())
        if last is None or (today - last).days >= EVERY[w["every"]]:
            out.append((last or dt.date.min, n, w))
    # The longest waiting first, the person's order between equals: a brief with no room for
    # one leaves it the oldest, so the next brief takes it (the release review: a daily item
    # early in the list took every slot, and a monthly one later in it never ran). Their first
    # item, the most important, always leads when it is due: a work permit their profile says
    # "outranks everything else" was moved to the wider searches behind items waiting longer
    # (engine audit 23, 2026-11-03).
    ranked = [w for _l, _n, w in sorted(out, key=lambda x: (x[1] != 0, x[0], x[1]))]
    return ranked


def home_place() -> str:
    """Where the person's employer news is placed, in their own words: the last part of their
    location ("Toronto, ON, Canada" gives "Canada"), so a common name finds its local news."""
    loc = str(person.get("identity.location", "") or "")
    return loc.split(",")[-1].strip()[:40] if "," in loc else ""


def _dated(what: str, today: dt.date) -> str:
    """A search with the month on it, to bring this month's news first; none in a month's
    first week, when "November 2026" on the 2nd found almost nothing and the brief said
    "Quiet week" (2026-11-01 and 02). The reader's own date check keeps it fresh."""
    return what if today.day <= 7 else "%s %s" % (what, today.strftime("%B %Y"))


def queries(today: dt.date, live_employers: list[str], watch: list[dict] | None = None,
            searched: dict | None = None) -> list[str]:
    """At most six searches: the employers in play (two at most), then what the person's brief
    watches that is due today, in their own words and their order. Nothing else: no kind of
    news is decided here for anyone, and what matters to a nurse, a lawyer or a student on a
    visa is what their own list says (person.json `brief.watch`)."""
    off = set(setting("leave_out"))
    where = home_place()
    out = [_dated("%s%s news" % (n, " " + where if where else ""), today)
           for n in live_employers[:2]] if "employers" not in off else []
    for w in due_watch(today, watch, searched):
        out.append(_dated(w["what"], today))
    return list(dict.fromkeys(out))[:QUERIES_MAX]


def wider(today: dt.date, live_employers: list[str], watch: list[dict] | None = None,
          qs: list[str] | None = None) -> list[str]:
    """The wider searches the news reader runs in the same round as today's, all at once, each
    with no month, so last week's and last month's news is found (a
    "November 2026" search on the 2nd finds almost nothing): what the person's list watches
    that today's searches leave out first, as a new subject brings new items, then the
    employers in play, then the rest of the list. Only as many as keep the reader within
    SEARCHES_MAX."""
    watch = watch_list() if watch is None else watch
    qs = list(qs or [])
    room = SEARCHES_MAX - len(qs)
    if room <= 0 or not qs:
        return []
    rest = resting(today)
    watch = [w for w in watch if w["what"].lower() not in rest]
    due = {w["what"] for w in watch if _dated(w["what"], today) in qs}
    where = home_place()
    out = [w["what"] for w in watch if w["what"] not in due]
    if "employers" not in set(setting("leave_out")):
        out += ["%s%s news" % (n, " " + where if where else "") for n in live_employers[:2]]
    # The local job market, which has news every week: widening only by the same employers
    # and watched things found nothing new three mornings running (2026-11-03).
    if where:
        out += ["%s job market news" % where, "%s hiring layoffs this week" % where]
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
        # The furthest stage wins, whatever order the rows are in (the release review).
        if k and st in set(throttle.LIVE_PROCESS) and stage.get(k) in (None, "applied"):
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


def numbered(qs: list[str], wide: list[str], watch: list[dict], today: dt.date) -> list[dict]:
    """Today's searches and the wider ones as one numbered list for the reader's one round:
    {"n", "q", "what" (the watched thing it carries, or ""), "wider"}. Each item it returns
    starts with the number of the search that found it, so a watched thing that keeps finding
    nothing new can rest (note_found)."""
    whats = {}
    for w in watch or []:
        whats.setdefault(_dated(w["what"], today), w["what"])
        whats.setdefault(w["what"], w["what"])
    out = []
    for wider_, group in ((False, qs), (True, wide)):
        for q in group:
            out.append({"n": len(out) + 1, "q": q, "what": whats.get(q, ""), "wider": wider_})
    return out


def numbered_text(searches: list[dict], wider_: bool) -> str:
    return " | ".join("[%d] %s" % (x["n"], x["q"]) for x in searches if bool(x["wider"]) is wider_)


def searched_whats(qs: list[str], watch: list[dict], today: dt.date) -> list[str]:
    """Which watched things the searches handed on carry, to note them as searched."""
    return [w["what"] for w in watch if _dated(w["what"], today) in qs]


def links_sent(paths: list[str]) -> list[str]:
    """Every link the news sections of the briefs of the last four weeks carried, so none is
    sent twice: the news widens back a month, and with only the last two briefs read, a link
    sent three briefs ago came back as new (the release review, 2026-11-02)."""
    out = []
    days = [(_d(os.path.basename(p)[:10]), p) for p in paths]
    newest = max((d for d, _p in days if d), default=None)
    for d, p in days:
        if newest and d and (newest - d).days > CARRY_DAYS:
            continue
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
                more = re.match(r"\s*(?:\.\.\.|…)\s*and (\d+) more\b", nxt)
                if more:
                    # The sync lists twenty and counts the rest on one line: an update of 103
                    # changes read "and 19 more" (X-70).
                    got["more"] = int(more.group(1))
                    break
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
    # The person's work that has waited off master a day or more (land.stranded): every
    # landing brings in what waits, so only work something keeps out is named, never a branch
    # a landing an hour ago left for the next one to bring in, and the line every morning was
    # never true for long (X-30).
    try:
        import land
        branches = " ".join(land.stranded(ROOT))
    except Exception:  # noqa: BLE001  the brief goes on; the next run looks again
        branches = ""
    with open(sync_log_path(), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("date: %s\nexit: %d\nearlier: %s\nsetup: %s\n---\n%s%s"
                 % (today.isoformat(), r.returncode, branches, setup, r.stdout or "",
                    r.stderr or ""))
    # What the update check printed goes to the log, never to the run: the step that brings
    # the person's own tests in line after an update is said here first, before any work,
    # while they still fail (a person's copy, 2026-11-05).
    step = subprocess.run([py, "-c", "import sys; sys.path.insert(0, %r); import app; "
                           "print(app.own_tests_first())" % _HERE], cwd=ROOT, text=True,
                          capture_output=True, encoding="utf-8", errors="replace")
    if step.returncode == 0 and step.stdout.strip():
        sys.stdout.write(step.stdout.strip() + "\n\n")
        sys.stdout.flush()
    url = page_url()
    if url and "--page-applied" not in argv and not setup_waiting():
        sys.stdout.write(page_first(url, argv))
        return 0
    return subprocess.run([py, os.path.abspath(__file__)] + argv, cwd=ROOT).returncode


def setup_waiting() -> str:
    """The page's link while setup waits on the person (a page, and setup not finished), else
    "": then the run is the one setup reminder, and its whole message says so."""
    url = page_url()
    if not url:
        return ""
    try:
        import app_setup
        return "" if app_setup._finished() else url
    except Exception:  # noqa: BLE001  cannot tell: the brief runs as usual
        return ""


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
    # Nothing is counted from before the person set up, and nothing "has not gone out in 14
    # days" for someone who started two days ago (X-72).
    set_up_on = setup_day()
    if set_up_on and since < set_up_on <= today:
        since = set_up_on
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
    if write:
        # Each clean draft is also where the page's Messages shows it, so To do opens it and
        # never asks for it again (2026-11-04: the pack alone reached no screen).
        followup_drafts.keep_drafted(got)

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
    lead = _lead(counts, replies, nudges_due, sent_lately, warm, owned, today, set_up_on)

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
        more = len(sync["changed"]) - 1 + int(sync.get("more") or 0)
        lines.append("Updated: %s%s." % (sync["changed"][0].rstrip(". "),
                                         ", and %d more" % more if more > 0 else ""))
    if brk.get("over"):
        lines.append(brk["over"])
    lines += _lapsed_asks(got, since, today)
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
    page = page_url()
    new = bool(set_up_on) and (today - set_up_on).days < QUIET_DAYS
    three = _next_three(got, counts, replies, unconfirmed(tracker, today), preps, export_line,
                        profile_line, sent_lately, warm, today, page=bool(page), new=new)
    where = _where_once(write)
    if where:
        lines.append(where)

    live_names = _live_employers(tracker, contacts, threads, today)
    claude_md = _profile_text("CLAUDE.md")
    watch = watch_list()
    qs = queries(today, live_names, watch)
    wide = wider(today, live_names, watch, qs)
    searches = numbered(qs, wide, watch, today)
    b = {
        "date": iso, "weekday": today.strftime("%A"), "since": since.isoformat(),
        "counts": {"owed": len(live), **{k: v for k, v in counts.items() if k != "processes"}},
        "since_counts": since_counts, "lead": lead,
        "owed": [_owed_line(i) for i in live],
        "set_aside": _set_aside(asks, old, held),
        "lines": lines, "next_three": three,
        "drafts": got, "pack": pack, "closed": closed, "preps": preps,
        "queries": qs, "wider": wide, "watch": watch, "searches": searches,
        "in_play": in_play(tracker, contacts, threads, live_names), "watch_due": watch_needs_writing(claude_md),
        "language": news_language(person.country()),
        "what_counts": what_counts(claude_md, watch), "skip_links": links_sent(earlier),
        "sync": sync, "export_line": export_line, "profile_line": profile_line,
        "write_here": followup_drafts.to_write_here(got),
        "url": _brief_url(iso), "page": page, "tip": "", "written": write,
        "paused": brk.get("until", "") if brk and brk.get("until", "") > iso else "",
        # Said in a chat's short message too, where a page holds the rest.
        "back": BACK_SAID if (brk or {}).get("over") else "",
    }
    if write:
        b["tip"] = _tip(today)
        write_record(b)
        if setting("news") and not b["paused"]:
            plan_searched(searched_whats(qs, watch, today), today, searches)
    return b


_NOTE_DAY = re.compile(r"(?:^|[|;]\s*)(\d{4}-\d{2}-\d{2}):\s*([^|;]*)")
STAGE_NOTE = "(from the application's record)"


def _person_note_day(notes: str) -> str:
    """The day of the row's last note that is not the app's own (a news line the brief noted,
    a stage this upkeep wrote): those are written after the fact, and a news note on 30 October
    hid a test ticked done for the 29th (the release review, 2026-11-02)."""
    days = [m.group(1) for m in _NOTE_DAY.finditer(notes or "")
            if not m.group(2).lstrip().startswith("news:") and STAGE_NOTE not in m.group(2)]
    return max(days or [""])


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
        written = _person_note_day(notes)
        folder, _files, stages = open_actions.stages(r)
        # Only a ticked box on the record's checklist: a hand-written record's dated heading is
        # read as done once its day has passed, and "Final interview - 30 Oct (cancelled by them)"
        # was written as done (the release review, 2026-11-02).
        if not re.search(r"^##\s*Interview stages reached\s*$", _read(os.path.join(folder, "outcome.md")),
                         re.M | re.I):
            continue
        for st in stages:
            day = st.get("date") or ""
            if not st.get("done") or not _d(day) or day <= written or _d(day) > today:
                continue
            line = "%s: %s done %s" % (day, st["label"].rstrip(" :"), STAGE_NOTE)
            if line not in notes:
                notes = (notes.rstrip() + " | " + line).strip(" |")
                added.append(str(r.get("company") or ""))
        r["notes"] = notes
    if added:
        csv_store.write_rows(path, rows, csv_store.header(path))
    return list(dict.fromkeys(added))


BACK_SAID = "Welcome back: your break is over."


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


def _soonest(procs, today: dt.date) -> tuple:
    """(row, stage) of the process whose next step comes first: a round booked for a day, or
    a day still to choose by the day to answer by. Tracker order put a process with nothing
    booked ahead of an interview that evening (the audit, 2026-11-03)."""
    import open_actions
    best = (None, {})
    key = None
    for r in procs:
        _f, _files, stages = open_actions._stages(r)
        for st in stages:
            if st.get("done"):
                continue
            day = _d(st.get("date"))
            offered = [_d(x) for x in st.get("offered") or [] if _d(x) and _d(x) >= today]
            when = day if day and day >= today else (
                min([_d(st.get("reply_by"))] + offered[:1]) if offered and _d(st.get("reply_by"))
                else (offered[0] if offered else None))
            if when and (key is None or (when, st.get("time") or "") < key):
                key, best = (when, st.get("time") or ""), (r, st)
    return best if best[0] is not None else ((procs[0], {}) if procs else (None, {}))


def setup_day() -> dt.date | None:
    """The day setup finished (profile/place.json, setup.finished), or None."""
    try:
        with open(person.path("place.json"), encoding="utf-8") as fh:
            got = json.load(fh)
        return _d(str(((got or {}).get("setup") or {}).get("finished") or "")[:10])
    except (person.NoProfile, OSError, ValueError, AttributeError):
        return None


def _where_once(write: bool) -> str:
    """Once, on the first brief after this update or after it is made: where the brief comes
    and when, so a person whose brief posts into a chat they never reopen is told where it is
    (X-1, X-11). Never a promise of a push."""
    try:
        import routines
        return routines.where_once(write)
    except Exception:  # noqa: BLE001  no registry: nothing to say
        return ""


def _lead(counts, replies, nudges_due, sent_lately, warm, owned, today, set_up_on=None) -> str:
    procs = counts["processes"]
    if procs:
        r, st = _soonest(procs, today)
        company = (r.get("company") or "").strip()
        more = " (and %d more)" % (len(procs) - 1) if len(procs) > 1 else ""
        label = (st.get("label") or "next round").strip()
        label = label[:1].upper() + label[1:]
        if st.get("offered") and not st.get("date"):
            import open_actions
            by = _d(st.get("reply_by"))
            return "%s: choose your %s day (%s) and tell them%s." % (
                company, label[:1].lower() + label[1:],
                open_actions._days_said([x for x in st["offered"] if x >= today.isoformat()]),
                ", by %s" % _weekday(by) if by else "")
        if st.get("date"):
            day = _d(st["date"])
            when = ("today" if day == today else "tomorrow" if day == today + dt.timedelta(days=1)
                    else "on %s" % _weekday(day))
            return "%s with %s is %s%s%s. Your prep is on your page." % (
                label, company, when, " at %s" % st["time"] if st.get("time") else "", more)
        # An employer whose own chat runs its process: the chat is Claude's to know, never
        # named to the person ("its own chat (... campaign (this chat))", the audit).
        return "Your %s process is live%s. Your prep is on your page." % (company, more)
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
        warm_said = " Warm routes already in your contacts: %s." % routes if routes else ""
        days = (today - set_up_on).days if set_up_on and set_up_on <= today else QUIET_DAYS
        if days <= 1:
            return ("Your search is set up.%s A fresh shortlist is one \"find me jobs\" away."
                    % warm_said)
        return ("Nothing has gone out in %d days.%s A fresh shortlist is one \"find me jobs\" away."
                % (min(QUIET_DAYS, days), warm_said))
    return "Nothing is owed today."


def _weekday(day) -> str:
    """"Wed 4 Nov"."""
    return "%s %d %s" % (day.strftime("%a"), day.day, day.strftime("%b")) if day else ""


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


def _lapsed_asks(items, since, today) -> list[str]:
    """A request for the resume closed by itself since the last brief (open_actions,
    state.RESUME_ASK_LAPSE_DAYS), said once, on the brief after it closed."""
    out = []
    for i in items:
        on = _d(i.get("lapsed_on"))
        if on is None or not (since < on <= today):
            continue
        who = str(i.get("name") or "").split(" (")[0] or "Someone"
        asked = _d(i.get("asked") or i.get("since"))
        out.append("Closed by itself: %s's request for your %s%s, with nothing from them since. "
                   "It stays on their card in Contacts, and a word from them opens it again."
                   % (who, _noun(), " (asked %d %s)" % (asked.day, asked.strftime("%b")) if asked else ""))
    return out


def _set_aside(asks, old, held) -> list[str]:
    out = []
    if asks:
        out.append("%d connection request%s nobody accepted: withdraw them on LinkedIn"
                   % (len(asks), "" if len(asks) == 1 else "s"))
    if old:
        out.append("%d owed over 45 days with nothing done, set aside" % len(old))
    if held:
        out.append("%d held for now (an interview, a referral, your own note or your own rules)"
                   % len(held))
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


def _on_page(item) -> bool:
    """Is a message to this contact drafted where the person reads and sends it: Messages on
    their page (documents/network/<contact>/draft.md)? The brief said "it is drafted for you"
    of a reply that sat only in this brief's own pack, which cannot be copied or marked sent,
    while Messages had nothing (2026-11-03)."""
    cid = str(item.get("contact_id") or "").strip()
    return bool(cid) and os.path.isfile(person.state("documents", "network", cid, "draft.md"))


def _linkedin_on_file() -> bool:
    try:
        with open(person.path("person.json"), encoding="utf-8") as fh:
            got = json.load(fh)
        return bool(str(((got or {}).get("identity") or {}).get("linkedin") or "").strip())
    except (person.NoProfile, OSError, ValueError, AttributeError):
        return True


def _next_three(got, counts, replies, drafted, preps, export_line, profile_line, sent_lately,
                warm, today, page: bool = True, new: bool = False) -> list[str]:
    """Exactly three things to do before the next brief, most valuable first, each one line
    and under half an hour. With no page, each says the words to use in a chat, never a
    button they do not have (X-68). In the first fortnight after setup, a search comes before
    the question about their own LinkedIn profile, which is asked as whether they have one
    when none is on file (X-72)."""
    out: list[str] = []
    seen: set = set()
    find_jobs = ("Find new jobs: Jobs, Find jobs." if page else
                 "Find new jobs: say \"find me jobs\".")
    find_people = ("Find people at an employer you want: Contacts, Find people." if page else
                   "Find people at an employer you want: say \"who should I talk to at "
                   "<employer>?\".")
    watch = ("Watch an employer you would love to work at (Jobs, Change the search), and "
             "Claude reads its own jobs every search." if page else
             "Name an employer you would love to work at, and Claude reads its own jobs every "
             "search.")

    def add(key, text):
        if key not in seen and len(out) < 3:
            seen.add(key)
            out.append(text)

    live = [i for i in got if not i.get("held") and not i.get("quiet") and not i.get("old")]
    # An interview's own first, whatever else is owed: the day to choose, the prep before it,
    # the thank-you after it (the audit, 2026-11-03: the thank-you came after every reply).
    for i in live:
        if i.get("kind") == "interview" and i.get("sub") == "choose":
            add(i.get("key"), "%s: %s." % (i["name"].split(" (")[0], i["what"]))
    for i in live:
        if i.get("kind") == "interview" and "no pack yet" in (i.get("what") or ""):
            add(i.get("key"), "Prepare for your interview at %s, %s." % (
                i["name"].split(" (")[0], i["what"].split(" (")[0].replace("interview ", "", 1)))
    for i in live:
        if i.get("kind") == "interview" and "thank-you" in (i.get("what") or ""):
            add(i.get("key"), "Send the thank-you after your interview at %s."
                % i["name"].split(" (")[0])
    for i in replies:
        who = i.get("name", "")
        if _noun() + " owed" in (i.get("what") or "") or i.get("kind") == "resume":
            add(i.get("key"), "Send %s the %s they asked for." % (who, _noun()))
        elif _on_page(i):
            add(i.get("key"), "Send your reply to %s: it is drafted for you." % who)
        else:
            add(i.get("key"), "Reply to %s." % who)
    for i in live:
        if _on_page(i) and i.get("kind") in ("nudge", "first_message") \
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
    if new and not sent_lately:
        add("search", find_jobs)
    if profile_line:
        m = re.search(r"\"([^\"]+)\"", profile_line)
        if m:
            ask = m.group(1)
            if not _linkedin_on_file() and "LinkedIn profile" in ask:
                ask = ("If you have a LinkedIn profile, want me to look it over once, for "
                       "anything that would stop people replying?")
            add("own_profile", ask)
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
        add("search", find_jobs)
    if counts.get("applications"):
        add("outcome", "Heard back from anyone? Mark it on the application." if page else
            "Heard back from anyone? Tell me, and I'll mark it on the application.")
    add("search", find_jobs)
    add("network", find_people)
    add("targets", watch)
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


def _n(n: int, one: str, many: str) -> str:
    return "%d %s" % (n, one if n == 1 else many)


def since_line(b: dict) -> str:
    s = b["since_counts"]
    extra = "".join(", " + _n(s[k], one, many) for k, one, many in (
        ("offers", "offer", "offers"), ("rejections", "rejection", "rejections")) if s[k])
    return "Since %s: %d sent, %s, %s%s" % (
        _short_date(b["since"]), s["sent"], _n(s["replies"], "reply", "replies"),
        _n(s["interviews"], "interview", "interviews"), extra)


def _short_date(iso: str) -> str:
    d = _d(iso)
    return "%d %s" % (d.day, d.strftime("%b")) if d else iso


def message_lines(b: dict, owed_max: int = 4) -> list[str]:
    """The message as a phone shows it, news left for the model to put in. With a page, the
    chat gets the headline, the lead and the link: the page holds the rest, and a chat that
    posted the whole brief beside it said everything twice (the maintainer, 2026-11-04)."""
    if b.get("paused"):
        return ["Your search is paused until %s. Nothing is chased meanwhile." % _short_date(
            b["paused"])] + (["Your page: " + b["url"]] if b.get("page") else [])
    asks = len((b.get("sync") or {}).get("questions") or [])
    asked = ["", "%d question%s wait%s for you on your page." % (
        asks, "" if asks == 1 else "s", "s" if asks == 1 else "")] if asks else []
    if b.get("page"):
        return [headline(b), b["lead"]] + ([b["back"]] if b.get("back") else []) + asked + [
            "", "Your page: " + b["url"]]
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
    if b["url"]:
        out += ["", "Full brief: " + b["url"]]
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


PUSH_MAX = 199          # PushNotification: "Keep it under 200 characters; mobile OSes truncate"


def push_line(b: dict) -> str:
    """The one plain line the run sends as a push at its end: the most pressing thing (the
    message's lead), and the page's link where there is a page, under 200 characters."""
    if b.get("waiting"):
        text = "Your job search setup is waiting for you on your page."
    elif b.get("paused"):
        text = "Your search is paused until %s." % _short_date(b["paused"])
    else:
        text = b.get("lead") or (headline(b) if b.get("counts") else "Your brief is ready.")
    tail = (" " + b["page"]) if b.get("page") else ""
    room = PUSH_MAX - len(tail)
    if len(text) > room:
        text = text[:room - 1].rsplit(" ", 1)[0].rstrip(",;:") + "…"
    return text + tail


def push_wanted() -> bool:
    """Did the person choose a phone notification for their brief? Off unless they did
    (person.json `brief_push`, Settings' "Phone notification"; the maintainer, 2026-11-04:
    "make it off by default but maybe part of the setup"). A copy that never answered and
    whose brief already sent one (pushed_before) keeps it: it stopped the day such a copy
    took the update otherwise (the engine review, 2026-11-05)."""
    try:
        import person
        said = person.get("brief_push", None)
    except Exception:  # noqa: BLE001  no profile: nobody chose one
        return False
    if said is None:
        return pushed_before()
    return str(said or "off").strip().lower() == "on"


def pushed_before() -> bool:
    """A day's record says the brief's own run sent the person a push (pushed): what a brief
    did every morning before the notification became a choice."""
    try:
        folder = person.state(*BRIEFS)
        names = sorted(n for n in os.listdir(folder) if n.endswith(".md"))
    except Exception:  # noqa: BLE001  no records, or no profile
        return False
    for n in reversed(names):
        try:
            with open(os.path.join(folder, n), encoding="utf-8", errors="replace") as fh:
                if "<!-- push: sent;" in fh.read():
                    return True
        except OSError:
            continue
    return False


def keep_push() -> str:
    """Write the push the brief already sent into person.json as their setting ("on"), so
    Settings shows what happens (the brief-push-kept upgrade); nothing where they answered."""
    import person
    if person.get("brief_push", None) is not None:
        return "brief: the phone notification is set already; nothing changed"
    if not pushed_before():
        return "brief: the brief has sent no phone notification; nothing changed"
    person.put(["brief_push"], "on")
    return "brief: the phone notification the brief already sent stays on"


def push_due(b: dict) -> bool:
    """Does this run send the person a push itself? Only when they chose one (push_wanted).
    A brief bound to a chat has no notification of its own (routines.brief_pushes_itself); a
    Routines-screen task and an older ops chat's relay send theirs, a brief asked for by hand
    is read in the chat, and a paused search sends nothing. The setup reminder always does."""
    if b.get("waiting"):
        return True
    if b.get("paused") or not push_wanted():
        return False
    try:
        import routines
        reg = routines.load()
        return routines._brief(reg) is not None and not routines.brief_pushes_itself(reg)
    except Exception:  # noqa: BLE001  no registry: a brief asked for by hand
        return False


def push_step(b: dict) -> str:
    """The one place a run is asked to push (the builder's decision of 3 November: the brief
    stays bound to the chat with the copy and sends its headline itself): just before the
    landing, so what the push answered is saved with the day's record. Nothing promises it
    reaches a phone; where it was not sent, the person's next message in this chat says so,
    once (unsent_line)."""
    if not push_due(b):
        return ""
    return ("push, before step 6: PushNotification (ToolSearch select:PushNotification) with "
            "%s, then python3 tools/brief.py pushed \"<its answer>\"; whatever it answers, "
            "never mention it" % json.dumps(push_line(b), ensure_ascii=False))


# The words app_setup.start says for the same (the saving fix, X-30), so the person hears one.
UNSAVED_SAY = ("Some of your work from the last few days hadn't been saved yet. I'm saving it "
               "now.")
_PUSH_MARK = re.compile(r"\n*<!-- push: (sent|not sent); chat: (\S*) -->\n?")
PUSH_SAID = "ljs-brief-push-said.txt"     # in the git folder: the day already said, never committed


def pushed(answer: str, today: dt.date | None = None) -> str:
    """What the run's PushNotification answered, noted on the day's record (saved with it by
    the landing that follows), so the person's next message in this chat can say it was not
    sent (unsent_line). A cloud run was answered "Mobile push requested."; anything saying
    "not sent", or an error, is not sent."""
    today = today or dt.date.today()
    path = brief_path(today.isoformat())
    if not os.path.exists(path):
        return "brief: no record of today's brief to note the push on"
    sent = not re.search(r"\bnot sent\b|\berror\b|\bfail|\bno such tool\b|\bunavailable\b",
                         answer or "", re.I)
    try:
        import app_listen
        chat = app_listen.this_chat()
    except Exception:  # noqa: BLE001
        chat = ""
    text = _PUSH_MARK.sub("\n", _read(path)).rstrip("\n")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("%s\n\n<!-- push: %s; chat: %s -->\n" % (text, "sent" if sent else "not sent",
                                                           chat or "-"))
    return "brief: the push was %s; noted on today's record" % ("sent" if sent else "not sent")


def unsent_line(chat: str, today: dt.date | None = None) -> str:
    """For the person's next message in the chat a brief ran in, once: where the brief is,
    when its push was not sent (the builder's decision of 3 November). "" otherwise, in any
    other chat, and once said."""
    today = today or dt.date.today()
    if not str(chat or "").startswith("session_"):
        return ""
    for back in (0, 1):
        day = (today - dt.timedelta(days=back)).isoformat()
        m = _PUSH_MARK.search(_read(brief_path(day)))
        if not m:
            continue
        if m.group(1) != "not sent" or m.group(2) != chat:
            return ""
        said = os.path.join(os.path.dirname(sync_log_path()), PUSH_SAID)
        if _read(said).strip() == day:
            return ""
        try:
            with open(said, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(day + "\n")
        except OSError:
            return ""
        where = " and on your page" if page_url() else ""
        return ("Tell the person once, at the start of your reply, in these words: \"Your "
                "morning brief is earlier in this chat%s; %s notification could not be sent to "
                "your phone.\"" % (where, "today's" if back == 0 else "yesterday's"))
    return ""


def _computer_lines(b: dict) -> list[str]:
    """The computer side, for someone who works on one (tools/computer.py): its daily check
    against the page's database, and the week's runs as measured, once a week (Mondays)."""
    try:
        import computer
        import place
        if place.works_on() not in ("computer", "both") and not place.has_local():
            return []
        today = _d(b.get("date")) or dt.date.today()
        trend = computer.trend(today) if today.weekday() == 0 else ""
    except Exception:  # noqa: BLE001  a check never stops the brief
        return []
    out = ["computer: python3 tools/computer.py check <page work+beats> --envs "
           "<list_environments saved> --triggers <list_triggers saved>; do each line"]
    if trend:
        out.append(f"the computer's week, one line at the end of the message: \"{trend}\"")
    return out


def claude_lines(b: dict) -> list[str]:
    """For the model only: what it acts on. Never in the message."""
    s = b["sync"] or {}
    out = []
    if b.get("paused"):
        return ["paused until %s: the message is the line above, as it is; no news search, no "
                "drafts, nothing else to do or save" % b["paused"]] + [
                    x for x in [push_step(b)] if x]
    if not s and b.get("written"):
        out.append("the start did not run today: run python3 tools/brief.py --start --on "
                   "\"<model>\" --write")
    if s.get("blocked"):
        out.append("job sites are blocked: the message opens with the line above about it")
    if s.get("exit"):
        out.append("the update check stopped (exit %d): %s" % (s["exit"], s.get("first", "")[:160]))
    if s.get("setup"):
        out.append("setting up the Python side failed: %s" % s["setup"])
    if s.get("earlier"):
        # Only work off master a day or more (land.stranded), said once a day at most (X-30).
        out.append("the person's work has waited off their saved copy a day or more (%s): this "
                   "run's landing brings it in; not green, fix what its check names and land "
                   "again. At the end of the message, the line: \"%s\"" % (
                       " ".join(s["earlier"]), UNSAVED_SAY))
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
    out += _computer_lines(b)
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
        searches = b.get("searches") or numbered(b["queries"], b.get("wider") or [], [],
                                                 _d(b["date"]) or dt.date.today())
        out.append("news: the news-reader agent, given these searches: %s; at most %d item%s in the "
                   "message%s" % (
                       numbered_text(searches, False), n, "" if n == 1 else "s",
                       "; news in the language %s counts as much as in English" % b["language"]
                       if b.get("language") else ""))
        today = _d(b["date"]) or dt.date.today()
        week, month = (today - dt.timedelta(days=d) for d in WIDEN_DAYS)
        wide = numbered_text(searches, True)
        out.append("news, one round: today is %s; every search at once, in parallel, then %d to "
                   "%d items, newest and most relevant first, each story once, each opening with "
                   "its search's [n]; the wider back to %s, then %s%s" % (
                       today.isoformat(), NEWS_MIN, NEWS_MAX, week.isoformat(),
                       month.isoformat(), "; the wider: " + wide if wide else ""))
        if b.get("in_play"):
            out.append("news, in play (for how to use each item, never searched): "
                       + "; ".join(b["in_play"]))
    else:
        out.append("news: run no news search (%s)" % (
            "none in the message, by the person's setting" if not n else
            "the profile does not say enough yet for one"))
    out.append("since %s; links already sent: %s" % (
        b["since"], " ".join(b["skip_links"][-20:]) or "none"))
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
        out.append("the page, once the news is recorded (step 4): ArtifactData query, url %s, "
                   "collections screen, meta, addr, work and beats, out_dir <D>, limit 1000; "
                   "python3 tools/app.py view <D>/view --dump <D> --chat brief; send every batch "
                   "it prints, and do any for_claude line it prints at once, unasked (a fresh "
                   "helper when the helper's day is up or work waits that no chat is awake to "
                   "take: this run starts it). Then python3 tools/computer.py waiting <D>; "
                   "under queued: list_environments, saved to a file, then python3 "
                   "tools/computer.py route <D> --chat <this chat's id> --envs <that file> "
                   "--tools \"<this chat's tool names, comma separated>\", and do what it prints "
                   "(it wakes the chat that starts chats on the computer, or makes it once). "
                   "Then the app skill's steps 1 to 3, for work still waiting" % b["page"])
    try:
        import routines
        owed = routines.calls(today=b.get("date") or "")
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
        # Judged once, an employer that clears nothing stops filling the person's To do. Only
        # where the person's own profile states a bar (bar.applies): unjudged_contacts is
        # empty otherwise, and nobody is judged on words they never said (X-18).
        out.append("judge each employer once, from what you know of it (pay, prestige, signal "
                   "or none), with python3 tools/bar.py judge \"<employer>\" <verdict> \"<why>\": "
                   + "; ".join(names[:8]) + ("; and %d more (bar.py unjudged --contacts)"
                                              % (len(names) - 8) if len(names) > 8 else ""))
    push = push_step(b)
    if push:
        out.append(push)
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
    planned = (_watched_file().get("_planned") or {})
    searches = planned.get("searches") if planned.get("day") == today.isoformat() else None
    note_searched(None, today)
    items, tags = [], []
    for ln in text.splitlines():
        s = ln.strip()
        if not s or s.lower().startswith(("quiet week", "nothing new", "none", "no news")):
            continue
        s = s.lstrip("-*• ").strip()
        m = _TAG.match(s)
        if m:
            s = s[m.end():].lstrip("-*• ").strip()
        if s:
            items.append(s)
            tags.append([int(x) for x in re.findall(r"\d+", m.group(1))] if m else [])
    # Earlier briefs only: today's own record is replaced below, and counting it sent every
    # item of a second run that day as already sent (the release review, 2026-11-02).
    seen = set(links_sent(earlier_briefs(today)))
    kept, dropped, ruled, found_by = [], [], [], []
    same: dict = {}
    for s, tag in zip(items, tags):
        links = [u.rstrip(".,;") for u in _LINK.findall(s)]
        if links and any(u in seen for u in links):
            dropped.append(s)
            continue
        # One story once: the reader ran every search at once, and two of them can find it;
        # each search that found it is counted as having found something.
        key = tuple(sorted(links)) or (re.sub(r"\W+", " ", s.lower()).strip(),)
        if key in same:
            if same[key] is not None:
                found_by[same[key]] = found_by[same[key]] + tag
            continue
        same[key] = None
        # The person's own exclusions, as the job round applies them: news about an employer
        # kind they ruled out is no use to them (the maintainer's brief, 2026-11-10).
        why = ruled_out(s)
        if why:
            ruled.append(s)
            continue
        same[key] = len(found_by)
        found_by.append(tag)
        if len(kept) < NEWS_MAX:
            kept.append(news_as_of(s, today))
    # Which watched things found something new: only from a reader that numbered its items,
    # and never from one that returned nothing (it may not have run at all).
    if searches and any(tags):
        found: dict = {}
        for x in searches:
            if x.get("what"):
                found.setdefault(x["what"], 0)
        for tag in found_by:
            for n in tag:
                x = next((y for y in searches if y.get("n") == n), None)
                if x and x.get("what"):
                    found[x["what"]] = found.get(x["what"], 0) + 1
        note_found(found, today)
    path = brief_path(today.isoformat())
    body = _read(path)
    carried, day = ([], "") if kept else carry_news(today)
    # Fewer than NEWS_MIN new: the newest earlier items fill it to NEWS_MIN, after a line
    # that says so. One point on its own read as an empty panel (the maintainer, 2026-11-03).
    more = carry_news(today, NEWS_MIN - len(kept), skip=kept)[0] if 0 < len(kept) < NEWS_MIN else []
    if kept:
        news = [NEWS_SOURCE, ""] + ["- " + s for s in kept] + (
            ["", NEWS_ALSO, ""] + ["- " + s for s in more] if more else [])
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
            "carried": carried, "carried_from": day, "ruled_out": ruled}


_TAG = re.compile(r"^\[(\d+(?:\s*,\s*\d+)*)\]\s*")


def ruled_out(line: str) -> str:
    """Why a news item is about an employer or a kind of employer the person ruled out, or "":
    the same hard rules the job round applies by name (tools/bar.py excluded_by_name: a sector
    they will not work in, an employer they declined, a public body they named), read in what
    the item says happened. Public bodies in general are not read here: a government's change
    to the right to work is news they need."""
    m = _ITEM_SOURCE.search(line) or _UNDATED_SOURCE.search(line)
    what = line[:m.start()] if m else line
    try:
        import bar
    except Exception:  # noqa: BLE001  no profile to read the rules from: nothing ruled out
        return ""
    for rx, why in bar.EXCLUDED_RULES:
        if rx.search(what):
            return why
    low = " %s " % re.sub(r"\W+", " ", what.lower())
    for k, why in bar.DECLINED.items():
        name = re.sub(r"\W+", " ", str(k).lower()).strip()
        if name and " %s " % name in low:
            return why
    if bar.NAMED_PUBLIC.search(what):
        return bar._NAMED_WHY
    return ""


def news_items(text: str) -> list[str]:
    """A brief record's news lines, as written, without their bullets."""
    return [ln[2:].strip() for ln in _section(text, "News").splitlines()
            if ln.startswith("- ") and ln[2:].strip()]


NEWS_ALSO = "Also from earlier briefs."


def gathered_news(text: str) -> list[str]:
    """The news a brief's own search found, never what it carried from an earlier one, so a
    carried item is never renewed by being carried again (news from 1 October read as from
    10 November on the 25th, the release review)."""
    sec = _section(text, "News")
    if _CARRIED.search(sec):
        return []
    out = []
    for ln in sec.splitlines():
        if ln.strip() == NEWS_ALSO:
            break
        if ln.startswith("- ") and ln[2:].strip():
            out.append(ln[2:].strip())
    return out


def carry_news(today: dt.date, need: int = NEWS_MAX, skip=(), paths=None) -> tuple[list[str], str]:
    """Up to `need` news items the briefs of the last CARRY_DAYS found, newest first, none
    already in `skip` by its words or its link, and the day the newest of them was found:
    what a brief whose reader brought nothing new shows instead of an empty panel. It reached
    back to one brief only, so one old point stood alone for days (2026-11-03)."""
    items, day = [], ""
    texts = set(skip)
    links = {u.rstrip(".,;") for s in skip for u in _LINK.findall(s)}
    for p in reversed(earlier_briefs(today) if paths is None else list(paths)):
        d = _d(os.path.basename(p)[:10])
        if not d or (today - d).days > CARRY_DAYS:
            break
        for s in gathered_news(_read(p)):
            got = {u.rstrip(".,;") for u in _LINK.findall(s)}
            if s in texts or got & links or ruled_out(s):
                continue
            texts.add(s)
            # A line written without its day keeps the day it was found, so a carried point
            # never reads as today's (the release review, 2026-11-03).
            s = news_as_of(_UNDATED_SOURCE.sub(r"(\1, %s, \2)" % d.isoformat(), s, count=1),
                           today)
            items.append(s)
            texts.add(s)
            links |= got
            day = day or d.isoformat()
            if len(items) >= need:
                return items, day
    return items, day


_CARRIED = re.compile(r"Carried from the brief of (\d{4}-\d{2}-\d{2})")
_UNDATED_SOURCE = re.compile(r"\(([^(),]{2,80}),\s*(https?://[^\s()]+)\)")

# An item's time words count from the day its piece was dated, so a brief later than that day
# says what they meant: the brief of 4 November said an employer "has a product launch event
# next week" from a piece of 28 October, when that week had already come (the maintainer,
# 2026-11-04). Only what happened is read this way; how to use it is the reader's, today's.
_ITEM_SOURCE = re.compile(r"\((?P<src>[^()]{2,80}?),\s*(?P<date>\d{4}-\d{2}-\d{2})"
                          r"(?:,\s*(?P<url>https?://[^\s()]+))?\)")
_WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
_SOON = r"(early |late |later |earlier )?"


def _month_name(d: dt.date, n: int) -> str:
    y, m = divmod(d.month - 1 + n, 12)
    return dt.date(d.year + y, m + 1, 1).strftime("%B")


def news_as_of(line: str, today: dt.date) -> str:
    """A news line whose piece is dated before `today`, its time words ("next week",
    "tomorrow", "this month") written against that date instead; any other line as it is."""
    m = _ITEM_SOURCE.search(line)
    d = _d(m.group("date")) if m else None
    if not d or d >= today:
        return line
    what = line[:m.start()]

    def day(n: int) -> str:
        return _short_date((d + dt.timedelta(days=n)).isoformat())
    weekday = "|".join(_WEEKDAYS)
    subs = (
        (r"\blater today\b", "later on " + day(0)),
        (r"\btoday's\b", day(0) + "'s"),
        (r"\b(?:today|tonight)\b", day(0)),
        (r"\b(?:yesterday|last night)\b", day(-1)),
        (r"\btomorrow\b", day(1)),
        (r"\bthis weekend\b", "the weekend after " + day(0)),
        (r"\b%sthis week\b" % _SOON, r"\1in the week of " + day(0)),
        (r"\b%snext week\b" % _SOON, r"\1in the week after " + day(0)),
        (r"\blast week\b", "in the week before " + day(0)),
        (r"\b%sthis month\b" % _SOON, r"\1in " + _month_name(d, 0)),
        (r"\b%snext month\b" % _SOON, r"\1in " + _month_name(d, 1)),
        (r"\blast month\b", "in " + _month_name(d, -1)),
        (r"\b%sthis year\b" % _SOON, r"\1in %d" % d.year),
        (r"\b%snext year\b" % _SOON, r"\1in %d" % (d.year + 1)),
        (r"\blast year\b", "in %d" % (d.year - 1)),
        (r"\bthis (%s)\b" % weekday,
         lambda w: "%s %s" % (w.group(1).capitalize(), day(
             (_WEEKDAYS.index(w.group(1).capitalize()) - d.weekday()) % 7))),
        (r"\bnext (%s)\b" % weekday, lambda w: "the %s after %s" % (w.group(1).capitalize(),
                                                                    day(0))),
    )
    for pat, new in subs:
        what = re.sub(pat, new, what, flags=re.I)
    return what + line[m.start():]


def again_line(n: int, today: dt.date) -> str:
    """Nothing came back from the news reader: the chat searches again itself, once. On 4
    November it returned none, dropping every result whose date was not shown day by day,
    while three ordinary searches straight after found a results miss and a funding round
    from the week before (the maintainer, 2026-11-04)."""
    month = today - dt.timedelta(days=WIDEN_DAYS[1])
    return ("news: only %d came back, so search again yourself now, once (the one exception to "
            "\"nothing else finds the news\"): WebSearch each of the brief's news searches, then "
            "the wider ones; keep reporting dated back to %s, its "
            "date read from its title, its text or its link (a path like /%s/ or %s), or an age "
            "it states counted back from %s, never guessed; then python3 tools/brief.py news "
            "--again with every line, the earlier ones and the new, each as \"- <what happened> "
            "(<publisher>, <YYYY-MM-DD>, <link>). <how the person can use it>.\""
            % (n, month.isoformat(), today.strftime("%Y/%m/%d"), today.isoformat(),
               today.isoformat()))


def message_news(line: str) -> str:
    """A news line for the chat's message: its source and day kept, its link left out."""
    def short(m):
        return "(%s, %s)" % (m.group("src").strip(), _short_date(m.group("date")))
    line = _UNDATED_SOURCE.sub(r"(\1)", _ITEM_SOURCE.sub(short, line, count=1))
    return re.sub(r"\s*https?://[^\s()]+", "", line).strip()


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
                         important first (the first leads whenever it is due; one their
                         profile says outranks everything is first, every day), each as
                         often as it really changes: their right to
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
        live = _live_employers(tracker, contacts, threads, today)
        qs = queries(today, live, watch)
        searches = numbered(qs, wider(today, live, watch, qs), watch, today)
        plan_searched(searched_whats(qs, watch, today), today, searches)
        for x in searches:
            print("[%d] %s%s" % (x["n"], x["q"], " (wider)" if x["wider"] else ""))
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
        ap.add_argument("--again", action="store_true",
                        help="the lines after searching again: never asks for a third search")
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
        if lines and page_url():
            print("news: on the page with today's record; the message carries none")
        elif lines:
            print("for the message, the first %d, each with its day:" % setting("news"))
            for ln in lines[:setting("news")]:
                print("- " + message_news(ln))
        if got.get("ruled_out"):
            print("news: %d left out, about an employer or a kind of employer the person ruled "
                  "out" % len(got["ruled_out"]))
        # One search of the chat's own, only when the reader brought nothing at all: on 4 and
        # 10 November it came back empty while a plain search found three (2026-11-10).
        if not got["kept"] and not got.get("ruled_out") and setting("news") and not a.again:
            print(again_line(len(got["kept"]), _today(a.today)))
        return 0
    if argv[:1] == ["watch"]:
        return watch_main(argv[1:])
    if argv[:1] == ["pushed"]:
        print(pushed(" ".join(argv[1:])))
        return 0
    if argv[:1] == ["keep-push"]:
        print(keep_push())
        return 0
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
        # A copy that was reset (or never set up) with its scheduled tasks still on: said once,
        # and the run turns them off, rather than "no profile" every morning for good (X-81).
        print("Your job search was reset, so its morning brief is off now. Say \"set me up\" in "
              "any chat to start again.\n\nFOR CLAUDE\n- no profile here: list_triggers (every "
              "page) and turn off (update_trigger, enabled false) each task whose prompt starts "
              "\"Scheduled run:\" and names automation/prompts/, this one included; then the "
              "line above is the whole message. Nothing to save.")
        return 1
    waiting = setup_waiting()
    if waiting:
        # Setup not finished: the one reminder's whole message (X-23).
        b = {"waiting": True, "page": waiting}
        print("Your job search setup is waiting for you on your page: %s. Answer there, one "
              "question at a time; Claude does the rest.\n\nFOR CLAUDE\n- setup is not "
              "finished: the line above is the whole message; no news, nothing to save\n- %s"
              % (waiting, push_step(b)))
        return 0
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
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception as e:  # noqa: BLE001  one line for Claude naming the file, never a traceback
        # A profile file missing a setting broke every brief with a raw traceback (X-39).
        try:
            import app
            said = app.stopped_on(e)
        except Exception:  # noqa: BLE001  the plain line without the helper
            said = "brief: stopped: %s: %s" % (type(e).__name__, " ".join(str(e).split())[:240])
        print(said)
        raise SystemExit(1) from None
