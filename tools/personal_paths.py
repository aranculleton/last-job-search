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
    # Left by the removed /notion-sync in a repo that used it: still theirs.
    "job_scraper/notion_sync.json",
    "documents/**",
    "company_research/*.json",
    "networking/**",
    "upskill/*.md",
    "salary_data.json",
    # Left by the mail sync an older version of the app had: still theirs.
    "gmail_sync/**",
    "rounds/**",
    # Rendered documents. Everything in the two document folders is the
    # person's, whatever the prefix or the noun (Resume, CV): only the app's own
    # templates and fonts there ship, listed in APP_EXCEPTIONS.
    "cv/**",
    "cover_letters/**",
    # Job portals. The app ships only portals that work anywhere (APP_EXCEPTIONS);
    # a board for one country or one field is the person's, built for them by
    # /add-portal in their own repo. So the app's leak scan fails if a
    # market's portal is ever added to the app, and a person's portal is never
    # reported as drift by a sync or scanned as part of the app's tree.
    ".agents/skills/**",
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
    ".agents/skills/linkedin-search/**",
    ".agents/skills/freehire-search/**",
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


def changed(root: str = ROOT, base: str = "origin/master") -> list[str] | None:
    """Every path this checkout changed since it left `base`: committed, staged, unstaged
    and untracked (ignored files aside). None when `base` is not known here."""
    def git(*args):
        return subprocess.run(["git", "-C", root, *args], capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
    fork = git("merge-base", "HEAD", base)
    if fork.returncode:
        return None
    out = set()
    # Both sides of a rename: an app file moved into a personal folder is an app file gone,
    # and with renames read as one change only the new, personal, path was listed, so the
    # light local CI skipped the app's checks (2026-10-21).
    for args in (("diff", "--name-only", "--no-renames", "-z", fork.stdout.strip()),
                 ("ls-files", "--others", "--exclude-standard", "-z")):
        r = subprocess.run(["git", "-C", root, *args], capture_output=True)
        out.update(p for p in r.stdout.decode("utf-8", "replace").split("\0") if p)
    return sorted(out)


# Where the sync keeps the app it merged: the release it took, and the app's master
# (tools/sync_app.py fetches both under its "app" remote).
APP_REFS = ("refs/remotes/app/release-tag", "refs/remotes/app/master")


def _blobs(root: str, ref: str) -> dict[str, str] | None:
    r = subprocess.run(["git", "-C", root, "ls-tree", "-r", "-z", ref], capture_output=True)
    if r.returncode:
        return None
    out = {}
    for entry in r.stdout.decode("utf-8", "replace").split("\0"):
        if "\t" in entry:
            meta, path = entry.split("\t", 1)
            out[path] = meta.split()[2]
    return out


def the_apps_own(root: str, paths: list[str]) -> bool:
    """Whether every one of these app-owned paths is, as committed and in the working tree,
    exactly the app's: the release the sync merged, or the app's master. A merge of an app
    update changes only such files, and the app's own CI tested them on Linux, a Mac and
    Windows before release: running the app's suite again cost a person about 8 minutes a
    merge, and on Windows it stopped a merge outright (2026-10-25)."""
    if not paths:
        return False
    dirty = subprocess.run(["git", "-C", root, "status", "--porcelain", "-z", "--", *paths],
                           capture_output=True).stdout
    if dirty.strip(b"\0"):
        return False
    head = _blobs(root, "HEAD")
    apps = [b for b in (_blobs(root, ref) for ref in APP_REFS) if b is not None]
    if head is None or not apps:
        return False
    return all(any(head.get(p) == app.get(p) for app in apps) for p in paths)


def same_as_the_app(root: str) -> set[str]:
    """Every path whose blob at HEAD is exactly the app's (its release or its master,
    APP_REFS). Empty where no app ref is known."""
    head = _blobs(root, "HEAD")
    apps = [b for b in (_blobs(root, ref) for ref in APP_REFS) if b is not None]
    if head is None or not apps:
        return set()
    return {p for p, blob in head.items() if any(app.get(p) == blob for app in apps)}


def main(argv: list[str]) -> int:
    if argv[:1] in (["-h"], ["--help"]):
        print("usage: python3 tools/personal_paths.py [--personal | --app | "
              "--only-personal-changed]")
        return 0
    if "--only-personal-changed" in argv:
        # For ./tools/ci_local.sh: exit 0, listing them, when every change since master is
        # the person's own (their data, their profile, their tests); 3 when nothing changed
        # at all (the caller decides: a copy has nothing of the app's to test, the app
        # itself checks everything); 1 otherwise.
        got = changed()
        if got is None:
            return 1
        if not got:
            return 3
        app, mine = split(got)
        print("\n".join(mine))
        if not app:
            return 0
        # 2: the app files that changed are the app's own release, tested by its CI.
        return 2 if the_apps_own(ROOT, app) else 1
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
