#!/usr/bin/env python3
"""The rules that shape a person's search, said in their words, and what each one left out.

Two views the page draws, both computed here (the engine computes, the page draws):

- **What a search left out, by the rule that cut it** (`left_view`): one row a rule in plain
  words ("Not your field", "Needs French", "Outside your places"), its count, the day it
  last cut something, three examples, the rows themselves held for a search box (never all
  thirteen thousand drawn), a few picked across the whole group for the person to check by
  eye, and which of their settings the pencil changes. A flat list of 13,168 rows under
  "Title · 5183" was no way to change a rule, spot a wrong cut or change one's mind (the
  maintainer, 2026-11-05).
- **Your rules** (`your_rules`): every rule that shapes the search and the messages, each
  one sentence, the day it was set and the person's own words where they gave them, how
  many jobs it left out in the last 30 days, and how to change or drop it, through the
  writers the engine already has (tweak's search rows, exclude.py, bar.py's lists in
  search.py, learned.py).

Preferences change, and nobody is pestered about it: a rule set more than REVIEW_DAYS ago that
left out at least REVIEW_MIN jobs in the last 30 days, or one the person set "for now" whose
own review day has come, carries a quiet "Still right?" on its row in Your rules, and the
Brief says so in one line at most once a month (`review_line`), never as a To do. Keeping a
rule as it is is remembered, and so is the Brief line being dismissed.

The day each rule was set, the person's words and a review day live in
documents/rules/set.json, written by the page's own writers as a rule changes (`note_set`).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import person  # noqa: E402
from lookup_score import norm  # noqa: E402

# Each kind of rule a row can be left out by: its words on the page and the setting its
# pencil changes (tools/app_actions.py search.set: places, roles, window, pay, languages;
# employers, the ones turned down by name, in Your rules). None: nothing of theirs to change.
KINDS = {
    "field": ("Not your field", "roles"),
    "language": ("Needs {lang}", "languages"),
    "place": ("Outside your places", "places"),
    "declined": ("An employer you turned down", "employers"),
    "sector": ("A kind of employer you rule out", "employers"),
    "public": ("A public body", None),
    "agency": ("A staffing agency, so no employer is named", None),
    "bar": ("Clears none of your employer bar", None),
    "pay": ("Pay under your cut line", "pay"),
    "age": ("Older than your search window", "window"),
    "eligibility": ("Needs a status or a place to live you do not have", None),
    "credential": ("Needs a qualification you do not hold", None),
    "internal": ("Open to the employer's own staff only", None),
    "research": ("Research-grade work", None),
    "copy": ("Already applied or a copy", None),
    "ruled": ("Left out before", None),
    "throttle": ("Enough already at that employer", None),
    "referral": ("Someone is putting your name forward there", None),
    "closed": ("No longer open", None),
    "other": ("Other reasons", None),
}
# How many of a rule's rows the page holds for its search box and Show more, and how many in
# all: the rest are counted, never drawn (13,168 rows would be megabytes on every open).
HELD_PER_RULE = 250
HELD_MAX = 3000
FIRST = 20
EXAMPLES = 3
CHECK_A_FEW = 5
REVIEW_DAYS = 90
REVIEW_MIN = 50
WINDOW_DAYS = 30
SET_FILE = ("documents", "rules", "set.json")
REVIEW_FILE = ("documents", "rules", "review.json")

_LANG = re.compile(r"^\s*(.{1,60}?) stated as a requirement", re.I)
_TITLE_LANG = re.compile(r"job title is in ([A-Z][\w-]+)", re.I)


def _declined_keys() -> dict:
    try:
        import run_round
        return run_round.declined_now()
    except Exception:  # noqa: BLE001  no profile: nobody turned down
        return {}


def _bar_kind(why: str, company: str, declined: dict) -> str:
    low = why.lower()
    if "staffing agency" in low:
        return "agency"
    if "clears none" in low or "judged" in low:
        return "bar"
    if "public" in low:
        return "public"
    from company_key import key as company_key
    if company and company_key(company) in declined:
        return "declined"
    return "declined" if low.startswith(("you said", "you turned", "turned down",
                                          "no more roles")) else "sector"


def _language(phrase: str) -> str:
    """The language a cut's words name ("French", "fluent in German"), or ""."""
    try:
        import text_screen
        known = set(text_screen.LANGUAGE_WORDS)
    except Exception:  # noqa: BLE001  no profile: read the words as written
        text_screen, known = None, set()
    for word in reversed(re.findall(r"[^\W\d_]+", phrase)):
        name = text_screen.language_named(word) if text_screen else word.lower()
        if name in known:
            return name.capitalize()
    return ""


