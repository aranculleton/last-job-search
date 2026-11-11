"""Every change of a work item's status sets and clears the same fields, whoever makes it.

Found by the audit of 2026-11-10 (PE-11, PE-5, CC-3): an answer on the page put the work back
in the queue with its question still on it (`needs`, `asked_you_at`); a claim kept them; a
sign-in seen on the computer cleared a list of its own; and a late tap on a card drawn before
its work finished put the finished job back in the queue. Now each change is one function in
tools/page_db.py (answered, taken, asked, ended), the computer's sign-in and the page's own
answer write what `answered` writes, and the page writes over the record as the store holds
it. Every person, employer and computer here is invented.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "network"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import app_model  # noqa: E402
import computer  # noqa: E402
import page_db  # noqa: E402
import test_the_page_journeys as journeys  # noqa: E402
from test_a_question_is_answered_on_its_card import ASK, T as PAGE_T, _asking, _no_questions  # noqa: E402
from test_a_tick_on_the_page_is_applied_once import NOW, _db, _w  # noqa: E402
from test_the_page_journeys import PHONE, WIDE, _go  # noqa: E402

T = app_model.parse_time(NOW)
AT = app_model.stamp(T)
QUESTION = "LinkedIn is signed out in Claude's browser."


def _waiting(**kw):
    item = _w("network", "Harbourline Bank", to="computer", status="needs_you")
    item.update(note=QUESTION, needs={"question": QUESTION, "signin": "linkedin"},
                asked_you_at=app_model.stamp(T - dt.timedelta(minutes=4)), choices=None, **kw)
    return item


def _written(batches) -> list[dict]:
    out = []
    for b in batches:
        with open(b, encoding="utf-8") as fh:
            for e in json.load(fh):
                body = {}
                if e.get("file_path"):
                    with open(e["file_path"], encoding="utf-8") as fh2:
                        body = {k: v for k, v in json.load(fh2).items() if k != page_db.VERSION_FIELD}
                out.append(dict(e, body=body))
    return out


def _after(item: dict, fields: dict) -> dict:
    """The item as the store holds it once `fields` are written (None and a delete clear)."""
    out = dict(item)
    for k, v in fields.items():
        if v is None or (isinstance(v, dict) and v.get("__delete__")):
            out.pop(k, None)
        else:
            out[k] = v
    return out


# ------------------------------------------------------------------ the engine's changes


def test_an_answer_clears_the_question_and_keeps_when_it_was_asked():
    item = _waiting(claimed_by="mac-1")
    got = _after(item, page_db.answered(item, "Signed in", AT))
    assert got["status"] == "queued" and got["answered_at"] == AT
    for k in page_db.ASKED + page_db.HELD:
        assert not got.get(k), (k, got)
    assert got["args"]["answers"] == {QUESTION: "Signed in"}
    assert got["last_asked_at"] == item["asked_you_at"]


def test_a_claim_leaves_nothing_of_the_question_its_answer_replied_to(tmp_path):
    # As the page left an answered item before this release: its question still on it.
    item = dict(_waiting(), status="queued", answered_at=AT, last_asked_at=AT)
    db = _db(("n1", item))
    chosen = page_db.next_item(db, "computer", T)
    batches = page_db.claim(db, chosen, "mac-1", "computer", T, str(tmp_path), beat=False)
    body = next(e["body"] for e in _written(batches) if e["collection"] == "work")
    got = _after(item, body)
    assert got["status"] == "claimed" and got["claimed_by"] == "mac-1"
    for k in ("note", "needs", "asked_you_at", "choices", "last_asked_at"):
        assert not got.get(k), (k, got)


def test_a_question_and_its_end_are_written_one_way(tmp_path):
    item = _w("network", "Harbourline Bank", to="computer", status="running", claimed_by="mac-1",
              claimed_at=AT, lease_until=AT)
    db = _db(("n1", item))
    got = page_db.finish(db, "n1", T, str(tmp_path / "a"), question=QUESTION, chat="mac-1",
                         chat_kind="computer", signin="linkedin")
    body = next(e["body"] for e in _written(got["batches"]) if e["collection"] == "work")
    # The one transition writes the question; a sign-in stop is also counted on it, so the
    # third in a row is asked plainly (audit CC-11, the computer area's change).
    assert {k: v for k, v in body.items() if k != "signin_stops"} == \
        page_db.asked(QUESTION, body["needs"], None, AT)
    assert body["signin_stops"] == 1
    # Finished another way, the question it carried goes with it: no Answer box under Stopped.
    asked_item = _after(item, body)
    db = _db(("n1", asked_item))
    got = page_db.finish(db, "n1", T, str(tmp_path / "b"), status="stopped", chat="mac-1",
                         chat_kind="computer", summary="Called off: read earlier today.")
    body = next(e["body"] for e in _written(got["batches"]) if e["collection"] == "work")
    assert {k for k in page_db.ASKED if asked_item.get(k)} <= {k for k, v in body.items() if v is None}
    assert body["status"] == "stopped"


def test_the_sign_in_seen_on_the_computer_is_the_same_answer(tmp_path):
    item = _waiting(computer_session={"id": "session_mac1", "at": AT})
    db = _db(("n1", item))
    batches = computer.signed_in(db, "n1", T, str(tmp_path))
    body = next(e["body"] for e in _written(batches) if e["collection"] == "work")
    assert "needs" in body and body["needs"] is None and body["asked_you_at"] is None, body
    want = page_db.answered(item, computer.SIGNED_IN_SAID, AT)
    assert {k: v for k, v in body.items() if k != "computer_session"} == want
    # Still that chat's while it carries on: no second chat is started for it.
    assert computer.waiting(_db(("n1", _after(item, body))), T)["started"] == {"n1": "session_mac1"}


# ------------------------------------------------------------------ the page's own answer


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


@pytest.fixture(params=[PHONE, WIDE], ids=["phone", "wide"])
def vp(request):
    return request.param


def test_the_pages_answer_writes_what_the_engine_writes(run, tmp_path, vp):
    seed = _asking({"key": "answer", "kind": "yesno"}, question="Did the call go ahead?")
    before = dict(seed["work/follow_up~wren"])
    got = _go(run, tmp_path, [{"hash": "todo", "click": "Yes", "exact": True, "within": ASK}],
              vp, seed=seed, model=_no_questions(), clock=PAGE_T)
    w = [x for x in got["work"] if x.get("title") == "Follow up with Wren"][-1]
    assert w["status"] == "queued" and not w.get("needs") and not w.get("asked_you_at"), w
    want = page_db.answered(before, "yes", w.get("answered_at"))
    for k, v in want.items():
        assert w.get(k) == v, (k, w.get(k), v)


def test_a_late_tap_on_a_card_drawn_before_its_work_finished_changes_nothing(run, tmp_path):
    seed = _asking({"key": "answer", "kind": "yesno"}, question="Did the call go ahead?")
    done = dict(seed["work/follow_up~wren"], status="done", note=None, needs=None,
                finished_at="2026-10-25T08:58:00.000Z", result={"summary": "Sent.", "links": []})
    hold = ("(window.__held = [...document.querySelectorAll('" + ASK.replace("'", "\\'") +
            " .ask-choices button')], window.__held.length)")
    got = _go(run, tmp_path, [
        {"hash": "todo", "eval": hold},
        {"write": {"work/follow_up~wren": done}, "eval": "(window.__held[0].click(), true)"},
        {"wait": 300, "eval": "[...document.querySelectorAll('#toasts')].map((t) => t.textContent).join(' ')"},
    ], WIDE, seed=seed, model=_no_questions(), clock=PAGE_T)
    assert got["after"][0]["eval"] >= 1, got["after"][0]
    w = [x for x in got["work"] if x.get("title") == "Follow up with Wren"][-1]
    assert w["status"] == "done" and not (w.get("args") or {}).get("answers"), w
    assert "already finished" in got["after"][2]["eval"], got["after"][2]["eval"]


def test_a_double_tap_on_an_answer_writes_it_once(run, tmp_path):
    """The review of 2026-11-11: two taps on a chip wrote the answer twice, and the store's
    number ran past the record's own stamp, so every chat's next write to it was refused once."""
    seed = _asking({"key": "answer", "kind": "yesno"}, question="Did the call go ahead?")
    tap = ("(() => { const b = [...document.querySelectorAll('" + ASK.replace("'", "\\'") + " button')]"
           ".find((x) => x.textContent === 'Yes'); b.click(); b.click(); return true; })()")
    got = _go(run, tmp_path, [{"hash": "todo", "eval": tap}, {"wait": 300, "writes": True}], WIDE,
              seed=seed, model=_no_questions(), clock=PAGE_T)
    assert got["after"][1]["writes"].get("work/follow_up~wren") == 1, got["after"][1]["writes"]


FAILED_ITEM = {"kind": "draft", "title": "Draft: Kestrel Mutual", "to": "cloud", "args": {},
               "asked_at": "2026-10-25T08:00:00.000Z", "status": "failed", "attempt": 1,
               "error": "The letter could not be read back.", "finished_at": "2026-10-25T08:58:00.000Z",
               "claimed_by": "session_gone1", "run_by": "session_EXAMPLEchild9", "claimed_as": "cloud", "_v": 5}


def _work_card(id_):
    return '[data-work="' + id_ + '"]'


def test_the_pages_try_again_and_stop_write_what_the_engine_writes(run, tmp_path):
    """The review of 2026-11-11 (item 2): the page's Try again and Stop wrote field lists of
    their own; now each is the engine's (page_db.retried, stop_tapped), field for field."""
    seed = {"work/draft~kestrel": FAILED_ITEM,
            "work/draft~oakmere": dict(FAILED_ITEM, title="Draft: Oakmere Foods", status="queued",
                                       error=None, finished_at=None, claimed_by=None, run_by=None,
                                       claimed_as=None, asked_at="2026-10-25T08:58:00.000Z", _v=1)}
    tap = ("(() => { const c = document.querySelector('[data-work=\"%s\"]');"
           " const b = c && [...c.querySelectorAll('button')].find((x) => x.textContent.trim() === '%s');"
           " if (b) b.click(); return !!b; })()")
    got = _go(run, tmp_path, [
        {"hash": "jobs", "wait": 200, "eval": tap % ("draft~kestrel", "Try again")},
        {"wait": 300, "eval": tap % ("draft~oakmere", "Stop Claude")},
        {"wait": 300},
    ], WIDE, seed=seed, clock=PAGE_T)
    assert got["after"][0]["eval"] and got["after"][1]["eval"], got["after"][:2]
    work = {w["id"]: w for w in got["after"][-1]["work"]}
    again = work["draft~kestrel"]
    want = page_db.retried(FAILED_ITEM, again["asked_at"], again["asked_from"]["tab"])
    for k, v in want.items():
        assert again.get(k) == v, (k, again.get(k), v)
    stopped = work["draft~oakmere"]
    want = page_db.stop_tapped(seed["work/draft~oakmere"], stopped["finished_at"])
    for k, v in want.items():
        assert stopped.get(k) == v, (k, stopped.get(k), v)


