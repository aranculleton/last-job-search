#!/usr/bin/env python3
"""Every name the tools read from a profile's Python modules, read off the code.

/setup writes a person's profile in the shape of profile.example/, but the
example sets only what it needs: most names have a neutral default in the tool
that reads them, and a new market often needs one the example leaves out. This
lists them all, so nobody has to grep for `getattr(_S, ...)`:

    python3 tools/profile_names.py             # every module, every name
    python3 tools/profile_names.py search      # one module
    python3 tools/profile_names.py --missing   # only names the example does not set

For each name: whether a tool needs it (read directly, no default) or only uses
it when present (read with getattr and a fallback), whether profile.example/
sets it, and every file and line that reads it. The line is where to look for
what it means and what shape it takes: read the code before writing the value.

person.json is listed the same way, as dotted keys ("documents.noun"): read
through `person.get("a.b")`, or through a section held in a variable
(`_DOC = person.get("documents")`, then `_DOC.get("noun")`). A key read with no
default is needed; one with a default is optional. `python3 tools/profile_names.py
person` lists only those.
"""

from __future__ import annotations

import os
import re
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLE = os.path.join(ROOT, "profile.example")
SCAN = ("tools", "templates")

_NAME = r"[A-Z_][A-Z0-9_]*"
_BIND = re.compile(r"(\w+)\s*=\s*_?person\.module\(\"(\w+)\"\)")
_GETATTR_ALIAS = re.compile(r"getattr\(\s*(\w+)\s*,\s*\"(" + _NAME + r")\"")
_GETATTR_INLINE = re.compile(r"getattr\(\s*_?person\.module\(\"(\w+)\"\)\s*,\s*\"(" + _NAME + r")\"")
_ATTR_INLINE = re.compile(r"_?person\.module\(\"(\w+)\"\)\.(" + _NAME + r")\b")
_ATTR_ALIAS = re.compile(r"\b(\w+)\.(" + _NAME + r")\b")
# A reader written as a wrapper, `def _NET_GET(name, default): return
# getattr(_NET, name, default)`, then called `_NET_GET("TITLE_SETS", None)`.
# Unseen, every networking name read that way was missing from this list, so no
# check could ever say a profile lacked one.
_GETTER_DEF = re.compile(r"def (\w+)\(\s*(\w+)\s*,\s*(\w+)\s*\)\s*(?:->[^:]+)?:\s*\n"
                         r"\s*return getattr\(\s*(\w+)\s*,\s*\2\s*,\s*\3\s*\)")


def _files():
    for top in SCAN:
        for dp, dns, fns in os.walk(os.path.join(ROOT, top)):
            dns[:] = [d for d in dns if d != "__pycache__"]
            for f in sorted(fns):
                if f.endswith(".py") and f != "profile_names.py":
                    yield os.path.join(dp, f)


def collect() -> dict:
    """{module: {name: {"required": bool, "where": [file:line, ...]}}}"""
    out: dict = defaultdict(lambda: defaultdict(lambda: {"required": False, "where": []}))
    for path in _files():
        rel = os.path.relpath(path, ROOT)
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
        alias = {a: m for line in lines for a, m in _BIND.findall(line)}
        getters = {fn: alias[a] for fn, _, _, a in _GETTER_DEF.findall("\n".join(lines))
                   if a in alias}
        getter_call = (re.compile(r"\b(" + "|".join(map(re.escape, getters)) + r")\(\s*\"("
                                  + _NAME + r")\"") if getters else None)
        for n, line in enumerate(lines, 1):
            if line.lstrip().startswith("#"):
                continue
            hits = []
            for mod, name in _GETATTR_INLINE.findall(line):
                hits.append((mod, name, False))
            for a, name in _GETATTR_ALIAS.findall(line):
                if a in alias:
                    hits.append((alias[a], name, False))
            if getter_call:
                for fn, name in getter_call.findall(line):
                    hits.append((getters[fn], name, False))
            soft = {(m, nm) for m, nm, _ in hits}
            for mod, name in _ATTR_INLINE.findall(line):
                if (mod, name) not in soft:
                    hits.append((mod, name, True))
            for a, name in _ATTR_ALIAS.findall(line):
                if a in alias and (alias[a], name) not in soft:
                    hits.append((alias[a], name, True))
            for mod, name, required in hits:
                entry = out[mod][name]
                entry["required"] = entry["required"] or required
                where = f"{rel}:{n}"
                if where not in entry["where"]:
                    entry["where"].append(where)
    return out


