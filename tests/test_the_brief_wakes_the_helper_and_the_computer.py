"""The brief's run wakes what nothing else would, and the computer approval lives in one small
chat of its own.

Found on 2026-11-10 in the maintainer's copy: since the brief moved to a chat of its own, a
quiet morning woke no helper, so none renewed (one was still answering at 11:00), and a read
the brief queued for the computer at 08:12 sat unstarted for three hours. The helper had
approved computer access, so no chat could archive it, itself included, and every daily
hand-over left an old helper in the sidebar. And LinkedIn signed out on the computer overnight
was found only when a job stopped there, by the maintainer checking. Invented people and
computers only.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "network"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import app_model  # noqa: E402
import computer  # noqa: E402
from test_a_tick_on_the_page_is_applied_once import NOW, _db, _w  # noqa: E402
from test_one_chat_answers_the_page import _on_github, renew_call  # noqa: E402
from test_the_computer_side_just_works import BRIDGE  # noqa: E402

T = app_model.parse_time(NOW)
STARTER = {"chat": "session_starter", "bell": "https://claude.ai/artifact/bell-1",
           "made_at": "2026-11-01T08:00:00Z", "rung_at": None}


def _cloud(monkeypatch, tmp_path=None):
    import app_listen
    import tempfile
    # What this checkout saw (renewed_at) is kept in a throwaway folder, never the checkout's.
    monkeypatch.setenv("LJS_STATE", str(tmp_path or tempfile.mkdtemp()))
    monkeypatch.setattr(app_listen, "chat_kind", lambda: "cloud")
    monkeypatch.setattr(app_listen, "_zone", lambda: "UTC")
    monkeypatch.setattr(app_listen, "history_tokens", lambda: 0)
    _on_github(monkeypatch)


def _fresh_seen():
    import app_listen
    app_listen._save_seen({k: v for k, v in app_listen.seen().items() if k != "renewed_at"})


# ------------------------------------------------------------------ the fresh helper


def test_the_brief_starts_the_fresh_helper_when_its_day_is_up(tmp_path, monkeypatch):
    import app_listen
    _cloud(monkeypatch, tmp_path)
    monkeypatch.setattr(app_listen, "this_chat", lambda c="": "session_brief")
    now = dt.datetime(2026, 11, 10, 8, 12, tzinfo=dt.timezone.utc)
    rec = {"chat": "session_helper", "kind": "cloud", "helper": True,
           "since": "2026-11-09T09:00:00Z", "answered_at": "2026-11-09T21:00:00Z"}
    db = {"meta": {"listener": {"data": rec, "version": 5}}, "work": {}}
    _fresh_seen()
    lines = app_listen.view_renewal(db, "brief", now)
    assert len(lines) == 1 and lines[0].startswith("listen: renew:"), lines
    call = renew_call(lines[0])
    assert call["source_url"].endswith("/my-job-search") and call["permission_mode"] == "auto"
    # Asked for once: the brief run again within the hour asks for no second one.
    assert app_listen.view_renewal(db, "brief", now) == []
    # A helper that took the page this morning, with nothing waiting, is left to answer.
    _fresh_seen()
    today = dict(rec, since="2026-11-10T07:30:00Z", answered_at="2026-11-10T07:40:00Z")
    assert app_listen.view_renewal({"meta": {"listener": {"data": today, "version": 5}},
                                    "work": {}}, "brief", now) == []
    # A helper at work on something small right now takes what waits after it.
    busy = dict(db, work={"w1": {"data": {"status": "running", "kind": "reply",
                                          "claimed_by": "session_helper",
                                          "lease_until": "2026-11-10T08:30:00Z"}, "version": 1}})
    assert app_listen.view_renewal(busy, "brief", now) == []
    # A chat on a computer answering the page is never renewed.
    desk = dict(rec, kind="computer")
    assert app_listen.view_renewal({"meta": {"listener": {"data": desk, "version": 5}},
                                    "work": {}}, "brief", now) == []


def test_work_waiting_that_no_chat_took_starts_the_fresh_helper(tmp_path, monkeypatch):
    import app_listen
    _cloud(monkeypatch, tmp_path)
    monkeypatch.setattr(app_listen, "this_chat", lambda c="": "session_brief")
    now = dt.datetime(2026, 11, 10, 9, 0, tzinfo=dt.timezone.utc)
    rec = {"chat": "session_helper", "kind": "cloud", "helper": True,
           "since": "2026-11-10T07:30:00Z", "answered_at": "2026-11-10T07:40:00Z"}
    waiting = {"w1": {"data": {"status": "queued", "kind": "draft",
                               "asked_at": "2026-11-10T08:12:00Z"}, "version": 1}}
    db = {"meta": {"listener": {"data": rec, "version": 5}}, "work": waiting}
    _fresh_seen()
    lines = app_listen.view_renewal(db, "brief", now)
    assert len(lines) == 1 and lines[0].startswith("listen: renew:"), lines
    # Work this very run queued (its own self-fixes) counts the same, at once.
    _fresh_seen()
    quiet = {"meta": {"listener": {"data": rec, "version": 5}}, "work": {}}
    assert app_listen.view_renewal(quiet, "brief", now) == []
    assert len(app_listen.view_renewal(quiet, "brief", now, queued=True)) == 1


# ------------------------------------------------------------------ the computer starter


def test_a_helper_never_approves_computer_access_it_wakes_the_starter(monkeypatch):
    _cloud(monkeypatch)
    item = _w("network", "Harbourline Bank", to="computer")
    db = _db(("network~people", item))
    tools = ["create_session"]
    url, copy_ = "https://claude.ai/artifact/page-1", "github.com/someone/my-job-search"
    # 1. No starter yet: the helper makes it once, from the copy, in Auto.
    got = computer.route(db, T, chat="session_helper", envs=BRIDGE, tools=tools, url=url,
                         copy=copy_)
    assert got["route"] == "make starter", got
    call = got["call"]
    assert call["title"] == computer.STARTER_TITLE and call["permission_mode"] == "auto"
    assert call["source_url"] == "https://github.com/someone/my-job-search"
    assert "confirm_repository_trust" not in got["then"]
    assert "never approves computer access" in got["then"]
    assert "bell-file" in call["prompt"] and "starter-ready" in call["prompt"]
    assert "never answers my page" in call["prompt"]
    # Made, not ready yet: nothing is made twice meanwhile.
    made = dict(db, meta={"computer_starter": {"data": dict(STARTER, bell="",
                                                            made_at=app_model.stamp(T)),
                                               "version": 1}})
    assert computer.route(made, T, chat="session_helper", envs=BRIDGE,
                          tools=tools)["route"] == "starter starting"
    # 2. Ready: the bell is rung (republished), and this chat's own watch on it stopped.
    ready = dict(db, meta={"computer_starter": {"data": STARTER, "version": 2}})
    got = computer.route(ready, T, chat="session_helper", envs=BRIDGE, tools=tools)
    assert got["route"] == "ring starter" and got["bell"] == STARTER["bell"]
    assert "Artifact publish" in got["then"] and "on: false" in got["then"]
    assert "computer.py rung" in got["then"] and "create_session" not in got["then"]
    # Rung a minute ago for this work: not rung again.
    rung = dict(db, meta={"computer_starter": {"data": dict(
        STARTER, rung_at=app_model.stamp(T + dt.timedelta(minutes=1))), "version": 3}})
    assert computer.route(rung, T + dt.timedelta(minutes=2), chat="session_helper",
                          envs=BRIDGE, tools=tools)["route"] == "starter rung"
    # 3. The starter itself starts the chat on the computer, and only it approves.
    got = computer.route(ready, T, chat="session_starter", envs=BRIDGE, tools=tools, url=url,
                         copy=copy_)
    assert got["route"] == "computer session"
    assert "confirm_repository_trust" in got["then"] and "only ever in this chat" in got["then"]


def test_the_starter_record_and_its_bell(tmp_path):
    db = _db(("network~people", _w("network", to="computer")))
    batches = computer.starter_made(db, "session_starter", T, str(tmp_path / "a"))
    entry = json.load(open(batches[0], encoding="utf-8"))[0]
    assert (entry["collection"], entry["doc_id"]) == ("meta", "computer_starter")
    with open(entry["file_path"], encoding="utf-8") as fh:
        assert json.load(fh)["chat"] == "session_starter"
    bell = computer.write_bell(str(tmp_path / "bell.html"), T)
    with open(bell, encoding="utf-8") as fh:
        html = fh.read()
    assert "<title>" + computer.BELL_TITLE in html and app_model.stamp(T) in html
    # Each ring differs, so a republish is a republish.
    assert computer.bell_html(T) != computer.bell_html(T + dt.timedelta(seconds=1))


def test_the_tidy_up_keeps_the_starter():
    import tidy
    assert tidy.APP_TITLE.match(computer.STARTER_TITLE)
    assert tidy.STARTER_NAME.match(computer.STARTER_TITLE)
    assert not tidy.STARTER_NAME.match("Job search page (finishing up)")


# ------------------------------------------------------------------ the LinkedIn sign-in


def test_a_job_stopped_at_the_sign_in_has_its_chat_put_away_and_waits_for_them(monkeypatch):
    stopped = _w("network", "Harbourline Bank", to="computer")
    stopped.update(status="needs_you", computer_session={"id": "session_mac1", "at": NOW})
    db = _db(("network~people", stopped))
    w = computer.waiting(db, T)
    assert w["finished"] == [{"work": "network~people", "session": "session_mac1"}]
    assert w["queued"] == []                      # started again only once they answer
    # The helper that sees it wakes the starter to put it away.
    _cloud(monkeypatch)
    ready = dict(db, meta={"computer_starter": {"data": STARTER, "version": 2}})
    got = computer.route(ready, T, chat="session_helper", envs=BRIDGE, tools=["create_session"])
    assert got["route"] == "ring starter"
    # And the chat on the computer rings at its end itself.
    prompt = computer.session_prompt("network~people", "People", "https://claude.ai/artifact/x",
                                     "their job search")
    assert "computer.py ring" in prompt


def test_a_sign_in_that_did_not_last_says_to_keep_it(tmp_path):
    day1 = computer.beat_fields("Studio Laptop", T - dt.timedelta(hours=26), linkedin="in")
    first = computer.cookies_seen({}, day1)
    assert first == {"signed_in_at": day1["seen_at"]}
    was = dict(day1, **first)
    day2 = computer.beat_fields("Studio Laptop", T, linkedin="out")
    lost = computer.cookies_seen(was, day2)
    assert lost["keep_cookies"] == "off" and lost["signin_lost"]["out_at"] == day2["seen_at"]
    beat = dict(day2, **lost)
    db = {"chats": {computer.beat_id("Studio Laptop"): {"data": beat, "version": 2}},
          "work": {}}
    st = computer.state(db, T)
    assert st["state"] == "signed_out" and "keep the sign-in" in st["line"]
    # It leads the brief, whatever waits.
    first_line = [ln for ln in computer.check(db, T) if "first line of the message" in ln]
    assert first_line and st["line"] in first_line[0]
    # Signed in again and held for a day: the browser keeps it now.
    back = computer.beat_fields("Studio Laptop", T + dt.timedelta(hours=1), linkedin="in")
    again = computer.cookies_seen(beat, back)
    assert again["keep_cookies"] == "off"
    held = computer.beat_fields("Studio Laptop", T + dt.timedelta(hours=22), linkedin="in")
    assert computer.cookies_seen(dict(back, **again), held)["keep_cookies"] == "unknown"


def test_a_chat_on_the_computer_that_sees_the_sign_in_carries_on_with_no_tap(tmp_path):
    item = _w("network", "Harbourline Bank", to="computer")
    item.update(status="needs_you", note="LinkedIn is signed out in Claude's browser.",
                needs={"question": "x", "signin": "linkedin"},
                computer_session={"id": "session_mac1", "at": "2026-10-25T08:00:00Z"})
    db = _db(("network~read~1", item))
    batches = computer.signed_in(db, "network~read~1", T, str(tmp_path / "s"),
                                 dump_dir=str(tmp_path / "d"))
    entry = json.load(open(batches[0], encoding="utf-8"))[0]
    with open(entry["file_path"], encoding="utf-8") as fh:
        got = json.load(fh)
    assert got["status"] == "queued" and got["claimed_by"] is None and got["note"] is None
    assert computer.SIGNED_IN_SAID in got["args"]["answers"].values()
    # Kept as at work on the computer: no second chat is started for it meanwhile.
    after = _db(("network~read~1", dict(item, **got)))
    assert computer.waiting(after, T)["started"] == {"network~read~1": "session_mac1"}
    # The chat on the computer is told to do it, and never to send them to the page.
    prompt = computer.session_prompt("network~read~1", "Reading", "https://claude.ai/artifact/x",
                                     "their job search")
    assert "computer.py signed-in" in prompt and "Never tell them to tap" in prompt
    # Only for a job waiting on a sign-in.
    import pytest
    with pytest.raises(KeyError):
        computer.signed_in(_db(("n2", _w("network", to="computer"))), "n2", T, str(tmp_path / "x"))


def test_the_chat_that_answers_the_page_can_withdraw_unstarted_computer_work(tmp_path):
    """A repeat read queued for the computer could only be called off by the person's own Stop:
    `done --stopped` from the cloud was refused (the maintainer, 2026-11-10)."""
    import page_db
    import pytest
    item = _w("network", "Harbourline Insurance", to="computer")
    db = _db(("network~read~2", item))
    with pytest.raises(ValueError, match="say why"):
        page_db.finish(db, "network~read~2", T, str(tmp_path / "a"), status="stopped",
                       chat_kind="cloud", chat="session_helper")
    got = page_db.finish(db, "network~read~2", T, str(tmp_path / "b"), status="stopped",
                         summary="Called off: these profiles were read earlier today.",
                         chat_kind="cloud", chat="session_helper")
    entry = json.load(open(got["batches"][0], encoding="utf-8"))[0]
    with open(entry["file_path"], encoding="utf-8") as fh:
        fields = json.load(fh)
    assert fields["status"] == "stopped" and fields["withdrawn"] is True
    assert fields["result"]["summary"].startswith("Called off")
    # Once a chat on the computer has it, a cloud chat still cannot end it.
    running = _db(("network~read~3", dict(item, status="running", claimed_by="mac-1",
                                          claimed_at=NOW)))
    with pytest.raises((ValueError, KeyError)):
        page_db.finish(running, "network~read~3", T, str(tmp_path / "c"), status="stopped",
                       summary="Called off.", chat_kind="cloud", chat="session_helper")
