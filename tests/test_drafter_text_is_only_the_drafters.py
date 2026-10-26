""""DRAFTER TEXT ON PAGE" fires on the drafter's own notes, never on ordinary prose.

The check looked for `\\bp[124]\\b` and `their (SQL|resume|\\w+ years)`, case-blind, so a
letter that said "P1 incidents", "their SQL reports" or "their two years of" failed the
batch (the drafting audit, 2026-10-25). A field's name is written in lower case, and the
candidate in the third person is their document or their years at one of their employers.

The letters' sentences are invented; the candidate is the example person.
"""
from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import audit_letters as A  # noqa: E402


@pytest.mark.parametrize("prose", [
    "The alerting I built cut P1 incidents from nine a month to two.",
    "Your depot teams and their SQL reports deserve one governed source.",
    "Larkspur has kept its service levels through their two years of growth.",
    "A p2-sized change, if any.",
    "Your planners can raise their profile with the board.",
])
def test_ordinary_prose_is_not_drafter_text(prose):
    assert A.drafter_text(prose) == ""


@pytest.mark.parametrize("note,said", [
    ("I would welcome a conversation. conceded in one sentence mid-letter in p2", "conceded"),
    ("Moved to p4 for the close.", "p4"),
    ("This leans on their CV for the dates.", "their CV"),
    ("Draws on their four years at Brindle & Hart Logistics.",
     "their four years at Brindle & Hart Logistics"),
])
def test_the_drafters_notes_are(note, said):
    assert A.drafter_text(note) == said
