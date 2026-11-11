"""A job's own chat is known by its own id, so a job that pauses is never run twice.

The second audit of 2026-11-10 (C1, root R4): a job's chat works under the id of the chat that
started it (the helper), and its own id was kept only in a local file. A job chat that paused on
an approval, or did not pin for half an hour, was started again in a second chat; both passed
the claim check, and the helper never saw its own job chats to ask how they were. Now the job
chat says on the job that it runs it (`run_by`, its first pin), another chat's writes are
refused, the helper lists its own job chats to ask, keeps a working one going (`pin --alive`),
and a job whose own chat is known waits one lease more before it is started again. Every chat
and employer here is invented.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import app  # noqa: E402
import app_model  # noqa: E402
import page_db  # noqa: E402
from test_a_tick_on_the_page_is_applied_once import NOW, _db, _w  # noqa: E402

T = app_model.parse_time(NOW)
HELPER, CHILD, SECOND = "session_EXAMPLEhelper1", "session_EXAMPLEchild1", "session_EXAMPLEchild2"


def _at(minutes: float) -> str:
    return app_model.stamp(T + dt.timedelta(minutes=minutes))


def _running(**kw):
    item = _w("draft", "Harbourline Bank", status="running", claimed_by=HELPER,
              claimed_at=_at(-10), lease_until=_at(20))
    item.update(kw)
    return item


def _body(batches) -> dict:
    with open(batches[0], encoding="utf-8") as fh:
        entry = json.load(fh)[0]
    with open(entry["file_path"], encoding="utf-8") as fh:
        return json.load(fh)


def test_the_job_chats_first_pin_says_it_runs_the_job_and_another_is_refused(tmp_path):
    db = _db(("d1", _running()))
    body = _body(page_db.pin(db, "d1", T, str(tmp_path / "a"), line="Started.", chat=HELPER,
                             me=CHILD)["batches"])
    assert body["run_by"] == CHILD
    mine = _db(("d1", _running(run_by=CHILD)))
    # Its own pins and finish go on; the chat that started it may still write (it claimed it).
    assert "run_by" not in _body(page_db.pin(mine, "d1", T, str(tmp_path / "b"), chat=HELPER,
                                             me=CHILD)["batches"])
    assert page_db.finish(mine, "d1", T, str(tmp_path / "c"), summary="Your letter is ready.",
                          chat=HELPER, me="")["status"] == "done"
    # A second chat started for the same job is refused, pin and finish alike.
    with pytest.raises(KeyError, match="another chat runs this job"):
        page_db.pin(mine, "d1", T, str(tmp_path / "d"), chat=HELPER, me=SECOND)
    with pytest.raises(KeyError, match="another chat runs this job"):
        page_db.finish(mine, "d1", T, str(tmp_path / "e"), summary="Your letter is ready.",
                       chat=HELPER, me=SECOND)


def test_the_helper_lists_its_own_job_chats_to_ask_how_they_are():
    db = _db(("d1", _running(run_by=CHILD)), ("d2", _running()))
    assert app.running_elsewhere(db, HELPER) == [("d1", CHILD)]


def test_a_job_whose_chat_is_known_waits_a_lease_more_before_it_starts_again(tmp_path):
    quiet = _running(run_by=CHILD, lease_until=_at(-5))
    assert page_db.next_item(_db(("d1", quiet)), "cloud", T, cap=page_db.HEAVY_CAP_CHATS) is None
    # Kept going by the helper, which asked and heard it is still at work.
    body = _body(page_db.mark_alive(_db(("d1", quiet)), "d1", T, str(tmp_path / "a"))["batches"])
    assert body["lease_until"] > NOW and set(body) <= {"lease_until", page_db.VERSION_FIELD}
    # A lease more with no word: started again, and the new claim knows no chat yet.
    later = T + dt.timedelta(minutes=page_db.LEASE_S / 60 + 1)
    db = _db(("d1", quiet))
    chosen = page_db.next_item(db, "cloud", later, cap=page_db.HEAVY_CAP_CHATS)
    assert chosen and chosen["again"] == 2
    claim = _body(page_db.claim(db, chosen, HELPER, "cloud", later, str(tmp_path / "c"),
                                beat=False))
    assert claim["run_by"] == {"__delete__": True}
    # With no chat of its own known, as before: started again once its lease is out.
    assert page_db.next_item(_db(("d1", _running(lease_until=_at(-5)))), "cloud", T,
                             cap=page_db.HEAVY_CAP_CHATS)


def test_the_job_chats_steps_begin_with_its_own_pin_and_the_command_finds_its_id(tmp_path):
    chosen = {"work": "d1", "kind": "draft", "title": "Draft", "stages": page_db.progress("draft")["stages"]}
    steps = " ".join(app.job_steps(chosen, HELPER, "https://claude.ai/artifact/p-1"))
    assert f"pin \"$D\" --work d1 --chat {HELPER} --line \"Started.\"" in steps
    dump = tmp_path / "dump"
    (dump / "work").mkdir(parents=True)
    with open(dump / "work" / "d1.json", "w", encoding="utf-8") as fh:
        json.dump({"data": _running(), "version": 3}, fh)
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "app.py"), "pin", str(dump),
                        "--work", "d1", "--chat", HELPER, "--line", "Started.", "--now", NOW],
                       capture_output=True, text=True, encoding="utf-8",
                       env=dict(os.environ, LJS_CHAT=CHILD))
    assert r.returncode == 0, r.stderr
    assert _body(json.loads(r.stdout)["batches"])["run_by"] == CHILD


def _first_pin(dump, *more):
    return subprocess.run([sys.executable, os.path.join(ROOT, "tools", "app.py"), "pin",
                           str(dump), "--work", "d1", "--chat", HELPER, "--line", "Started.",
                           "--first", "--now", NOW, *more],
                          capture_output=True, text=True, encoding="utf-8",
                          env=dict(os.environ, LJS_CHAT=CHILD))


def test_a_jobs_first_command_keeps_its_reads_versions_and_its_own_folder(tmp_path):
    """A job's own chat is told no versions step where its copy's settings hold the app's
    hook, but a chat runs the hooks it started with: its read may have kept none, and every
    write would be pinned to a stale number. And one folder name for every job (`j1`) had a
    job chat's second job read into the first one's (the review of 2026-11-11, E-6 and E-18).
    The job's folder is named after it, and its first command checks both before writing."""
    chosen = {"work": "draft~r9-3", "kind": "draft", "title": "Draft",
              "stages": page_db.progress("draft")["stages"]}
    steps = " ".join(app.job_steps(chosen, HELPER, "https://claude.ai/artifact/p-1"))
    assert "a fresh folder in your scratchpad named j-draft-r9-3," in steps
    assert "--line \"Started.\" --first" in steps
    # Read with no hook: the store's fields alone, no version kept.
    dump = tmp_path / "j-d1"
    (dump / "work").mkdir(parents=True)
    with open(dump / "work" / "d1.json", "w", encoding="utf-8") as fh:
        json.dump(_running(), fh)
    r = _first_pin(dump)
    assert r.returncode == 2 and "app.py versions" in r.stdout, r.stdout + r.stderr
    assert not (dump / "out").exists(), "nothing written"
    kept = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "app.py"), "versions",
                           str(dump)], input="work/d1 3\n", capture_output=True, text=True,
                          encoding="utf-8")
    assert kept.returncode == 0, kept.stdout + kept.stderr
    r = _first_pin(dump)
    assert r.returncode == 0, r.stdout + r.stderr
    assert _body(json.loads(r.stdout)["batches"])["run_by"] == CHILD
    # The same folder read into again for a later run of a job: refused, with a fresh one.
    r = _first_pin(dump)
    assert r.returncode == 2 and "holds an earlier run's read" in r.stdout, r.stdout
    assert str(tmp_path / "j-d1.2") in r.stdout and (tmp_path / "j-d1.2").is_dir()


