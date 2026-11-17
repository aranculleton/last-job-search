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
                "date": "...", "by": "chat"}}}

An employer or a kind out is a cut by the bar (hard); an employer in is lifted by its tier
(soft: TIER_1 +30, TIER_2 +20, YC_AND_BACKED +14, TIER_3 +10). Every "no" the writers keep is
hard and every "yes" soft: a no that only ranks down, or a yes that cuts everything else, is
not one the search reads yet. This file compiles the record: the bar's employers and kinds
out (bar.DECLINED, bar.SECTORS_OUT, run_round.declined_now, `sectors_out`) and the tier sets
(opportunity.TIER_1 and the rest) are read from it, together with anything still written in
the old settings, and what is searched by name and whose job sites are read are checked
against it (`drift`). `move` takes the old settings into it, each entry's effect unchanged (the
profile upgrade wants-moved runs it by itself). A sector pattern (BAR_EXCLUDED) stays where it
is: which kind it means needs a chat.

    python3 tools/wants.py decline "<employer>" --said "<their words>"
    python3 tools/wants.py undecline "<employer>"
    python3 tools/wants.py sector-out "<kind of employer>" --said "<their words>"
    python3 tools/wants.py sector-back "<kind of employer>"
    python3 tools/wants.py want "<employer>" --tier 1|2|3|backed --said "<their words>"
    python3 tools/wants.py unwant "<employer>"
    python3 tools/wants.py show      what the record holds, in plain words
    python3 tools/wants.py move      the old settings taken into the record, effect unchanged
    python3 tools/wants.py check     exit 1 while anything turned down is still searched or lifted
    python3 tools/wants.py tidy      takes every employer turned down off what searches or lifts it
    python3 tools/wants.py header    what a search searches with, as a round prints it first

`decline` turns the employer down by name (in the record, keyed as the bar reads it), takes it
off every list that lifts or searches it (the tier sets, SCRAPE_EMPLOYERS, SCRAPE_QUERIES,
boards.py), keeps the person's words and the day, and notes it under Deal-breakers in
profile/CLAUDE.md. It refuses a form the bar would never match (a pattern, a kind of employer,
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
_wants_cache: dict = {}


def _wants_path() -> str:
    return person.path(WANTS_FILE)


def load() -> dict:
    """The record as stored ({"employers": {...}, "kinds": {...}}), each part {} where there is
    none. Read again whenever the file changes, by its time and its size (MAINTAINING.md, a
    cache is keyed on what it reads). A file that cannot be read is said once, on stderr, and
    read as empty: every setting still written the old way goes on working meanwhile."""
    try:
        p = _wants_path()
        st = os.stat(p)
    except (OSError, person.NoProfile):
        return {"employers": {}, "kinds": {}}
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
    return {"employers": {str(k): v for k, v in dict(got.get("employers") or {}).items()
                          if isinstance(v, dict)},
            "kinds": {str(k): v for k, v in dict(got.get("kinds") or {}).items()
                      if isinstance(v, dict)}}


def _save(rec: dict) -> None:
    """Write the record whole, sorted, as merge_state merges it (profile/wants.json)."""
    p = _wants_path()
    out = {"employers": dict(sorted(rec.get("employers", {}).items())),
           "kinds": dict(sorted(rec.get("kinds", {}).items()))}
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, indent=2, ensure_ascii=False, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, p)
    _wants_cache.clear()


def held_declined() -> dict:
    """{employer key: what the bar says} for every employer the record turns down, read
    through the employer key as the bar reads its list (company_key.keyed)."""
    from company_key import keyed
    return keyed({k: str(v.get("why") or v.get("said") or "turned down")
                  for k, v in load()["employers"].items() if v.get("want") == "out"})


