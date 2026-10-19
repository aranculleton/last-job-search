#!/usr/bin/env python3
"""What the person has told the search about themselves, kept for good.

The app ships defaults for everything a person has not had a view on yet: the
voice of a first note, the questions an interview pack asks, who counts as worth
contacting, which roles rank high. Defaults are how anyone starts. But every time
the person reacts ("I don't like this message", "not this kind of company", "too
formal", "stop asking me that"), that reaction is worth more than any default, and
it was being lost: applied once in the chat, forgotten by the next session, and
open to the next sync or upgrade putting the default back.

So every reaction is recorded here, in profile/learned.json, which is the person's
file and which no sync touches:

    {"entries": [{"date": "2026-10-15", "area": "voice",
                  "said": "too formal, I'd never say 'I hope this finds you well'",
                  "rule": "plain and direct; no stock pleasantries",
                  "applied_to": ["profile/networking.py OPENER"],
                  "never_say": ["hope this finds you well"],
                  "status": "active"}]}

- `rule` is what is different from now on, in one sentence, read before drafting.
- `applied_to` names every setting the reaction changed. Those settings are the
  person's now: an upgrade or a redone /setup section never changes them
  (`locked()`), only an explicit new instruction from the person does.
- `never_say` phrases are enforced in code: tools/network/tone.py and
  tools/voice_check.py flag them in anything drafted, as `person_dislikes`.

    python3 tools/learned.py brief [area]        # the active rules, for a drafting step
    python3 tools/learned.py list [area]         # every entry, numbered
    python3 tools/learned.py record --area voice --said "..." --rule "..." \\
        [--applied-to "profile/networking.py OPENER"]... [--never-say "..."]...
    python3 tools/learned.py retire <n>          # they changed their mind
    python3 tools/learned.py locked              # the settings no upgrade may change
    python3 tools/learned.py offers              # app improvements waiting on their choice
    python3 tools/learned.py decide <n> keep|switch

**When the app learns something better.** A sync brings genuine fixes, and they
apply: they change code, not the person's settings. When an update would change a
setting the person has shaped (a better default voice, a sharper question set),
nothing changes behind their back and nothing is quietly ignored either: /upgrade
records an *offer* (`offer()`): what the app now does, what they chose and why. It is
put to them with the session's other questions: keep theirs, or switch. Either answer is
recorded; a switch retires the old entry and records the new choice as theirs, and a
keep is offered again after REOFFER_DAYS, saying when they kept it, because a no is for
now, never for ever.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import person  # noqa: E402

FILE = "learned.json"
# Where a reaction belongs. "other" catches the rest; an area is a filter for the
# brief, never a reason to drop what was said.
AREAS = ("voice", "messages", "questions", "people", "jobs", "documents", "search",
         "interview", "other")


def _path() -> str | None:
    try:
        return person.path(FILE)
    except person.NoProfile:
        return None


def load() -> list[dict]:
    path = _path()
    if not path:
        return []
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return []
    rows = data.get("entries") if isinstance(data, dict) else data
    return [r for r in (rows or []) if isinstance(r, dict)]


def _data() -> dict:
    path = _path()
    if not path:
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {"entries": data}


def _save(rows: list[dict], offers_: list[dict] | None = None) -> None:
    path = _path()
    if not path:
        raise SystemExit("learned: no profile; nothing can be recorded before /setup")
    data = {"entries": rows, "offers": offers_ if offers_ is not None else all_offers()}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def entries(area: str | None = None) -> list[dict]:
    """The active entries, oldest first, for one area or all of them."""
    return [r for r in load() if r.get("status", "active") == "active"
            and (area is None or r.get("area") == area)]


def record(area: str, said: str, rule: str, applied_to=(), never_say=(),
           today: str | None = None) -> dict:
    """Keep one reaction. Returns the entry written."""
    if area not in AREAS:
        raise SystemExit(f"learned: area {area!r}; one of {', '.join(AREAS)}")
    if not str(said or "").strip() or not str(rule or "").strip():
        raise SystemExit("learned: record needs what they said and the rule it gives")
    entry = {"date": today or dt.date.today().isoformat(), "area": area,
             "said": " ".join(str(said).split()), "rule": " ".join(str(rule).split()),
             "applied_to": [str(a) for a in applied_to if str(a).strip()],
             "never_say": [str(p) for p in never_say if str(p).strip()],
             "status": "active"}
    rows = load()
    rows.append(entry)
    _save(rows)
    return entry


def retire(n: int) -> dict:
    """The person changed their mind: entry n stops applying, and stays as history."""
    rows = load()
    if not 1 <= n <= len(rows):
        raise SystemExit(f"learned: no entry {n}; there are {len(rows)}")
    rows[n - 1]["status"] = "retired"
    _save(rows)
    return rows[n - 1]


def locked() -> list[str]:
    """Every setting a reaction changed: the person's, which no upgrade may change."""
    seen, out = set(), []
    for r in entries():
        for a in r.get("applied_to") or ():
            if a not in seen:
                seen.add(a)
                out.append(a)
    return out


