#!/usr/bin/env python3
"""What a CI run needs to run, decided in one place a test can hold.

    python3 tools/ci_plan.py part 2/3 [file ...]      the test files the second of three
                                                      runners takes (every tests/test_*.py
                                                      when none are named)

.github/workflows/ci.yml splits its suite across runners side by side with this, and
tools/platform_check.py splits Windows' the same way. Standard library only, and Python 3.9
(tools/python_floor.py), like every tool here.
"""
from __future__ import annotations

import os
import re
import sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TOOLS)

# ------------------------------------------------------------------ a split suite

def every_test(root: str = ROOT) -> list[str]:
    """Every test file pytest collects from tests/, as os.path.join("tests", name)."""
    tests = os.path.join(root, "tests")
    return sorted(os.path.join("tests", f) for f in os.listdir(tests)
                  if f.startswith("test_") and f.endswith(".py"))


def part(shard: str, files: list[str] | None = None, root: str = ROOT) -> list[str] | None:
    """The files one runner takes when `files` (every test file when None) are split
    ("2/3": the second of three). Each file goes, largest first, to the part with the least
    so far, so every runner splits them the same way and each file is in exactly one part.
    None for an empty or malformed shard."""
    m = re.fullmatch(r"\s*(\d+)\s*/\s*(\d+)\s*", shard or "")
    if not m or not 1 <= int(m.group(1)) <= int(m.group(2)):
        return None
    k, n = int(m.group(1)), int(m.group(2))
    files = sorted(set(files)) if files else every_test(root)
    size = {f: os.path.getsize(os.path.join(root, f)) for f in files}
    loads, mine = [0] * n, []
    for f in sorted(files, key=lambda f: (-size[f], f)):
        i = loads.index(min(loads))
        loads[i] += size[f]
        if i == k - 1:
            mine.append(f)
    return sorted(mine)


# ------------------------------------------------------------------ the command

def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["part"] and len(argv) >= 2:
        mine = part(argv[1], argv[2:] or None)
        if not mine:
            print(f"ci_plan: no part {argv[1]!r} of these files", file=sys.stderr)
            return 2
        print(" ".join(f.replace(os.sep, "/") for f in mine))
        return 0
    print("usage: python3 tools/ci_plan.py part K/N [file ...]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