# person.json. A key is dotted from its section ("identity.email"). Only the
# sections person.json has count, because `person` is also a common name for a
# contact's dict in the networking tools ("person.get('title')").
_PGET = re.compile(r"\bperson\.get\(\s*\"([a-z_]+(?:\.[a-z_]+)*)\"\s*(,)?")
_OWN_GET = re.compile(r"(?<![\w.])get\(\s*\"([a-z_]+(?:\.[a-z_]+)*)\"\s*(,)?")
_SECTION_BIND = re.compile(r"(\w+)\s*=\s*person\.get\(\s*\"([a-z_]+)\"")
_ALIAS_GET = r"\b{a}\.get\(\s*\"([a-z_]+)\"\s*(,)?"
_ALIAS_ITEM = r"\b{a}\[\s*\"([a-z_]+)\"\s*\]"
SECTIONS = ("identity", "documents", "grounding")


def collect_person() -> dict:
    """{dotted key: {"required": bool, "where": [file:line, ...]}} for person.json.

    A key is needed where a file reads it with no default and does not also
    read it with one (`if _ID.get("linkedin"): ... _ID["linkedin"]` is a guard,
    not a requirement). Docstrings are skipped: a usage line in one is not a
    read.
    """
    out: dict = defaultdict(lambda: {"required": False, "where": []})
    for path in _files():
        rel = os.path.relpath(path, ROOT)
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
        own = os.path.basename(path) == "person.py"
        sections = {a: sec for line in lines for a, sec in _SECTION_BIND.findall(line)
                    if sec in SECTIONS}
        reads: dict = defaultdict(list)          # key -> [(hard, where)]
        in_doc = False
        for n, line in enumerate(lines, 1):
            quotes = line.count('"""')
            if in_doc or line.lstrip().startswith("#"):
                in_doc = in_doc != (quotes % 2 == 1)
                continue
            if quotes % 2 == 1:
                in_doc = True
                continue
            where = f"{rel}:{n}"
            for key, comma in _PGET.findall(line) + (_OWN_GET.findall(line) if own else []):
                reads[key].append((not comma, where))
            for a, sec in sections.items():
                for key, _comma in re.findall(_ALIAS_GET.format(a=re.escape(a)), line):
                    reads[f"{sec}.{key}"].append((False, where))
                for key in re.findall(_ALIAS_ITEM.format(a=re.escape(a)), line):
                    reads[f"{sec}.{key}"].append((True, where))
        for key, rs in reads.items():
            if key.split(".")[0] not in SECTIONS or key in SECTIONS:
                continue
            e = out[key]
            e["required"] = e["required"] or all(hard for hard, _ in rs)
            e["where"] += [w for _, w in rs if w not in e["where"]]
    return out


def example_person_keys() -> set:
    """Every dotted key profile.example/person.json sets."""
    import json
    with open(os.path.join(EXAMPLE, "person.json"), encoding="utf-8") as fh:
        data = json.load(fh)
    keys = set()

    def walk(node, prefix):
        for k, v in node.items():
            if k.startswith("_"):
                continue
            keys.add(prefix + k)
            if isinstance(v, dict):
                walk(v, prefix + k + ".")
    walk(data, "")
    return keys


def example_sets(module: str) -> set:
    path = os.path.join(EXAMPLE, module + ".py")
    if not os.path.isfile(path):
        return set()
    with open(path, encoding="utf-8") as fh:
        return set(re.findall(r"^(" + _NAME + r")\s*(?::[^=]+)?=", fh.read(), re.M))


def main(argv: list[str]) -> int:
    if argv[:1] in (["-h"], ["--help"]):
        print("usage: python3 tools/profile_names.py [<module> | person] [--missing]")
        return 0
    missing_only = "--missing" in argv
    wanted = [a for a in argv if not a.startswith("--")]
    names = collect()
    if not wanted or "person" in wanted:
        have = example_person_keys()
        rows = []
        keys = collect_person()
        for key in sorted(keys):
            e = keys[key]
            if missing_only and key in have:
                continue
            need = "needed" if e["required"] else "optional"
            ex = "example sets it" if key in have else "example does not"
            rows.append(f"  {key:36} {need:8}  {ex:16}  {', '.join(e['where'][:3])}"
                        + (" ..." if len(e["where"]) > 3 else ""))
        if rows:
            print("profile/person.json")
            print("\n".join(rows))
            print()
    for mod in sorted(names):
        if wanted and mod not in wanted:
            continue
        have = example_sets(mod)
        rows = []
        for name in sorted(names[mod]):
            e = names[mod][name]
            if missing_only and name in have:
                continue
            need = "needed" if e["required"] else "optional"
            ex = "example sets it" if name in have else "example does not"
            rows.append(f"  {name:28} {need:8}  {ex:16}  {', '.join(e['where'][:4])}"
                        + (" ..." if len(e["where"]) > 4 else ""))
        if rows:
            print(f"profile/{mod}.py")
            print("\n".join(rows))
            print()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
