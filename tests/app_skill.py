"""The app skill's own text, all of it, for a test that checks what it says.

The skill is split so a ring loads only what it needs (the efficiency audit, E-3): SKILL.md is
what the listener carries (the inbox and step 0, the rules that hold everywhere, and which
file holds the rest); wake.md the subagent's steps 1 to 3 and 5; work.md step 4's table, whose
one row `wake` prints; chat.md a message in the page's chat; jobs.md big jobs and the daily
tidy. A test that checks a rule is still said reads them together, in that order.
"""
from __future__ import annotations

import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = os.path.join(ROOT, ".claude", "skills", "app")
FILES = ("SKILL.md", "wake.md", "work.md", "chat.md", "jobs.md")


def read(name: str) -> str:
    with open(os.path.join(DIR, name), encoding="utf-8") as fh:
        return fh.read()


def text() -> str:
    """Every file of the skill, in order."""
    return "\n".join(read(n) for n in FILES)
