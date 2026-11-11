"""Work the person hands to a chat in that chat is taken there, and only held work is pinned.

Found by the audit of 2026-11-10. On the computer, a chat saw LinkedIn signed in again, but
the job stayed parked waiting on the person until they found its card and tapped Done, 22
minutes on: no command let the chat take its own question back when the person said "logged
in" there (CC-3). When the person typed "just read them here", the chat read the profiles while
the queued job sat unclaimed, so the job was started again elsewhere and the reads ran twice
(CC-19). And a pin on work waiting for the person made it running with nobody's claim, so any
chat could pin or finish it and, its lease out, it was handed to another chat (PE-1).
`app.py resume` takes such work into the chat, and `pin` refuses work no chat holds. Every
person, employer and computer here is invented.
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
from test_a_tick_on_the_page_is_applied_once import NOW, _db, _w  # noqa: E402

T = app_model.parse_time(NOW)
AT = app_model.stamp(T)
QUESTION = "LinkedIn is signed out in Claude's browser."


def _signin(**kw):
    item = _w("network", "Harbourline Bank", to="computer", status="needs_you")
    item.update(note=QUESTION, needs={"question": QUESTION, "signin": "linkedin"},
                asked_you_at=app_model.stamp(T - dt.timedelta(minutes=6)), claimed_by=None,
                computer_session={"id": "session_mac1", "at": app_model.stamp(T - dt.timedelta(minutes=20))},
                **kw)
    return item


def _body(batches) -> dict:
    with open(batches[0], encoding="utf-8") as fh:
        entry = json.load(fh)[0]
    with open(entry["file_path"], encoding="utf-8") as fh:
        return json.load(fh)


def _after(item, fields):
    out = dict(item)
    for k, v in fields.items():
        if v is None:
            out.pop(k, None)
        else:
            out[k] = v
    return out


# ------------------------------------------------------------------ CC-3: an answer given in the chat


def test_an_answer_given_in_the_chat_takes_its_own_question_back(tmp_path):
    item = _signin()
    db = _db(("network~read~1", item))
    got = page_db.resume(db, "network~read~1", "mac-1", "computer", T, str(tmp_path),
                         answer="logged in")
    after = _after(item, _body(got["batches"]))
    assert after["status"] == "running" and after["claimed_by"] == "mac-1" and after["in_chat"]
    assert after["claimed_as"] == "computer" and after["lease_until"] > AT
    for k in ("note", "needs", "asked_you_at", "choices"):
        assert not after.get(k), (k, after)
    assert after["args"]["answers"] == {QUESTION: "logged in"}
    # Its own chat has it: no other chat is started for it, nor given it.
    assert computer.waiting(_db(("network~read~1", after)), T) == \
        {"queued": [], "started": {}, "finished": []}
    assert page_db.next_item(_db(("network~read~1", after)), "computer", T) is None
    # Pinned and finished as any claimed work.
    db2 = _db(("network~read~1", after))
    assert page_db.pin(db2, "network~read~1", T, str(tmp_path / "p"), stage="read",
                       chat="mac-1")["batches"]


def test_a_question_taken_back_needs_their_words():
    db = _db(("network~read~1", _signin()))
    with pytest.raises(ValueError, match="--answer"):
        page_db.resume(db, "network~read~1", "mac-1", "computer", T, "/nonexistent")


# ------------------------------------------------------------------ CC-19: "just read them here"


def test_queued_work_done_in_the_chat_is_claimed_there_and_never_started_again(tmp_path):
    item = _w("network", "Harbourline Bank", to="computer")
    db = _db(("network~read~2", item))
    assert computer.waiting(db, T)["queued"] == ["network~read~2"]
    got = page_db.resume(db, "network~read~2", "mac-1", "computer", T, str(tmp_path))
    after = _after(item, _body(got["batches"]))
    assert after["status"] == "running" and after["claimed_by"] == "mac-1" and after["in_chat"]
    assert "the chat you asked in" in after["steps"][-1]["text"]
    later = _db(("network~read~2", after))
    assert computer.waiting(later, T) == {"queued": [], "started": {}, "finished": []}
    # Even once its lease is out it is never started again elsewhere: begun in the chat, it is
    # that chat's (page_db.next_item, computer.lapsed).
    much_later = T + dt.timedelta(hours=2)
    assert computer.waiting(later, much_later)["queued"] == []
    assert page_db.next_item(later, "computer", much_later) is None


def test_another_chat_still_at_it_keeps_it_and_a_cloud_chat_never_takes_computer_work(tmp_path):
    running = _w("network", "Harbourline Bank", to="computer", status="running",
                 claimed_by="mac-2", claimed_at=AT,
                 lease_until=app_model.stamp(T + dt.timedelta(minutes=20)))
    with pytest.raises(KeyError, match="another chat"):
        page_db.resume(_db(("n", running)), "n", "mac-1", "computer", T, str(tmp_path))
    gone = dict(running, lease_until=app_model.stamp(T - dt.timedelta(minutes=5)))
    assert page_db.resume(_db(("n", gone)), "n", "mac-1", "computer", T, str(tmp_path / "g"))
    with pytest.raises(ValueError, match="computer"):
        page_db.resume(_db(("n", _w("network", to="computer"))), "n", "session_cloud", "cloud", T,
                       str(tmp_path / "c"))
    for status in ("done", "stopped"):
        with pytest.raises(KeyError):
            page_db.resume(_db(("n", _w("network", to="computer", status=status))), "n", "mac-1",
                           "computer", T, str(tmp_path / status))


def test_resume_is_one_command(tmp_path):
    dump = tmp_path / "dump"
    (dump / "work").mkdir(parents=True)
    # "network~read~1" as the dump names it ("~" is kept as "@" on disk), made here rather
    # than written out, which reads as an email address to the leak scan.
    name = "~".join(("network", "read", "1")).replace("~", "@") + ".json"
    with open(dump / "work" / name, "w", encoding="utf-8") as fh:
        json.dump({"data": _signin(), "version": 4}, fh)
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "app.py"), "resume", str(dump),
                        "--work", "network~read~1", "--chat", "mac-1", "--kind", "computer",
                        "--answer", "logged in", "--now", NOW],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stdout + r.stderr
    got = json.loads(r.stdout)
    assert got["batches"] and "app.py done" in got["then"]
    # Kept in the folder as it will be once sent: the pin made next is pinned to it.
    db = page_db.load(str(dump))
    assert db["work"]["network~read~1"]["data"]["claimed_by"] == "mac-1"
    assert db["work"]["network~read~1"]["version"] == 5


# ------------------------------------------------------------------ PE-1: only held work is pinned


def test_a_pin_on_work_no_chat_holds_is_refused(tmp_path):
    for status in ("needs_you", "queued"):
        db = _db(("n", _w("network", to="computer", status=status, claimed_by=None)))
        with pytest.raises(KeyError, match="not claimed"):
            page_db.pin(db, "n", T, str(tmp_path / status), stage="read", chat="mac-1")
        with pytest.raises(KeyError, match="not claimed"):
            page_db.pin(db, "n", T, str(tmp_path / (status + "-2")), stage="read")
    mine = _db(("n", _w("network", to="computer", status="running", claimed_by="mac-1",
                        claimed_at=AT, lease_until=AT)))
    got = page_db.pin(mine, "n", T, str(tmp_path / "mine"), stage="read", chat="mac-1")
    assert _body(got["batches"])["status"] == "running"


# ------------------------------------------------------------------ CC-3: a sign-in seen sends it back


def test_linkedin_seen_signed_in_sends_every_job_waiting_on_it_back_by_itself(tmp_path):
    db = _db(("network~read~1", _signin()), ("network~read~2", _w("network", to="computer")))
    batches = computer.beat(db, "Studio Laptop", T, str(tmp_path / "in"), browser="shown",
                            linkedin="in")
    assert len(batches) == 2, batches
    with open(batches[1], encoding="utf-8") as fh:
        entry = json.load(fh)[0]
    assert entry["doc_id"] == "network~read~1"
    with open(entry["file_path"], encoding="utf-8") as fh:
        body = json.load(fh)
    assert body["status"] == "queued" and body["needs"] is None and body["note"] is None
    # Signed out, or not looked at: the heartbeat alone.
    assert len(computer.beat(db, "Studio Laptop", T, str(tmp_path / "out"), browser="shown",
                             linkedin="out")) == 1


def test_a_read_of_someone_a_waiting_job_reads_is_refused_until_it_is_taken(tmp_path, monkeypatch):
    """The review of 2026-11-11 (CC-19): `resume` held only if the chat ran it first; a read made
    with reading.py on its own, of a person a job waiting on the page reads, still ran twice."""
    sys.path.insert(0, os.path.join(ROOT, "tools", "network"))
    import reading
    mirror = tmp_path / "mirror"
    (mirror / "work").mkdir(parents=True)
    queued = _w("network", "Harbourline Bank", to="computer",
                args={"company": "Harbourline Bank", "contacts": ["harbourline_bank_ash"]})
    name = "~".join(("network", "read", "4")).replace("~", "@") + ".json"
    with open(mirror / "work" / name, "w", encoding="utf-8") as fh:
        json.dump({"data": queued, "version": 2}, fh)
    monkeypatch.setenv("LJS_PAGE_MIRROR", str(mirror))
    said = reading.queued_read_refusal("harbourline_bank_ash")
    assert "network~read~4" in said and "app.py resume" in said, said
    assert reading.queued_read_refusal("someone_else") == ""
    # Taken into the chat, the read goes on.
    with open(mirror / "work" / name, "w", encoding="utf-8") as fh:
        json.dump({"data": dict(queued, status="running", claimed_by="mac-1", in_chat=True), "version": 3}, fh)
    assert reading.queued_read_refusal("harbourline_bank_ash") == ""


def _read_job(tmp_path, monkeypatch, mirror_item, dump_item, version=2):
    """A copy of the page kept here (the mirror) and a chat's own fresh read of it ($D), each
    holding the read-first job for one invented person."""
    sys.path.insert(0, os.path.join(ROOT, "tools", "network"))
    name = "~".join(("network", "read", "4")).replace("~", "@") + ".json"
    mirror, dump = tmp_path / "mirror", tmp_path / "D"
    for where, item, v in ((mirror, mirror_item, version), (dump, dump_item, version + 1)):
        (where / "work").mkdir(parents=True)
        with open(where / "work" / name, "w", encoding="utf-8") as fh:
            json.dump({"data": item, "version": v}, fh)
    monkeypatch.setenv("LJS_PAGE_MIRROR", str(mirror))
    return dump


def _app(*args, env=None):
    return subprocess.run([sys.executable, os.path.join(ROOT, "tools", "app.py"), *args],
                          capture_output=True, text=True, encoding="utf-8",
                          env=dict(os.environ, **(env or {})))


def test_a_read_refused_for_waiting_work_is_never_refused_for_good(tmp_path, monkeypatch):
    """The engine review of 2026-11-11: the refusal read only the copy of the page this checkout
    keeps, which only a planned read moved on. The chat that took the job with `resume`, the
    step the refusal names, was still refused its read; and a job finished since that copy was
    read refused every read of its person for good, `resume` saying "has finished"."""
    import reading
    wid = "~".join(("network", "read", "4"))
    queued = _w("network", "Harbourline Bank", to="computer", asked=AT,
                args={"company": "Harbourline Bank", "contacts": ["harbourline_bank_ash"],
                      "read_first": True})
    # Taken into this chat with resume: the read goes on.
    dump = _read_job(tmp_path / "taken", monkeypatch, queued, queued)
    assert reading.queued_read_refusal("harbourline_bank_ash")
    r = _app("resume", str(dump), "--work", wid, "--chat", "mac-1", "--kind", "computer",
             "--now", NOW, env={"LJS_PAGE_MIRROR": os.environ["LJS_PAGE_MIRROR"]})
    assert r.returncode == 0, r.stdout + r.stderr
    assert reading.queued_read_refusal("harbourline_bank_ash") == ""
    # Finished on the page since this copy was read: resume takes nothing, and the read goes on.
    done = dict(queued, status="done", finished_at=AT, claimed_by="mac-old")
    dump = _read_job(tmp_path / "over", monkeypatch, queued, done)
    said = reading.queued_read_refusal("harbourline_bank_ash")
    assert "has finished" in said, said
    r = _app("resume", str(dump), "--work", wid, "--chat", "mac-1", "--kind", "computer",
             "--now", NOW, env={"LJS_PAGE_MIRROR": os.environ["LJS_PAGE_MIRROR"]})
    assert r.returncode == 2 and "has finished" in r.stderr, r.stdout + r.stderr
    assert reading.queued_read_refusal("harbourline_bank_ash") == ""


def test_the_chat_that_claimed_the_job_is_never_refused_its_own_read(tmp_path, monkeypatch):
    import app_setup
    import reading
    wid = "~".join(("network", "read", "4"))
    queued = _w("network", "Harbourline Bank", to="computer", asked=AT,
                args={"company": "Harbourline Bank", "contacts": ["harbourline_bank_ash"]})
    _read_job(tmp_path, monkeypatch, queued, queued)
    assert reading.queued_read_refusal("harbourline_bank_ash")
    # Claimed on this computer (app.py next --computer-only keeps the id it took it under).
    monkeypatch.setattr(app_setup, "claimed_as", lambda w: "mac-1" if w == wid else "")
    assert reading.queued_read_refusal("harbourline_bank_ash") == ""


def test_a_claim_moves_the_kept_copy_on(tmp_path, monkeypatch):
    """`app.py next` claims the job in the chat's own read; the copy the refusal reads takes it."""
    import page_reads
    import reading
    wid = "~".join(("network", "read", "4"))
    queued = _w("network", "Harbourline Bank", to="computer", asked=AT,
                args={"company": "Harbourline Bank", "contacts": ["harbourline_bank_ash"]})
    dump = _read_job(tmp_path, monkeypatch, queued, queued)
    assert reading.queued_read_refusal("harbourline_bank_ash")
    r = _app("next", str(dump), "--chat", "mac-1", "--kind", "computer", "--now", NOW,
             "--claim-out", str(tmp_path / "out"),
             env={"LJS_PAGE_MIRROR": os.environ["LJS_PAGE_MIRROR"]})
    assert r.returncode == 0 and json.loads(r.stdout)["work"] == wid, r.stdout + r.stderr
    assert reading.queued_read_refusal("harbourline_bank_ash") == ""
    # A copy newer than the chat's read is never put back by an older one.
    with open(dump / "work" / (wid.replace("~", "@") + ".json"), "w", encoding="utf-8") as fh:
        json.dump({"data": queued, "version": 1}, fh)
    page_reads.keep_work(str(dump), [wid])
    assert reading.queued_read_refusal("harbourline_bank_ash") == ""


def test_a_pin_naming_no_chat_never_writes_over_a_live_claim(tmp_path):
    """The review of 2026-11-11 (PE-1): with no --chat, a pin still wrote to another chat's live
    claim."""
    live = _db(("n", _w("network", to="computer", status="running", claimed_by="mac-2",
                        claimed_at=AT, lease_until=app_model.stamp(T + dt.timedelta(minutes=20)))))
    with pytest.raises(KeyError, match="--chat"):
        page_db.pin(live, "n", T, str(tmp_path / "a"), stage="read")
    # Its own chat, known by its own id, still pins without naming it.
    assert page_db.pin(live, "n", T, str(tmp_path / "b"), stage="read", me="mac-2")["batches"]
