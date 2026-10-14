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
person.json's keys are read with .get() and are documented in that file's
example instead.
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
        for n, line in enumerate(lines, 1):
            if line.lstrip().startswith("#"):
                continue
            hits = []
            for mod, name in _GETATTR_INLINE.findall(line):
                hits.append((mod, name, False))
            for a, name in _GETATTR_ALIAS.findall(line):
                if a in alias:
                    hits.append((alias[a], name, False))
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


def example_sets(module: str) -> set:
    path = os.path.join(EXAMPLE, module + ".py")
    if not os.path.isfile(path):
        return set()
    with open(path, encoding="utf-8") as fh:
        return set(re.findall(r"^(" + _NAME + r")\s*(?::[^=]+)?=", fh.read(), re.M))


def main(argv: list[str]) -> int:
    missing_only = "--missing" in argv
    wanted = [a for a in argv if not a.startswith("--")]
    names = collect()
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
