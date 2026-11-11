#!/usr/bin/env python3
"""Rule a posting out, or lift a ruling, in job_scraper/seen_jobs.json.

A ruling is only as good as the reason behind it, and reasons change: the person
starts learning French, gets a permit that clears a citizenship bar, decides a sector
is fine after all. So every exclusion records what it rests on:

    basis "rules"   the person's own screening rules (profile/10-triage-blockers.md,
                    profile/04-job-evaluation.md and the gate settings in search.py).
                    When what it rests on changes, the exclusion stops blocking and the
                    posting is screened again the next time a round finds it
                    (tools/throttle.py ruled_out). Nothing is fetched before then.
    basis "person"  the person's own words ("not this kind of company"). It holds until
                    they change their mind, and then `lift` takes it off. Written with
                    by "chat", it is a chat's judgement on that one posting (a draft it
                    stopped, `app.py done --left-out`): it holds as theirs does, for that
                    posting alone and never for good, shown under Held back for now.

What a rules ruling rests on is as narrow as it can say. The rules come in parts
(`parts` lists them): each blocker row on the triage card, the evaluation framework,
and each gate setting in search.py. A ruling that names its part (`--rests-on
"triage #4"`, or a reason that cites "blocker 4") lapses only when that part changes,
so moving one pay threshold leaves every language, eligibility and discipline ruling
standing. A ruling that names none rests on the whole rules and lapses on any change;
`lapsed` lists those after a change, and `restamp` records the ones that still hold,
with the part they rest on, so the next change leaves them alone.

Employer-level rulings are read fresh every round and need nothing here: the bar's
excluded sectors and declined employers (tools/bar.py) and do_not_target.json, whose
entries expire on their own `review_after` date.

Rulings made before this file existed say nothing about what they rest on, so they
cannot lapse by themselves. `review` lists them grouped by reason, once; each group is
checked against the person's current rules and either lifted (it no longer holds) or
stamped with what it rests on (the profile upgrade rulings-review does this with nobody
asking). Queue decisions (a same-employer duplicate, the company throttle) and the bar's
verdicts are re-made every round already and are never part of it.

Several rulings can share a reason word for word. `--url` (repeatable) narrows `lift`,
`stamp` and `restamp` to the named postings, and `review --full` and `lapsed` list each
one's address.

Usage:
    python3 tools/exclude.py add <url> --title "<title>" --company "<company>" --reason "<why>" [--basis person] [--rests-on "<part>"]
    exclude.add_many([{"url", "reason", "title", "company", "location"}, ...])   # a round's own cuts, one write
    python3 tools/exclude.py lift ["<words in the reason>"] [--url <url>]... [--why "<what changed>"]
    python3 tools/exclude.py review [--full]   # older rulings with no basis, grouped by reason
    python3 tools/exclude.py stamp ["<words>"] [--url <url>]... --basis rules|person [--rests-on "<part>"]
    python3 tools/exclude.py lapsed            # rules rulings a rules change has lapsed
    python3 tools/exclude.py restamp ["<words>"] [--url <url>]... --rests-on "<part>"|all
    python3 tools/exclude.py unnamed           # standing rulings stamped before parts existed
    python3 tools/exclude.py cite              # name the part for those whose reason cites one
    python3 tools/exclude.py parts             # the parts of the rules, as --rests-on names them
    python3 tools/exclude.py rules             # the current rules fingerprint
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import person  # noqa: E402
from lookup_score import norm  # noqa: E402

SEEN = person.state("job_scraper", "seen_jobs.json")
RULE_DOCS = ("10-triage-blockers.md", "04-job-evaluation.md")
# The search.py settings a posting can be cut on. The rest of the file (what to
# search for, where, how to score) decides nothing a ruling rests on, so editing it
# never lifts one.
GATE_NAMES = ("DEGREE_FLAGS", "DESIGNATED_TITLE", "DESIGNATION", "ELIGIBILITY",
              "ELIGIBILITY_ALWAYS", "ELIGIBILITY_CUT_REASON", "ELIGIBILITY_NOT_BY_PERMIT",
              "ELIGIBILITY_STATUS_TERMS", "ENTITLED", "INTERNAL_ONLY", "INTERNAL_ONLY_TITLE",
              "LANGUAGES_HELD", "LANGUAGE_GATE", "LOCATION", "NEGATIVE", "PERMIT_ACCEPTED",
              "POSITIVE",
              "RESEARCH_ML", "SALARY_CUT_BELOW", "SALARY_FLOOR", "TITLE_LANGUAGE",
              "WORKDAY_INTERNAL_SITES", "YEARS_HELD")
BASES = ("rules", "person")
ALL = "all"
# Who made a ruling with basis "person" when it was not the person: a chat that stopped a draft
# because the job is not one they can take (app.py done --left-out). Written as a ruling by the
# rules, it was judged again against today's rules on every page build, and a stop on a degree,
# a place or pay was back on Jobs at the next one (the engine review, 2026-11-11).
CHAT = "chat"

# A role the person set aside holds for this long from the day they did, then it is shown
# once more, marked, in case things changed: kept for good, one "not for me" in January held
# every later opening of that title at the employer, wherever it was posted, with nothing
# saying so (the rules review, 2026-11-11). It holds for good only where their own words say
# so (FOR_GOOD). Their own number of days: profile/search.py SET_ASIDE_DAYS (set_aside_days).
SET_ASIDE_DEFAULT = 182


def set_aside_days() -> int:
    """How many days a role the person set aside holds: their own number (search.py
    SET_ASIDE_DAYS), read each time it is asked, else SET_ASIDE_DEFAULT. Read once when this
    file was imported, a process kept the old end after the person changed it, and a profile
    with no search.py could not import this file at all (the rules review, 2026-11-11)."""
    try:
        _s = person.module("search") if person.exists("search.py") else None
        n = int(getattr(_s, "SET_ASIDE_DAYS", SET_ASIDE_DEFAULT) or SET_ASIDE_DEFAULT)
    except (TypeError, ValueError, person.NoProfile):
        n = SET_ASIDE_DEFAULT
    return n if n >= 1 else SET_ASIDE_DEFAULT


# Only words that say "never show me this" hold a set-aside for good: "for good", "forever",
# "never" said of the role or the employer, "not at all" said of wanting it ("not interested at
# all"). "never" or "at all" anywhere held a reason that only described the role for good: "they
# never replied", "does not use Python at all" (the rules review, 2026-11-11).
FOR_GOOD = re.compile(
    r"\bfor\s+good\b|\bfor\s*ever\b|\bpermanently\b|\bnot\s+ever\b|\bnever\s+(?:again|ever)\b"
    r"|\bno\s+more\b[^.;]*\bever\b|\bnever\b"
    r"|\bnot\s+(?:at\s+all|(?:interested|keen|for\s+me|a\s+fit|my\s+thing)\s+at\s+all)\b", re.I)
# "never" describing what someone else did, or what happened: a subject before it in its clause
# (they, it, the team ...), or a verb in the past after it.
_NEVER_SAID_OF = re.compile(
    r"\b(?:they|it|he|she|who|which|the\s+\w+|we|nobody|no\s+one)(?:'ve|'d)?\s+(?:\w+\s+)?never\b"
    r"|\bnever\s+(?:(?!interested\b)\w+ed|heard|got|had|did|was|were|said|made|gave|came|knew|saw|been|seen|"
    r"wrote|met|went|sent|paid|told|took)\b", re.I)


def for_good(words) -> bool:
    """Whether the person's words for a set-aside say it holds for good (FOR_GOOD), read
    clause by clause, a "never" that only describes something not counting."""
    for clause in re.split(r"[.;,:!?()]+", str(words or "")):
        for m in FOR_GOOD.finditer(clause):
            if m.group(0).lower() != "never" or not _NEVER_SAID_OF.search(clause):
                return True
    return False
# The day a ruling of theirs was made, in the order each writer stamps one; then, for one
# written by hand with none, the earliest day the posting was seen, which it is no older than.
# Never the latest: a search seeing the posting again (--keep-ruled-out) moved its last_seen
# on, and with it the start of the six months, so it never ended (the rules review, 2026-11-11).
# `held_from` is no day it was made: the day an update gave an undated one its six months
# (date_set_asides), said nowhere as the day it was set aside.
_RULED_ON = ("excluded_date", "excluded_on", "date", "reviewed_date", "restamped_date",
             "held_from")
_SEEN_ON = ("last_seen", "skipped_date", "rank_date", "first_seen")


def _day_of(value) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None


def ruled_on(entry) -> dt.date | None:
    """The day a ruling was made, or None when nothing on it is dated."""
    for k in _RULED_ON:
        day = _day_of((entry or {}).get(k))
        if day:
            return day
    days = [d for d in (_day_of((entry or {}).get(k)) for k in _SEEN_ON) if d]
    return min(days) if days else None


def set_aside_until(entry) -> dt.date | None:
    """The first day a role the person set aside no longer holds: set_aside_days() after the day
    they did; None while it holds for good, their own words saying so (for_good). One nothing
    dates holds as if set today, until the next save writes that day on it (date_undated).
    Only for their own rulings (basis "person"): the rules' own lapse when the rule they rest
    on changes. A chat's judgement (`by` "chat") is never for good: its words are the chat's,
    not theirs."""
    if (entry or {}).get("by") != CHAT and for_good((entry or {}).get("exclusion_reason")):
        return None
    # One with no day at all (a check of the person's own, or an older tool, wrote it so)
    # held nothing in 4.15.0 until something dated it, so what such a writer set aside was not
    # held, and four of the maintainer's own checks failed on the update (2026-11-11). It holds
    # from the day it is read, and the next save dates it, so it still ends: never for ever.
    day = ruled_on(entry) or person.today()
    return day + dt.timedelta(days=set_aside_days())


def set_aside_on(entry) -> dt.date | None:
    """The day the person set it aside, as the page says it, or None where none is known: never
    the day an update dated it (`held_from`)."""
    if not any(_day_of((entry or {}).get(k)) for k in _RULED_ON if k != "held_from") \
            and _day_of((entry or {}).get("held_from")):
        return None
    return ruled_on(entry)


def _undated_set_aside(entry) -> bool:
    return (isinstance(entry, dict) and entry.get("basis") == "person"
            and str(entry.get("status") or "").lower() == "excluded"
            and not any(_day_of(entry.get(k)) for k in _RULED_ON)
            and not for_good(entry.get("exclusion_reason")))


def undated_set_asides(path=None) -> list[str]:
    """The keys of the roles the person set aside with no day of their own, kept from before a
    set-aside had an end, or written since with none: each would end on its posting's first
    seen day's six months, all on the next search, or hold from whichever day it is read
    until a save dates it (date_undated)."""
    data = _load(path or SEEN)
    return [k for k, e in (data.get("seen") or {}).items() if _undated_set_aside(e)]


def date_set_asides(today: str = "", path=None) -> int:
    """Give each role the person set aside with no day of its own (`undated_set_asides`) its
    set_aside_days() from `today` (`held_from`), so the ones set aside before an update come
    back one by one from then, never all at once (profile upgrade set-asides-dated). Words
    that say for good keep it for good. How many were dated."""
    path = path or SEEN
    data = _load(path)
    day = today or person.today().isoformat()
    n = 0
    for e in (data.get("seen") or {}).values():
        if _undated_set_aside(e):
            e["held_from"] = day
            n += 1
    if n:
        _save(data, path)
    return n


def _no_day(entry) -> bool:
    """A set-aside of the person's that nothing dates (no day it was made, none its posting
    was seen: ruled_on) and that ends: set_aside_until counts it from the day it is read."""
    return (isinstance(entry, dict) and entry.get("basis") == "person"
            and str(entry.get("status") or "").lower() == "excluded"
            and ruled_on(entry) is None and set_aside_until(entry) is not None)


def date_undated(data: dict, today: str = "") -> int:
    """Write today on each set-aside nothing dates (_no_day), as `held_from`, so it ends
    set_aside_days() on from the day it was first saved rather than holding from whichever day
    it is read. Every writer of the file calls it before it writes (save_seen, the search's
    throttle.write_back). Never said as the day it was set aside (set_aside_on). How many."""
    day = today or person.today().isoformat()
    n = 0
    seen = data.get("seen") if isinstance(data, dict) else None
    for e in (seen.values() if isinstance(seen, dict) else ()):
        if _no_day(e):
            e["held_from"] = day
            n += 1
    return n


def set_aside_holds(entry, today: dt.date) -> bool:
    """Does this ruling of the person's still hold on `today`?"""
    until = set_aside_until(entry)
    return until is None or until > today
