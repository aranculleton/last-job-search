"""An interview's prep opens, and stays open, inside the Claude app.

The incident (the maintainer, 2026-11-11, the night before an interview): in the Claude app
on a Mac, the interview's card in Coming up had Practise 3 questions and Read your prep, and
both flickered as if pressed and opened nothing; Draft on a job and the card's More worked.
The same page, data and code opened the prep in every browser, bare or in a sandboxed frame.
The one thing on the page that closes a sheet unasked is a move of its address: the sheet
pushes `#interviews/<id>/open`, and any address event that did not end in `/open` closed it.
A frame that answers that push (its own address said again, the address before it put back,
the push refused, or any of these a moment later) closed the sheet the instant it opened.

Each test plays such a frame in the page itself, wrapping `history.pushState` the way a host
could, then taps the card's button as a person would on the invented sample search (the live
prep is the engine's own, built for the example person's invented application) and checks the
sheet is open after the frame has answered. A real Back, after the sheet has been open a
moment, still closes it. Every person and employer is invented.
"""
from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import app_page  # noqa: E402
from test_interview_pack import app  # noqa: E402,F401
from test_the_live_prep_on_the_page import _soon  # noqa: E402
from test_the_page_journeys import PHONE, WIDE, _sample, browser  # noqa: E402

# The live prep is built from the example person's invented application, on disk for each test.
pytestmark = pytest.mark.usefixtures("app")


@pytest.fixture(scope="module")
def run():
    yield from browser()


# How a frame can answer the address a page pushes. `before`: the address before the push.
# Each says when it has answered (window.__answered), so a test waits for that, never a time.
ANSWERS = {
    # The same address said again, as a move of its own.
    "same": "orig(s, t, u); say();",
    # The push taken back at once: the address before it put back, and said.
    "put_back": "orig(s, t, u); history.replaceState(null, '', before); say();",
    # The push refused: the address never moves, and a move is said all the same.
    "refused": "say();",
    # The push taken back a moment later, after the page has drawn the sheet.
    "put_back_later": "orig(s, t, u); setTimeout(() => { history.replaceState(null, '', before); say(); }, 50);",
}


def _frame(answer):
    # The page is in another page's frame, as the Claude app shows it (window.__ljsFramed
    # stands in for window.self !== window.top, which a test's own tab cannot make true).
    return ("(() => { window.__ljsFramed = true; const orig = history.pushState.bind(history);"
            " history.pushState = function (s, t, u) { const before = location.hash;"
            " const say = () => { window.dispatchEvent(new PopStateEvent('popstate', {state: history.state}));"
            " window.dispatchEvent(new HashChangeEvent('hashchange')); window.__answered = true; };"
            " %s }; return 1; })()" % ANSWERS[answer])


SHEET = ("(() => { const d = document.querySelector('dialog.detail'); const lp = d && d.querySelector('.lp');"
         " return {open: !!(d && d.open), title: d ? d.querySelector('.detail-title').textContent : '',"
         " hash: location.hash, mode: lp ? lp.dataset.mode : ''}; })()")


def _go(run, tmp_path, model, steps, vp):
    path = os.path.join(str(tmp_path), "page.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(app_page.standalone(app_page.render(model)))
    got = run("engine", html=path, viewport=vp, steps=steps, seed={}, fake={"canSend": "available"})
    assert not got["errors"], got["errors"]
    return got


# The two buttons of the incident: Read your prep on the sample's interview three days away,
# and Practise 3 questions on its live prep the day before.
TAPS = {"read": ("Read your prep", lambda: _sample()), "practise": ("Practise 3 questions", lambda: _soon(1))}


@pytest.mark.parametrize("answer", sorted(ANSWERS))
@pytest.mark.parametrize("tap", sorted(TAPS))
def test_the_prep_stays_open_whatever_the_frame_does_with_its_address(run, tmp_path, tap, answer):
    name, make = TAPS[tap]
    model = make()
    company = next(iv["company"] for iv in model["interviews"] if iv["id"] == "int-larkspur-supply")
    got = _go(run, tmp_path, model, [
        {"hash": "interviews"},
        {"click": "Interviews", "exact": True, "eval": _frame(answer)},
        {"click": name, "within": "#main", "ready": "window.__answered === true", "eval": SHEET},
    ], PHONE)
    seen = got["after"][2]["eval"]
    assert seen["open"], (tap, answer, seen)
    assert company in seen["title"], seen
    # The sheet the tap opened, never one drawn again over it: the practice keeps its answers
    # hidden (a redraw for its own address opened it with every answer showing).
    if tap == "practise":
        assert seen["mode"] == "hidden", seen


@pytest.mark.parametrize("vp", [PHONE, WIDE], ids=["phone", "wide"])
def test_back_still_closes_the_prep_once_it_is_open(run, tmp_path, vp):
    got = _go(run, tmp_path, _sample(), [
        {"hash": "interviews"},
        {"click": "Interviews", "exact": True},
        {"click": "Read your prep", "within": "#main", "eval": SHEET},
        # A moment later the person goes Back: the sheet closes and Coming up is where it was.
        {"tick": 1500, "eval": "(() => { history.back(); return 1; })()"},
        {"ready": "!document.querySelector('dialog.detail')", "eval": SHEET},
    ], vp)
    opened, closed = got["after"][2]["eval"], got["after"][4]["eval"]
    assert opened["open"] and opened["hash"] == "#interviews/int-larkspur-supply/open", opened
    assert not closed["open"] and closed["hash"] == "#interviews", closed

