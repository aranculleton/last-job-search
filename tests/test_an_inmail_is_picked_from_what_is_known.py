"""The InMail chooser picks only from what is already known, and never asks for a click.

A run on 2026-11-09 was told two people were worth an InMail "once their message window is
checked", and checking it meant opening that window on LinkedIn, a click no chat makes: it
left them connection notes after all. Someone whose window nobody has seen (no reading
holds it, the person has not said) keeps the connection note, and the pick says nothing
about opening anything. Every person here is invented.
"""
from __future__ import annotations

import datetime
import inspect
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import inmail_pick  # noqa: E402
import reading  # noqa: E402
import state  # noqa: E402


def test_only_people_whose_window_is_known_are_weighed(monkeypatch):
    rows = [{"contact_id": c, "name": c, "company": "Kestrel Mutual", "title": "Talent Partner",
             "status": "not_contacted"} for c in ("unseen", "said_credits", "said_free")]
    windows = {"said_credits": {"message_window": {"answer": "credits"}},
               "said_free": {"message_window": {"answer": "free"}}}
    seen = {}
    monkeypatch.setattr(state, "load_contacts", lambda *a, **k: rows)
    monkeypatch.setattr(state, "load_threads", lambda *a, **k: [])
    monkeypatch.setattr(state, "platform_budget", lambda *a, **k: {
        "inmails_left": 5, "queued_unsent": {"inmail": 0}})
    monkeypatch.setattr(reading, "load", lambda cid: windows.get(cid))

    def choose(people, readings, **kw):
        seen["ids"] = [p["contact_id"] for p in people]
        return []
    monkeypatch.setattr(inmail_pick, "choose", choose)
    inmail_pick.pick(["unseen", "said_credits", "said_free"], datetime.date(2026, 11, 9))
    assert seen["ids"] == ["said_credits", "said_free"]
    assert not inmail_pick.window_known({})
    assert inmail_pick.window_known(windows["said_free"])


def test_the_pick_never_tells_a_chat_to_open_the_window():
    src = inspect.getsource(inmail_pick.main)
    assert "--message-check" not in src and "extractor" not in src