# seen_jobs.json as every writer of it writes it: tools/throttle.py and the row-wise
# merge (tools/merge_state.py) both use this. A different indent rewrote every line of
# the file on a one-ruling change, a diff of the whole file that two chats then had to
# merge.
INDENT = 2

# A blocker row on the triage card: "| 4 | Language | ... |".
_ROW = re.compile(r"^\|\s*(\d+)\s*\|")
# A reason that names its blocker: "blocker 4", "Blocker #4".
_CITES_BLOCKER = re.compile(r"\bblocker\s*#?\s*(\d+)\b", re.I)
# The prefilter's own wording for a cut, and the settings each one reads. Only wording
# that no other cut shares: a reason written in other words names no part and rests on
# the whole rules. The text screen's cuts are read in its own words, from the one table
# it writes them from (text_screen.cut_settings).
_SCREEN_WORDING = (
    (re.compile(r"pre-?filter\b[^:]*:\s*title:", re.I), ("POSITIVE", "NEGATIVE")),
    (re.compile(r"pre-?filter\b[^:]*:\s*location:", re.I), ("LOCATION",)),
    (re.compile(r"internal Workday site", re.I), ("WORKDAY_INTERNAL_SITES",)),
)


def _screen_cut_settings(reason: str) -> list:
    """The settings the text screen's own cuts in `reason` rest on, or [] without one."""
    try:
        import text_screen
    except Exception:                     # no profile search.py: no screen to cite
        return []
    return text_screen.cut_settings(reason)


