"""A computer the person's own list shows on is never said to be off or gone.

The maintainer's copy, 2026-11-11: a Mac connection set up at 12:42 that day showed as active,
but the work for it said the Mac was off and "nothing in the cloud can start it": the computer's
last check-in, 11:50 the day before, was all that was read. Its state took a check-in older than
a day for gone before it looked at the list, and a chat that cannot start a chat there said the
computer was off. Every computer here is invented.
"""
from __future__ import annotations

import datetime as dt
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import computer  # noqa: E402
from test_a_computer_chat_is_seen_to_its_end import T, _as, _starter  # noqa: E402
from test_a_tick_on_the_page_is_applied_once import _db, _w  # noqa: E402
from test_the_computer_side_just_works import BRIDGE  # noqa: E402

OFF_WORDS = (computer.SAY["off"], computer.SAY["gone"])


def _stale(db: dict, days: float) -> dict:
    seen = (T - dt.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    db.setdefault("chats", {})[computer.BEAT_PREFIX + "studio"] = {
        "data": {"kind": "computer", "computer": "Studio Laptop", "seen_at": seen}, "version": 1}
    return db


def test_a_check_in_over_a_week_old_is_not_gone_while_the_list_shows_the_computer_on():
    db = _stale(_db(("network~read~1", _w("network", to="computer", title="Reading one profile"))), 8)
    assert computer.state(db, T, envs=BRIDGE)["state"] not in ("gone", "off", "no_bridge")
    # With no list, or a list without it, the old check-in still says so.
    assert computer.state(db, T)["state"] == "gone"
    assert computer.state(db, T, envs={"environments": []})["state"] == "gone"


def test_a_chat_that_cannot_start_one_rings_the_starter_for_a_computer_that_is_on(tmp_path, monkeypatch):
    _as(monkeypatch, "cloud", tmp_path)
    db = _stale(dict(_db(("network~read~1", _w("network", to="computer", title="Reading one profile"))),
                     **_starter()), 1.2)
    got = computer.route(db, T, chat="session_helper", envs=BRIDGE, tools=[])
    assert got["route"] == "ring starter", got


def test_with_no_starter_and_no_way_to_start_one_the_computer_is_said_to_be_on(tmp_path, monkeypatch):
    _as(monkeypatch, "cloud", tmp_path)
    db = _stale(_db(("network~read~1", _w("network", to="computer", title="Reading one profile"))), 1.2)
    got = computer.route(db, T, chat="session_helper", envs=BRIDGE, tools=[])
    assert got["line"] not in OFF_WORDS and "Studio Laptop" in got["line"], got
    assert "create_session" in got.get("then", ""), got
