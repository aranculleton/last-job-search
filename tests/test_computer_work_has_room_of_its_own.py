"""Work for the person's computer is routed and capped on its own: a chat the app started there
is never taken for a chat listening on the computer, cloud jobs never fill the computer's room,
one computer chat reads at a time, and the computer used is one that can take it.

From the builder audit of 2026-11-10 (CC-7, CC-8, CC-16, CC-22): a computer job chat's claim
read as "your computer's chat takes it" for twenty minutes after that chat had stopped; three
cloud searches or drafts left the computer chat with nothing it could take, and a read of named
people waited behind a cloud networking run's lock; two jobs started two chats moving one
browser; and with two computers, the first listed was used even when it was the wrong one.
Invented people and computers only.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "network"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import app_model  # noqa: E402
import computer  # noqa: E402
import page_db  # noqa: E402
from test_a_tick_on_the_page_is_applied_once import NOW, _db, _w  # noqa: E402
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


def _sent(batches) -> dict:
    """{(collection, doc id): fields} of every write in the batch files."""
    out = {}
    for path in batches:
        with open(path, encoding="utf-8") as fh:
            for e in json.load(fh):
                fields = e.get("data")
                if fields is None and e.get("file_path"):
                    with open(e["file_path"], encoding="utf-8") as f2:
                        fields = json.load(f2)
                coll = page_db._LOGICAL.get(e["collection"], e["collection"])
                out[(coll, e["doc_id"])] = fields or {}
    return out


# ------------------------------------------------------------------ CC-16


def test_a_computer_job_chat_is_never_counted_as_the_computer_listening(tmp_path, monkeypatch):
    """Its claim writes its heartbeat as at work, not listening, so the next computer job is
    still started for: counted as listening, `route` said "Your computer's chat takes it" for
    twenty minutes after that chat had stopped."""
    import app
    _as(monkeypatch, "computer", tmp_path)
    db = _db(("network~read~1", _w("network", "Harbourline Bank", to="computer",
                                   title="Reading on your computer")))
    chosen = app.choose(db, "mac-job", "computer", T, on="claude-opus-5-5", no_sessions=True,
                        computer_only=True, claim_out=str(tmp_path / "claim"))
    beat = _sent(chosen["batches"]).get(("chats", "mac-job"))
    assert beat is not None and beat["kind"] == "computer"
    assert beat.get("watching") is False, beat
    # A second piece of work for the computer is still routed to a new chat.
    _as(monkeypatch, "cloud", tmp_path)
    after = _db(("network~read~1", dict(_w("network", "Harbourline Bank", to="computer"),
                                        status="running", claimed_by="mac-job", claimed_at=NOW)),
                ("network~read~2", _w("network", "Fernway Insurance", to="computer")))
    after["chats"] = {"mac-job": {"data": beat, "version": 1}}
    after["meta"] = {"computer_starter": {"data": STARTER, "version": 2}}
    got = computer.route(after, T, chat="session_helper", envs=BRIDGE, tools=["create_session"])
    assert got["route"] != "computer chat", got
    # A chat the person opened on the computer, answering the page, still counts as listening.
    _as(monkeypatch, "computer", tmp_path)
    db2 = _db(("network~read~3", _w("network", "Fernway Insurance", to="computer")))
    mine = app.choose(db2, "mac-listener", "computer", T, on="claude-opus-5-5",
                      no_sessions=True, claim_out=str(tmp_path / "claim2"))
    assert _sent(mine["batches"])[("chats", "mac-listener")].get("watching") is not False


# ------------------------------------------------------------------ CC-7


def _live(kind: str, title: str, **kw) -> dict:
    return dict(_w(kind, title), status="running", claimed_by="session_cloud",
                claimed_at=NOW, lease_until=app_model.stamp(T + __import__("datetime").timedelta(
                    minutes=20)), claimed_as="cloud", **kw)


def test_cloud_jobs_never_fill_the_computers_room(tmp_path):
    """Three cloud searches, drafts or preps live (ten may run in the cloud) left the chat on
    the computer with nothing it could take, so it stopped and another was started half an
    hour on. The computer's cap counts the computer's own jobs alone."""
    read = _w("network", "", to="computer", title="Reading 2 profiles on your computer",
              args={"contacts": ["c-ana-1", "c-bo-2"], "read_first": True, "rewrite": True})
    db = _db(("search~1", _live("search", "Jobs")), ("draft~1", _live("draft", "Fernway Bank")),
             ("network~cloud~1", _live("network", "")), ("network~read~1", read))
    got = page_db.next_item(db, "computer", T, cap=page_db.HEAVY_CAP, to_only="computer")
    assert got is not None and got["work"] == "network~read~1", got
    # A read of named people takes each person's lock, never the one a whole networking run
    # in the cloud holds.
    assert "network" not in got["locks"]
    assert sorted(got["locks"]) == ["contact~c-ana-1", "contact~c-bo-2"]
    # The computer's own jobs still fill its room.
    mine = {f"network~read~{n}": dict(_live("network", ""), to="computer", claimed_as="computer")
            for n in (2, 3, 4)}
    full = _db(*mine.items(), ("network~read~1", read))
    assert page_db.next_item(full, "computer", T, cap=page_db.HEAVY_CAP, to_only="computer") is None
    # A chat answering the page in the cloud counts every job, as before.
    assert page_db.next_item(_db(("search~1", _live("search", "Jobs")),
                                 ("draft~1", _live("draft", "Fernway Bank")),
                                 ("prep~1", _live("prep", "Kestrel")),
                                 ("search~2", _w("search", "More jobs"))), "cloud", T,
                             cap=3) is None
    # A networking run in the cloud with no employer still holds the whole run's lock.
    assert page_db.locks_for(_w("network", "")) == ["network"]


# ------------------------------------------------------------------ CC-23


def test_the_computers_app_version_is_compared_and_shown_when_older(monkeypatch, tmp_path):
    """"Behind" was any difference, a newer computer too, and the brief then promised its next
    chat would take the update; and nothing on the page ever showed it."""
    import datetime as dt

    def db(version):
        beat = computer.beat_fields("Studio Laptop", T - dt.timedelta(minutes=5),
                                    browser="shown", linkedin="in", version=version, task=False)
        return {"chats": {computer.beat_id("Studio Laptop"): {"data": beat, "version": 1}},
                "work": {}}
    assert computer.state(db("4.15.0"), T, envs=BRIDGE, version="4.14.0")["behind"] is False
    assert computer.state(db("4.14.0"), T, envs=BRIDGE, version="4.14.0")["behind"] is False
    assert computer.state(db("4.9.2"), T, envs=BRIDGE, version="4.14.0")["behind"] is True
    assert not any("older version" in ln for ln in computer.check(db("4.15.0"), T, envs=BRIDGE,
                                                                 version="4.14.0"))
    st = computer.state(db("4.9.2"), T, envs=BRIDGE, version="4.14.0")
    model, _ = app_model.build(T.date(), T, only=("where",), computer=st)
    assert "older version of the app" in model["where"]["computer"]["say"]
    same = computer.state(db("4.14.0"), T, envs=BRIDGE, version="4.14.0")
    model2, _ = app_model.build(T.date(), T, only=("where",), computer=same)
    assert "older version" not in model2["where"]["computer"]["say"]


# ------------------------------------------------------------------ CC-21


def test_the_heartbeat_names_the_computer_itself(tmp_path, monkeypatch):
    """The chat was told to pass --name "<this computer's name>" and typed "Mac": a second
    record beside the real one. The name is worked out in code; a typed one changes nothing."""
    # The computer's own name first: the one kept in place.json travels with the copy, so two
    # computers both wrote under it (the independent review, 2026-11-11).
    import place
    import platform
    monkeypatch.setattr(computer.sys, "platform", "linux")
    monkeypatch.setattr(place, "place_record", lambda: {"computer_name": "Old Desktop"})
    monkeypatch.setattr(platform, "node", lambda: "studio-laptop.local")
    assert computer.this_computer("Mac") == "studio-laptop"
    assert computer.beat_id(computer.this_computer("Mac")) == computer.beat_id("Studio Laptop")
    monkeypatch.setattr(platform, "node", lambda: "old-desktop")
    assert computer.this_computer("Mac") == "old-desktop"
    # Where the computer gives no name, the one kept, then the one typed.
    monkeypatch.setattr(platform, "node", lambda: "")
    assert computer.this_computer("Mac") == "Old Desktop"
    monkeypatch.setattr(place, "place_record", lambda: {})
    assert computer.this_computer("Mac") == "Mac"
    # The prompt never asks the chat to type it.
    prompt = computer.session_prompt("network~read~1", "Reading", URL, "their job search")
    assert "this computer's name" not in prompt and "computer.py beat" in prompt
    # The command takes no name and still writes the record.
    import json
    import subprocess
    dump = tmp_path / "dump"
    (dump / "beats").mkdir(parents=True)
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "computer.py"), "beat",
                        str(dump), "--browser", "shown", "--linkedin", "in"],
                       env=dict(os.environ, LJS_STATE=str(tmp_path / "s")), capture_output=True,
                       text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    entry = json.load(open(json.loads(r.stdout)["batches"][0], encoding="utf-8"))[0]
    assert entry["doc_id"].startswith(computer.BEAT_PREFIX), entry


# ------------------------------------------------------------------ CC-22


def test_with_two_computers_the_one_that_can_take_it_is_used(tmp_path, monkeypatch):
    """The first computer listed was always used, with no fallback."""
    import datetime as dt
    import place
    monkeypatch.setattr(place, "place_record", lambda: {})
    _as(monkeypatch, "cloud", tmp_path)
    envs = {"environments": [
        {"environment_id": "env_old", "name": "Old Desktop:Documents:aa11",
         "description": "Bridge environment (Old Desktop)", "kind": "bridge", "state": "active"},
        {"environment_id": "env_lap", "name": "Studio Laptop:Documents:ab12",
         "description": "Bridge environment (Studio Laptop)", "kind": "bridge",
         "state": "active"}]}
    lap = computer.beat_fields("Studio Laptop", T - dt.timedelta(minutes=5), browser="shown",
                               linkedin="in", version="4.14.0", task=False)
    old = computer.beat_fields("Old Desktop", T - dt.timedelta(days=3), browser="none",
                               linkedin="out", version="4.14.0", task=False)
    db = _db(("network~read~1", _w("network", "Harbourline Bank", to="computer")))
    db["chats"] = {computer.beat_id("Studio Laptop"): {"data": lap, "version": 1},
                   computer.beat_id("Old Desktop"): {"data": old, "version": 1}}
    db["meta"] = {"computer_starter": {"data": STARTER, "version": 2}}
    got = computer.route(db, T, chat="session_starter", envs=envs, tools=["create_session"],
                         url=URL, copy="github.com/someone/my-job-search")
    assert got["route"] == "computer session" and got["call"]["environment_id"] == "env_lap", got
    # Only one there, or none known by its heartbeat: the first listed, as before.
    assert computer.pick_bridge(computer.bridges(envs), {}, T)[0]["id"] == "env_old"
    # The one the setup was tested on, where no heartbeat says more.
    monkeypatch.setattr(place, "place_record", lambda: {"computer_name": "Studio Laptop"})
    assert computer.pick_bridge(computer.bridges(envs), {}, T)[0]["id"] == "env_lap"
    # One switched off is never listed at all.
    envs["environments"][1]["state"] = "inactive"
    assert [b["id"] for b in computer.bridges(envs)] == ["env_old"]


# ------------------------------------------------------------------ second audit, C7


def test_reads_on_the_computer_never_fill_the_clouds_room():
    """The cap counted computer and cloud jobs together both ways: three reads on the computer
    held a cloud search back as well."""
    mine = {f"network~read~{n}": dict(_live("network", ""), to="computer", claimed_as="computer",
                                      args={"contacts": [f"c-{n}"], "read_first": True})
            for n in (1, 2, 3)}
    db = _db(*mine.items(), ("search~1", _w("search", "Jobs")))
    got = page_db.next_item(db, "cloud", T, cap=3)
    assert got is not None and got["work"] == "search~1", got
    # A chat on the computer answering the page counts every job there, as before.
    assert page_db.next_item(db, "computer", T, cap=3) is None


# ------------------------------------------------------------------ second audit, C8


def test_a_chat_started_for_one_job_checks_the_job_sites_only_for_a_search(monkeypatch):
    """Every fresh job chat's container probed some 35 job sites, about 8 seconds, even for a
    draft or a prep that reads none of them."""
    import app_setup
    monkeypatch.setenv("CLAUDE_CODE_REMOTE", "true")
    monkeypatch.setattr(app_setup, "job_sites", lambda: {})
    assert app_setup.job_sites_due("") is True                 # the chat that answers the page
    assert app_setup.job_sites_due("search~20261110T0900-ab") is True
    for wid in ("draft~20261110T0900-ab", "prep~1", "network~read~1", "update~refresh-x"):
        assert app_setup.job_sites_due(wid) is False, wid
    import datetime as dt
    monkeypatch.setattr(app_setup, "job_sites", lambda: {"checked": dt.date.today().isoformat()})
    assert app_setup.job_sites_due("") is False                # once a day
    monkeypatch.setenv("CLAUDE_CODE_REMOTE", "false")
    monkeypatch.setattr(app_setup, "job_sites", lambda: {})
    assert app_setup.job_sites_due("") is False                # a chat on a computer


# ------------------------------------------------------------------ CC-8


def test_one_chat_at_a_time_on_the_computer(tmp_path, monkeypatch):
    """`route` started one chat per queued job: two jobs, two chats moving one browser pane."""
    import datetime as dt
    _as(monkeypatch, "cloud", tmp_path)
    running = dict(_w("network", "Harbourline Bank", to="computer"), status="running",
                   claimed_by="session_mac1", claimed_as="computer", claimed_at=NOW,
                   stage_at=NOW, lease_until=app_model.stamp(T + dt.timedelta(minutes=25)),
                   computer_session={"id": "session_mac1",
                                     "at": app_model.stamp(T - dt.timedelta(minutes=50))})
    db = _db(("network~read~1", running),
             ("network~read~2", _w("network", "Fernway Insurance", to="computer")))
    db["meta"] = {"computer_starter": {"data": STARTER, "version": 2}}
    for chat in ("session_starter", "session_helper"):
        got = computer.route(db, T, chat=chat, envs=BRIDGE, tools=["create_session"], url=URL)
        assert got["route"] == "computer busy" and "call" not in got, (chat, got)
    # And the chat at work there takes it next, as a chat on the computer.
    import app
    assert "--computer-only" in app._next_job(URL, kind="computer", computer_only=True)
    # Once that chat's work is over and its last steps with it, the next one is started.
    done = dict(running, status="done", finished_at=NOW)
    db["work"]["network~read~1"]["data"] = done
    assert computer.route(db, T, chat="session_starter", envs=BRIDGE, tools=["create_session"],
                          url=URL)["route"] == "computer busy"
    after = T + dt.timedelta(seconds=computer.END_WAIT_S)
    assert computer.route(db, after, chat="session_starter", envs=BRIDGE,
                          tools=["create_session"], url=URL)["route"] == "computer session"


# ------------------------------------------------------------------ CC-18


def test_on_the_computer_is_judged_by_the_clouds_own_markers_not_one_flag(monkeypatch):
    """A chat on the computer and a cloud chat were told apart by CLAUDE_CODE_REMOTE alone. A
    session started over Remote Control that sets it would have claimed as a cloud chat,
    opened a pull request from the person's computer and taken the page."""
    import app_listen
    import land
    import place
    cloud = {"CLAUDECODE": "1", "CLAUDE_CODE_REMOTE": "true",
             "CLAUDE_CODE_CONTAINER_ID": "container_example1",
             "SSL_CERT_FILE": "/root/.ccr/ca-bundle.crt"}
    computer_chat = {"CLAUDECODE": "1"}
    remote_control = {"CLAUDECODE": "1", "CLAUDE_CODE_REMOTE": "true",
                      "CLAUDE_CODE_REMOTE_SESSION_ID": "cse_example2"}
    # Only the proxy's certificate in place is enough, and so is the container alone.
    assert place.in_cloud({"CLAUDE_CODE_REMOTE": "true",
                           "NODE_EXTRA_CA_CERTS": "/root/.ccr/ca-bundle.crt"})
    assert place.in_cloud({"CLAUDE_CODE_REMOTE": "true", "CLAUDE_CODE_CONTAINER_ID": "c"})
    assert place.in_cloud(cloud) and not land.on_computer(cloud)
    assert not place.in_cloud(computer_chat) and land.on_computer(computer_chat)
    assert not place.in_cloud(remote_control) and land.on_computer(remote_control)
    # A bridge environment is the person's computer whatever else is set.
    assert not place.in_cloud(dict(cloud, CLAUDE_CODE_REMOTE_ENVIRONMENT_TYPE="bridge"))
    # The chat's own kind follows the same rule.
    for env, kind in ((cloud, "cloud"), (computer_chat, "computer"), (remote_control, "computer")):
        for k in ("CLAUDE_CODE_REMOTE", "CLAUDE_CODE_REMOTE_ENVIRONMENT_TYPE",
                  *place.CLOUD_MARKERS, *place.CLOUD_CA_VARS):
            monkeypatch.delenv(k, raising=False)
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        monkeypatch.setattr(place, "CCR_DIR", "/nonexistent-ccr-folder")
        assert app_listen.chat_kind() == kind, env


