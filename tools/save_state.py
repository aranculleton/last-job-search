#!/usr/bin/env python3
"""Stage a person's own files for a commit: the persistence rule in CLAUDE.md, as code.

The rule was a shell loop pasted into chats. Under zsh, the Mac's own shell, a pattern
that matched nothing (`cv/*_CV_*.tex` in a repo that only has resumes) stopped the loop
with "no matches found" before it had staged anything (2026-10-24). Here every pattern is
expanded in Python, so the shell does not matter, and a folder forced in is walked file
by file so the build noise the rule says never to commit stays out.

    python3 tools/save_state.py            # stage them; prints what it staged
    python3 tools/save_state.py --list     # say what it would stage, and change nothing

`profile`, `networking`, `documents` and `handoff` take a plain `git add` (never forced, which would bring the
caches under profile/tests/ with them); everything else is ignored by .gitignore on
purpose, so it is forced in by path, one existing path at a time, and a file of theirs the
repo holds that has gone from disk is staged as removed. Exit 0, or 1 when git refused.

`tools/land.py` runs this first, then commits, merges master, runs the landing check
(`./tools/ci_local.sh --quick`) and pushes, all in the background (RUNBOOK.md, "4. Record
and persist, then land on master"): the check held the chat that answers the page for
minutes in the foreground.
"""
from __future__ import annotations

import fnmatch
import glob
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Taken whole with a plain add, which keeps .gitignore's private folders out: everything the
# app writes under documents/ is the person's record (personal_paths.PERSONAL), and a new
# file there is saved without anyone listing it here. The brief's own records
# (documents/briefs/), what is coming up (documents/upcoming.json) and the page's file ids
# (documents/page_assets.json) were never staged, and two days of briefs were lost with their
# containers (engine audit, 2026-11-03).
PLAIN = ("profile", "networking", "documents", "handoff")
# What personal_paths.PERSONAL holds that is never saved, and why: tests/test_saving_works_in_
# any_shell.py fails on a personal path that is neither saved nor here.
NEVER = {
    "salary_data.json": "licensed salary data, never committed",
    "gmail_sync/**": "the mail cursor an older version left: message ids and subjects",
    "rounds/**": "a search round's working files, tens of megabytes, made again by the round",
    "job_scraper/notion_sync.json": "left by the removed /notion-sync, kept as it is",
    ".agents/skills/**": "a job site of their own: committed by /add-portal with its code, "
                         "then saved like the profile once it is in the repo (own_portals)",
    "documents/linkedin/**": "the LinkedIn download: only its connections and invitations go",
    "documents/postings/**": "postings' own text, kept out like a round's",
    "documents/diplomas/**": "copies of their certificates, never committed",
    "documents/references/**": "references' own letters, never committed",
    "documents/to_send/**": "copies made each time a prep is sent; the kept file is the record",
}
FORCED = (
    "job_search_tracker.csv", "network_contacts.csv", "network_threads.csv",
    "job_scraper/seen_jobs.json", "job_scraper/do_not_target.json",
    "documents/cv", "documents/applications", "documents/network", "documents/rounds",
    "documents/interview",
    # Every rendered document, whatever the person's word for it: a resume named in their
    # own language (Lebenslauf, curriculo) matched neither "_Resume_" nor "_CV_", and every
    # tailored one was lost with its chat (the stranger audit, 2026-11-03). The app's own
    # templates there are left out by personal_paths.
    "cv/*.tex", "cv/*.pdf", "cv/*.docx",
    "cover_letters/*.tex", "cover_letters/*.pdf", "cover_letters/*.docx",
    "company_research/*.json", "upskill/*.md",
    # The LinkedIn download's connections and invitations, which later runs read (the ladder's
    # first rung, who has a request pending). In the cloud a chat's folder goes when it ends,
    # so they were gone by the next chat (2026-10-29). Not messages.csv: its history is in
    # network_threads.csv already, and it runs to tens of megabytes.
    "documents/linkedin/Connections.csv", "documents/linkedin/Invitations.csv",
)
# Never forced in: LaTeX's build files, text dumps of a resume, caches, licensed salary
# data, and the mail cursor an older version of the app left in some repos (CLAUDE.md,
# "Never force-add build noise").
NOISE = ("*.aux", "*.log", "*.out", "*.fls", "*.fdb_latexmk", "*.synctex.gz", "cv/*.txt",
         "*/__pycache__/*", "__pycache__/*", "*.pyc", "*/.pytest_cache/*", ".pytest_cache/*",
         "salary_data.json", "*/salary_data.json", "gmail_sync/state.json", ".DS_Store",
         "*/.DS_Store")


