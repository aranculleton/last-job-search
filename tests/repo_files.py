"""The repo's own files, for a test that reads across many of them.

Claude Code puts an agent's isolated checkout inside the repo, at
`.claude/worktrees/<name>/` (a session starts `/upgrade` in one: RUNBOOK.md, "Start of a
session"), and a person's
repo can hold another checkout too. A recursive glob walks straight into it and
reads a whole second copy of the repo: an older version of every document and the
person's generated files. A test then fails, or passes, on files that are not this
tree. This is how a test lists files: every match inside a nested checkout (a
directory below the root holding its own `.git`) is left out.

`tracked()` is how a test lists what git tracks. This suite runs in a person's repo too,
where tracked files include their own notes, research and profile, which say whatever
they wrote: two tests that read every tracked file failed there on a person's notes
quoting a switch or a name. And `git ls-files` split on whitespace cut a name with a
space in two. So it reads `-z`, and leaves a person's own files out
(tools/personal_paths.py) unless a test asks for them.
"""
from __future__ import annotations

import functools
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def files(*patterns: str, root: Path | str = ROOT) -> list[Path]:
    """Every file under `root` matching any of `patterns`, outside nested checkouts."""
    root = Path(root)
    checkout: dict[Path, bool] = {}

    def nested(path: Path) -> bool:
        for parent in path.relative_to(root).parents:
            if parent == Path("."):
                return False
            d = root / parent
            if d not in checkout:
                checkout[d] = (d / ".git").exists()
            if checkout[d]:
                return True
        return False

    out = set()
    for pattern in patterns:
        out.update(p for p in root.glob(pattern) if p.is_file() and not nested(p))
    return sorted(out)


def tracked(*pathspecs: str, root: Path | str = ROOT, app_only: bool = True,
            new: bool = False) -> list[str]:
    """The files git tracks under `root` (matching `pathspecs`), relative, each name whole;
    with `app_only`, never a person's own file; with `new`, also the files not committed
    yet that no ignore rule covers (a change being tested before it is committed). []
    where `root` is not a git checkout."""
    out = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--", *pathspecs],
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    if out.returncode != 0:
        return []
    names = [n for n in out.stdout.split("\0") if n]
    if new:
        more = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--others",
                               "--exclude-standard", "--", *pathspecs],
                              capture_output=True, text=True, encoding="utf-8", errors="replace")
        names += [n for n in more.stdout.split("\0") if n and n not in names]
    if app_only:
        sys.path.insert(0, str(ROOT / "tools"))
        import personal_paths
        names = [n for n in names if not personal_paths.is_personal(n)]
    return names


# A copy's address on GitHub, for a test of what the app does with one where the checkout the
# suite runs in has none: the computer check runs this suite in a person's copy cloned from a
# folder (tools/platform_check.py), and there a big job went to a background agent rather than
# a chat of its own, and a scheduled run had no copy to fetch (2026-11-04).
ON_GITHUB = ("someone", "my-job-search")
_BOOT = ("import os, runpy, sys\n"
         "sys.argv = sys.argv[1:]\n"
         "sys.path.insert(0, os.path.dirname(os.path.abspath(sys.argv[0])))\n"
         "import app_setup, place\n"
         "app_setup.origin = lambda: {on!r}\n"
         "place.repo = lambda: {on!r}\n"
         "runpy.run_path(sys.argv[0], run_name='__main__')\n")


@functools.lru_cache(maxsize=None)
def on_github(root: Path | str = ROOT) -> bool:
    """Whether the checkout at `root` has an address on GitHub (tools/sync_app.repo_of)."""
    sys.path.insert(0, str(Path(root) / "tools"))
    import sync_app
    got = subprocess.run(["git", "-C", str(root), "remote", "get-url", "origin"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    return got.returncode == 0 and sync_app.repo_of(got.stdout) != ("", "")


def python_on_github(script: str) -> list[str]:
    """The command that runs one of the app's tools: [python, script] where this checkout has
    an address on GitHub, and where it has none, the same tool told ON_GITHUB is its address."""
    if on_github():
        return [sys.executable, script]
    return [sys.executable, "-c", _BOOT.format(on=ON_GITHUB), script]