# ------------------------------------------------------------------ review 6


def test_every_cloud_check_is_the_one_in_place_in_cloud(tmp_path):
    """Only the chat's kind and the save followed place.in_cloud; the update check, the job
    sites, the setup's own lines, the brief's time zone, the job search's pace and a report
    still read CLAUDE_CODE_REMOTE alone, so a session over Remote Control on the person's
    computer that sets it was a cloud chat to them (sync_app's _unsaved committed another
    chat's half-written files there)."""
    import json
    import subprocess
    probe = ("import json, os, sys; sys.path[:0] = ['tools', 'tools/network']; "
             "import sync_app, env_check, scrape_wide, app_setup, report, person; "
             "env = {'CLAUDE_CODE_REMOTE': 'true'}; "
             "print(json.dumps({'sync_app': sync_app.CLOUD, 'env_check': env_check.CLOUD, "
             "'scrape_wide': scrape_wide.CLOUD, 'app_setup': app_setup._cloud(), "
             "'job_sites': app_setup.job_sites_due(''), "
             "'report': report._where() == 'a cloud chat'}))")
    base = {k: v for k, v in os.environ.items()
            if not k.startswith(("CCR_", "CLAUDE_CODE_CONTAINER")) and k not in (
                "SSL_CERT_FILE", "NODE_EXTRA_CA_CERTS", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE",
                "CLAUDE_CODE_REMOTE_ENVIRONMENT_TYPE")}
    base.update(CLAUDE_CODE_REMOTE="true", LJS_CCR_DIR=str(tmp_path / "no-such-folder"),
                LJS_STATE=str(tmp_path / "state"))

    def ask(**extra):
        r = subprocess.run([sys.executable, "-c", probe], cwd=ROOT, env=dict(base, **extra),
                           capture_output=True, text=True, encoding="utf-8")
        assert r.returncode == 0, r.stderr
        return json.loads(r.stdout.strip().splitlines()[-1])
    remote_control = ask()
    assert not any(remote_control.values()), remote_control
    cloud = ask(CLAUDE_CODE_CONTAINER_ID="container_example")
    assert all(cloud[k] for k in ("sync_app", "env_check", "scrape_wide", "app_setup",
                                  "report")), cloud
    # The cloud's own folder, where its variables are not given.
    folder = tmp_path / "ccr"
    folder.mkdir()
    assert ask(LJS_CCR_DIR=str(folder))["sync_app"] is True
    # The brief's day: the person's own zone only in the cloud.
    import person
    assert person.cloud_day({"CLAUDE_CODE_REMOTE": "true"}) == ""


