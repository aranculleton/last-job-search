"""Chat opens on its newest message, shows the last day, and has a way back down.

The maintainer, 2026-11-05: "when u press chat ... it seems to put u all the way at the top and
u gotta scroll down. also if u scroll up there isnt an easy scroll down arrow, also i can see the
entire history of the entire chat ... surely it should show like 24hrs max". Every message here
is invented.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_the_page_journeys import _sample, browser  # noqa: E402
from test_the_page_works_in_a_browser import _write  # noqa: E402

WIDE = {"width": 1400, "height": 800}
CLOCK = "2026-10-25T18:30:00Z"


@pytest.fixture(scope="module")
def run():
    yield from browser()


def _talk():
    seed = {"talk/cloud-1": {"to": "cloud", "conv": "1", "title": "Questions", "created_at": "2026-10-20T09:00:00Z", "_v": 1}}
    # Thirty messages last week, then twenty today.
    for i in range(30):
        seed["talk/cloud-1/messages/o%02d" % i] = {"from": "you" if i % 2 == 0 else "cloud", "text": "Older message %d" % i, "at": "2026-10-20T10:%02d:00Z" % i, "_v": 1}
    for i in range(20):
        seed["talk/cloud-1/messages/n%02d" % i] = {"from": "you" if i % 2 == 0 else "cloud", "text": "Today's message %d, long enough to take some room on the screen." % i,
                                                  "at": "2026-10-25T17:%02d:00Z" % (10 + i), "_v": 1}
    return seed


def test_chat_opens_at_its_newest_shows_the_last_day_and_has_a_way_down(run, tmp_path):
    html = _write(tmp_path, "talk", _sample())
    probe = ("(() => { const sc = document.scrollingElement; const t = [...document.querySelectorAll('#main .talk-msg .talk-text')].map((e) => e.textContent);"
             " const j = document.querySelector('[data-k=\"talk-jump\"]');"
             " return {end: sc.scrollHeight - sc.scrollTop - sc.clientHeight < 90, older: t.filter((x) => x.startsWith('Older')).length,"
             " today: t.filter((x) => x.startsWith('Today')).length, jump: !!j && !j.hidden, earlier: !!document.querySelector('.talk-earlier-msgs')}; })()")
    got = run("engine", html=html, viewport=WIDE, clock=CLOCK, seed=_talk(), steps=[
        {"hash": "chat", "wait": 300, "eval": probe},
        {"eval": "(window.scrollTo(0, 0), window.dispatchEvent(new Event('scroll')), 1)"},
        {"wait": 300, "eval": probe},
        {"click": "Go to the latest message", "wait": 300, "eval": probe},
    ])
    assert not got["errors"], got["errors"]
    first = got["after"][0]["eval"]
    assert first["end"] and first["today"] == 20 and first["older"] == 0 and first["earlier"], first
    assert got["after"][2]["eval"]["jump"], got["after"][2]["eval"]
    assert got["after"][3]["eval"]["end"], got["after"][3]["eval"]


def test_a_question_the_quick_answer_fails_goes_to_claude(run, tmp_path):
    """The maintainer, 2026-11-05: two messages saved in the page's quick chat that nothing
    answered and that never reached Claude. A quick answer that fails or never comes hands the
    question to Claude, as one that needs Claude does."""
    html = _write(tmp_path, "quickfail", _sample())
    got = run("talk", html=html, question="What did Juno say about the role last week?", sample={"error": "upstream_error"})
    assert not got["errors"], got["errors"]
    talk = [w for w in got["work"] if w.get("kind") == "talk"]
    assert len(talk) == 1, (got["work"], got["quick"])
    assert not any("That did not work" in t for t in got["quick"]), got["quick"]


def test_latest_on_a_phone_stops_with_the_field_at_the_foot_of_the_screen(run, tmp_path):
    # On a phone, Latest scrolled to the page's own end, past the field and its note to the
    # privacy line, and left a band of empty page under the field (the maintainer, 2026-11-05).
    html = _write(tmp_path, "talkphone", _sample())
    # In the window's own px (__drawnRect): Safari measures before the page's zoom.
    gap = ("(() => { const f = document.querySelector('#main .talk-form'); const t = document.querySelector('.tabs');"
           " const under = t && getComputedStyle(t).position === 'fixed' ? t.__drawnRect().height : 0;"
           " return Math.round(window.innerHeight - under - f.__drawnRect().bottom); })()")
    got = run("engine", html=html, viewport={"width": 390, "height": 760}, clock=CLOCK, seed=_talk(), steps=[
        {"hash": "chat", "wait": 300},
        {"eval": "(window.scrollTo(0, 0), window.dispatchEvent(new Event('scroll')), 1)"},
        {"click": "Go to the latest message", "wait": 300, "eval": gap},
    ])
    assert not got["errors"], got["errors"]
    left = got["after"][2]["eval"]
    assert 0 <= left <= 40, f"{left}px of empty page under the field"


# What the thread draws: Claude's messages, and the state said under each of your questions.
THREAD = ("({claude: [...document.querySelectorAll('#main .talk-msg:not(.from-you) .talk-text')].map((e) => e.textContent),"
          " states: [...document.querySelectorAll('#main .talk-msg.from-you .talk-state')].map((e) => e.textContent.trim())})")


def test_an_answer_waits_until_the_page_has_what_its_work_changed(run, tmp_path):
    # The answer said "see the updated message" while the card still showed the old draft
    # (reported from a person's copy, 2026-11-05): an answer written with its work after the
    # page's newest view says it is putting the change on the page first, for five minutes at
    # most; one older than the page's view reads as written.
    html = _write(tmp_path, "held", _sample())
    def seed(at):
        return {"talk/cloud-1": {"to": "cloud", "conv": "1", "title": "Questions", "created_at": "2026-10-25T17:00:00Z", "_v": 1},
                "talk/cloud-1/messages/q1": {"from": "you", "text": "Make the note shorter", "at": "2026-10-25T17:59:00Z", "work": "talk~1", "_v": 1},
                "talk/cloud-1/messages/a1": {"from": "cloud", "text": "Done: see the updated message on the card.", "at": at, "work": "talk~1", "_v": 1,
                                             "go": [{"label": "Contacts", "to": "page:contacts"}]}}
    # Said under the question, never as a Claude message that reads as the answer (issue #234).
    fresh = run("engine", html=html, viewport=WIDE, clock=CLOCK, seed=seed("2026-10-25T18:29:00Z"), steps=[{"hash": "chat", "eval": THREAD}])
    assert not fresh["errors"], fresh["errors"]
    got = fresh["after"][0]["eval"]
    assert got["claude"] == [] and got["states"] == ["Putting the change on your page"], got
    old = run("engine", html=html, viewport=WIDE, clock=CLOCK, seed=seed("2026-10-25T18:00:00Z"), steps=[{"hash": "chat", "eval": THREAD}])
    got = old["after"][0]["eval"]
    assert "see the updated message" in " ".join(got["claude"]) and got["states"] == [], got


def test_an_answer_that_changed_nothing_on_the_page_shows_at_once(run, tmp_path):
    # A plain answer waits for nothing: held behind "Putting the change on your page first"
    # until the chat's last item was put on the page, a question asked behind three message
    # changes read as slow, the line promising an order the chat did not keep (issue #226).
    html = _write(tmp_path, "plain", _sample())
    seed = {"talk/cloud-1": {"to": "cloud", "conv": "1", "title": "Questions", "created_at": "2026-10-25T17:00:00Z", "_v": 1},
            "talk/cloud-1/messages/q1": {"from": "you", "text": "When is the Larkspur interview?", "at": "2026-10-25T18:28:00Z", "work": "talk~2", "_v": 1},
            "talk/cloud-1/messages/a1": {"from": "cloud", "text": "Thursday at 10am, with the data team.", "at": "2026-10-25T18:29:00Z", "work": "talk~2", "_v": 1}}
    texts = "[...document.querySelectorAll('#main .talk-msg .talk-text')].map((e) => e.textContent)"
    got = run("engine", html=html, viewport=WIDE, clock=CLOCK, seed=seed, steps=[{"hash": "chat", "eval": texts}])
    assert not got["errors"], got["errors"]
    said = " ".join(got["after"][0]["eval"])
    assert "Thursday at 10am" in said and "Putting the change on your page first" not in said, said


def test_a_queued_question_says_so_under_itself_until_its_answer_is_drawn(run, tmp_path):
    # Issue #234: a question sent while other work ran got a grey Claude message, one more for
    # each question, and nothing on the question said whether it waited or was being answered.
    # Now each says it under itself, a spinner and a word or two, and no Claude message is
    # drawn until there is an answer; the state goes once it is.
    html = _write(tmp_path, "waiting", _sample())
    seed = {"talk/cloud-1": {"to": "cloud", "conv": "1", "title": "Questions", "created_at": "2026-10-25T17:00:00Z", "_v": 1},
            "talk/cloud-1/messages/q1": {"from": "you", "text": "Which jobs came in today?", "at": "2026-10-25T18:25:00Z", "work": "talk~3", "_v": 1},
            "talk/cloud-1/messages/q2": {"from": "you", "text": "And which are in Leeds?", "at": "2026-10-25T18:27:00Z", "work": "talk~4", "_v": 1},
            "work/talk~3": {"kind": "talk", "title": "Which jobs came in today?", "to": "cloud", "args": {"thread": "cloud-1"},
                            "asked_at": "2026-10-25T18:25:00Z", "status": "claimed", "claimed_by": "session_EXAMPLEhelper2",
                            "claimed_at": "2026-10-25T18:25:10Z", "lease_until": "2026-10-25T18:55:10Z", "stage": 0, "steps": [], "_v": 2},
            "work/talk~4": {"kind": "talk", "title": "And which are in Leeds?", "to": "cloud", "args": {"thread": "cloud-1"},
                            "asked_at": "2026-10-25T18:27:00Z", "status": "queued", "stage": 0, "steps": [], "_v": 1},
            "chats/session_EXAMPLEhelper2": {"kind": "cloud", "seen_at": "2026-10-25T18:29:30Z", "watching": True}}
    waiting = run("engine", html=html, viewport=WIDE, clock=CLOCK, seed=seed, steps=[{"hash": "chat", "eval": THREAD}])
    assert not waiting["errors"], waiting["errors"]
    got = waiting["after"][0]["eval"]
    assert got["claude"] == [] and got["states"] == ["Claude is answering", "Waiting its turn"], got
    # Answered: the answer is drawn and the first question's state is gone.
    seed["talk/cloud-1/messages/a1"] = {"from": "cloud", "text": "Two came in today, both in York.", "at": "2026-10-25T18:28:00Z", "work": "talk~3", "_v": 1}
    seed["work/talk~3"] = dict(seed["work/talk~3"], status="done", done_at="2026-10-25T18:28:00Z")
    answered = run("engine", html=html, viewport=WIDE, clock=CLOCK, seed=seed, steps=[{"hash": "chat", "eval": THREAD}])
    assert not answered["errors"], answered["errors"]
    got = answered["after"][0]["eval"]
    assert got["claude"] == ["Two came in today, both in York."] and got["states"] == ["Waiting its turn"], got
