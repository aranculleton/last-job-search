"""A pick held for the person's answer is named when its batch is assembled, never left out.

On 2026-11-10 a pick staged and held (its posting had been ruled out before, so staging asked
whether to draft it anyway) was missing from what assembling the batch reported: it was in
held.json, which assembling never read, so the batch said nothing about it. Invented employers.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import stage_picks  # noqa: E402


def test_a_held_pick_is_reported_with_its_question(tmp_path):
    (tmp_path / "picks.json").write_text("[]")
    (tmp_path / "held.json").write_text(json.dumps([
        {"company": "Quayside Foods", "role": "Analyst", "slug": "quayside",
         "hold": [{"id": "ruled_out", "question": "This was ruled out before. Still want it drafted?"}]}]))
    drafts, missing, rejected = stage_picks.assemble(str(tmp_path))
    assert drafts == [] and rejected == []
    assert missing == ["Quayside Foods (waiting on the person's answer: This was ruled out before. "
                       "Still want it drafted?)"], missing
    # Only the roles asked for, as with the rest.
    assert stage_picks.assemble(str(tmp_path), only=())[1] == missing