# ------------------------------------------------------------------ review 16 (CC-8)


def test_any_chat_reading_with_the_computers_browser_keeps_a_second_from_starting(
        tmp_path, monkeypatch):
    """busy_there counted only the chats the app started on the computer: a cloud chat lent
    the computer's browser, or one the person opened there, reading at the same moment, did
    not stop a second chat from moving the same browser."""
    import datetime as dt
    _as(monkeypatch, "cloud", tmp_path)
    lent = dict(_w("network", "Harbourline Bank", to="computer"), status="running",
                claimed_by="session_helper", claimed_as="computer", claimed_at=NOW,
                stage_at=NOW, lease_until=app_model.stamp(T + dt.timedelta(minutes=25)))
    db = _db(("network~read~1", lent),
             ("network~read~2", _w("network", "Fernway Insurance", to="computer")))
    db["meta"] = {"computer_starter": {"data": STARTER, "version": 2}}
    assert computer.busy_there(db, T) == "session_helper"
    got = computer.route(db, T, chat="session_starter", envs=BRIDGE, tools=["create_session"],
                         url=URL)
    assert got["route"] == "computer busy", got
    # A cloud job (claimed as the cloud's) uses no browser of the computer's.
    cloud = dict(lent, claimed_as="cloud", kind="draft")
    assert computer.busy_there(_db(("draft~1", cloud)), T) == ""