def _stable(value) -> str:
    """A regex prints its pattern and flags, a dict sorts: the same rules, the same text."""
    if hasattr(value, "pattern"):
        return f"re({value.pattern!r},{value.flags})"
    if isinstance(value, dict):
        return "{" + ",".join(f"{k!r}:{_stable(v)}" for k, v in sorted(value.items(), key=str)) + "}"
    if isinstance(value, (list, tuple, set, frozenset)):
        items = [_stable(v) for v in value]
        return "[" + ",".join(sorted(items) if isinstance(value, (set, frozenset)) else items) + "]"
    return repr(value)


def _doc(name: str) -> bytes:
    if not person.exists(name):
        return b""
    with open(person.path(name), "rb") as fh:
        return fh.read()


def _search():
    return person.module("search") if person.exists("search.py") else None


def rules_fingerprint() -> str:
    """Twelve hex characters that change when, and only when, a ruling's basis does."""
    h = hashlib.sha256()
    for name in RULE_DOCS:
        h.update(name.encode())
        h.update(_doc(name))
    s = _search()
    for name in GATE_NAMES:
        h.update(f"{name}={_stable(getattr(s, name, None))}".encode())
    return h.hexdigest()[:12]


def _short(data) -> str:
    return hashlib.sha256(data if isinstance(data, bytes) else data.encode()).hexdigest()[:12]


