"""Journeys from the page to the person's computer, played end to end.

The maintainer's own Mac, 4.15.0, 2026-11-11: a LinkedIn read waited 16 hours. The page said the
Mac was off though its connection made that day was active; Start it now did nothing; the chat
told them to go and type in another chat. The local review found why (items 1, 2, 3, 8 and 9);
each journey here walks the whole way a person's tap takes, with the tools each chat really
has, and holds what they see:

- J1, Start it now: the page's chat in the cloud (its subagent has the page's tools and no
  remote ones), the Mac on today by the person's list, its check-in 26 hours old, a read for it
  waiting. The wake names it; the subagent hands the list back; the listener lists the
  computers and routes, which rings or makes the starter; the row is never off, and no card.
- J4, over every chat: whatever tools and list a chat has, every tool `route` names is one it
  has or one it hands back, and "off" is never said with a fresh check-in or a computer on.
- J6, names and folders: two connections on one Mac, a heartbeat named by the Mac itself, the
  copy four folders down: the copy's folder is chosen, and the copy is found.
- J7, the Mac asleep: chats started and never coming for over 90 minutes: at most one waits at
  a time, and every one is put away in the end.

Every person, computer, folder and chat here is invented.
"""
from __future__ import annotations

import datetime as dt
import itertools
import json
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import pytest  # noqa: E402

import app_model  # noqa: E402
import computer  # noqa: E402
import page_db  # noqa: E402
from test_a_computer_chat_is_seen_to_its_end import _apply, _as  # noqa: E402
from test_a_ring_is_answered_in_one_command import CHAT, Ring, land  # noqa: E402
from test_a_tick_on_the_page_is_applied_once import NOW, _db, _w  # noqa: E402

T = app_model.parse_time(NOW)
WID = "network~read~1"
BELL = "https://claude.ai/artifact/bell-example"
TODAY = {"environments": [
    {"environment_id": "env_cloud", "name": "Default", "kind": "anthropic_cloud", "state": "active"},
    {"environment_id": "env_mac", "name": "Mac:my-job-search:9c9c",
     "description": "Bridge environment (Mac)", "kind": "bridge", "state": "active"}]}
SUBAGENT = ["Bash", "Read", "Artifact", "ArtifactData", "ArtifactComments"]
LISTENER = SUBAGENT + ["Agent", "ToolSearch", "mcp__claude-code-remote__list_environments",
                       "mcp__claude-code-remote__create_session",
                       "mcp__claude-code-remote__get_session",
                       "mcp__claude-code-remote__archive_session"]
COMPUTER = os.path.join(ROOT, "tools", "computer.py")


# ------------------------------------------------------------------ J1: Start it now


@pytest.fixture
def ring(tmp_path):
    r = Ring(tmp_path)
    yield r
    sys.path.remove(r.root)


