"""The Chat panel sits on either side, its buttons are the page's own, and its history comes
back only when asked.

The maintainer, 2026-11-06: the bigger Chat panel is great; "would be great if there was one
that puts it to the left side of the screen if desired, and back to the right ... and it should
work with the bigger one ... should also exist in settings somewhere smart", and "make the
buttons open in chat and close actual buttons consistent with the app theme" (they were two
underlined words). And: "it appears i can still scroll to the beginning of time": scrolling to
the top of the conversation loaded twenty more by itself, again and again.
Every person and employer is invented (the sample's own).
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import test_the_page_journeys as journeys  # noqa: E402
from test_the_chat_opens_on_its_latest import CLOCK, _talk  # noqa: E402
from test_the_page_journeys import _sample  # noqa: E402
from test_the_page_works_in_a_browser import _write  # noqa: E402

LAPTOP = {"width": 1280, "height": 800}
WHERE = ("(() => { const d = document.querySelector('#chat-dock'); const f = document.querySelector('#chat-fab');"
         " const r = (e) => e && e.getClientRects().length ? Math.round(e.getBoundingClientRect().left) : null;"
         " return {dock: d && !d.hidden ? r(d) : null, fab: r(f), big: d ? d.classList.contains('is-big') : null,"
         " kept: localStorage.getItem('ljs:dock-side'),"
         " pills: ['dock-full', 'dock-close'].map((k) => { const b = document.querySelector('[data-k=\"' + k + '\"]'); return b ? b.classList.contains('secondary') && !b.classList.contains('quiet') : null; })}; })()")


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


def test_the_panel_moves_left_and_back_big_or_small(run, tmp_path):
    html = _write(tmp_path, "side", _sample())
    got = run("engine", html=html, viewport=LAPTOP, clock=CLOCK, fake={"canSend": "available"}, steps=[
        {"hash": "todo", "click": "Chat with Claude", "wait": 200, "eval": WHERE},
        {"eval": "(document.querySelector('[data-k=\"dock-side\"]').click(), 1)", "wait": 200},
        {"eval": WHERE},
        {"eval": "(document.querySelector('[data-k=\"dock-size\"]').click(), 1)", "wait": 200},
        {"eval": WHERE},
        {"eval": "(document.querySelector('[data-k=\"dock-side\"]').click(), 1)", "wait": 200},
        {"eval": WHERE},
    ])
    assert not got["errors"], got["errors"]
    right, left, big_left, back = (got["after"][i]["eval"] for i in (0, 2, 4, 6))
    assert right["dock"] is not None and right["dock"] > LAPTOP["width"] / 2, right
    assert right["pills"] == [True, True], ("Open in Chat and Close are the page's own soft pills", right)
    assert left["dock"] is not None and left["dock"] < 40 and left["kept"] == "left", left
    assert big_left["big"] and big_left["dock"] < 40, big_left
    assert back["dock"] > LAPTOP["width"] / 3 and back["kept"] is None, back


def test_settings_look_sets_the_same_side(run, tmp_path):
    html = _write(tmp_path, "sideset", _sample())
    got = run("engine", html=html, viewport=LAPTOP, clock=CLOCK, fake={"canSend": "available"}, steps=[
        {"hash": "settings", "eval": "!!document.querySelector('[data-k=\"side-right\"]:checked')"},
        {"eval": "(document.querySelector('[data-k=\"side-left\"]').click(), 1)", "wait": 200},
        {"eval": "[localStorage.getItem('ljs:dock-side'), Math.round(document.querySelector('#chat-fab').getBoundingClientRect().left)]"},
    ])
    assert not got["errors"], got["errors"]
    assert got["after"][0]["eval"] is True
    kept, fab = got["after"][2]["eval"]
    assert kept == "left" and fab < 300, (kept, fab)


COUNT = "document.querySelectorAll('#main .talk-msg').length"


def test_earlier_messages_come_only_when_asked(run, tmp_path):
    html = _write(tmp_path, "back", _sample())
    got = run("engine", html=html, viewport={"width": 1400, "height": 800}, clock=CLOCK, seed=_talk(), steps=[
        {"hash": "chat", "wait": 300, "eval": COUNT},
        {"eval": "(window.scrollTo(0, 0), window.dispatchEvent(new Event('scroll')), 1)", "wait": 800},
        {"eval": COUNT},
        {"eval": "(window.scrollTo(0, 0), window.dispatchEvent(new Event('scroll')), 1)", "wait": 800},
        {"eval": COUNT},
        {"eval": "(document.querySelector('[data-k=\"talk-earlier-msgs\"]').click(), 1)", "wait": 300},
        {"eval": COUNT},
    ])
    assert not got["errors"], got["errors"]
    first, scrolled, again, shown = (got["after"][i]["eval"] for i in (0, 2, 4, 6))
    assert scrolled == first and again == first, ("scrolling up loaded older messages by itself", first, scrolled, again)
    assert shown > first, (first, shown)
