#!/usr/bin/env python3
"""The job-market tables the app ships: what /setup reads before it researches anything.

Setup used to research every person's market from nothing: the job boards of their
country, the wording postings there use for a work permit or a clearance, how a resume
is written there, where pay is published, how the big cities are named. That is the same
public research for everyone in a country, and it was most of what setup cost. So the
app carries it, in small tables, and setup researches only what a table lacks (the
person's own city, their target employers, pay for their exact role).

    tools/markets/<cc>.json          a country: national boards, eligibility wording,
                                     documents, pay sources, the largest metros
    tools/markets/fields/<f>.json    a field: its boards (worldwide and per country),
                                     document conventions, licences, pay sources, titles,
                                     interchangeable tools
    tools/markets/levels/<l>.json    graduate, mid, senior, executive: boards and
                                     conventions by country where they differ
    tools/markets/remote.json        remote-first boards that hire across borders
    tools/markets/regions/<cc>.json  regional boards (state or provincial), for the
                                     largest countries only

Every fact carries the page it came from (`source`), the day it was checked (`checked`),
a sentence from that page (`quote`) and `verified`: true only when code found the quote,
and every name in `on_page`, on the page as fetched that day (`verify`). Anything not
verified stays in the file, marked, and is left out of what `load` and `boards` give
setup. A board's robots.txt verdict for its search and posting paths is made by code the
way tools/robots_check.py makes it (`robots`), never written by hand, and a board from a
table is still built only through /add-portal, which reads robots.txt again first.

The tables hold public facts about markets, never anything about a person. A person's
own portals (the CLIs /add-portal builds under .agents/skills/) stay personal paths.

    python3 tools/markets.py --check                       # validate every table
    python3 tools/markets.py brief de --field engineering --level graduate --city Hamburg
    python3 tools/markets.py gaps au --field healthcare-nursing --city Perth --employers 3
    python3 tools/markets.py counts                         # what the tables hold
    python3 tools/markets.py robots [--write] [<table>...]  # re-check robots.txt by code
    python3 tools/markets.py verify [--write] [<table>...]  # re-fetch sources, check quotes
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import json
import os
import re
import subprocess
import sys
from urllib.parse import urlsplit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import local_path  # noqa: E402

DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "markets")
LEVELS = ("graduate", "mid", "senior", "executive")
ROBOTS = ("allowed", "partial", "disallowed", "no_policy", "unconfirmed")
SEARCH = ("open", "open_browser", "blocked", "not_found", "not_tried")
KINDS = ("public", "general", "aggregator", "field", "graduate", "executive", "remote",
         "regional")
MEANS = ("citizenship", "residence", "work_right", "sponsorship", "clearance")
TOPICS = ("noun", "pages", "photo", "date_format", "spelling")
# A quote that proves anything is a sentence, not a word: the shortest that says who does
# what ("Job Bank is Canada's national employment service") is about six words. Japanese
# and Chinese write no spaces, so there two characters count as a word (_size).
MIN_QUOTE_WORDS = 6
# How evenly the countries are covered: no market more detailed than the others, so none
# stands out. (fewest, most) of each kind of fact a country table lists.
EVEN = {"boards": (3, 5), "eligibility": (3, 5), "documents": (5, 5), "pay": (2, 3),
        "places": (3, 3)}
# A fact checked more than a year ago is a lead, not a fact: load() leaves it out like an
# unverified one, so setup researches it afresh, and `verify` and `robots` bring it back.
STALE_DAYS = 365
# The honest client a public-search check identifies as, the convention every portal CLI
# follows (.claude/commands/add-portal.md, "Fetching").
HONEST_UA = "Mozilla/5.0 (compatible; markets-check/1.0)"


# ------------------------------------------------------------------ reading the tables

def _read(path: str):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _files(root: str = DIR) -> list[str]:
    out = []
    for dp, dns, fns in os.walk(root):
        dns.sort()
        out += [os.path.join(dp, f) for f in sorted(fns) if f.endswith(".json")]
    return out


def _fold(text: str) -> str:
    import unicodedata
    plain = "".join(c for c in unicodedata.normalize("NFKD", str(text or ""))
                    if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", plain.casefold()).strip()


def countries(root: str = DIR) -> dict[str, dict]:
    """{code: table} for every country the app has a table for."""
    out = {}
    for f in sorted(os.listdir(root)) if os.path.isdir(root) else []:
        if f.endswith(".json") and f != "remote.json":
            out[f[:-5]] = _read(os.path.join(root, f))
    return out


def _kind(sub: str, root: str = DIR) -> dict[str, dict]:
    folder = os.path.join(root, sub)
    out = {}
    for f in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
        if f.endswith(".json"):
            out[f[:-5]] = _read(os.path.join(folder, f))
    return out


def fields(root: str = DIR) -> dict[str, dict]:
    return _kind("fields", root)


def levels(root: str = DIR) -> dict[str, dict]:
    return _kind("levels", root)


def regions(root: str = DIR) -> dict[str, dict]:
    return _kind("regions", root)


def remote(root: str = DIR) -> dict:
    path = os.path.join(root, "remote.json")
    return _read(path) if os.path.exists(path) else {"boards": []}


def _resolve(wanted, tables: dict[str, dict]) -> str | None:
    """The code of the table `wanted` names: its code, its name or any of its `aka`."""
    if not wanted:
        return None
    w = _fold(wanted)
    for code, t in tables.items():
        names = [code, t.get("name", "")] + list(t.get("aka") or [])
        if w in {_fold(n) for n in names}:
            return code
    return None


def country_code(wanted, root: str = DIR) -> str | None:
    return _resolve(wanted, countries(root))


def field_code(wanted, root: str = DIR) -> str | None:
    return _resolve(wanted, fields(root))


def level_code(wanted, root: str = DIR) -> str | None:
    return _resolve(wanted, levels(root))


def _is_fact(o) -> bool:
    return isinstance(o, dict) and "source" in o and "verified" in o


def _fresh(fact: dict, today: dt.date) -> bool:
    try:
        return (today - dt.date.fromisoformat(str(fact.get("checked")))).days <= STALE_DAYS
    except ValueError:
        return False


def _kept(items, unverified: bool, today: dt.date | None = None) -> list:
    """The items setup may rely on: every one that is not a fact, and each fact verified
    within the last STALE_DAYS. With `unverified`, everything."""
    today = today or dt.date.today()
    return [dict(i) for i in items or [] if unverified or not _is_fact(i)
            or (i.get("verified") and _fresh(i, today))]


def _keyed(block, cc: str) -> list:
    """A field's or a level's list for this country: the worldwide entries ("*") first."""
    if isinstance(block, list):
        return list(block)
    block = block or {}
    return list(block.get("*") or []) + list(block.get(cc) or [])


def load(country, field=None, level=None, region=None, unverified: bool = False,
         root: str = DIR, today: dt.date | None = None) -> dict:
    """Everything the tables hold for one person's market, merged: their country, field,
    level and region, and the remote boards. Facts not verified, or verified more than
    STALE_DAYS ago, are left out unless `unverified`. Raises KeyError for a country with
    no table (gaps() says what to research instead)."""
    cc = country_code(country, root)
    if cc is None:
        raise KeyError(f"no market table for {country!r}")
    c = countries(root)[cc]
    fc, lc = field_code(field, root), level_code(level, root)
    f = fields(root).get(fc) if fc else None
    lv = levels(root).get(lc) if lc else None
    rg_all = (regions(root).get(cc) or {}).get("regions") or {}
    rc = _resolve(region, rg_all) if region else None
    rg = rg_all.get(rc) if rc else None

    def tag(items, scope):
        return [dict(i, scope=scope) for i in _kept(items, unverified, today)]

    boards = tag(c.get("boards"), "country")
    docs = tag(c.get("documents"), "country")
    pay = tag(c.get("pay"), "country")
    out = {"country": cc, "name": c.get("name"), "languages": c.get("languages") or [],
           "currency": c.get("currency"), "field": fc, "level": lc, "region": rc,
           "field_name": (f or {}).get("name"),
           "eligibility": tag(c.get("eligibility"), "country"),
           "places": tag(c.get("places"), "country"),
           "titles": [], "families": [], "licences": [], "norms": []}
    if f:
        boards += tag(_keyed(f.get("boards"), cc), "field")
        docs += tag(_keyed(f.get("documents"), cc), "field")
        pay += tag(_keyed(f.get("pay"), cc), "field")
        out["licences"] = tag(_keyed(f.get("licences"), cc), "field")
        out["titles"] = tag(f.get("titles"), "field")
        out["families"] = tag(f.get("families"), "field")
    if lv:
        boards += tag(_keyed(lv.get("boards"), cc), "level")
        docs += tag(_keyed(lv.get("documents"), cc), "level")
        out["norms"] = tag(_keyed(lv.get("norms"), cc), "level")
    if rg:
        boards += tag(rg.get("boards"), "region")
    boards += tag(remote(root).get("boards"), "remote")
    seen, unique = set(), []
    for b in boards:                       # each board once, where it is first met
        host = (urlsplit(b.get("url", "")).hostname or "").lower()
        if host not in seen:
            seen.add(host)
            unique.append(b)
    out.update(boards=unique, documents=docs, pay=pay)
    return out


def boards(country, field=None, level=None, region=None, unverified: bool = False,
           root: str = DIR, today: dt.date | None = None) -> list[dict]:
    """The boards the tables hold for this market, each tagged with its `scope`: country,
    field, level, region or remote. Each still goes through /add-portal before a round
    searches it."""
    return load(country, field, level, region, unverified, root, today)["boards"]


def families(field, root: str = DIR, today: dt.date | None = None) -> list[tuple]:
    """A field's interchangeable tools in tools/bridges.py's FAMILIES shape, for a profile
    to add to its skills.py FAMILIES: (what the family is, (name, pattern), ...)."""
    fc = field_code(field, root)
    f = fields(root).get(fc) if fc else None
    return [tuple([fam["family"]] + [tuple(m) for m in fam["members"]])
            for fam in _kept((f or {}).get("families"), False, today)]


def gaps(country, field=None, level=None, region=None, city=None, employers: int = 0,
         root: str = DIR, today: dt.date | None = None) -> list[str]:
    """What setup still has to research for this person, in plain lines: everything the
    tables do not hold. The research agent is sent for these and nothing else."""
    out = []
    cc = country_code(country, root)
    if cc is None:
        return [f"everything about {country}: its national job boards (and what each "
                "robots.txt allows), the eligibility wording postings use, how a resume is "
                "written there, where pay is published, and how its cities are named"]
    m = load(cc, field, level, region, root=root, today=today)
    if city:
        names = {_fold(n) for p in m["places"] for n in [p.get("metro", "")] + (p.get("written") or [])}
        if _fold(city) not in names:
            out.append(f"the place names around {city}: the towns a posting may name "
                       "instead, and what counts as too far")
    else:
        out.append("the person's own city: the towns around it a posting may name instead")
    if field and not m["field"]:
        out.append(f"the boards of {field} in {m['name']}, its document conventions, its "
                   "licences or registrations, its pay sources, its titles and tools")
    elif m["field"] and not [b for b in m["boards"] if b["scope"] == "field"]:
        out.append(f"the boards of {m['field_name'].lower()} in {m['name']}")
    if level and not m["level"]:
        out.append(f"what changes at {level} level: page length, graduate or executive boards")
    elif m["level"] in ("graduate", "executive") and not [b for b in m["boards"]
                                                         if b["scope"] == "level"]:
        out.append(f"the {m['level']} boards of {m['name']}")
    if region and not m["region"] and regions(root).get(cc):
        out.append(f"the regional boards of {region}")
    out.append("pay for their role and level in their city, from the pay sources listed: "
               "the tables name where pay is published, never the numbers")
    if employers:
        out.append(f"the hiring system of each of their {employers} target employers: "
                   "code, not research (python3 tools/ats_boards.py --find, one per employer)")
    held = {d.get("topic") for d in m["documents"] if d.get("scope") == "country"}
    missing = [t.replace("_", " ") for t in TOPICS if t not in held]
    if missing:
        out.append(f"how a resume is written in {m['name']}: {', '.join(missing)} (the table "
                   "could not confirm these from a page it read)")
    means = {e.get("means") for e in m["eligibility"]}
    if not {"citizenship", "work_right"} & means or len(means) < 2:
        out.append(f"the eligibility wording postings in {m['name']} use for citizenship, "
                   "residence, a work permit and sponsorship")
    if len(m["pay"]) < 1:
        out.append(f"where pay is published in {m['name']}")
    return out


def brief(country, field=None, level=None, region=None, city=None, employers: int = 0,
          root: str = DIR, today: dt.date | None = None) -> str:
    """The merged tables as a short text for setup to read, then what is still missing."""
    cc = country_code(country, root)
    if cc is None:
        return "No market table for %s.\nStill to research:\n- %s" % (
            country, "\n- ".join(gaps(country, field, level, region, city, employers, root,
                                      today)))
    m = load(cc, field, level, region, root=root, today=today)
    lines = [f"Market: {m['name']} ({cc})"
             + "".join(f", {k} {m[k]}" for k in ("field", "level", "region") if m[k])]
    lines.append("Boards (robots.txt for search / posting, checked by code; /add-portal checks again):")
    for b in m["boards"]:
        r = b.get("robots") or {}
        s = (b.get("public_search") or {}).get("status", "not_tried")
        lines.append(f"- {b['name']} {b['url']} [{b['scope']}, {b.get('kind')}] robots "
                     f"{r.get('status')} (search {_yn(r.get('search'))}, posting "
                     f"{_yn(r.get('posting'))}"
                     + (f", crawl-delay {r['crawl_delay']:g}s" if r.get("crawl_delay") else "")
                     + (", asks no AI input" if r.get("ai_input") == "no" else "")
                     + f"); public search {s}; source {b['source']}")
    for kind, label, key in (("eligibility", "Eligibility wording", "phrase"),
                             ("documents", "Documents", "value"),
                             ("licences", "Licences and registrations", "value"),
                             ("norms", "Norms at this level", "value"),
                             ("pay", "Pay sources (numbers are researched, never stored)", "name"),
                             ("places", "Places", "metro")):
        if not m[kind]:
            continue
        lines.append(label + ":")
        for i in m[kind]:
            v = i.get(key)
            extra = ""
            if kind == "eligibility":
                extra = f" [{i.get('means')}, {i.get('lang')}]"
            elif kind == "documents":
                extra = f" [{i.get('topic', '')}]".replace(" []", "")
            elif kind == "places":
                v = f"{v}: " + ", ".join(i.get("written") or [])
            elif kind == "pay":
                v = f"{v} {i.get('url')}: {i.get('what', '')}"
            lines.append(f"- {v}{extra} ({i['source']})")
    if m["titles"]:
        lines.append("Titles: " + "; ".join(", ".join(t["value"]) for t in m["titles"]))
    if m["families"]:
        lines.append("Interchangeable tools (add to skills.py FAMILIES): "
                     + "; ".join(f"{f['family']}: " + ", ".join(n for n, _ in f["members"])
                                 for f in m["families"]))
    lines.append("Still to research:")
    lines += ["- " + g for g in gaps(cc, field, level, region, city, employers, root, today)]
    return "\n".join(lines)


def _yn(v) -> str:
    return {True: "allowed", False: "disallowed"}.get(v, "unknown")


# ------------------------------------------------------------------ validating them

def _size(quote) -> int:
    """How many words a quote holds, two characters a word in a script without spaces."""
    text = str(quote or "")
    cjk = sum(1 for c in text if "\u3040" <= c <= "\u30ff" or "\u4e00" <= c <= "\u9fff")
    return len(text.split()) + cjk // 2


def _url_ok(u) -> bool:
    p = urlsplit(str(u or ""))
    return p.scheme == "https" and bool(p.hostname) and "." in (p.hostname or "")


def _date_ok(d, today: dt.date) -> bool:
    try:
        day = dt.date.fromisoformat(str(d))
    except ValueError:
        return False
    return dt.date(2026, 1, 1) <= day <= today


def _fact_problems(where: str, f, today: dt.date) -> list[str]:
    if not isinstance(f, dict):
        return [f"{where}: not an object"]
    out = []
    if not _url_ok(f.get("source")):
        out.append(f"{where}: source is not an https address")
    if not _date_ok(f.get("checked"), today):
        out.append(f"{where}: checked is not a date in 2026 or later and not in the future")
    if not isinstance(f.get("verified"), bool):
        out.append(f"{where}: verified is not true or false")
    q = f.get("quote")
    if not isinstance(q, str):
        out.append(f"{where}: quote is not text")
    elif f.get("verified") and _size(q) < MIN_QUOTE_WORDS:
        out.append(f"{where}: a verified quote under {MIN_QUOTE_WORDS} words proves nothing")
    if not f.get("verified") and not f.get("why"):
        out.append(f"{where}: unverified with no why")
    if "on_page" in f and not (isinstance(f["on_page"], list)
                               and all(isinstance(x, str) and x for x in f["on_page"])):
        out.append(f"{where}: on_page is not a list of names")
    return out


def _board_problems(where: str, b, today: dt.date) -> list[str]:
    out = _fact_problems(where, b, today)
    if not isinstance(b, dict):
        return out
    if list(b)[:2] != ["name", "url"]:
        # The leak scan reads a board's name beside its own address (leak_scan.py,
        # market_allowance), so the two open every board.
        out.append(f"{where}: a board starts with its name, then its url")
    if not _url_ok(b.get("url")):
        out.append(f"{where}: url is not an https address")
    if b.get("kind") not in KINDS:
        out.append(f"{where}: kind {b.get('kind')!r} is not one of {', '.join(KINDS)}")
    paths = b.get("paths") or {}
    if not (isinstance(paths, dict) and str(paths.get("search", "")).startswith("/")):
        out.append(f"{where}: paths.search is not a path")
    if paths.get("posting") is not None and not str(paths["posting"]).startswith("/"):
        out.append(f"{where}: paths.posting is not a path")
    r = b.get("robots")
    if not isinstance(r, dict) or r.get("status") not in ROBOTS:
        out.append(f"{where}: robots.status is not one of {', '.join(ROBOTS)}")
    else:
        if not _date_ok(r.get("checked"), today):
            out.append(f"{where}: robots.checked is not a date")
        want = _status(r.get("search"), r.get("posting"), r["status"])
        if want != r["status"]:
            out.append(f"{where}: robots.status {r['status']} does not follow from its verdicts")
    s = b.get("public_search")
    if not isinstance(s, dict) or s.get("status") not in SEARCH:
        out.append(f"{where}: public_search.status is not one of {', '.join(SEARCH)}")
    elif not _date_ok(s.get("checked"), today):
        out.append(f"{where}: public_search.checked is not a date")
    elif isinstance(r, dict) and r.get("search") is not True and s["status"] != "not_tried":
        out.append(f"{where}: its search page was fetched though robots.txt did not allow it")
    if "api" in b:
        out += _fact_problems(where + " api", b["api"], today)
    return out


def _status(search, posting, current: str) -> str:
    """The robots status two path verdicts make: the one a robots() run writes."""
    if current in ("no_policy", "unconfirmed"):
        return current
    if search is True and posting in (True, None):
        return "allowed"
    if search is True or posting is True:
        return "partial"
    return "disallowed"


def _family_problems(where: str, fam, today: dt.date) -> list[str]:
    out = _fact_problems(where, fam, today)
    if not isinstance(fam, dict):
        return out
    if not isinstance(fam.get("family"), str) or not fam.get("family"):
        out.append(f"{where}: no family name")
    members = fam.get("members")
    if not isinstance(members, list) or len(members) < 2:
        out.append(f"{where}: a family needs two members or more")
        return out
    for m in members:
        if not (isinstance(m, list) and len(m) == 2 and all(isinstance(x, str) for x in m)):
            out.append(f"{where}: a member is not [name, pattern]")
            continue
        try:
            rx = re.compile(m[1], re.I)
        except re.error as e:
            out.append(f"{where}: {m[0]}'s pattern does not compile ({e})")
            continue
        if not rx.search(m[0]):
            out.append(f"{where}: {m[0]}'s pattern does not match its own name")
    return out


def check(root: str = DIR, today: dt.date | None = None) -> list[str]:
    """Every problem in every table: fields, addresses, dates, robots verdicts, evenness."""
    today = today or dt.date.today()
    out: list[str] = []
    for path in _files(root):
        try:
            _read(path)
        except (OSError, ValueError) as e:
            out.append(f"{local_path.rel(path, root)}: does not read as JSON ({e})")
    if out:
        return out
    cs = countries(root)
    seen_aka: dict[str, str] = {}
    for cc, c in cs.items():
        w = f"{cc}.json"
        if not re.fullmatch(r"[a-z]{2}", cc) or c.get("country") != cc:
            out.append(f"{w}: country must be its own two-letter file name")
        for k in ("name", "languages", "currency", "boards", "eligibility", "documents",
                  "pay", "places"):
            if not c.get(k):
                out.append(f"{w}: no {k}")
        for n in [c.get("name", "")] + list(c.get("aka") or []):
            if _fold(n) in seen_aka and seen_aka[_fold(n)] != cc:
                out.append(f"{w}: {n!r} also names {seen_aka[_fold(n)]}")
            seen_aka[_fold(n)] = cc
        for kind, (lo, hi) in EVEN.items():
            n = len(c.get(kind) or [])
            if not lo <= n <= hi:
                out.append(f"{w}: {n} {kind}, where every country lists {lo} to {hi}")
        for i, b in enumerate(c.get("boards") or []):
            out += _board_problems(f"{w} boards[{i}]", b, today)
        for i, e in enumerate(c.get("eligibility") or []):
            out += _fact_problems(f"{w} eligibility[{i}]", e, today)
            if e.get("means") not in MEANS:
                out.append(f"{w} eligibility[{i}]: means is not one of {', '.join(MEANS)}")
            if not e.get("phrase") or not e.get("lang"):
                out.append(f"{w} eligibility[{i}]: needs its phrase and its language")
        topics = [d.get("topic") for d in c.get("documents") or []]
        if sorted(topics) != sorted(TOPICS):
            out.append(f"{w}: documents cover {', '.join(map(str, topics))}, not each of "
                       f"{', '.join(TOPICS)} once")
        for i, d in enumerate(c.get("documents") or []):
            out += _fact_problems(f"{w} documents[{i}]", d, today)
        for i, p in enumerate(c.get("pay") or []):
            out += _fact_problems(f"{w} pay[{i}]", p, today)
            if not _url_ok(p.get("url")) or not p.get("name"):
                out.append(f"{w} pay[{i}]: needs its name and an https url")
        for i, p in enumerate(c.get("places") or []):
            out += _fact_problems(f"{w} places[{i}]", p, today)
            if not p.get("metro") or not p.get("written"):
                out.append(f"{w} places[{i}]: needs its metro and how it is written")
    for fc, f in fields(root).items():
        w = f"fields/{fc}.json"
        if f.get("field") != fc or not f.get("name"):
            out.append(f"{w}: field must be its own file name, with a name")
        out += _keyed_problems(w, f, ("boards", "documents", "pay", "licences"), cs, today)
        for i, t in enumerate(f.get("titles") or []):
            out += _fact_problems(f"{w} titles[{i}]", t, today)
            if not (isinstance(t.get("value"), list) and t["value"]):
                out.append(f"{w} titles[{i}]: value is not a list of titles")
        for i, fam in enumerate(f.get("families") or []):
            out += _family_problems(f"{w} families[{i}]", fam, today)
    for lc, lv in levels(root).items():
        w = f"levels/{lc}.json"
        if lc not in LEVELS or lv.get("level") != lc:
            out.append(f"{w}: level must be one of {', '.join(LEVELS)} and its own file name")
        out += _keyed_problems(w, lv, ("boards", "documents", "norms"), cs, today)
    for i, b in enumerate(remote(root).get("boards") or []):
        out += _board_problems(f"remote.json boards[{i}]", b, today)
    for rc, r in regions(root).items():
        w = f"regions/{rc}.json"
        if rc not in cs or r.get("country") != rc:
            out.append(f"{w}: a region file is named for a country with a table")
        for code, reg in (r.get("regions") or {}).items():
            if not reg.get("name"):
                out.append(f"{w} {code}: no name")
            for i, b in enumerate(reg.get("boards") or []):
                out += _board_problems(f"{w} {code} boards[{i}]", b, today)
    return out


def _keyed_problems(w: str, table: dict, kinds, cs: dict, today: dt.date) -> list[str]:
    out = []
    for kind in kinds:
        block = table.get(kind) or {}
        if not isinstance(block, dict):
            out.append(f"{w}: {kind} is keyed by country (\"*\" for everywhere)")
            continue
        for key, items in block.items():
            if key != "*" and key not in cs:
                out.append(f"{w} {kind}: {key!r} is not a country with a table")
            for i, item in enumerate(items or []):
                where = f"{w} {kind}[{key}][{i}]"
                out += (_board_problems if kind == "boards" else _fact_problems)(where, item, today)
                if kind == "pay" and (not _url_ok(item.get("url")) or not item.get("name")):
                    out.append(f"{where}: needs its name and an https url")
    return out


def counts(root: str = DIR) -> dict:
    """What the tables hold, verified and listed, by dimension: for a report."""
    out: dict = {"countries": {}, "fields": {}, "levels": {}, "remote": {}, "regions": {}}

    def tally(items):
        items = items or []
        return [sum(1 for i in items if not _is_fact(i) or i.get("verified")), len(items)]

    def robots_of(items):
        tally_r: dict = {}
        for b in items or []:
            s = (b.get("robots") or {}).get("status")
            tally_r[s] = tally_r.get(s, 0) + 1
        return tally_r

    for cc, c in countries(root).items():
        out["countries"][cc] = {k: tally(c.get(k)) for k in EVEN}
        out["countries"][cc]["robots"] = robots_of(c.get("boards"))
    for fc, f in fields(root).items():
        bs = [b for items in (f.get("boards") or {}).values() for b in items]
        out["fields"][fc] = {"boards": tally(bs), "robots": robots_of(bs),
                             "titles": tally(f.get("titles")),
                             "families": tally(f.get("families")),
                             "documents": tally([d for v in (f.get("documents") or {}).values() for d in v]),
                             "licences": tally([d for v in (f.get("licences") or {}).values() for d in v]),
                             "pay": tally([d for v in (f.get("pay") or {}).values() for d in v])}
    for lc, lv in levels(root).items():
        bs = [b for items in (lv.get("boards") or {}).values() for b in items]
        out["levels"][lc] = {"boards": tally(bs), "robots": robots_of(bs),
                             "documents": tally([d for v in (lv.get("documents") or {}).values() for d in v]),
                             "norms": tally([d for v in (lv.get("norms") or {}).values() for d in v])}
    rb = remote(root).get("boards")
    out["remote"] = {"boards": tally(rb), "robots": robots_of(rb)}
    for rc, r in regions(root).items():
        bs = [b for reg in (r.get("regions") or {}).values() for b in reg.get("boards") or []]
        out["regions"][rc] = {"regions": len(r.get("regions") or {}), "boards": tally(bs),
                              "robots": robots_of(bs)}
    return out


# ------------------------------------------------------------------ checking them again, by code

def _all_boards(table) -> list[dict]:
    """Every board object anywhere in a table."""
    found = []

    def walk(o):
        if isinstance(o, dict):
            if "robots" in o and "paths" in o and "url" in o:
                found.append(o)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(table)
    return found


def _all_facts(table) -> list[dict]:
    """Every fact object anywhere in a table, boards included."""
    found = []

    def walk(o):
        if isinstance(o, dict):
            if _is_fact(o):
                found.append(o)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(table)
    return found


def _robots_fetch(url: str, ua: str):
    """robots_check's own curl, tried three times, the last over HTTP/1.1: a host that drops
    a second request in quick succession answered nothing, and one behind the cloud's proxy
    broke every HTTP/2 stream, so both read as unconfirmed."""
    import time
    import robots_check
    last: Exception = RuntimeError("no attempt")
    for attempt in range(3):
        try:
            if attempt < 2:
                return robots_check._fetch(url, ua)
            r = subprocess.run(
                ["curl", "-sS", "-L", "--http1.1", "--max-redirs", "5", "--max-time", "12",
                 "-A", ua, "-H", "Accept: text/plain,*/*", "-w", "\n%{http_code}", "--", url],
                capture_output=True, text=True, timeout=20, encoding="utf-8", errors="replace")
            if r.returncode != 0:
                raise RuntimeError("curl exit %d" % r.returncode)
            body, _, code = r.stdout.rpartition("\n")
            return body, int(code or 0)
        except Exception as e:  # noqa: BLE001 - curl's own failure, retried
            last = e
            time.sleep(3)
    raise last


def _curl(url: str, headers: dict) -> tuple[int, dict, str]:
    """company_research's curl, and once more over HTTP/1.1 when it got no answer at all."""
    import company_research as cr
    got = cr.curl(url, headers)
    if got[0] != 0:
        return got
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        head, body = os.path.join(d, "h"), os.path.join(d, "b")
        cmd = ["curl", "-sS", "--http1.1", "--max-time", "30", "--compressed", "-D", head,
               "-o", body, "-w", "%{http_code}"]
        for k, v in headers.items():
            cmd += ["-H", f"{k}: {v}"]
        try:
            r = subprocess.run(cmd + ["--", url], capture_output=True, text=True, timeout=45,
                               encoding="utf-8", errors="replace")
        except (OSError, subprocess.TimeoutExpired):
            return got
        status = int((r.stdout or "0").strip()[-3:] or 0) if (r.stdout or "").strip() else 0
        hdrs = {}
        try:
            with open(head, encoding="latin-1") as fh:
                for line in fh.read().strip().split("\r\n\r\n")[-1].splitlines()[1:]:
                    k, _, v = line.partition(":")
                    hdrs[k.strip().lower()] = v.strip()
            with open(body, "rb") as fh:
                raw = fh.read(cr.MAX_BYTES)
        except OSError:
            return got
        charset = re.search(r"charset=([\w-]+)", hdrs.get("content-type", ""), re.I)
        return status, hdrs, raw.decode(charset.group(1) if charset else "utf-8", "replace")


