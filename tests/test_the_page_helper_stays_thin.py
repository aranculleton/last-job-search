"""The chat that answers the page stays thin: it reads only what changed, saves once a batch
without waking itself, and keeps what each wake cost.

The page's helper grew by hundreds of thousands of tokens a day: every tap read the whole
database (a line in the chat for each of some hundreds of records), printed the same long
text beside every batch, and every save woke the chat again, once when it ended and once more
when the hook held the turn for work still saving (the maintainer, 2026-11-05). Each wake's
work now runs in a short-lived subagent (the app skill, step 0); these pin what the code
does for it: `app.py reads` asks for what changed since the last read and lays the rest from
the copy this checkout keeps, a refused write makes the next read whole, a page another chat
drew is read before it is drawn over, `land.py --detach` returns at once and the hook stays
quiet while it runs, and `helper_usage` turns the session's own files into one number a day.
The store here is the folder that keeps the real one's rules, with `where` answered the way
ArtifactData's query answers it. Every person, employer, page and chat id is invented.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import pytest  # noqa: E402

import land  # noqa: E402
import test_a_ring_is_answered_in_one_command as R  # noqa: E402
import test_a_chat_lands_its_work_in_one_command as L  # noqa: E402
from test_a_chat_lands_its_work_in_one_command import write  # noqa: E402

LATER = "2026-10-25T18:01:00Z"


@pytest.fixture
def landing_copy(tmp_path, monkeypatch):
    """The landing tests' throwaway copy with a bare origin (never a real one)."""
    return L.copy.__wrapped__(tmp_path, monkeypatch)


@pytest.fixture
def ring(tmp_path, monkeypatch):
    monkeypatch.setenv("LJS_PAGE_MIRROR", str(tmp_path / "mirror"))
    r = R.Ring(tmp_path)
    r.mirror = str(tmp_path / "mirror")
    yield r
    sys.path.remove(r.root)


def query(r, out, q):
    """The store answering one query: `where` with >= and not-in, as ArtifactData does."""
    src = os.path.join(r.db, q["collection"])
    if not os.path.isdir(src):
        return
    for f in os.listdir(src):
        with open(os.path.join(src, f), encoding="utf-8") as fh:
            doc = json.load(fh)
        ok = True
        for field, op, val in q["query"].get("where") or []:
            v = doc["data"].get(field)
            ok = ok and v is not None and (str(v) >= str(val) if op == ">=" else v not in val)
        if ok:
            os.makedirs(os.path.join(out, q["collection"]), exist_ok=True)
            with open(os.path.join(out, q["collection"], f.replace("~", "@")), "w",
                      encoding="utf-8") as fh:
                json.dump(dict(doc["data"], _v=doc["version"]), fh)


def read(r, name, *args, now=R.NOW):
    """`app.py reads` and the queries it prints: (the folder, what reads printed)."""
    out = os.path.join(r.root, name)
    said = r.run("reads", out, "--now", now, *args, LJS_PAGE_MIRROR=r.mirror)
    for line in said.splitlines()[1:]:
        if line.startswith("{"):
            query(r, out, json.loads(line))
    return out, said


def records(folder):
    return sum(len([f for f in os.listdir(os.path.join(folder, c)) if f.endswith(".json")])
               for c in os.listdir(folder) if os.path.isdir(os.path.join(folder, c))
               and not c.startswith(".") and c not in ("wake", "view"))


def view(r, d, now=R.NOW, *extra):
    import fake_db
    got = json.loads(r.run("view", os.path.join(d, "v"), "--dump", d, "--chat", R.CHAT, "--now",
                           now, *extra, LJS_PAGE_MIRROR=r.mirror, ok=(0, 2)))
    return got, all(fake_db.apply(r.db, b) for b in got["batches"])


def wake(r, d, now=R.NOW):
    return r.run("wake", d, "--chat", R.CHAT, "--kind", "cloud", "--on", "Opus 5.5", "--now", now,
                 LJS_PAGE_MIRROR=r.mirror)


def used_page(r):
    """Two months of use: finished work, applied taps with their receipts."""
    for n in range(60):
        r.put("work", f"talk~old{n:02d}", {"kind": "talk", "status": "done", "title": "A question",
                                           "asked_at": "2026-10-01T10:00:00Z",
                                           "finished_at": "2026-10-01T10:05:00Z"})
        r.put("actions", f"old{n:02d}", {"action": "job.keep", "item": "x",
                                         "at": "2026-10-02T10:00:00Z"})
        r.put("receipts", f"old{n:02d}", {"result": "ok", "applied_at": "2026-10-02T10:01:00Z"})