def never_say() -> list[tuple[str, re.Pattern]]:
    """(phrase, pattern) for every phrase the person has said never to use."""
    out = []
    for r in entries():
        for phrase in r.get("never_say") or ():
            words = [re.escape(w) for w in str(phrase).split()]
            if words:
                # Edges that work for a phrase that opens or closes on punctuation: \b
                # needs a word character there, so "(remote)" or "[sic]" never matched.
                out.append((phrase, re.compile(r"(?<!\w)" + r"\s+".join(words) + r"(?!\w)",
                                               re.I)))
    return out


def dislikes(text: str) -> list[str]:
    """The phrases in `text` the person has said never to use."""
    return [m.group(0) for _, rx in never_say() for m in rx.finditer(str(text or ""))]


def _key(r: dict) -> tuple:
    return (r.get("date"), r.get("area"), r.get("rule"))


def superseded(rows: list[dict] | None = None) -> dict:
    """{key of an active entry: the later active entry that overrules it}.

    A later entry overrules an earlier one when the earlier rule prescribes a phrase the
    later one says never to use: "every first note names the move (said as: I made the
    move)" and, two days on, never_say "I made the move". Both stayed active, and the
    brief told a drafting step to do both. The earlier stays on record as history; the
    brief leaves it out. An earlier entry that itself says never to use the phrase agrees
    with the later one and stands.
    """
    rows = load() if rows is None else rows
    active = [r for r in rows if r.get("status", "active") == "active"]
    out = {}
    for n, r in enumerate(active):
        text = str(r.get("rule") or "").lower()
        own = {str(p).lower() for p in r.get("never_say") or ()}
        for later in active[n + 1:]:
            if any(p.strip() and p.lower() in text and p.lower() not in own
                   for p in map(str, later.get("never_say") or ())):
                out[_key(r)] = later
                break
    return out


def brief(area: str | None = None) -> str:
    """The active rules as lines to follow before drafting, or "" when there are none.
    A rule a later one overrules (superseded) is left out."""
    over = superseded()
    rows = [r for r in entries(area) if _key(r) not in over]
    if area is not None:
        rows = rows + [r for r in entries("other") if r not in rows and _key(r) not in over]
    return "\n".join(f"- {r['rule']} ({r['date']}, they said: \"{r['said']}\")" for r in rows)


def all_offers() -> list[dict]:
    rows = _data().get("offers") or []
    return [r for r in rows if isinstance(r, dict)]


# Keeping their own way is an answer for now, never for ever: a kept choice is offered
# again once this many days have passed (tools/profile_upgrades.py REASK_DAYS, the same
# rule every question follows), saying when they kept it. A switch is final: it is theirs.
REOFFER_DAYS = 30


def offers(today: dt.date | None = None) -> list[tuple[int, dict]]:
    """(number, offer) for every app improvement waiting on the person's choice: never
    answered, or kept long enough ago to be worth asking again."""
    today = today or dt.date.today()
    out = []
    for i, o in enumerate(all_offers(), 1):
        if not o.get("decision"):
            out.append((i, o))
        elif o.get("decision") == "keep":
            try:
                kept = dt.date.fromisoformat(str(o.get("decided") or ""))
            except ValueError:
                continue
            if (today - kept).days >= REOFFER_DAYS:
                out.append((i, {**o, "again": f"you kept your own way on {kept.isoformat()}"}))
    return out


