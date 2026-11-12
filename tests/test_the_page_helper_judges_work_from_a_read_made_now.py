"""The page's helper judges work from a read made now, and work for the computer is never
queued twice (issue #255).

A first Find people run on the person's computer had finished, at 8 of 20. The person then
asked the page's helper, in a message, for 12 more. The helper answered that nothing new needed
doing and their people search was still running on their computer, and queued nothing: it
judged from a read of the page made before that run finished (`app.py ask` refused "one at a
time: ... is still going" from the folder the wake had read minutes before, and a wake run
again over that folder said nothing was waiting). A little later the same 12 were queued twice,
once by the helper and once from what the person typed in the chat on their computer, each
asked from a read that did not hold the other.

Now `app.py ask` queues nothing from a folder read more than `page_reads.FRESH_S` ago: it names
a read of the page's work to make now, into a fresh folder, and is run again over that; a wake
run again over an old folder asks for a new read before it says that nothing is waiting; and
work for the computer already queued or running for the same thing is not queued again, the
answer saying it is on its way. The store is the folder that keeps the real one's rules
(tests/test_the_page_helper_stays_thin.py). Every person, page, computer and chat id is
invented.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import pytest  # noqa: E402

import app_model  # noqa: E402
import page_db  # noqa: E402
import page_reads  # noqa: E402
import repo_files  # noqa: E402
import test_a_ring_is_answered_in_one_command as R  # noqa: E402
import test_the_page_helper_stays_thin as T  # noqa: E402

FIRST = "network~20261025T1730-ab12"
MAC = "session_EXAMPLEMACCHAT"
AFTER_IT_FINISHED = "2026-10-25T18:02:00Z"
A_MOMENT_ON = "2026-10-25T18:00:40Z"
FIVE_MINUTES_ON = "2026-10-25T18:05:00Z"
SIX_MINUTES_ON = "2026-10-25T18:06:00Z"


@pytest.fixture
def ring(tmp_path, monkeypatch):
    yield from T.ring.__wrapped__(tmp_path, monkeypatch)


def first_run(status: str, **more) -> dict:
    """The first Find people run, sent to the person's computer."""
    return dict({"kind": "network", "title": "Find people", "to": "computer",
                 "args": {"count": 20}, "status": status,
                 "asked_at": "2026-10-25T17:30:00Z", "changed_at": "2026-10-25T17:40:00Z",
                 "claimed_by": MAC, "claimed_as": "computer", "stage": 1}, **more)


def ask(r, folder, *args, now, **env):
    """`app.py ask` as a chat runs it: (exit code, everything it printed)."""
    got = subprocess.run([*repo_files.python_on_github(os.path.join(ROOT, "tools", "app.py")),
                          "ask", folder, "--kind", "network", *args, "--now", now],
                         env=r.env(LJS_PAGE_MIRROR=r.mirror, **env), capture_output=True,
                         encoding="utf-8", errors="replace", timeout=120)
    return got.returncode, got.stdout + got.stderr


def open_network(r) -> list[str]:
    """The networking runs the store holds that are not finished."""
    src = os.path.join(r.db, "work")
    out = []
    for f in sorted(os.listdir(src)):
        with open(os.path.join(src, f), encoding="utf-8") as fh:
            d = json.load(fh)["data"]
        if d.get("kind") == "network" and d.get("status") not in page_db.FINISHED:
            out.append(f[:-5])
    return out


def read_as_asked(r, said: str) -> str:
    """The reads `ask` named, made into the folder it named, as ArtifactData answers them."""
    folder = re.search(r'out_dir "([^"]+)"', said).group(1)
    queries = [json.loads(ln) for ln in said.splitlines() if ln.startswith("{")]
    assert queries, said
    for q in queries:
        T.query(r, folder, q)
    return folder


# ------------------------------------------------------------------ 1. the issue, as it went


