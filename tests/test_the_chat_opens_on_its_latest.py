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
