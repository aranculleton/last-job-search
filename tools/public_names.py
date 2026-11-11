#!/usr/bin/env python3
"""The app's public names, so that none is taken away without saying so.

A person's own tests (profile/tests) may use any of the app's public names: a top-level
name in tools/ or templates/ that does not start with an underscore, outside
tools/openroles/ (CLAUDE.md, "App-owned files and personal files"). 3.5.0 moved the
board reading into tools/openroles and broke dozens of the maintainer's own tests, and the
work towards the release after 3.13.0 removed holidays.is_holiday and
score_eval.EXPECTATIONS with nothing in their place. Nothing stopped either.

    python3 tools/public_names.py check      # every name the newest release ships is still here, or listed as gone

The names people have are the newest release's: read from that tag's own files (`git
ls-tree` and `git cat-file`), never from a copy kept beside the code. A clone without the
tag fetches that one tag (`--depth=1` in a shallow clone, as CI's); a copy whose own remote
has no app releases, as a person's copy has, says so and passes. Until 4.15.1 a snapshot of
every name, 89 KB, was written afresh at each release, a step of its own.

The names are read with ast, never imported: every def, async def and class, and every
module-level assignment, annotated ones included. A name may go only when
docs/removed_names.json lists it (the file, the name, the day and the CHANGELOG section
that announces it) and an entry in that section names it. A section is "Unreleased" until
`release.py cut` names the version, which rewrites the listing with it. A name still
imported under its old module has not gone, because a test using it still works. A new
name needs nothing. Exit 1 on a finding, 0 otherwise.
"""
from __future__ import annotations

import ast
import datetime as dt
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCAN = ("tools", "templates")
REMOVED = "docs/removed_names.json"
CHANGELOG = "CHANGELOG.md"
# Vendored from openroles and never edited here: its names are openroles' own.
SKIP = ("tools/openroles",)
NEEDS = ("module", "name", "date", "announced")
RELEASE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
SECTION = re.compile(r"^(Unreleased|\d+\.\d+\.\d+)$")


def counted(path: str) -> bool:
    """Is this file, a path from the root, one whose names a person's tests may use: a .py
    under tools/ or templates/, but openroles and any test or cache folder."""
    parts = path.split("/")
    if not path.endswith(".py") or parts[0] not in SCAN or len(parts) < 2:
        return False
    if any(path == s or path.startswith(s + "/") for s in SKIP):
        return False
    return not any(d in ("tests", "test") or d.startswith((".", "__")) or d.endswith("_cache")
                   for d in parts[1:-1])


def _files(root: str):
    """Every counted .py in this tree, as a path from the root."""
    for top in SCAN:
        start = os.path.join(root, top)
        for base, dirs, files in os.walk(start):
            rel = top + base[len(start):].replace(os.sep, "/")
            dirs[:] = sorted(d for d in dirs if counted(f"{rel}/{d}/x.py"))
            for name in sorted(files):
                if counted(f"{rel}/{name}"):
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


def _public(text: str, path: str, imports: bool) -> list[str]:
    return sorted({n for n in _bound(ast.parse(text, filename=path).body, imports)
                   if not n.startswith("_") and n != "*"})


def names(root: str = ROOT, imports: bool = False) -> dict[str, list[str]]:
    """{file: [public names]} for this tree, files with none left out. With `imports`,
    the names each file's imports bring in are counted as well."""
    out = {}
    for path in _files(root):
        with open(os.path.join(root, path), encoding="utf-8") as fh:
            got = _public(fh.read(), path, imports)
        if got:
            out[path] = got
    return out


# ------------------------------------------------------------------ the newest release

