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


def test_the_rule_and_the_handover_step_say_the_same():
    text = _read("MAINTAINING.md")
    assert "**The maintainer's notes are the only work.**" in text
    assert "with none, it\n  builds nothing" in text
    assert "never a list of work: no \"do first\" and no to-do heading" in text


def test_the_handover_is_background_with_no_list_of_work():
    note = _read("docs/NEXT_BUILDER.md")
    headings = re.findall(r"^#+\s*(.+)$", note, flags=re.M)
    for heading in headings:
        assert not re.search(r"\b(do first|to ?do|next steps|fix first|start with)\b",
                             heading, flags=re.I), heading
    assert "background" in note.split("\n## ", 1)[0]
