#!/usr/bin/env python3
"""Which of the person's GitHub repositories is their copy of the app?

A chat on a new computer clones the person's private copy, and a person who made it with
"Use this template" a week ago may not remember what they called it. GitHub records the
template a repository was made from, so once `gh` is signed in this asks, and prints
each of their repositories made from the app, newest first:

    python3 tools/find_copy.py              owner/name, one a line; exit 1 when none
    python3 tools/find_copy.py --gh <path>  with a gh that is not on PATH yet

The chat clones the only one without asking; with two or more it asks which, by name.
It runs from the public app (COMPUTER.md clones it first), before any copy is here.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

APP = "aranculleton/last-job-search"
QUERY = ("query($after: String) { viewer { repositories(first: 100, after: $after, "
         "ownerAffiliations: [OWNER, ORGANIZATION_MEMBER, COLLABORATOR], "
         "orderBy: {field: CREATED_AT, direction: DESC}) { pageInfo { hasNextPage endCursor } "
         "nodes { nameWithOwner isPrivate templateRepository { nameWithOwner } } } } }")


def copies(pages: list[dict], app: str = APP) -> list[str]:
    """owner/name of every repository in GitHub's answer made from `app`, newest first."""
    out = []
    for page in pages:
        repos = (((page or {}).get("data") or {}).get("viewer") or {}).get("repositories") or {}
        for node in repos.get("nodes") or []:
            tpl = (node.get("templateRepository") or {}).get("nameWithOwner") or ""
            if tpl.lower() == app.lower() and node.get("nameWithOwner"):
                out.append(node["nameWithOwner"])
    return out


def ask_github(gh: str, limit_pages: int = 10) -> list[dict]:
    pages, after = [], None
    for _ in range(limit_pages):
        cmd = [gh, "api", "graphql", "-f", f"query={QUERY}"]
        if after:
            cmd += ["-f", f"after={after}"]
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=60, stdin=subprocess.DEVNULL)
        if p.returncode != 0:
            raise RuntimeError((p.stderr or p.stdout).strip().splitlines()[-1:] or ["gh failed"])
        page = json.loads(p.stdout)
        pages.append(page)
        info = page["data"]["viewer"]["repositories"]["pageInfo"]
        if not info.get("hasNextPage"):
            break
        after = info.get("endCursor")
    return pages


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] in (["-h"], ["--help"]):
        print(__doc__.strip().split("\n\n")[1])
        return 0
    gh = argv[argv.index("--gh") + 1] if "--gh" in argv else shutil.which("gh")
    if not gh or not os.path.exists(gh) and not shutil.which(gh):
        print("find_copy: GitHub's command line is not here yet", file=sys.stderr)
        return 2
    try:
        found = copies(ask_github(gh))
    except Exception as exc:  # noqa: BLE001  one plain line, whatever gh said
        print(f"find_copy: GitHub did not answer: {exc}", file=sys.stderr)
        return 2
    for name in found:
        print(name)
    return 0 if found else 1


if __name__ == "__main__":
    sys.exit(main())
