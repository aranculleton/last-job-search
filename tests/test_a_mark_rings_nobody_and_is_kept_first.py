"""A mark on the page (applied, not applying, I sent it, set aside, put off) rings nobody, and
the next chat that works on the search keeps it first.

From a real copy, 2026-11-05: "applied" or "not applying" took two to four minutes. The page
shows a mark at once, but the tap waited, unreceipted, until the page rang Claude for it on
the person's next tap, and a whole helper then read the page to keep one line; ten minutes on,
the page said Claude was not listening and offered to start a fresh helper, which took the
page from the one that was there. Now a mark is the engine's to keep: it never rings, never
counts as the page waiting on an answer, and is kept by whichever chat next draws the page (a
wake, `app.py view` at the end of any work, the brief) before the page is drawn. A tap that
needs Claude still rings. Every person, employer, page and chat id is invented.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import pytest  # noqa: E402

import app_actions  # noqa: E402
import app_listen  # noqa: E402
import test_a_ring_is_answered_in_one_command as R  # noqa: E402
import test_the_page_helper_stays_thin as thin  # noqa: E402

LATER = "2026-10-25T18:01:00Z"


@pytest.fixture
def ring(tmp_path, monkeypatch):
    monkeypatch.setenv("LJS_PAGE_MIRROR", str(tmp_path / "mirror"))
    r = R.Ring(tmp_path)
    r.mirror = str(tmp_path / "mirror")
    yield r
    sys.path.remove(r.root)


def T(hhmm: str) -> dt.datetime:
    return dt.datetime.fromisoformat(f"2026-10-25T{hhmm}:00+00:00")


def test_the_marks_are_the_taps_that_need_no_judgement():
    for name in ("ready.applied", "ready.not_applying", "job.applied", "msg.sent",
                 "job.dismiss", "job.bring_back", "due.snooze", "due.done", "msg.skip"):
        assert name in app_actions.MARKS, name
    # What needs Claude still rings: setup, a booked interview, a download to read, a tap that
    # queues work or leaves a chat's own call, and an undo, which may be anything.
    for name in ("setup.answer", "outcome.interview", "export.take", "job.add", "job.draft",
                 "msg.received", "needs.answer", "reading.done", "brief.move", "undo",
                 "consent.yes", "work.stop", "app.update_now", "setting.set"):
        assert name not in app_actions.MARKS, name
    # The page reads the same list, from the model.
    assert app_listen.model_part("example-owner/example-copy")["marks"] == sorted(app_actions.MARKS)


def test_a_mark_waiting_never_makes_the_chat_that_answers_look_gone():
    """The page's helper answered at 09:00; a mark made at 09:05 and left for an hour is no
    sign it has gone, so no other chat takes the page and no fresh helper starts. A tap that
    needs Claude, left as long, still is."""
    rec = {"chat": "session_EXAMPLELIVE", "helper": True, "kind": "cloud",
           "since": "2026-10-25T08:00:00Z", "answered_at": "2026-10-25T09:00:00Z"}
    mark = {"action": "ready.applied", "item": "app-x", "at": "2026-10-25T09:05:00Z"}
    db = {"meta": {"listener": {"data": rec, "version": 3}}, "work": {},
          "actions": {"a1": {"data": mark, "version": 1}}}
    assert app_listen.waiting_since(db, T("10:05")) is None
    assert not app_listen.lapsed(rec, db, T("10:05"))
    got = app_listen.decide(db, "session_EXAMPLEOTHER", "/nonexistent/out", T("10:05"))
    assert got["role"] == "other", got["lines"]
    needs = dict(db, actions={"a1": {"data": dict(mark, action="setup.answer"), "version": 1}})
    assert app_listen.lapsed(rec, needs, T("10:05"))


def test_a_mark_is_kept_first_by_the_next_chat_that_draws_the_page(ring):
    """No ring and no read of its own: the view a chat runs at the end of any work keeps the
    marks waiting before it draws the page, so the page it draws already shows them done."""
    import fake_db
    first, _ = thin.read(ring, "r1")
    thin.wake(ring, first)
    assert thin.view(ring, first)[1]
    before = ring.tracker()
    aid = ring.act("ready.applied", R.KESTREL)
    d, _ = thin.read(ring, "r2", now=LATER)
    # A chat at work on something else ends with the view it always runs: the mark first.
    run = lambda: json.loads(ring.run(  # noqa: E731
        "view", os.path.join(d, "v"), "--dump", d, "--chat", R.CHAT, "--now", LATER,
        LJS_PAGE_MIRROR=ring.mirror, ok=(0, 2)))
    got = run()
    said = " ".join(got.get("for_claude") or [])
    assert "1 mark the person made on the page" in said and "ArtifactData query" not in said, got
    assert all(fake_db.apply(ring.db, b) for b in got["batches"])
    assert ring.stored("actions", aid)["data"]["claimed_by"] == R.CHAT
    assert ring.tracker() == before, "never kept before its claim is accepted"
    got = run()
    assert any(ln.startswith("marks kept first: 1 applied") for ln in got["for_claude"]), got
    assert all(fake_db.apply(ring.db, b) for b in got["batches"])
    assert ring.stored("receipts", aid)["data"]["result"] == "ok"
    assert ring.tracker() != before
    # Nothing is left waiting for anyone, and the next view has nothing to keep.
    assert app_actions.pending(_db(ring), R.CHAT, T("18:02")) == []
    got = run()
    assert not any("mark" in ln for ln in got.get("for_claude") or []), got


def _db(ring):
    import page_db
    return page_db.load(ring.read("check"))


def test_the_next_wake_keeps_marks_before_it_takes_its_work(ring):
    """A wake for work that needs Claude keeps the marks waiting first, in the same pass,
    before it chooses the work."""
    aid = ring.act("job.applied", "r9-3")
    ring.queue("talk~1", kind="talk")
    d = ring.read("wake1")
    said = ring.wake(d)
    assert R.parts(said) == [[R.CHECK_IN, R.TAPS]] and "next:" not in said, said
    assert all(R.land(ring, said))
    said = ring.wake(d)
    assert R.parts(said) == [[R.APPLIED], [R.WORK]], said
    assert all(R.land(ring, said))
    assert ring.stored("receipts", aid)["data"]["result"] == "ok"
    assert R.next_item(said)["work"] == "talk~1"


# ------------------------------------------------------------------ the page


@pytest.fixture(scope="module")
def run():
    import test_the_page_journeys as journeys
    yield from journeys.browser()


ROW = "app-ellerwick-insight"


def test_a_mark_rings_nobody_and_the_page_never_says_claude_is_not_listening(run, tmp_path):
    """A mark made twenty minutes ago and not kept yet, with the helper's last answer before
    it: the page says nothing about Claude not listening, offers no fresh chat, and the
    person's next tap rings nobody. A tap that needs Claude, left as long, still does."""
    from test_the_page_journeys import WIDE, _go, _sample
    model = _sample()
    model["listener"] = dict(model["listener"], marks=app_listen.model_part("x/y")["marks"])
    heard = {"meta/listener": {"chat": "cloud-1", "kind": "cloud", "since": "2026-10-24T08:00:00.000Z",
                               "answered_at": "2026-10-25T08:30:00.000Z"}}
    mark = {"actions/act~" + ROW + "~ready.applied": {
        "action": "ready.applied", "item": ROW, "value": {"on": "2026-10-25"},
        "at": "2026-10-25T08:40:00.000Z", "rev_seen": "a1", "tab": "t-old"}}
    # To do read, then a tap elsewhere on the page: the person's next tap is when the page
    # sends what waits.
    steps = [{"hash": "todo"}, {"hash": "jobs", "open": "jobsw:applied"}]
    got = _go(run, tmp_path, steps, WIDE, model=model, seed=dict(heard, **mark),
              clock="2026-10-25T09:00:00.000Z")
    assert "isn't listening" not in got["after"][0]["text"], got["after"][0]["text"][:400]
    assert got["rings"] == [], got["rings"]
    # The same wait for a booked interview, which needs Claude: the page says so and rings.
    booked = {"actions/act~int-x~outcome.interview": {
        "action": "outcome.interview", "item": ROW, "value": None,
        "at": "2026-10-25T08:40:00.000Z", "rev_seen": "a1", "tab": "t-old"}}
    got = _go(run, tmp_path, steps, WIDE, model=model, seed=dict(heard, **booked),
              clock="2026-10-25T09:00:00.000Z")
    assert "isn't listening" in got["after"][0]["text"]
    assert got["rings"] and "act" in got["rings"][0], got["rings"]
