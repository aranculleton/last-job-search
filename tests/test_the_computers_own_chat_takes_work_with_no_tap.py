"""Work for the person's computer needs no tap in the normal case: the chat on the computer kept
open after its job (the listener, "Job search: on your computer") is woken by its own bell, and
no chat is started from the cloud.

Issue #250: every "Find people" press started a chat on the computer from the cloud, and Claude
asked "Allow Claude to start a session?" in the starter's chat each time, with no "always". That
rule is Claude's own, so the fix is to stop needing it after the first job. A listener that does
not answer is stale, and the work goes the way it went before. Every person, chat and computer
here is invented.
"""
from __future__ import annotations

import io
import json
import os
import sys
from contextlib import redirect_stdout
from datetime import timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "network"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import app_model  # noqa: E402
import computer  # noqa: E402
from test_a_computer_chat_is_seen_to_its_end import BELL, NOW, T, URL, _apply, _as  # noqa: E402
from test_a_tick_on_the_page_is_applied_once import _db, _w  # noqa: E402
from test_the_computer_side_just_works import BRIDGE  # noqa: E402

WID = "network~read~1"
WORK = (WID, _w("network", "Harbourline Bank", to="computer", title="People at Harbourline Bank",
                asked=NOW))
LBELL = "https://claude.ai/artifact/listener-bell-1"
STARTER = {"chat": "session_starterEXAMPLE", "bell": BELL, "made_at": "2026-10-20T08:00:00Z",
           "ready_at": "2026-10-20T08:02:00Z"}
LISTENER = {"chat": "session_listenerEXAMPLE", "bell": LBELL, "computer": "Studio Laptop",
            "ready_at": app_model.stamp(T - timedelta(hours=3)),
            "answered_at": app_model.stamp(T - timedelta(minutes=30)), "rings": 0,
            "kept_at": app_model.stamp(T - timedelta(minutes=30))}
EVERY_TOOL = ["create_session", "get_session", "list_triggers", "confirm_repository_trust",
              "ArtifactData", "Artifact", "ArtifactComments", "list_environments"]
COPY = "github.com/someone/my-job-search"


def _with(db: dict, listener: dict | None = None, **kw) -> dict:
    meta = {"computer_starter": {"data": dict(STARTER), "version": 3}}
    if listener is not None:
        meta["computer_listener"] = {"data": dict(listener, **kw), "version": 4}
    return dict(db, meta=meta)


def _cloud(monkeypatch, tmp_path):
    import app_setup
    _as(monkeypatch, "cloud", tmp_path)
    monkeypatch.setattr(app_setup, "origin", lambda: ("someone", "my-job-search"))
    monkeypatch.setattr(app_setup, "page_record", lambda: {"url": URL})


def _dump(db: dict, path) -> str:
    """The page's database as a chat reads it into a folder (one file a record)."""
    import page_db
    for coll, docs in db.items():
        where = page_db.STORE.get(coll, coll)
        os.makedirs(os.path.join(path, where), exist_ok=True)
        for did, doc in docs.items():
            with open(os.path.join(path, where, did.replace("~", "@") + ".json"), "w",
                      encoding="utf-8") as fh:
                json.dump(doc, fh)
    return str(path)


def _run(*args) -> str:
    out = io.StringIO()
    with redirect_stdout(out):
        assert computer.main([str(a) for a in args]) == 0
    return out.getvalue()


# ------------------------------------------------------------------ rung, never started


def test_a_live_computer_chat_is_rung_and_no_chat_is_started(tmp_path, monkeypatch):
    """With the computer's own chat watching its bell, the starter itself, the page's helper and
    its subagent all ring that bell: none of them starts a chat on the computer, so nobody is
    asked to Allow one."""
    _cloud(monkeypatch, tmp_path)
    db = _with(_db(WORK), LISTENER)
    for chat, tools in ((STARTER["chat"], EVERY_TOOL), ("session_helperEXAMPLE", EVERY_TOOL)):
        got = computer.route(db, T, chat=chat, envs=BRIDGE, tools=tools, url=URL, copy=COPY)
        assert got["route"] == "ring computer chat", got
        assert "create_session" not in json.dumps(got), got
        assert got["line"] == computer.LISTENER_TAKES and got["bell"] == LBELL
        assert "listener-rung" in got["then"] and f"Artifact read with url {LBELL}" in got["then"]
    # A helper's own agent, with the page's data tools only, hands the ring back, never a start.
    got = computer.route(db, T, chat="session_helperEXAMPLE", tools=["ArtifactData"], url=URL,
                         copy=COPY)
    assert got["route"] == "ring computer chat" and "create_session" not in json.dumps(got)
    calls = [ln for ln in got["handback"] if ln.startswith("call: ")]
    assert '"action": "read"' in calls[0] and '"action": "publish"' in calls[1], calls
    assert "listener-rung" in got["handback"][-1]
    # Printed, its bell page is the computer chat's own, and the steps name it.
    filled = computer.filled(computer.route(db, T, chat=STARTER["chat"], envs=BRIDGE,
                                            tools=EVERY_TOOL, url=URL, copy=COPY),
                             str(tmp_path / "d"), T)
    page = open(tmp_path / "d" / "bell.html", encoding="utf-8").read()
    assert "<title>" + computer.LISTENER_BELL_TITLE in page
    assert "listener-rung" in filled["then"] and str(tmp_path / "d" / "bell.html") in filled["then"]
    # Without it, the same chat starts one, as before.
    before = computer.route(_with(_db(WORK)), T, chat=STARTER["chat"], envs=BRIDGE,
                            tools=EVERY_TOOL, url=URL, copy=COPY)
    assert before["route"] == "computer session" and before["tool"] == "create_session"


