"""Each chat the app starts on the person's computer, and the small chat that starts them, is
seen to its end: its last steps run, it is put away by the one chat that can, and a starter
that stopped answering is noticed instead of rung for good.

From the builder audit of 2026-11-10 (CC-2, CC-6, CC-14, CC-15): the chat on the computer was
told to archive itself before its last three steps, so its heartbeat, the earlier chats and the
starter's wake never came; a starter that was gone, or waited on the person's approval in a chat
they never open, was rung every ten minutes for good, or made a second time; and a refused
archive left the starter ringing at every wake. Invented people and computers only.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "network"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import app_model  # noqa: E402
import computer  # noqa: E402
from test_a_tick_on_the_page_is_applied_once import NOW, _db, _w  # noqa: E402
from test_the_computer_side_just_works import BRIDGE  # noqa: E402

T = app_model.parse_time(NOW)
URL = "https://claude.ai/artifact/page-1"


def _as(monkeypatch, kind: str, tmp_path=None):
    import app_listen
    import tempfile
    monkeypatch.setenv("LJS_STATE", str(tmp_path or tempfile.mkdtemp()))
    monkeypatch.setattr(app_listen, "chat_kind", lambda: kind)


# ------------------------------------------------------------------ CC-2


def test_the_chat_on_the_computer_never_archives_itself_before_its_last_steps(
        tmp_path, monkeypatch):
    """With nothing more waiting, the steps `next` prints send the chat on to step 7 of its
    prompt (the heartbeat, the earlier chats, the starter's wake), never to archive_session:
    archived there, the starter was never woken, so the work it brings to master waited."""
    import app
    _as(monkeypatch, "computer", tmp_path)
    db = _db(("network~targets~1", _w("network", to="computer", title="People",
                                      args={"count": 5})))
    chosen = app.choose(db, "mac-chat", "computer", T, on="claude-opus-5-5", no_sessions=True,
                        computer_only=True)
    steps = "\n".join(chosen["steps"])
    assert "archive_session" not in steps, steps
    assert "step 7 of your prompt" in steps
    # The next piece of work for this computer is still taken first.
    assert "--kind computer --computer-only" in steps
    # The prompt's own steps 7 to 9 are what follow, and the starter archives this chat.
    prompt = computer.session_prompt("network~targets~1", "People", URL, "their job search")
    assert "7. At the end" in prompt and "computer.py ring" in prompt
    assert "the chat that started you archives this one" in prompt
    # A big job's own chat in the cloud still puts itself away, as before.
    assert "archive_session" in app._next_job(URL, kind="cloud")


# ------------------------------------------------------------------ CC-15


def test_a_refused_archive_still_counts_as_put_away(tmp_path, monkeypatch):
    """The starter recorded `archived` only after archive_session worked. A chat the person had
    deleted, or one already put away, was refused, never recorded, and every empty wake of the
    page's helper rang the starter again for it."""
    import json
    prompt = computer.starter_prompt(URL, "github.com/someone/my-job-search")
    said = prompt[prompt.index("under `finished`"):]
    said = said[:said.index("land.py")]
    assert "whatever archive_session answered" in said
    assert "not found" in said and "already archived" in said and "refused" in said
    # Recorded, the finished chat is not rung for again.
    done = dict(_w("network", "Harbourline Bank", to="computer", status="done"),
                computer_session={"id": "session_mac1", "at": NOW})
    db = _db(("network~read~1", done))
    db["meta"] = {"computer_starter": {"data": {"chat": "session_starter",
                                                "bell": "https://claude.ai/artifact/bell-1",
                                                "made_at": "2026-10-20T08:00:00Z"},
                                       "version": 2}}
    _as(monkeypatch, "cloud", tmp_path)
    assert computer.route(db, T, chat="session_helper", tools=["create_session"])["route"] == \
        "ring starter"
    batches = computer.archived(db, "network~read~1", T, str(tmp_path / "a"))
    entry = json.load(open(batches[0], encoding="utf-8"))[0]
    fields = entry.get("data")
    if fields is None:
        with open(entry["file_path"], encoding="utf-8") as fh:
            fields = json.load(fh)
    after = _db(("network~read~1", dict(done, **fields)))
    after["meta"] = db["meta"]
    assert computer.route(after, T, chat="session_helper",
                          tools=["create_session"])["route"] == "none"


# ------------------------------------------------------------------ CC-6 and CC-14


BELL = "https://claude.ai/artifact/bell-1"


def _starter(**kw) -> dict:
    return {"meta": {"computer_starter": {"data": dict({"chat": "session_starter",
                                                         "bell": BELL,
                                                         "made_at": "2026-10-20T08:00:00Z"},
                                                        **kw), "version": 3}}}


def _apply(db: dict, batches) -> dict:
    """The page's database once these batches are sent (meta and work only)."""
    import copy
    import json
    import page_db
    out = copy.deepcopy(db)
    for path in batches:
        with open(path, encoding="utf-8") as fh:
            for e in json.load(fh):
                fields = e.get("data")
                if fields is None:
                    with open(e["file_path"], encoding="utf-8") as f2:
                        fields = json.load(f2)
                coll = page_db._LOGICAL.get(e["collection"], e["collection"])
                doc = out.setdefault(coll, {}).setdefault(e["doc_id"], {"data": {},
                                                                         "version": 0})
                base = doc["data"] if e.get("op", e.get("action")) == "update" else {}
                doc["data"] = dict(base, **fields)
                doc["version"] = int(doc.get("version") or 0) + 1
    return out


def test_a_starter_that_never_answers_is_looked_at_and_the_person_asked(tmp_path, monkeypatch):
    """Rung for good: a starter the person deleted, or one waiting on their approval in a chat
    they never open, left the page saying ready and the bell ringing every ten minutes."""
    from datetime import timedelta
    _as(monkeypatch, "cloud", tmp_path)
    tools = ["create_session"]
    work = ("network~read~1", _w("network", "Harbourline Bank", to="computer",
                                 title="People at Harbourline Bank"))
    db = dict(_db(work), **_starter())
    # Rung, and nothing answered: rung again after RING_S, then looked at, not rung a third time.
    t = T
    for n in (1, 2):
        got = computer.route(db, t, chat="session_helper", envs=BRIDGE, tools=tools)
        assert got["route"] == "ring starter", (n, got)
        db = _apply(db, computer.rung(db, t, str(tmp_path / f"r{n}")))
        assert computer.unanswered(db) == n
        t = t + timedelta(seconds=computer.RING_S + 60)
    got = computer.route(db, t, chat="session_helper", envs=BRIDGE, tools=tools)
    assert got["route"] == "check starter", got
    assert got["call"] == {"session_id": "session_starter"} and "get_session" in got["then"]
    assert "computer.py starter-seen" in got["then"]
    # Waiting on the person (its approval card): never made again, and the page asks them.
    waits = _apply(db, computer.starter_seen(db, "blocked", t, str(tmp_path / "s1")))
    assert computer.route(waits, t, chat="session_helper", envs=BRIDGE, tools=tools)["route"] == "starter waits"
    st = computer.state(waits, t, envs=BRIDGE)
    assert st["state"] == "starter_waits" and st["card"]
    card = computer.card(st)
    assert card and "approve" in card["body"] and "Harbourline Bank" in card["body"]
    # It answers (a chat started on the computer): the card goes, and the ring count with it.
    started = _apply(waits, computer.started(waits, "network~read~1", "session_mac1", "env_1",
                                             "Studio Laptop", t + timedelta(minutes=1),
                                             str(tmp_path / "st")))
    assert computer.starter_stuck(started) == "" and computer.unanswered(started) == 0
    assert computer.state(started, t + timedelta(minutes=2), envs=BRIDGE)["state"] != "starter_waits"
    # Gone (archived or deleted): its record is cleared, and the next route makes a new one.
    gone = _apply(db, computer.starter_seen(db, "archived", t, str(tmp_path / "s2")))
    assert computer.starter(gone)["chat"] == "" and computer.starter(gone)["gone"]["chat"] == \
        "session_starter"
    monkeypatch.setattr(__import__("app_setup"), "origin", lambda: ("someone", "my-job-search"))
    assert computer.route(gone, t, chat="session_helper", envs=BRIDGE, tools=tools, url=URL)["route"] == \
        "make starter"
    # Alive but silent, twice: the person is asked to open it.
    alive = db
    for n in (1, 2):
        alive = _apply(alive, computer.starter_seen(alive, "idle", t, str(tmp_path / f"a{n}")))
    assert computer.starter_stuck(alive) == "silent"
    silent = computer.state(alive, t, envs=BRIDGE)
    assert silent["state"] == "starter_silent" and silent["card"]
    assert "not answering" in computer.card(silent)["body"]
    # A starter that answers each ring is never looked at.
    answered = dict(_db(work), **_starter(woke_at=app_model.stamp(T + timedelta(minutes=1))))
    answered = _apply(answered, computer.rung(answered, T, str(tmp_path / "w1")))
    later = T + timedelta(minutes=2)
    answered["meta"]["computer_starter"]["data"]["woke_at"] = app_model.stamp(later)
    assert computer.unanswered(answered) == 0
    assert computer.route(answered, later + timedelta(seconds=computer.RING_S + 60),
                          chat="session_helper", envs=BRIDGE, tools=tools)["route"] == "ring starter"
    # The starter says it answered, at every wake.
    assert "computer.py starter-woke" in computer.starter_prompt(URL, "github.com/x/y")


def test_a_starter_slow_to_be_ready_is_looked_at_never_made_twice(tmp_path, monkeypatch):
    """Not ready (no bell) STARTER_WAIT_S after it was asked for, it was made again: a slow
    first run, or its approval card waiting on the person, made a second starter, and an
    approved one can never be put away."""
    from datetime import timedelta
    _as(monkeypatch, "cloud", tmp_path)
    monkeypatch.setattr(__import__("app_setup"), "origin", lambda: ("someone", "my-job-search"))
    work = ("network~read~1", _w("network", "Harbourline Bank", to="computer"))
    late = T + timedelta(seconds=computer.STARTER_WAIT_S + 60)
    db = dict(_db(work), **_starter(bell="", made_at=NOW))
    got = computer.route(db, late, chat="session_helper", envs=BRIDGE, tools=["create_session"], url=URL)
    assert got["route"] == "check starter", got
    # Still starting (alive): left, and looked at again later, never made again meanwhile.
    alive = _apply(db, computer.starter_seen(db, "working", late, str(tmp_path / "a")))
    assert computer.route(alive, late + timedelta(minutes=5), chat="session_helper", envs=BRIDGE,
                          tools=["create_session"], url=URL)["route"] == "starter starting"
    # Waiting on the person: the page asks them, and no second starter is made.
    waits = _apply(db, computer.starter_seen(db, "blocked", late, str(tmp_path / "b")))
    assert computer.route(waits, late + timedelta(hours=3), chat="session_helper", envs=BRIDGE,
                          tools=["create_session"], url=URL)["route"] == "check starter"
    assert computer.route(waits, late + timedelta(minutes=5), chat="session_helper", envs=BRIDGE,
                          tools=["create_session"], url=URL)["route"] == "starter waits"
    assert computer.state(waits, late + timedelta(minutes=20), envs=BRIDGE)["state"] == "starter_waits"


# ------------------------------------------------------------------ CC-26


def test_signed_in_on_work_already_handled_is_not_an_error(tmp_path):
    """`computer.py signed-in` on work that no longer waits on a sign-in exited 2 with the id
    quoted like an error, so a chat read "already handled" as a failure."""
    import json
    import subprocess
    dump = tmp_path / "dump"
    (dump / "work").mkdir(parents=True)
    with open(dump / "work" / ("~".join(("network", "read", "1")).replace("~", "@") + ".json"), "w", encoding="utf-8") as fh:
        json.dump({"data": _w("network", "Harbourline Bank", to="computer"), "version": 3}, fh)

    def run(wid):
        return subprocess.run([sys.executable, os.path.join(ROOT, "tools", "computer.py"),
                               "signed-in", str(dump), "--work", wid, "--now", NOW],
                              capture_output=True, text=True, encoding="utf-8")
    queued = run("network~read~1")
    assert queued.returncode == 0, queued.stdout + queued.stderr
    assert queued.stdout.startswith("signed-in:") and "nothing to send" in queued.stdout
    missing = run("network~read~9")
    assert missing.returncode != 0 and "no work" in missing.stderr


# ------------------------------------------------------------------ E-10


def _signed_out_item(**kw) -> dict:
    from datetime import timedelta
    item = _w("network", "Harbourline Bank", to="computer", status="needs_you")
    item.update(note="LinkedIn is signed out in Claude's browser.",
                needs={"question": "LinkedIn is signed out in Claude's browser.",
                       "signin": "linkedin"},
                asked_you_at=app_model.stamp(T - timedelta(minutes=3)),
                computer_session={"id": "session_mac1", "at": NOW})
    item.update(kw)
    return item


def test_the_sign_in_wait_is_one_fresh_look_every_three_minutes(tmp_path):
    """A look a minute, three calls each, read the copy of the page taken before the wait: up
    to 45 calls at the chat's full context, and a sign-in made on the page or a Stop tapped
    there was never seen."""
    import json
    import subprocess
    assert computer.SIGNIN_LOOK_S == 180
    prompt = computer.session_prompt("network~read~1", "People", URL, "their job search")
    step5 = prompt[prompt.index("5. Say how"):prompt.index("6. Follow")]
    assert "collection work" in step5 and "signin-wait" in step5 and "--url" in step5
    assert "timeout 240000" in step5 and "reading.py signin --url" not in step5

    def run(item, *extra):
        dump = tmp_path / str(len(list(tmp_path.iterdir())))
        (dump / "work").mkdir(parents=True)
        with open(dump / "work" / ("~".join(("network", "read", "1")).replace("~", "@") + ".json"), "w", encoding="utf-8") as fh:
            json.dump({"data": item, "version": 4}, fh)
        return subprocess.run([sys.executable, os.path.join(ROOT, "tools", "computer.py"),
                               "signin-wait", str(dump), "--work", "network~read~1",
                               "--every", "0", "--now", NOW, *extra],
                              env=dict(os.environ, LJS_STATE=str(tmp_path / "state")),
                              capture_output=True, text=True, encoding="utf-8")
    # The page sent it back (they signed in there): seen at the next look.
    back = run(dict(_signed_out_item(), status="queued"), "--url",
               "https://www.linkedin.com/login")
    assert back.stdout.startswith("answered:"), back.stdout + back.stderr
    # They tapped Stop on the page: the chat stops waiting.
    stop = run(_signed_out_item(stop_asked=True), "--url", "https://www.linkedin.com/login")
    assert stop.stdout.startswith("stopped:"), stop.stdout
    # The sign-in tab shows them signed in: carried on at once, with no wait.
    signed = run(_signed_out_item(), "--url", "https://www.linkedin.com/feed/")
    assert signed.stdout.startswith("signed-in:") and "computer.py signed-in" in signed.stdout
    # Still on the sign-in page: the next look is the same three calls, the work read afresh.
    look = run(_signed_out_item(), "--url", "https://www.linkedin.com/login")
    assert look.stdout.startswith("look:") and "collection work" in look.stdout, look.stdout


# ------------------------------------------------------------------ second audit, C6


def test_the_chat_started_on_the_computer_gets_the_pages_tools_and_names_itself(
        tmp_path, monkeypatch):
    """The chat started on the computer had none of the page's tools pre-approved, unlike a
    cloud job's chat, so each read and write of the page asked the person in a chat they never
    open, its last steps never ran, and it was left open ("Reading 10 profiles on your
    computer", the second audit, C6). Its heartbeat now names it too."""
    import app
    _as(monkeypatch, "cloud", tmp_path)
    db = dict(_db(("network~read~1", _w("network", "Harbourline Bank", to="computer"))),
              **_starter())
    got = computer.route(db, T, chat="session_starter", envs=BRIDGE, tools=["create_session"],
                         url=URL, copy="github.com/someone/my-job-search")
    assert got["route"] == "computer session"
    assert sorted(got["call"]["extra_allowed_tools"]) == sorted(app.CHILD_TOOLS)
    assert sorted(computer.STARTER_TOOLS) == sorted(app.CHILD_TOOLS)
    prompt = got["call"]["prompt"]
    assert prompt.count("computer.py beat \"$D\" --chat <your id>") == 2


# ------------------------------------------------------------------ CC-25


def test_a_chat_that_compacts_finds_the_id_its_work_was_claimed_under(tmp_path):
    """Nothing told a chat on the computer that had compacted to read its steps again, and it
    went on only if it still knew its claim's id: under a new one its pins were refused."""
    import json
    import subprocess
    from test_a_tick_on_the_page_is_applied_once import Search
    s = Search(str(tmp_path))
    s.put("work", "network~read~1", _w("network", "Harbourline Bank", to="computer",
                                       title="Reading on your computer"), version=1)
    got = json.loads(s.run("next", s.dump, "--chat", "mac-job-7", "--kind", "computer",
                           "--computer-only", "--now", NOW,
                           "--claim-out", os.path.join(s.dump, "claim")))
    assert got["work"] == "network~read~1"
    env = dict(os.environ, LJS_PROFILE=s.profile, LJS_STATE=s.state, LJS_COPY="private")
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "computer.py"), "prompt",
                        "--work", "network~read~1"], env=env, capture_output=True, text=True,
                       encoding="utf-8")
    assert r.returncode == 0, r.stderr
    assert r.stdout.startswith("Claimed here as mac-job-7: pass --chat mac-job-7"), r.stdout
    assert "After a compaction" in r.stdout and "computer.py prompt --work network~read~1" in \
        r.stdout
    # Work nobody claimed here says no id.
    other = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "computer.py"), "prompt",
                            "--work", "network~read~2"], env=env, capture_output=True, text=True,
                           encoding="utf-8")
    assert not other.stdout.startswith("Claimed here")