# ------------------------------------------------------------------ 3. read only what changed

def test_a_wake_reads_only_what_changed_and_the_rest_is_laid_from_the_last_read(ring):
    used_page(ring)
    first, said = read(ring, "r1")
    assert "a whole read (nothing kept yet)" in said
    whole = records(first)
    assert whole > 180
    wake(ring, first)
    got, ok = view(ring, first)
    assert ok, got
    # A tap and a question since: the next read asks only for what changed.
    ring.queue("talk~new", kind="talk", asked_at=LATER)
    aid = ring.act("job.draft", "r9-3", value={"answers": {"already_applied": "no"}})
    d, said = read(ring, "r2", now=LATER)
    assert "what changed since" in said, said
    assert records(d) < 20, records(d)              # some 190 records before; a handful now
    said = wake(ring, d, now=LATER)
    # The folder holds the whole database once laid: a finished item from weeks ago is there
    # (a finished id asked for again is pinned to its version), and the one line says what
    # needs doing, by id.
    assert os.path.isfile(os.path.join(d, "work", "talk~old07".replace("~", "@") + ".json"))
    line = next(ln for ln in said.splitlines() if ln.startswith("read: "))
    assert "kept from the last read" in line and aid in line and "talk~new" in line, line
    assert len(line) < 400


def test_a_refused_write_makes_the_next_read_whole(ring):
    first, _ = read(ring, "r1")
    wake(ring, first)
    view(ring, first)
    d, said = read(ring, "r2", now=LATER)
    assert "what changed since" in said
    ring.run("version", d, "meta/listen", "7", LJS_PAGE_MIRROR=ring.mirror)
    _, said = read(ring, "r3", now=LATER)
    assert "a whole read (a write was refused)" in said
    # And the first wake of a new day reads whole by itself.
    d, _ = read(ring, "r4", now=LATER)
    wake(ring, d, now=LATER)
    _, said = read(ring, "r5", now="2026-10-26T07:00:00Z")
    assert "a whole read (a new day)" in said


def test_a_page_another_chat_drew_is_read_before_it_is_drawn_again(ring):
    first, _ = read(ring, "r1")
    wake(ring, first)
    assert view(ring, first)[1]
    # Another chat draws the page: the revision it leaves (meta/now) is not this copy's.
    now_doc = os.path.join(ring.db, "meta", "now.json")
    with open(now_doc, encoding="utf-8") as fh:
        doc = json.load(fh)
    doc["data"]["by"], doc["version"] = "session_EXAMPLEOTHER", doc["version"] + 1
    with open(now_doc, "w", encoding="utf-8") as fh:
        json.dump(doc, fh)
    d, _ = read(ring, "r2", now=LATER)
    wake(ring, d, now=LATER)
    assert not os.path.isdir(os.path.join(d, "screen"))     # never laid from the old copy
    got, _ = view(ring, d, LATER)
    assert got["batches"] == [] and "another chat drew the page" in got["for_claude"][0]
    for coll in ("screen", "addr"):
        query(ring, d, {"collection": coll, "query": {"limit": 1000}})
    got, ok = view(ring, d, LATER)
    assert ok, got
    # Drawn here again: the next read lays the screens and reads none of them.
    d2, _ = read(ring, "r3", now="2026-10-25T18:02:00Z")
    assert not os.path.isdir(os.path.join(d2, "screen"))
    wake(ring, d2, now="2026-10-25T18:02:00Z")
    assert os.path.isdir(os.path.join(d2, "screen"))


def test_a_ring_that_names_a_revision_already_read_needs_no_read(ring):
    assert "new since the last read" in ring.run("reads", "--rev", "4",
                                                 LJS_PAGE_MIRROR=ring.mirror)
    assert "nothing new" in ring.run("reads", "--rev", "4", LJS_PAGE_MIRROR=ring.mirror)
    assert "nothing new" in ring.run("reads", "--rev", "3", LJS_PAGE_MIRROR=ring.mirror)
    assert "new since" in ring.run("reads", "--rev", "5", LJS_PAGE_MIRROR=ring.mirror)


# ------------------------------------------------------------------ 4. once a batch, said once