def held_kinds() -> dict:
    """{kind, as sector.kind_key: what the bar says} for every kind the record turns down."""
    import sector
    return {sector.kind_key(k): str(v.get("why") or v.get("said") or "turned down")
            for k, v in load()["kinds"].items()
            if v.get("want") == "out" and sector.kind_key(k)}


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
             name: str = "") -> None:
    """One "out" written into the record, keeping a lift it already carries (a drifted lift
    stays until `tidy`, so its effect is unchanged until then)."""
    old = rec[section].get(entry) or {}
    rec[section][entry] = {**{k: v for k, v in old.items() if k in ("tiers", "name")},
                           "want": "out", "hard": True, "why": why, "said": said,
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


def _out_key(name, declined: dict, kinds: dict, cat: dict) -> tuple[str, str, str]:
    """(employer key, kind, why) for an employer out, or ("", "", "")."""
    import bar
    import sector
    from company_key import entry_key
    k = entry_key(name)
    if k and k in declined:
        return k, "", declined[k]
    if kinds:
        what = sector.kind_key(sector.kind(str(name or ""), cat))
        if what in kinds:
            return "", what, bar.kind_why(what, kinds[what])
    return "", "", ""


# ------------------------------------------------------------------ the check

def _finding(file, line, setting, entry, does, why, key="", kind="", plain=True, fix="") -> dict:
    return {"file": f"profile/{file}", "line": line, "setting": setting, "entry": entry,
            "does": does, "why": why, "key": key, "kind": kind, "tidy": bool(plain),
            "fix": fix or ("take it off: `python3 tools/wants.py tidy`" if plain
                           else "change that line by hand")}


def _names(pattern, text: str) -> bool:
    """Whether a lift's pattern names this employer whole, never a word inside it: a lift for
    consulting work that reads "Consulting" in a consultancy's name is about the work."""
    from company_key import entry_key
    m = pattern.search(text) if hasattr(pattern, "search") else None
    return bool(m) and entry_key(m.group(0)) == entry_key(text)


def drift() -> list[dict]:
    """Every place an employer or a kind of employer the person turned down is still searched,
    read from its own job site or lifted, each with the line to change."""
    from opportunity import _names_in, _scoped
    declined, kinds, cat = declined_now(), sectors_out(), catalogue()
    if not declined and not kinds:
        return []
    out: list[dict] = []

    def look(file, setting, does):
        for entry, line, plain in _entries(file, setting):
            if not isinstance(entry, str):
                continue
            k, kind, why = _out_key(entry, declined, kinds, cat)
            if why:
                out.append(_finding(file, line, setting, entry, does, why, k, kind, plain))

    look("search.py", "SCRAPE_EMPLOYERS", "is searched by name every round")
    for entry, line, plain in _entries("search.py", "SCRAPE_QUERIES"):
        c = " %s " % " ".join(str(entry or "").lower().split())
        hit = _names_in(c, set(declined)) if isinstance(entry, str) else None
        if hit:
            out.append(_finding("search.py", line, "SCRAPE_QUERIES", entry,
                                "is a search for it by name", declined[hit], hit, "", plain))
    if person.exists("boards.py"):
        look("boards.py", "BOARDS", "has its own job site read every round")
    if person.exists("employers.py"):
        for setting, pts in TIERS:
            look("employers.py", setting, f"is lifted +{pts} on every job there")
    # A lift the record itself still carries for an employer turned down (a merge of two
    # chats, or a lift it kept when it was moved): taken off the record by `tidy`.
    for entry, v in sorted(load()["employers"].items()):
        for setting in v.get("tiers") or ():
            if setting not in POINTS:
                continue
            k, kind, why = _out_key(entry, declined, kinds, cat)
            if why:
                out.append(_finding(WANTS_FILE, None, setting, entry,
                                    f"is lifted +{POINTS[setting]} on every job there", why,
                                    k, kind, True))
    # A lift written as a pattern: one naming the employer whole, or, for a kind turned down,
    # one reading what the employer is (scope "employer") that names the kind.
    lev = _plain("search.py", "OPP_LEVERAGE", []) or []
    lines = [ln for _v, ln, _ok in _entries("search.py", "OPP_LEVERAGE")]
    written = dict(_plain("search.py", "BAR_DECLINED", {}) or {})
    from company_key import entry_key
    names = {}
    for e in written:
        names.setdefault(entry_key(e), []).append(str(e))
    for k in declined:
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
            if k in declined and any(_names(pat, s) for s in said):
                out.append(_finding("search.py", line, "OPP_LEVERAGE", str(reason),
                                    f"lifts {said[0]} +{pts} by name", declined[k], k, "",
                                    False, "take its name out of that pattern by hand"))
        for kind, why in kinds.items():
            if scope == "employer" and pat.search(kind):
                out.append(_finding("search.py", line, "OPP_LEVERAGE", str(reason),
                                    f"lifts every {kind} +{pts}", why, "", kind, False,
                                    "take that kind out of the pattern by hand"))
    return out


def say(f: dict) -> str:
    """One finding as a line: where, what, why it is out, and what to do."""
    where = f"{f['file']}" + (f" line {f['line']}" if f.get("line") else "") + f", {f['setting']}"
    return f"{where}: {f['entry']!r} {f['does']}, though you turned it down ({f['why']}): {f['fix']}"


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
    found = drift()
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


def decline(company: str, said: str = "", day: str | None = None, by: str = "chat") -> dict:
    """Turn one employer down by name, everywhere at once: kept in the record of what the
    person wants, with their words and the day. {"key", "added" (False where it was turned
    down already, however written), "removed", "by_hand"}. Refused for a form the bar would
    never match."""
    import rules_view
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
    added = k not in declined_now()
    why = _why(said, day, by)
    if added:
        rec = load()
        _set_out(rec, "employers", k, why, " ".join(str(said or "").split()), day, by, name)
        _save(rec)
    done = tidy(keys={k})
    if added:
        rules_view.note_set(f"rule~declined~{k}", said or ("no more roles from them"
                                                          if by == "page" else ""),
                            day, name=name, tidied=done["removed"])
        _note(NOTE_MARK.format(k), f"- No roles at {name}: {why}.")
    return {"key": k, "added": added, **done}


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
    if k in declined_now():
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


def sector_out(kind: str, said: str = "", day: str | None = None, by: str = "chat") -> dict:
    """Turn a kind of employer down: one rule on what the employer is, kept in the record of
    what the person wants, and every employer of that kind taken off what searches or lifts
    it. {"kind", "added", "covers": [employers the catalogue files under it], "kinds": [every
    kind it files], ...}."""
    import rules_view
    import sector
    why_not = kind_refusal(kind)
    if why_not:
        raise Refused(why_not)
    day = day or person.today().isoformat()
    k = sector.kind_key(kind)
    added = k not in sectors_out()
    why = _why(said, day, by)
    if added:
        rec = load()
        _set_out(rec, "kinds", k, why, " ".join(str(said or "").split()), day, by)
        _save(rec)
    done = tidy(kinds={k})
    cat = catalogue()
    covers = sorted(n for n, what in cat.items() if sector.kind_key(what) == k)
    if added:
        rules_view.note_set(f"rule~sector_out~{_slug(k)}", said, day, name=k,
                            tidied=done["removed"])
        _note(KIND_MARK.format(k), f"- No roles at any {k}: {why}.")
    return {"kind": k, "added": added, "covers": covers,
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
    """The record, a line a want, in plain words: what is out, what is lifted, and anything
    still written the old way."""
    rec = load()
    lines = []
    for k, v in sorted(rec["kinds"].items()):
        lines.append(f"no {k}: {v.get('said') or v.get('why') or ''} ({v.get('date') or 'no date'})")
    for e, v in sorted(rec["employers"].items()):
        if v.get("want") == "out":
            lines.append(f"no {v.get('name') or e}: {v.get('said') or v.get('why') or ''} "
                         f"({v.get('date') or 'no date'})")
    for e, v in sorted(rec["employers"].items()):
        for t in v.get("tiers") or ():
            lines.append(f"wanted, +{POINTS.get(t, 0)}: {e}"
                         + (f": {v['said']}" if v.get("said") else "")
                         + f" ({v.get('date') or 'no date'})")
    left = to_move()
    if left:
        lines.append("still written the old way, read all the same (`python3 tools/wants.py "
                     "move` takes them in): " + ", ".join(f"{s} {len(v)}"
                                                         for s, v in sorted(left.items())))
    return lines


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text or "").lower()).strip("-")[:40] or "x"


