"""Work for the computer that is stuck on the person says so on their page, in one line with one
button, and nothing sends them to a chat as the way through.

The maintainer, 2026-11-11: a read was stuck on his Mac (a chat there held it, LinkedIn signed
out), the page showed it running with nothing to tap, and the chat that answers the page, with
no page action to offer, told him to go to a chat. The To do card came only for work nobody had
started; the route that hands a start to the chat that answers the page told the person so; and
the card for the chat that starts work on the computer said "open that chat" with no name and no
way there. Invented people and computers only.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import app_model  # noqa: E402
import computer  # noqa: E402
from test_a_computer_chat_is_seen_to_its_end import T, _as  # noqa: E402
from test_a_tick_on_the_page_is_applied_once import _db, _w  # noqa: E402
from test_the_computer_side_just_works import BRIDGE, _beat  # noqa: E402

WID = "network~read~1"


def _held(minutes: int, **extra) -> dict:
    at = app_model.stamp(T - dt.timedelta(minutes=minutes))
    item = _w("network", "Harbourline Bank", to="computer", title="Reading 3 profiles",
              status="running", claimed_by="session_mac1", claimed_as="computer", claimed_at=at,
              lease_until=app_model.stamp(T + dt.timedelta(minutes=20)),
              computer_session={"id": "session_mac1", "at": at})
    item.update(extra)
    return item


def test_a_read_held_on_the_computer_while_linkedin_is_signed_out_has_its_card():
    db = dict(_db((WID, _held(15))), chats=_beat(linkedin="out"))
    st = computer.state(db, T, envs=BRIDGE)
    assert st["state"] == "signed_out" and st["card"], st
    card = computer.card(st)
    # Decided 2026-11-12 (the maintainer's Mac): the one way through opens the chat on the
    # computer that holds the read, where LinkedIn's sign-in is open in its own browser; a
    # sign-in beside the page did not reach it, so no LinkedIn link is on the card.
    assert card["body"].startswith("Sign in to LinkedIn once, in the chat on your Studio "
                                   "Laptop"), card["body"]
    assert card["open"] == {"label": "Open the chat",
                            "url": "https://claude.ai/code/session_mac1"}
    assert "browser" not in card and "linkedin.com" not in json.dumps(card)
    # Just taken: the chat there gets its ten minutes to put it on the page itself.
    assert not computer.state(dict(_db((WID, _held(2))), chats=_beat(linkedin="out")), T,
                              envs=BRIDGE)["card"]
    # Held while all is well: nothing to do, no card.
    assert not computer.state(dict(_db((WID, _held(15))), chats=_beat()), T, envs=BRIDGE)["card"]


def test_a_read_waiting_on_its_own_sign_in_card_gets_no_second_card():
    asked = _held(15, status="needs_you", claimed_by=None, note="LinkedIn is signed out.",
                  needs={"question": "LinkedIn is signed out in Claude's browser.",
                         "signin": "linkedin"},
                  asked_you_at=app_model.stamp(T - dt.timedelta(minutes=12)))
    st = computer.state(dict(_db((WID, asked)), chats=_beat(linkedin="out")), T, envs=BRIDGE)
    assert not st["card"], st


def test_the_person_hears_nothing_of_chats_when_only_the_chat_that_answers_the_page_can_start_it(
        tmp_path, monkeypatch):
    _as(monkeypatch, "cloud", tmp_path)
    old = (T - dt.timedelta(days=1.2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    db = _db((WID, _w("network", to="computer", title="Reading one profile")))
    db["chats"] = {computer.BEAT_PREFIX + "studio": {
        "data": {"kind": "computer", "computer": "Studio Laptop", "seen_at": old}, "version": 1}}
    got = computer.route(db, T, chat="session_helper", envs=BRIDGE, tools=[])
    assert got["route"] == "on, start it elsewhere"
    assert "chat" not in got["line"].lower() and "Studio Laptop" in got["line"], got["line"]
    assert "create_session" in got["then"]
