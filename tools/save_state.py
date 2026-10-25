#!/usr/bin/env python3
"""Stage a person's own files for a commit: the persistence rule in CLAUDE.md, as code.

The rule was a shell loop pasted into chats. Under zsh, the Mac's own shell, a pattern
that matched nothing (`cv/*_CV_*.tex` in a repo that only has resumes) stopped the loop
with "no matches found" before it had staged anything (2026-10-24). Here every pattern is
expanded in Python, so the shell does not matter, and a folder forced in is walked file
by file so the build noise the rule says never to commit stays out.

    python3 tools/save_state.py            # stage them; prints what it staged
    python3 tools/save_state.py --list     # say what it would stage, and change nothing

`profile` and `networking` take a plain `git add` (never forced, which would bring the
caches under profile/tests/ with them); everything else is ignored by .gitignore on
purpose, so it is forced in by path, one existing path at a time, and a file of theirs the
repo holds that has gone from disk is staged as removed. Exit 0, or 1 when git refused.
"""
from __future__ import annotations

import fnmatch
import glob
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PLAIN = ("profile", "networking")
FORCED = (
    "job_search_tracker.csv", "network_contacts.csv", "network_threads.csv",
    "job_scraper/seen_jobs.json", "job_scraper/do_not_target.json",
    "documents/cv", "documents/applications", "documents/network", "documents/rounds",
    "documents/interview",
    "cv/*_Resume_*.tex", "cv/*_Resume_*.pdf", "cv/*_CV_*.tex", "cv/*_CV_*.pdf",
    "cover_letters/*_Cover_Letter_*.tex", "cover_letters/*_Cover_Letter_*.pdf",
    "company_research/*.json", "upskill/*.md",
)
# Never forced in: LaTeX's build files, text dumps of a resume, caches, licensed salary
# data and the Gmail sync's cursor (CLAUDE.md, "Never force-add build noise").
NOISE = ("*.aux", "*.log", "*.out", "*.fls", "*.fdb_latexmk", "*.synctex.gz", "cv/*.txt",
         "*/__pycache__/*", "__pycache__/*", "*.pyc", "*/.pytest_cache/*", ".pytest_cache/*",
         "salary_data.json", "*/salary_data.json", "gmail_sync/state.json", ".DS_Store",
         "*/.DS_Store")


def _noise(rel: str) -> bool:
    return any(fnmatch.fnmatch(rel, pat) for pat in NOISE)


def paths(root: str = ROOT) -> tuple[list[str], list[str]]:
    """(plain, forced): the paths that exist, relative to `root`, in the rule's order."""
    plain = [p for p in PLAIN if os.path.exists(os.path.join(root, p))]
    forced: list[str] = []
    for pat in FORCED:
        for full in sorted(glob.glob(os.path.join(root, pat))):
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            if os.path.isdir(full):
                for dp, dirs, files in os.walk(full):
                    dirs[:] = sorted(d for d in dirs if d not in ("__pycache__", ".pytest_cache"))
                    for f in sorted(files):
                        r = os.path.relpath(os.path.join(dp, f), root).replace(os.sep, "/")
                        if not _noise(r):
                            forced.append(r)
            elif not _noise(rel):
                forced.append(rel)
    return plain, list(dict.fromkeys(forced))


def _git(root: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", root, *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def _under(rel: str) -> bool:
    """Is a path one of the rule's: a FORCED file or pattern, or inside a FORCED folder."""
    return any(fnmatch.fnmatch(rel, pat) or rel.startswith(pat.rstrip("/") + "/")
               for pat in FORCED)


def gone(root: str = ROOT) -> list[str]:
    """Files the repo holds under the rule's paths that are no longer on disk: a sent
    draft taken away (documents/network/<id>/draft.md), say. The loop staged their removal
    as `git add -f -- documents/network` did; walking only what exists did not, and the
    draft came back in the next container (2026-10-24)."""
    r = _git(root, "ls-files", "--deleted", "-z")
    if r.returncode != 0:
        return []
    return [p for p in dict.fromkeys(r.stdout.split("\0")) if p and _under(p)]



def _utf8_stdio() -> None:
    """The terminal in UTF-8 whatever the computer's code page (python_floor.utf8_stdio): a
    name with "Ł" in it stopped this on a cp1252 Windows terminal. Never raises."""
    try:
        import python_floor
        python_floor.utf8_stdio()
    except Exception:  # noqa: BLE001
        pass


def main(argv: list[str] | None = None, root: str = ROOT) -> int:
    _utf8_stdio()
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] in (["-h"], ["--help"]):
        print(__doc__.strip())
        return 0
    plain, forced = paths(root)
    removed = gone(root)
    if "--list" in argv:
        for p in plain:
            print(f"add     {p}")
        for p in forced:
            print(f"add -f  {p}")
        for p in removed:
            print(f"remove  {p}")
        print(f"save_state: {len(plain)} plain, {len(forced)} forced, {len(removed)} removed; "
              "nothing staged (--list)")
        return 0
    failed = []
    if plain:
        r = _git(root, "add", "--", *plain)
        if r.returncode != 0:
            failed.append(r.stderr.strip())
    # In batches, so a long list never runs into the system's limit on one command's length.
    for i in range(0, len(forced), 200):
        r = _git(root, "add", "-f", "--", *forced[i:i + 200])
        if r.returncode != 0:
            failed.append(r.stderr.strip())
    for i in range(0, len(removed), 200):
        r = _git(root, "rm", "--cached", "--quiet", "--", *removed[i:i + 200])
        if r.returncode != 0:
            failed.append(r.stderr.strip())
    if failed:
        print("save_state: git refused: " + "; ".join(f for f in failed if f))
        return 1
    staged = _git(root, "diff", "--cached", "--name-only").stdout.split()
    print(f"save_state: staged; {len(staged)} file(s) now waiting to be committed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
