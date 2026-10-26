"""One rule takes a requisition number off a role: doc_name.role_core, which names the
files, the folder lookup and the copies sent alike.

Three rules disagreed: `outreach.without_ref("Data Analyst - REQ-2026-0412")` gave "Data
Analyst - REQ-2026", and `shown` left "Planner - REQ-20931" and "(Job ID: 88231)" on a
role, while the file names had neither, so a folder named without the number was looked
for under another name (the drafting audit, 2026-10-25). The roles are invented.
"""
from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import doc_name  # noqa: E402
import outreach  # noqa: E402
import shown  # noqa: E402


@pytest.mark.parametrize("title,core", [
    ("Data Analyst - REQ-2026-0412", "Data Analyst"),
    ("Planner - REQ-20931", "Planner"),
    ("Pricing Analyst (Job ID: 88231)", "Pricing Analyst"),
    ("Data Scientist II (R_1506034)", "Data Scientist II"),
    ("Analyst [JR166447]", "Analyst"),
    ("Analyst (Level 2)", "Analyst (Level 2)"),
    ("Analyst (Remote)", "Analyst (Remote)"),
])
def test_every_place_takes_the_same_number_off(title, core):
    assert doc_name.role_core(title) == core
    assert outreach.without_ref(title) == core
    assert shown._role_shown("Fernhill Freight", title, []) == core


def test_two_roles_told_apart_only_by_their_number_keep_it():
    rows = [{"company": "Fernhill Freight", "role": r}
            for r in ("Planner - REQ-20931", "Planner - REQ-20944")]
    assert shown._role_shown("Fernhill Freight", "Planner - REQ-20931", rows) == \
        "Planner - REQ-20931"
