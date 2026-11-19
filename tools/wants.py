#!/usr/bin/env python3
"""What the person wants from a search, said once, kept in one record and followed by every
part of the search.

A person's wants lived in settings each stage of a search reads on its own: the bar
(search.py BAR_DECLINED for employers by name, BAR_SECTORS_OUT for kinds of employer), the
tier lifts (employers.py TIER_1, TIER_2, TIER_3, YC_AND_BACKED), the leverage lifts
(search.py OPP_LEVERAGE), what is searched by name (SCRAPE_EMPLOYERS, SCRAPE_QUERIES) and
whose own job sites are read (boards.py BOARDS). One spoken "no" was carried into them by hand,
a missed one went on working against the person, and nothing said so: four employers the
person had turned down were still lifted, and one's own job site was read every round
(issue 307). This is the one writer of a "no" and a "yes", the record they are kept in, and
the check between it and the settings that search.

**The record, profile/wants.json** (issue 327). Each want with the person's words, the day and
whether it cuts (hard) or only ranks (soft):

    {"employers": {"<employer as written>": {"want": "out", "hard": true, "why": "<what the
                    bar says>", "said": "<their words>", "date": "YYYY-MM-DD", "by": "chat",
                    "name": "<as they said it>"},
                   "<employer as written>": {"want": "in", "hard": false, "tiers": ["TIER_2"],
                    "said": "...", "date": "...", "by": "moved"}},
     "kinds": {"<kind of employer>": {"want": "out", "hard": true, "why": "...", "said": "...",
                "date": "...", "by": "chat"}},
     "settings": {"places": {"setting": "search.py SCRAPE_LOCATIONS", "value": [...],
                   "hard": true, "said": "...", "date": "...", "by": "chat"}},
     "signals": {"<its name>": {"words": "<what it is, in plain words, or empty until a chat
                  asks>", "hard": false, "said": "...", "date": "...", "by": "moved",
                  "patterns": [{"setting": "OPP_LEVERAGE", "match": "<the entry's reason>"}]}},
     "families": {...the same, for the kinds of role...}}

An employer or a kind out is a cut by the bar (hard), unless it was written soft on purpose
(`--soft`): then a job there is only ranked down (opportunity.SOFT_NO), never cut. Every "no"
written before, and every one written without the flag, is hard. An employer in is lifted by
its tier (soft: TIER_1 +30, TIER_2 +20, YC_AND_BACKED +14, TIER_3 +10). This file compiles the
record: the bar's employers and kinds out (bar.DECLINED, bar.SECTORS_OUT, run_round.
declined_now, `sectors_out`) and the tier sets (opportunity.TIER_1 and the rest) are read from
it, together with anything still written in the old settings, and what is searched by name and
whose job sites are read are checked against it (`drift`). `move` takes the old settings into
it, each entry's effect unchanged (the profile upgrade wants-moved runs it by itself).

**Wants that stay single settings** (`SETTINGS`): where the person searches, where they search
for remote work, the pay floor and the pay cut line are each one setting many modules read
(search.py SCRAPE_LOCATIONS, SCRAPE_REMOTE_LOCATIONS, SALARY_FLOOR, SALARY_CUT_BELOW). The
setting stays what the code reads; the record keeps the person's words for it, and `set`
changes both in one step (profile_set, and the page's own Settings through tools/tweak.py).
Hard or soft follows what the setting does: the places, the remote rule and the cut line
leave jobs out, the floor only ranks a job stating less down.

**Wants written as patterns** (`PATTERN_SETTINGS`): the work-life signs among the leverage
lifts (OPP_LEVERAGE) and the kinds of role the scoring weighs (OPP_TITLE_FAMILY,
OPP_WRONG_FAMILY, FIT_WRONG_FAMILY) stay patterns, since a pattern is what reads a posting. The
record keeps each in plain words, linked to the pattern entries that carry it by the entry's
own reason (or its pattern, where it gives none). `seed` writes what is not kept yet, with the
entry's reason as its words, or none where it has no reason: a chat asks the person and writes
theirs with `words`, never guessed. A sector pattern (BAR_EXCLUDED) stays where it is: which
kind it means needs a chat, and `show` and Your rules say which are still written that way.

    python3 tools/wants.py decline "<employer>" --said "<their words>" [--soft]
    python3 tools/wants.py undecline "<employer>"
    python3 tools/wants.py sector-out "<kind of employer>" --said "<their words>" [--soft]
    python3 tools/wants.py sector-back "<kind of employer>"
    python3 tools/wants.py want "<employer>" --tier 1|2|3|backed --said "<their words>"
    python3 tools/wants.py unwant "<employer>"
    python3 tools/wants.py set places|remote|pay-floor|pay-cut [<value>...] [--add X] [--drop X]
                               --said "<their words>"
    python3 tools/wants.py words "<signal or family>" "<plain words>" --said "<their words>"
    python3 tools/wants.py link "<signal or family>" <SETTING> "<the entry's reason or pattern>"
    python3 tools/wants.py forget "<signal or family>"
    python3 tools/wants.py show      what the record holds, in plain words
    python3 tools/wants.py move      the old settings taken into the record, effect unchanged
    python3 tools/wants.py seed      the single settings and the patterns kept in the record
    python3 tools/wants.py check     exit 1 while anything turned down is still searched or lifted
    python3 tools/wants.py tidy      takes every employer turned down off what searches or lifts it
    python3 tools/wants.py header    what a search searches with, as a round prints it first

`decline` turns the employer down by name (in the record, keyed as the bar reads it), takes it
off every list that lifts or searches it (the tier sets, SCRAPE_EMPLOYERS, SCRAPE_QUERIES,
boards.py), keeps the person's words and the day, and notes it under Deal-breakers in
profile/CLAUDE.md; with `--soft` it is only ranked down, so it comes off the lists that lift it
and nothing else. It refuses a form the bar would never match (a pattern, a kind of employer,
two employers at once). `sector-out` does the same for a kind of employer, one rule on what
the employer is (tools/sector.py: the person's catalogue, employers.py NOT_TECH, or the
posting saying it of itself), never a list of names. A lift written as a pattern
(OPP_LEVERAGE) is code: `check` names its line, and it is changed by hand.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import person  # noqa: E402

TIERS = (("TIER_1", 30), ("TIER_2", 20), ("YC_AND_BACKED", 14), ("TIER_3", 10))
# Where the prose a chat reads keeps the person's deal-breakers (profile/CLAUDE.md).
NOTES_FILE = "CLAUDE.md"
NOTES_HEADING = re.compile(r"^(#{2,4})\s+Deal-?breakers\b.*$", re.I | re.M)
NOTE_MARK = "<!-- turned down: {} -->"
KIND_MARK = "<!-- turned down kind: {} -->"
# What the last round searched with, for the next to say what changed since.
RECORD = ("documents", "rounds", "searched", "with.json")
RECORD_KEEP = 5
# A group or a kind said where one employer's name belongs: the bar compares names, so an
# entry "pension funds" or "MBB" never matched an employer and cut nothing.
GROUPS = {"bank", "insurer", "insurance company", "insurance", "pension fund", "consultancy",
          "consulting firm", "airline", "retailer", "retail", "telco", "startup", "fintech",
          "big four", "big 4", "mbb", "faang", "maang", "public sector", "government",
          "staffing agency", "recruitment agency", "agency", "hedge fund", "bank and insurer",
          "investment bank", "asset manager", "crypto", "gambling", "charity", "university"}
# A group of named employers, never a kind the catalogue files an employer under: each of its
# employers is turned down by name.
NAMED_GROUPS = {"big four", "big 4", "mbb", "faang", "maang", "magnificent seven"}


class Refused(ValueError):
    """A "no" that cannot be written as asked, said in plain words."""


# ------------------------------------------------------------------ the one record

# The person's wants, one file (issue 327): the module docstring gives its shape.
WANTS_FILE = "wants.json"
POINTS = dict(TIERS)
# How a person names a tier in `want`, and the tier set it compiles into.
TIER_WORDS = {"1": "TIER_1", "2": "TIER_2", "3": "TIER_3", "backed": "YC_AND_BACKED"}
# Every part of the record (issue 327): the employers and kinds of employer in and out, the
# single settings a want lives in, and the work-life signs and kinds of role the scoring weighs.
SECTIONS = ("employers", "kinds", "settings", "signals", "families")
# The wants that are one setting each, in search.py: {want: (setting, hard, what it is)}. Hard
# or soft follows what the setting does: a place not searched, a remote rule and the cut line
# leave a job out; the floor only ranks a job stating less down ("a decision input, never a
# cut", score_posting.py).
SETTINGS = {
    "places": ("SCRAPE_LOCATIONS", True, "the places you search"),
    "remote": ("SCRAPE_REMOTE_LOCATIONS", True, "where you search for remote work"),
    "pay floor": ("SALARY_FLOOR", False, "your pay floor"),
    "pay cut": ("SALARY_CUT_BELOW", True, "your pay cut line"),
}
# The settings whose pattern entries carry the wants written as patterns, by section.
PATTERN_SETTINGS = {"signals": ("OPP_LEVERAGE",),
                    "families": ("OPP_TITLE_FAMILY", "OPP_WRONG_FAMILY", "FIT_WRONG_FAMILY")}
SECTION_WORD = {"signals": "sign of work-life balance", "families": "kind of role"}
# A leverage entry reads a work-life sign where it reads working terms ("terms", opportunity.
# SCOPES) or its reason or pattern names one; travel and a commute only as a cost (a lift on
# "travel" is the travel trade, a penalty on it is the travel asked of the person). Never one
# that reads what the employer is.
WORK_LIFE = re.compile(r"work[- ]?life|flexib\w*|\bhours\b|overtime|on[- ]call|weekends?|"
                       r"evenings?|remote|hybrid|in[- ]office|office days?|(?:four|4)[- ]day|"
                       r"compressed|crunch|burn[- ]?out|\bshifts?\b|balance", re.I)
WORK_LIFE_COST = re.compile(r"\btravel\w*|commut\w*", re.I)
_NONE = object()
_wants_cache: dict = {}


def _wants_path() -> str:
    return person.path(WANTS_FILE)


def load() -> dict:
    """The record as stored ({"employers": {...}, "kinds": {...}, ...}, every part of SECTIONS),
    each part {} where there is none. Read again whenever the file changes, by its time and its size (MAINTAINING.md, a
    cache is keyed on what it reads). A file that cannot be read is said once, on stderr, and
    read as empty: every setting still written the old way goes on working meanwhile."""
    try:
        p = _wants_path()
        st = os.stat(p)
    except (OSError, person.NoProfile):
        return {s: {} for s in SECTIONS}
    at = (p, st.st_mtime_ns, st.st_size)
    if _wants_cache.get("at") != at:
        try:
            with open(p, encoding="utf-8") as fh:
                got = json.load(fh)
            if not isinstance(got, dict):
                raise ValueError("not a record")
        except (OSError, ValueError) as e:
            if _wants_cache.get("said") != at:
                print(f"wants: profile/{WANTS_FILE} cannot be read ({e}); until it is put "
                      "right, only the settings written the old way are read", file=sys.stderr)
            _wants_cache["said"] = at
            got = {}
        _wants_cache.update(at=at, rec=got)
    got = _wants_cache["rec"]
    return {s: {str(k): v for k, v in dict(got.get(s) or {}).items() if isinstance(v, dict)}
            for s in SECTIONS}


def _save(rec: dict) -> None:
    """Write the record whole, sorted, as merge_state merges it (profile/wants.json)."""
    p = _wants_path()
    out = {s: dict(sorted(rec.get(s, {}).items())) for s in SECTIONS}
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, indent=2, ensure_ascii=False, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, p)
    _wants_cache.clear()


def _hard(v: dict) -> bool:
    """Whether a "no" in the record cuts: every one does but one written soft on purpose."""
    return v.get("hard") is not False


def held_declined() -> dict:
    """{employer key: what the bar says} for every employer the record turns down (hard),
    read through the employer key as the bar reads its list (company_key.keyed)."""
    from company_key import keyed
    return keyed({k: str(v.get("why") or v.get("said") or "turned down")
                  for k, v in load()["employers"].items()
                  if v.get("want") == "out" and _hard(v)})


def held_kinds() -> dict:
    """{kind, as sector.kind_key: what the bar says} for every kind the record turns down
    (hard)."""
    import sector
    return {sector.kind_key(k): str(v.get("why") or v.get("said") or "turned down")
            for k, v in load()["kinds"].items()
            if v.get("want") == "out" and _hard(v) and sector.kind_key(k)}


def held_soft() -> dict:
    """{"employers": {employer key: their words}, "kinds": {kind: their words}} for every "no"
    the person said only ranks down (written with `--soft`): opportunity.py ranks a job there
    down by SOFT_NO and says why, and nothing cuts it. An employer or a kind also turned down
    hard is not here: the cut stands."""
    import sector
    from company_key import keyed
    rec = load()
    hard_e, hard_k = held_declined(), held_kinds()
    emp = {k: v for k, v in keyed({e: str(v.get("said") or v.get("why") or "you would rather "
                                          "not work there")
                                   for e, v in rec["employers"].items()
                                   if v.get("want") == "out" and not _hard(v)}).items()
           if k not in hard_e}
    kinds = {sector.kind_key(k): str(v.get("said") or v.get("why") or "you would rather not "
                                     "work at one")
             for k, v in rec["kinds"].items()
             if v.get("want") == "out" and not _hard(v) and sector.kind_key(k)}
    return {"employers": emp, "kinds": {k: w for k, w in kinds.items() if k not in hard_k}}


def held_tiers() -> dict:
    """{tier set: {employers as written}} for every employer the record lifts: what
    opportunity.py joins to the sets still written in employers.py."""
    out: dict = {s: set() for s, _p in TIERS}
    for name, v in load()["employers"].items():
        for s in v.get("tiers") or ():
            if s in out:
                out[s].add(name)
    return out


def _words(why: str) -> tuple[str, str]:
    """(the person's own words, the day) inside a reason the bar was given: "turned down in a
    chat, 2026-11-10: \"no banks\"" is ("no banks", "2026-11-10"); one written by hand is
    itself, with the first date in it."""
    why = " ".join(str(why or "").split())
    m = re.match(r"^turned down (?:in a chat|on the page), (\d{4}-\d\d-\d\d):?\s*\"?(.*?)\"?$",
                 why)
    if m:
        return m.group(2), m.group(1)
    d = re.search(r"\b(20\d\d-\d\d-\d\d)\b", why)
    return why, d.group(1) if d else ""


def _set_out(rec: dict, section: str, entry: str, why: str, said: str, day: str, by: str,
             name: str = "", hard: bool = True) -> None:
    """One "out" written into the record, keeping a lift it already carries (a drifted lift
    stays until `tidy`, so its effect is unchanged until then)."""
    old = rec[section].get(entry) or {}
    rec[section][entry] = {**{k: v for k, v in old.items() if k in ("tiers", "name")},
                           "want": "out", "hard": bool(hard), "why": why, "said": said,
                           "date": day, "by": by, **({"name": name} if name else {})}


def compiled() -> dict:
    """What every stage reads, now: the employers and kinds turned down and the tier sets, from
    the record and the old settings together (`move` takes the second into the first)."""
    import run_round
    tiers = held_tiers()
    if person.exists("employers.py"):
        for s, _p in TIERS:
            tiers[s] |= {str(v) for v, _l, _ok in _entries("employers.py", s)
                         if isinstance(v, str)}
    return {"declined": run_round.declined_now(), "kinds": sectors_out(), "tiers": tiers}


# ------------------------------------------------------------------ the settings, as they are now

def _source(name: str) -> tuple[str, ast.Module | None]:
    try:
        with open(person.path(name), encoding="utf-8") as fh:
            text = fh.read()
        return text, ast.parse(text)
    except (OSError, SyntaxError, person.NoProfile):
        return "", None


def _entries(name: str, key: str) -> list[tuple]:
    """[(entry, line, written plain)] for the list, set or dict `key` in profile/<name>: a dict
    by its keys. One written as code is read as the profile module has it, each at the
    setting's own line, and can only be changed by hand."""
    import profile_set
    _text, tree = _source(name)
    if tree is None:
        return []
    n = profile_set._node(tree, key)
    if n is None:
        return []
    node = profile_set._container(n)
    lines: list = []
    if node is not None and not isinstance(node, ast.Call):
        items = node.keys if isinstance(node, ast.Dict) else node.elts
        out = []
        for el in items:
            if el is None:
                continue
            try:
                out.append((ast.literal_eval(el), el.lineno, True))
            except ValueError:
                out.append((None, el.lineno, False))
        if all(ok for _v, _l, ok in out):
            return out
        lines = [ln for _v, ln, _ok in out]
    try:
        got = getattr(person.module(name[:-3]), key, ()) or ()
    except Exception:  # noqa: BLE001  a profile file that does not load: nothing read
        return []
    vals = list(got.keys() if isinstance(got, dict) else got)
    return [(v, lines[i] if len(lines) == len(vals) else n.lineno, False)
            for i, v in enumerate(vals)]


def _plain(name: str, key: str, default):
    import profile_set
    try:
        got = profile_set.get(name, key)
    except Exception:  # noqa: BLE001  no profile file: the default
        return default
    if got is profile_set.MISSING:
        return default
    if got is None:
        try:
            got = getattr(person.module(name[:-3]), key, default)
        except Exception:  # noqa: BLE001
            return default
    return got


def declined_now() -> dict:
    """{employer key: the person's words} for every employer turned down by name, as the
    record and the settings hold it now (run_round.declined_now)."""
    import run_round
    return run_round.declined_now()


def sectors_out() -> dict:
    """{kind, as sector.kind_key: the person's words} for every kind of employer turned down,
    as the record and search.py BAR_SECTORS_OUT hold it now: an entry still in the setting
    reads as it did before it was moved."""
    import sector
    got = _plain("search.py", "BAR_SECTORS_OUT", {})
    out = held_kinds()
    out.update({sector.kind_key(k): str(v) for k, v in dict(got or {}).items()
                if sector.kind_key(k)})
    return out


def catalogue() -> dict:
    """The person's catalogue of what each employer is (employers.py NOT_TECH), read now."""
    if not person.exists("employers.py"):
        return {}
    return dict(_plain("employers.py", "NOT_TECH", {}) or {})


def out_fn():
    """A function from an employer's name to why it is out, by name or by kind, or "": the
    settings read once, now. What a round asks before it spends a request on an employer."""
    import bar
    from company_key import entry_key
    declined, kinds, cat = declined_now(), sectors_out(), catalogue()

    def out(name) -> str:
        k = entry_key(name)
        if k and k in declined:
            return declined[k]
        return bar.kind_out(str(name or ""), out=kinds, catalogue=cat) if kinds else ""
    out.declined, out.kinds = declined, kinds
    return out


def _out_key(name, declined: dict, kinds: dict, cat: dict,
             soft: bool = False) -> tuple[str, str, str]:
    """(employer key, kind, why) for an employer out, or ("", "", ""); with `soft`, out only
    as a "no" that ranks down."""
    import bar
    import sector
    from company_key import entry_key
    k = entry_key(name)
    if k and k in declined:
        return k, "", declined[k]
    if kinds:
        what = sector.kind_key(sector.kind(str(name or ""), cat))
        if what in kinds:
            return "", what, (f"a kind of employer you would rather not work for ({what}): "
                              f"{kinds[what]}" if soft else bar.kind_why(what, kinds[what]))
    return "", "", ""


# ------------------------------------------------------------------ the check

def _finding(file, line, setting, entry, does, why, key="", kind="", plain=True, fix="",
             about="out") -> dict:
    """One place a setting disagrees with what the person wants. `about`: "out" (something
    turned down still searched or lifted, which `check` fails on), "soft" (one they would
    rather not work for still lifted), "setting" (a single setting the record keeps otherwise)
    or "link" (a pattern and the record's words for it, one without the other)."""
    return {"file": f"profile/{file}", "line": line, "setting": setting, "entry": entry,
            "does": does, "why": why, "key": key, "kind": kind, "tidy": bool(plain),
            "about": about,
            "fix": fix or ("take it off: `python3 tools/wants.py tidy`" if plain
                           else "change that line by hand")}


def _names(pattern, text: str) -> bool:
    """Whether a lift's pattern names this employer whole, never a word inside it: a lift for
    consulting work that reads "Consulting" in a consultancy's name is about the work."""
    from company_key import entry_key
    m = pattern.search(text) if hasattr(pattern, "search") else None
    return bool(m) and entry_key(m.group(0)) == entry_key(text)


def drift() -> list[dict]:
    """Every place a setting disagrees with what the person wants, each with the line to
    change: an employer or a kind of employer turned down that is still searched, read from its
    own job site or lifted ("out"); one they would only rather not work for that is still
    lifted ("soft"); a single setting holding other than what the record keeps for it
    ("setting"); and a work-life sign or a kind of role that a pattern weighs with no words in
    the record, or words in the record that no pattern carries any more ("link")."""
    return _turned_down() + _settings_drift() + _links_drift()


def _turned_down() -> list[dict]:
    from opportunity import _names_in, _scoped
    declined, kinds, cat = declined_now(), sectors_out(), catalogue()
    soft = held_soft()
    soft_e, soft_k = soft["employers"], soft["kinds"]
    if not declined and not kinds and not soft_e and not soft_k:
        return []
    out: list[dict] = []

    def hit(entry, lifts: bool) -> tuple:
        k, kind, why = _out_key(entry, declined, kinds, cat)
        if why:
            return k, kind, why, "out"
        if lifts and (soft_e or soft_k):
            k, kind, why = _out_key(entry, soft_e, soft_k, cat, soft=True)
            if why:
                return k, kind, why, "soft"
        return "", "", "", ""

    def look(file, setting, does, lifts=False):
        for entry, line, plain in _entries(file, setting):
            if not isinstance(entry, str):
                continue
            k, kind, why, about = hit(entry, lifts)
            if why:
                out.append(_finding(file, line, setting, entry, does, why, k, kind, plain,
                                    about=about))

    look("search.py", "SCRAPE_EMPLOYERS", "is searched by name every round")
    for entry, line, plain in _entries("search.py", "SCRAPE_QUERIES"):
        c = " %s " % " ".join(str(entry or "").lower().split())
        hit_ = _names_in(c, set(declined)) if isinstance(entry, str) and declined else None
        if hit_:
            out.append(_finding("search.py", line, "SCRAPE_QUERIES", entry,
                                "is a search for it by name", declined[hit_], hit_, "", plain))
    if person.exists("boards.py"):
        look("boards.py", "BOARDS", "has its own job site read every round")
    # A lift is wrong for a "no" either way: a soft one ranks the employer down, and a lift
    # working against that is what turning it down soft takes off.
    if person.exists("employers.py"):
        for setting, pts in TIERS:
            look("employers.py", setting, f"is lifted +{pts} on every job there", lifts=True)
    # A lift the record itself still carries for an employer turned down (a merge of two
    # chats, or a lift it kept when it was moved): taken off the record by `tidy`.
    for entry, v in sorted(load()["employers"].items()):
        for setting in v.get("tiers") or ():
            if setting not in POINTS:
                continue
            k, kind, why, about = hit(entry, True)
            if why:
                out.append(_finding(WANTS_FILE, None, setting, entry,
                                    f"is lifted +{POINTS[setting]} on every job there", why,
                                    k, kind, True, about=about))
    # A lift written as a pattern: one naming the employer whole, or, for a kind turned down,
    # one reading what the employer is (scope "employer") that names the kind.
    lev = _plain("search.py", "OPP_LEVERAGE", []) or []
    lines = [ln for _v, ln, _ok in _entries("search.py", "OPP_LEVERAGE")]
    written = dict(_plain("search.py", "BAR_DECLINED", {}) or {})
    from company_key import entry_key
    names: dict = {}
    for e in written:
        names.setdefault(entry_key(e), []).append(str(e))
    for k in (*declined, *soft_e):
        names.setdefault(k, []).append(k)
    for i, e in enumerate(lev):
        try:
            pat, pts, reason, scope, _aside = _scoped(e)
        except (TypeError, ValueError):
            continue
        if (pts or 0) <= 0 or pat is None:
            continue
        line = lines[i] if i < len(lines) else None
        for k, said in names.items():
            why, about = ((declined[k], "out") if k in declined
                          else (soft_e[k], "soft") if k in soft_e else ("", ""))
            if why and any(_names(pat, x) for x in said):
                out.append(_finding("search.py", line, "OPP_LEVERAGE", str(reason),
                                    f"lifts {said[0]} +{pts} by name", why, k, "", False,
                                    "take its name out of that pattern by hand", about))
        for pool, about in ((kinds, "out"), (soft_k, "soft")):
            for kind, why in pool.items():
                if scope == "employer" and pat.search(kind):
                    out.append(_finding("search.py", line, "OPP_LEVERAGE", str(reason),
                                        f"lifts every {kind} +{pts}", why, "", kind, False,
                                        "take that kind out of the pattern by hand", about))
    return out


def _shown(value) -> str:
    """A setting's value as a line says it."""
    if isinstance(value, (list, tuple)):
        return "[" + "; ".join(str(x) for x in value) + "]" if value else "nothing"
    if isinstance(value, int) and not isinstance(value, bool):
        return f"{value:,}"
    return str(value)


def _who(v: dict) -> str:
    """Who wrote a record entry, and when, as a line says it."""
    day = v.get("date") or "no date"
    if v.get("said"):
        return f"your words \"{v['said']}\", {day}"
    if v.get("by") == "moved":
        return f"kept from your settings as they were on {day}"
    if v.get("by") == "page":
        return f"set on your page, {day}"
    return f"set by a chat, {day}"


def _same(a, b) -> bool:
    """Equal as a setting and a record keep it: a tuple and a list holding the same alike."""
    norm = (lambda x: list(x) if isinstance(x, (list, tuple)) else x)
    return norm(a) == norm(b)


def _line(file: str, key: str):
    import profile_set
    _text, tree = _source(file)
    n = profile_set._node(tree, key) if tree is not None else None
    return n.lineno if n is not None else None


def setting_now(want: str):
    """What a single-setting want's setting holds now, or _NONE where it is not set."""
    return _plain("search.py", SETTINGS[want][0], _NONE)


def _settings_drift() -> list[dict]:
    """Each single setting holding other than what the record keeps for it: changed by hand
    since, or taken out. Never put right by itself: which is right is the person's to say."""
    out = []
    for want, v in sorted(load()["settings"].items()):
        if want not in SETTINGS:
            continue                     # a want a later version knows: kept, never read here
        key, _hard_, what = SETTINGS[want]
        now = setting_now(want)
        if _same(None if now is _NONE else now, v.get("value")):
            continue
        does = (f"{what} {'is not set' if now is _NONE else 'read ' + _shown(now)}, though "
                f"your record of what you want keeps {_shown(v.get('value'))} ({_who(v)})")
        out.append(_finding("search.py", _line("search.py", key), key, want, does, "",
                            plain=False, about="setting",
                            fix=("write the one that is right with `python3 tools/wants.py set "
                                 f"{want.replace(' ', '-')} <value> --said \"<their words>\"`")))
    return out


def patterns(section: str) -> list[dict]:
    """Every pattern entry of the settings `section` links to (PATTERN_SETTINGS), each
    {"setting", "match", "why", "points", "pattern", "line", "record"}: "match" is what the
    record links it by (its own reason, or its pattern where it gives none), and "record"
    whether its words belong in the record (every kind of role; a leverage entry only where it
    reads a work-life sign)."""
    out = []
    for setting in PATTERN_SETTINGS[section]:
        for entry, line, _ok in _entries("search.py", setting):
            if not isinstance(entry, (tuple, list)) or len(entry) < 2:
                continue
            pat, pts = entry[0], entry[1]
            why = " ".join(entry[2].split()) if len(entry) > 2 and isinstance(entry[2], str) \
                else ""
            src = getattr(pat, "pattern", pat if isinstance(pat, str) else "")
            if not isinstance(src, str) or not (why or src):
                continue
            out.append({"setting": setting, "match": why or src, "why": why,
                        "points": int(pts) if isinstance(pts, (int, float)) else 0,
                        "pattern": src,
                        "line": line,
                        "record": setting != "OPP_LEVERAGE" or _work_life(entry)})
    return out


def _work_life(entry) -> bool:
    """Whether a leverage entry reads a work-life sign (WORK_LIFE): one reading working terms,
    or one whose reason or pattern names a sign, never one reading what the employer is."""
    from opportunity import _scoped
    try:
        pat, pts, reason, scope, _aside = _scoped(entry)
    except (TypeError, ValueError):
        return False
    if scope == "employer":
        return False
    if scope == "terms":
        return True
    text = f"{reason} {getattr(pat, 'pattern', '')}"
    return bool(WORK_LIFE.search(text) or ((pts or 0) < 0 and WORK_LIFE_COST.search(text)))


def _links(v: dict) -> list[tuple[str, str]]:
    return [(str(x.get("setting") or ""), " ".join(str(x.get("match") or "").split()))
            for x in v.get("patterns") or () if isinstance(x, dict)]


def _links_drift() -> list[dict]:
    """A record entry no pattern carries any more, and a pattern the record keeps no words
    for."""
    rec = load()
    out = []
    for section in PATTERN_SETTINGS:
        found = patterns(section)
        have = {(p["setting"], p["match"]) for p in found}
        linked: set = set()
        for name, v in sorted(rec[section].items()):
            links = _links(v)
            linked |= set(links)
            gone = [f"{s} \"{m}\"" for s, m in links if (s, m) not in have]
            if gone or not links:
                said = v.get("words") or name
                out.append(_finding(
                    WANTS_FILE, None, section, name,
                    f"your record keeps \"{said}\" as a {SECTION_WORD[section]}, but "
                    + (f"no pattern carries it any more ({', '.join(gone)})" if gone
                       else "no pattern is linked to it"), "", plain=False, about="link",
                    fix=("link it to the pattern that carries it now with `python3 tools/wants.py "
                         f"link \"{name}\" <SETTING> \"<its reason>\"`, or take it off with "
                         f"`python3 tools/wants.py forget \"{name}\"`")))
        for p in found:
            if p["record"] and (p["setting"], p["match"]) not in linked:
                out.append(_finding(
                    "search.py", p["line"], p["setting"], p["match"],
                    f"\"{p['match']}\" weighs a {SECTION_WORD[section]} ({p['points']:+d}) your "
                    "record of what you want has no words for", "", plain=False, about="link",
                    fix="`python3 tools/wants.py seed` keeps it there with its own reason"))
    return out


def say(f: dict) -> str:
    """One finding as a line: where, what, why it is out, and what to do."""
    where = f"{f['file']}" + (f" line {f['line']}" if f.get("line") else "") + f", {f['setting']}"
    if f.get("about") in ("setting", "link"):
        return f"{where}: {f['does']}: {f['fix']}"
    though = ("though you would rather not work there" if f.get("about") == "soft"
              else "though you turned it down")
    return f"{where}: {f['entry']!r} {f['does']}, {though} ({f['why']}): {f['fix']}"


# ------------------------------------------------------------------ the one writer

def refusal(name: str) -> str:
    """Why an entry would never match an employer as the bar reads its list, or ""."""
    import sector
    import company_key as ck
    n = " ".join(str(name or "").split())
    if not n:
        return "say which employer"
    if re.search(r"[\\|*?\[\]^$]|\(\?", n):
        return (f"\"{n}\" is written as a pattern, and the list is read as employers' names: "
                "give the employer's name as it is written")
    # A name written two ways ("Acme Assurance / Acme Insurance") is one employer, as the
    # employer key reads it; a comma or a semicolon between two names is two.
    parts = [p for p in re.split(r"\s*[,;]\s*", n) if p.strip()]
    real = [p for p in parts if ck.key(p) and ck.strip_legal_forms("x " + p).strip() != "x"]
    if len(real) > 1:
        return f"\"{n}\" names more than one employer: turn each down on its own"
    if not ck.key(n) or ck.strip_legal_forms("x " + n).strip() == "x":
        return f"\"{n}\" has no employer's name in it"
    k = sector.kind_key(n)
    if k in NAMED_GROUPS:
        return (f"\"{n}\" is a group of employers, not one: turn each of them down by name")
    kinds = {sector.kind_key(v) for v in catalogue().values()} | GROUPS
    if k in kinds or sector.kind_key(n.lower().replace("all ", "", 1)) in kinds:
        return (f"\"{n}\" is a kind or group of employer, not one employer: turn the kind down "
                f"with `python3 tools/wants.py sector-out \"{n}\"`, or name each employer")
    return ""


def _why(said: str, day: str, by: str) -> str:
    said = " ".join(str(said or "").split())
    if by == "page":
        return f"turned down on the page, {day}: {said or 'no more roles from them'}"
    return f"turned down in a chat, {day}: \"{said}\"" if said else f"turned down in a chat, {day}"


def tidy(keys=None, kinds=None) -> dict:
    """Take what can be taken off the lists (each entry written plain), for the employers in
    `keys` and the kinds in `kinds`, or for everything out where both are None. Never an entry
    for an employer the person did not turn down. {"removed": [what came off, each with its
    text as written, which `put_back` restores], "by_hand": [the findings left]}."""
    import profile_set
    found = _turned_down()
    pick = [f for f in found if f["tidy"] and (
        (keys is None and kinds is None)
        or (f["key"] and f["key"] in set(keys or ()))
        or (f["kind"] and f["kind"] in set(kinds or ())))]
    removed = []
    by_setting: dict = {}
    for f in pick:
        by_setting.setdefault((f["file"][len("profile/"):], f["setting"]), set()).add(f["entry"])
    for (file, setting), entries in by_setting.items():
        if file == WANTS_FILE:
            removed += [{"file": file, "setting": setting, "entry": e, "src": e, "as": "record"}
                        for e in _drop_tier(entries, setting)]
            continue
        try:
            gone = profile_set.drop_entries(file, setting, lambda e, s=entries: e in s)
        except profile_set.Refused:
            continue
        removed += [{"file": file, "setting": setting, "entry": g["entry"], "src": g["src"],
                     "as": "dict" if setting == "BOARDS" else
                           "set" if file == "employers.py" else "list"} for g in gone]
    took = {(r["file"], r["setting"], r["entry"]) for r in removed}
    left = [f for f in found if (f["file"][len("profile/"):], f["setting"], f["entry"]) not in took]
    if keys is not None or kinds is not None:
        left = [f for f in left if (f["key"] and f["key"] in set(keys or ()))
                or (f["kind"] and f["kind"] in set(kinds or ()))]
    return {"removed": removed, "by_hand": left}


def put_back(records) -> list[dict]:
    """Restore what `tidy` took off, each where it was not put back already."""
    import profile_set
    done = []
    groups: dict = {}
    for r in records or ():
        if isinstance(r, dict) and r.get("file") and r.get("setting") and r.get("src"):
            groups.setdefault((r["file"], r["setting"], r.get("as") or "list"), []).append(r)
    for (file, setting, kind), rs in groups.items():
        if kind == "record":
            done += _add_tier([r for r in rs if isinstance(r.get("entry"), str)], setting)
            continue
        have = {v for v, _l, _ok in _entries(file, setting) if isinstance(v, (str, int))}
        add = [r for r in rs if r.get("entry") not in have]
        if add:
            try:
                profile_set.add_entries(file, setting, [r["src"] for r in add], kind)
            except profile_set.Refused:
                continue
            done += add
    return done


def _drop_tier(entries, setting: str) -> list[str]:
    """Take one tier's lift off each of these record entries; an entry left with no want and
    no lift goes. The entries it changed."""
    rec = load()
    done = []
    for e in sorted(entries):
        v = rec["employers"].get(e)
        if not v or setting not in (v.get("tiers") or ()):
            continue
        v = dict(v, tiers=[t for t in v.get("tiers") or () if t != setting])
        if not v["tiers"]:
            v.pop("tiers")
        if v.get("want") == "in" and not v.get("tiers"):
            rec["employers"].pop(e)
        else:
            rec["employers"][e] = v
        done.append(e)
    if done:
        _save(rec)
    return done


def _add_tier(rs, setting: str) -> list[dict]:
    """Put a tier's lift `tidy` took off back on each record entry; one gone whole comes back
    as an employer lifted by it."""
    rec = load()
    done = []
    for r in rs:
        e = r["entry"]
        v = dict(rec["employers"].get(e) or {"want": "in", "hard": False,
                                              "date": person.today().isoformat(),
                                              "by": "put back"})
        if setting in (v.get("tiers") or ()):
            continue
        v["tiers"] = sorted(set(v.get("tiers") or ()) | {setting})
        rec["employers"][e] = v
        done.append(r)
    if done:
        _save(rec)
    return done


def _note(mark: str, line: str) -> None:
    """The line, kept under Deal-breakers in profile/CLAUDE.md (the summary every chat reads),
    marked so it is found again; replaced where its mark is already there."""
    try:
        p = person.path(NOTES_FILE)
        with open(p, encoding="utf-8") as fh:
            text = fh.read()
    except (OSError, person.NoProfile):
        return
    full = f"{line} {mark}"
    lines = text.splitlines()
    for i, ln in enumerate(lines):
        if mark in ln:
            lines[i] = full
            break
    else:
        m = NOTES_HEADING.search(text)
        if m:
            at = text[:m.end()].count("\n") + 1
            j = at
            while j < len(lines) and not re.match(r"^#{1,6}\s", lines[j]):
                j += 1
            while j > at and not lines[j - 1].strip():
                j -= 1
            lines.insert(j, full)
        else:
            lines += ["", "### Deal-breakers", full]
    out = "\n".join(lines) + ("\n" if text.endswith("\n") or not text else "")
    with open(p, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(out)


def _unnote(mark: str) -> None:
    try:
        p = person.path(NOTES_FILE)
        with open(p, encoding="utf-8") as fh:
            text = fh.read()
    except (OSError, person.NoProfile):
        return
    kept = [ln for ln in text.splitlines(keepends=True) if mark not in ln]
    if len(kept) != len(text.splitlines(keepends=True)):
        with open(p, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("".join(kept))


def _old_setting(setting: str) -> dict:
    """search.py BAR_DECLINED or BAR_SECTORS_OUT as still written the old way, {} where not."""
    import profile_set
    try:
        got = profile_set.get("search.py", setting)
    except Exception:  # noqa: BLE001  no profile file: nothing written there
        return {}
    return got if isinstance(got, dict) and got is not profile_set.MISSING else {}


def decline(company: str, said: str = "", day: str | None = None, by: str = "chat",
            hard: bool = True) -> dict:
    """Turn one employer down by name, everywhere at once: kept in the record of what the
    person wants, with their words and the day. {"key", "added" (False where it was turned
    down already, however written), "hard", "removed", "by_hand"}. Refused for a form the bar
    would never match. With `hard` False (`--soft`, only ever on purpose) a job there is
    ranked down and never cut, and only the lists that lift it are changed."""
    import rules_view
    from company_key import entry_key
    from company_key import key as company_key
    name = " ".join(str(company or "").split())
    # A name the page passes is a posting's own employer, never a list or a pattern a chat
    # wrote ("Smith, Jones and Partners" is one firm): only a name with no employer in it is
    # refused there.
    why_not = refusal(name) if by != "page" else ("" if company_key(name) else
                                                  f"\"{name}\" has no employer's name in it")
    if why_not:
        raise Refused(why_not)
    day = day or person.today().isoformat()
    k = company_key(name)
    if hard:
        added = k not in declined_now()
    else:
        if k in {entry_key(e) for e in _old_setting("BAR_DECLINED")}:
            raise Refused(f"{name} is turned down in profile/search.py BAR_DECLINED, still "
                          "written the old way: `python3 tools/wants.py move` takes it into "
                          "your record first")
        added = k not in held_soft()["employers"]
    why = _why(said, day, by)
    if added:
        rec = load()
        same = [e for e, v in rec["employers"].items()
                if v.get("want") == "out" and entry_key(e) == k]
        _set_out(rec, "employers", same[0] if same else k, why,
                 " ".join(str(said or "").split()), day, by, name, hard)
        _save(rec)
    done = tidy(keys={k})
    if added:
        # A "no" said again harder or softer keeps what the first took off, so taking it back
        # puts everything back.
        before = (rules_view.set_record().get(f"rule~declined~{k}") or {}).get("tidied") or []
        rules_view.note_set(f"rule~declined~{k}", said or ("no more roles from them"
                                                          if by == "page" else ""),
                            day, name=name, tidied=[*before, *done["removed"]])
        if hard:
            _note(NOTE_MARK.format(k), f"- No roles at {name}: {why}.")
        else:
            _unnote(NOTE_MARK.format(k))      # ranked down is no deal-breaker
    return {"key": k, "added": added, "hard": bool(hard), **done}


def put_out(key: str, why: str) -> None:
    """An employer turned down again as it was (the page's undo of taking a rule off): kept in
    the record with what the bar said before, and taken off every list that lifts or searches
    it again."""
    why = str(why or "turned down on the page")
    said, day = _words(why)
    rec = load()
    _set_out(rec, "employers", str(key), why, said, day or person.today().isoformat(), "page")
    _save(rec)
    tidy(keys={str(key)})


def undecline(company: str, restore=None) -> dict:
    """Take an employer off the ones turned down, however its entry was written and wherever
    (the record, or BAR_DECLINED still written the old way), and put back what turning it down
    took off the lists (`restore`, else what was kept with the rule)."""
    import profile_set
    import rules_view
    from company_key import entry_key
    k = entry_key(company)
    taken = False
    rec = load()
    for e in [e for e, v in rec["employers"].items()
              if v.get("want") == "out" and entry_key(e) == k]:
        v = rec["employers"][e]
        if v.get("tiers"):
            rec["employers"][e] = {"want": "in", "hard": False, "tiers": v["tiers"],
                                   "said": "", "date": person.today().isoformat(),
                                   "by": "kept when taken back"}
        else:
            rec["employers"].pop(e)
        taken = True
    if taken:
        _save(rec)
    got = profile_set.get("search.py", "BAR_DECLINED")
    if isinstance(got, dict) and got is not profile_set.MISSING:
        kept = {e: w for e, w in got.items() if entry_key(e) != k}
        if len(kept) != len(got):
            profile_set.set_line("search.py", "BAR_DECLINED", kept)
            taken = True
    rid = f"rule~declined~{k}"
    rules = rules_view.set_record().get(rid) or {}
    back = put_back(rules.get("tidied") if restore is None else restore)
    if taken:
        rules_view.drop_set(rid)
    _unnote(NOTE_MARK.format(k))
    return {"key": k, "taken": taken, "restored": back}


def want(company: str, tier: str, said: str = "", day: str | None = None,
         by: str = "chat") -> dict:
    """An employer the person wants, lifted on every job there by its tier (`TIER_WORDS`: 1, 2,
    3 or backed), kept in the record with their words. {"key", "added", "tier"}. Refused for a
    form the bar would never match, a tier it does not know, and an employer turned down
    (taking a "no" back is `undecline`)."""
    from company_key import entry_key
    name = " ".join(str(company or "").split())
    why_not = refusal(name)
    if why_not:
        raise Refused(why_not)
    setting = TIER_WORDS.get(str(tier or "").strip().lower().replace("tier ", "").replace(
        "tier_", ""))
    if not setting:
        raise Refused(f"\"{tier}\" is not a tier: say 1, 2, 3 or backed")
    k = entry_key(name)
    if k in declined_now() or k in held_soft()["employers"]:
        raise Refused(f"{name} is turned down: take that back first with `python3 "
                      f"tools/wants.py undecline \"{name}\"`")
    entry = name.lower()
    rec = load()
    v = dict(rec["employers"].get(entry) or {})
    added = setting not in (v.get("tiers") or ())
    if added:
        rec["employers"][entry] = {**v, "want": "in", "hard": False,
                                   "tiers": sorted(set(v.get("tiers") or ()) | {setting}),
                                   "said": " ".join(str(said or "").split()),
                                   "date": day or person.today().isoformat(), "by": by}
        _save(rec)
    return {"key": entry, "added": added, "tier": setting}


def unwant(company: str) -> dict:
    """Take an employer off the ones the record lifts, however it was written there. {"key",
    "taken"}. A lift still written in employers.py is named by `show`, never changed here."""
    from company_key import entry_key
    k = entry_key(company)
    rec = load()
    gone = [e for e, v in rec["employers"].items()
            if v.get("want") == "in" and entry_key(e) == k]
    for e in gone:
        rec["employers"].pop(e)
    if gone:
        _save(rec)
    return {"key": k, "taken": bool(gone)}


def kind_refusal(kind: str) -> str:
    """Why a kind of employer would never match as one, or ""."""
    import sector
    from company_key import entry_key
    n = " ".join(str(kind or "").split())
    if not sector.kind_key(n):
        return "say which kind of employer"
    if sector.kind_key(n) in NAMED_GROUPS:
        return (f"\"{n}\" is a group of named employers, not a kind the bar can read: turn each "
                "of them down by name with `python3 tools/wants.py decline \"<employer>\"`")
    if re.search(r"[\\|*?\[\]^$]|\(\?", n):
        return f"\"{n}\" is written as a pattern: give the kind in words (\"pension funds\")"
    k = entry_key(n)
    names = {entry_key(e) for e in catalogue()}
    names |= {entry_key(v) for got in compiled()["tiers"].values() for v in got}
    if k and k in names:
        return (f"\"{n}\" is an employer, not a kind of employer: turn it down by name with "
                f"`python3 tools/wants.py decline \"{n}\"`")
    return ""


def sector_out(kind: str, said: str = "", day: str | None = None, by: str = "chat",
               hard: bool = True) -> dict:
    """Turn a kind of employer down: one rule on what the employer is, kept in the record of
    what the person wants, and every employer of that kind taken off what searches or lifts
    it. {"kind", "added", "hard", "covers": [employers the catalogue files under it], "kinds":
    [every kind it files], ...}. With `hard` False (`--soft`, only ever on purpose) a job at one
    is ranked down and never cut, and only the lists that lift one are changed."""
    import rules_view
    import sector
    why_not = kind_refusal(kind)
    if why_not:
        raise Refused(why_not)
    day = day or person.today().isoformat()
    k = sector.kind_key(kind)
    if hard:
        added = k not in sectors_out()
    else:
        if k in {sector.kind_key(x) for x in _old_setting("BAR_SECTORS_OUT")}:
            raise Refused(f"every {k} is turned down in profile/search.py BAR_SECTORS_OUT, "
                          "still written the old way: `python3 tools/wants.py move` takes it "
                          "into your record first")
        added = k not in held_soft()["kinds"]
    why = _why(said, day, by)
    if added:
        rec = load()
        same = [x for x in rec["kinds"] if sector.kind_key(x) == k]
        for x in same[1:]:
            rec["kinds"].pop(x)
        _set_out(rec, "kinds", same[0] if same else k, why, " ".join(str(said or "").split()),
                 day, by, hard=hard)
        _save(rec)
    done = tidy(kinds={k})
    cat = catalogue()
    covers = sorted(n for n, what in cat.items() if sector.kind_key(what) == k)
    if added:
        before = ((rules_view.set_record().get(f"rule~sector_out~{_slug(k)}") or {})
                  .get("tidied") or [])
        rules_view.note_set(f"rule~sector_out~{_slug(k)}", said, day, name=k,
                            tidied=[*before, *done["removed"]])
        if hard:
            _note(KIND_MARK.format(k), f"- No roles at any {k}: {why}.")
        else:
            _unnote(KIND_MARK.format(k))
    return {"kind": k, "added": added, "hard": bool(hard), "covers": covers,
            "kinds": sorted({sector.kind_key(v) for v in cat.values()} - {""}), **done}


def put_kind(kind: str, why: str) -> None:
    """A kind of employer turned down again as it was (the page's undo), kept in the record."""
    import sector
    k = sector.kind_key(kind)
    why = str(why or "turned down on the page")
    said, day = _words(why)
    rec = load()
    _set_out(rec, "kinds", k, why, said, day or person.today().isoformat(), "page")
    _save(rec)
    tidy(kinds={k})


def sector_back(kind: str, restore=None) -> dict:
    """Take a kind of employer off the ones turned down, in the record and in BAR_SECTORS_OUT
    still written the old way, and put back what turning it down took off the lists."""
    import profile_set
    import rules_view
    import sector
    k = sector.kind_key(kind)
    taken = False
    rec = load()
    gone = [x for x in rec["kinds"] if sector.kind_key(x) == k]
    for x in gone:
        rec["kinds"].pop(x)
    if gone:
        _save(rec)
        taken = True
    got = profile_set.get("search.py", "BAR_SECTORS_OUT")
    if isinstance(got, dict) and got is not profile_set.MISSING:
        kept = {x: w for x, w in got.items() if sector.kind_key(x) != k}
        if len(kept) != len(got):
            profile_set.set_line("search.py", "BAR_SECTORS_OUT", kept)
            taken = True
    rid = f"rule~sector_out~{_slug(k)}"
    rules = rules_view.set_record().get(rid) or {}
    back = put_back(rules.get("tidied") if restore is None else restore)
    if taken:
        rules_view.drop_set(rid)
    _unnote(KIND_MARK.format(k))
    return {"kind": k, "taken": taken, "restored": back}


# ------------------------------------------------------------------ wants that are one setting

# How a person or a chat names a single-setting want on the command line.
SETTING_WORDS = {"places": "places", "place": "places", "where": "places",
                 "remote": "remote", "pay-floor": "pay floor", "pay floor": "pay floor",
                 "floor": "pay floor", "pay-cut": "pay cut", "pay cut": "pay cut",
                 "cut": "pay cut"}


def setting_entry(want: str) -> dict:
    """What the record keeps for a single-setting want (SETTINGS), or {}."""
    return dict(load()["settings"].get(want) or {})


def keep_setting(want: str, value, said: str = "", day: str | None = None,
                 by: str = "chat") -> dict:
    """The record's entry for a single-setting want written, the setting itself left to the
    caller (`set_want`, or the page's Settings, tools/tweak.py, which writes it beside this).
    {"want", "before": the entry it replaced, or None}, which `put_setting` restores."""
    if want not in SETTINGS:
        raise Refused(f"\"{want}\" is not one of the wants kept as a setting: say places, "
                      "remote, pay-floor or pay-cut")
    key, hard, _what = SETTINGS[want]
    rec = load()
    before = rec["settings"].get(want)
    rec["settings"][want] = {"setting": f"search.py {key}",
                             "value": list(value) if isinstance(value, tuple) else value,
                             "hard": hard, "said": " ".join(str(said or "").split()),
                             "date": day or person.today().isoformat(), "by": by}
    _save(rec)
    return {"want": want, "before": before}


def put_setting(want: str, before) -> None:
    """The record's entry for a want put back as `keep_setting` found it (None: none)."""
    rec = load()
    if isinstance(before, dict):
        rec["settings"][want] = before
    else:
        rec["settings"].pop(want, None)
    _save(rec)


def _setting_writes(want: str, values, add, drop) -> list[tuple]:
    """The settings lines a want's change writes, each ("line", file, key, value): a place
    added or taken off the page's own way (tools/tweak.py, row J7), so the location filter
    keeps the town it searches; the floor never under the cut line (row J12)."""
    import tweak
    key = SETTINGS[want][0]
    now = setting_now(want)
    have = list(now) if isinstance(now, (list, tuple)) else []
    lines = (lambda ws: [w for w in ws if w[0] == "line"])  # noqa: E731  the record is ours
    try:
        if want == "places":
            if not (add or drop):
                raise Refused("add a place or take one off, one at a time (--add or --drop), "
                              "so the location filter keeps each place searched")
            writes, _then, _said = tweak._writes(
                {"p": "J7", "v": {"add": add} if add else {"drop": drop}}, {}, True)
            return lines(writes)
        if want == "remote":
            if add:
                return [] if add in have else [("line", "search.py", key, have + [add])]
            if drop:
                return [("line", "search.py", key, [x for x in have if x != drop])] \
                    if drop in have else []
            new = [" ".join(str(v).split()) for v in values or () if str(v).strip()]
            return [] if _same(now, new) else [("line", "search.py", key, new)]
        if add or drop or len(values or ()) != 1:
            raise Refused(f"say your {want} as one number")
        try:
            n = int(str(values[0]).replace(",", "").replace("_", ""))
        except ValueError:
            raise Refused(f"\"{values[0]}\" is not a number") from None
        if want == "pay floor":
            writes, _then, _said = tweak._writes({"p": "J12", "v": n}, {}, True)
            return [] if _same(now, n) else lines(writes)
        floor = _plain("search.py", "SALARY_FLOOR", 0) or 0
        if floor and n > floor:
            raise Refused(f"That is over your pay floor ({floor:,}): a cut line leaves out "
                          "what tops out under it, so it sits at or below the floor")
        return [] if _same(now, n) else [("line", "search.py", key, n)]
    except tweak.Refused as e:
        raise Refused(str(e)) from None


def set_want(what: str, values=(), add: str = "", drop: str = "", said: str = "",
             day: str | None = None, by: str = "chat") -> dict:
    """A single-setting want changed in one step: the setting written through the settings
    writer (profile_set), with what a place needs beside it, and the record kept with the
    person's words; every write taken back if one fails. {"want", "value", "changed"}."""
    import profile_set
    want = SETTING_WORDS.get(" ".join(str(what or "").lower().split()))
    if not want:
        raise Refused(f"\"{what}\" is not one of the wants kept as a setting: say places, "
                      "remote, pay-floor or pay-cut")
    if want == "places" and add and drop:
        raise Refused("add a place or take one off, one at a time")
    writes = _setting_writes(want, list(values or ()), " ".join(str(add or "").split()),
                             " ".join(str(drop or "").split()))
    now = setting_now(want)
    if not writes and not str(said or "").strip() and setting_entry(want) and \
            _same(setting_entry(want).get("value"), None if now is _NONE else now):
        return {"want": want, "value": setting_entry(want).get("value"), "changed": False}
    done = []
    try:
        for w in writes:
            done.append(profile_set.set_line(w[1], w[2], w[3]))
        now = setting_now(want)
        keep_setting(want, None if now is _NONE else now, said, day, by)
    except Exception as e:
        for r in reversed(done):
            profile_set.restore(r)
        if isinstance(e, profile_set.Refused):
            raise Refused(str(e)) from None
        raise
    return {"want": want, "value": setting_entry(want).get("value"), "changed": bool(writes)}


# ------------------------------------------------------------------ wants written as patterns

def _section_of(name: str) -> tuple[str, str]:
    """(section, the entry's name as kept) for a work-life sign or a kind of role, by its name
    or its words, or Refused."""
    n = " ".join(str(name or "").split()).lower()
    rec = load()
    for section in PATTERN_SETTINGS:
        for e, v in rec[section].items():
            if n in (e.lower(), " ".join(str(v.get("words") or "").split()).lower()):
                return section, e
    raise Refused(f"\"{name}\" is not in your record as a sign of work-life balance or a kind "
                  "of role: `python3 tools/wants.py show` lists them")


def words(name: str, plain: str, said: str = "", day: str | None = None,
          by: str = "chat") -> dict:
    """A work-life sign or a kind of role given the person's plain words (and their own, where
    said): the words a pattern weighs it by, which a seed from the pattern could not invent."""
    plain = " ".join(str(plain or "").split())
    if not plain:
        raise Refused("say what it is in plain words")
    section, e = _section_of(name)
    rec = load()
    rec[section][e] = dict(rec[section][e], words=plain,
                           said=" ".join(str(said or "").split()),
                           date=day or person.today().isoformat(), by=by)
    _save(rec)
    return {"section": section, "name": e, "words": plain}


def link(name: str, setting: str, match: str, day: str | None = None) -> dict:
    """A work-life sign or a kind of role linked to the pattern entry that carries it now (by
    the entry's reason, or its pattern where it gives none): its links to patterns gone are
    dropped, and an entry seeded for the same pattern with no words of the person's goes."""
    section, e = _section_of(name)
    match = " ".join(str(match or "").split())
    found = {(p["setting"], p["match"]) for p in patterns(section)}
    if (setting, match) not in found:
        raise Refused(f"no entry of profile/search.py {setting} reads \"{match}\": give its "
                      "reason as written, or its pattern where it has none")
    rec = load()
    for other, v in list(rec[section].items()):
        if other != e and (setting, match) in _links(v):
            keep = [x for x in v.get("patterns") or ()
                    if isinstance(x, dict) and (x.get("setting"), x.get("match")) !=
                    (setting, match)]
            if not keep and not v.get("said") and v.get("by") == "moved":
                rec[section].pop(other)
            else:
                rec[section][other] = dict(v, patterns=keep)
    v = rec[section][e]
    kept = [{"setting": s, "match": m} for s, m in _links(v) if (s, m) in found]
    if (setting, match) not in {(x["setting"], x["match"]) for x in kept}:
        kept.append({"setting": setting, "match": match})
    rec[section][e] = dict(v, patterns=kept, date=day or person.today().isoformat())
    _save(rec)
    return {"section": section, "name": e, "patterns": kept}


def forget(name: str) -> dict:
    """A work-life sign or a kind of role taken off the record. A pattern still carrying it is
    kept again by the next seed, with its own reason."""
    section, e = _section_of(name)
    rec = load()
    rec[section].pop(e)
    _save(rec)
    return {"section": section, "name": e}


# ------------------------------------------------------------------ what the record keeps by itself

def to_seed() -> dict:
    """{"settings": [wants], "signals": [names], "families": [names]}: each single setting set
    now, and each pattern a want is written as, that the record keeps nothing for yet."""
    rec = load()
    out = {"settings": [w for w in SETTINGS
                        if w not in rec["settings"] and setting_now(w) is not _NONE]}
    for section in PATTERN_SETTINGS:
        linked = {x for v in rec[section].values() for x in _links(v)}
        out[section] = list(dict.fromkeys(p["match"] for p in patterns(section)
                                          if p["record"]
                                          and (p["setting"], p["match"]) not in linked))
    return out


def seed(day: str | None = None) -> dict:
    """Keep in the record what it holds nothing for yet: each single setting as it is now, and
    each work-life sign and kind of role a pattern weighs, with the entry's own reason as its
    words, or none where it has no reason (`show` asks for a chat's), never guessed. "moved"
    is who wrote each; no setting is changed. Safe to run again. {section: n kept}."""
    todo = to_seed()
    if not any(todo.values()):
        return {}
    day = day or person.today().isoformat()
    rec = load()
    got: dict = {}
    for want in todo["settings"]:
        key, hard, _what = SETTINGS[want]
        now = setting_now(want)
        rec["settings"][want] = {"setting": f"search.py {key}",
                                 "value": list(now) if isinstance(now, tuple) else now,
                                 "hard": hard, "said": "", "date": day, "by": "moved"}
        got["settings"] = got.get("settings", 0) + 1
    for section in PATTERN_SETTINGS:
        linked = {x for v in rec[section].values() for x in _links(v)}
        for p in patterns(section):
            link_ = (p["setting"], p["match"])
            if not p["record"] or link_ in linked:
                continue
            linked.add(link_)
            v = rec[section].get(p["match"])
            if v is None:
                rec[section][p["match"]] = {"words": p["why"], "hard": False, "said": "",
                                            "date": day, "by": "moved",
                                            "patterns": [{"setting": p["setting"],
                                                          "match": p["match"]}]}
            else:                        # the same reason in another setting: one want
                rec[section][p["match"]] = dict(v, patterns=list(v.get("patterns") or ())
                                            + [{"setting": p["setting"], "match": p["match"]}])
            got[section] = got.get(section, 0) + 1
    _save(rec)
    return got


# ------------------------------------------------------------------ the old settings, moved in

def to_move() -> dict:
    """{setting: [entries]} for every plain entry still written the old way that belongs in the
    record: BAR_DECLINED and BAR_SECTORS_OUT in search.py, and the tier sets in employers.py.
    One written as code is left where it is (it is read with the record all the same)."""
    import profile_set
    out: dict = {}
    for setting in ("BAR_DECLINED", "BAR_SECTORS_OUT"):
        got = profile_set.get("search.py", setting)
        if isinstance(got, dict) and got is not profile_set.MISSING and got:
            out[setting] = list(got)
    if person.exists("employers.py"):
        for setting, _p in TIERS:
            got = _entries("employers.py", setting)
            if got and all(ok for _v, _l, ok in got):
                out[setting] = [v for v, _l, _ok in got]
    return out


def _effect() -> tuple:
    """Everything the moved settings decide, compiled: the same before and after a move."""
    c = compiled()
    return (c["declined"], c["kinds"], {k: sorted(v) for k, v in c["tiers"].items()})


def move(day: str | None = None) -> dict:
    """Take every plain entry of BAR_DECLINED, BAR_SECTORS_OUT and the tier sets into the
    record, each with the words and the day it already carried, and off the settings, which
    stay, empty. What each decides is compiled before and after and must be the same, else
    every file is put back as it was. Safe to run again: a second run finds nothing to move.
    {"moved": {setting: n}, "same": True}, or Refused."""
    import profile_set
    import sector
    from company_key import entry_key
    todo = to_move()
    if not todo:
        return {"moved": {}, "same": True}
    day = day or person.today().isoformat()
    files = {n: person.path(n) for n in (WANTS_FILE, "search.py", "employers.py")
             if person.exists(n)}
    kept = {}
    for n, p in files.items():
        with open(p, encoding="utf-8") as fh:
            kept[n] = fh.read()
    before = _effect()
    rec = load()
    moved: dict = {}
    # An employer turned down: one record entry an employer, as the bar reads it, the first
    # entry of the setting deciding its reason, as keyed() read it.
    got = profile_set.get("search.py", "BAR_DECLINED") if "BAR_DECLINED" in todo else {}
    taken: set = set()
    for name, why in dict(got or {}).items():
        k = entry_key(name)
        if not k or k in taken:
            continue
        taken.add(k)
        same = [e for e, v in rec["employers"].items()
                if v.get("want") == "out" and entry_key(e) == k]
        there = same[0] if same else str(name)
        for e in same[1:]:                       # one entry an employer from now on
            v = rec["employers"].pop(e)
            if v.get("tiers"):
                rec["employers"][e] = {"want": "in", "hard": False, "tiers": v["tiers"],
                                       "said": "", "date": day, "by": "moved"}
        said, when = _words(why)
        _set_out(rec, "employers", there, str(why), said, when or day, "moved",
                 str(name) if str(name) != there else "")
        moved["BAR_DECLINED"] = moved.get("BAR_DECLINED", 0) + 1
    got = profile_set.get("search.py", "BAR_SECTORS_OUT") if "BAR_SECTORS_OUT" in todo else {}
    # A kind: the last entry of the setting decides, as the bar's reading of it did.
    last = {sector.kind_key(x): (x, w) for x, w in dict(got or {}).items() if sector.kind_key(x)}
    for k, (_x, why) in last.items():
        same = [e for e in rec["kinds"] if sector.kind_key(e) == k]
        there = same[0] if same else k
        for e in same[1:]:
            rec["kinds"].pop(e)
        said, when = _words(why)
        _set_out(rec, "kinds", there, str(why), said, when or day, "moved")
        moved["BAR_SECTORS_OUT"] = moved.get("BAR_SECTORS_OUT", 0) + 1
    notes = _entry_notes(kept.get("employers.py", ""))
    for setting, _p in TIERS:
        for name in todo.get(setting, ()):
            if not isinstance(name, str):
                continue
            v = dict(rec["employers"].get(name) or {"want": "in", "hard": False,
                                                    "said": notes.get(name, ""),
                                                    "date": day, "by": "moved"})
            v["tiers"] = sorted(set(v.get("tiers") or ()) | {setting})
            rec["employers"][name] = v
            moved[setting] = moved.get(setting, 0) + 1
    _save(rec)
    try:
        for setting in todo:
            profile_set.drop_entries("employers.py" if setting.startswith(("TIER", "YC"))
                                     else "search.py", setting, lambda e: True)
        same = _effect() == before
    except Exception:  # noqa: BLE001  any failure: every file put back as it was
        same = False
    if not same:
        for n, p in files.items():
            with open(p, "w", encoding="utf-8", newline="") as fh:
                fh.write(kept[n])
        if WANTS_FILE not in files:
            try:
                os.remove(_wants_path())
            except OSError:
                pass
        _wants_cache.clear()
        person.reset()
        raise Refused("moving your settings into profile/wants.json would have changed what "
                      "they decide, so nothing was moved: every file is as it was")
    return {"moved": moved, "same": True}


def _entry_notes(text: str) -> dict:
    """{entry: its note} for each entry of a list written one a line with a note after it
    (`"acme",  # a grocer`): the note goes into the record with it, never lost."""
    out = {}
    for m in re.finditer(r'^\s*"([^"\n]+)"\s*,?\s*#\s*(.+?)\s*$', text or "", re.M):
        out.setdefault(m.group(1), m.group(2))
    return out


def show() -> list[str]:
    """The record, a line a want, in plain words: what is out, what is only ranked down, what
    is lifted, the single settings, the work-life signs and kinds of role (each needing a
    chat's words said so), and anything still written the old way or as a pattern."""
    try:
        from opportunity import SOFT_NO
        down = f"ranked down {SOFT_NO:+d}"
    except Exception:  # noqa: BLE001  a profile the scorer cannot read: said without the points
        down = "ranked down"
    rec = load()
    lines = []

    def no(name, v):
        said = f"{v.get('said') or v.get('why') or ''} ({v.get('date') or 'no date'})"
        if _hard(v):
            return f"no {name}: {said}"
        return f"rather not {name}, {down} and never left out: {said}"
    for k, v in sorted(rec["kinds"].items()):
        lines.append(no(k, v))
    for e, v in sorted(rec["employers"].items()):
        if v.get("want") == "out":
            lines.append(no(v.get("name") or e, v))
    for e, v in sorted(rec["employers"].items()):
        for t in v.get("tiers") or ():
            lines.append(f"wanted, +{POINTS.get(t, 0)}: {e}"
                         + (f": {v['said']}" if v.get("said") else "")
                         + f" ({v.get('date') or 'no date'})")
    for want, v in sorted(rec["settings"].items()):
        if want in SETTINGS:
            lines.append(f"{SETTINGS[want][2]}: {_shown(v.get('value'))}, "
                         + ("leaves jobs out" if _hard(v) else "only ranks, never leaves out")
                         + f" ({_who(v)})")
    for section in PATTERN_SETTINGS:
        points = {(p["setting"], p["match"]): p["points"] for p in patterns(section)}
        for name, v in sorted(rec[section].items()):
            pts = [points[x] for x in _links(v) if x in points]
            weighs = ", ".join(f"{p:+d}" for p in pts) or "no pattern"
            if v.get("words"):
                lines.append(f"{SECTION_WORD[section]} ({weighs}): {v['words']} ({_who(v)})")
            else:
                where = ", ".join(f"{s_} `{m}`" for s_, m in _links(v)) or name
                lines.append(f"needs your words: a {SECTION_WORD[section]} ({weighs}) written "
                             f"only as {where}: a chat asks what it is for and keeps it with "
                             f"`python3 tools/wants.py words \"{name}\" \"<their words>\"`")
    for why in excluded_patterns():
        lines.append("still written as a pattern (profile/search.py BAR_EXCLUDED), not yet as a "
                     f"kind of employer, which needs a chat: {why}")
    left = to_move()
    if left:
        lines.append("still written the old way, read all the same (`python3 tools/wants.py "
                     "move` takes them in): " + ", ".join(f"{s} {len(v)}"
                                                         for s, v in sorted(left.items())))
    todo = to_seed()
    if any(todo.values()):
        lines.append("not kept in your record yet (`python3 tools/wants.py seed` keeps them): "
                     + ", ".join(f"{k} {len(v)}" for k, v in sorted(todo.items()) if v))
    return lines


def excluded_patterns() -> list[str]:
    """The reason of each sector rule still written as a pattern (search.py BAR_EXCLUDED, those
    not set aside in BAR_EXCLUDED_OFF): which kind of employer each means needs a chat."""
    off = {str(x) for x in _plain("search.py", "BAR_EXCLUDED_OFF", []) or []}
    return [str(r[1]) for r in _plain("search.py", "BAR_EXCLUDED", []) or []
            if isinstance(r, (list, tuple)) and len(r) > 1 and str(r[1]) not in off]


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text or "").lower()).strip("-")[:40] or "x"


# ------------------------------------------------------------------ what a round searches with

def snapshot(window: int) -> dict:
    """The settings a round searches with, as they stand: what the next round compares."""
    return {"window": int(window),
            "places": [str(x) for x in _plain("search.py", "SCRAPE_LOCATIONS", []) or []],
            "remote": [str(x) for x in _plain("search.py", "SCRAPE_REMOTE_LOCATIONS", []) or []],
            "kinds_out": sorted(sectors_out()),
            "excluded": excluded_patterns(),
            "employers_out": sorted(declined_now())}


def _record_path(at: str = "") -> str:
    """The record of what rounds searched with: beside the round's summaries (`at`, its
    `--summary-dir`), else the person's own documents/rounds/searched/with.json. Kept in the
    person's own folder whatever a round's summaries said, a test's round in a folder of its
    own left a file in the person's copy (the 4.17.0 rehearsal)."""
    return os.path.join(at, *RECORD[2:]) if at else person.state(*RECORD)


def last_record(at: str = "") -> tuple[str, dict]:
    """(the round's name, what it searched with) for the last round recorded, or ("", {})."""
    try:
        with open(_record_path(at), encoding="utf-8") as fh:
            got = json.load(fh)
    except (OSError, ValueError):
        return "", {}
    if not isinstance(got, dict):
        return "", {}
    rows = [(str(r.get("date") or ""), n, r) for n, r in got.items() if isinstance(r, dict)]
    if not rows:
        return "", {}
    _d, name, r = max(rows)
    return name, r


def record(name: str, snap: dict, day: str, at: str = "") -> None:
    """Keep what this round searched with, the last RECORD_KEEP rounds (`at`: _record_path)."""
    p = _record_path(at)
    try:
        with open(p, encoding="utf-8") as fh:
            got = json.load(fh)
        got = got if isinstance(got, dict) else {}
    except (OSError, ValueError):
        got = {}
    got[name] = {"date": day, "with": snap}
    keep = sorted(got, key=lambda n: (str(got[n].get("date") or ""), n))[-RECORD_KEEP:]
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump({n: got[n] for n in sorted(keep)}, fh, indent=1, ensure_ascii=False,
                  sort_keys=True)
        fh.write("\n")
    os.replace(tmp, p)


def _listed(names, most: int = 6) -> str:
    names = [str(n) for n in names]
    if len(names) > most:
        return ", ".join(names[:most]) + f" and {len(names) - most} more"
    return ", ".join(names[:-1]) + " and " + names[-1] if len(names) > 1 else "".join(names)


def changed(before: dict, now: dict) -> list[str]:
    """What changed between two snapshots, in plain words."""
    out = []
    if before.get("window") != now.get("window") and before.get("window"):
        out.append(f"window {before['window']} to {now['window']} days")
    for field, word in (("places", "places"), ("remote", "remote places"),
                        ("kinds_out", "kinds of employer out"), ("excluded", "rules out"),
                        ("employers_out", "employers out")):
        a, b = set(before.get(field) or ()), set(now.get(field) or ())
        if a == b:
            continue
        bits = []
        if b - a:
            bits.append("added " + _listed(sorted(b - a)))
        if a - b:
            bits.append("taken off " + _listed(sorted(a - b)))
        out.append(f"{word}: " + "; ".join(bits))
    return out


def _own_steps() -> list[str]:
    """The person's own steps every brief runs, each with what its file says it does."""
    try:
        import brief
        steps = brief.own_steps()
    except Exception:  # noqa: BLE001  no brief settings: no steps of their own
        return []
    out = []
    for rel in steps:
        doc = ""
        try:
            with open(os.path.join(person.directory(), rel[len("profile/"):]),
                      encoding="utf-8") as fh:
                doc = (ast.get_docstring(ast.parse(fh.read())) or "").strip().split("\n")[0]
        except (OSError, SyntaxError):
            pass
        out.append(f"{rel}" + (f": \"{doc}\"" if doc else ""))
    return out


def header(window_line: str, window: int, name: str = "", today: str = "",
           keep: bool = True, skipped: dict | None = None, at: str = "") -> list[str]:
    """The lines a round prints before it searches: its window (whose), its places, the kinds
    of employer out, how many employers are out by name, the person's own steps that also
    clear the list, what changed since the last round, and anything turned down still on a
    list that searches or lifts it (skipped this round). With `keep`, what it searched with is
    recorded for the next round."""
    snap = snapshot(window)
    lines = ["searching with:", f"  {window_line}"]
    places = [p.split(",")[0].strip() for p in snap["places"]]
    where = _listed(places) if places else "no places set"
    if snap["remote"]:
        where += "; remote: " + _listed(snap["remote"])
    lines.append(f"  places: {where}")
    kinds = snap["kinds_out"] + snap["excluded"]
    lines.append("  kinds of employer out: " + (_listed(kinds) if kinds else "none"))
    lines.append(f"  employers turned down by name: {len(snap['employers_out'])}")
    for step in _own_steps():
        lines.append(f"  also before each brief, your own step {step} (its own setting, "
                     "left as it is)")
    was, before = last_record(at)
    if before.get("with"):
        moved = changed(before["with"], snap)
        lines.append(f"  since the last search ({was}, {before.get('date') or 'no date'}): "
                     + ("; ".join(moved) if moved else "nothing changed"))
    else:
        lines.append("  since the last search: no record of one yet")
    skipped = skipped or {}
    if skipped.get("by_name") or skipped.get("boards"):
        bits = []
        if skipped.get("by_name"):
            bits.append("searches by name for " + _listed(skipped["by_name"]))
        if skipped.get("boards"):
            bits.append("the job sites of " + _listed(skipped["boards"]))
        lines.append("  turned down, so not asked for this round: " + "; ".join(bits))
    found = drift()
    out = [f for f in found if f["about"] == "out"]
    if out:
        lines.append(f"  {len(out)} setting(s) still name what you turned down "
                     "(`python3 tools/wants.py check` names each; `tidy` fixes the plain ones)")
    if len(found) > len(out):
        lines.append(f"  {len(found) - len(out)} line(s) where your settings and your record of "
                     "what you want differ (`python3 tools/wants.py check` names each)")
    if keep and name:
        try:
            record(name, snap, today or person.today().isoformat(), at)
        except OSError:
            pass
    return lines


def skipped_now() -> dict:
    """{"by_name": [...], "boards": [...]}: the employers a round passes over because they are
    turned down, by name or by kind, as the settings stand now."""
    out = out_fn()
    if not out.declined and not out.kinds:
        return {"by_name": [], "boards": []}
    names = [e for e in _plain("search.py", "SCRAPE_EMPLOYERS", []) or [] if out(e)]
    boards = []
    if person.exists("boards.py"):
        boards = [e for e in dict(_plain("boards.py", "BOARDS", {}) or {}) if out(e)]
    return {"by_name": [str(e) for e in names], "boards": [str(e) for e in boards]}


# ------------------------------------------------------------------ the command

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd")
    for c in ("decline", "sector-out"):
        p = sub.add_parser(c)
        p.add_argument("what")
        p.add_argument("--said", default="", help="the person's own words, kept with the rule")
        p.add_argument("--by", default="chat", choices=("chat", "page"))
        p.add_argument("--today", default=None)
        p.add_argument("--soft", action="store_true",
                       help="only rank a job there down, never leave it out: only where the "
                            "person said so")
    for c in ("undecline", "sector-back", "unwant", "forget"):
        sub.add_parser(c).add_argument("what")
    p = sub.add_parser("set")
    p.add_argument("what", help="places, remote, pay-floor or pay-cut")
    p.add_argument("values", nargs="*", help="the places searched for remote work, or a number")
    p.add_argument("--add", default="", help="a place to search, as the job sites write it")
    p.add_argument("--drop", default="", help="a place to stop searching")
    p.add_argument("--said", default="", help="the person's own words, kept with the want")
    p.add_argument("--today", default=None)
    p = sub.add_parser("words")
    p.add_argument("what", help="the sign or kind of role, as `show` names it")
    p.add_argument("plain", help="what it is, in plain words")
    p.add_argument("--said", default="", help="the person's own words, kept with it")
    p.add_argument("--today", default=None)
    p = sub.add_parser("link")
    p.add_argument("what", help="the sign or kind of role, as `show` names it")
    p.add_argument("setting", help="OPP_LEVERAGE, OPP_TITLE_FAMILY, OPP_WRONG_FAMILY or "
                                   "FIT_WRONG_FAMILY")
    p.add_argument("match", help="the entry's reason as written, or its pattern")
    sub.add_parser("seed")
    p = sub.add_parser("want")
    p.add_argument("what")
    p.add_argument("--tier", required=True, help="1 (+30), 2 (+20), 3 (+10) or backed (+14)")
    p.add_argument("--said", default="", help="the person's own words, kept with the want")
    p.add_argument("--today", default=None)
    sub.add_parser("check")
    sub.add_parser("tidy")
    sub.add_parser("show")
    sub.add_parser("move")
    p = sub.add_parser("header")
    p.add_argument("--window", type=int, default=None)
    a = ap.parse_args(argv)
    if not person.exists():
        print("wants: there is no profile here yet, so nothing is turned down")
        return 0
    try:
        if a.cmd == "decline":
            got = decline(a.what, a.said, a.today, a.by, hard=not a.soft)
            print(f"{a.what}: " + (("turned down from now on" if got["hard"] else
                                    "ranked down from now on, never left out")
                                   if got["added"] else "already turned down"))
        elif a.cmd == "sector-out":
            got = sector_out(a.what, a.said, a.today, a.by, hard=not a.soft)
            print(f"every {got['kind']}: " + (("turned down from now on" if got["hard"] else
                                               "ranked down from now on, never left out")
                                              if got["added"] else "already turned down"))
            if got["covers"]:
                print(f"  your lists file {len(got['covers'])} employers as one: "
                      + _listed(got["covers"], 10))
            else:
                print(f"  none of your employers is filed as a {got['kind']} yet, so only a "
                      "posting saying it is one is left out; the kinds your list files are: "
                      + (_listed(got["kinds"], 20) or "none"))
        elif a.cmd == "undecline":
            got = undecline(a.what)
            print(f"{a.what}: " + ("shown again from now on" if got["taken"]
                                   else "was not turned down"))
        elif a.cmd == "sector-back":
            got = sector_back(a.what)
            print(f"{got['kind']}: " + ("shown again from now on" if got["taken"]
                                        else "was not turned down"))
        elif a.cmd == "want":
            got = want(a.what, a.tier, a.said, a.today)
            print(f"{a.what}: " + (f"lifted +{POINTS[got['tier']]} on every job there from now on"
                                   if got["added"] else "already lifted by that tier"))
            return 0
        elif a.cmd == "unwant":
            got = unwant(a.what)
            print(f"{a.what}: " + ("no longer lifted from now on" if got["taken"]
                                   else "was not lifted by your record"))
            return 0
        elif a.cmd == "set":
            got = set_want(a.what, a.values, a.add, a.drop, a.said, a.today)
            print(f"{SETTINGS[got['want']][2]}: {_shown(got['value'])}"
                  + (" from now on" if got["changed"] else ", as it was")
                  + (", kept with your words" if a.said else ""))
            return 0
        elif a.cmd == "words":
            got = words(a.what, a.plain, a.said, a.today)
            print(f"{got['name']}: kept as \"{got['words']}\"")
            return 0
        elif a.cmd == "link":
            got = link(a.what, a.setting, a.match)
            print(f"{got['name']}: carried by " + ", ".join(
                f"{x['setting']} \"{x['match']}\"" for x in got["patterns"]))
            return 0
        elif a.cmd == "forget":
            got = forget(a.what)
            print(f"{got['name']}: taken off your record")
            return 0
        elif a.cmd == "seed":
            got = seed()
            if not got:
                print("wants: your record keeps every setting and pattern already")
            for section, n in sorted(got.items()):
                print(f"kept {n} of your {section} in profile/{WANTS_FILE}, each as it is now")
            return 0
        elif a.cmd == "show":
            lines = show()
            print("\n".join(lines) if lines else "wants: your record holds nothing yet")
            return 0
        elif a.cmd == "move":
            got = move()
            if not got["moved"]:
                print("wants: nothing is left to move; your record holds every one")
            for setting, n in sorted(got["moved"].items()):
                print(f"moved {n} from {setting} into profile/{WANTS_FILE}, each as it was")
            return 0
        elif a.cmd == "tidy":
            got = tidy()
            for r in got["removed"]:
                print(f"took {r['entry']!r} off profile/{r['file']} {r['setting']}")
            for f in got["by_hand"]:
                print(say(f))
            if not got["removed"] and not got["by_hand"]:
                print("wants: nothing you turned down is still searched or lifted")
            return 0
        elif a.cmd == "check":
            found = drift()
            for f in found:
                print(say(f))
            out = [f for f in found if f["about"] == "out"]
            if out:
                print(f"wants: {len(out)} setting(s) still search or lift what you turned "
                      "down; a round skips their searches and job sites meanwhile")
                return 1
            print("wants: nothing you turned down is still searched or lifted"
                  + (f"; {len(found)} line(s) above for a chat to put right" if found else ""))
            return 0
        elif a.cmd == "header":
            import run_round
            own = run_round._job_age_days()
            w = a.window or own
            print("\n".join(header(run_round.window_line(w, own, a.window), w, keep=False,
                                   skipped=skipped_now())))
            return 0
        else:
            ap.print_help()
            return 2
    except Refused as e:
        print(f"wants: {e}")
        return 2
    for key in ("removed",):
        for r in got.get(key) or ():
            print(f"  took {r['entry']!r} off profile/{r['file']} {r['setting']}")
    for r in got.get("restored") or ():
        print(f"  put {r['entry']!r} back on profile/{r['file']} {r['setting']}")
    for f in got.get("by_hand") or ():
        print("  " + say(f))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
