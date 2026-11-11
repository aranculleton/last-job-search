"""The steps for saving say what tools/land.py does now.

Audit E-7 and its review (2026-11-11): CLAUDE.md "Saving", RUNBOOK.md step 4 and the routines'
"Landing work" told every chat to run plain land.py in the background and then make four calls,
though land.py opens and merges its pull request itself where it can (and the background run's
end woke the chat, a turn of the whole history, about $0.43 in the brief). A chat saves with
--detach, which wakes nobody; a scheduled run keeps the background run, whose end it waits for
before the run is over, and each says what an ending of "saved to master" asks.
"""
from __future__ import annotations

import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


def test_a_chat_saves_with_detach_and_the_steps_name_what_land_prints():
    core = _read("CLAUDE.md")
    saving = core.split("## Saving", 1)[1].split("\n## ", 1)[0]
    assert "tools/land.py --detach" in saving and "then the calls it prints" not in saving
    step4 = _read("RUNBOOK.md").split("2. **Finish by getting the work onto master.**", 1)[1]
    step4 = step4.split("\n## ", 1)[0]
    assert "land.py --detach" in step4 and "land: saved to master" in step4
    for rel in (("automation", "prompts", "_common.md"),):
        landing = _read(*rel).split("## Landing work", 1)[1].split("\n## ", 1)[0]
        assert "land: saved to master" in landing, rel