def _screen_kind(why: str) -> tuple[str, str]:
    low = why.lower()
    # The screen's own words for each cut (text_screen.CUTS), the other kinds before a
    # language: "professional designation stated as a requirement" names no language.
    if "designation" in low or "credential" in low:
        return "credential", ""
    m = _LANG.search(why) or _TITLE_LANG.search(why)
    lang = _language(m.group(1)) if m else ""
    if lang:
        return "language", lang
    if "stated range tops out" in low:
        return "pay", ""
    if "own staff only" in low or "internal" in low:
        return "internal", ""
    if "designation" in low or "credential" in low:
        return "credential", ""
    if "research-grade" in low:
        return "research", ""
    if "eligib" in low or "live in another country" in low or "citizen" in low:
        return "eligibility", ""
    return "other", ""


def kind_of(entry: dict, declined: dict | None = None) -> tuple[str, str]:
    """(kind, language) for one left-out row: which of KINDS cut it, from the stage and the
    reason its stage wrote (tools/filtered.py entries, run_round.leave_out)."""
    stage = str(entry.get("stage") or "")
    why = " ".join(str(entry.get("reason") or "").split())
    low = why.lower()
    declined = _declined_keys() if declined is None else declined
    if stage == "screen" or low.startswith("screen: "):
        return _screen_kind(why[8:] if low.startswith("screen: ") else why)
    head = low.split(":", 1)[0].strip()
    if head == "age":
        return "age", ""
    if head in ("location", "place"):
        return "place", ""
    if head == "title":
        return "field", ""
    if head == "eligibility":
        return "internal", ""
    if head in ("candidate's bar", "do not target"):
        return (_bar_kind(why.split(":", 1)[1] if ":" in why else why,
                          str(entry.get("company") or ""), declined), "")
    if low.startswith(("already applied", "already in a hiring", "already drafted",
                       "already in your applications", "already on your list",
                       "same-employer duplicate")):
        return "copy", ""
    if head == "company throttle":
        return "throttle", ""
    if head.startswith("referral"):
        return "referral", ""
    if head.startswith("closed"):
        return "closed", ""
    if stage == "already seen" or head.startswith(("already ruled out", "ruled out", "seen")):
        return "ruled", ""
    return "other", ""


def label_of(kind: str, lang: str = "") -> str:
    return KINDS.get(kind, KINDS["other"])[0].format(lang=lang or "another language")


def group_id(kind: str, lang: str = "") -> str:
    return "filtered~" + kind + (f"-{lang.lower()}" if lang else "")


def _day(value) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None


def _spread(n: int, k: int) -> list[int]:
    """k indices spread evenly across n, first and last included: a few to check by eye
    from the whole of a rule, not its first page."""
    if n <= k:
        return list(range(n))
    return sorted({round(i * (n - 1) / (k - 1)) for i in range(k)})