def test_what_a_refusal_means_is_said_once_not_beside_every_batch(ring):
    ring.act("ready.applied", R.KESTREL)
    ring.queue("talk~1", kind="talk")
    d = ring.read("wake1")
    said = ring.wake(d)
    assert all(R.land(ring, said))
    said = ring.wake(d)
    whys = [why for _, why in R.sends(said)]
    assert len(whys) == 2, said
    assert sum("python3 tools/app.py version" in w for w in whys) <= 1, whys
    assert all(len(w) < 120 or "python3 tools/app.py version" in w for w in whys), whys


@pytest.mark.parametrize("system", ["posix", "nt"])
def test_a_detached_save_returns_at_once_and_the_hook_waits_for_it(landing_copy, capsys,
                                                                   monkeypatch, system):
    """Each system detaches its own way, and both are checked on every runner: a new session
    on Linux and Mac, and on Windows, where Popen has no sessions, a process with no console
    of its own in a group of its own (the creation flags, docs.python.org/3/library/
    subprocess.html). The test asked for a session on Windows too, and the Windows run of
    4.11.0 failed on it."""
    _origin, chat, _other = landing_copy
    write(chat, "profile/notes.md", "changed\n")
    assert land.save_due(str(chat), "a chat", "2026-11-05")       # unsaved: held, as before
    started = []
    with monkeypatch.context() as m:
        m.setattr(os, "name", system)
        if system == "nt":       # Windows' own values, where Linux and Mac have none
            m.setattr(subprocess, "DETACHED_PROCESS", 0x00000008, raising=False)
            m.setattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200, raising=False)
        code = land.detach(str(chat), "Notes", popen=lambda *a, **k: started.append((a, k)))
    out = capsys.readouterr().out
    assert code == 0 and out.strip() == "land: saving in the background; nothing to wait for or say."
    (args,), kw = started[0]
    assert "--run-detached" in args
    if system == "posix":
        assert kw.get("start_new_session") is True and "creationflags" not in kw, kw
    else:
        assert "start_new_session" not in kw, kw
        assert kw["creationflags"] == 0x00000008 | 0x00000200, kw
    assert kw["stdin"] is not None and kw["stdout"] is not None    # nothing reaches the chat
    # Asked for and not finished: the hook holds no turn for it.
    assert land.wanted(str(chat))
    assert land.save_due(str(chat), "a chat", "2026-11-05") == []


def test_a_save_asked_for_is_aged_on_the_clock_that_asked(landing_copy):
    """The mark was aged by the file's time, the disk's clock: on a clock moved a month on (the
    4.11.0 clock runs) a mark a second old read as stale, and the hook held the turn the
    background save was already taking. It is aged by its own "at", as the lock is."""
    _origin, chat, _other = landing_copy
    p = land._mark(str(chat), land.WANTED_FILE, json.dumps({"message": "Notes", "at": time.time()}) + "\n")
    old = time.time() - 40 * 86400
    os.utime(p, (old, old))                        # the disk's clock, far from this one
    assert land.wanted(str(chat))
    land._mark(str(chat), land.WANTED_FILE, json.dumps({"message": "Notes", "at": old}) + "\n")
    assert not land.wanted(str(chat))              # asked a month ago, never finished: stale
    land._mark(str(chat), land.WANTED_FILE, "\n")  # no stamp: aged by the file, as before
    assert land.wanted(str(chat))


def test_a_detached_save_opens_and_merges_its_pull_request_itself(landing_copy, capsys):
    _origin, chat, _other = landing_copy
    calls = []

    class R_:
        def __init__(self, code, out):
            self.returncode, self.stdout, self.stderr = code, out, ""

    def run(args, **kw):
        calls.append(args)
        if "POST" in args:
            return R_(0, json.dumps({"number": 41}))
        return R_(0, json.dumps({"merged": True}))
    ok, number = land.finish_on_github(str(chat), {"owner": "someone", "repo": "my-job-search",
                                                   "head": "claude/chat-1", "title": "Notes",
                                                   "body": "green"}, run=run,
                                       which=lambda name: "/usr/bin/gh")
    assert ok and number == "41"
    assert calls[0][:4] == ["gh", "api", "-X", "POST"] and "head=claude/chat-1" in calls[0]
    assert calls[1][:5] == ["gh", "api", "-X", "PUT", "repos/someone/my-job-search/pulls/41/merge"]
    # Where GitHub's part cannot be done here, the calls are kept and said once, by the next
    # read, never again.
    write(chat, "profile/notes.md", "changed\n")

    def landed(root, message, check=None, sleep=None):
        print("land: ready claude/chat-1 (1 commit(s) ahead of master)")
        print("land: next, each its own call, and nothing said to the person:")
        print('  1. create_pull_request: owner "someone"')
        land.READY.update({"owner": "someone", "repo": "r", "head": "claude/chat-1",
                           "title": "t", "body": "b"})
        return 0
    land.run_detached(str(chat), "Notes", land_fn=landed,
                      finish=lambda root, ready: (False, "gh is not on this computer"))
    said = land.github_waiting(str(chat))
    assert "could not be done here (gh is not on this computer)" in said
    assert "create_pull_request" in said
    assert land.github_waiting(str(chat)) == ""
    assert not land.wanted(str(chat))