def _git(root: str, *args: str, data: bytes | None = None,
         timeout: float = 120) -> subprocess.CompletedProcess:
    """git -C root, never prompting and never raising: a missing git or a stalled network
    is an ordinary failure."""
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    try:
        return subprocess.run(["git", "-C", root, *args], input=data, capture_output=True,
                              env=env, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as e:
        return subprocess.CompletedProcess(args, 127, b"", str(e).encode())


def _key(tag: str) -> tuple:
    return tuple(int(x) for x in RELEASE.match(tag).groups())


def release_tags(root: str = ROOT) -> tuple[dict[str, str], bool]:
    """({tag: its commit, "" where not known}, whether GitHub was asked and answered), for
    every vX.Y.Z this clone holds and its own remote (origin) has. A person's copy has none:
    its origin is their own."""
    found: dict[str, str] = {}
    local = _git(root, "tag", "-l", "v*")
    for tag in local.stdout.decode("utf-8", "replace").split() if local.returncode == 0 else []:
        found[tag] = ""
    remote = _git(root, "ls-remote", "--tags", "origin", "v*", timeout=30)
    for line in remote.stdout.decode("utf-8", "replace").splitlines() if remote.returncode == 0 else []:
        sha, _, ref = line.partition("\trefs/tags/")
        tag, peeled = (ref[:-3], True) if ref.endswith("^{}") else (ref, False)
        if tag and (peeled or not found.get(tag)):
            found[tag] = sha.strip()
    return {t: s for t, s in found.items() if RELEASE.match(t)}, remote.returncode == 0


def _commit(root: str, tag: str, sha: str) -> str:
    """The tag's commit if this clone holds it, else ""."""
    for ref in (f"refs/tags/{tag}^{{commit}}", f"{sha}^{{commit}}" if sha else ""):
        if ref:
            r = _git(root, "rev-parse", "--verify", "-q", ref)
            if r.returncode == 0:
                return r.stdout.decode().strip()
    return ""


def newest_release(root: str = ROOT) -> tuple[str, str, str]:
    """(tag, commit, "") for the newest release this tree holds, fetching that one tag where
    the clone lacks it; ("", "", why) when there is none to compare with."""
    tags, asked = release_tags(root)
    if not tags:
        return "", "", ("no release of the app is known here" if asked else
                        "no release of the app is known here, and GitHub could not be asked")
    order = sorted(tags, key=_key, reverse=True)
    tag = order[0]
    commit = _commit(root, tag, tags[tag])
    shallow = _git(root, "rev-parse", "--is-shallow-repository").stdout.decode().strip() == "true"
    held = lambda c: _git(root, "merge-base", "--is-ancestor", c, "HEAD").returncode == 0  # noqa: E731
    if commit and not held(commit) and not shallow:
        # A copy made before the newest release: the newest it holds is what it must keep.
        for older in order[1:]:
            c = _commit(root, older, tags[older])
            if c and held(c):
                return older, c, ""
    if not commit:
        _git(root, "fetch", "--quiet", "--no-tags", *(["--depth=1"] if shallow else []),
             "origin", f"refs/tags/{tag}")
        commit = _commit(root, tag, tags[tag])
    if not commit:
        return "", "", f"the newest release, {tag}, could not be fetched"
    return tag, commit, ""


def names_at(root: str, commit: str) -> dict[str, list[str]]:
    """{file: [public names]} in that commit's own files, read from git, never checked out."""
    listing = _git(root, "ls-tree", "-r", "--full-tree", commit, "--", *SCAN)
    if listing.returncode != 0:
        raise OSError(listing.stderr.decode("utf-8", "replace").strip() or "git ls-tree failed")
    blobs = []
    for line in listing.stdout.decode("utf-8", "replace").splitlines():
        meta, _, path = line.partition("\t")
        parts = meta.split()
        if len(parts) == 3 and parts[1] == "blob" and counted(path):
            blobs.append((path, parts[2]))
    batch = _git(root, "cat-file", "--batch", data="".join(f"{s}\n" for _, s in blobs).encode())
    if batch.returncode != 0:
        raise OSError(batch.stderr.decode("utf-8", "replace").strip() or "git cat-file failed")
    out, raw, at = {}, batch.stdout, 0
    for path, _sha in blobs:
        head_end = raw.index(b"\n", at)
        size = int(raw[at:head_end].split()[2])
        text = raw[head_end + 1:head_end + 1 + size].decode("utf-8")
        at = head_end + 1 + size + 1
        got = _public(text, path, imports=False)
        if got:
            out[path] = got
    return out


# ------------------------------------------------------------------ what was taken away

def _load(root: str) -> dict:
    full = os.path.join(root, REMOVED)
    if not os.path.exists(full):
        return {}
    with open(full, encoding="utf-8") as fh:
        return json.load(fh)


def write_removed(root: str, doc: dict) -> None:
    """docs/removed_names.json, one record a line."""
    rows = ",\n".join("  " + json.dumps({k: e[k] for k in NEEDS if k in e}, ensure_ascii=False)
                      for e in doc.get("removed", []))
    text = ("{\n \"about\": " + json.dumps(doc.get("about", ""), ensure_ascii=False)
            + ",\n \"removed\": [\n" + rows + ("\n" if rows else "") + " ]\n}\n")
    with open(os.path.join(root, REMOVED), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def announce(root: str, version: str) -> int:
    """Every removal announced in [Unreleased] is announced in `version` from now on, as
    `release.py cut` names that section. How many were."""
    doc = _load(root)
    moved = 0
    for e in doc.get("removed", []):
        if e.get("announced") == "Unreleased":
            e["announced"] = version
            moved += 1
    if moved:
        write_removed(root, doc)
    return moved


def _entries(changelog: str) -> dict[str, list[str]]:
    """{section: [each entry's whole text]}, a section named as its heading names it."""
    out: dict[str, list[str]] = {}
    current = None
    for line in changelog.splitlines():
        h = re.match(r"^## \[([^\]]+)\]", line)
        if h:
            current = out.setdefault(h.group(1), [])
        elif current is not None and line.startswith("- "):
            current.append(line[2:])
        elif current and line.startswith("  "):
            current[-1] += " " + line.strip()
    return out


def _listing_problem(entry: dict, sections: dict[str, list[str]]) -> str:
    """Why a removal's record in docs/removed_names.json does not yet tell people, or ""."""
    missing = [k for k in NEEDS if not str(entry.get(k) or "").strip()]
    if missing:
        return f"listed in {REMOVED} with no {' and no '.join(missing)}"
    try:
        dt.date.fromisoformat(str(entry["date"]))
    except ValueError:
        return f"listed in {REMOVED} with a date that is not YYYY-MM-DD ({entry['date']})"
    where = str(entry["announced"])
    if not SECTION.match(where):
        return (f"listed in {REMOVED} as announced in {where!r}, which is not a version "
                f"or Unreleased")
    if where not in sections:
        return f"listed in {REMOVED} as announced in {where}, but {CHANGELOG} has no [{where}]"
    name = re.escape(str(entry["name"]))
    stem = os.path.splitext(os.path.basename(str(entry["module"])))[0]
    if not any(re.search(rf"(?<![\w]){name}(?![\w])", e) and stem in e for e in sections[where]):
        return (f"listed in {REMOVED}, but no entry in [{where}] of {CHANGELOG} names it "
                f"with its file ({stem})")
    return ""


def check(root: str = ROOT, release: tuple[str, str] | None = None) -> list[str]:
    """One plain line per public name the newest release ships that this tree no longer has
    and docs/removed_names.json does not account for, and per record there that does not
    tell people. Empty when nothing is wrong, and when there is no release to compare with
    (`release`, (tag, commit), is found when not given)."""
    full = os.path.join(root, CHANGELOG)
    changelog = open(full, encoding="utf-8").read() if os.path.exists(full) else ""
    sections = _entries(changelog)
    records = _load(root).get("removed", [])
    out = []
    for e in records:
        why = _listing_problem(e, sections)
        if why:
            out.append(f"{e.get('module')} {e.get('name')}: {why}.")
    if release is None:
        tag, commit, _why = newest_release(root)
        release = (tag, commit)
    if not release[1]:
        return out
    listed = {(e.get("module"), e.get("name")) for e in records}
    now = names(root, imports=True)
    for path, wanted in sorted(names_at(root, release[1]).items()):
        here = set(now.get(path, ()))
        for name in wanted:
            if name in here or (path, name) in listed:
                continue
            where = "" if os.path.exists(os.path.join(root, path)) else " (the file is gone)"
            out.append(f"{path}{where} no longer has {name}, which {release[0]} ships.")
    return out


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "-h" in argv or "--help" in argv:
        print("usage:\n" + __doc__.split("\n\n")[2])
        return 0
    if argv[:1] != ["check"]:
        print(__doc__.split("\n\n")[2])
        return 2
    try:
        tag, commit, why = newest_release()
        found = check(release=(tag, commit))
    except (OSError, SyntaxError, ValueError) as e:
        print(f"public_names: could not read the names: {e}")
        return 1
    if not found:
        print(f"public_names: every name {tag} ships is still here, or listed as gone" if tag
              else f"public_names: nothing to compare with: {why}, so no name can have gone.")
        return 0
    print(f"public_names: {len(found)} name{'s' if len(found) != 1 else ''} a person's own "
          f"tests may use {'are' if len(found) != 1 else 'is'} gone, or not yet announced:")
    for line in found:
        print(f"  {line}")
    print(f"Put each one back (an import under its old module is enough), or list it in "
          f"{REMOVED} with its file, the day and the CHANGELOG section whose entry names it "
          f"(\"Unreleased\" until the version is cut).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
