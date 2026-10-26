#!/usr/bin/env python3
"""The app's public names, so that none is taken away without saying so.

A person's own tests (profile/tests) may use any of the app's public names: a top-level
name in tools/ or templates/ that does not start with an underscore, outside
tools/openroles/ (CLAUDE.md, "App-owned files and personal files"). 3.5.0 moved the
board reading into tools/openroles and broke dozens of the maintainer's own tests, and the
work towards the release after 3.13.0 removed holidays.is_holiday and
score_eval.EXPECTATIONS with nothing in their place. Nothing stopped either.

    python3 tools/public_names.py snapshot   # write tools/public_names.json from this tree
    python3 tools/public_names.py check      # every name in it is still here, or listed as gone

The names are read with ast, never imported: every def, async def and class, and every
module-level assignment, annotated ones included, as {file: [names]}. Each release writes
the snapshot afresh (MAINTAINING.md, "Releasing"), so it holds the names people have.

A name may go only when docs/removed_names.json lists it with the date, the reason and
the CHANGELOG line that tells people, and that line is in CHANGELOG.md. A name still
imported under its old module has not gone, because a test using it still works. A new
name needs nothing. Only the tree is read, so this works in CI's shallow checkout, which
has no tags and no history. Exit 1 on a finding, 0 otherwise.
"""
from __future__ import annotations

import ast
import datetime as dt
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCAN = ("tools", "templates")
SNAPSHOT = "tools/public_names.json"
REMOVED = "docs/removed_names.json"
CHANGELOG = "CHANGELOG.md"
# Vendored from openroles and never edited here: its names are openroles' own.
SKIP = ("tools/openroles",)
NEEDS = ("date", "reason", "changelog")


def _files(root: str):
    """Every .py under tools/ and templates/, as a path from the root, but openroles and
    any test or cache folder."""
    for top in SCAN:
        start = os.path.join(root, top)
        for base, dirs, files in os.walk(start):
            rel = top + base[len(start):].replace(os.sep, "/")
            dirs[:] = sorted(d for d in dirs if f"{rel}/{d}" not in SKIP
                             and d not in ("tests", "test") and not d.startswith((".", "__"))
                             and not d.endswith("_cache"))
            for name in sorted(files):
                if name.endswith(".py"):
                    yield f"{rel}/{name}"


def _main_guard(node: ast.If) -> bool:
    sides = [node.test.left, *node.test.comparators] if isinstance(node.test, ast.Compare) else []
    return any(isinstance(s, ast.Name) and s.id == "__name__" for s in sides)


def _targets(target):
    if isinstance(target, ast.Name):
        yield target.id
    elif isinstance(target, (ast.Tuple, ast.List)):
        for each in target.elts:
            yield from _targets(each)
    elif isinstance(target, ast.Starred):
        yield from _targets(target.value)


def _bound(body: list, imports: bool):
    """Every name these module-level statements bind, and with `imports` the names an
    import brings in too. A block run at import (an if, a try, a with) binds at module
    level; the `if __name__ == "__main__":` block does not run when a test imports it."""
    for node in body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            yield node.name
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                yield from _targets(target)
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            yield from _targets(node.target)     # `x: int` alone binds nothing
        elif imports and isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                yield (alias.asname or alias.name).split(".")[0]
        elif isinstance(node, ast.If) and not _main_guard(node):
            yield from _bound(node.body + node.orelse, imports)
        elif isinstance(node, ast.Try):
            yield from _bound(node.body + node.orelse + node.finalbody
                              + [s for h in node.handlers for s in h.body], imports)
        elif isinstance(node, ast.With):
            yield from _bound(node.body, imports)


def _read(root: str, path: str) -> ast.Module:
    with open(os.path.join(root, path), encoding="utf-8") as fh:
        return ast.parse(fh.read(), filename=path)