def robots_verdict(base: str, paths: dict, fetch=None) -> dict:
    """The robots.txt verdict for a board's search and posting paths, made the way
    tools/robots_check.py makes it: read as Claude-User, then as a browser; a Disallow for
    Claude-User or * refuses; a 404 is no policy; anything else unread is unconfirmed."""
    import robots_check
    from openroles.robots import content_signals, crawl_delay
    body, why = robots_check.read_policy(base, fetch=fetch or _robots_fetch)
    out = {"status": "", "search": None, "posting": None, "crawl_delay": None,
           "ai_input": None, "why": ""}
    if body is None:
        out.update(status="unconfirmed", why=f"robots.txt could not be read ({why})")
        return out
    if body == "":
        out.update(status="no_policy", search=True, posting=True if paths.get("posting") else None,
                   why="no robots.txt published")
        return out
    root = base.rstrip("/")
    for key in ("search", "posting"):
        if paths.get(key):
            rc, _msg = robots_check.decide(body, root + paths[key])
            out[key] = rc == 0
    out["status"] = _status(out["search"], out["posting"], "")
    delay = max(crawl_delay(body, "Claude-User"), crawl_delay(body, "*"))
    out["crawl_delay"] = delay or None
    if any(content_signals(body, a).get("ai-input") == "no" for a in ("Claude-User", "*")):
        out["ai_input"] = "no"
    return out