# ------------------------------------------------------------------ CC-1


def test_work_saved_on_the_computer_is_never_said_lost():
    """A job finished on the computer saves there and is brought to master by the computer
    starter's land.py; its branch not on GitHub yet was asked about and then said lost, and the
    page turned a finished read into "results lost, Try again" while the work was on the Mac."""
    import datetime as dt
    import tidy
    from test_a_finished_chat_closes_at_once_and_one_page_helper_stays import (
        LIVE, REPO, _chat, _detail)
    job, title, branch = "session_EXAMPLEMACREAD", "Job search: Reading on your computer", \
        "claude/reading-mac-x1"
    listener = {"chat": LIVE, "kind": "cloud", "helper": True, "since": "2026-11-05T08:00:00Z"}
    det = {job: _detail(job, title, branch=branch)}
    items = tidy.job_items({"work": {"network~read~1": {"data": {
        "kind": "network", "status": "done", "claimed_by": job, "claimed_as": "computer",
        "finished_at": "2026-11-06T08:00:00Z"}}}})
    assert items[job]["computer"] is True
    at = dt.datetime(2026, 11, 6, 9, 0, tzinfo=dt.timezone.utc)
    for later in (0, 40, 120):
        got = tidy.plan([_chat(LIVE, "Job search page"),
                         _chat(job, title, updated="2026-11-06T08:00:00Z")], [], det, {},
                        listener, LIVE, REPO, dt.date(2026, 11, 6), set(), set(), set(),
                        {job: "2026-11-06T08:00:00Z"}, now=at + dt.timedelta(minutes=later),
                        on_github={"master"},
                        saves={job: {"work": "network~read~1",
                                     "asked": "2026-11-06T09:00:00Z"}},
                        job_items=items)
        assert not got["lost"] and not got["save"], got
        assert any(k["id"] == job and "person's computer" in k["why"] for k in got["keep"])
    # Reported back the same way: kept, never asked to save, never said lost.
    db = {"work": {"network~read~1": {"data": {"kind": "network", "status": "done",
                                                "claimed_by": job, "claimed_as": "computer"},
                                       "version": 3}}}
    what, why = tidy.close(job, "network~read~1", db, det, listener, LIVE, REPO, set(),
                           {"master"}, now=at, record={})
    assert what == "keep" and "person's computer" in why
    # Work done in the cloud is judged as before.
    assert tidy.job_items({"work": {"s": {"data": {"claimed_by": job, "status": "done",
                                                   "claimed_as": "cloud"}}}})[job]["computer"] \
        is False


