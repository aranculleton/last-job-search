"""A reply in a live thread loads no skill: `reply.py prepare` prints what it needs.

The efficiency audit of 2026-11-10 (E-4) measured a reply job loading the whole networking
skill, about 72,000 characters, of which discovery, composition and the pipeline (about 52,000)
a reply never uses: `reply.py prepare` prints the scenario, the guidance, the thread and the
person's own rules, and `reply.py finish` holds the checks. Like the follow-ups, a reply now
loads no skill, and every rule keeps its home (tests/test_core_rules_have_a_home.py).
"""
from __future__ import annotations

import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL = ".claude/skills/networking/SKILL.md"


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


def test_the_page_sends_a_reply_to_reply_alone():
    # Step 4's table, where every kind of work's row is kept (the app skill in parts, E-3).
    rows = [r for r in _read(".claude/skills/app/work.md").splitlines() if r.startswith("| ")]
    reply = [r for r in rows if re.match(r"\|\s*reply\s*\|", r)]
    assert len(reply) == 1, "a row of its own for a reply"
    assert "/reply" in reply[0] and "the networking skill" not in reply[0], reply[0]
    assert "No skill is loaded" in reply[0], reply[0]
    network = [r for r in rows if re.match(r"\|\s*network\s*\|", r)]
    assert network and "the networking skill" in network[0]


def test_nothing_else_sends_a_reply_to_the_networking_skill():
    readers = json.loads(_read("docs/rule_map.json"))["readers"]
    assert SKILL not in readers["/reply"]["files"], readers["/reply"]
    head = _read(SKILL).split("---")[1]
    assert "/reply" not in head and "draft a reply" not in head, head
    assert "No skill is loaded" in _read(".claude/commands/reply.md")
    row = next(r for r in _read("CLAUDE.md").splitlines() if r.startswith("| Networking"))
    assert "/reply" not in row, row


def test_the_runbook_and_the_app_skill_send_a_reply_to_no_skill():
    """The review of 2026-11-11: RUNBOOK.md's map still listed /reply under the networking skill,
    called it one of the skill's actions, and the app skill named the skill beside reply.py
    finish."""
    runbook = _read("RUNBOOK.md")
    start = runbook.index("## Commands and skills: what routes where")
    section = runbook[start:runbook.index("\n## ", start + 10)]
    row = next(r for r in section.splitlines() if r.startswith("| `networking` |"))
    assert "/reply" not in row, row
    assert "`/reply`" in section and "no skill" in section
    assert "`/reply`, `/threads` and" not in section
    app = "\n".join(_read(os.path.join(".claude", "skills", "app", f))
                    for f in os.listdir(os.path.join(ROOT, ".claude", "skills", "app"))
                    if f.endswith(".md"))
    assert "`reply.py finish`, the networking skill" not in app