def test_the_tidy_counts_a_job_to_the_chat_that_ran_it():
    """The second audit, C2: the tidy grouped jobs by the chat that claimed them, so a finished
    job chat was never seen as finished, and its unsaved work was never looked for."""
    import tidy
    done = dict(_running(run_by=CHILD), status="done", finished_at=_at(-1))
    db = _db(("d1", done), ("d2", _running()))
    assert tidy.finished_jobs(db) == {CHILD: _at(-1)}
    # Neither was done on the person's computer (tidy.on_computer, CC-1).
    assert tidy.job_items(db) == {CHILD: {"all": ["d1"], "done": ["d1"], "computer": False},
                                  HELPER: {"all": ["d2"], "done": [], "computer": False}}


def test_a_job_chat_that_asked_the_person_is_finished_while_they_answer(tmp_path):
    """The review of 2026-11-11 (item 3): a job chat that stopped on a question kept the item
    in its name (`run_by`), and the tidy counted the waiting item as still going, so that chat
    was never finished while the question waited, nor after the answer."""
    import tidy
    running = _running(run_by=CHILD)
    got = page_db.finish(_db(("d1", running)), "d1", T, str(tmp_path / "q"), chat=HELPER, me=CHILD,
                         question="Which of the two roles should the letter be for?")
    asked = dict(running, **{k: v for k, v in _body(got["batches"]).items() if k != page_db.VERSION_FIELD})
    assert tidy.finished_jobs(_db(("d1", asked))) == {CHILD: asked["asked_you_at"]}
    back = dict(asked, **page_db.answered(asked, "The analyst one", _at(5)))
    assert tidy.finished_jobs(_db(("d1", back))) == {CHILD: _at(5)}
