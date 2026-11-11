"""A message is checked against its limit when it is logged, and an Open Profile message is one
of its own, never a follow-up.

The audit of 2026-11-10 (NW-21) found twelve rows logged as follow-ups ("nudge") of 600 to 700
characters, over the 280 a follow-up keeps to: messages to an Open Profile, logged as chases, and
nothing checked them when they were logged (PD-19). Every person and employer is invented.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import schema  # noqa: E402
import state  # noqa: E402

CID = "quayside_foods_ivo"
TODAY = "2026-11-10"
LONG = ("Hi Ivo, I hope this finds you well. " + "I build forecasting models for stock and "
        "transport, and I have spent four years on the planning side of food supply chains. " * 6)


def _book():
    contacts = [{"contact_id": CID, "name": "Ivo Marsh", "company": "Quayside Foods",
                 "status": "awaiting_reply", "next_action": "", "next_action_due": ""}]
    threads = [{"contact_id": CID, "date": "2026-10-01", "direction": "out",
                "channel": "connection", "scenario": "connection_note",
                "summary": "First note sent", "full_text": "Hi Ivo, I'd love to hear about the team."}]
    return contacts, threads


def test_an_open_profile_message_logs_under_its_own_name():
    contacts, threads = _book()
    got = state.followed_up(contacts, threads, CID, TODAY, text=LONG, channel="open_profile",
                            kind="message")
    assert got["row"]["scenario"] == "open_profile", got["row"]
    assert "over" not in got["said"], got["said"]
    assert state._chases(state.threads_for(threads, CID)) == 2


def test_a_follow_up_over_its_limit_is_said_when_logged_and_raised_after():
    contacts, threads = _book()
    got = state.followed_up(contacts, threads, CID, TODAY, text=LONG, kind="nudge")
    assert got["row"]["scenario"] == "nudge"
    assert f"over the {schema.LIMITS['nudge_chars']}" in got["said"], got["said"]
    found = [p for p in state.reconcile(contacts, threads) if p["reason"] == "nudge_over_limit"]
    assert [p["contact_id"] for p in found] == [CID], found


def test_an_open_profile_message_past_the_limit_is_said_like_any_follow_up():
    """The review of 2026-11-11: logged as an Open Profile message, a third unanswered message
    was logged with nothing said; it counts as a message with no reply, so it is said."""
    contacts, threads = _book()
    state.followed_up(contacts, threads, CID, "2026-10-20", kind="nudge",
                      text="Hi Ivo, a quick follow-up to my note from October.")
    got = state.followed_up(contacts, threads, CID, TODAY, text=LONG, channel="open_profile",
                            kind="message")
    assert got["row"]["scenario"] == "open_profile"
    assert "the rule is" in got["said"] and "over the" not in got["said"], got["said"]