def rules_parts() -> dict:
    """{part: fingerprint} for each part of the rules a ruling can rest on alone.

    "triage #N" is one blocker row on the triage card, "evaluation" the evaluation
    framework, and "search.py NAME" one gate setting. A blocker that is not there has
    no entry, so a ruling resting on a removed blocker lapses. A gate setting the
    profile leaves unset is a part all the same, at the app's default: a ruling the
    screen made under that default rests on it, and lapses the day the person sets it.
    It used to have no entry, so such a ruling could not name it and rested on the
    whole rules, lapsing on any change to them.
    """
    parts = {}
    for line in _doc(RULE_DOCS[0]).decode("utf-8", "replace").splitlines():
        m = _ROW.match(line.strip())
        if m:
            parts.setdefault(f"triage #{int(m.group(1))}", _short(" ".join(line.split())))
    evaluation = _doc(RULE_DOCS[1])
    if evaluation:
        parts["evaluation"] = _short(evaluation)
    s = _search()
    for name in GATE_NAMES if s is not None else ():
        parts[f"search.py {name}"] = _short(_stable(getattr(s, name, None)))
    return parts


def part_lines() -> list:
    """[(part, what it says)] for `parts`, so a part can be chosen by what it is."""
    out = []
    for line in _doc(RULE_DOCS[0]).decode("utf-8", "replace").splitlines():
        m = _ROW.match(line.strip())
        if m:
            cells = [c.strip(" *") for c in line.strip().strip("|").split("|")]
            out.append((f"triage #{int(m.group(1))}", " | ".join(cells[1:3])[:100]))
    if _doc(RULE_DOCS[1]):
        out.append(("evaluation", "the evaluation framework, " + RULE_DOCS[1]))
    s = _search()
    for name in GATE_NAMES if s is not None else ():
        out.append((f"search.py {name}", "the gate setting in profile/search.py"
                    + ("" if hasattr(s, name) else ", not set: the app's default")))
    return out


def cited(reason: str, parts: dict | None = None) -> list:
    """The parts a reason names itself.

    "blocker 4", a gate setting by its name, or the cut in the screen's own words
    ("Tier 1 pre-filter: title: ...", "French stated as a requirement: ..."). Every
    part has to be one the rules hold now; a reason that names none rests on them all.
    """
    parts = rules_parts() if parts is None else parts
    reason = reason or ""
    found = [f"triage #{int(n)}" for n in _CITES_BLOCKER.findall(reason)]
    found += [f"search.py {g}" for g in GATE_NAMES if re.search(rf"\b{g}\b", reason)]
    for wording, names in _SCREEN_WORDING:
        if wording.search(reason):
            found += [f"search.py {g}" for g in names]
    found += [f"search.py {g}" for g in _screen_cut_settings(reason)]
    out = [p for p in dict.fromkeys(found) if p in parts]
    # Named, but not all of it is here any more: rest on the whole rules, never on half.
    return out if len(out) == len(dict.fromkeys(found)) else []


