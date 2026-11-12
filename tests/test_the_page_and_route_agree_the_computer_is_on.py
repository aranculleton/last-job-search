"""The page's own model and `route` agree that a computer the person's list shows is on, and the
words for a computer that is on never send anyone nowhere.

From a review of 4.15.1's branch (2026-11-11): the page is built through `computer.seen`, which
read the check-in alone, so a check-in three hours old drew "off" and eight days "gone", with a
To do card to set it up again, while `route` at the same moment treated the Mac as on and rang
the starter (finding 2). Tool names were matched bare, so a chat passing
`mcp__claude-code-remote__create_session` was told it had none, and the starter itself could be
told to hand its work to another chat, which its rules forbid (finding 5). A computer with no
name was "your your computer" (finding 7). Every computer here is invented.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import app_model  # noqa: E402
import computer  # noqa: E402
from test_a_computer_chat_is_seen_to_its_end import T, _as  # noqa: E402
from test_a_tick_on_the_page_is_applied_once import Search, _db, _w  # noqa: E402
from test_the_computer_side_just_works import BRIDGE  # noqa: E402

WORK = ("network~read~1", _w("network", to="computer", title="Reading one profile"))


def _with(hours: float, kept_hours_ago: float | None, name: str = "Studio Laptop") -> dict:
    db = _db(WORK)
    beat = computer.beat_fields(name, T - dt.timedelta(hours=hours), task=False)
    db["chats"] = {computer.beat_id(name): {"data": beat, "version": 1}}
    if kept_hours_ago is not None:
        db["meta"] = {"computer_envs": {"data": {
            "at": app_model.stamp(T - dt.timedelta(hours=kept_hours_ago)),
            "environments": computer._listed_bridges(BRIDGE)}, "version": 1}}
    return db


@pytest.mark.parametrize("hours", [3, 8 * 24])
def test_the_page_model_says_on_while_route_rings_the_starter(tmp_path, monkeypatch, hours):
    import person
    s = Search(str(tmp_path))
    monkeypatch.setenv(person.ENV, s.profile)
    monkeypatch.setenv(person.STATE_ENV, s.state)
    person._modules.clear()
    person._data.clear()
    _as(monkeypatch, "cloud", tmp_path)
    monkeypatch.setattr(computer, "_works_on", lambda: "computer")
    db = _with(hours, kept_hours_ago=1)
    db["meta"]["computer_starter"] = {"data": {"chat": "session_starter",
                                               "bell": "https://claude.ai/artifact/bell-1",
                                               "made_at": "2026-10-20T08:00:00Z"}, "version": 3}
    # The helper routes with the person's list: it rings the starter, the computer being on.
    assert computer.route(db, T, chat="session_helper", tools=["create_session"])["route"] == \
        "ring starter"
    # The page, built from the same database at the same moment, says the same.
    st = computer.seen(db, T)
    model, _ = app_model.build(T.date(), T, only=("where",), computer=st)
    row = model["where"]["computer"]
    assert row["state"] not in ("off", "gone", "no_bridge"), row
    assert computer.SAY["off"] not in row["say"] and computer.SAY["gone"] not in row["say"]
    assert computer.card(st) is None
    person._modules.clear()
    person._data.clear()


def test_full_tool_names_count_everywhere_route_looks():
    had = computer.tools_had(["mcp__claude-code-remote__create_session",
                              "mcp__claude-code-remote__request_computer_folder"])
    assert {"create_session", "request_computer_folder"} <= had


def test_the_starter_is_never_told_to_hand_its_work_to_another_chat(tmp_path, monkeypatch):
    _as(monkeypatch, "cloud", tmp_path)
    db = dict(_db(WORK), meta={"computer_starter": {"data": {"chat": "session_starter",
                                                             "bell": "b"}, "version": 1}})
    for tools in ([], ["Bash"], ["mcp__claude-code-remote__get_session"]):
        got = computer.route(db, T, chat="session_starter", envs=BRIDGE, tools=tools)
        assert got["route"] != "on, start it elsewhere" and "handback" not in got, got
        assert got["line"] not in (computer.SAY["off"], computer.SAY["gone"]), got
        assert "next brief" in got["line"], got


def test_a_chat_with_create_session_is_never_told_it_has_none(tmp_path, monkeypatch):
    _as(monkeypatch, "cloud", tmp_path)
    for tools in (["create_session"], ["mcp__claude-code-remote__create_session"]):
        got = computer.route(_db(WORK), T, chat="session_helper", envs=BRIDGE, tools=tools)
        assert "has no create_session" not in json.dumps(got), got


def test_a_computer_with_no_name_is_said_once(tmp_path, monkeypatch):
    _as(monkeypatch, "cloud", tmp_path)
    nameless = {"environments": [{"environment_id": "env_x", "name": "", "kind": "bridge",
                                  "description": "", "state": "active"}]}
    starter = {"computer_starter": {"data": {"chat": "session_starter", "bell": "b"},
                                    "version": 1}}
    for chat, tools in (("session_helper", []), ("session_helper", ["create_session"]),
                        ("session_starter", [])):
        got = computer.route(dict(_db(WORK), meta=starter if "starter" in chat else {}), T,
                             chat=chat, envs=nameless, tools=tools)
        assert "your your" not in got["line"].lower(), got
    assert got["line"].startswith("Your computer is on"), got