def test_the_hook_holds_no_turn_for_a_save_this_turn_started():
    import learned
    assert "--detach" in learned.SAVE_STEPS and "run_in_background" not in learned.SAVE_STEPS
    for ran in ("python3 tools/land.py --detach --message Notes",
                "python3 tools/land.py --message Notes",
                'python3 tools/app.py view "$D/view" --dump "$D" --chat x --end --message y'):
        assert learned._LANDING.search(ran), ran
    for ran in ("python3 tools/land.py --after-merge", "python3 tools/app.py view x --dump y"):
        assert not learned._LANDING.search(ran), ran


def end(ring, d, now, reads=True):
    """`app.py view --end`, with the late reads it asks for made first (the store answering
    them), as a wake's subagent ends its batch."""
    run = lambda: json.loads(ring.run(  # noqa: E731
        "view", os.path.join(d, "v"), "--dump", d, "--chat", R.CHAT, "--now", now, "--end",
        "--message", "Answered", LJS_PAGE_MIRROR=ring.mirror, ok=(0, 2)))
    got = run()
    asked = [ln for ln in got.get("for_claude") or [] if "came in while the work ran" in ln]
    if asked and reads:
        assert got["batches"] == [] and len(asked) == 1, got
        for q in re.findall(r"\{\"collection\".*?\]\]\}\}", asked[0]):
            query(ring, d, json.loads(q))
        got = run()
    return got


def test_taps_made_while_the_work_ran_are_applied_before_the_batch_ends(ring):
    """Seven "I sent it" taps made while the helper answered another question waited for the
    person's next message: only a wake's start read taps (the maintainer's copy, 2026-11-05).
    The end of the batch reads what came in since the wake's read and applies it there."""
    import fake_db
    first, _ = read(ring, "r1")
    wake(ring, first)
    assert view(ring, first)[1]
    before = ring.tracker()
    d, _ = read(ring, "r2", now=LATER)
    assert all(R.land(ring, wake(ring, d, now=LATER)))
    # While the wake's work runs, the person taps: after its read.
    aid = ring.act("ready.applied", R.KESTREL)
    got = json.loads(ring.run("view", os.path.join(d, "v"), "--dump", d, "--chat", R.CHAT,
                              "--now", LATER, "--end", LJS_PAGE_MIRROR=ring.mirror, ok=(2,)))
    asked = got["for_claude"][0]
    assert got["batches"] == [] and "came in while the work ran" in asked, got
    assert '"collection":"actions"' in asked and '["at",">="' in asked
    for q in re.findall(r"\{\"collection\".*?\]\]\}\}", asked):
        query(ring, d, json.loads(q))
    # The tap changes the copy: its claim first, then the same command applies it.
    got = json.loads(ring.run("view", os.path.join(d, "v"), "--dump", d, "--chat", R.CHAT,
                              "--now", LATER, "--end", LJS_PAGE_MIRROR=ring.mirror, ok=(2,)))
    assert "1 tap came in while the work ran" in got["for_claude"][0], got
    assert all(fake_db.apply(ring.db, b) for b in got["batches"])
    assert ring.stored("actions", aid)["data"]["claimed_by"] == R.CHAT
    got = json.loads(ring.run("view", os.path.join(d, "v"), "--dump", d, "--chat", R.CHAT,
                              "--now", LATER, "--end", LJS_PAGE_MIRROR=ring.mirror))
    assert any("1 applied" in ln for ln in got["for_claude"]), got
    assert all(fake_db.apply(ring.db, b) for b in got["batches"])
    assert ring.stored("receipts", aid)["data"]["result"] == "ok"
    assert ring.tracker() != before
    # Work asked for meanwhile is named, for the helper to take before it ends.
    d, _ = read(ring, "r3", now="2026-10-25T18:05:00Z")
    assert all(R.land(ring, wake(ring, d, now="2026-10-25T18:05:00Z")))
    ring.queue("talk~late", kind="talk", asked_at="2026-10-25T18:06:00Z")
    got = end(ring, d, "2026-10-25T18:07:00Z")
    said = [ln for ln in got.get("for_claude") or [] if ln.startswith("late: ")]
    assert len(said) == 1 and "talk~late" in said[0] and "app.py wake" in said[0], got
    assert all(fake_db.apply(ring.db, b) for b in got["batches"])
    # Ended again without taking it, it is named again: a pass that ended on the first naming
    # left two follow-ups queued for minutes (the maintainer's copy, 2026-11-05).
    got = end(ring, d, "2026-10-25T18:08:00Z")
    said = [ln for ln in got.get("for_claude") or [] if ln.startswith("late: ")]
    assert len(said) == 1 and "talk~late" in said[0], got
    assert all(fake_db.apply(ring.db, b) for b in got["batches"])
    # Taken (claimed by the wake that line names), it is named no more.
    assert all(R.land(ring, wake(ring, d, now="2026-10-25T18:09:00Z")))
    assert ring.stored("work", "talk~late")["data"]["claimed_by"] == R.CHAT
    got = end(ring, d, "2026-10-25T18:10:00Z")
    assert not [ln for ln in got.get("for_claude") or [] if ln.startswith("late: ")], got


