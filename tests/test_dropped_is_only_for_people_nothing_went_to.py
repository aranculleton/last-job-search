""""Dropped" is a note set aside before anything went, never a conversation with words in it.

The 2026-11-10 audit (NW-13) found 22 dropped contacts with messages sent and 19 with replies,
one of them a reply offering a time for a call, with an unsent draft: dropped is one of the
statuses no list owes anything, so they appeared nowhere. Setting dropped is now refused where
the log holds a message either way, and reconcile names the rows already like that (PD-15).
Every person and employer is invented.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import pytest  # noqa: E402

import state  # noqa: E402

TODAY = "2026-11-10"
CID = "quayside_foods_ivo"


def _book(status="not_contacted"):
    return [{"contact_id": CID, "name": "Ivo Marsh", "company": "Quayside Foods",
             "status": status, "next_action": "", "next_action_due": "", "first_contacted": ""}]


THEY_WROTE = [{"contact_id": CID, "date": "2026-09-28", "direction": "in", "channel": "message",
               "scenario": "reply", "summary": "Offered a call",
               "full_text": "Happy to talk, Thursday 10 to 11 suits me.", "subject": ""}]


def test_dropping_someone_who_wrote_is_refused_both_ways():
    with pytest.raises(ValueError, match="written to|wrote"):
        state.drop(_book(), THEY_WROTE, CID, TODAY, "set aside")
    with pytest.raises(ValueError, match="written to|wrote"):
        state.set_contact(_book("in_conversation"), THEY_WROTE, CID, status="dropped", today=TODAY)
    sent = [dict(THEY_WROTE[0], direction="out", scenario="connection_note",
                 channel="connection")]
    with pytest.raises(ValueError, match="written to|wrote"):
        state.set_contact(_book("awaiting_reply"), sent, CID, status="dropped", today=TODAY)
    # Nothing either way: set aside, as ever.
    book = _book()
    state.set_contact(book, [], CID, status="dropped", today=TODAY)
    assert book[0]["status"] == "dropped"


def test_reconcile_names_a_dropped_row_with_words_in_its_thread():
    found = [p for p in state.reconcile(_book("dropped"), THEY_WROTE)
             if p["reason"] == "dropped_but_written"]
    assert [p["contact_id"] for p in found] == [CID], found
    assert "state.py set %s --status" % CID in found[0]["detail"], found
    assert not [p for p in state.reconcile(_book("dropped"), []) if p["reason"] == "dropped_but_written"]