def test_a_ring_on_its_way_is_not_rung_again_and_the_page_says_it_is_starting(
        tmp_path, monkeypatch):
    _cloud(monkeypatch, tmp_path)
    rung = _with(_db(WORK), LISTENER, rung_at=app_model.stamp(T - timedelta(minutes=2)), rings=1)
    got = computer.route(rung, T, chat=STARTER["chat"], envs=BRIDGE, tools=EVERY_TOOL, url=URL,
                         copy=COPY)
    assert got["route"] == "computer chat rung" and "create_session" not in json.dumps(got)
    assert computer.state(rung, T, envs=BRIDGE)["state"] == "starting_chat"


# ------------------------------------------------------------------ a listener that is gone


def test_a_computer_chat_that_does_not_answer_is_stale_and_the_chat_is_started_as_before(
        tmp_path, monkeypatch):
    """Rung five minutes ago with no answer, or rung twice unanswered: the work goes the way it
    went before the listener, and the route marks it stale, so nobody rings it again."""
    _cloud(monkeypatch, tmp_path)
    for kw in ({"rung_at": app_model.stamp(T - timedelta(minutes=6)), "rings": 1},
               {"rung_at": app_model.stamp(T - timedelta(minutes=1)), "rings": 2}):
        db = _with(_db(WORK), LISTENER, **kw)
        assert computer.listener_stale(db, T)
        got = computer.route(db, T, chat=STARTER["chat"], envs=BRIDGE, tools=EVERY_TOOL,
                             url=URL, copy=COPY)
        assert got["route"] == "computer session" and got["tool"] == "create_session", got
        helper = computer.route(db, T, chat="session_helperEXAMPLE", envs=BRIDGE,
                                tools=EVERY_TOOL, url=URL, copy=COPY)
        assert helper["route"] == "ring starter", helper
    # The command marks it stale on the page, once.
    db = _with(_db(WORK), LISTENER, rung_at=app_model.stamp(T - timedelta(minutes=6)), rings=1)
    dump = _dump(db, tmp_path / "dump")
    got = json.loads(_run("route", dump, "--chat", STARTER["chat"], "--envs",
                          _write(tmp_path / "envs.json", BRIDGE), "--tools",
                          ",".join(EVERY_TOOL), "--now", NOW))
    assert got["route"] == "computer session"
    marked = _apply(db, got["batches"])
    assert computer.listener(marked)["stale_at"] == NOW and computer.listener_stale(marked, T)
    # Answering again (woken late) makes it live once more.
    back = _apply(marked, computer.listener_woke(marked, LISTENER["chat"], T + timedelta(
        minutes=1), str(tmp_path / "w"))["batches"])
    assert computer.listener_live(back, T + timedelta(minutes=1))


def _write(path, data) -> str:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    return str(path)


# ------------------------------------------------------------------ who becomes it


