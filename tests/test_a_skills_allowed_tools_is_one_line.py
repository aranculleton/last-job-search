"""A skill's `allowed-tools` is one line. An edit made on GitHub broke the app skill's list
over two lines, and every tool after the break (starting, archiving and messaging chats)
asked the person again on each call (the maintainer, 2026-11-09)."""
from __future__ import annotations

import glob
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_every_skills_allowed_tools_is_on_one_line():
    bad = []
    for path in glob.glob(os.path.join(ROOT, ".claude", "skills", "*", "SKILL.md")):
        lines = open(path, encoding="utf-8").read().split("\n")
        if not lines or lines[0].strip() != "---":
            continue
        end = lines.index("---", 1) if "---" in lines[1:] else len(lines)
        for i in range(1, end):
            if lines[i].startswith("allowed-tools:") and i + 1 < end and \
                    lines[i + 1][:1] in (" ", "\t") and ":" not in lines[i + 1].split("(")[0]:
                bad.append(os.path.relpath(path, ROOT))
    assert bad == [], bad
