"""A draft Claude decided to hold is on hold everywhere, never offered as ready to send.

The maintainer, 2026-11-10: a person's card offered a draft as ready (its words, Copy, and
"I sent it" as the first pill) while the line under it said the opposite: "Finished: held: no
message to <them> until a fitting role appears." The hold lived only in the finished change's
summary on the page, so the engine went on offering the draft, To do counted it as one to send
and the brief knew nothing of it. Now `app.py done --outcome held` puts the hold on the
person's record (their next action, dated with --until), the engine holds a draft to anyone
whose record holds them, and a change Claude finished as held before that (its summary
"Held ...") holds the very version of the draft it was asked about. The card says it is on hold
and why, with one way to send it anyway. Invented people and employers only.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import pytest  # noqa: E402

import app_model  # noqa: E402
import test_a_ring_is_answered_in_one_command as R  # noqa: E402
import test_the_page_helper_stays_thin as T  # noqa: E402
import test_the_page_journeys as journeys  # noqa: E402
from test_the_page_journeys import _go, _sample  # noqa: E402

PELL = "kestrel_mutual_ansgar"            # the small search's one first note waiting to go
MID = "msg-" + PELL


def test_hold_words_say_why_and_when_plainly():
    day = dt.date(2026, 11, 23)
    assert app_model.hold_words("Held until Kestrel Mutual posts a fitting role; I check again "
                                "23 Nov.", day) == \
        "On hold until Kestrel Mutual posts a fitting role. Claude checks again on Mon 23 Nov."
    assert app_model.hold_words("held: no message to Pell until a fitting role appears.") == \
        "On hold: no message to Pell until a fitting role appears."
    assert app_model.hold_words("Hold until 2026-11-23", day) == \
        "On hold. Claude checks again on Mon 23 Nov."


@pytest.fixture
def ring(tmp_path, monkeypatch):
    yield from T.ring.__wrapped__(tmp_path, monkeypatch)


def _message(ring):
    m = json.loads(ring.run("model", "--now", R.NOW))
    return m, next(x for x in m["messages"] if x["id"] == MID)


def _tweak(ring, wid, rev, **data):
    ring.put("work", wid, dict({"kind": "tweak", "title": "Change the note to Pell", "to": "either",
                                "status": "running", "asked_at": "2026-10-25T17:30:00Z",
                                "args": {"v": 1, "text": "Is now the time to send this?",
                                         "changes": [], "target": {"id": MID, "output": "message",
                                                                   "contact": PELL, "rev": rev}}},
                               **data), 2)


def test_a_change_finished_as_held_puts_the_hold_on_their_record(ring):
    _m, msg = _message(ring)
    assert msg["hold"] is None and MID in _m["to_send"]["ids"]
    _tweak(ring, "tweak~msg-pell~1", msg["rev"])
    d = ring.dump()
    got = json.loads(ring.run("done", d, "--work", "tweak~msg-pell~1", "--summary",
                              "Held until Kestrel Mutual posts a fitting role; I check again 23 Nov.",
                              "--outcome", "held", "--until", "2026-11-23", "--now", R.NOW))
    assert got["status"] == "done" and got.get("held"), got
    from network import state
    # The whole suite's own state folder is put back after (tests/conftest.py sets it once):
    # popped, every test after this one lost it (the Mac run, 2026-11-10).
    was = os.environ.get("LJS_STATE")
    os.environ["LJS_STATE"] = ring.state
    try:
        row = next(c for c in state.load_contacts(os.path.join(ring.state, "network_contacts.csv"))
                   if c["contact_id"] == PELL)
    finally:
        if was is None:
            os.environ.pop("LJS_STATE", None)
        else:
            os.environ["LJS_STATE"] = was
    assert row["next_action"] == "Hold until Kestrel Mutual posts a fitting role, or until 2026-11-23", row
    assert row["next_action_due"] == "2026-11-23"
    # Every screen holds it: the draft, To do's count of messages to send.
    m, msg = _message(ring)
    assert msg["hold"] == ("On hold until Kestrel Mutual posts a fitting role. Claude checks "
                           "again on Mon 23 Nov."), msg["hold"]
    assert msg["hold_why"] == "person_hold" and MID not in m["to_send"]["ids"]


def test_a_change_held_before_the_record_holds_the_version_it_was_about(ring):
    _m, msg = _message(ring)
    _tweak(ring, "tweak~msg-pell~old", msg["rev"], status="done",
           finished_at="2026-10-25T17:40:00Z",
           result={"summary": "held: no message to Pell until a fitting role appears.", "links": []})
    d, _ = T.read(ring, "r0")
    T.wake(ring, d)
    got, ok = T.view(ring, d)
    assert ok, got
    with open(os.path.join(ring.db, "screen", "messages.json"), encoding="utf-8") as fh:
        shown = next(x for x in json.load(fh)["data"]["data"] if x["id"] == MID)
    assert shown["hold"] == "On hold: no message to Pell until a fitting role appears.", shown
    assert shown["hold_why"] == "decided"
    # A new version of the draft is not the one held.
    assert app_model.held_by_work({"w": {"data": {
        "kind": "tweak", "status": "done", "args": {"target": {"id": MID, "rev": "other"}},
        "result": {"summary": "Made it shorter."}}}}) == {}


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


LOOK = r"""(() => {
  const card = document.querySelector('[data-msg="msg-ash-1"]');
  const line = document.querySelector('[data-k="held:msg-ash-1"]');
  return {line: line ? line.textContent.replace(/\s+/g, ' ').trim() : null,
          copy: !!(card && card.querySelector('.bubble-copy')),
          sent: !!document.querySelector('[data-k="sent:msg-ash-1"]'),
          anyway: !!document.querySelector('[data-k="unhold:msg-ash-1"]'),
          finished: [...document.querySelectorAll('[data-tweak-done]')].map((e) => e.textContent).filter((t) => /held/i.test(t))};
})()"""


def test_the_card_says_it_is_on_hold_and_offers_one_way_to_send_it_anyway(run, tmp_path):
    m = _sample()
    for msg in m["messages"]:
        if msg["id"] == "msg-ash-1":
            msg["hold"] = "On hold until Copperleaf Pay posts a fitting role. Claude checks again on Mon 23 Nov."
            msg["hold_why"] = "decided"
    got = _go(run, tmp_path, [
        {"hash": "contacts", "eval": LOOK},
        {"eval": "(() => { document.querySelector('[data-k=\"unhold:msg-ash-1\"]').click(); return 1; })()"},
        {"tick": 300},
        {"eval": LOOK},
    ], journeys.WIDE, model=m)
    held, after = got["after"][0]["eval"], got["after"][3]["eval"]
    assert held["line"].startswith("On hold until Copperleaf Pay posts a fitting role"), held
    assert "Send it anyway" in held["line"] and held["anyway"], held
    assert not held["copy"] and not held["sent"] and not held["finished"], held
    # Sent anyway: Copy and I sent it are back, and the line has gone.
    assert after["copy"] and after["sent"] and after["line"] is None, after