# ------------------------------------------------------------------ section 12


def test_the_chat_on_the_computer_reads_only_what_it_needs_to_start(tmp_path, monkeypatch):
    """It read six collections, over a megabyte of the page's screens, before it started; it
    needs work, holds, beats and meta until it brings the page up to date."""
    import app
    prompt = computer.session_prompt("network~read~1", "People", URL, "their job search")
    step3 = prompt[prompt.index("3. Load ArtifactData"):prompt.index("4. python3")]
    assert "work, holds, beats and meta" in step3
    assert "screen" not in step3.split("The page's screens")[0] and "addr" not in step3
    _as(monkeypatch, "computer", tmp_path)
    db = _db(("network~read~1", _w("network", "Harbourline Bank", to="computer", title="People",
                                   args={"count": 5})))
    chosen = app.choose(db, "mac-chat", "computer", T, on="claude-opus-5-5", no_sessions=True,
                        computer_only=True)
    first = chosen["steps"][0]
    assert "work, holds and meta" in first and "screen" not in first and "addr" not in first
    # It still reads the screens where it brings the page up to date: through the copy kept,
    # `app.py reads --for-view` (the page review of 2026-11-11, 2C-4).
    assert any("--for-view" in s and "app.py view" in s for s in chosen["steps"])
    # A cloud job's chat reads its own two up front, work and holds, and the screens at its
    # finish too (the second audit of 2026-11-10, C4).
    _as(monkeypatch, "cloud", tmp_path)
    cloud = app.job_steps({"work": "draft~1", "kind": "draft"}, "session_x", URL)
    assert "collections work and holds, each" in cloud[0], cloud[0]
    assert "screen" not in cloud[0] and "addr" not in cloud[0], cloud[0]
    assert any("--for-view" in s for s in cloud)