def _computer(ring, *args) -> dict:
    r = subprocess.run([sys.executable, COMPUTER, *args, "--now", NOW],
                       env=ring.env(CLAUDE_CODE_REMOTE="true"), capture_output=True,
                       encoding="utf-8", errors="replace", timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    return json.loads(r.stdout)


def _send(ring, paths) -> None:
    import fake_db
    for p in paths:
        assert fake_db.apply(ring.db, p), p


def _row(ring, name) -> dict:
    """The computer as the page is drawn with it from the page's database (computer.seen)."""
    db = page_db.load(ring.read(name))
    return computer.state(db, T, works_on="computer")


def _command(line: str) -> str:
    return line[line.index("python3 tools/computer.py route"):].split(" (with --envs")[0] \
        .split(", and do what it prints")[0]


@pytest.mark.parametrize("starter", [True, False], ids=["rings the starter", "makes the starter"])
def test_j1_start_it_now_reaches_the_computer_the_page_never_says_off(ring, starter):
    ring.put("work", WID, _w("network", "Harbourline Bank", to="computer",
                             title="People at Harbourline Bank",
                             asked=app_model.stamp(T - dt.timedelta(minutes=40))), version=3)
    beat = computer.beat_fields("Studio Laptop", T - dt.timedelta(hours=26), linkedin="in",
                                task=False)
    ring.put("beats", "computer~studio-laptop", beat, version=5)
    if starter:
        ring.put("meta", "computer_starter", {"chat": "session_starter", "bell": BELL,
                                              "made_at": "2026-11-01T08:00:00Z"}, version=4)
    # The ring (Start it now) wakes the listener, which starts its subagent: reads, then wake.
    d = ring.read("wake1")
    said = ring.wake(d)
    line = next((ln for ln in said.splitlines() if ln.startswith("computer:")), "")
    assert WID in line, said
    assert all(land(ring, said))
    # The subagent routes it with its own tools: no list of computers, so it hands that back.
    cmd = _command(line)
    assert f'--chat {CHAT}' in cmd
    got = _computer(ring, "route", d, "--chat", CHAT, "--tools", ",".join(SUBAGENT))
    assert got["line"] not in (computer.SAY["off"], computer.SAY["gone"]), got
    back = got["handback"]
    assert back[0] == "call: list_environments {}" and back[1].startswith("then: "), back
    _send(ring, got.get("batches") or [])
    # Meanwhile the page's row is not off or gone, and no card asks the person anything.
    row = _row(ring, "row1")
    assert row["state"] not in ("off", "gone", "no_bridge") and not row["card"], row
    # The listener makes the call as printed, then its `then`.
    then = back[1][len("then: "):]
    envs = re.search(r'save its answer to "([^"]+)"', then).group(1)
    with open(envs, "w", encoding="utf-8") as fh:
        json.dump(TODAY, fh)
    route = then[then.index("python3 tools/computer.py route"):]
    assert f'"{d}"' in route and f"--envs \"{envs}\"" in route and f"--chat {CHAT}" in route
    if not starter:
        subprocess.run(["git", "init", "-q", ring.state], check=True)
        subprocess.run(["git", "-C", ring.state, "remote", "add", "origin",
                        "https://github.com/morgan-example/my-job-search.git"], check=True)
    mine = _computer(ring, "route", d, "--chat", CHAT, "--envs", envs, "--tools",
                     ",".join(LISTENER))
    assert "handback" not in mine, mine
    assert mine["route"] == ("ring starter" if starter else "make starter"), mine
    if starter:
        bell = re.search(r"file_path (\S+)", mine["then"]).group(1).strip('"')
        assert os.path.isfile(bell) and "Artifact publish" in mine["then"]
    else:
        assert mine["tool"] == "create_session"
        assert mine["call"]["title"] == computer.STARTER_TITLE
    _send(ring, mine.get("batches") or [])
    # The list is kept: the page's row and its To do say the Mac is on, and ask nothing.
    row = _row(ring, "row2")
    assert row["state"] not in ("off", "gone", "no_bridge", "checking") and not row["card"], row
    assert computer.card(row) is None


# ------------------------------------------------------------------ J4: over every chat


TOOLS = ("create_session", "list_environments", "get_session", "Artifact", "ArtifactComments",
         "request_computer_folder")


def _universe():
    """None, each tool alone, all but each one, all: every gap a chat can have, in few runs."""
    yield []
    for t in TOOLS:
        yield [t]
        yield [x for x in TOOLS if x != t]
    yield list(TOOLS)
    yield ["mcp__claude-code-remote__" + t if not t.startswith("Artifact") else t for t in TOOLS]
    yield SUBAGENT
    yield LISTENER
    yield ["mcp__remote-devices__Claude_Browser__navigate"]
    yield ["browser"]


def _dbs():
    """(name, db, fresh check-in or computer on): the page as it may be."""
    work = (WID, _w("network", to="computer", title="People",
                    asked=app_model.stamp(T - dt.timedelta(minutes=40))))
    done = (WID, dict(_w("network", to="computer", status="done",
                         finished_at=app_model.stamp(T - dt.timedelta(hours=1))),
                      computer_session={"id": "session_mac1",
                                        "at": app_model.stamp(T - dt.timedelta(hours=2))}))
    starters = {"none": {},
                "ready": {"computer_starter": {"data": {"chat": "session_starter", "bell": BELL,
                                                        "made_at": "2026-11-01T08:00:00Z"},
                                               "version": 2}},
                "silent": {"computer_starter": {"data": {
                    "chat": "session_starter", "bell": BELL, "made_at": "2026-11-01T08:00:00Z",
                    "rung_at": app_model.stamp(T - dt.timedelta(hours=1)),
                    "rings": computer.STARTER_SILENT_RINGS}, "version": 2}}}
    kept = {"computer_envs": {"data": {"at": app_model.stamp(T - dt.timedelta(hours=1)),
                                       "environments": computer._listed_bridges(TODAY)},
                              "version": 1}}
    for (wname, item), age, (sname, meta), list_kept in itertools.product(
            (("queued", work), ("finished", done)), (None, 10, 30, 26 * 60),
            starters.items(), (False, True)):
        db = _db(item)
        if age is not None:
            b = computer.beat_fields("Studio Laptop", T - dt.timedelta(minutes=age), task=False)
            db["chats"] = {computer.beat_id("Studio Laptop"): {"data": b, "version": 1}}
        db["meta"] = dict(meta, **(kept if list_kept else {}))
        fresh = age is not None and age * 60 < computer.OFF_S
        yield f"{wname}/{age}/{sname}/{list_kept}", db, fresh, list_kept


@pytest.mark.parametrize("kind", ["cloud", "computer"])
def test_j4_every_tool_a_route_names_is_had_or_handed_back_and_never_off_when_on(
        tmp_path, monkeypatch, kind):
    _as(monkeypatch, kind, tmp_path)
    routes, handed = set(), set()
    for origin in (("", ""), ("morgan-example", "my-job-search")):
        monkeypatch.setattr("app_setup.origin", lambda *a, o=origin, **k: o)
        for (name, db, fresh, kept), envs, chat in itertools.product(
                list(_dbs()), (None, TODAY, {"environments": []}), ("session_helper", "")):
            on = kept and envs is None or envs is TODAY
            for tools in _universe():
                got = computer.route(db, T, chat=chat, envs=envs, tools=tools, url="u",
                                     copy="github.com/morgan-example/my-job-search")
                named = computer.tools_named(got.get("then")) | (
                    {got["tool"]} if got.get("tool") else set())
                back = computer.tools_named("\n".join(got.get("handback") or []))
                where = (name, envs is not None, chat, tools, origin, got["route"])
                assert named <= computer.tools_had(tools) | back, (where, named, got)
                routes.add(got["route"])
                if got.get("handback"):
                    handed.add(got["route"])
                if fresh or on:
                    assert got["line"] != computer.SAY["off"], (where, got)
                    assert computer.state(db, T, envs=envs)["line"] != computer.SAY["off"], where
    # Never vacuous: the chain was walked, and steps were handed back.
    assert {"paste", "computer task"} & routes, routes
    if kind == "cloud":
        assert {"ask", "ring starter", "on, start it elsewhere", "check starter"} <= handed, \
            handed


# ------------------------------------------------------------------ J6: names and folders


def _repo(path, origin):
    os.makedirs(os.path.join(path, "tools"), exist_ok=True)
    open(os.path.join(path, "tools", "app.py"), "w", encoding="utf-8").close()
    subprocess.run(["git", "init", "-q", path], check=True)
    subprocess.run(["git", "-C", path, "remote", "add", "origin", origin], check=True)


def test_j6_the_copys_folder_is_chosen_and_the_copy_found(tmp_path, monkeypatch):
    _as(monkeypatch, "cloud", tmp_path)
    copy = "github.com/morgan-example/my-job-search"
    envs = {"environments": [
        {"environment_id": "env_docs", "name": "Mac:Documents:4ba6", "kind": "bridge",
         "description": "Bridge environment (Mac)", "state": "active"},
        {"environment_id": "env_copy", "name": "Mac:my-job-search:77c1", "kind": "bridge",
         "description": "Bridge environment (Mac)", "state": "active"}]}
    home = tmp_path / "home"
    docs = home / "Documents"
    mine = docs / "GitHub" / "my-job-search"
    _repo(str(mine), "https://github.com/morgan-example/my-job-search.git")
    _repo(str(docs / "GitHub" / "last-job-search"), "https://github.com/aranculleton/last-job-search")
    monkeypatch.setenv("HOME", str(home))
    # The chat on the Mac said where the copy is, under the Mac's own name.
    beat = computer.beat_fields("Morgan's MacBook Air", T - dt.timedelta(minutes=50),
                                linkedin="in", chat="session_mac0", task=False,
                                copy=computer.copy_place(str(mine)))
    assert beat["copy"] == "Documents/GitHub/my-job-search"
    db = _db((WID, _w("network", to="computer", title="People")))
    db["chats"] = {computer.beat_id("Morgan's MacBook Air"): {"data": beat, "version": 1}}
    db["meta"] = {"computer_starter": {"data": {"chat": "session_starter", "bell": BELL},
                                       "version": 1}}
    got = computer.route(db, T, chat="session_starter", envs=envs, tools=LISTENER, url="u",
                         copy=copy)
    assert got["route"] == "computer session" and got["call"]["environment_id"] == "env_copy"
    started_in = {"env_copy": mine, "env_docs": docs}
    # Found where the chat starts, by its own address, the app's own copy beside it left.
    cmd = computer.find_copy_command(copy)
    assert cmd in got["call"]["prompt"]
    for env, depth in (("env_copy", ["."]), ("env_docs", ["./GitHub/my-job-search"])):
        r = subprocess.run(["bash", "-c", cmd], cwd=str(started_in[env]), capture_output=True,
                           text=True)
        assert r.stdout.split() == depth, (env, r.stdout, r.stderr)
    # With only Documents shared, Documents: it holds the copy, four folders down.
    docs_only = {"environments": envs["environments"][:1]}
    got = computer.route(db, T, chat="session_starter", envs=docs_only, tools=LISTENER, url="u",
                         copy=copy)
    assert got["call"]["environment_id"] == "env_docs"
    if shutil.which("zsh"):
        r = subprocess.run(["zsh", "-c", cmd], cwd=str(docs), capture_output=True, text=True)
        assert r.stdout.split() == ["./GitHub/my-job-search"], r.stdout + r.stderr


# ------------------------------------------------------------------ J7: the Mac asleep


def _starter_wake(db: dict, now: dt.datetime, tmp, n: int, made: list) -> dict:
    """One wake of the starter, as its prompt says: put away what `waiting` lists, then route
    what is queued and start the chat it prints."""
    w = computer.waiting(db, now)
    for f in w["finished"]:
        db = _apply(db, computer.archived(db, f["work"], now, str(tmp / f"a{n}"),
                                          session=f["session"]))
    got = computer.route(db, now, chat="session_starter", envs=TODAY, tools=LISTENER, url="u",
                         copy="github.com/morgan-example/my-job-search")
    if got["route"] == "computer session":
        sid = f"session_mac{len(made) + 1}"
        made.append(sid)
        db = _apply(db, computer.started(db, WID, sid, "env_mac", "Mac", now, str(tmp / f"s{n}")))
    return db


def _waiting_chats(db: dict, made: list) -> list:
    d = db["work"][WID]["data"]
    gone = {s["id"] for s in d.get("computer_earlier") or [] if s.get("archived_at")}
    if (d.get("computer_session") or {}).get("archived_at"):
        gone.add(d["computer_session"]["id"])
    return [s for s in made if s not in gone and not computer._shown_up(db, s, None)]


def test_j7_a_mac_asleep_gets_one_chat_at_a_time_and_every_one_is_put_away(tmp_path, monkeypatch):
    _as(monkeypatch, "cloud", tmp_path)
    db = _db((WID, _w("network", to="computer", title="People",
                      asked=app_model.stamp(T - dt.timedelta(minutes=5)))))
    db["meta"] = {"computer_starter": {"data": {"chat": "session_starter", "bell": BELL},
                                       "version": 1}}
    made: list = []
    # The bell rings every quarter of an hour for three hours; the Mac sleeps throughout.
    for n in range(13):
        db = _starter_wake(db, T + dt.timedelta(minutes=15 * n), tmp_path, n, made)
        assert len(_waiting_chats(db, made)) <= 1, (n, made)
        if 15 * n <= 90:
            assert made == ["session_mac1"], (n, made)
    # The Mac wakes: the newest chat claims the work and finishes it, then its last heartbeat.
    woke = T + dt.timedelta(hours=3, minutes=10)
    last = made[-1]
    db["work"][WID]["data"].update(status="done", claimed_by=last,
                                   finished_at=app_model.stamp(woke))
    beat = computer.beat_fields("Mac", woke + dt.timedelta(minutes=2), chat=last, task=False)
    db["chats"] = {computer.beat_id("Mac"): {"data": beat, "version": 1}}
    db = _starter_wake(db, woke + dt.timedelta(minutes=3), tmp_path, 99, made)
    d = db["work"][WID]["data"]
    put_away = {s["id"] for s in d.get("computer_earlier") or [] if s.get("archived_at")}
    if d["computer_session"].get("archived_at"):
        put_away.add(d["computer_session"]["id"])
    assert put_away == set(made), (made, d)