def _robots_child(base: str, paths: dict, timeout: int = 60) -> dict:
    """robots_verdict in a process of its own, with a time limit. A robots.txt of
    thousands of rules with a hundred wildcards in one took minutes to decide one path
    (openroles' matcher backtracks), and threads would have waited on it together."""
    try:
        r = subprocess.run([sys.executable, os.path.abspath(__file__), "_robots_one",
                            json.dumps({"base": base, "paths": paths})],
                           capture_output=True, text=True, timeout=timeout,
                           encoding="utf-8", errors="replace")
        return json.loads(r.stdout)
    except (subprocess.TimeoutExpired, ValueError):
        return {"status": "unconfirmed", "search": None, "posting": None,
                "crawl_delay": None, "ai_input": None,
                "why": f"robots.txt could not be decided within {timeout}s"}


def search_check(board: dict, transport=None) -> dict:
    """Whether a board's search answers a reader with no login, tried only where its
    robots.txt allows the search path: open (an honest client gets the page), open_browser
    (only ordinary browser headers do), blocked, not_found, or not_tried."""
    import company_research as cr
    r = board.get("robots") or {}
    if r.get("search") is not True or not board.get("search"):
        return {"status": "not_tried", "http": None}
    transport = transport or _curl
    url = board["search"]
    got = None
    for headers, ok in (({"User-Agent": HONEST_UA, "Accept": "text/html,*/*"}, "open"),
                        (cr.BROWSER_HEADERS, "open_browser")):
        for _hop in range(5):
            status, head, body = transport(url, headers)
            loc = (head or {}).get("location")
            if status in (301, 302, 303, 307, 308) and loc:
                from urllib.parse import urljoin
                nxt = urljoin(url, loc)
                if (urlsplit(nxt).hostname or "") != (urlsplit(url).hostname or ""):
                    break                  # another host: its own robots.txt is not read here
                url = nxt
                continue
            break
        state, _why = cr.classify(status, body)
        got = {"status": ok if state == "ok" else
               ("not_found" if state == "not_found" else "blocked"), "http": status}
        if state in ("ok", "not_found"):
            return got
    return got or {"status": "blocked", "http": None}


