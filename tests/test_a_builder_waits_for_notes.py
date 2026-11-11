"""A new builder chat sets up and waits for the maintainer's notes; the handover is background.

On 2026-11-04 a builder given an empty notes section started working through the last
handover's "Do first" list on its own. The maintainer: the notes passed from one builder to
the next "shouldn't automatically start fixes unless fixes are explicitly provided"; "the main
objective is just to set up and be ready for them". These pins hold the prompt, the rule and
the handover's shape, so a later handover cannot bring the to-do list back.
"""
from __future__ import annotations

import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(rel: str) -> str:
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


def _builder_prompt() -> str:
    text = _read("MAINTAINING.md")
    section = text.split("## The builder prompt", 1)[1]
    return section.split("```text", 1)[1].split("```", 1)[0]


def test_the_builder_prompt_says_set_up_and_wait():
    prompt = _builder_prompt()
    assert "tell me in one line you are ready, and wait for my notes" in prompt
    assert "build nothing until they ask for it" in prompt
    assert "Build only what my notes below ask" in prompt
    assert "never a list to start on" in prompt
    assert prompt.rstrip().endswith("My notes for this version:")


def _flat(text: str) -> str:
    # A pin holds a phrase, never where a line wraps (process audit, 2026-11-11).
    return " ".join(text.split())


def _builder_section() -> str:
    text = _read("MAINTAINING.md")
    return "## Builder\n" + text.split("\n## Builder\n", 1)[1].split("\n## ", 1)[0]


def test_the_rule_and_the_handover_step_say_the_same():
    text = _flat(_read("MAINTAINING.md"))
    assert "**The maintainer's notes are the only work.**" in text
    assert "with none, it builds nothing" in text
    assert "never a list of work: no \"do first\" and no to-do heading" in text


def test_the_handover_is_background_with_no_list_of_work():
    note = _read("docs/NEXT_BUILDER.md")
    headings = re.findall(r"^#+\s*(.+)$", note, flags=re.M)
    for heading in headings:
        assert not re.search(r"\b(do first|to ?do|next steps|fix first|start with)\b",
                             heading, flags=re.I), heading
    assert "background" in note.split("\n## ", 1)[0]


def test_a_builder_reads_one_short_section_first():
    # Before 4.15.1 the prompt named three long sections, about 8,000 tokens before the notes.
    section = _builder_section()
    assert len(section.rstrip().splitlines()) <= 120, len(section.rstrip().splitlines())
    prompt = _flat(_builder_prompt())
    assert 'read MAINTAINING.md "Builder"' in prompt
    for gone in ('"Before pushing", "Releasing"', "batch your commits"):
        assert gone not in prompt, gone
    flat = _flat(section)
    for step in ("tools/push_gate.sh", "release.py cut", "Fast checks", "origin/master",
                 "without force", "docs/NEXT_BUILDER.md"):
        assert step in flat, step


def test_the_handover_says_only_what_was_not_tested_and_what_is_red():
    note = _read("docs/NEXT_BUILDER.md")
    assert len(note.rstrip().splitlines()) <= 15, len(note.rstrip().splitlines())
    assert "decided" not in note.lower(), "a decision lives in MAINTAINING.md, never only here"


def test_the_decisions_that_hold_are_written_down_in_maintaining():
    # 4.14.0's hand-over held these two, and the next hand-over, written afresh, lost them.
    text = _read("MAINTAINING.md")
    held = _flat(text.split("\n## Decisions that hold\n", 1)[1].split("\n## ", 1)[0])
    assert "ubuntu-24.04" in held
    assert "allowed-tools" in held and "maintainer's edits" in held
    assert "fold the unpushed commits" not in _flat(text)