# ------------------------------------------------------------------ CC-1, the save itself


def _repo(tmp_path):
    import subprocess

    def g(cwd, *args):
        return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True,
                              encoding="utf-8", check=True)
    origin = tmp_path / "origin"
    origin.mkdir()
    g(origin, "init", "-q", "--bare", "-b", "master")
    me = tmp_path / "me"
    g(tmp_path, "clone", "-q", str(origin), str(me))
    (me / "README.md").write_text("x\n", encoding="utf-8")
    g(me, "add", "README.md")
    g(me, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "one")
    g(me, "push", "-q", "origin", "HEAD:master")
    g(me, "fetch", "-q", "origin")
    return me, g


def test_a_chat_on_the_computer_waits_for_its_save_and_says_when_it_never_left(tmp_path):
    """It saved in the background and was put away at once; when the push never left the Mac
    (asleep, offline), the work sat on a branch there and nothing said so. Never called lost:
    a save on its way, a branch already on GitHub and a change not saved yet are all kept
    (the independent review, 2026-11-11), and what cannot leave yet is said as kept on the
    computer and sent by the next save there."""
    import json
    import land
    me, g = _repo(tmp_path)
    root = str(me)
    # Nothing of its own: saved.
    assert land.saved_state(root)[0] == "nothing"
    # Work committed and never pushed (offline): not sent yet, with what the save could not do.
    g(me, "switch", "-q", "-c", "chat/reading-1")
    (me / "documents").mkdir()
    (me / "documents" / "notes.json").write_text("{}\n", encoding="utf-8")
    g(me, "add", "documents/notes.json")
    g(me, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "two")
    with open(os.path.join(land.git_dir(root), land.RESULT_FILE), "w", encoding="utf-8") as fh:
        json.dump({"at": 0, "lines": ["land: the push was refused: could not resolve host"]}, fh)
    state, why = land.wait_saved(root, timeout=0)
    assert state == "unsaved" and "could not resolve host" in why
    assert land.main(["--wait-saved", "--timeout", "0"], root=root) == 1
    # Still saving when its time is up: on its way, never lost.
    token = land._take_lock(root)
    try:
        assert land.saved_state(root)[0] == "saving"
        state, why = land.wait_saved(root, timeout=0)
        assert state == "saving" and "on its way" in why
        assert land.main(["--wait-saved", "--timeout", "0"], root=root) == 0
    finally:
        land._drop_lock(root, token)
    # Its branch on GitHub without the landing's own record (a save a check held back pushes
    # the branch and waits there): saved.
    g(me, "push", "-q", "origin", "chat/reading-1")
    assert land.saved_state(root) == ("pushed", "chat/reading-1")
    assert land.main(["--wait-saved", "--timeout", "0"], root=root) == 0
    # A change of the person's never saved is saved now, then waited for: never left out.
    (me / "documents" / "notes.json").write_text('{"a": 1}\n', encoding="utf-8")

    def save_now():
        g(me, "add", "documents/notes.json")
        g(me, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "three")
        g(me, "push", "-q", "origin", "chat/reading-1")
    assert land.wait_saved(root, timeout=0, start=save_now) == ("pushed", "chat/reading-1")
    # What cannot leave yet is kept on the computer: its cards say so, still done.
    db = _db(("network~read~1", dict(_w("network", "Harbourline Bank", to="computer",
                                        args={"contacts": ["c_ana"], "read_first": True,
                                              "rewrite": True}),
                                     status="done", claimed_by="mac-job-7",
                                     claimed_as="computer")),
             ("network~read~2", dict(_w("network", "Fernway Insurance", to="computer"),
                                     status="done", claimed_by="mac-other")))
    batches = computer.saved_here(db, "mac-job-7", T, str(tmp_path / "here"))
    entries = json.load(open(batches[0], encoding="utf-8"))
    assert [e["doc_id"] for e in entries] == ["network~read~1"]
    body = entries[0].get("data")
    if body is None:
        with open(entries[0]["file_path"], encoding="utf-8") as fh:
            body = json.load(fh)
    assert "status" not in body and body["saved_here"]
    assert body["steps"][-1]["text"] == computer.SAVED_HERE_SAID
    # Its people are not queued to be read again meanwhile.
    import app
    kept = dict(db["work"]["network~read~1"]["data"], **body)
    model = {"person": {"computer": True},
             "linkedin": {"reading": {"setting": "browser", "paused": False,
                                      "queue": [{"contact": "c_ana", "first_name": "Ana"}]}}}
    work = {"network~read~0": {"data": kept, "version": 2}}
    assert app.computer_reads(model, work, T + __import__("datetime").timedelta(days=2)) is None
    # The prompt's last step waits for the save and says one kept here, never lost.
    prompt = computer.session_prompt("network~read~1", "People", URL, "their job search")
    step7 = prompt[prompt.index("7. At the end"):prompt.index("8. Wake")]
    assert "land.py --wait-saved" in step7 and "saved-here" in step7 and "lost" not in step7