def robots(paths=None, write: bool = False, today: dt.date | None = None,
           searches: bool = True, root: str = DIR) -> list[str]:
    """Re-check every board's robots.txt (and, where it allows the search, whether the
    search answers), by code. Returns one line a board; with `write`, saves the verdicts."""
    today = today or dt.date.today()
    files = paths or _files(root)
    lines = []
    for path in files:
        table = _read(path)
        bs = _all_boards(table)
        with cf.ThreadPoolExecutor(6) as ex:
            verdicts = list(ex.map(lambda b: _robots_child(b["url"], b.get("paths") or {}), bs))
        for b, v in zip(bs, verdicts):
            v["checked"] = today.isoformat()
            b["robots"] = v
        if searches:
            with cf.ThreadPoolExecutor(6) as ex:
                found = list(ex.map(search_check, bs))
            for b, s in zip(bs, found):
                s["checked"] = today.isoformat()
                b["public_search"] = s
        for b in bs:
            lines.append(f"{local_path.rel(path, root)}: {b['name']}: robots "
                         f"{b['robots']['status']}, public search "
                         f"{(b.get('public_search') or {}).get('status')}")
        if write:
            dump(path, table)
    return lines


_LAST: dict = {}
_LOCK = __import__("threading").Lock()


def _paced(url: str, gap: float = 1.5) -> None:
    """One request to a host every `gap` seconds across this run's threads: an
    encyclopedia asked a run that read twenty of its pages at once to slow down."""
    import time
    host = (urlsplit(url).hostname or "").lower()
    with _LOCK:
        now = time.time()
        start = max(now, _LAST.get(host, 0.0) + gap)
        _LAST[host] = start
    if start > now:
        time.sleep(start - now)