def left_view(found: list[dict], name: str, made: dt.date | None, targets: dict,
              item_of=None, declined: dict | None = None) -> dict:
    """The left-out list of round `name` grouped by the rule that cut each row:
    {count, groups: [{id, kind, reason, label, count, last, examples, items, check, held,
    edit, rev}], held: [every row the page holds for search, at most HELD_PER_RULE a rule]}.
    `item_of(n, entry)` makes the page's row for entry n (1-based) and records its target;
    `made` is the day the round ran, the day a rule last cut something here."""
    declined = _declined_keys() if declined is None else declined
    by: dict = {}
    for n, e in enumerate(found, 1):
        kind, lang = kind_of(e, declined)
        g = by.setdefault((kind, lang), {"kind": kind, "lang": lang, "ns": []})
        g["ns"].append(n)
    groups, held = [], []
    item_of = item_of or (lambda n, e: {"id": f"{name}-f{n}", "title": e.get("title") or ""})
    for (kind, lang), g in sorted(by.items(), key=lambda kv: (-len(kv[1]["ns"]), kv[0])):
        ns = g["ns"]
        gid = group_id(kind, lang)
        keep = ns[:HELD_PER_RULE] if len(held) < HELD_MAX else []
        keep = keep[:max(0, HELD_MAX - len(held))]
        rows = [dict(item_of(n, found[n - 1]), g=gid) for n in keep]
        held.extend(rows)
        check = [dict(item_of(ns[i], found[ns[i] - 1]), g=gid) for i in _spread(len(ns), CHECK_A_FEW)]
        edit = KINDS.get(kind, KINDS["other"])[1]
        groups.append({
            "id": gid, "kind": kind, "reason": label_of(kind, lang), "label": label_of(kind, lang),
            "count": len(ns), "last": made.isoformat() if made else None,
            "examples": [str(found[n - 1].get("title") or "") for n in ns[:EXAMPLES]],
            "items": rows[:FIRST], "held": len(rows), "check": check,
            "edit": ({"what": edit, **({"language": lang} if lang else {})} if edit else None)})
        g_rev = (gid, len(ns), [(found[n - 1].get("url"), found[n - 1].get("title")) for n in ns[:50]])
        groups[-1]["rev"] = _rev(g_rev)
        targets[gid] = {"kind": "filtered_group", "round": name, "reason": groups[-1]["label"],
                        "ns": ns, "rev": groups[-1]["rev"]}
    return {"count": len(found), "groups": groups, "held": held}


def _rev(obj) -> str:
    import app_model
    return app_model.rev_of(obj)


# ------------------------------------------------------------------ what each rule cut lately

def _head(path: str) -> dict:
    """A left-out list's first line, its round, counts and kinds, without reading its rows:
    a search can leave out thirteen thousand, and every page build reads a month of them."""
    try:
        with open(path, encoding="utf-8") as fh:
            line = fh.readline()
    except OSError:
        return {}
    cut = line.rfind(', "filtered": [')
    try:
        return json.loads(line[:cut] + "}") if cut > 0 else json.loads(line)
    except ValueError:
        return {}


# The kinds an older list, written before it counted them, is read as by its rules.
_RULE_KIND = {"title": "field", "location": "place", "age": "age", "age (relist)": "age",
              "eligibility": "internal", "candidate's bar": "sector", "already ruled out": "ruled",
              "company throttle": "throttle", "already on your list or applied for": "copy"}


def kinds_of(found: list[dict], declined: dict | None = None) -> dict:
    """{kind: count} and {"language:<Lang>": count} for a left-out list, as its head keeps them."""
    declined = _declined_keys() if declined is None else declined
    out: dict = {}
    for e in found:
        kind, lang = kind_of(e, declined)
        k = f"{kind}:{lang}" if lang else kind
        out[k] = out.get(k, 0) + 1
    return out


def recent(today: dt.date, days: int = WINDOW_DAYS) -> dict:
    """{kind or "language:<Lang>": {"n": how many it left out in the last `days` days,
    "last": the newest day it left any out}}, from each search's left-out list."""
    import glob
    out: dict = {}
    for p in glob.glob(person.state("documents", "rounds", "filtered", "*.json")):
        head = _head(p)
        # Its day from what it holds, never a file's time: a fresh clone touches every file,
        # and the same state must read the same (app_model.model_rev).
        day = _day(head.get("day")) or content_day(person.state(
            "documents", "rounds", os.path.basename(p)))
        if day is not None and not 0 <= (today - day).days <= days:
            continue
        day = day or today
        kinds = head.get("kinds")
        if not isinstance(kinds, dict):
            kinds = {}
            for rule, n in (head.get("counts") or {}).items():
                k = _RULE_KIND.get(str(rule), "other")
                kinds[k] = kinds.get(k, 0) + int(n or 0)
        for k, n in kinds.items():
            got = out.setdefault(k, {"n": 0, "last": None})
            got["n"] += int(n or 0)
            got["last"] = max(filter(None, [got["last"], day.isoformat()]))
    return out


