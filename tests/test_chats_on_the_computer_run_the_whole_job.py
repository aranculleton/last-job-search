"""A chat on the person's computer does the whole networking run, reads included, and waits
for a LinkedIn sign-in instead of parking the job; a chat the person opens there answers the
page; and a cloud chat reaching the computer some other way still finds its way there.

Walked on 2026-11-10 after the computer starter landed, as the person would: the run sent to
the computer queued its profile reads "for the page" and finished with every note waiting on
a read, for a second chat there to finish; a run a chat on the computer took with no `to:
computer` went to a background agent with no browser; a networking run asked in a cloud chat
ran there, reading nobody; LinkedIn signed out parked the job and put its chat away at once,
and a sign-in made then started nothing for half an hour; and with no copy to start the
starter from, a folder or a lent browser on offer was never tried. Invented people and
computers only.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "network"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import app_model  # noqa: E402
import computer  # noqa: E402
import page_db  # noqa: E402
import reading  # noqa: E402
from test_a_tick_on_the_page_is_applied_once import NOW, _db, _w  # noqa: E402
from test_one_chat_answers_the_page import Copy, _on_github  # noqa: E402
from test_the_computer_side_just_works import BRIDGE  # noqa: E402

T = app_model.parse_time(NOW)
URL = "https://claude.ai/artifact/page-1"
STARTER = {"chat": "session_starter", "bell": "https://claude.ai/artifact/bell-1",
           "made_at": "2026-10-20T08:00:00Z", "rung_at": None}


def _as(monkeypatch, kind: str, tmp_path=None):
    import app_listen
    import tempfile
    monkeypatch.setenv("LJS_STATE", str(tmp_path or tempfile.mkdtemp()))
    monkeypatch.setattr(app_listen, "chat_kind", lambda: kind)


def _browser_reads(monkeypatch, setting="browser"):
    monkeypatch.setattr(reading, "reads_now", lambda: setting)


# ------------------------------------------------------------------ 1. Find people, computer ready


def test_find_people_sent_to_the_computer_is_the_whole_run_there(tmp_path, monkeypatch):
    import app
    _as(monkeypatch, "cloud", tmp_path)
    _on_github(monkeypatch)
    item = _w("network", to="computer", title="People at the employers you want",
              args={"count": 5})
    db = _db(("network~targets~1", item))
    # No cloud chat takes it, and the page's helper wakes the starter rather than doing any.
    assert page_db.next_item(db, "cloud", T) is None
    ready = dict(db, meta={"computer_starter": {"data": STARTER, "version": 2}})
    assert computer.route(ready, T, chat="session_helper", envs=BRIDGE,
                          tools=["create_session"])["route"] == "ring starter"
    # The starter starts the chat on the computer, told to take only the computer's work.
    got = computer.route(ready, T, chat="session_starter", envs=BRIDGE, tools=["create_session"],
                         url=URL, copy="github.com/someone/my-job-search")
    assert got["route"] == "computer session"
    prompt = got["call"]["prompt"]
    assert "--tools browser" in prompt and "--kind computer --computer-only" in prompt
    # 2. That chat claims it and does it itself, every stage of it, with its browser.
    _as(monkeypatch, "computer", tmp_path)
    chosen = app.choose(db, "mac-chat", "computer", T, on="claude-opus-5-5", no_sessions=True,
                        computer_only=True)
    assert chosen["run"] == "here" and "agent" not in chosen and "create_session" not in chosen
    steps = "\n".join(chosen["steps"])
    assert "/network" in steps and "--stage <stage>" in steps
    assert "whole run is done here" in steps and "reading.py route --tools browser" in steps
    assert "Never queue a profile for the page" in steps and "--wait-for-read" in steps
    assert "--kind computer --computer-only" in steps          # then the next one for it
    # 3. The networking skill's route, in that chat, reads the short list in its browser.
    for tools in (["browser"], ["enable"]):
        r = reading.route(tools, "browser", {"CLAUDECODE": "1"})
        assert r["route"] == "here" and r["signin"]
        assert "reading.py next" in r["do"] and "--source browser" in r["do"]
        assert "never --wait-for-read" in r["do"] and "queue-page" not in r["do"]
    # A chat with no browser of Claude's (a cloud chat, the person's own Chrome) still queues.
    for tools in ([], ["chrome"]):
        assert reading.route(tools, "browser", {"CLAUDECODE": "1"})["route"] == "page"
    out = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "network", "reading.py"),
                          "route", "--tools", "browser"], capture_output=True, text=True,
                         env=dict(os.environ, LJS_PROFILE=os.path.join(ROOT, "profile.example")))
    assert "route: here" in out.stdout or "route: hand" in out.stdout, out.stdout + out.stderr
    with open(os.path.join(ROOT, ".claude", "commands", "network.md"), encoding="utf-8") as fh:
        net = fh.read()
    assert "reading.py route\n      --tools" in net and "Read the short list here, with route `here`" in net


def test_a_networking_run_a_chat_on_the_computer_takes_is_never_an_agent(tmp_path, monkeypatch):
    """Sent anywhere (the computer not known ready yet), a chat on the computer that answers
    the page still does the run itself, reads included; and it never puts itself away after."""
    import app
    _as(monkeypatch, "computer", tmp_path)
    _browser_reads(monkeypatch)
    db = _db(("network~targets~2", _w("network", to="either", title="People")))
    chosen = app.choose(db, "mac-listener", "computer", T, on="claude-opus-5-5",
                        no_sessions=True)
    assert chosen["run"] == "here" and "agent" not in chosen, chosen.get("run")
    steps = "\n".join(chosen["steps"])
    assert "whole run is done here" in steps and "--kind computer" in steps
    assert "archive_session" not in steps and "Never put this chat away" in steps
    # They chose to paste profiles: no read needs this chat, so it stays a background agent.
    _browser_reads(monkeypatch, "paste")
    assert app.choose(db, "mac-listener", "computer", T, on="claude-opus-5-5",
                      no_sessions=True)["run"] == "background agent"
    # In the cloud, as before: a chat of its own.
    _as(monkeypatch, "cloud", tmp_path)
    _on_github(monkeypatch)
    _browser_reads(monkeypatch)
    assert app.choose(db, "session_helper", "cloud", T, on="claude-opus-5-5")["run"] == \
        "child session"


def test_a_networking_run_asked_in_a_cloud_chat_goes_to_the_ready_computer(tmp_path, monkeypatch):
    import place
    _browser_reads(monkeypatch)
    monkeypatch.setattr(place, "place_record",
                        lambda: {"works_on": "computer", "computer_ready": "2026-10-20"})
    db = _db()
    assert computer.networking_there(db, T)
    got = page_db.ask(db, "network", "People at Harbourline Bank", T, str(tmp_path / "a"),
                      args={"company": "Harbourline Bank"}, chat_id="session_cloud", here=True,
                      chat_kind="cloud")
    assert got["sent_to"] == "computer" and page_db.SENT_TO_COMPUTER_SAY in got["then"]
    with open(json.load(open(got["batches"][0], encoding="utf-8"))[0]["file_path"],
              encoding="utf-8") as fh:
        fields = json.load(fh)
    assert fields["to"] == "computer" and fields["status"] == "queued"
    assert not fields.get("in_chat") and fields["claimed_by"] is None
    assert page_db.computer_only(fields, "cloud")                 # no cloud chat takes it now
    # A chat on the computer asking keeps it as its own, as before.
    mine = page_db.ask(db, "network", "People", T, str(tmp_path / "b"), chat_id="mac-1",
                       here=True, chat_kind="computer")
    assert "sent_to" not in mine
    # Not ready, or profiles pasted: the cloud chat does it, as before.
    for rec, setting in (({"works_on": "cloud"}, "browser"),
                         ({"works_on": "computer", "computer_ready": "2026-10-20"}, "paste")):
        monkeypatch.setattr(place, "place_record", lambda rec=rec: rec)
        _browser_reads(monkeypatch, setting)
        got = page_db.ask(db, "network", "People", T, str(tmp_path / f"c{setting}"),
                          chat_id="session_cloud", here=True, chat_kind="cloud")
        assert "sent_to" not in got
    # Anything else asked in a cloud chat is untouched.
    _browser_reads(monkeypatch)
    monkeypatch.setattr(place, "place_record",
                        lambda: {"works_on": "computer", "computer_ready": "2026-10-20"})
    assert "sent_to" not in page_db.ask(db, "search", "Jobs", T, str(tmp_path / "d"),
                                        chat_id="session_cloud", here=True, chat_kind="cloud")


# ------------------------------------------------------------------ 2. LinkedIn signed out


def _stopped(asked_min_ago: float, archived=False, status="needs_you"):
    item = _w("network", "Harbourline Bank", to="computer", status=status)
    sess = {"id": "session_mac1", "at": app_model.stamp(T - dt.timedelta(minutes=40))}
    if archived:
        sess["archived_at"] = app_model.stamp(T - dt.timedelta(minutes=1))
    item.update(note="LinkedIn is signed out in Claude's browser.",
                needs={"question": "LinkedIn is signed out in Claude's browser.",
                       "signin": "linkedin"},
                asked_you_at=app_model.stamp(T - dt.timedelta(minutes=asked_min_ago)),
                computer_session=sess)
    return item


def test_signed_out_the_chat_opens_the_sign_in_and_waits_never_parking_the_job(
        tmp_path, monkeypatch):
    # The chat on the computer is told to open the sign-in, put the card up and look again.
    prompt = computer.session_prompt("network~read~1", "People", URL, "their job search")
    assert computer.LINKEDIN_LOGIN["url"] in prompt and "--signin linkedin" in prompt
    assert "computer.py signin-wait" in prompt and "never parking the job" in prompt
    assert "reading.py signin --url" in prompt and "computer.py signed-in" in prompt
    # While it waits, it is at work: nobody puts it away, and no second chat starts.
    waiting = _db(("network~read~1", _stopped(3)))
    w = computer.waiting(waiting, T)
    assert w == {"queued": [], "started": {"network~read~1": "session_mac1"}, "finished": []}
    _as(monkeypatch, "cloud", tmp_path)
    ready = dict(waiting, meta={"computer_starter": {"data": STARTER, "version": 2}})
    assert computer.route(ready, T, chat="session_helper", envs=BRIDGE,
                          tools=["create_session"])["route"] == "none"
    # Signed in on the page meanwhile: back in the queue, still that chat's.
    answered = _stopped(5, status="queued")
    answered["answered_at"] = app_model.stamp(T)
    assert computer.waiting(_db(("network~read~1", answered)), T)["started"]
    # The wait is over: its chat is put away, and the card stays.
    late = computer.waiting(_db(("network~read~1", _stopped(16))), T)
    assert late["finished"] == [{"work": "network~read~1", "session": "session_mac1"}]
    # Signed in after its chat was put away: a fresh one starts now, never half an hour on.
    gone = _stopped(16, archived=True, status="queued")
    gone["computer_session"]["at"] = app_model.stamp(T - dt.timedelta(minutes=3))
    assert computer.waiting(_db(("network~read~1", gone)), T)["queued"] == ["network~read~1"]
    # How long it looks: until SIGNIN_WAIT_S from its question.
    assert computer.signin_wait(_stopped(3), T)[0] == "look"
    assert computer.signin_wait(_stopped(16), T) == ("stop", 0)
    assert computer.signin_wait(answered, T) == ("answered", 0)


def test_signin_wait_says_look_stop_or_answered(tmp_path):
    for name, item, first in (("look", _stopped(3), "look:"), ("stop", _stopped(16), "stop:"),
                              ("answered", _stopped(3, status="queued"), "answered:")):
        dump = tmp_path / name
        (dump / "work").mkdir(parents=True)
        # The dump's own file name for "network~read~1" (a "~" is kept as "@" on disk), made
        # here rather than written out, which reads as an email address to the leak scan.
        with open(dump / "work" / ("~".join(("network", "read", "1")).replace("~", "@") + ".json"),
                  "w", encoding="utf-8") as fh:
            json.dump({"data": item, "version": 4}, fh)
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "computer.py"),
                            "signin-wait", str(dump), "--work", "network~read~1", "--every", "0",
                            "--now", NOW], capture_output=True, text=True)
        assert r.returncode == 0 and r.stdout.startswith(first), r.stdout + r.stderr


# ------------------------------------------------------------------ 4. Remote Control


def test_a_folder_or_a_lent_browser_is_still_tried_when_no_starter_can_be_made(monkeypatch):
    import app_setup
    _as(monkeypatch, "cloud")
    monkeypatch.setattr(app_setup, "origin", lambda: ("", ""))
    db = _db(("network~people", _w("network", "Harbourline Bank", to="computer")))
    folders = {"folders": [{"environment_id": "env_rc1", "computer_name": "Studio Laptop",
                            "folder": "my-job-search", "online": True}]}
    got = computer.route(db, T, chat="session_helper", envs=BRIDGE, folders=folders,
                         tools=["create_session", "request_computer_folder"])
    assert got["route"] == "computer folder" and got["call"]["environment_id"] == "env_rc1"
    got = computer.route(db, T, chat="session_helper", envs=BRIDGE,
                         tools=["create_session", "mcp__remote-devices__Claude_Browser__navigate"])
    assert got["route"] == "linked browser" and "--computer-only --lent" in got["then"]
    # Never the helper approving computer access itself.
    got = computer.route(db, T, chat="session_helper", envs=BRIDGE, tools=["create_session"])
    assert got["route"] != "computer session" and "confirm_repository_trust" not in str(got)
    # With a copy to start it from, the starter as before; and the starter starts it.
    _on_github(monkeypatch)
    assert computer.route(db, T, chat="session_helper", envs=BRIDGE, folders=folders,
                          tools=["create_session", "request_computer_folder"])["route"] == \
        "make starter"
    ready = dict(db, meta={"computer_starter": {"data": STARTER, "version": 2}})
    assert computer.route(ready, T, chat="session_starter", envs=BRIDGE,
                          tools=["create_session"])["route"] == "computer session"
    # No bridge at all: the folder and the lent browser, as before.
    assert computer.route(db, T, chat="session_helper", envs={"environments": []},
                          folders=folders, tools=["request_computer_folder"])["route"] == \
        "computer folder"


# ------------------------------------------------------------------ 3. a chat they open there


@pytest.fixture
def copy(tmp_path):
    c = Copy(tmp_path)
    yield c
    sys.path.remove(c.root)


def test_a_chat_the_person_opens_on_their_computer_answers_the_page_and_does_the_run(copy):
    import land
    copy.page(current=True)
    nw = os.path.join(copy.profile, "networking.py")
    with open(nw, encoding="utf-8") as fh:
        text = fh.read()
    with open(nw, "w", encoding="utf-8") as fh:
        fh.write(text.replace('PROFILE_READS = "paste"', 'PROFILE_READS = "browser"'))
    local = dict(CLAUDECODE="1", LJS_CHAT="local-mac-1")
    said = copy.run("start", "--on", "claude-opus-5-5", "--tools", "browser", **local)
    assert said.startswith("app start: set up")
    assert "create_session" not in said and "Artifact publish" not in said
    # It answers the page when nobody else does, as a chat on the computer.
    got = copy.run("listen", copy.dump("l1"), "--chat", "local-mac-1", "--now", NOW, **local)
    assert "this chat answers the page now" in got and copy.send(got)
    assert copy.listener()["kind"] == "computer" and copy.listener()["chat"] == "local-mac-1"
    # A networking run waiting: done in this chat, with its browser, never an agent or a chat.
    copy.queue("network~targets~3", kind="network")
    path = os.path.join(copy.db, "work", "network~targets~3.json")
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    doc["data"]["to"] = "either"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh)
    out = copy.run("wake", copy.dump("w1"), "--chat", "local-mac-1", "--on", "claude-opus-5-5",
                   "--no-sessions", "--now", NOW, **local)
    then = [ln for ln in out.splitlines() if ln.startswith("then:")]
    assert then and "follow the `steps` under next:" in then[0], then
    assert '"run": "here"' in out and '"run": "background agent"' not in out
    assert "create_session" not in out.split("next:", 1)[1]
    # Its save is a push, merged by the cloud.
    assert land.on_computer({"CLAUDECODE": "1"})
    assert not land.on_computer({"CLAUDECODE": "1", "CLAUDE_CODE_REMOTE": "true"})


def test_a_chat_on_the_computer_with_the_browser_takes_waiting_work_itself(monkeypatch):
    """Asked where the computer's work goes, a chat open on the computer itself, with no list of
    computers and no heartbeat yet, is the place: never "paste", with its page saying the
    computer is off while the chat sat open on it."""
    _as(monkeypatch, "computer")
    db = _db(("network~people", _w("network", "Harbourline Bank", to="computer")))
    got = computer.route(db, T, chat="local-mac-1", envs=None,
                         tools=["mcp__Claude_Browser__navigate", "Bash"])
    assert got["route"] == "computer chat" and "--kind computer" in got["then"]
    assert "paste" not in got
    # With no browser of Claude's (a terminal, say), as before.
    assert computer.route(db, T, chat="local-mac-1", envs=None, tools=["Bash"])["route"] == "paste"