def test_follow_ups_tapped_while_a_pass_ran_are_taken_and_written_by_claude(
        ring):
    """Two follow-ups queued while a pass of the helper ran sat on "starts in a moment" for
    minutes after it ended; it said each waited on a question, but neither was taken and no
    card asked anything (the maintainer's copy, 2026-11-05). The pass's end names them until
    they are taken; taken, one command drafts them, and one with nothing new to say is
    Claude's to write, never a question for the person."""
    import fake_db
    import subprocess
    import app_state
    import repo_files
    # The person's own rule: no follow-up with nothing new to say, so code cannot write it.
    with open(os.path.join(ring.profile, "networking.py"), "a", encoding="utf-8") as fh:
        fh.write("\nPLAIN_NUDGE = False\n")
    ids = app_state.nudges_due(ring.state, 2)
    first, _ = read(ring, "r1")
    wake(ring, first)
    assert view(ring, first)[1]
    d, _ = read(ring, "r2", now=LATER)
    assert all(R.land(ring, wake(ring, d, now=LATER)))
    # While that pass runs, the person taps Follow up on two people.
    for n, cid in enumerate(ids):
        ring.put("work", "follow_up~" + cid, {
            "kind": "follow_up", "status": "queued", "to": "either", "title": "Follow up",
            "asked_at": f"2026-10-25T18:0{2 + n}:00Z", "args": {"contact": cid}})
    work = ["follow_up~" + cid for cid in ids]
    for at in ("2026-10-25T18:05:00Z", "2026-10-25T18:06:00Z"):
        got = end(ring, d, at)
        said = [ln for ln in got.get("for_claude") or [] if ln.startswith("late: ")]
        assert len(said) == 1 and all(w in said[0] for w in work), got
        assert all(fake_db.apply(ring.db, b) for b in got["batches"])
    said = wake(ring, d, now="2026-10-25T18:07:00Z")
    assert all(R.land(ring, said)), said
    assert f"app.py follow-ups \"{d}\"" in said, said
    ran = subprocess.run([*repo_files.python_on_github(os.path.join(R.ROOT, "tools", "app.py")),
                          "follow-ups", d, "--chat", R.CHAT, "--now", "2026-10-25T18:08:00Z",
                          "--today", "2026-10-25"], env=ring.env(LJS_PAGE_MIRROR=ring.mirror),
                         capture_output=True, encoding="utf-8", timeout=120)
    assert ran.returncode == 0, ran.stdout + ran.stderr
    # With nothing new to say they are Claude's to write, never the person's to answer (the
    # maintainer, 2026-11-06: "Asking the person should never be the fallback").
    assert "0 put to the person as a question" in ran.stdout and "2 to write here" in ran.stdout, ran.stdout
    for b in [ln for ln in ran.stdout.splitlines() if ln.endswith(".json")]:
        assert fake_db.apply(ring.db, b), b
    for w in work:
        item = ring.stored("work", w)["data"]
        assert item["status"] != "needs_you" and not item.get("needs"), item
    # Nothing is left for the pass to take: its end names nothing.
    got = end(ring, d, "2026-10-25T18:09:00Z")
    assert not [ln for ln in got.get("for_claude") or [] if ln.startswith("late: ")], got


