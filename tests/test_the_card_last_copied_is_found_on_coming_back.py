"""Coming back from LinkedIn, the page points at the message whose Copy or "Open their
profile" was pressed last.

The maintainer, 2026-11-10: "sometimes i get confused as to whose profile i copied/opened last
after going to the linkedin page and back (so i press copy, then open profile and send the
request, but i might forget which one to put I sent it on)". The page remembers, on this
device, the message last copied or opened; when the page is shown again (the browser's
visibilitychange, or the window's focus) and that message is still unsent, its card is brought
into view, ringed for a few seconds in the page's selected style, and its I sent it is the
filled pill. I sent it, or a tap anywhere else, lets it go. Every name here is the sample's.

Beside it, the same day's other note on leaving the page for a chat: work started in a chat on
the person's computer says so on its card while it runs.
"""
from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from test_the_page_works_in_a_browser import PHONE, WIDE, _sample, _write, run  # noqa: E402

_ = run   # the fixture, used by name


@pytest.fixture(scope="module")
def sample_page(tmp_path_factory):
    return _write(tmp_path_factory.mktemp("lastused"), "sample", _sample())


@pytest.mark.parametrize("viewport,how,motion", [(PHONE, "hidden", "no-preference"), (WIDE, "hidden", "reduce"),
                                                 (PHONE, "blur", "reduce")])
def test_the_card_last_copied_or_opened_is_shown_and_marked_on_return(run, sample_page, viewport, how, motion):
    first, second = "msg-juno-1", "msg-rafe-1"
    seed = {"reach/larkspur_retail_castellan": {"linkedin": "https://www.linkedin.com/in/juno-example"}}
    r = run("last_used", html=sample_page, viewport=viewport, how=how, reducedMotion=motion,
            first=first, second=second, seed=seed)
    assert not r.get("errors"), r.get("errors")
    # Copied: remembered for this tab, and its I sent it filled.
    assert r["afterCopy"]["kept"] == first and r["afterCopy"]["sentFilled"], r["afterCopy"]
    # Back on the page, scrolled to the top meanwhile: its card is in view, ringed, I sent it
    # the screen's one filled pill; the other card is not marked.
    back = r["back"]
    assert back["inView"] and back["sentInView"], back
    assert back["marked"] and back["ring"], back
    assert back["filled"] == ["sent:" + first], back["filled"]
    assert not r["other"]["marked"], r["other"]
    # The ring fades after a few seconds; I sent it stays filled.
    assert not r["later"]["marked"] and not r["later"]["ring"] and r["later"]["sentFilled"], r["later"]
    # A second card's Copy moves the mark.
    moved = r["moved"]
    assert moved["inView"] and moved["sentInView"] and moved["marked"], moved
    assert moved["filled"] == ["sent:" + second], moved["filled"]
    assert not r["oldOne"]["marked"] and not r["oldOne"]["sentFilled"], r["oldOne"]
    # A tap elsewhere lets it go.
    assert not r["tapped"]["marked"] and r["tapped"]["kept"] is None, r["tapped"]
    # Open their profile does what Copy does, and I sent it lets it go.
    assert r["link"], "the sample's first card carries Open their profile once its address is known"
    assert r["afterOpen"]["kept"] == first and r["afterOpen"]["sentFilled"], r["afterOpen"]
    assert r["opened"]["inView"] and r["opened"]["marked"] and r["opened"]["filled"] == ["sent:" + first], r["opened"]
    assert r["afterSent"] == {"kept": None, "marked": 0}, r["afterSent"]


@pytest.mark.parametrize("viewport", [PHONE, WIDE])
def test_work_started_in_a_chat_on_the_computer_says_so_on_its_card_while_it_runs(run, sample_page, viewport):
    """Where the computer side starts a chat on the person's computer (tools/computer.py
    route, then started), its work card says so in plain words while the work runs, past the
    steps Claude writes after it, and stops saying it once that chat is archived or done."""
    import computer
    say = computer.runs_there("Studio Laptop")
    assert say == "This runs in a chat on your Studio Laptop, which you can delete when it's done."
    r = run("runs_there", html=sample_page, viewport=viewport, say=say)
    assert not r.get("errors"), r.get("errors")
    assert r["running"] == [say], r
    assert r["now"] != say, "the newest step is its own line; the computer's stays beside it"
    assert r["archived"] == [] and r["done"] == [], r
