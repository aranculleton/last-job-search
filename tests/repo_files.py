"""The repo's own files, for a test that reads across many of them.

Claude Code puts an agent's isolated checkout inside the repo, at
`.claude/worktrees/<name>/` (CLAUDE.md starts `/upgrade` in one), and a person's
repo can hold another checkout too. A recursive glob walks straight into it and
reads a whole second copy of the repo: an older version of every document and the
person's generated files. A test then fails, or passes, on files that are not this
tree. This is how a test lists files: every match inside a nested checkout (a
directory below the root holding its own `.git`) is left out.
"""
from __future__ import annotations

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
