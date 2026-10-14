#!/usr/bin/env python3
"""The one list of paths that belong to a person, not to the app.

Everything in a person's repo is either theirs (their profile and their search's
state) or the app's (code, skills, docs, templates, the example person). This
file is where that line is drawn, once, and three things read it:

  tools/build_app.py   exports a tree WITHOUT these paths to make the app
  the app's CI guard   fails if any of them exists in the app
  tools/sync_app.py    never touches them, and reports drift: an app-owned file
                       edited in a person's repo, which the next sync overwrites

A path matching PERSONAL and not matching APP_EXCEPTIONS is personal. Patterns
are repo-relative globs: `*` stays within one path segment, `**` crosses them.

Usage:
    from personal_paths import is_personal, split
    is_personal("job_search_tracker.csv")       # True
    python3 tools/personal_paths.py             # every tracked file, classified
    python3 tools/personal_paths.py --personal  # just the personal ones
"""

from __future__ import annotations

import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PERSONAL = (
    # The profile: identity, history, bullets, skills, market, preferences,
    # voice, the person's own tests and their routines' ids.
    "profile/**",
    # Work-in-progress notes about one person's repo.
    "handoff/**",
    # The search's state.
    "job_search_tracker.csv",
    "network_contacts.csv",
    "network_threads.csv",
    "job_scraper/seen_jobs.json",
    "job_scraper/do_not_target.json",
    "job_scraper/notion_sync.json",
    "documents/**",
    "company_research/*.json",
    "networking/**",
    "upskill/*.md",
    "salary_data.json",
    "gmail_sync/**",
    "rounds/**",
    # Rendered documents. Everything in the two document folders is the
    # person's, whatever the prefix or the noun (Resume, CV): only the app's own
    # templates and fonts there ship, listed in APP_EXCEPTIONS.
    "cv/**",
    "cover_letters/**",
)

# Scaffolding inside personal directories that ships with the app, so a new
# copy has the folders /setup and the tools expect.
APP_EXCEPTIONS = (
    "documents/README.md",
    "documents/**/.gitkeep",
    "cv/main_example.tex",
    "cover_letters/cover.cls",
    "cover_letters/cover_example.tex",
    "cover_letters/OpenFonts/**",
)


def _regex(glob: str) -> re.Pattern:
    out, i = [], 0
    while i < len(glob):
        if glob.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif glob.startswith("**", i):
            out.append(".*")
            i += 2
        elif glob[i] == "*":
            out.append("[^/]*")
            i += 1
        elif glob[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(glob[i]))
            i += 1
    return re.compile("".join(out) + r"\Z")


_PERSONAL = [_regex(g) for g in PERSONAL]
_EXCEPT = [_regex(g) for g in APP_EXCEPTIONS]


def is_personal(path: str) -> bool:
    """Whether a repo-relative path belongs to the person rather than the app."""
    p = path.replace(os.sep, "/")
    if p.startswith("./"):
        p = p[2:]
    if any(r.match(p) for r in _EXCEPT):
        return False
    return any(r.match(p) for r in _PERSONAL)


def split(paths) -> tuple[list[str], list[str]]:
    """(app, personal) for an iterable of repo-relative paths."""
    app, mine = [], []
    for p in paths:
        (mine if is_personal(p) else app).append(p)
    return app, mine


def tracked(root: str = ROOT) -> list[str]:
    out = subprocess.run(["git", "-C", root, "ls-files", "-z"],
                         capture_output=True, check=True).stdout
    return [p for p in out.decode("utf-8").split("\0") if p]


def main(argv: list[str]) -> int:
    app, mine = split(tracked())
    if "--personal" in argv:
        print("\n".join(mine))
    elif "--app" in argv:
        print("\n".join(app))
    else:
        print(f"{len(app)} app-owned, {len(mine)} personal")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