def _rests_on(names, parts: dict) -> dict:
    unknown = [n for n in names if n not in parts]
    if unknown:
        raise ValueError(f"no part of the rules is called {', '.join(map(repr, unknown))}; "
                         f"`exclude.py parts` lists them")
    return {n: parts[n] for n in names}


def holds(entry, rules_now: str | None = None, parts_now: dict | None = None) -> bool:
    """Does a rules ruling still stand under the rules as they are now?

    A ruling that names its parts stands while every one of them is unchanged. One that
    names none stands while the whole rules are unchanged. A ruling with no fingerprint
    at all says nothing about its rules and is not this function's to lapse.
    """
    rests = entry.get("rests_on")
    if isinstance(rests, dict) and rests:
        parts_now = rules_parts() if parts_now is None else parts_now
        return all(parts_now.get(p) == h for p, h in rests.items())
    if not entry.get("rules"):
        return True
    return entry["rules"] == (rules_now or rules_fingerprint())


def load_seen(path=SEEN) -> dict:
    from throttle import as_seen
    try:
        with open(path, encoding="utf-8") as fh:
            return as_seen(json.load(fh))
    except FileNotFoundError:
        return {"seen": {}}


_load = load_seen  # the module's own name for it; other modules call load_seen


def save_seen(data, path=SEEN) -> None:
    # A bare file name ("seen.json") has no folder to make: os.makedirs("") raised, so
    # `text_screen.py --seen seen.json` crashed on its first cut and wrote nothing.
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    date_undated(data)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, indent=INDENT, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, path)


_save = save_seen  # the module's own name for it; other modules call save_seen


def _stamp_rules(entry: dict, names=(), fp: str = "", parts: dict | None = None) -> None:
    """Record a rules ruling's fingerprint and what it rests on: its parts, or ALL.

    Every ruling written from now on says one or the other, so `unnamed` finds only
    the rulings stamped before parts existed.
    """
    parts = rules_parts() if parts is None else parts
    names = list(names) or cited(str(entry.get("exclusion_reason") or ""), parts)
    entry["rules"] = fp or rules_fingerprint()
    entry["rests_on"] = _rests_on(names, parts) if names else ALL


def _rule(data: dict, url: str, reason: str, title: str = "", company: str = "",
          basis: str = "rules", today: str = "", rests_on=(), location: str = "",
          fp: str = "", parts: dict | None = None, index: dict | None = None,
          by: str = "") -> dict:
    """Write one ruling into loaded seen data; `add` and `add_many` share it.

    `index` is {normalised URL: entry key}, for a caller writing many at once.
    """
    if basis not in BASES:
        raise ValueError(f"basis is one of {', '.join(BASES)}")
    if not reason.strip():
        raise ValueError("a ruling needs its reason: one that cannot say why blocks nothing")
    if rests_on and basis != "rules":
        raise ValueError("only a ruling on the rules rests on a part of them")
    if by and basis != "person":
        raise ValueError("only a set-aside is made by a chat for the person (basis person)")
    n = norm(url) or url
    # An entry a round already recorded under the raw URL is the same posting.
    if index is None:
        index = {norm(u) or u: u for u in data["seen"]}
    k = index.setdefault(n, n)
    entry = data["seen"].get(k) or {}
    day = today or person.today().isoformat()
    entry.update({"url": entry.get("url") or url, "title": title or entry.get("title", ""),
                  "company": company or entry.get("company", ""), "status": "excluded",
                  "exclusion_reason": reason.strip(), "basis": basis, "excluded_date": day})
    # Where it was ruled out: a ruling on a place, or a language, holds there and
    # not for the same title in another city (tools/throttle.py ruled_out).
    if location and not entry.get("location"):
        entry["location"] = location
    if by:
        entry["by"] = by
    else:
        entry.pop("by", None)
    entry.setdefault("first_seen", day)
    if basis == "rules":
        _stamp_rules(entry, rests_on, fp, parts)
    else:
        entry.pop("rules", None)
        entry.pop("rests_on", None)
    data["seen"][k] = entry
    return entry


def add(url: str, reason: str, title: str = "", company: str = "", basis: str = "rules",
        today: str = "", path=SEEN, rests_on=(), location: str = "", by: str = "") -> dict:
    data = _load(path)
    entry = _rule(data, url, reason, title, company, basis, today, rests_on, location, by=by)
    _save(data, path)
    return entry