def test_the_first_chat_on_the_computer_to_finish_becomes_it_and_is_never_put_away(
        tmp_path, monkeypatch):
    """The first chat on the computer that finishes while there is no live listener stays open
    as it: the starter never archives it, nor does a later chat on the computer. A second
    chat that finishes is put away as before."""
    done = dict(WORK[1], status="done", finished_at=NOW,
                computer_session={"id": "session_macA", "at": NOW, "computer": "Studio Laptop"})
    db = _with(_db((WID, done)))
    later = T + timedelta(hours=1)
    assert computer.waiting(db, later)["finished"] == [{"work": WID, "session": "session_macA"}]
    _as(monkeypatch, "computer", tmp_path)
    bell = tmp_path / "bell.html"
    said = computer.listener_become(db, "session_macA", str(bell), T)
    assert said.startswith("stay:") and "listener-ready" in said and computer.LISTENER_TITLE in said
    assert "<title>" + computer.LISTENER_BELL_TITLE in bell.read_text(encoding="utf-8")
    became = _apply(db, computer.listener_ready(db, "session_macA", LBELL, "Studio Laptop", T,
                                                str(tmp_path / "r")))
    rec = computer.listener(became)
    assert rec["chat"] == "session_macA" and rec["bell"] == LBELL
    title = computer.session_title("People at Harbourline Bank", "Studio Laptop")
    assert rec["title"] == title and computer.listener_live(became, later)
    # Never put away: not by the starter, nor by a later chat on the computer.
    assert computer.waiting(became, later)["finished"] == []
    old = app_model.stamp(T - timedelta(days=1))
    listing = [{"title": title, "status": "idle", "updated_at": old},
               {"title": computer.LISTENER_TITLE, "status": "idle", "updated_at": old}]
    assert [r["title"] for r in computer.archivable(listing, False, later)] == [title]
    assert computer.archivable(listing, False, later,
                               keep=(rec["chat"], rec["title"], computer.LISTENER_TITLE)) == []
    import tidy
    assert tidy.LISTENER_NAME.match(computer.LISTENER_TITLE)
    assert tidy._computer_chat(became) == "session_macA"
    # It finishes its next job and stays; a second chat there is put away as before.
    assert computer.listener_become(became, "session_macA", str(bell), later).startswith("stay:")
    assert computer.listener_become(became, "session_macB", str(bell), later) == ""
    dump = _dump(became, tmp_path / "dump")
    rang = _run("ring", dump, "--chat", "session_macB", "--file", tmp_path / "b2.html",
                "--now", NOW)
    assert rang.startswith("ring: ") and f"url {BELL}" in rang
    # Every job's prompt sends the chat there through that step.
    prompt = computer.session_prompt(WID, "People", URL, "their job search")
    step8 = prompt[prompt.index("8. Wake"):prompt.index("9. Your last")]
    assert "ring \"$D\" --chat <your id>" in step8 and "`stay`" in step8
    assert "archivable \"$D/chats.json\" --dump \"$D\"" in prompt
    # A cloud chat never becomes it.
    _as(monkeypatch, "cloud", tmp_path)
    assert computer.listener_become(db, "session_cloudEXAMPLE", str(bell), T) == ""


# ------------------------------------------------------------------ its wake, and keep-alive


def test_a_wake_takes_the_work_keeps_its_own_bell_or_rests(tmp_path, monkeypatch):
    _as(monkeypatch, "computer", tmp_path)
    me = LISTENER["chat"]
    db = _with(_db(WORK), LISTENER, rung_at=app_model.stamp(T - timedelta(minutes=1)), rings=1)
    got = computer.listener_woke(db, me, T, str(tmp_path / "a"))
    assert got["next"].startswith("take:") and f"prompt --work {WID}" in got["next"]
    woke = _apply(db, got["batches"])
    assert computer.listener(woke)["rings"] == 0 and computer.listener(woke)["answered_at"] == NOW
    # Nothing waiting: its own bell republished at most once an hour, then rest.
    idle = _with(_db(), LISTENER, kept_at=app_model.stamp(T - timedelta(hours=2)))
    got = computer.listener_woke(idle, me, T, str(tmp_path / "b"), path=str(tmp_path / "l.html"))
    assert got["next"].startswith("keep:") and f"url {LBELL}" in got["next"]
    kept = _apply(idle, got["batches"])
    assert computer.listener(kept)["kept_at"] == NOW
    again = computer.listener_woke(kept, me, T + timedelta(minutes=1), str(tmp_path / "c"))
    assert again["next"].startswith("rest:")
    # A chat no longer the listener is told so, and writes nothing.
    gone = computer.listener_woke(kept, "session_oldEXAMPLE", T, str(tmp_path / "d"))
    assert gone["next"].startswith("gone:") and gone["batches"] == []
    steps = "\n".join(computer.listener_steps(URL, me))
    assert f"listener-woke \"$D\" --chat {me}" in steps and "listener-steps" in steps


def test_the_scheduled_task_rings_a_quiet_listener_once_and_never_a_fresh_one(
        tmp_path, monkeypatch):
    """A watch can end after hours with nothing happening: the hourly task, with nothing
    waiting, rings a listener quiet for two hours, and leaves a fresh one alone. One keep-alive
    left unanswered makes it stale, so the next job goes the way it went before."""
    _as(monkeypatch, "computer", tmp_path)
    path = str(tmp_path / "bell.html")
    quiet = _with(_db(), LISTENER, answered_at=app_model.stamp(T - timedelta(hours=3)))
    said = computer.keep_alive(quiet, T, path)
    assert said.startswith("keep-alive: ") and "listener-rung" in said and f"url {LBELL}" in said
    assert "<title>" + computer.LISTENER_BELL_TITLE in open(path, encoding="utf-8").read()
    assert computer.keep_alive(_with(_db(), LISTENER), T, path) == ""
    assert computer.keep_alive(_with(_db()), T, path) == ""
    rung = _apply(quiet, computer.listener_rung(quiet, T, str(tmp_path / "r")))
    assert computer.keep_alive(rung, T + timedelta(minutes=1), path) == ""      # once
    assert computer.listener_stale(rung, T + timedelta(minutes=6))
    assert computer.keep_alive(rung, T + timedelta(hours=1), path) == ""        # stale: left
    # The task's steps run it whenever nothing waits.
    steps = "\n".join(computer.task_steps(URL))
    assert "computer.py keep-alive" in steps and computer.TASK_EVERY_MIN == 60