def names(root: str = ROOT, imports: bool = False) -> dict[str, list[str]]:
    """{file: [public names]} for this tree, files with none left out. With `imports`,
    the names each file's imports bring in are counted as well."""
    out = {}
    for path in _files(root):
        got = sorted({n for n in _bound(_read(root, path).body, imports)
                      if not n.startswith("_") and n != "*"})
        if got:
            out[path] = got
    return out


def _load(root: str, path: str, empty):
    full = os.path.join(root, path)
    if not os.path.exists(full):
        return empty
    with open(full, encoding="utf-8") as fh:
        return json.load(fh)


def snapshot(root: str = ROOT, write: bool = True) -> dict[str, list[str]]:
    """This tree's public names, written to tools/public_names.json unless `write` is
    False."""
    got = names(root)
    if write:
        with open(os.path.join(root, SNAPSHOT), "w", encoding="utf-8") as fh:
            fh.write(json.dumps(got, indent=1, sort_keys=True) + "\n")
    return got


def stale(root: str = ROOT) -> bool:
    """True when the snapshot is not this tree's names exactly: what a release must not
    ship with, since the next release is checked against it."""
    return _load(root, SNAPSHOT, None) != names(root)


def _flat(text: str) -> str:
    return " ".join(text.split())


def _listing_problem(entry: dict, changelog: str) -> str:
    """Why a removal's entry in docs/removed_names.json does not yet tell people, or ""."""
    missing = [k for k in NEEDS if not str(entry.get(k) or "").strip()]
    if missing:
        return f"listed in {REMOVED} with no {' and no '.join(missing)}"
    try:
        dt.date.fromisoformat(str(entry["date"]))
    except ValueError:
        return f"listed in {REMOVED} with a date that is not YYYY-MM-DD ({entry['date']})"
    if _flat(str(entry["changelog"])) not in _flat(changelog):
        return f"listed in {REMOVED}, but its CHANGELOG line is not in {CHANGELOG}"
    return ""


def check(root: str = ROOT) -> list[str]:
    """One plain line per public name in the snapshot that this tree no longer has and
    docs/removed_names.json does not account for. Empty when nothing is wrong."""
    shot = _load(root, SNAPSHOT, None)
    if shot is None:
        return [f"There is no {SNAPSHOT} yet: `python3 tools/public_names.py snapshot` writes it."]
    now = names(root, imports=True)
    listed = {(e.get("module"), e.get("name")): e
              for e in _load(root, REMOVED, {}).get("removed", [])}
    full = os.path.join(root, CHANGELOG)
    changelog = open(full, encoding="utf-8").read() if os.path.exists(full) else ""
    out = []
    for path, wanted in sorted(shot.items()):
        here = set(now.get(path, ()))
        for name in wanted:
            if name in here:
                continue
            entry = listed.get((path, name))
            if entry is None:
                where = "" if os.path.exists(os.path.join(root, path)) else " (the file is gone)"
                out.append(f"{path}{where} no longer has {name}.")
            elif (why := _listing_problem(entry, changelog)):
                out.append(f"{path} no longer has {name}: {why}.")
    return out


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["snapshot"]:
        got = snapshot()
        print(f"public_names: wrote {sum(map(len, got.values()))} names from {len(got)} files "
              f"to {SNAPSHOT}")
        return 0
    if argv[:1] != ["check"]:
        print(__doc__.split("\n\n")[1])
        return 2
    try:
        found = check()
    except (OSError, SyntaxError, ValueError) as e:
        print(f"public_names: could not read the names: {e}")
        return 1
    if not found:
        print(f"public_names: every name in {SNAPSHOT} is still here, or listed as gone")
        return 0
    print(f"public_names: {len(found)} name{'s' if len(found) != 1 else ''} a person's own "
          f"tests may use {'are' if len(found) != 1 else 'is'} gone:")
    for line in found:
        print(f"  {line}")
    print(f"Put each one back (an import under its old module is enough), or list it in "
          f"{REMOVED} with the date, the reason and the CHANGELOG line that tells people.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