def test_a_page_update_that_ends_a_batch_clears_saving_and_starts_no_save_outside_a_copy(ring):
    import fake_db
    first, _ = read(ring, "r1")
    wake(ring, first)
    view(ring, first)
    ring.put("beats", R.CHAT.replace("~", "@"), {"chat": R.CHAT, "busy": "Saving your work",
                                                  "seen_at": R.NOW})
    d, _ = read(ring, "r2", now=LATER)
    assert all(R.land(ring, wake(ring, d, now=LATER)))
    got = end(ring, d, LATER)
    assert all(fake_db.apply(ring.db, b) for b in got["batches"])
    assert ring.stored("beats", R.CHAT)["data"]["busy"] is None
    assert "for_claude" not in got or not any("land" in x for x in got["for_claude"])


# ------------------------------------------------------------------ 5. what a wake cost

def _session(home, name, turns):
    path = home / "projects" / "-home-user" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps({"type": "assistant", "message": {"usage": {
        "input_tokens": 2, "cache_read_input_tokens": r, "cache_creation_input_tokens": w,
        "output_tokens": o}}}) for r, w, o in turns) + "\n", encoding="utf-8")
    return path


def test_each_wake_keeps_what_it_cost_and_the_day_is_one_number(tmp_path, monkeypatch):
    import helper_usage
    import merge_state
    home = tmp_path / "claude"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(home))
    monkeypatch.setenv("LJS_STATE", str(tmp_path / "state"))
    listener = _session(home, "s1.jsonl", [(50_000, 2_000, 300), (60_000, 0, 200)])
    _session(home, "s1/subagents/agent-1.jsonl", [(40_000, 10_000, 500), (52_000, 0, 900)])
    os.utime(listener, (1, 1))           # the listener's own file is the only top-level one
    now = dt.datetime(2026, 11, 5, 9, 0, tzinfo=dt.timezone.utc)
    e = helper_usage.record("wake", "session_EXAMPLEHELPER", now)
    assert e["listener"] == 60_002 and e["agent_in"] == 102_004 and e["agent_out"] == 1400
    assert 0 < e["est_usd"] < 1
    # A cost get_session gave is used as it is.
    e2 = helper_usage.record("wake", "session_EXAMPLEHELPER", now + dt.timedelta(minutes=5),
                             usage={"usage": {"total_cost_usd": 0.31}})
    assert e2["est_usd"] == 0.31 and e2["cost_from"] == "get_session"
    helper_usage.record("handover", "session_EXAMPLEHELPER", now + dt.timedelta(hours=1),
                        tokens=650_000)
    line = helper_usage.day_line("2026-11-05")
    assert line.startswith("Answering your page cost about $") and "2 taps" in line, line
    assert helper_usage.day_line("2026-11-04") == ""
    with open(helper_usage.path(), encoding="utf-8") as fh:
        kept = json.load(fh)
    assert [x["kind"] for x in kept["entries"]] == ["wake", "wake", "handover"]
    # Two chats adding entries on one day keep both, entry by entry.
    rules = merge_state.json_rules("documents/helper_usage.json")
    assert rules["lists"] == {"entries": ("at", "chat", "kind")}
    with open(os.path.join(ROOT, ".gitattributes"), encoding="utf-8") as fh:
        assert "documents/helper_usage.json merge=ljs-state" in fh.read()


def test_the_apps_own_checkout_is_never_written_to(monkeypatch, tmp_path):
    import helper_usage
    import person
    monkeypatch.delenv("LJS_STATE", raising=False)
    monkeypatch.setattr(person, "state", lambda *p: os.path.join(str(tmp_path), *p))
    helper_usage.record("wake", "session_EXAMPLEHELPER")
    assert not os.path.exists(os.path.join(str(tmp_path), "documents"))
