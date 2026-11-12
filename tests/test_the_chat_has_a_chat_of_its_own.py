"""A question typed in the page's Chat gets a chat of its own, so it never waits on other work.

The page's Chat was answered by the same chat that works through the page's other work: a
question asked behind three message changes waited for them (issue #226). The maintainer:
"like as if u did a job search or people search etc with the same limits and cleanups to make
it logical so it disappears afterwards". So a Chat question is started in a chat of its own
the way a big job is (create_session from the chat that answers the page), one such chat
answers every Chat question while it is at work, it takes a place against the same limit as
the big jobs' chats, and it is put away as theirs are once its work has ended. Where no chat
can be started (no create_session, or the limit reached), the question is answered first,
where it is (tests/test_a_question_is_answered_first.py).

On the real path: the store is the folder that keeps the real one's rules, read as
ArtifactData saves it, woken with `app.py wake` as a ring is. Every id is invented.
"""
from __future__ import annotations

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import app  # noqa: E402
import page_db  # noqa: E402
import tidy  # noqa: E402
import pytest  # noqa: E402

import test_a_ring_is_answered_in_one_command as R  # noqa: E402
from test_a_ring_is_answered_in_one_command import CHAT, NOW, land, next_item  # noqa: E402


@pytest.fixture
def ring(tmp_path):
    r = R.Ring(tmp_path)
    yield r
    sys.path.remove(r.root)

QUESTION_CHAT = "session_EXAMPLEQUESTIONS"


def _ask(ring, wid, at="2026-10-25T17:05:00Z", about=None):
    args = {"thread": "cloud-1", "message": "m-" + wid, "text": "When is my next interview?"}
    if about:
        args["about"] = about
    ring.put("work", wid, {"kind": "talk", "status": "queued", "asked_at": at, "to": "cloud",
                           "title": "Answer: “When is my next interview?”", "args": args})


def _items(said: str) -> list[dict]:
    return [next_item(said)] + [json.JSONDecoder().raw_decode(said[m.end():])[0]
                                for m in re.finditer(r"\nalso: ", said)]


def test_a_chat_question_starts_the_chats_own_chat_and_the_changes_stay_here(ring):
    for i in range(3):
        ring.queue(f"tweak~{i}", kind="tweak", asked_at=f"2026-10-25T17:0{i}:00Z")
    _ask(ring, "talk~q1")
    said = ring.wake(ring.read("wake1"))
    item = next_item(said)
    # Handed out first, to a chat of its own, started as a big job's is.
    assert item["work"] == "talk~q1" and item["run"] == "child session", said
    call = item["create_session"]
    assert call["title"] == page_db.QUESTION_CHAT_TITLE
    assert "--kind talk" in call["prompt"] and "More is waiting" in said
    # A refused or failed start is said with the call: let go at once, answered here.
    assert "never make it again for this question: python3 tools/app.py let-go" in said, said
    assert all(land(ring, said))
    stored = ring.stored("work", "talk~q1")["data"]
    assert stored["status"] == "claimed" and stored["chat_title"] == page_db.QUESTION_CHAT_TITLE
    # The changes stay with the chat that answers the page, taken on the same folder.
    again = ring.wake(ring.read("wake2"))
    assert [it["work"] for it in _items(again)] == ["tweak~0", "tweak~1", "tweak~2"], again
    assert all(it["run"] == "here" for it in _items(again))


def test_the_chats_own_chat_is_reused_for_the_next_question(ring):
    ring.queue("tweak~0", kind="tweak", asked_at="2026-10-25T17:00:00Z")
    _ask(ring, "talk~q1")
    said = ring.wake(ring.read("wake1"))
    assert next_item(said)["run"] == "child session" and all(land(ring, said))
    assert all(land(ring, ring.wake(ring.read("wake1b"))))       # tweak~0, taken here
    # Another question while that chat is at work: the chat that answers the page leaves it
    # to that chat, and starts no second one.
    _ask(ring, "talk~q2", at="2026-10-25T17:06:00Z")
    ring.queue("tweak~1", kind="tweak", asked_at="2026-10-25T17:07:00Z")
    again = ring.wake(ring.read("wake2"))
    assert [it["work"] for it in _items(again)] == ["tweak~1"], again
    assert ring.stored("work", "talk~q2")["data"]["status"] == "queued"
    assert not any("create_session" in it for it in _items(again))
    # The Chat's own chat, finishing its question, takes the next one, and never a change.
    got = json.loads(ring.run("next", ring.read("dump3"), "--chat", QUESTION_CHAT, "--kind",
                              "cloud", "--job-chat", "--questions", "--now", NOW))
    assert got["work"] == "talk~q2" and got["run"] == "here", got
    assert any("--job-chat --questions" in s for s in got["steps"]), got["steps"]
    # Its steps answer and bring the page up to date before the save.
    finish = next(s for s in got["steps"] if "Finish as step 5 says" in s)
    assert finish.index("app.py view") < finish.index("tools/land.py"), finish