def _noise(rel: str) -> bool:
    return any(fnmatch.fnmatch(rel, pat) for pat in NOISE)


def own_portals(root: str = ROOT) -> list[str]:
    """The person's own job sites already in the repo (.agents/skills/<name>, committed by
    /add-portal): a later fix to one was never saved, since only /add-portal's own first
    commit ever added the folder (the stranger audit, 2026-11-03). Taken with a plain add,
    so .gitignore keeps their node_modules and logs out."""
    import personal_paths
    base = os.path.join(root, ".agents", "skills")
    try:
        names = sorted(n for n in os.listdir(base) if os.path.isdir(os.path.join(base, n)))
    except OSError:
        return []
    out = []
    for n in names:
        rel = f".agents/skills/{n}"
        if personal_paths.is_personal(rel + "/SKILL.md") and \
                _git(root, "ls-files", "--", rel).stdout.strip():
            out.append(rel)
    return out


def paths(root: str = ROOT) -> tuple[list[str], list[str]]:
    """(plain, forced): the paths that exist, relative to `root`, in the rule's order."""
    import personal_paths
    plain = [p for p in PLAIN if os.path.exists(os.path.join(root, p))] + own_portals(root)
    forced: list[str] = []
    for pat in FORCED:
        for full in sorted(glob.glob(os.path.join(glob.escape(root), pat))):
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            if os.path.isdir(full):
                for dp, dirs, files in os.walk(full):
                    dirs[:] = sorted(d for d in dirs if d not in ("__pycache__", ".pytest_cache"))
                    for f in sorted(files):
                        r = os.path.relpath(os.path.join(dp, f), root).replace(os.sep, "/")
                        if not _noise(r):
                            forced.append(r)
            elif not _noise(rel) and personal_paths.is_personal(rel):
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
    # A folder taken whole (PLAIN) has its removals staged by its own plain add.
    return [p for p in dict.fromkeys(r.stdout.split("\0")) if p and _under(p)
            and not any(p.startswith(d + "/") for d in PLAIN)]


def _would_add(root: str, *args: str) -> list[str]:
    """The files `git add <args>` would stage, asked with --dry-run, so nothing is staged;
    a name with an accent comes back as it is (core.quotePath off)."""
    got = _git(root, "-c", "core.quotePath=false", "add", "-n", *args).stdout
    return [ln[5:-1] for ln in got.splitlines() if ln.startswith("add '") and ln.endswith("'")]


def plain_files(root: str = ROOT, plain: list[str] | None = None) -> list[str]:
    """Each file the plain add of the person's folders would take, by name. --list said
    "add documents" for the whole folder, so a helper looking for the brief's record there
    found no line and added it by hand, though a save takes it (2026-11-04)."""
    plain = paths(root)[0] if plain is None else plain
    return _would_add(root, "--", *plain) if plain else []


def unsaved(root: str = ROOT) -> list[str]:
    """What this checkout holds of the person's that no commit holds yet: what a save would
    stage (asked with git add --dry-run, so nothing is staged), what is staged already, and
    what was taken away. [] when nothing waits."""
    plain, forced = paths(root)
    out: list[str] = plain_files(root, plain)
    for i in range(0, len(forced), 200):
        out += _would_add(root, "-f", "--", *forced[i:i + 200])
    out += gone(root)
    out += _git(root, "diff", "--cached", "--name-only").stdout.split()
    return list(dict.fromkeys(out))


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
        taken = plain_files(root, plain)
        for p in taken:
            print(f"add     {p}")
        for p in forced:
            print(f"add -f  {p}")
        for p in removed:
            print(f"remove  {p}")
        print(f"save_state: {len(taken)} new or changed in {', '.join(plain) or 'no folder'}, "
              f"{len(forced)} forced, {len(removed)} removed; nothing staged (--list)")
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
    if staged:
        print(LAND)
    return 0


# What follows: one command lands it, in the background, so the chat that answers the page
# is never held by the check (it was, for minutes, 2026-10-29), and a landing is one step,
# not fourteen (2026-11-03).
LAND = ("save_state: landing is one command, python3 tools/land.py --message \"<what changed>\", "
        "run in the background (Bash run_in_background) once the answer is out: it commits, "
        "merges master, runs the check, pushes, and prints the calls left. While it runs the "
        "page says \"Saving your work\" (app.py busy; the app skill, step 5).")


if __name__ == "__main__":
    sys.exit(main())