def test_more_people_asked_for_after_a_run_finished_are_judged_from_a_read_made_now(ring):
    import fake_db
    ring.put("work", FIRST, first_run("running"), version=4)
    d, _ = T.read(ring, "r1")                       # the wake's read, before the run finished
    assert all(R.land(ring, T.wake(ring, d)))
    # The run on the computer finishes at 8 of 20, after that read.
    ring.put("work", FIRST, first_run("done", finished_at=AFTER_IT_FINISHED,
                                      changed_at=AFTER_IT_FINISHED,
                                      count={"done": 8, "total": 20, "word": "found"}), version=5)
    # Five minutes on, the person asks for 12 more. From the old read, nothing is judged: no
    # "still going", nothing queued, and a read of the page's work to make now, elsewhere.
    code, said = ask(ring, d, "--title", "12 more people", "--args", '{"count": 12}', "--to",
                     "computer", "--chat", R.CHAT, now=FIVE_MINUTES_ON)
    assert "still going" not in said, said
    assert code == 3 and "nothing is queued" in said, (code, said)
    assert not os.path.isdir(os.path.join(d, "out")), "it wrote nothing from the old read"
    fresh = read_as_asked(ring, said)
    assert os.path.abspath(fresh) != os.path.abspath(d)
    assert f'"{fresh}" in place of "{d}"' in said, said
    # Asked again over the read made now: the first run is finished there, so the 12 are queued.
    code, said = ask(ring, fresh, "--title", "12 more people", "--args", '{"count": 12}', "--to",
                     "computer", "--chat", R.CHAT, now=FIVE_MINUTES_ON)
    assert code == 0, said
    got = json.loads(said)
    assert not got.get("already") and got["work"] != FIRST, got
    assert all(fake_db.apply(ring.db, b) for b in got["batches"])
    assert open_network(ring) == [got["work"]]
    # The person types the same in the chat on their computer, which reads the page now and
    # asks for it as its own: the same work is on its way, and nothing is queued twice.
    code, said = ask(ring, os.path.join(ring.root, "mac"), "--title", "Find 12 more people",
                     "--args", '{"count": 12}', "--here", "--chat", MAC, now=SIX_MINUTES_ON)
    assert code == 3, said                                # that folder holds no read yet
    mac = read_as_asked(ring, said)
    code, said = ask(ring, mac, "--title", "Find 12 more people", "--args", '{"count": 12}',
                     "--here", "--chat", MAC, now=SIX_MINUTES_ON)
    assert code == 0, said
    again = json.loads(said)
    assert again["already"] is True and again["work"] == got["work"], again
    assert again["batches"] == [] and "already on its way" in again["say"], again
    assert "12 more people" in again["say"]
    assert open_network(ring) == [got["work"]], "queued once, never twice"


# ------------------------------------------------------------------ 2. never queued twice


T0 = app_model.parse_time(R.NOW)


def _db(*items) -> dict:
    return {"work": {wid: {"data": d, "version": 2} for wid, d in items}}


def _queued(args, status="queued", to="computer", kind="network", **more) -> dict:
    return dict({"kind": kind, "title": "12 more people", "to": to, "args": args,
                 "status": status, "asked_at": "2026-10-25T17:55:00Z"}, **more)


@pytest.mark.parametrize("status", ["queued", "claimed", "running", "needs_you"])
def test_computer_work_already_on_its_way_is_never_queued_again(tmp_path, monkeypatch, status):
    import computer
    db = _db(("network~more", _queued({"count": 12, "note": "Product teams"}, status=status)))
    out = str(tmp_path / "out")
    # Asked in the chat on the computer, as its own, with the same words spaced and cased
    # another way and the count as text: the same thing.
    got = page_db.ask(db, "network", "Find 12 more", T0, out,
                      args={"note": " product  Teams ", "count": "12"}, chat_id=MAC,
                      here=True, chat_kind="computer")
    assert got["already"] is True and got["work"] == "network~more" and got["batches"] == []
    assert "already on its way" in got["say"] and "12 more people" in got["say"]
    assert "nothing is done twice" in got["then"]
    assert not os.path.exists(out), "nothing written"
    # Asked in a cloud chat while the computer is ready: sent there, so the same.
    monkeypatch.setattr(computer, "networking_there", lambda db, now: True)
    got = page_db.ask(db, "network", "12 more", T0, out, args={"count": 12, "note": "product teams"},
                      chat_id="session_EXAMPLECLOUD", chat_kind="cloud")
    assert got["already"] is True and got["work"] == "network~more"


