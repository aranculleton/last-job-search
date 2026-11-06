"""The page measures in the window's own px in every engine, and a computer with no pointer is a
computer.

4.12's Safari run: the page is drawn at 0.9 (0.85 on a phone), and Safari measures a box before
that zoom while Chrome and Firefox measure it after. Set against the window's height as it came,
Safari's laptop Brief thought it had less room and gave up rows it had room for (and never
filled to its foot at 1000 by 560), and the Chat's Latest scrolled short of the field on a
phone. Here Chrome measures Safari's way (the harness's `measureBeforeZoom`), so the ordinary
run holds both.

4.12's Firefox run: Firefox with no mouse it can see reports no pointer, and the laptop's
14px type was only for a fine pointer, so the Brief drew at 16px and scrolled, a job card's
facts took two lines and the privacy line wrapped short. A computer reporting no pointer is
drawn as one with a mouse; only a touch screen keeps the larger type.
Every person and employer is invented (the sample's own).
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import test_the_page_journeys as journeys  # noqa: E402
from test_the_brief_fits_a_laptop_and_its_foot_reads_as_one_line import FIT, LAPTOPS, PERSON_ZONE, T, _full  # noqa: E402
from test_the_chat_opens_on_its_latest import CLOCK, _talk  # noqa: E402
from test_the_page_works_in_a_browser import _write  # noqa: E402


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


@pytest.mark.parametrize("size", LAPTOPS, ids=lambda s: "%dx%d" % (s["width"], s["height"]))
def test_a_full_brief_fills_a_laptop_measured_safaris_way(run, tmp_path, size):
    html = _write(tmp_path, "brief", _full())
    got = run("engine", html=html, viewport=size, clock=T, timezoneId=PERSON_ZONE, measureBeforeZoom=True,
              fake={"canSend": "available"}, steps=[{"hash": "brief", "eval": FIT}])
    assert not got["errors"], got["errors"]
    r = got["after"][0]["eval"]
    assert r["scroll"] <= 1 and not r["out"] and not r["spill"], r
    assert r["tip"] is True and r["priv"] == [True], r
    assert r["filled"] is True, ("the Brief gave up room it had, measured Safari's way", size, r)


def test_latest_on_a_phone_measured_safaris_way_stops_at_the_field(run, tmp_path):
    html = _write(tmp_path, "talkphone", journeys._sample())
    gap = ("(() => { const f = document.querySelector('#main .talk-form'); const t = document.querySelector('.tabs');"
           " const under = t && getComputedStyle(t).position === 'fixed' ? t.__drawnRect().height : 0;"
           " return Math.round(window.innerHeight - under - f.__drawnRect().bottom); })()")
    got = run("engine", html=html, viewport={"width": 390, "height": 760}, clock=CLOCK, seed=_talk(), measureBeforeZoom=True, steps=[
        {"hash": "chat", "wait": 300},
        {"eval": "(window.scrollTo(0, 0), window.dispatchEvent(new Event('scroll')), 1)"},
        {"click": "Go to the latest message", "wait": 300, "eval": gap},
    ])
    assert not got["errors"], got["errors"]
    left = got["after"][2]["eval"]
    assert 0 <= left <= 40, f"{left}px of empty page under the field, measured Safari's way"


def test_a_computer_with_no_pointer_gets_the_laptops_type():
    with open(os.path.join(ROOT, "templates", "app", "app.css"), encoding="utf-8") as fh:
        css = fh.read()
    laptop = [q for q in re.findall(r"@media ([^{]+)\{", css) if "(pointer: fine)" in q and "760px" in q and "hover" not in q]
    assert laptop, "the laptop's own rules were found"
    for q in laptop:
        assert "(pointer: none)" in q, ("a computer reporting no pointer misses this laptop rule", q.strip())