def test_the_question_chat_counts_against_the_cloud_chats_limit(ring):
    # Every place taken by big jobs at work in chats of their own: the question is answered
    # here, first, and no chat is started for it.
    for i in range(page_db.HEAVY_CAP_CHATS):
        ring.put("work", f"draft~{i}", {"kind": "draft", "status": "running", "title": "A job",
                                        "to": "cloud", "asked_at": "2026-10-25T16:00:00Z",
                                        "claimed_by": CHAT, "claimed_at": "2026-10-25T17:50:00Z",
                                        "lease_until": "2026-10-25T18:40:00Z"})
    ring.queue("tweak~0", kind="tweak", asked_at="2026-10-25T17:00:00Z")   # busy here
    _ask(ring, "talk~q1")
    said = ring.wake(ring.read("wake1"))
    assert next_item(said)["work"] == "talk~q1" and next_item(said)["run"] == "here", said
    # And the Chat's own chat takes a place a big job would: one fewer big job starts.
    db = {"work": {"talk~q1": {"version": 2, "data": {
        "kind": "talk", "status": "claimed", "chat_title": page_db.QUESTION_CHAT_TITLE,
        "claimed_by": CHAT, "lease_until": "2026-10-25T18:40:00Z", "args": {"thread": "t"}}}}}
    import datetime as dt
    now = dt.datetime(2026, 10, 25, 18, 0, tzinfo=dt.timezone.utc)
    assert page_db.chats_at_work(db, now) == 1 and page_db.question_chat_live(db, now)


def test_no_create_session_or_a_cards_question_is_answered_here_first(ring):
    for i in range(3):
        ring.queue(f"tweak~{i}", kind="tweak", asked_at=f"2026-10-25T17:0{i}:00Z")
    _ask(ring, "talk~q1")
    said = ring.wake(ring.read("wake1"), "--no-sessions")
    assert next_item(said)["work"] == "talk~q1" and next_item(said)["run"] == "here", said
    assert "create_session" not in next_item(said) and "first: the item under next:" in said
    # A question asked under a card is answered under it, here, as before.
    _ask(ring, "talk~card", about={"kind": "job", "id": "job-1", "label": "A job"})
    assert not page_db.chat_question(ring.stored("work", "talk~card")["data"])


def test_the_chats_own_chat_is_put_away_when_its_work_has_ended():
    # Its first pin records it as the chat that runs the question (run_by), as a big job's
    # does, so the daily tidy-up finds it finished and archives it, and it puts itself away
    # when no question is left (its last step).
    db = {"work": {"talk~q1": {"version": 4, "data": {
        "kind": "talk", "status": "done", "finished_at": "2026-10-25T18:02:00Z",
        "claimed_by": CHAT, "run_by": QUESTION_CHAT, "chat_title": page_db.QUESTION_CHAT_TITLE,
        "args": {"thread": "t"}}}}}
    assert tidy.finished_jobs(db, skip=CHAT) == {QUESTION_CHAT: "2026-10-25T18:02:00Z"}
    steps = app.job_steps({"work": "talk~q1", "kind": "talk", "stages": []}, CHAT, "<url>")
    last = steps[-1]
    assert "--questions" in last and "archive_session" in last, last