def content_day(path: str) -> dt.date | None:
    """The day a saved search ran, from what it holds alone: the latest day a posting in it
    was first seen, or None."""
    rows = _json(path, [])
    days = [_day(r.get("first_seen")) for r in rows if isinstance(r, dict)]
    return max((d for d in days if d), default=None)


# ------------------------------------------------------------------ when each rule was set

def _json(path: str, default):
    try:
        with open(path, encoding="utf-8") as fh:
            got = json.load(fh)
    except (OSError, ValueError):
        return default
    return got if isinstance(got, type(default)) else default


def _save(path: str, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, indent=1, ensure_ascii=False, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, path)


def set_record() -> dict:
    return _json(person.state(*SET_FILE), {})


# The person's words that make a rule temporary: its review day comes by itself.
_FOR_NOW = re.compile(r"\bfor now\b|\bfor the moment\b|\bfor a while\b|\bfor (?:a|the next) "
                      r"(?:few )?(?:weeks?|months?)\b|\buntil\b|\btemporar", re.I)
FOR_NOW_DAYS = 30


def note_set(rule_id: str, words: str = "", today: str = "", review_on: str = "",
             **extra) -> dict:
    """Keep the day a rule was set, the person's words for it and, for one they set "for
    now", the day to ask about it again. The page's own writers call this as a rule changes."""
    day = today or dt.date.today().isoformat()
    words = " ".join(str(words or "").split())[:300]
    if not review_on and words and _FOR_NOW.search(words):
        review_on = (dt.date.fromisoformat(day) + dt.timedelta(days=FOR_NOW_DAYS)).isoformat()
    data = set_record()
    data[rule_id] = {k: v for k, v in {"set_on": day, "words": words or None,
                                       "review_on": review_on or None, **extra}.items() if v}
    _save(person.state(*SET_FILE), data)
    return data[rule_id]


def drop_set(rule_id: str) -> None:
    data = set_record()
    if data.pop(rule_id, None) is not None:
        _save(person.state(*SET_FILE), data)


def review_record() -> dict:
    return _json(person.state(*REVIEW_FILE), {})


def keep_rule(rule_id: str, today: str) -> None:
    """"Still right?" answered yes: the rule is not asked about for another REVIEW_DAYS."""
    data = review_record()
    data.setdefault("kept", {})[rule_id] = today
    _save(person.state(*REVIEW_FILE), data)
    rec = set_record()
    if rule_id in rec and rec[rule_id].get("review_on"):
        rec[rule_id].pop("review_on", None)
        _save(person.state(*SET_FILE), rec)


def dismiss_brief(today: str) -> None:
    """The Brief's line about old rules set aside: not said again this month."""
    data = review_record()
    data["brief_dismissed"] = today[:7]
    _save(person.state(*REVIEW_FILE), data)


# ------------------------------------------------------------------ Your rules

def _search(key: str, default=None):
    try:
        return getattr(person.module("search"), key, default)
    except Exception:  # noqa: BLE001  no profile: no setting
        return default


def _listed(names, most: int = 6) -> str:
    names = [str(x) for x in names or () if str(x).strip()]
    if len(names) > most:
        return ", ".join(names[:most]) + f" and {len(names) - most} more"
    return ", ".join(names[:-1]) + (" and " if len(names) > 1 else "") + (names[-1] if names else "")


def _plain(why: str) -> str:
    """A reason the profile wrote for the chat, in the person's words."""
    text = re.sub(r"\bthe candidate\b", "you", str(why or ""), flags=re.I)
    return text[:1].upper() + text[1:]


