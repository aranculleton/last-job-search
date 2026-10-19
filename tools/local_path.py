"""Where a person's own computer keeps the tools the app calls, put on PATH.

A chat on a Mac runs its commands in a shell that is not a login shell, so the
places a login shell adds are missing from its PATH: MacTeX's /Library/TeX/texbin
(lualatex, xelatex) and the official Bun installer's ~/.bun/bin. The tools were
installed and working, and setup_env.sh still said "still missing: lualatex xelatex",
and the place check told the person to install LaTeX they already had. A Mac should
need no profile edits for this, so every tool adds them itself: person.py, which
nearly every tool imports, calls `extend()` once.

Only directories that exist are added. Two hold nothing but the tools they are for
and go first (TeX's and Bun's); the package managers' general directories go last,
so they never shadow a Python the person chose, such as a virtual environment's.

    python3 tools/local_path.py          # what this adds here
"""
from __future__ import annotations

import glob
import os
import sys

HOME = os.path.expanduser("~")


def _found(patterns) -> list:
    out = []
    for p in patterns:
        for d in sorted(glob.glob(os.path.expanduser(p)), reverse=True):
            if os.path.isdir(d) and d not in out:
                out.append(d)
    return out


def dirs(platform: str | None = None) -> tuple[list, list]:
    """(directories to put first, directories to put last) that exist here."""
    platform = platform or sys.platform
    first = ["~/.bun/bin"]
    last = []
    if platform == "darwin":
        first += ["/Library/TeX/texbin", "~/Library/TinyTeX/bin/*"]
        last += ["/opt/homebrew/bin", "/usr/local/bin"]
    elif platform.startswith("win"):
        local = os.environ.get("LOCALAPPDATA", "~/AppData/Local")
        first += [os.path.join(local, "Programs", "MiKTeX", "miktex", "bin", "x64"),
                  r"C:\Program Files\MiKTeX\miktex\bin\x64"]
    else:
        first += ["~/.TinyTeX/bin/*"]
    first += ["/usr/local/texlive/20*/bin/*"]
    return _found(first), _found(last)


def extend(env: dict | None = None, platform: str | None = None) -> list:
    """Add the directories that exist and are missing to env["PATH"] (os.environ by
    default). Returns what was added. Never removes or reorders what was there."""
    env = os.environ if env is None else env
    have = [p for p in env.get("PATH", "").split(os.pathsep) if p]
    first, last = dirs(platform)
    add_first = [d for d in first if d not in have]
    add_last = [d for d in last if d not in have and d not in add_first]
    if add_first or add_last:
        env["PATH"] = os.pathsep.join(add_first + have + add_last)
    return add_first + add_last


if __name__ == "__main__":
    added = extend()
    print("local_path: " + (", ".join(added) if added else "nothing to add here"))
