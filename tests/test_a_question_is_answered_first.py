"""A question the person asks Claude goes before every message change, redraft or draft.

The page's Chat and the work it asks for were answered by the same chat, oldest first: a
question asked behind three message changes waited while each was done, the page saying
"Putting the change on your page first. The answer follows in a moment." while each change
showed "Getting started" (issue #226). Now the engine hands a question out before anything
else as urgent, a wake's pass answers it first and puts it on the page before the next item,
and between the other items a question asked meanwhile is looked for and answered first.
This is how a question is answered where no chat of its own can be started for it (no
create_session here: `--no-sessions`), the fallback of tests/test_the_chat_has_a_chat_of_its_own.py.

On the real path: the page's store is the folder that keeps the real one's rules
(tests/test_one_chat_answers_the_page.py), read as ArtifactData saves it, and woken with
`app.py wake` as a ring is. Every id is invented.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import app  # noqa: E402
import pytest  # noqa: E402

import test_a_ring_is_answered_in_one_command as R  # noqa: E402
from test_a_ring_is_answered_in_one_command import CHAT, NOW, land, next_item  # noqa: E402


@pytest.fixture
def ring(tmp_path):
    r = R.Ring(tmp_path)
    yield r
    sys.path.remove(r.root)


def _items(said: str) -> list[dict]:
    return [next_item(said)] + [json.JSONDecoder().raw_decode(said[m.end():])[0]
                                for m in re.finditer(r"\nalso: ", said)]


def _three_changes_then_a_question(ring) -> None:
    for i in range(3):
        ring.queue(f"tweak~{i}", kind="tweak", asked_at=f"2026-10-25T17:0{i}:00Z")
    ring.queue("talk~asked", kind="talk", asked_at="2026-10-25T17:05:00Z")


def test_a_question_queued_behind_three_changes_is_handed_out_first(ring):
    _three_changes_then_a_question(ring)
    said = ring.wake(ring.read("wake1"), "--no-sessions")
    assert all(land(ring, said)), said
    took = [it["work"] for it in _items(said)]
    assert took == ["talk~asked", "tweak~0", "tweak~1", "tweak~2"], said
    # Answered first, and on the page before the next item starts: the line that held it
    # behind the last item's view never promises an order the chat does not keep.
    assert "first: the item under next: is the person's question" in said, said
    assert "without --end" in said
    # Two or more other items follow it: a question asked meanwhile is looked for between them.
    assert "between items:" in said and "waiting \"$E\" --question" in said, said


def test_next_alone_hands_out_the_question_first_but_an_update_still_goes_before_it(ring):
    _three_changes_then_a_question(ring)
    got = json.loads(ring.run("next", ring.read("dump1"), "--chat", CHAT, "--kind", "cloud",
                              "--now", NOW, "--no-sessions"))
    assert got["work"] == "talk~asked", got
    # An update changes the code the answer runs on: it keeps its place ahead (priority 1).
    ring.put("work", "update~abc", {"kind": "update", "status": "queued", "priority": 1,
                                    "asked_at": "2026-10-25T17:09:00Z", "title": "Updating the app",
                                    "to": "either"})
    got = json.loads(ring.run("next", ring.read("dump2"), "--chat", CHAT, "--kind", "cloud",
                              "--now", NOW, "--no-sessions"))
    assert got["work"] == "update~abc", got


def test_a_question_asked_part_way_through_a_pass_is_answered_before_its_next_item(ring):
    for i in range(3):
        ring.queue(f"tweak~{i}", kind="tweak", asked_at=f"2026-10-25T17:0{i}:00Z")
    said = ring.wake(ring.read("wake1"), "--no-sessions")
    assert all(land(ring, said)), said
    assert [it["work"] for it in _items(said)] == ["tweak~0", "tweak~1", "tweak~2"]
    assert "between items:" in said and "first: " not in said, said
    # The first change is done; a question comes in before the second starts.
    look = ring.read("between1")
    quiet = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "app_listen.py"),
                            "waiting", look, "--question"], capture_output=True, text=True)
    assert quiet.stdout.strip() == "waiting: no question", quiet
    ring.queue("talk~meanwhile", kind="talk", asked_at="2026-10-25T17:20:00Z")
    look = ring.read("between2")
    asked = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "app_listen.py"),
                            "waiting", look, "--question"], capture_output=True, text=True)
    assert asked.stdout.strip() == "waiting: a question, talk~meanwhile", asked
    # The step the line names hands it out, claimed for this chat, the changes still its own.
    got = json.loads(ring.run("next", look, "--chat", CHAT, "--kind", "cloud", "--now", NOW,
                              "--no-sessions", "--claim-out", os.path.join(look, "claim")))
    assert got["work"] == "talk~meanwhile" and got["batches"], got
    assert all(land(ring, "\n".join(f"1. {p}   (the claim)" for p in got["batches"])))
    assert ring.stored("work", "talk~meanwhile")["data"]["claimed_by"] == CHAT
    assert ring.stored("work", "tweak~1")["data"]["status"] == "running"


def test_a_pass_of_questions_alone_or_one_change_says_nothing_more(ring):
    ring.queue("talk~1", kind="talk", asked_at="2026-10-25T17:00:00Z")
    ring.queue("tweak~1", kind="tweak", asked_at="2026-10-25T17:01:00Z")
    said = ring.wake(ring.read("wake1"), "--no-sessions")
    assert [it["work"] for it in _items(said)] == ["talk~1", "tweak~1"]
    # One change after the question: shown first, and no look between (no item follows it).
    assert "first: the item under next:" in said and "between items:" not in said, said
    assert app.asked_first_lines([{"kind": "talk"}, {"kind": "talk"}], "D", CHAT, "u") == []
