"""A computer asleep, or Claude closed there, while its connection still shows active gets one
chat started for the work at a time, and every chat started for it is put away in the end.

The maintainer's copy, 2026-11-11 (local review 9): a chat started on the computer that did not
come (the Mac asleep) was replaced every half hour, each new id written over the last, so the
earlier ones were never put away; when the Mac woke, several started, all but one stopped at
the claim, refused, before the steps that let the starter put them away, and stayed in the
sidebar. Now the chats started for a piece of work are kept, no new one starts while an
earlier one has not come, and a chat refused its claim goes to its last steps. Every computer
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
from test_a_computer_chat_is_seen_to_its_end import T  # noqa: E402
from test_a_tick_on_the_page_is_applied_once import _db, _w  # noqa: E402

WID = "network~read~1"


def _fields(batches) -> dict:
    entry = json.load(open(batches[0], encoding="utf-8"))[0]
    if entry.get("data") is not None:
        return entry["data"]
    with open(entry["file_path"], encoding="utf-8") as fh:
        return json.load(fh)


def _start(db: dict, sid: str, at: dt.datetime, tmp_path) -> dict:
    got = _fields(computer.started(db, WID, sid, "env_bridge1", "Studio Laptop", at,
                                   str(tmp_path / sid)))
    db["work"][WID]["data"].update(got)
    db["work"][WID]["version"] += 1
    return db


def test_an_earlier_chat_is_kept_when_another_is_started(tmp_path):
    db = _db((WID, _w("network", to="computer")))
    db = _start(db, "session_a", T, tmp_path)
    db = _start(db, "session_b", T + dt.timedelta(hours=3), tmp_path)
    d = db["work"][WID]["data"]
    assert d["computer_session"]["id"] == "session_b"
    assert [s["id"] for s in d["computer_earlier"]] == ["session_a"]
    # The earlier one is put away (it did not come), the newest is waited for.
    w = computer.waiting(db, T + dt.timedelta(hours=3, minutes=5))
    assert {"work": WID, "session": "session_a"} in w["finished"]
    assert w["started"] == {WID: "session_b"}


def test_no_second_chat_while_the_first_has_not_come(tmp_path):
    db = _start(_db((WID, _w("network", to="computer"))), "session_a", T, tmp_path)
    for minutes in (31, 60, 90, 119):
        w = computer.waiting(db, T + dt.timedelta(minutes=minutes))
        assert w["started"] == {WID: "session_a"} and not w["queued"], minutes
    # Past the wait, it is put away and the work may start afresh.
    w = computer.waiting(db, T + computer_show_up() + dt.timedelta(minutes=1))
    assert w["queued"] == [WID] and {"work": WID, "session": "session_a"} in w["finished"]


def computer_show_up() -> dt.timedelta:
    return dt.timedelta(seconds=computer.SHOW_UP_S)


def test_a_chat_that_came_and_stopped_is_put_away_when_the_work_waits_again(tmp_path):
    db = _start(_db((WID, _w("network", to="computer"))), "session_a", T, tmp_path)
    # It claimed the work, then its claim lapsed (the chat died): the work waits again, and the
    # chat is put away rather than forgotten.
    db["work"][WID]["data"].update(status="running", claimed_by="session_a",
                                   claimed_at=app_model.stamp(T + dt.timedelta(minutes=2)),
                                   lease_until=app_model.stamp(T + dt.timedelta(minutes=32)))
    w = computer.waiting(db, T + dt.timedelta(hours=1))
    assert w["queued"] == [WID] and {"work": WID, "session": "session_a"} in w["finished"]


def test_a_chat_refused_its_claim_is_put_away_after_its_last_heartbeat(tmp_path):
    """Two came: one took the work, the other was refused and ran its last steps, ending with a
    heartbeat. The other is put away; the one at work is not."""
    db = _start(_db((WID, _w("network", to="computer"))), "session_a", T, tmp_path)
    db = _start(db, "session_b", T + computer_show_up() + dt.timedelta(minutes=1), tmp_path)
    later = T + computer_show_up() + dt.timedelta(minutes=20)
    db["work"][WID]["data"].update(status="running", claimed_by="session_a",
                                   claimed_at=app_model.stamp(later),
                                   lease_until=app_model.stamp(later + dt.timedelta(minutes=30)))
    beat = computer.beat_fields("Studio Laptop", later + dt.timedelta(minutes=2), chat="session_b")
    db["chats"] = {computer.beat_id("Studio Laptop"): {"data": beat, "version": 2}}
    w = computer.waiting(db, later + dt.timedelta(minutes=3))
    assert {"work": WID, "session": "session_b"} in w["finished"], w
    assert all(f["session"] != "session_a" for f in w["finished"]), w


def test_the_heartbeat_keeps_which_chats_came(tmp_path):
    db = {"chats": {}}
    batches = computer.beat(db, "Studio Laptop", T, str(tmp_path / "1"), chat="session_a")
    first = _fields(batches)
    db["chats"][computer.beat_id("Studio Laptop")] = {"data": first, "version": 1}
    second = _fields(computer.beat(db, "Studio Laptop", T + dt.timedelta(minutes=5),
                                   str(tmp_path / "2"), chat="session_b"))
    assert [c["chat"] for c in second["chats_seen"]][:2] == ["session_b", "session_a"]


def test_put_away_names_the_chat_and_an_older_starter_still_puts_away_the_right_ones(tmp_path):
    db = _start(_db((WID, _w("network", to="computer"))), "session_a", T, tmp_path)
    db = _start(db, "session_b", T + dt.timedelta(hours=3), tmp_path)
    at = T + dt.timedelta(hours=3, minutes=5)
    # A starter made before this knows no --session: what `waiting` listed is put away.
    got = _fields(computer.archived(db, WID, at, str(tmp_path / "old")))
    assert not (got.get("computer_session") or {}).get("archived_at")
    assert [s.get("archived_at") for s in got["computer_earlier"]] == [app_model.stamp(at)]
    # Named, only that one.
    got = _fields(computer.archived(db, WID, at, str(tmp_path / "new"), session="session_b"))
    assert got["computer_session"]["archived_at"] == app_model.stamp(at)
    assert "computer_earlier" not in got
    prompt = " ".join(computer.starter_prompt("u", "c").split())
    assert "--session <its session>" in prompt


def test_a_chat_refused_its_claim_goes_to_its_last_steps():
    prompt = " ".join(computer.session_prompt(WID, "People", "u", "github.com/x/y").split())
    step4 = prompt[prompt.index("4. "):prompt.index("5. ")].lower()
    assert "refused" in step4 and "step 7" in step4 and "stop)" not in step4


def test_the_row_says_a_chat_started_there_has_not_begun(tmp_path):
    """Not "reading LinkedIn now" for a chat that never began: the computer asleep."""
    db = _start(_db((WID, _w("network", to="computer"))), "session_a", T, tmp_path)
    from test_the_computer_side_just_works import BRIDGE
    assert computer.state(db, T + dt.timedelta(minutes=5), envs=BRIDGE)["say"] == "working"
    later = computer.state(db, T + dt.timedelta(minutes=45), envs=BRIDGE)
    assert later["state"] == "working" and later["say"] == "starting"
    assert later["line"] == computer.SAY["starting"] and not later["card"]
