"""A contact's next step reads plainly and counts what the engine counts.

The line the app wrote while a thread waited on a reply read "Follow up if no reply (1 of 2 sent;
your rule: 14 days, at most 2 with no reply)", and stayed on a row whose own count was 2 (the
audit of 2026-11-10, DW-5). It now says when the last message went and how many follow-ups are
left, from the engine's own count (`_chases`, each message once), and at the limit it says what
the page says. The older wordings are still read as the app's own, so a later run rewrites them.
Every person is invented.
"""
from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import app_model  # noqa: E402
import schema  # noqa: E402
import state  # noqa: E402

CID = "quayside_foods_ivo"


@pytest.fixture(autouse=True)
def _in_the_stories_year(monkeypatch):
    """The line names a day's year only when it is not the person's own year
    (state._day_said): every story here is in 2026, so their day is held there whatever the
    computer's clock says (the everywhere check, "400-days")."""
    monkeypatch.setenv("LJS_TODAY", "2026-11-11")


def _out(day, text, scenario="nudge"):
    return {"contact_id": CID, "date": day, "direction": "out", "channel": "message",
            "scenario": scenario, "summary": "sent", "full_text": text}


ROW = {"contact_id": CID, "name": "Ivo Marsh", "status": "awaiting_reply"}
NOTE = _out("2026-10-22", "Hi Ivo, I'd love to hear what the planning team is working on.",
            "first_message")
NUDGE = _out("2026-11-05", "Hi Ivo, a quick follow-up to my note from October.")


def test_the_line_says_when_it_went_and_what_is_left_from_the_engines_count():
    action, due = state.follow_up_plan(ROW, [NOTE])
    assert action == "Sent 22 Oct, no reply yet: follow up after 6 working days (one left), then stop", action
    assert due
    action, due = state.follow_up_plan(ROW, [NOTE, NUDGE])
    assert state._chases([NOTE, NUDGE]) == 2
    assert action == "No reply to 2 messages: leave it unless they write back" and due == ""
    assert state.STOP_LINE.match(action) and state._APP_ACTION.fullmatch(action)
    # The page says it as it is.
    assert app_model.plain_action(action) == action


def test_a_persons_own_limit_is_counted_down(monkeypatch):
    monkeypatch.setattr(schema, "MAX_UNANSWERED", 3)
    monkeypatch.setattr(schema, "MAX_NUDGES", 2)
    action, _due = state.follow_up_plan(ROW, [NOTE])
    assert action == "Sent 22 Oct, no reply yet: follow up after 6 working days (two left), then stop", action
    action, _due = state.follow_up_plan(ROW, [NOTE, NUDGE])
    assert action == "Sent 5 Nov, no reply yet: follow up after 6 working days (one left), then stop", action


def test_the_older_wordings_are_still_the_apps_own():
    for old in ("One nudge if no reply", state.NUDGED_STOP,
                "Follow up if no reply (1 of 2 sent; your rule: 14 days, at most 2 with no reply)",
                "No more follow-ups: 2 messages with no reply, your rule's limit (14 days, at most "
                "2 with no reply)"):
        assert state._APP_ACTION.fullmatch(old), old
    contact = dict(ROW, next_action="One nudge if no reply", next_action_due="2026-10-30")
    state.write_follow_ups([contact], [NOTE], "2026-10-24")
    assert contact["next_action"].startswith("Sent 22 Oct, no reply yet"), contact
