"""A resume asked for starts within a minute or two, whatever light work runs (issue #231).

A resume made for a contact was asked for just after four message changes. The chat that
answers the page took work oldest first, so it made each change itself, one after another, and
only then started the resume in a chat of its own: the resume's card sat at "Getting started"
for eight minutes. Now a big job is handed out before light work of the same urgency, wherever
it starts in a chat of its own (one create_session call, then the light work runs beside it),
and a big job asked for part way through a pass is started between its items, never after
the whole pass. A question still goes first, and an update before everything.

On the real path: the page's store is the folder that keeps the real one's rules
(tests/test_one_chat_answers_the_page.py), read as ArtifactData saves it, and woken with
`app.py wake` as a ring is. Every id and name is invented.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import pytest  # noqa: E402

import test_a_ring_is_answered_in_one_command as R  # noqa: E402
from test_a_ring_is_answered_in_one_command import CHAT, NOW, land, next_item  # noqa: E402

RESUME = "contact_resume~sam_example~r1"


@pytest.fixture
def ring(tmp_path):
    r = R.Ring(tmp_path)
    yield r
    sys.path.remove(r.root)


def _items(said: str) -> list[dict]:
    return [next_item(said)] + [json.JSONDecoder().raw_decode(said[m.end():])[0]
                                for m in re.finditer(r"\nalso: ", said)]


def _resume(ring, at="2026-10-25T17:01:00Z"):
    ring.put("work", RESUME, {"kind": "resume_for_contact", "status": "queued", "asked_at": at,
                              "to": "cloud", "title": "Resume for Sam (Example Insurance)",
                              "args": {"for_contact": "sam_example"}})


def _four_changes(ring, minute=0):
    for i in range(4):
        ring.queue(f"tweak~{i}", kind="tweak", asked_at=f"2026-10-25T17:0{minute}:{i:02d}Z")


def _waiting(look, *flags):
    return subprocess.run([sys.executable, os.path.join(ROOT, "tools", "app_listen.py"),
                           "waiting", look, *flags], capture_output=True, text=True,
                          encoding="utf-8").stdout.strip()


def test_a_resume_asked_after_four_changes_is_started_first_in_a_chat_of_its_own(ring):
    _four_changes(ring)
    _resume(ring)
    said = ring.wake(ring.read("wake1"))
    item = next_item(said)
    # Started first, with one call, never after the four changes are made here.
    assert item["work"] == RESUME and item["run"] == "child session", said
    assert "create_session" in item and "never wait for it" in said, said
    assert "More is waiting" in said, said
    assert all(land(ring, said))
    assert ring.stored("work", RESUME)["data"]["status"] == "claimed"
    # The changes are the next wake's, done here while the resume runs in its own chat.
    again = ring.wake(ring.read("wake2"))
    assert [it["work"] for it in _items(again)] == [f"tweak~{i}" for i in range(4)], again
    assert all(it["run"] == "here" for it in _items(again))


def test_a_question_still_goes_first_and_the_resume_straight_after(ring):
    _four_changes(ring)
    _resume(ring)
    ring.put("work", "talk~card", {"kind": "talk", "status": "queued",
                                   "asked_at": "2026-10-25T17:05:00Z", "title": "A question",
                                   "to": "cloud",
                                   "args": {"thread": "card-job-1", "message": "m-1",
                                            "about": {"kind": "job", "id": "job-1",
                                                      "label": "A job"}}})
    got = json.loads(ring.run("next", ring.read("dump1"), "--chat", CHAT, "--kind", "cloud",
                              "--now", NOW, "--claim-out", os.path.join(ring.root, "c1")))
    assert got["work"] == "talk~card", got
    assert all(land(ring, "\n".join(f"1. {p}   (the claim)" for p in got["batches"])))
    got = json.loads(ring.run("next", ring.read("dump2"), "--chat", CHAT, "--kind", "cloud",
                              "--now", NOW))
    assert got["work"] == RESUME and got["run"] == "child session", got


def test_a_resume_asked_part_way_through_a_pass_is_started_before_its_next_item(ring):
    _four_changes(ring)
    said = ring.wake(ring.read("wake1"))
    assert all(land(ring, said)), said
    assert [it["work"] for it in _items(said)] == [f"tweak~{i}" for i in range(4)], said
    # The look between items names a big job too, and its `next` is a command that runs.
    assert "waiting \"$E\" --question --jobs" in said and "--kind cloud" in said, said
    look = ring.read("between1")
    assert _waiting(look, "--question", "--jobs") == "waiting: no question"
    # The first change is done; the resume is asked for before the second starts.
    _resume(ring, at="2026-10-25T17:20:00Z")
    look = ring.read("between2")
    assert _waiting(look, "--question") == "waiting: no question"
    assert _waiting(look, "--question", "--jobs") == f"waiting: a big job to start, {RESUME}"
    got = json.loads(ring.run("next", look, "--chat", CHAT, "--kind", "cloud", "--now", NOW,
                              "--claim-out", os.path.join(look, "claim")))
    assert got["work"] == RESUME and got["run"] == "child session" and got["batches"], got
    assert all(land(ring, "\n".join(f"1. {p}   (the claim)" for p in got["batches"])))
    assert ring.stored("work", RESUME)["data"]["status"] == "claimed"
    # The pass's own changes are still this chat's.
    assert ring.stored("work", "tweak~1")["data"]["status"] == "running"


def test_a_chat_that_cannot_start_chats_starts_it_as_a_background_agent_first(ring):
    _four_changes(ring)
    _resume(ring)
    said = ring.wake(ring.read("wake1"), "--no-sessions")
    item = next_item(said)
    assert item["work"] == RESUME and item["run"] == "background agent", said
