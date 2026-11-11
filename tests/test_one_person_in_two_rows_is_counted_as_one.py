"""Someone kept on two rows, closed as the same person, is counted as one person.

When a row is closed as the duplicate of another (`state.py same-person`), its messages stay
under its own id. The page showed both rows' messages on the kept card, but the counts read each
row's half: a note under one row and a follow-up under the other read as one unanswered message
each, and a third went (the audit of 2026-11-10, NW-15). The limits now read the two as one
thread. Every person and employer is invented.
"""
from __future__ import annotations

import datetime
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import state  # noqa: E402

TODAY = datetime.date(2026, 10, 20)


def _book():
    contacts = [{"contact_id": "quayside_foods_ivo", "name": "Ivo Marsh", "company": "Quayside Foods",
                 "status": "awaiting_reply", "next_action": "", "next_action_due": ""},
                {"contact_id": "ivo", "name": "Ivo Marsh", "company": "", "status": "closed",
                 "outcome": "duplicate of quayside_foods_ivo", "next_action": "",
                 "next_action_due": ""}]
    threads = [{"contact_id": "quayside_foods_ivo", "date": "2026-09-01", "direction": "out",
                "channel": "connection", "scenario": "connection_note", "summary": "First note sent",
                "full_text": "Hi Ivo, I'd love to hear what the planning team is working on."},
               {"contact_id": "ivo", "date": "2026-09-14", "direction": "out", "channel": "message",
                "scenario": "nudge", "summary": "Nudge sent (message)",
                "full_text": "Hi Ivo, a quick follow-up to my note from earlier this month."}]
    return contacts, threads


def test_a_follow_up_logged_under_the_closed_row_counts_on_the_kept_one():
    contacts, threads = _book()
    owed = [i for i in state.owed(contacts, threads, TODAY) if i["contact_id"] == "quayside_foods_ivo"]
    assert owed == [], owed
    state.write_follow_ups(contacts, threads, TODAY)
    assert state.STOP_LINE.match(contacts[0]["next_action"]) and not contacts[0]["next_action_due"], \
        contacts[0]
    index = state.pooled(state.by_contact(threads), contacts)
    assert len(index["quayside_foods_ivo"]) == 2
    assert state.pooled(index, contacts) == index           # pooled twice is pooled once


def test_a_note_saying_not_a_duplicate_pools_nothing():
    """The review of 2026-11-11: "not a duplicate of <id>" in a note was read as one, and the
    other person's reply made this one's two unanswered messages read as one. Only the outcome
    `state.py same-person` writes pools a thread, and a "not a/isn't a duplicate of" is never one."""
    contacts = [{"contact_id": "kestrel_su", "name": "Ana Su", "company": "Kestrel Mutual",
                 "status": "awaiting_reply", "next_action": "", "next_action_due": ""},
                {"contact_id": "fernhill_su", "name": "Ana Su", "company": "Fernhill Freight",
                 "status": "closed", "notes": "Checked: not a duplicate of kestrel_su, another "
                 "person at Fernhill", "next_action": "", "next_action_due": ""}]
    threads = [{"contact_id": "kestrel_su", "date": "2026-10-01", "direction": "out",
                "channel": "message", "scenario": "first_message", "summary": "",
                "full_text": "Hi Ana, I'd love to hear what the pricing team is working on."},
               {"contact_id": "fernhill_su", "date": "2026-10-10", "direction": "in",
                "channel": "message", "scenario": "reply", "summary": "",
                "full_text": "Thanks, but I'm leaving Fernhill at the end of the month."},
               {"contact_id": "kestrel_su", "date": "2026-10-20", "direction": "out",
                "channel": "message", "scenario": "nudge", "summary": "",
                "full_text": "Hi Ana, a quick follow-up to my note from October."}]
    assert state.duplicate_of(contacts) == {}
    for said in ("isn't a duplicate of kestrel_su", "is not the same person as kestrel_su"):
        contacts[1]["notes"] = said
        assert state.duplicate_of(contacts) == {}, said
    # A free note saying it is the same person is shown together on the page, never pooled.
    contacts[1]["notes"] = "same person as kestrel_su, I think"
    assert state.pooled(state.by_contact(threads), contacts)["kestrel_su"] == \
        state.threads_for(threads, "kestrel_su")
    state.write_follow_ups(contacts, threads, "2026-11-11")
    assert contacts[0]["next_action"] == state.FOLLOW_UP_STOP.format(n=2, s="s"), contacts[0]