def test_every_engine_end_and_claim_is_one_of_the_transitions(tmp_path):
    """The review of 2026-11-11 (item 2): the stranded end, the lost result, the draft a search
    claims and the follow-up taken back each wrote a field list of their own."""
    import app_listen
    running = _w("draft", "Harbourline Bank", status="running", attempt=2, claimed_by="c-gone",
                 claimed_at="2026-10-25T08:00:00Z", lease_until="2026-10-25T08:30:00Z",
                 note="old question", needs={"question": "old question"})
    got = page_db.fail_stranded(_db(("d1", running)), T, str(tmp_path / "s"))
    body = _written(got["batches"])[0]["body"]
    assert {k: body[k] for k in page_db.ended(running, "failed", AT)} == page_db.ended(running, "failed", AT)
    done = _w("search", status="done", finished_at="2026-10-25T09:00:00Z")
    lost = _written(page_db.lose(_db(("s1", done)), ["s1"], T, str(tmp_path / "l")))[0]["body"]
    assert lost["status"] == "failed" and lost["finished_at"] == "2026-10-25T09:00:00Z"
    closed = app_listen.close_republish(_db(("r1", _w("republish", status="claimed"))), str(tmp_path / "r"), T)
    rbody = _written(closed["batches"])[0]["body"]
    assert {k: rbody[k] for k in page_db.ended({}, "done", AT)} == page_db.ended({}, "done", AT)