def add_many(rulings, today: str = "", path=SEEN) -> int:
    """Record several rules rulings in one write: each a dict with url, reason, and
    optionally title, company and location. The rest is `add`'s, word for word.

    A round's own cuts (tools/text_screen.py --seen) come in dozens, and `add`
    reads and writes the whole file for each one.
    """
    rulings = [r for r in rulings if r.get("url") and str(r.get("reason") or "").strip()]
    if not rulings:
        return 0
    data = _load(path)
    fp, parts = rules_fingerprint(), rules_parts()
    index = {norm(u) or u: u for u in data["seen"]}
    for r in rulings:
        _rule(data, r["url"], r["reason"], r.get("title") or "", r.get("company") or "",
              "rules", today, (), r.get("location") or "", fp, parts, index)
    _save(data, path)
    return len(rulings)


def _matcher(words: str = "", urls=(), postings=()):
    """Matches an entry by words in its reason, by its address, or by both. With
    `postings`, an entry whose ruling covers one of them by its title, employer and city
    (throttle.ruled_pair, as a round reads it) matches as its address would."""
    needle = (words or "").strip().lower()
    keys = {norm(u) or u for u in urls or ()}
    postings = [p for p in postings or () if isinstance(p, dict)]
    if not keys and not postings and len(needle) < 3:
        raise ValueError("name the rulings: words from the reason (three letters or more) "
                         "or --url for each posting")

    def covers(entry) -> bool:
        if not postings:
            return False
        import throttle
        pair = throttle.entry_pair(entry)
        return bool(pair) and any(throttle.ruled_pair({pair: "ruled"}, p) for p in postings)

    def match(key, entry) -> bool:
        if needle and needle not in str(entry.get("exclusion_reason") or "").lower():
            return False
        if not keys and not postings:
            return True
        return bool({key, norm(key), norm(entry.get("url") or "")} & keys) or covers(entry)
    return match


def lift(words: str = "", why: str = "", today: str = "", path=SEEN, urls=(),
         postings=()) -> list:
    """Every exclusion whose reason holds `words` (and, with `urls` or `postings`, only
    those: by its address, or as a ruling on a posting's title, employer and city), lifted."""
    match = _matcher(words, urls, postings)
    data = _load(path)
    out = []
    for key, entry in data["seen"].items():
        if not isinstance(entry, dict) or (entry.get("status") or "").lower() != "excluded":
            continue
        if match(key, entry):
            entry.update({"status": "lifted", "lifted_date": today or person.today().isoformat(),
                          "lifted_because": why or "the person changed their mind"})
            out.append(entry)
    if out:
        _save(data, path)
    return out


def _needs_review(entry) -> bool:
    """Does this ruling block while saying nothing about what it rests on?"""
    import throttle
    if not isinstance(entry, dict) or (entry.get("status") or "").lower() != "excluded":
        return False
    if entry.get("basis"):
        return False
    reason = str(entry.get("exclusion_reason") or "")
    # These already stop blocking or never did, and a fact about the posting (closed,
    # a duplicate, already applied) is not a ruling to review.
    return not (not reason.strip() or reason.lower().startswith(throttle.RE_EVALUATED)
                or throttle.QUEUE_DECISION.search(reason) or throttle.is_stale_exclusion(reason, entry)
                or throttle._NOT_A_VERDICT.search(reason))


def unreviewed(path=SEEN) -> list:
    """Exclusions that block and say nothing about what they rest on."""
    return [e for e in _load(path)["seen"].values() if _needs_review(e)]


def reason_group(reason: str) -> str:
    return re.split(r"[:;.(,]", reason.strip().lower())[0].strip()[:60] or "(no reason)"


_group = reason_group  # the module's own name for it; other modules call reason_group


def _grouped(entries) -> list:
    groups: dict[str, list] = {}
    for e in entries:
        groups.setdefault(_group(str(e.get("exclusion_reason"))), []).append(e)
    return sorted(groups.items(), key=lambda g: -len(g[1]))


def review(path=SEEN) -> list:
    """[(group, count, an example reason)] for the unreviewed rulings, biggest first."""
    return [(g, len(es), str(es[0].get("exclusion_reason"))[:160])
            for g, es in _grouped(unreviewed(path))]


def stamp(words: str = "", basis: str = "rules", today: str = "", path=SEEN, urls=(),
          rests_on=()) -> int:
    """Record what the unreviewed rulings whose reason holds `words` rest on."""
    if basis not in BASES:
        raise ValueError(f"basis is one of {', '.join(BASES)}")
    if rests_on and basis != "rules":
        raise ValueError("only a ruling on the rules rests on a part of them")
    match = _matcher(words, urls)
    data = _load(path)
    fp, parts = rules_fingerprint(), rules_parts()
    _rests_on(rests_on, parts)
    n = 0
    for key, entry in data["seen"].items():
        if not _needs_review(entry) or not match(key, entry):
            continue
        entry["basis"] = basis
        entry["reviewed_date"] = today or person.today().isoformat()
        if basis == "rules":
            _stamp_rules(entry, rests_on, fp, parts)
        n += 1
    if n:
        _save(data, path)
    return n


