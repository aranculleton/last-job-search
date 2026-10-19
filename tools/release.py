#!/usr/bin/env python3
"""Publish the newest CHANGELOG version as a release, once, when its PR lands.

Every person's repo follows the app's newest vX.Y.Z tag (tools/sync_app.py). The tag
used to be made by hand on the GitHub website after the release PR merged, a step
nothing reminded anyone of: 3.3.0 sat merged and unpublished, and a session cannot push
a tag. .github/workflows/release.yml runs this on every push to master that touches
CHANGELOG.md, so merging the release PR is the release.

    python3 tools/release.py newest            # the version, its date, and whether it is tagged
    python3 tools/release.py notes [X.Y.Z]     # the release notes a person reads
    python3 tools/release.py notes X.Y.Z --full    # the whole CHANGELOG section
    python3 tools/release.py publish           # tag and publish the newest, if it has no tag yet

The notes are short on purpose: one line per change, its headline from the CHANGELOG, a
few plain words where a change needs the person, and one closing line on what to do. The
CHANGELOG keeps the detail, for the sessions that work on the app; the release page held
the whole section once, and to a person it read as walls of text.

It never moves, replaces or deletes a tag. A version already tagged (by hand, or by an
earlier run) is not tagged again, and one no newer than the newest tag is not released:
a fix to an old section's wording is not a release. The newest release's notes are
rewritten when they differ from what this file now makes of its section.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHANGELOG = os.path.join(ROOT, "CHANGELOG.md")
HEAD = re.compile(r"^## \[(\d+)\.(\d+)\.(\d+)\] - (\d{4}-\d{2}-\d{2})\s*$", re.M)


def sections(text: str | None = None) -> list[dict]:
    """Every released section, newest first: {"version", "date", "notes"}."""
    if text is None:
        with open(CHANGELOG, encoding="utf-8") as fh:
            text = fh.read()
    out = []
    for m in HEAD.finditer(text):
        end = re.compile(r"^## \[", re.M).search(text, m.end())
        body = text[m.end():end.start() if end else len(text)].strip()
        out.append({"version": ".".join(m.group(1, 2, 3)), "date": m.group(4), "notes": body})
    return out


_GROUP = {"Added": "New", "Fixed": "Fixed", "Changed": "Changed", "Removed": "Removed"}


def _needs(ids: list[str]) -> str:
    """"you" when any of these profile upgrades asks the person, "nobody" when they apply
    themselves, "" for none known."""
    try:
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        import profile_upgrades
        found = [profile_upgrades.by_id(i) for i in ids if any(
            u.id == i for u in profile_upgrades.REGISTRY)]
    except Exception:  # noqa: BLE001  the notes never fail on a lookup
        return ""
    if not found:
        return ""
    return "you" if any(u.needs == "you" for u in found) else "nobody"


def short(notes: str) -> str:
    """The release notes a person reads, from a CHANGELOG section."""
    groups: list[tuple[str, list[str]]] = []
    asks = 0
    entries: list[tuple[str, str]] = []           # (group, the entry's whole text)
    group = ""
    for line in notes.splitlines():
        h = re.match(r"^###\s+(.+?)\s*$", line)
        if h:
            group = _GROUP.get(h.group(1), h.group(1))
            continue
        if line.startswith("- "):
            entries.append((group, line[2:]))
        elif entries and line.startswith("  "):
            entries[-1] = (entries[-1][0], entries[-1][1] + " " + line.strip())
    for group, text in entries:
        m = re.match(r"\*\*(.+?)\*\*", text)
        head = (m.group(1) if m else re.split(r"(?<=[.!?])\s", text, maxsplit=1)[0]).strip()
        # Every line a sentence, however its heading ended ("...them:", "...found").
        head = head.rstrip(":;, ") + ("" if head.rstrip(":;, ").endswith((".", "!", "?")) else ".")
        up = re.search(r"Profile upgrade:\s*([^.(]*)", text)
        ids = re.findall(r"[a-z][a-z0-9-]+", up.group(1)) if up else []
        need = _needs(ids)
        if need == "you":
            asks += 1
            head += " (Claude asks you once)"
        elif need == "nobody":
            head += " (set up for you)"
        if not groups or groups[-1][0] != group:
            groups.append((group, []))
        groups[-1][1].append(head)
    out = []
    for group, heads in groups:
        out += ([f"**{group}**"] if group else []) + [f"- {h}" for h in heads] + [""]
    out.append("What to do: nothing. Your next chat takes this update and sets it up"
               + (f", and asks you {asks} short question{'s' if asks != 1 else ''} once."
                  if asks else "."))
    return "\n".join(out)


def _gh(args: list[str]) -> subprocess.CompletedProcess:
    cmd = ["gh", *args]
    if os.environ.get("GITHUB_REPOSITORY"):
        cmd += ["--repo", os.environ["GITHUB_REPOSITORY"]]
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)


def _key(version: str) -> tuple:
    return tuple(int(x) for x in version.split("."))


def tags() -> list[str]:
    out = subprocess.run(["git", "-C", ROOT, "ls-remote", "--tags", "--refs", "origin", "v*"],
                         capture_output=True, text=True, check=True).stdout
    return [ln.split("refs/tags/", 1)[1] for ln in out.splitlines() if "refs/tags/" in ln]


def decide(newest: dict | None, existing: list[str]) -> str:
    """"" to publish `newest`, otherwise why not."""
    if not newest:
        return "no released section in CHANGELOG.md (only [Unreleased])"
    if not newest["notes"]:
        return f"{newest['version']} has no notes"
    tag = "v" + newest["version"]
    if tag in existing:
        return f"{tag} is already tagged"
    versions = [t[1:] for t in existing if re.fullmatch(r"v\d+\.\d+\.\d+", t)]
    if versions and _key(newest["version"]) <= max(map(_key, versions)):
        return f"{tag} is not newer than v{max(versions, key=_key)}"
    return ""


def publish(sha: str | None = None) -> int:
    got = sections()
    newest = got[0] if got else None
    existing = tags()
    why = decide(newest, existing)
    text = short(newest["notes"]) if newest else ""
    if why:
        tag = "v" + newest["version"] if newest else ""
        if newest and tag in existing:
            return refresh(tag, text)
        print(f"release: nothing to publish: {why}")
        return 0
    tag = "v" + newest["version"]
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as fh:
        fh.write(text + "\n")
        notes = fh.name
    r = _gh(["release", "create", tag, "--title", tag, "--notes-file", notes,
             "--target", sha or os.environ.get("GITHUB_SHA") or "master"])
    os.unlink(notes)
    print(f"release: published {tag}" if r.returncode == 0 else (r.stderr or r.stdout))
    return r.returncode


def refresh(tag: str, text: str) -> int:
    """The newest release's notes, rewritten when they differ from what its section now
    makes. Only the notes: the tag is never touched."""
    view = _gh(["release", "view", tag, "--json", "body", "--jq", ".body"])
    if view.returncode != 0:
        print(f"release: {tag} is tagged with no release to update")
        return 0
    if view.stdout.strip() == text.strip():
        print(f"release: {tag}'s notes are current")
        return 0
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as fh:
        fh.write(text + "\n")
        notes = fh.name
    r = _gh(["release", "edit", tag, "--notes-file", notes])
    os.unlink(notes)
    print(f"release: {tag}'s notes rewritten" if r.returncode == 0 else (r.stderr or r.stdout))
    return r.returncode


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] not in ("newest", "notes", "publish"):
        print(__doc__.split("\n\n")[2])
        return 2
    if argv[0] == "publish":
        return publish()
    got = sections()
    if argv[0] == "notes":
        rest = [a for a in argv[1:] if a != "--full"]
        want = rest[0] if rest else (got[0]["version"] if got else "")
        hit = next((s for s in got if s["version"] == want), None)
        if not hit:
            print(f"release: no section {want!r} in CHANGELOG.md", file=sys.stderr)
            return 1
        print(hit["notes"] if "--full" in argv else short(hit["notes"]))
        return 0
    if not got:
        print("release: no released section yet")
        return 0
    n = got[0]
    try:
        why = decide(n, tags())
    except subprocess.CalledProcessError:
        why = "(tags not readable here)"
    print(f"{n['version']} ({n['date']}): " + (why or "not tagged yet: merging it publishes it"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