def offer(setting: str, new: str, why: str, version: str, today: str | None = None) -> dict:
    """An update would change a setting the person shaped: ask, never overwrite.

    One offer per setting and app version; a version already offered, kept or
    switched is not offered again.
    """
    rows = all_offers()
    for o in rows:
        if o.get("setting") == setting and o.get("version") == version:
            return o
    mine = [r for r in entries() if setting in (r.get("applied_to") or ())]
    o = {"date": today or dt.date.today().isoformat(), "setting": setting,
         "version": version, "new": " ".join(str(new).split()),
         "why": " ".join(str(why).split()),
         "theirs": mine[-1]["rule"] if mine else "", "said": mine[-1]["said"] if mine else "",
         "decision": ""}
    rows.append(o)
    _save(load(), rows)
    return o


def question(o: dict) -> str:
    """The offer as the one plain question the person is asked."""
    theirs = (f" You told me \"{o['said']}\", so it is: {o['theirs']}." if o.get("said") else "")
    again = f" Asked again: {o['again']}." if o.get("again") else ""
    return (f"The app now does this differently ({o['setting']}): {o['new']}. {o['why']}.{theirs}"
            f"{again} Keep yours, or try the new way?")


def decide(n: int, choice: str, today: str | None = None) -> dict:
    """Record the person's answer to offer n: `keep` theirs or `switch` to the app's."""
    if choice not in ("keep", "switch"):
        raise SystemExit("learned: decide keep|switch")
    rows = all_offers()
    if not 1 <= n <= len(rows):
        raise SystemExit(f"learned: no offer {n}; there are {len(rows)}")
    o = rows[n - 1]
    o["decision"], o["decided"] = choice, today or dt.date.today().isoformat()
    entries_ = load()
    if choice == "switch":
        for r in entries_:
            if o["setting"] in (r.get("applied_to") or ()) and r.get("status", "active") == "active":
                r["status"] = "retired"
        entries_.append({"date": o["decided"], "area": "other",
                         "said": f"switched to the app's new way ({o['version']})",
                         "rule": o["new"], "applied_to": [o["setting"]], "never_say": [],
                         "status": "active"})
    _save(entries_, rows)
    return o


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("brief")
    b.add_argument("area", nargs="?")
    li = sub.add_parser("list")
    li.add_argument("area", nargs="?")
    r = sub.add_parser("record")
    r.add_argument("--area", required=True)
    r.add_argument("--said", required=True)
    r.add_argument("--rule", required=True)
    r.add_argument("--applied-to", action="append", default=[])
    r.add_argument("--never-say", action="append", default=[])
    t = sub.add_parser("retire")
    t.add_argument("n", type=int)
    sub.add_parser("locked")
    sub.add_parser("offers")
    d = sub.add_parser("decide")
    d.add_argument("n", type=int)
    d.add_argument("choice", choices=("keep", "switch"))
    o = sub.add_parser("offer")
    o.add_argument("--setting", required=True)
    o.add_argument("--new", required=True)
    o.add_argument("--why", required=True)
    o.add_argument("--version", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "brief":
        print(brief(a.area) or "(nothing learned yet: the defaults apply)")
    elif a.cmd == "list":
        over = superseded()
        for i, row in enumerate(load(), 1):
            if a.area and row.get("area") != a.area:
                continue
            later = over.get(_key(row))
            status = (f"overruled by {later.get('date')}" if later
                      else row.get("status", "active"))
            print(f"{i:3}. [{status}] {row.get('date')} {row.get('area')}: "
                  f"{row.get('rule')}  (said: \"{row.get('said')}\")")
    elif a.cmd == "record":
        e = record(a.area, a.said, a.rule, a.applied_to, a.never_say)
        print(f"learned: {e['area']}: {e['rule']}")
    elif a.cmd == "retire":
        e = retire(a.n)
        print(f"retired: {e.get('rule')}")
    elif a.cmd == "locked":
        for item in locked():
            print(item)
    elif a.cmd == "offers":
        for n, o in offers():
            print(f"{n}. {question(o)}")
    elif a.cmd == "offer":
        o = offer(a.setting, a.new, a.why, a.version)
        print(f"offered: {question(o)}")
    elif a.cmd == "decide":
        o = decide(a.n, a.choice)
        print(f"{o['setting']}: {o['decision']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