def test_a_look_between_items_leaves_a_chat_question_to_the_chats_own_chat():
    # The look a pass makes between its items (app_listen.py waiting --question) names a Chat
    # question only while no chat of its own is at work on Chat questions: `next` would hand
    # the chat that answers the page a change instead, and the line said it hands a question.
    import datetime as dt
    import app_listen
    now = dt.datetime(2026, 10, 25, 18, 0, tzinfo=dt.timezone.utc)
    waiting = {"version": 1, "data": {"kind": "talk", "status": "queued", "asked_at": "2026-10-25T17:58:00Z",
                                      "args": {"thread": "t", "message": "m2"}}}
    live = {"version": 2, "data": {"kind": "talk", "status": "claimed", "claimed_by": CHAT,
                                   "chat_title": page_db.QUESTION_CHAT_TITLE,
                                   "lease_until": "2026-10-25T18:30:00Z", "args": {"thread": "t"}}}
    assert app_listen.question_waiting({"work": {"talk~2": waiting}}, now) == "talk~2"
    assert app_listen.question_waiting({"work": {"talk~2": waiting, "talk~1": live}}, now) == ""


def test_a_question_with_nothing_else_going_on_is_answered_in_place(ring):
    # Nothing else running or waiting for the chat that answers the page: answered there, at
    # once, which is quicker than a fresh chat's full start (the coordinator, issue #226). A
    # big job at work in a chat of its own does not keep it busy.
    ring.put("work", "draft~1", {"kind": "draft", "status": "running", "title": "A job",
                                 "to": "cloud", "asked_at": "2026-10-25T16:00:00Z",
                                 "claimed_by": CHAT, "claimed_at": "2026-10-25T17:50:00Z",
                                 "chat_title": "Job search: A job", "run_by": "session_EXAMPLEJOB",
                                 "lease_until": "2026-10-25T18:40:00Z"})
    _ask(ring, "talk~q1")
    said = ring.wake(ring.read("wake1"))
    item = next_item(said)
    assert item["work"] == "talk~q1" and item["run"] == "here" and "create_session" not in item, said
    assert all(land(ring, said))
    assert ring.stored("work", "talk~q1")["data"]["status"] == "running"


def test_a_question_asked_while_this_chat_works_gets_a_chat_of_its_own(ring):
    # Busy: a change this chat is making, its claim live and no chat of its own named on it.
    ring.put("work", "tweak~1", {"kind": "tweak", "status": "running", "title": "A change",
                                 "to": "cloud", "asked_at": "2026-10-25T17:00:00Z",
                                 "claimed_by": CHAT, "claimed_at": "2026-10-25T17:55:00Z",
                                 "lease_until": "2026-10-25T18:25:00Z", "stage": 0})
    _ask(ring, "talk~q1")
    got = json.loads(ring.run("next", ring.read("dump1"), "--chat", CHAT, "--kind", "cloud",
                              "--now", NOW))
    assert got["work"] == "talk~q1" and got["run"] == "child session", got
    assert "app.py let-go" in got["if_refused"], got


def test_a_refused_start_lets_the_claim_go_and_the_question_is_answered_here_first(ring):
    for i in range(3):
        ring.queue(f"tweak~{i}", kind="tweak", asked_at=f"2026-10-25T17:0{i}:00Z")
    _ask(ring, "talk~q1")
    d = ring.read("wake1")
    said = ring.wake(d)
    assert next_item(said)["run"] == "child session" and all(land(ring, said))
    # create_session refused: the claim is let go at once, never left for thirty minutes.
    import subprocess
    out = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "app.py"), "let-go", d,
                          "--work", "talk~q1", "--chat", CHAT, "--now", NOW],
                         capture_output=True, text=True, encoding="utf-8")
    assert out.returncode == 0, out.stderr
    batch = [ln for ln in out.stdout.splitlines() if ln.endswith(".json")]
    import fake_db
    assert batch and all(fake_db.apply(ring.db, p) for p in batch), out.stdout
    stored = ring.stored("work", "talk~q1")["data"]
    assert stored["status"] == "queued" and not stored.get("claimed_by") \
        and not stored.get("chat_title") and stored["own_chat"] == "refused", stored
    # The wake again, with the same folder: the question first, answered here, then the changes.
    again = ring.wake(d)
    took = _items(again)
    assert [it["work"] for it in took] == ["talk~q1", "tweak~0", "tweak~1", "tweak~2"], again
    assert all(it["run"] == "here" for it in took)
    assert all(land(ring, again))
    assert ring.stored("work", "talk~q1")["data"]["claimed_by"] == CHAT
    # Nobody else's claim is let go.
    other = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "app.py"), "let-go",
                            ring.read("dump2"), "--work", "talk~q1", "--chat", "session_EXAMPLEOTHER",
                            "--now", NOW], capture_output=True, text=True, encoding="utf-8")
    assert other.returncode == 2 and "not claimed by this chat" in other.stderr