# ------------------------------------------------------------------ what a round searches with

def snapshot(window: int) -> dict:
    """The settings a round searches with, as they stand: what the next round compares."""
    return {"window": int(window),
            "places": [str(x) for x in _plain("search.py", "SCRAPE_LOCATIONS", []) or []],
            "remote": [str(x) for x in _plain("search.py", "SCRAPE_REMOTE_LOCATIONS", []) or []],
            "kinds_out": sorted(sectors_out()),
            "excluded": [str(r[1]) for r in _plain("search.py", "BAR_EXCLUDED", []) or []
                         if isinstance(r, (list, tuple)) and len(r) > 1
                         and str(r[1]) not in set(_plain("search.py", "BAR_EXCLUDED_OFF", [])
                                                  or [])],
            "employers_out": sorted(declined_now())}


def _record_path() -> str:
    return person.state(*RECORD)


def last_record() -> tuple[str, dict]:
    """(the round's name, what it searched with) for the last round recorded, or ("", {})."""
    try:
        with open(_record_path(), encoding="utf-8") as fh:
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


def record(name: str, snap: dict, day: str) -> None:
    """Keep what this round searched with, the last RECORD_KEEP rounds."""
    p = _record_path()
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
           keep: bool = True, skipped: dict | None = None) -> list[str]:
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
    was, before = last_record()
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
    if found:
        lines.append(f"  {len(found)} setting(s) still name what you turned down "
                     "(`python3 tools/wants.py check` names each; `tidy` fixes the plain ones)")
    if keep and name:
        try:
            record(name, snap, today or person.today().isoformat())
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
    for c in ("undecline", "sector-back", "unwant"):
        sub.add_parser(c).add_argument("what")
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
            got = decline(a.what, a.said, a.today, a.by)
            print(f"{a.what}: " + ("turned down from now on" if got["added"]
                                   else "already turned down"))
        elif a.cmd == "sector-out":
            got = sector_out(a.what, a.said, a.today, a.by)
            print(f"every {got['kind']}: " + ("turned down from now on" if got["added"]
                                              else "already turned down"))
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
            if found:
                print(f"wants: {len(found)} setting(s) still search or lift what you turned "
                      "down; a round skips their searches and job sites meanwhile")
                return 1
            print("wants: nothing you turned down is still searched or lifted")
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
