"""A follow-up still to be rewritten is never on the page as ready to send.

From a person's copy, 2026-11-11: the first run of `app.py follow-ups` there listed 27 of
code's own follow-up drafts as needing a rewrite, "to write here", and in the same run put
every one of them on its person's card, where the page says "Ready to send". The person has
rules of their own for messages, which code's short plain follow-up cannot fit, so each came
out flagged for Claude to rewrite (followup_drafts.RULES_TO_FIT); the run kept it on the card
all the same. Once there, the next run read it back as the draft waiting for them, with no
flag, and finished it as "Your follow-up to ... is ready to send" without anyone rewriting it.

Now a flagged draft stays off the card until it is rewritten and its checks pass: the run
lists it to write, the card holds nothing to send, and only what comes back through
`--written` and passes is kept and finished. Every person, employer and chat id is invented.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import pytest  # noqa: E402

import app_state  # noqa: E402
from test_a_ring_is_answered_in_one_command import NOW, Ring, land  # noqa: E402
from test_follow_ups_queued_together_are_one_job import batches, follow_ups  # noqa: E402

N = 4
# A rule of the person's own for messages, which code's plain follow-up cannot fit.
RULE = {"date": "2026-10-20", "area": "messages", "status": "active",
        "said": "always thank them and say I'm looking for analytics roles in Manchester",
        "rule": "thank them, and say the roles I want and where I am"}


@pytest.fixture
def ring(tmp_path):
    r = Ring(tmp_path)
    r.ids = app_state.nudges_due(r.state, N)
    for n, cid in enumerate(r.ids):
        r.put("work", "follow_up~" + cid, {
            "kind": "follow_up", "status": "queued", "to": "either",
            "asked_at": f"2026-10-25T17:{n:02d}:00Z", "title": "Follow up with someone",
            "args": {"contact": cid}})
    with open(os.path.join(r.profile, "learned.json"), "w", encoding="utf-8") as fh:
        json.dump({"entries": [RULE]}, fh)
    yield r
    sys.path.remove(r.root)


def _card(ring, cid) -> str:
    return os.path.join(ring.state, "documents", "network", cid, "draft.md")


def _apply(ring, said):
    import fake_db
    assert all(fake_db.apply(ring.db, b) for b in batches(said)), said


def _ready_on_the_page(ring) -> list:
    model = json.loads(ring.run("model", "--now", NOW))
    return [m["contact"] for m in model["messages"]
            if m.get("contact") in ring.ids and not m.get("hold") and not m.get("blocked")]


def test_a_draft_listed_to_rewrite_is_not_on_its_card_as_ready_to_send(ring):
    d = ring.read("wake1")
    assert all(land(ring, ring.wake(d)))
    got = follow_ups(ring, d)
    # Every one is listed for this chat to rewrite, and none finished.
    assert got.startswith("follow-ups: 0 finished") and f"{N} to write here" in got, got
    for cid in ring.ids:
        assert f"to write: {cid}" in got, got
    _apply(ring, got)
    # So none of them is on a card, and the page offers nothing of theirs to send.
    for cid in ring.ids:
        assert not os.path.isfile(_card(ring, cid)), cid
        doc = ring.stored("work", "follow_up~" + cid)["data"]
        assert doc["status"] == "running", (cid, doc)
    assert _ready_on_the_page(ring) == []
    # Run again without the rewrites: still to write, never finished as ready to send.
    again = follow_ups(ring, d)
    assert again.startswith("follow-ups: 0 finished") and f"{N} to write here" in again, again
    _apply(ring, again)
    for cid in ring.ids:
        doc = ring.stored("work", "follow_up~" + cid)["data"]
        assert doc["status"] == "running", (cid, doc)
        assert "ready to send" not in json.dumps(doc.get("result") or {}), doc


def test_only_the_rewrite_that_passes_is_kept_and_finished(ring):
    d = ring.read("wake1")
    assert all(land(ring, ring.wake(d)))
    _apply(ring, follow_ups(ring, d))
    good, bad = ring.ids[0], ring.ids[1]
    text = ("Hi there, thanks again for connecting. Following up on my note from September: "
            "I'm looking for analytics roles in Manchester. How is the analytics team set up "
            "these days?")
    written = [{"id": good, "text": text}, {"id": bad, "text": "x" * 900}]
    got = follow_ups(ring, d, "--written", "-", stdin=json.dumps(written))
    assert got.startswith("follow-ups: 1 finished"), got
    assert f"refused, write it again: {bad}" in got, got
    _apply(ring, got)
    assert ring.stored("work", "follow_up~" + good)["data"]["status"] == "done"
    with open(_card(ring, good), encoding="utf-8") as fh:
        assert "analytics roles in Manchester" in fh.read()
    # The refused one is still to write: nothing of code's is on its card in its place.
    assert ring.stored("work", "follow_up~" + bad)["data"]["status"] == "running"
    assert not os.path.isfile(_card(ring, bad))
    assert _ready_on_the_page(ring) == [good]