# ------------------------------------------------------------------ review 14 (CC-19)


def test_a_job_chat_the_person_types_into_can_do_the_work_and_none_starts_beside_it(
        tmp_path, monkeypatch):
    """A job chat on the computer whose own work is done, typed into by the person, must be able
    to read (no gate on a claim it no longer holds, sign-ins asked in the chat), and work it
    takes up there (claimed in the chat, as the page fixer's app.py resume does) keeps the
    starter from starting a second chat for it."""
    import datetime as dt
    import app_listen
    import app_setup
    import reading
    monkeypatch.setattr(app_setup, "_local_file", lambda name: str(tmp_path / name))
    monkeypatch.setattr(app_listen, "chat_kind", lambda: "computer")
    app_setup.record_claim("network~read~1", "session_mac1")
    app_setup.end_claim("network~read~1")
    assert reading.app_job_here() == ""
    assert reading.claim_gate("network~read~2", "", 10 ** 10) == ("go", "")
    # Taken up in the chat: claimed by it, in_chat, as a computer chat's.
    taken = dict(_w("network", "Fernway Insurance", to="computer"), status="running",
                 claimed_by="session_mac1", claimed_as="computer", in_chat=True,
                 claimed_at=NOW, stage_at=NOW,
                 lease_until=app_model.stamp(T + dt.timedelta(minutes=25)))
    db = _db(("network~read~2", taken),
             ("network~read~3", _w("network", "Harbourline Bank", to="computer")))
    db["meta"] = {"computer_starter": {"data": STARTER, "version": 2}}
    monkeypatch.setattr(app_listen, "chat_kind", lambda: "cloud")
    assert computer.route(db, T, chat="session_starter", envs=BRIDGE, tools=["create_session"],
                          url=URL)["route"] == "computer busy"
    assert "network~read~2" not in computer.waiting(db, T)["queued"]