def test_the_next_save_on_the_computer_sends_what_an_earlier_chat_left_behind(tmp_path):
    """A save that could not leave when its chat ended sat on its branch: no later chat there
    pushed it, its folder being another's."""
    import land
    me, g = _repo(tmp_path)
    root = str(me)
    g(me, "switch", "-q", "-c", "chat/reading-1")
    (me / "left.txt").write_text("left behind\n", encoding="utf-8")
    g(me, "add", "left.txt")
    g(me, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "left")
    g(me, "switch", "-q", "-c", "chat/reading-2", "origin/master")
    assert land._push_left_behind(root) == ["chat/reading-1"]
    assert "chat/reading-1" in g(me, "ls-remote", "--heads", "origin").stdout
    # Sent once: nothing more the next time, and never the branch checked out.
    g(me, "fetch", "-q", "origin")
    assert land._push_left_behind(root) == []


# ------------------------------------------------------------------ CC-17


def test_the_chats_merged_clean_folders_on_the_computer_are_removed_and_nothing_else(
        tmp_path, monkeypatch):
    """Every chat on the computer made a folder of its own and none was removed."""
    import json
    me, g = _repo(tmp_path)
    root = str(me)

    # Only the folders sync_app.worktree makes (under .claude/worktrees, on chat/ branches),
    # unused for hours: the review of 2026-11-11 found a just-made folder and the person's own
    # removed (test_tidy_folders_never_removes_a_persons_files_or_a_folder_in_use).
    (me / ".claude" / "worktrees").mkdir(parents=True)

    def folder(name, merged=True, change=False, claim=""):
        path = me / ".claude" / "worktrees" / name
        g(me, "worktree", "add", "-q", "-b", f"chat/{name}", str(path))
        if not merged:
            (path / f"{name}.txt").write_text("mine\n", encoding="utf-8")
            g(path, "add", f"{name}.txt")
            g(path, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", name)
        if change:
            (path / "notes.txt").write_text("not saved\n", encoding="utf-8")
        if claim:
            gd = g(path, "rev-parse", "--absolute-git-dir").stdout.strip()
            with open(os.path.join(gd, "ljs-claims.json"), "w", encoding="utf-8") as fh:
                json.dump({claim: {"chat": "mac-job-9", "day": "2026-11-10"}}, fh)
        _old(str(path), g)
        return str(path)
    done = folder("done")
    unsaved = folder("unsaved", change=True)
    unmerged = folder("unmerged", merged=False)
    busy = folder("busy", claim="network~read~5")
    db = _db(("network~read~5", dict(_w("network", "Harbourline Bank", to="computer"),
                                     status="running", claimed_by="mac-job-9",
                                     claimed_as="computer", claimed_at=NOW,
                                     lease_until=app_model.stamp(T.replace(hour=23)))))
    monkeypatch.chdir(root)
    got = [t["path"] for t in computer.stale_worktrees(root, db, T)]
    assert got == [done], got
    assert computer.remove_worktrees(root, computer.stale_worktrees(root, db, T)) == [done]
    assert not os.path.exists(done)
    for kept in (unsaved, unmerged, busy, root):
        assert os.path.isdir(kept), kept
    assert "chat/done" not in g(me, "branch").stdout
    # With no read of the page, a folder that claimed work is kept: it may be in use.
    assert computer.stale_worktrees(root, None, T) == []
    # The prompt's last steps run it.
    prompt = computer.session_prompt("network~read~1", "People", URL, "their job search")
    assert "computer.py tidy-folders" in prompt[prompt.index("7. At the end"):]


# ------------------------------------------------------------------ review 1: tidy-folders


def _old(path_str: str, g, hours: float = 30.0) -> None:
    """Make a chat folder look last used `hours` ago: its git folder's index and HEAD log."""
    import time
    gd = g(path_str, "rev-parse", "--absolute-git-dir").stdout.strip()
    t = time.time() - hours * 3600
    for name in ("index", os.path.join("logs", "HEAD"), "HEAD"):
        p = os.path.join(gd, name)
        if os.path.exists(p):
            os.utime(p, (t, t))


def test_tidy_folders_never_removes_a_persons_files_or_a_folder_in_use(tmp_path, monkeypatch):
    """Removed before: a folder just made at master (a chat that has just started), one holding
    an ignored resume never committed, and the person's own folder outside the app's ones."""
    import json
    me, g = _repo(tmp_path)
    root = str(me)
    (me / ".gitignore").write_text("documents/cv/*.pdf\n__pycache__/\n*.pyc\n",
                                   encoding="utf-8")
    g(me, "add", ".gitignore")
    g(me, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "ignore")
    g(me, "push", "-q", "origin", "HEAD:master")
    g(me, "fetch", "-q", "origin")
    base = me / ".claude" / "worktrees"
    base.mkdir(parents=True)

    def folder(where, branch, old=True):
        g(me, "worktree", "add", "-q", "-b", branch, str(where), "origin/master")
        if old:
            _old(str(where), g)
        return str(where)
    safe = folder(base / "done-1", "chat/done-1-2026-11-01")
    odd = folder(base / "my folder [2]", "chat/my-folder-2-2026-11-01")
    noise = folder(base / "noise", "chat/noise-2026-11-01")
    pyc = os.path.join(noise, "tools", "__pycache__")
    os.makedirs(pyc)
    open(os.path.join(pyc, "a.cpython-313.pyc"), "wb").close()
    _old(noise, g)
    resume = folder(base / "resume", "chat/resume-2026-11-01")
    os.makedirs(os.path.join(resume, "documents", "cv"))
    with open(os.path.join(resume, "documents", "cv", "my resume (final).pdf"), "wb") as fh:
        fh.write(b"%PDF-1.4 never committed")
    _old(resume, g)
    odd_resume = folder(base / "odd [x] resume", "chat/odd-resume-2026-11-01")
    os.makedirs(os.path.join(odd_resume, "documents", "cv"))
    open(os.path.join(odd_resume, "documents", "cv", "cv.pdf"), "wb").close()
    _old(odd_resume, g)
    fresh = folder(base / "just-made", "chat/just-made-2026-11-10", old=False)
    # Used just now on the test's own clock: git dates its files by the computer's, which a
    # clock moved on in Python alone left a year behind, so the folder read as old (the
    # everywhere check, "400-days").
    _old(fresh, g, hours=0)
    outside = folder(tmp_path / "my own folder", "chat/mine-2026-11-01")
    theirs = folder(base / "not-a-chat", "feature/theirs")
    in_use = folder(base / "in-use", "chat/in-use-2026-11-01")
    gd = g(in_use, "rev-parse", "--absolute-git-dir").stdout.strip()
    with open(os.path.join(gd, "ljs-job-chats.json"), "w", encoding="utf-8") as fh:
        json.dump({"session_EXAMPLEmacjob3": {"work": "network~read~3", "day": "2026-11-09"}}, fh)
    _old(in_use, g)
    monkeypatch.chdir(root)
    db = _db(("network~read~3", dict(_w("network", "Harbourline Bank", to="computer"),
                                     status="done", claimed_by="session_EXAMPLEmacjob3",
                                     computer_session={"id": "session_EXAMPLEmacjob3", "at": NOW})))
    got = sorted(t["path"] for t in computer.stale_worktrees(root, db, T))
    assert got == sorted([safe, odd, noise]), got
    assert sorted(computer.remove_worktrees(root, computer.stale_worktrees(root, db, T))) == \
        sorted([safe, odd, noise])
    for gone in (safe, odd, noise):
        assert not os.path.exists(gone), gone
    for kept in (resume, odd_resume, fresh, outside, theirs, in_use, root):
        assert os.path.isdir(kept), kept
    assert os.path.isfile(os.path.join(resume, "documents", "cv", "my resume (final).pdf"))
    branches = g(me, "branch", "--list").stdout
    assert "chat/mine-2026-11-01" in branches and "chat/resume-2026-11-01" in branches
    # The chat in use is put away: its folder can go then.
    put_away = _db(("network~read~3", dict(db["work"]["network~read~3"]["data"],
                                           computer_session={"id": "session_EXAMPLEmacjob3",
                                                             "at": NOW, "archived_at": NOW})))
    assert [t["path"] for t in computer.stale_worktrees(root, put_away, T)] == [in_use]


# ------------------------------------------------------------------ review 4


def test_a_chat_on_the_computer_is_put_away_only_after_its_last_steps(tmp_path, monkeypatch):
    """`waiting` listed a chat finished the moment its work was done, and any cloud route then
    rang the starter, which could archive it during its save's wait and its last steps."""
    from datetime import timedelta
    done = dict(_w("network", "Harbourline Bank", to="computer"), status="done",
                claimed_by="session_mac1", finished_at=app_model.stamp(T - timedelta(minutes=2)),
                computer_session={"id": "session_mac1",
                                  "at": app_model.stamp(T - timedelta(minutes=30))})
    db = _db(("network~read~1", done))
    w = computer.waiting(db, T)
    assert w["finished"] == [] and w["started"] == {"network~read~1": "session_mac1"}
    _as(monkeypatch, "cloud", tmp_path)
    ring = dict(db, **_starter())
    assert computer.route(ring, T, chat="session_helper", envs=BRIDGE,
                          tools=["create_session"])["route"] == "none"
    # Its last heartbeat came: put away now.
    last = computer.beat_fields("Studio Laptop", T - timedelta(minutes=1), linkedin="in",
                                version="4.14.0", task=False, chat="session_mac1")
    beat = dict(db, chats={computer.beat_id("Studio Laptop"): {"data": last, "version": 2}})
    assert computer.waiting(beat, T)["finished"] == [{"work": "network~read~1",
                                                      "session": "session_mac1"}]
    # Or long enough after its work ended that its steps are over whatever happened.
    late = T + timedelta(seconds=computer.END_WAIT_S + 60)
    assert computer.waiting(db, late)["finished"] == [{"work": "network~read~1",
                                                      "session": "session_mac1"}]
    # A second job of the same chat still going keeps it at work, heartbeat or not.
    going = _db(("network~read~1", done),
                ("network~read~2", dict(_w("network", "Fernway Insurance", to="computer"),
                                        status="running", claimed_by="session_mac1",
                                        claimed_at=NOW)))
    going["chats"] = beat["chats"]
    assert computer.waiting(going, late)["finished"] == []
    # The prompt sends the last heartbeat at the very end of step 7.
    prompt = computer.session_prompt("network~read~1", "People", URL, "their job search")
    step7 = prompt[prompt.index("7. At the end"):prompt.index("8. Wake")]
    assert step7.index("tidy-folders") < step7.index("final heartbeat")


# ------------------------------------------------------------------ review 5


def test_an_archive_refused_because_the_chat_still_works_never_starts_a_second(
        tmp_path, monkeypatch):
    """Recorded as put away whatever archive_session answered, a chat still running counted as
    gone, and a second chat could start beside it on the same browser."""
    import json
    from datetime import timedelta
    done = dict(_w("network", "Harbourline Bank", to="computer"), status="done",
                claimed_by="session_mac1",
                finished_at=app_model.stamp(T - timedelta(hours=1)),
                computer_session={"id": "session_mac1",
                                  "at": app_model.stamp(T - timedelta(hours=2))})
    queued = _w("network", "Fernway Insurance", to="computer")
    db = dict(_db(("network~read~1", done), ("network~read~2", queued)), **_starter())

    def apply(batches):
        entry = json.load(open(batches[0], encoding="utf-8"))[0]
        fields = entry.get("data")
        if fields is None:
            with open(entry["file_path"], encoding="utf-8") as fh:
                fields = json.load(fh)
        out = dict(db)
        out["work"] = dict(db["work"], **{"network~read~1": {
            "data": dict(done, **fields), "version": 9}})
        return out
    refused = apply(computer.archived(db, "network~read~1", T, str(tmp_path / "r"),
                                      refused=True))
    sess = refused["work"]["network~read~1"]["data"]["computer_session"]
    assert sess.get("archive_refused") and not sess.get("archived_at")
    assert computer.busy_there(refused, T + timedelta(minutes=1)) == "session_mac1"
    _as(monkeypatch, "cloud", tmp_path)
    got = computer.route(refused, T + timedelta(minutes=1), chat="session_starter", envs=BRIDGE,
                         tools=["create_session"], url=URL)
    assert got["route"] == "computer busy", got
    # Not rung for again at every wake meanwhile; asked again later.
    assert computer.waiting(refused, T + timedelta(minutes=1))["finished"] == []
    later = T + timedelta(seconds=computer.END_WAIT_S + 60)
    assert computer.waiting(refused, later)["finished"] == [{"work": "network~read~1",
                                                            "session": "session_mac1"}]
    # Put away (or not found, or already archived): gone, and the next chat may start.
    gone = apply(computer.archived(db, "network~read~1", T, str(tmp_path / "g")))
    assert computer.busy_there(gone, T + timedelta(minutes=1)) == ""
    prompt = computer.starter_prompt(URL, "github.com/someone/my-job-search")
    assert "--refused" in prompt and "still at work" in prompt


# ------------------------------------------------------------------ review 7 and 8


def test_a_pin_renews_the_claim_kept_here_and_a_finish_ends_it(tmp_path):
    """The claim's lease runs from its last pin, and a finished job is held no more: the read
    gate and the sign-in route follow the claim this chat holds now."""
    import json
    from test_a_tick_on_the_page_is_applied_once import Search
    s = Search(str(tmp_path))
    s.put("work", "network~read~1", _w("network", "Harbourline Bank", to="computer",
                                       title="Reading on your computer"), version=1)
    s.run("next", s.dump, "--chat", "mac-job-7", "--kind", "computer", "--computer-only",
          "--now", NOW, "--claim-out", os.path.join(s.dump, "claim"))
    rec_path = os.path.join(s.state, ".ljs-claims.json")

    def rec():
        with open(rec_path, encoding="utf-8") as fh:
            return json.load(fh)["network~read~1"]
    first = rec()
    assert first["chat"] == "mac-job-7" and first["renewed"] == first["at"]
    s.run("pin", s.dump, "--work", "network~read~1", "--chat", "mac-job-7", "--stage", "read",
          "--line", "Reading the first profile.", "--now", NOW)
    assert rec()["renewed"] >= first["renewed"] and not rec().get("ended")
    s.run("done", s.dump, "--work", "network~read~1", "--chat", "mac-job-7", "--kind",
          "computer", "--summary", "Two profiles read.", "--now", NOW)
    assert rec().get("ended")


# ------------------------------------------------------------------ review 17 (C6)


def test_a_chat_on_the_computer_is_put_away_whoever_started_it(tmp_path, monkeypatch):
    """Only a chat the starter itself started (computer_session) was put away: one started by a
    task, or by an earlier helper, stayed open once its work was done."""
    import json
    import app
    import page_db
    from datetime import timedelta

    def work_fields(batches):
        for path in batches:
            for e in json.load(open(path, encoding="utf-8")):
                if page_db._LOGICAL.get(e["collection"], e["collection"]) == "work":
                    body = e.get("data")
                    if body is None:
                        with open(e["file_path"], encoding="utf-8") as fh:
                            body = json.load(fh)
                    return body
        return {}
    _as(monkeypatch, "computer", tmp_path)
    db = _db(("network~read~1", _w("network", "Harbourline Bank", to="computer",
                                   title="Reading on your computer")))
    chosen = app.choose(db, "session_mactask", "computer", T, on="claude-opus-5-5",
                        no_sessions=True, computer_only=True, claim_out=str(tmp_path / "c"))
    fields = work_fields(chosen["batches"])
    assert fields["computer_session"]["id"] == "session_mactask"
    done = dict(db["work"]["network~read~1"]["data"],
                **dict(fields, status="done", finished_at=app_model.stamp(T)))
    later = T + timedelta(seconds=computer.END_WAIT_S + 60)
    assert computer.waiting(_db(("network~read~1", done)), later)["finished"] == [
        {"work": "network~read~1", "session": "session_mactask"}]
    # The chat the starter started keeps its own record; a cloud chat lent the computer's
    # browser, and a chat the person opened there (plain next), are never recorded so.
    started = _db(("network~read~1", dict(db["work"]["network~read~1"]["data"],
                                          computer_session={"id": "session_mac1", "at": NOW})))
    again = app.choose(started, "session_mac1", "computer", T, on="claude-opus-5-5",
                       no_sessions=True, computer_only=True, claim_out=str(tmp_path / "s"))
    assert "computer_session" not in work_fields(again["batches"])
    lent = app.choose(db, "session_helper", "computer", T, on="claude-opus-5-5",
                      no_sessions=True, computer_only=True, lent=True,
                      claim_out=str(tmp_path / "l"))
    assert "computer_session" not in work_fields(lent["batches"])
    mine = app.choose(db, "session_persons", "computer", T, on="claude-opus-5-5",
                      no_sessions=True, claim_out=str(tmp_path / "p"))
    assert "computer_session" not in work_fields(mine["batches"])


# ------------------------------------------------------------------ review 18 (2C-6)


def test_the_bell_step_says_what_happens_when_publishing_is_not_allowed():
    """Step 8 rings the starter by republishing its bell, but publishing is not among the tools
    the chat is given ahead (STARTER_TOOLS): where it asks or is refused, the chat was left
    with nothing to do and nothing said."""
    prompt = computer.session_prompt("network~read~1", "People", URL, "their job search")
    step8 = prompt[prompt.index("8. Wake"):prompt.index("9. Your last")]
    assert "Artifact" not in computer.STARTER_TOOLS
    assert "asks for an approval" in step8 and "next wake" in step8