# Each rule's short name in Your rules, by its kind.
NAMES = {"place": "Where", "field": "Your field", "age": "How recent", "pay": "Pay",
         "language": "Languages", "sector": "Kinds of employer", "bar": "Employer bar",
         "agency": "Staffing agencies", "learned": "Learned from you"}


def _row(rid: str, kind: str, sentence: str, effect: int | None, rec: dict, edit=None,
         drop=None, words: str = "", set_on: str = "", name: str = "", **more) -> dict:
    mine = rec.get(rid) or {}
    return {"id": rid, "kind": kind, "name": name or NAMES.get(kind, "A rule"), **more,
            "sentence": sentence.rstrip(".") + ".",
            "set_on": mine.get("set_on") or set_on or None,
            "words": mine.get("words") or words or None, "review_on": mine.get("review_on"),
            "left_out": effect, "edit": edit, "drop": drop}


def your_rules(today: dt.date, seen: dict | None = None, learned_rows=None) -> list[dict]:
    """Every rule that shapes the search and the messages, as rows the page draws: one plain
    sentence, the day it was set and the person's words where kept, how many jobs it left
    out in the last WINDOW_DAYS days, the pencil's setting (`edit`) and the bin's (`drop`),
    and `still_right` where it is old and busy, or its own review day has come."""
    rec = set_record()
    lately = recent(today)
    n = lambda k: (lately.get(k) or {}).get("n", 0)  # noqa: E731
    rows = []
    places = list(_search("SCRAPE_LOCATIONS", []) or [])
    if places:
        towns = list(dict.fromkeys(str(x).split(",")[0].strip() for x in places))
        rows.append(_row("rule~places", "place", f"You search in {_listed(towns)}; an on-site "
                         "role anywhere else is left out", n("place"), rec, edit={"what": "places"}))
    titles = list(_search("SCRAPE_QUERIES", []) or [])
    if titles:
        rows.append(_row("rule~roles", "field", f"You search for {_listed(titles)}; a title "
                         "outside your field is left out", n("field"), rec, edit={"what": "roles"}))
    window = _search("JOB_AGE_DAYS", 14)
    rows.append(_row("rule~window", "age", f"A job posted more than {window} days ago is left "
                     "out", n("age"), rec, edit={"what": "window"}))
    floor, cut = _search("SALARY_FLOOR"), _search("SALARY_CUT_BELOW")
    cur = str(_search("CURRENCY_SYMBOL", "") or "")
    if floor or cut:
        said = (f"Your pay floor is {cur}{int(floor):,}" if floor else "")
        if cut:
            said += ("; " if said else "") + f"a stated range topping out under {cur}{int(cut):,} is left out"
        rows.append(_row("rule~pay", "pay", said, n("pay"), rec, edit={"what": "pay"}))
    held = [str(x).capitalize() for x in _search("LANGUAGES_HELD", ("english",)) or ()]
    langs = sum(v["n"] for k, v in lately.items() if k.startswith("language:"))
    rows.append(_row("rule~languages", "language", f"You work in {_listed(held)}; a job that "
                     "needs another language is left out", langs, rec,
                     edit={"what": "languages"}, values=held))
    # Employers turned down by name, each its own row: the bin takes it off the list.
    declined = _declined_keys()
    names = _declined_names()
    for key, why in sorted(declined.items()):
        rid = f"rule~declined~{key}"
        dated = re.search(r"\b(20\d\d-\d\d-\d\d)\b", str(why))
        why = re.sub(r"^turned down on the page, 20\d\d-\d\d-\d\d: ", "", str(why))
        who = names.get(key) or key.title()
        rows.append(_row(rid, "declined", f"No more roles from {who}: "
                         f"{_plain(why).rstrip('.')}", _employer_left(key, seen, today), rec,
                         drop={"kind": "declined", "key": key},
                         set_on=dated.group(1) if dated else "", name=f"No more from {who}"))
    off = set(_search("BAR_EXCLUDED_OFF", []) or [])
    for _rx, why in list(_search("BAR_EXCLUDED", []) or []):
        if why in off:
            continue
        rows.append(_row(f"rule~sector~{_slug(why)}", "sector", f"Left out: {_plain(why)}",
                         n("sector"), rec, drop={"kind": "sector", "why": why}))
    try:
        import bar
        if bar.applies():
            rows.append(_row("rule~bar", "bar", "An employer must clear one of pay, prestige or "
                             "signal, or its jobs are left out", n("bar"), rec))
    except Exception:  # noqa: BLE001  no bar here: nothing to say about it
        pass
    try:
        import sector
        rx = getattr(sector, "AGENCY", None)
        if rx is not None and rx.pattern != "(?!x)x":
            rows.append(_row("rule~agency", "agency", "A staffing agency's posting is left out: it "
                             "names no employer", n("agency"), rec))
    except Exception:  # noqa: BLE001
        pass
    for i, e in enumerate(learned_rows if learned_rows is not None else _learned(), 1):
        if str(e.get("status") or "active") != "active":
            continue
        said = str(e.get("rule") or "").strip()
        if not said:
            continue
        rows.append(_row(f"rule~learned~{i}", "learned", said, None, rec,
                         drop={"kind": "learned", "n": i}, words=str(e.get("said") or ""),
                         set_on=str(e.get("date") or e.get("on") or "")[:10]))
    kept = review_record().get("kept") or {}
    for r in rows:
        r["still_right"] = still_right(r, today, kept.get(r["id"]))
    return rows


