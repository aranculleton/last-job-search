"""A contact marked "call booked" moves on once the call's day has passed (4 November).

It kept the status after the call, and any later date set on the contact then showed in
Coming up as a call. Invented people only.
"""
from __future__ import annotations

import datetime as dt
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "network"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import app_model  # noqa: E402
import person  # noqa: E402
import state  # noqa: E402
import upcoming  # noqa: E402

TODAY = "2026-11-04"


@pytest.fixture
def where(tmp_path, monkeypatch):
    import app_state
    (tmp_path / "state").mkdir()
    prof = app_state.profile_copy(str(tmp_path / "profile"))
    monkeypatch.setenv("LJS_STATE", str(tmp_path / "state"))
    monkeypatch.setenv("LJS_PROFILE", prof)
    person.reset()
    yield tmp_path / "state"
    person.reset()


def _contact(due, status="call_booked"):
    return {"contact_id": "ada-vale", "name": "Ada Vale", "company": "Quayside Analytics",
            "status": status, "next_action": "Call on 2026-11-02 at 2pm: prepare for it",
            "next_action_due": due}


def _coming(contacts):
    ctx = types.SimpleNamespace(today=dt.date.fromisoformat(TODAY),
                                now=app_model.parse_time("2026-11-04T16:00:00Z"),
                                zone="Europe/London", names=(), contacts=contacts, tracker=[])
    return [i for i in upcoming.build(ctx) if i["kind"] == "call"]


def test_a_call_booked_for_a_day_now_past_is_not_in_coming_up(where):
    book = [_contact("2026-11-02")]
    state.move_past_calls(book, TODAY)
    assert book[0]["status"] == "in_conversation"
    assert _coming(book) == []


def test_a_later_date_on_that_contact_is_not_shown_as_a_call(where):
    book = [_contact("2026-11-02")]
    assert [i["day"] for i in _coming([_contact("2026-11-12")])] == ["2026-11-12"]  # a real booking
    row, said = state.set_contact(book, [], "ada-vale", due="2026-11-12",
                                  next_action="Follow up", today=TODAY)
    assert row["status"] == "in_conversation" and any("in_conversation" in s for s in said)
    assert _coming(book) == []
    # a call still ahead that is moved is still a call
    ahead = [_contact("2026-11-06")]
    state.set_contact(ahead, [], "ada-vale", due="2026-11-09", today=TODAY)
    assert ahead[0]["status"] == "call_booked"


def test_the_stored_status_moves_on_after_the_daily_step(where):
    path = str(where / "network_contacts.csv")
    state.save_contacts([_contact("2026-11-02"), dict(_contact("2026-11-06"), contact_id="bo")], path)
    assert state.advance_past_calls(dt.date.fromisoformat(TODAY)) == ["ada-vale"]
    got = {c["contact_id"]: c for c in state.load_contacts(path)}
    assert got["ada-vale"]["status"] == "in_conversation"
    assert got["bo"]["status"] == "call_booked"
    assert state.advance_past_calls(dt.date.fromisoformat(TODAY)) == []


def test_the_contact_is_owed_a_thank_you_after_the_call(where):
    book = [_contact("2026-11-02")]
    state.move_past_calls(book, TODAY)
    ctx = app_model.Ctx(dt.date.fromisoformat(TODAY), app_model.parse_time("2026-11-04T16:00:00Z"))
    got = app_model.standing(ctx, book[0], "ada-vale", "in_conversation", [], [], None, None, None)
    assert got["owed"]["kind"] == "thanks" and got["group"] == "now"