def _page_text(url: str, pages: str | None, transport=None) -> tuple[str | None, str]:
    """(the readable text of a page, why not): robots.txt read first, as company research
    reads it; a page whose site disallows it, or asks for no AI input, is not fetched."""
    import hashlib
    import company_research as cr
    key = hashlib.sha1(url.encode("utf-8")).hexdigest()[:20]
    cached = os.path.join(pages, key + ".txt") if pages else None
    if cached and os.path.exists(cached):
        with open(cached, encoding="utf-8") as fh:
            return fh.read(), ""
    if transport is None:
        parts = urlsplit(url)
        here = (parts.path or "/") + ("?" + parts.query if parts.query else "")
        v = _robots_child(f"{parts.scheme}://{parts.netloc}", {"search": here})
        if v.get("search") is not True:
            why = v.get("why") or "robots.txt disallows it"
            return None, why if why.startswith("robots.txt") else "robots.txt: " + why
        if v.get("ai_input") == "no":
            return None, "its robots.txt asks for no AI input"
    transport = transport or _curl
    for _hop in range(6):
        if transport is _curl:
            _paced(url)
        status, head, body = transport(url, cr.BROWSER_HEADERS)
        if status == 429 and _hop == 0:
            import time
            wait = cr._retry_after((head or {}).get("retry-after"))
            time.sleep(min(30.0, wait if wait is not None else 10.0))
            continue
        loc = (head or {}).get("location")
        if status in (301, 302, 303, 307, 308) and loc:
            from urllib.parse import urljoin
            url = urljoin(url, loc)
            continue
        break
    state, why = cr.classify(status, body)
    if state != "ok":
        return None, why or state
    if "pdf" in (head or {}).get("content-type", "") or body[:5] == "%PDF-":
        return None, "a PDF, which this check does not read"
    text = cr.read_page(body, url)["text"]
    if cached:
        os.makedirs(pages, exist_ok=True)
        with open(cached, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    return text, ""


def verify_fact(fact: dict, text: str | None, why: str = "") -> dict:
    """The fact with `verified` set from the page text: its quote, and every name in its
    `on_page`, must be on the page."""
    import company_research as cr
    f = dict(fact)
    f.pop("why", None)
    if text is None:
        f["verified"], f["why"] = False, f"the source could not be read: {why}"
        return f
    page = cr.norm_text(text)
    q = cr.norm_text(f.get("quote"))
    missing = [n for n in f.get("on_page") or [] if cr.norm_text(n) not in page]
    if not (f.get("quote") or "").strip():
        f["verified"], f["why"] = False, "no sentence on the page was found that says it"
    elif _size(f.get("quote")) < MIN_QUOTE_WORDS:
        f["verified"], f["why"] = False, "the quote is too short to prove anything"
    elif q not in page:
        f["verified"], f["why"] = False, "the quote is not on the page"
    elif missing:
        f["verified"], f["why"] = False, "not on the page: " + ", ".join(missing)
    else:
        f["verified"] = True
    return f


def verify(paths=None, write: bool = False, today: dt.date | None = None,
           pages: str | None = None, root: str = DIR, transport=None) -> list[str]:
    """Fetch every fact's source and check its quote is there. One line a fact not
    verified; with `write`, saves `verified`, `why` and the day."""
    today = today or dt.date.today()
    lines = []
    for path in paths or _files(root):
        table = _read(path)
        facts = _all_facts(table)
        urls = sorted({f["source"] for f in facts})
        with cf.ThreadPoolExecutor(6) as ex:
            got = dict(zip(urls, ex.map(lambda u: _page_text(u, pages, transport), urls)))
        for f in facts:
            text, why = got[f["source"]]
            new = verify_fact(f, text, why)
            new["checked"] = today.isoformat()
            f.clear()
            f.update(new)
            if not f["verified"]:
                label = (f.get("name") or f.get("phrase") or f.get("metro") or f.get("topic")
                         or f.get("family") or f["source"])
                lines.append(f"{local_path.rel(path, root)}: {label}: {f['why']}")
        if write:
            dump(path, table)
    return lines


def dump(path: str, table) -> None:
    """Write a table the one way: two-space indent, UTF-8, a final newline."""
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(table, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


# ------------------------------------------------------------------ the command

def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["_robots_one"]:
        a = json.loads(argv[1])
        print(json.dumps(robots_verdict(a["base"], a["paths"])))
        return 0
    if argv[:1] == ["--check"]:
        problems = check()
        for p in problems:
            print(p)
        c = counts()
        print(f"markets: {len(c['countries'])} countries, {len(c['fields'])} fields, "
              f"{len(c['levels'])} levels, {len(c['regions'])} countries with regions; "
              f"{len(problems)} problem(s)", file=sys.stderr)
        return 1 if problems else 0
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("brief", "gaps"):
        p = sub.add_parser(name)
        p.add_argument("country")
        p.add_argument("--field")
        p.add_argument("--level")
        p.add_argument("--region")
        p.add_argument("--city")
        p.add_argument("--employers", type=int, default=0)
    for name in ("robots", "verify"):
        p = sub.add_parser(name)
        p.add_argument("tables", nargs="*")
        p.add_argument("--write", action="store_true")
        if name == "verify":
            p.add_argument("--pages", help="keep fetched page text here between runs")
    sub.add_parser("counts")
    a = ap.parse_args(argv)
    if a.cmd == "brief":
        print(brief(a.country, a.field, a.level, a.region, a.city, a.employers))
    elif a.cmd == "gaps":
        for g in gaps(a.country, a.field, a.level, a.region, a.city, a.employers):
            print("- " + g)
    elif a.cmd == "robots":
        for line in robots(a.tables or None, a.write):
            print(line)
    elif a.cmd == "verify":
        lines = verify(a.tables or None, a.write, pages=a.pages)
        for line in lines:
            print(line)
        print(f"markets: {len(lines)} fact(s) not verified", file=sys.stderr)
    elif a.cmd == "counts":
        print(json.dumps(counts(), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
