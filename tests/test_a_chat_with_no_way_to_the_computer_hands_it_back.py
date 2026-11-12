"""A chat with no tool to reach the person's computer hands the step back to the chat that
started it, in lines that chat carries out as printed, and never says the computer is off.

The maintainer's copy, 2026-11-11 (local review 3): the page's work runs in a subagent of the
chat that answers the page, which has no list of computers, no create_session and no
get_session. `route` with no list and no tools said the computer was off even with a check-in
30 minutes old; "on, start it elsewhere" told it to ask the chat that answers the page, which
a subagent cannot (its only way back is its answer); and checking or making the starter needed
tools it lacked. Now `route` prints a `handback`: `call: <tool> <json>` lines and the `then:`
that follows, which the listener makes exactly as printed (SKILL.md, step 0). Every computer
here is invented.
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
from test_a_computer_chat_is_seen_to_its_end import BELL, T, _as, _starter  # noqa: E402
from test_a_tick_on_the_page_is_applied_once import _db, _w  # noqa: E402
from test_the_computer_side_just_works import BRIDGE  # noqa: E402

WORK = ("network~read~1", _w("network", to="computer", title="Reading one profile"))
# A subagent of the chat that answers the page: the page's tools, no remote ones.
SUBAGENT = ["Bash", "Read", "Artifact", "ArtifactData", "ArtifactComments"]
LISTENER = SUBAGENT + ["mcp__claude-code-remote__list_environments",
                       "mcp__claude-code-remote__create_session",
                       "mcp__claude-code-remote__get_session",
                       "mcp__claude-code-remote__archive_session"]


def _beat(db: dict, minutes: float) -> dict:
    db.setdefault("chats", {})[computer.beat_id("Studio Laptop")] = {
        "data": {"kind": "computer", "computer": "Studio Laptop", "watching": False,
                 "seen_at": app_model.stamp(T - dt.timedelta(minutes=minutes))}, "version": 1}
    return db


def _back(got: dict) -> tuple[list, list]:
    """(calls as [(tool, args)], then lines) of a hand-back."""
    calls, then = [], []
    for ln in got.get("handback") or []:
        if ln.startswith("call: "):
            tool, _, args = ln[len("call: "):].partition(" ")
            calls.append((tool, json.loads(args)))
        else:
            assert ln.startswith("then: "), ln
            then.append(ln)
    return calls, then


def test_no_list_and_no_tools_never_says_off_with_a_fresh_check_in(tmp_path, monkeypatch):
    _as(monkeypatch, "cloud", tmp_path)
    db = _beat(_db(WORK), 30)
    got = computer.route(db, T, chat="session_helper", envs=None, tools=[])
    assert got["line"] != computer.SAY["off"], got
    # It asks the chat that started it for the list, and says how to route with it.
    calls, then = _back(got)
    assert calls == [("list_environments", {})], got
    assert "computer.py route" in then[0] and "--envs" in then[0] and "session_helper" in then[0]
    # On a computer, with no list to ask for and no browser, still never off on a fresh one.
    _as(monkeypatch, "computer", tmp_path)
    assert computer.route(db, T, chat="mac-1", envs=None, tools=[])["line"] != computer.SAY["off"]


def test_a_subagent_rings_the_starter_itself_and_hands_back_what_it_cannot(tmp_path, monkeypatch):
    _as(monkeypatch, "cloud", tmp_path)
    db = dict(_db(WORK), **_starter())
    # With the page's tools it rings the bell itself: nothing to hand back.
    got = computer.route(db, T, chat="session_helper", envs=BRIDGE, tools=SUBAGENT)
    assert got["route"] == "ring starter" and "handback" not in got, got
    # With no starter, it cannot make one: the create_session goes back, as printed.
    bare = _db(WORK)
    monkeypatch.setattr("app_setup.origin", lambda *a, **k: ("someone", "my-job-search"))
    got = computer.route(bare, T, chat="session_helper", envs=BRIDGE, tools=SUBAGENT,
                         url="https://claude.ai/artifact/page-1",
                         copy="github.com/someone/my-job-search")
    # Said as the computer being on, with nothing about chats (the maintainer, 2026-11-11).
    assert got["route"] == "on, start it elsewhere" and "chat" not in got["line"].lower(), got
    calls, then = _back(got)
    assert [c[0] for c in calls] == ["create_session"]
    assert calls[0][1]["title"] == computer.STARTER_TITLE
    assert "starter-made" in then[0]
    # The listener, with its own tools, makes it from the same output: no hand-back.
    mine = computer.route(bare, T, chat="session_helper", envs=BRIDGE, tools=LISTENER,
                          url="https://claude.ai/artifact/page-1",
                          copy="github.com/someone/my-job-search")
    assert mine["route"] == "make starter" and "handback" not in mine, mine


def test_a_starter_that_is_not_answering_is_looked_at_by_the_listener(tmp_path, monkeypatch):
    _as(monkeypatch, "cloud", tmp_path)
    old = app_model.stamp(T - dt.timedelta(hours=2))
    db = dict(_db(WORK), **_starter(rung_at=old, rings=computer.STARTER_SILENT_RINGS))
    got = computer.route(db, T, chat="session_helper", envs=BRIDGE, tools=SUBAGENT)
    assert got["route"] == "check starter", got
    calls, then = _back(got)
    assert calls == [("get_session", {"session_id": "session_starter"})]
    assert "starter-seen" in then[0] and "computer.py route" in then[0]


def test_a_chat_with_no_publish_hands_the_ring_back(tmp_path, monkeypatch):
    _as(monkeypatch, "cloud", tmp_path)
    db = dict(_db(WORK), **_starter())
    got = computer.route(db, T, chat="session_helper", envs=BRIDGE, tools=["Bash", "ArtifactData"])
    calls, then = _back(got)
    # The bell is read first: it is the starter's page, and a publish to a page this chat has
    # not read is refused (decided 2026-11-12, the maintainer's Mac).
    assert [c[0] for c in calls] == ["Artifact", "Artifact", "ArtifactComments"]
    assert calls[0][1] == {"action": "read", "url": BELL}
    assert calls[1][1]["url"] == BELL and calls[1][1]["action"] == "publish"
    assert calls[2][1] == {"action": "watch", "url": BELL, "on": False}
    assert "computer.py rung" in then[0]


def test_full_tool_names_count(tmp_path, monkeypatch):
    """A chat passes its tools as it has them: mcp__claude-code-remote__create_session was
    not create_session, so a helper that could start the starter was told it could not."""
    _as(monkeypatch, "cloud", tmp_path)
    monkeypatch.setattr("app_setup.origin", lambda *a, **k: ("someone", "my-job-search"))
    got = computer.route(_db(WORK), T, chat="session_helper", envs=BRIDGE, tools=LISTENER,
                         url="https://claude.ai/artifact/page-1",
                         copy="github.com/someone/my-job-search")
    assert got["route"] == "make starter" and "handback" not in got, got


def test_on_start_it_elsewhere_is_never_a_dead_end(tmp_path, monkeypatch):
    _as(monkeypatch, "cloud", tmp_path)
    db = _db(WORK)
    got = computer.route(db, T, chat="session_helper", envs=BRIDGE, tools=SUBAGENT)
    assert "ask the chat that answers the page" not in json.dumps(got), got
    assert got.get("handback"), got


def test_the_cli_fills_in_the_folder_and_notes_the_list_was_asked(tmp_path, monkeypatch, capsys):
    """The listener does not know the subagent's folder: the hand-back names it. And until the
    list comes, the page's row says Claude is checking, never off."""
    _as(monkeypatch, "cloud", tmp_path)
    dump = tmp_path / "dump"
    os.makedirs(dump / "work")
    with open(dump / "work" / "@".join(("network", "read", "1.json")), "w", encoding="utf-8") as fh:
        json.dump(WORK[1], fh)
    os.makedirs(dump / "beats")
    with open(dump / "beats" / "@".join(("computer", "studio-laptop.json")), "w", encoding="utf-8") as fh:
        json.dump({"kind": "computer", "computer": "Studio Laptop", "watching": False,
                   "seen_at": app_model.stamp(T - dt.timedelta(hours=26))}, fh)
    computer.main(["route", str(dump), "--chat", "session_helper", "--tools", ",".join(SUBAGENT),
                   "--now", app_model.stamp(T)])
    got = json.loads(capsys.readouterr().out)
    assert "<dump>" not in "\n".join(got["handback"]) and str(dump) in got["handback"][-1]
    entry = json.load(open(got["batches"][0], encoding="utf-8"))[0]
    with open(entry["file_path"], encoding="utf-8") as fh:
        asked = json.load(fh)
    db = _db(WORK)
    db["chats"] = {"computer~studio-laptop": {"data": {
        "kind": "computer", "computer": "Studio Laptop",
        "seen_at": app_model.stamp(T - dt.timedelta(hours=26))}, "version": 1}}
    db["meta"] = {"computer_envs": {"data": asked, "version": 1}}
    st = computer.state(db, T)
    assert st["state"] == "checking" and not st["card"], st


def test_the_listener_carries_out_a_hand_back_as_printed():
    """SKILL.md step 0: an answer with `call:` lines is a hand-back, made by the listener exactly
    as printed, then its `then:`; the subagent is told to end its answer with them."""
    with open(os.path.join(ROOT, ".claude", "skills", "app", "SKILL.md"), encoding="utf-8") as fh:
        skill = " ".join(fh.read().split())
    assert "`call:`" in skill and "`then:`" in skill and "hand-back" in skill
    assert "exactly as printed" in skill.split("hand-back", 1)[1][:600]
