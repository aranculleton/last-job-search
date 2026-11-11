"""A closed, gone-cold or set-aside contact owes nothing, and no list says it is due.

The 2026-11-10 audit (NW-7) found `open_actions.py` printing contacts the person had closed with
a DUE date, among them "No more follow-ups ... DUE" and "Send now: connection note DUE" on rows
closed weeks before, while `state.owed` skipped them: two views disagreeing about who is owed.
Setting a closed status left the old next action and its date on the row, and nothing raised
the rows that kept one (PD-14). Every person and employer is invented.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import open_actions  # noqa: E402
import state  # noqa: E402

TODAY = "2026-11-10"


def _book():
    closed = {"contact_id": "quayside_foods_ivo", "name": "Ivo Marsh", "company": "Quayside Foods",
              "status": "closed", "next_action": "Send now: connection note",
              "next_action_due": "2026-10-17"}
    cold = {"contact_id": "quayside_foods_tamsin", "name": "Tamsin Ure", "company": "Quayside Foods",
            "status": "gone_cold", "next_action": state.NUDGED_STOP,
            "next_action_due": "2026-11-04"}
    live = {"contact_id": "quayside_foods_bryn", "name": "Bryn Okafor", "company": "Quayside Foods",
            "status": "in_conversation", "next_action": "Send the deck they asked for",
            "next_action_due": "2026-11-08"}
    return [closed, cold, live]


def test_a_closed_contact_is_never_listed_as_due():
    text = open_actions.render(open_actions.build(_book(), [], [], TODAY), TODAY)
    assert "Bryn Okafor" in text and "**DUE 2026-11-08**" in text, text
    for line in text.splitlines():
        if "Ivo Marsh" in line or "Tamsin Ure" in line:
            assert "DUE" not in line and "[closed]" not in line and "[gone_cold]" not in line, line
    assert "also here: Ivo Marsh, Tamsin Ure" in text, text


def test_closing_a_contact_takes_its_next_action_and_date_off():
    book = _book()
    book[2]["status"] = "awaiting_reply"
    state.set_contact(book, [], "quayside_foods_bryn", status="closed", today=TODAY)
    assert book[2]["next_action"] == "" and book[2]["next_action_due"] == "", book[2]
    # Closed with a next action given in the same breath: that one stands, with no date.
    state.set_contact(book, [], "quayside_foods_bryn", status="gone_cold",
                      next_action="Ask again in the new year", today=TODAY)
    assert book[2]["next_action"] == "Ask again in the new year", book[2]


def test_reconcile_raises_a_closed_row_that_still_carries_a_date():
    found = [p for p in state.reconcile(_book(), []) if p["reason"] == "closed_with_a_date"]
    assert sorted(p["contact_id"] for p in found) == ["quayside_foods_ivo", "quayside_foods_tamsin"]
    assert "state.py set quayside_foods_ivo --due \"\"" in found[0]["detail"] or \
        "state.py set quayside_foods_ivo --due \"\"" in found[1]["detail"], found