def _on_rules(entry) -> bool:
    return (isinstance(entry, dict) and (entry.get("status") or "").lower() == "excluded"
            and entry.get("basis") == "rules")


def _is_lapsed(entry, fp: str, parts: dict) -> bool:
    return _on_rules(entry) and not holds(entry, fp, parts)


def lapsed(path=SEEN) -> list:
    """[(group, [(entry, the parts that changed or None for the whole rules)])], biggest first.

    The rules rulings a rules change has lapsed: each is screened again the next time a
    round finds it, unless `restamp` records that it still holds.
    """
    fp, parts = rules_fingerprint(), rules_parts()
    out = []
    for e in _load(path)["seen"].values():
        if not _is_lapsed(e, fp, parts):
            continue
        rests = e.get("rests_on")
        changed = ([p for p, h in rests.items() if parts.get(p) != h]
                   if isinstance(rests, dict) and rests else None)
        out.append((e, changed))
    groups: dict[str, list] = {}
    for e, changed in out:
        groups.setdefault(_group(str(e.get("exclusion_reason"))), []).append((e, changed))
    return sorted(groups.items(), key=lambda g: -len(g[1]))


def restamp(words: str = "", rests_on=(), today: str = "", path=SEEN, urls=()) -> int:
    """Record that rules rulings hold under the rules as they are now, and on what.

    For a ruling a change lapsed, this is the judgement that it still holds; for one
    still standing (`unnamed`), it records the part it rests on before the next change.
    `rests_on` names the part, so a change to any other part leaves it standing; "all"
    records the whole rules, for a ruling that rests on more than one part can say. A
    ruling whose own part changed is not restamped onto that part: that change is the
    one it rests on, so it is screened again instead.
    """
    names = list(rests_on)
    if not names:
        raise ValueError(f"restamp needs --rests-on: a part (`exclude.py parts`) or {ALL!r}")
    whole = names == [ALL]
    match = _matcher(words, urls)
    data = _load(path)
    fp, parts = rules_fingerprint(), rules_parts()
    if not whole:
        _rests_on(names, parts)
    n = 0
    for key, entry in data["seen"].items():
        if not _on_rules(entry) or not match(key, entry):
            continue
        old = entry.get("rests_on") if isinstance(entry.get("rests_on"), dict) else {}
        if any(p in old and parts.get(p) != old[p] for p in names):
            continue
        entry["rules"] = fp
        entry["rests_on"] = ALL if whole else {p: parts[p] for p in names}
        entry["restamped_date"] = today or person.today().isoformat()
        n += 1
    if n:
        _save(data, path)
    return n


def _is_unnamed(entry, fp: str) -> bool:
    """A standing rules ruling stamped before parts existed: it says nothing either way."""
    return _on_rules(entry) and entry.get("rules") == fp and "rests_on" not in entry


def unnamed(path=SEEN) -> list:
    """[(group, [entry])] for the standing rules rulings that say nothing of their part."""
    fp = rules_fingerprint()
    return _grouped(e for e in _load(path)["seen"].values() if _is_unnamed(e, fp))


def cite(path=SEEN) -> int:
    """Name the part for every unnamed ruling whose reason cites one.

    Done while the rules are still the ones it was made under, so a later change to any
    other part leaves it standing. The profile upgrade ruling-parts runs this, then
    names the rest with `restamp`.
    """
    data = _load(path)
    fp, parts = rules_fingerprint(), rules_parts()
    n = 0
    for entry in data["seen"].values():
        if not _is_unnamed(entry, fp):
            continue
        names = cited(str(entry.get("exclusion_reason") or ""), parts)
        if names:
            entry["rests_on"] = {p: parts[p] for p in names}
            n += 1
    if n:
        _save(data, path)
    return n


