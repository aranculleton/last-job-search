#!/usr/bin/env python3
"""Is this person already set up? Asked by a chat that has just arrived in their copy.

A chat on the person's own computer, opened after a cloud chat had already built the
profile and the brief and was drafting, asked them for a resume all over again
(2026-10-25). The profile was there, on another chat's branch not yet on master, and
nothing looked. So before a new chat runs /setup it asks this, and only an empty copy,
with no profile anywhere, is set up:

    python3 tools/setup_state.py          the state, then the one line to say

    ready             a profile is here                      -> ask nothing, carry on
    ready-elsewhere   a finished profile is on another chat's branch (not yet on master)
                                                             -> ask nothing, carry on
    running           a setup is under way in another chat   -> start nothing, say so
    unfinished        a setup was left part-way on a branch  -> /setup carries it on
    none              no profile anywhere                    -> run /setup

Exit 0 for ready and ready-elsewhere, 3 for running, 4 for unfinished and none.

"Under way" is the marker /setup keeps while it runs (`profile/.setup_running`, removed
when it ends), or a branch holding part of a profile that was pushed to within the
last RECENT_HOURS. A part-profile older than that was left, and /setup carries it on.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# What a finished setup has written. person.json comes first and CLAUDE.md near the end
# (/setup Step 3), so a branch with the first and not the last is a setup part-way.
DONE_FILES = ("profile/person.json", "profile/01-candidate-profile.md", "profile/CLAUDE.md")
MARKER = "profile/.setup_running"
RECENT_HOURS = 3

SAY = {
    "ready": "Your search is ready on this computer. I can read LinkedIn in your browser "
             "whenever you ask.",
    "ready-elsewhere": "Your search is ready on this computer. I can read LinkedIn in your "
                       "browser whenever you ask.",
    "running": "Your setup is still running in your other chat. Let it finish there; this "
               "chat is ready once it has.",
    "unfinished": "Your setup was started but not finished. I'll carry it on from where it "
                  "stopped.",
    "none": "",
}
EXIT = {"ready": 0, "ready-elsewhere": 0, "running": 3, "unfinished": 4, "none": 4}


def _git(*args, root=ROOT, timeout=60):
    try:
        p = subprocess.run(["git", "-C", root, *args], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout,
                           stdin=subprocess.DEVNULL,
                           env=dict(os.environ, GIT_TERMINAL_PROMPT="0",
                                    GCM_INTERACTIVE="never"))
    except (OSError, subprocess.TimeoutExpired):
        return 1, ""
    return p.returncode, p.stdout


def _files(ref: str, root=ROOT) -> set:
    code, out = _git("ls-tree", "-r", "--name-only", ref, "--", "profile/", root=root)
    return set(out.split("\n")) - {""} if code == 0 else set()


def _age_hours(ref: str, root=ROOT, now=None) -> float:
    code, out = _git("log", "-1", "--format=%ct", ref, root=root)
    try:
        return ((now or time.time()) - int(out.strip())) / 3600
    except ValueError:
        return float("inf")


def judge(files: set, age_hours: float) -> str:
    """What a branch's profile files say: ready, running, unfinished or none."""
    if not any(f.startswith("profile/") for f in files):
        return "none"
    if MARKER in files:
        return "running"
    if all(f in files for f in DONE_FILES):
        return "ready"
    return "running" if age_hours < RECENT_HOURS else "unfinished"


def state(root=ROOT, fetch=True, now=None) -> tuple[str, str]:
    """(state, the branch it was found on, or "")."""
    here = {os.path.relpath(os.path.join(dp, f), root).replace(os.sep, "/")
            for dp, _d, fs in os.walk(os.path.join(root, "profile")) for f in fs}
    if here:
        j = judge(here, 0 if MARKER in here else float("inf"))
        if j == "ready":
            return "ready", ""
        if j == "running":
            return "running", "this folder"
    if fetch:
        _git("fetch", "-q", "--prune", "origin", root=root, timeout=120)
    base = "origin/master"
    if _git("rev-parse", "--verify", "-q", base, root=root)[0] != 0:
        base = "origin/HEAD"
    if judge(_files(base, root), float("inf")) == "ready":
        return "ready", base
    code, out = _git("branch", "-r", "--no-merged", base, "--format=%(refname:short)", root=root)
    seen = []
    for ref in [b.strip() for b in out.splitlines() if b.strip() and not b.strip().endswith("/HEAD")]:
        j = judge(_files(ref, root), _age_hours(ref, root, now))
        if j != "none":
            seen.append((j, ref))
    for want in ("running", "ready", "unfinished"):
        for j, ref in seen:
            if j == want:
                return ("ready-elsewhere" if j == "ready" else j), ref
    if here:
        return "unfinished", "this folder"
    return "none", ""


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] in (["-h"], ["--help"]):
        print(__doc__.strip().split("\n\n")[1])
        return 0
    s, where = state(fetch="--no-fetch" not in argv)
    print(s + (f" ({where})" if where else ""))
    if SAY[s]:
        print(SAY[s])
    return EXIT[s]


if __name__ == "__main__":
    sys.exit(main())
