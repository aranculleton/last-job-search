#!/usr/bin/env python3
"""Publish the newest CHANGELOG version as a release, once, when its PR lands.

Every person's repo follows the app's newest vX.Y.Z tag (tools/sync_app.py). The tag
used to be made by hand on the GitHub website after the release PR merged, a step
nothing reminded anyone of: 3.3.0 sat merged and unpublished, and a session cannot push
a tag. .github/workflows/release.yml runs this on every push to master that touches
CHANGELOG.md, so merging the release PR is the release.

    python3 tools/release.py newest            # the version, its date, and whether it is tagged
    python3 tools/release.py notes [X.Y.Z]     # a version's CHANGELOG section, the release notes
    python3 tools/release.py publish           # tag and publish the newest, if it has no tag yet

It never moves, replaces or deletes a tag. A version already tagged (by hand, or by an
earlier run) is left alone, and so is one no newer than the newest tag: a fix to an old
section's wording is not a release.
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
    why = decide(newest, tags())
    if why:
        print(f"release: nothing to publish: {why}")
        return 0
    tag = "v" + newest["version"]
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as fh:
        fh.write(newest["notes"] + "\n")
        notes = fh.name
    cmd = ["gh", "release", "create", tag, "--title", tag, "--notes-file", notes,
           "--target", sha or os.environ.get("GITHUB_SHA") or "master"]
    if os.environ.get("GITHUB_REPOSITORY"):
        cmd += ["--repo", os.environ["GITHUB_REPOSITORY"]]
    r = subprocess.run(cmd, cwd=ROOT)
    os.unlink(notes)
    if r.returncode == 0:
        print(f"release: published {tag}")
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
        want = argv[1] if len(argv) > 1 else (got[0]["version"] if got else "")
        hit = next((s for s in got if s["version"] == want), None)
        if not hit:
            print(f"release: no section {want!r} in CHANGELOG.md", file=sys.stderr)
            return 1
        print(hit["notes"])
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