def test_the_same_asked_after_it_finished_or_for_another_thing_is_not_on_its_way(tmp_path):
    # Finished: asked again, it is new work.
    db = _db(("network~first", _queued({"count": 12}, status="done")))
    got = page_db.ask(db, "network", "12 more people", T0, str(tmp_path / "a"),
                      args={"count": 12}, to="computer")
    assert not got.get("already") and got["work"] != "network~first" and got["batches"]
    # Another thing while one runs: refused as one at a time, as before, never "on its way".
    db = _db(("network~first", _queued({"count": 12}, status="running")))
    with pytest.raises(ValueError, match="one at a time"):
        page_db.ask(db, "network", "People at a bank", T0, str(tmp_path / "b"),
                    args={"company": "Harbourline Bank"}, to="computer")


# ------------------------------------------------------------------ 3. a read made now


def test_a_read_is_judged_by_when_it_was_made(tmp_path):
    now = dt.datetime(2026, 10, 25, 18, 5, tzinfo=dt.timezone.utc)
    # Never read: there is nothing to judge from.
    assert page_reads.read_age_s(str(tmp_path / "none"), now) is None
    # A read `reads` planned, and one `ask` asked for, are as old as their plan.
    planned = tmp_path / "w1"
    planned.mkdir()
    (planned / page_reads.PLAN).write_text(json.dumps({"at": "2026-10-25T18:00:00Z"}))
    assert page_reads.read_age_s(str(planned), now) == 300
    got = page_reads.fresh_read(str(planned), now)
    assert got["dump"] != str(planned) and page_reads.read_age_s(got["dump"], now) == 0
    assert {q["collection"] for q in got["queries"]} >= {"work", "holds", "beats"}
    # A folder a chat read by hand is as old as what it saved.
    hand = tmp_path / "hand"
    (hand / "work").mkdir(parents=True)
    (hand / "work" / "talk~one.json").write_text("{}")
    old = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=10)).timestamp()
    os.utime(hand / "work" / "talk~one.json", (old, old))
    assert page_reads.read_age_s(str(hand), now) > page_reads.FRESH_S
    # The reads that end a batch bring the work asked for since: a wake taking it judges by them.
    (planned / page_reads.PLAN).write_text(json.dumps({"at": "2026-10-25T18:00:00Z",
                                                       "late_from": "2026-10-25T18:04:00Z"}))
    assert page_reads.read_age_s(str(planned), now, late=True) == 60
    assert page_reads.read_age_s(str(planned), now) == 300


def test_a_wake_run_again_over_an_old_read_reads_again_before_saying_nothing_waits(ring):
    d, _ = T.read(ring, "r1")
    assert all(R.land(ring, T.wake(ring, d)))
    # Run again at once (step 3 again, after a big job's call): from the same read, as before.
    said = T.wake(ring, d, now=A_MOMENT_ON)
    assert "nothing else is waiting" in said, said
    # Minutes on, never: a run may have finished, or work been asked for, since.
    said = T.wake(ring, d, now=FIVE_MINUTES_ON)
    assert "nothing else is waiting" not in said and "app.py reads --in" in said, said
    assert "\nnext: " not in said and not R.sends(said), "nothing taken or sent from it"


def test_the_skill_says_so():
    import app_skill
    text = " ".join(app_skill.text().split())
    assert "already on its way" in text, "the helper is told what an ask for the same says"
