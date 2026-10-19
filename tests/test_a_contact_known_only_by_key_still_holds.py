"""A contact row with only its stored employer key is that employer, for every reader.

tools/network/state.py reads a contact row whose company name is blank by its
stored `company_key` column. The throttle skipped such a row, so a contact at
`referral_in_progress` written that way gave `referral_holds()` nothing: the one
contact state meant to stop a cold application colliding with a referral held
nothing back. Both now read the row through `company_key.row_key`.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "network"))

import company_key  # noqa: E402
import state  # noqa: E402
import throttle  # noqa: E402

ROW = {"contact_id": "shirin_example_brindlehart", "name": "Shirin Example",
       "title": "Head of Planning", "company": "", "company_key": "brindlehart",
       "status": "referral_in_progress", "next_action": "wait for HR"}


def test_a_referral_known_only_by_its_key_holds_the_employer():
    holds = throttle.referral_holds(rows=[ROW], live={})
    assert list(holds) == ["brindlehart"]
    assert "Shirin Example" in holds["brindlehart"]


def test_the_contact_book_and_the_throttle_read_a_row_the_same_way():
    for row in (ROW, {**ROW, "company": "Brindle Hart"}, {**ROW, "company_key": ""}):
        assert state.row_company_key(row) == company_key.row_key(row)