def _where(e) -> str:
    return f"{e.get('title') or '?'} ({e.get('company') or '?'}) {e.get('url') or ''}".strip()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a_ = sub.add_parser("add")
    a_.add_argument("url")
    a_.add_argument("--reason", required=True)
    a_.add_argument("--title", default="")
    a_.add_argument("--company", default="")
    a_.add_argument("--basis", choices=BASES, default="rules")
    a_.add_argument("--rests-on", action="append", default=[], dest="rests_on")
    l_ = sub.add_parser("lift")
    l_.add_argument("words", nargs="?", default="")
    l_.add_argument("--url", action="append", default=[], dest="urls")
    l_.add_argument("--why", default="")
    sub.add_parser("rules")
    sub.add_parser("parts")
    sub.add_parser("cite")
    sub.add_parser("unnamed")
    sub.add_parser("lapsed")
    d_ = sub.add_parser("date-set-asides", help="give each role set aside with no day its "
                                               "months from today")
    d_.add_argument("--dry", action="store_true", help="count them, change nothing")
    r_ = sub.add_parser("review")
    r_.add_argument("--full", action="store_true", help="list each ruling, with its address")
    s_ = sub.add_parser("stamp")
    s_.add_argument("words", nargs="?", default="")
    s_.add_argument("--url", action="append", default=[], dest="urls")
    s_.add_argument("--basis", choices=BASES, required=True)
    s_.add_argument("--rests-on", action="append", default=[], dest="rests_on")
    t_ = sub.add_parser("restamp")
    t_.add_argument("words", nargs="?", default="")
    t_.add_argument("--url", action="append", default=[], dest="urls")
    t_.add_argument("--rests-on", action="append", default=[], dest="rests_on", required=True)
    a = ap.parse_args(argv)
    try:
        return _run(a)
    except ValueError as e:
        print(f"exclude: {e}", file=sys.stderr)
        return 2


def _run(a) -> int:
    if a.cmd == "date-set-asides":
        n = len(undated_set_asides()) if a.dry else date_set_asides()
        print(f"exclude: {n} role(s) set aside with no day " + ("to date" if a.dry else
              f"given {set_aside_days()} days from today"))
        return 0
    if a.cmd == "review":
        groups = _grouped(unreviewed())
        print(f"exclude: {sum(len(es) for _, es in groups)} older ruling(s) with no basis, "
              f"in {len(groups)} group(s)")
        for g, es in groups:
            print(f"  {len(es):>4}  {g}\n        e.g. {str(es[0].get('exclusion_reason'))[:160]}")
            if a.full:
                for e in es:
                    print(f"        - {_where(e)}")
        return 0
    if a.cmd == "stamp":
        print(f"exclude: {stamp(a.words, a.basis, urls=a.urls, rests_on=a.rests_on)} "
              f"ruling(s) stamped ({a.basis})")
        return 0
    if a.cmd == "lapsed":
        groups = lapsed()
        total = sum(len(es) for _, es in groups)
        print(f"exclude: {total} ruling(s) on the rules lapsed by a change to them, in "
              f"{len(groups)} group(s); each is screened again when a round finds it, "
              f"unless `restamp` records that it still holds")
        for g, es in groups:
            changed = sorted({p for _, c in es for p in (c or ())})
            print(f"  {len(es):>4}  {g}\n        e.g. {str(es[0][0].get('exclusion_reason'))[:160]}")
            print("        rests on: " + (", ".join(changed) + " (changed)" if changed
                                          else "the whole rules (no part named)"))
            for e, _ in es:
                print(f"        - {_where(e)}")
        return 0
    if a.cmd == "restamp":
        print(f"exclude: {restamp(a.words, a.rests_on, urls=a.urls)} ruling(s) restamped "
              f"({', '.join(a.rests_on)})")
        return 0
    if a.cmd == "unnamed":
        groups = unnamed()
        print(f"exclude: {sum(len(es) for _, es in groups)} standing ruling(s) on the rules say "
              f"nothing of the part they rest on, in {len(groups)} group(s): `restamp` each "
              f"group onto its part, or onto all")
        for g, es in groups:
            print(f"  {len(es):>4}  {g}\n        e.g. {str(es[0].get('exclusion_reason'))[:160]}")
            for e in es:
                print(f"        - {_where(e)}")
        return 0
    if a.cmd == "cite":
        print(f"exclude: {cite()} ruling(s) now rest on the part their reason cites")
        return 0
    if a.cmd == "parts":
        for p, what in part_lines():
            print(f"{p:34} {what}")
        return 0
    if a.cmd == "rules":
        print(rules_fingerprint())
        return 0
    if a.cmd == "add":
        e = add(a.url, a.reason, a.title, a.company, a.basis, rests_on=a.rests_on)
        rests = e.get("rests_on")
        on = (", ".join(rests) if isinstance(rests, dict) else
              "the whole rules" if a.basis == "rules" else "their own words")
        print(f"exclude: {e.get('title') or a.url} ruled out ({a.basis}, rests on {on}): "
              f"{e['exclusion_reason'][:100]}")
        return 0
    lifted = lift(a.words, a.why, urls=a.urls)
    print(f"exclude: {len(lifted)} ruling(s) lifted")
    for e in lifted[:20]:
        print(f"  {e.get('title')} ({e.get('company')}): {str(e.get('exclusion_reason'))[:90]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
