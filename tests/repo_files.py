"""The repo's own files, for a test that reads across many of them.

Claude Code puts an agent's isolated checkout inside the repo, at
`.claude/worktrees/<name>/` (CLAUDE.md starts `/upgrade` in one), and a person's
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


def tracked(*pathspecs: str, root: Path | str = ROOT, app_only: bool = True) -> list[str]:
    """The files git tracks under `root` (matching `pathspecs`), relative, each name whole;
    with `app_only`, never a person's own file. [] where `root` is not a git checkout."""
    out = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--", *pathspecs],
                         capture_output=True, text=True)
    if out.returncode != 0:
        return []
    names = [n for n in out.stdout.split("\0") if n]
    if app_only:
        sys.path.insert(0, str(ROOT / "tools"))
        import personal_paths
        names = [n for n in names if not personal_paths.is_personal(n)]
    return names
