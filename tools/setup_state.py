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
    unfinished        a setup stopped part-way, or this chat is the one setting up
                                                             -> /setup carries it on
    none              no profile anywhere                    -> run /setup

Exit 0 for ready and ready-elsewhere, 3 for running, 4 for unfinished and none.

    python3 tools/setup_state.py --paste  the one line a person pastes into a new chat on
                                          their computer (COMPUTER.md), naming this copy

The rule is place.setup_state(), the one /setup step 0 runs (`python3 tools/place.py
state`): this only names its answer for COMPUTER.md. It had a rule of its own, a marker
file nothing wrote and three hours where /setup said six, and the two told one person
"I'll carry it on" and "it is still going in your other chat" about the same setup
(2026-10-25). "Under way" is /setup's own mark in profile/place.json, started and not
finished, with a commit within place.STALLED_HOURS.
"""
from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import place  # noqa: E402

READY = ("Your search is ready on this computer. I can read LinkedIn in your browser "
         "whenever you ask.")
SAY = {"ready": READY, "ready-elsewhere": READY, "running": place.STILL_GOING,
       "unfinished": place.STOPPED, "none": ""}
EXIT = {"ready": 0, "ready-elsewhere": 0, "running": 3, "unfinished": 4, "none": 4}
# place.setup_state()'s states, as COMPUTER.md names them. "self" (this chat is the one
# setting up) carries on with /setup, as "unfinished" does.
STATES = {"here": "ready", "landed": "ready", "branch": "ready-elsewhere", "going": "running",
          "stopped": "unfinished", "self": "unfinished", "none": "none"}
PAGE = "https://github.com/aranculleton/last-job-search/blob/master/COMPUTER.md"


def paste(owner: str, name: str) -> str:
    """What the person pastes into the first chat on their computer: their copy and the
    page that chat follows."""
    return f"Open my job search on this computer: github.com/{owner}/{name}. Steps: {PAGE}"


def this_copy(root=ROOT) -> tuple[str, str]:
    """(owner, name) of this copy on GitHub, from its origin; ("", "") when not known."""
    import re
    code, url = _git("remote", "get-url", "origin", root=root)
    m = re.search(r"github\.com[/:]([^/]+)/([^/]+?)(?:\.git)?/?$", url.strip()) if code == 0 else None
    return (m.group(1), m.group(2)) if m else ("", "")


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


def _judged(root=None, fetch=True, now=None) -> tuple[str, str]:
    """place.setup_state()'s own (state, ref) for the copy at `root`."""
    old = place.ROOT
    place.ROOT = root or ROOT
    try:
        got = place.setup_state(now=now, fetch=fetch)
    finally:
        place.ROOT = old
    return got["state"], got.get("ref") or ""


def state(root=None, fetch=True, now=None) -> tuple[str, str]:
    """(state, where it was found, or ""), by place.setup_state()'s rule."""
    judged, ref = _judged(root, fetch, now)
    return STATES[judged], ("" if ref == "HEAD" else ref)


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] in (["-h"], ["--help"]):
        print(__doc__.strip().split("\n\n")[1])
        return 0
    if "--paste" in argv:
        owner, name = this_copy()
        if not owner:
            print("setup_state: this copy has no GitHub address to name", file=sys.stderr)
            return 1
        print(paste(owner, name))
        return 0
    judged, ref = _judged(fetch="--no-fetch" not in argv)
    s, where = STATES[judged], ("" if ref == "HEAD" else ref)
    print(s + (f" ({where})" if where else ""))
    if SAY[s] and judged != "self":          # the chat setting up has nothing to tell itself
        print(SAY[s])
    return EXIT[s]


if __name__ == "__main__":
    sys.exit(main())