def still_right(row: dict, today: dt.date, kept_on: str | None = None) -> bool:
    """Whether a rule's row asks "Still right?": its own review day has come, or it was set
    REVIEW_DAYS ago or more and left out REVIEW_MIN or more lately; a yes in the last
    REVIEW_DAYS days is kept."""
    kept = _day(kept_on)
    if kept and (today - kept).days < REVIEW_DAYS:
        return False
    due = _day(row.get("review_on"))
    if due and due <= today:
        return True
    since = _day(row.get("set_on"))
    return bool(since and (today - since).days >= REVIEW_DAYS
                and (row.get("left_out") or 0) >= REVIEW_MIN)


def review_line(rows: list[dict], today: dt.date) -> str | None:
    """The Brief's one line about rules to look at again, at most once a month and never once
    set aside this month: "2 of your rules are 3 months old: Your rules"."""
    due = [r for r in rows if r.get("still_right")]
    if not due:
        return None
    if review_record().get("brief_dismissed") == today.isoformat()[:7]:
        return None
    ages = [(today - d).days for d in (_day(r.get("set_on")) for r in due) if d]
    old = f"{max(1, max(ages) // 30)} months old" if ages and max(ages) >= 60 else "due a look"
    n = len(due)
    return f"{n} of your rules {'are' if n > 1 else 'is'} {old}: Your rules"


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text or "").lower()).strip("-")[:40] or "x"


def _declined_names() -> dict:
    """{key: the employer's name as the person or a page wrote it}: BAR_DECLINED holds keys."""
    rec = set_record()
    return {k.split("~", 2)[2]: v.get("name") for k, v in rec.items()
            if k.startswith("rule~declined~") and v.get("name")}


def _employer_left(key: str, seen: dict | None, today: dt.date) -> int:
    """How many postings at this employer were ruled out in the last WINDOW_DAYS days."""
    from company_key import key as company_key
    n = 0
    for e in (seen or {}).values():
        if not isinstance(e, dict) or str(e.get("status") or "") != "excluded":
            continue
        d = _day(e.get("excluded_date"))
        if d and 0 <= (today - d).days <= WINDOW_DAYS and company_key(str(e.get("company") or "")) == key:
            n += 1
    return n


def _learned() -> list[dict]:
    try:
        import learned
        return learned.load()
    except Exception:  # noqa: BLE001  nothing learned yet
        return []


def held_key(url) -> str:
    return norm(str(url or "")) or ""