def test_a_sign_in_on_the_page_keeps_a_second_chat_off_the_browser(tmp_path, monkeypatch):
    """The page signs the person in to LinkedIn inside the Claude app, in its own reading
    panel, with no claim of its own: a chat started on the computer meanwhile moved the same
    browser and took the sign-in page away from them (the independent review, 2026-11-11,
    CC-8). Held while the question is fresh, never longer."""
    import datetime as dt
    _as(monkeypatch, "cloud", tmp_path)
    parked = dict(_w("network", "Harbourline Bank", to="computer"), status="needs_you",
                  claimed_as="cloud", asked_you_at=app_model.stamp(T - dt.timedelta(minutes=2)),
                  needs={"question": "Sign in to LinkedIn", "signin": "linkedin"})
    db = _db(("network~read~1", parked),
             ("network~read~2", _w("network", "Fernway Insurance", to="computer")))
    db["meta"] = {"computer_starter": {"data": STARTER, "version": 2}}
    assert computer.busy_there(db, T) == computer.SIGNING_IN
    got = computer.route(db, T, chat="session_starter", envs=BRIDGE, tools=["create_session"],
                         url=URL)
    assert got["route"] == "computer busy" and "signed in" in got["line"], got
    # An old question holds nothing: the browser is free again.
    later = T + dt.timedelta(seconds=computer.SIGNIN_WAIT_S + 60)
    assert computer.busy_there(db, later) == ""
