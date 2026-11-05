"""What the review of this version's screens found, each pinned (2026-11-05).

A reviewer who did not build the screens read them as a tired person on a phone: the Latest
button sat behind the box on a phone; Jobs' search squeezed the To apply / Applied switch
unreadable; "Not confirmed yet" stretched into a bar; the pencil's box left the cursor on the
pencil. And the maintainer: a downloaded resume was named "..._Resume_<employer>_<role run together>.pdf",
"quite a robotic name". Every person and employer here is the sample's, invented.
"""
from __future__ import annotations

import copy
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_the_page_journeys import _sample, browser  # noqa: E402
from test_the_page_works_in_a_browser import _write  # noqa: E402
from test_the_chat_opens_on_its_latest import _talk  # noqa: E402

PHONE = {"width": 390, "height": 844}
WIDE = {"width": 1400, "height": 900}
CLOCK = "2026-10-25T18:30:00Z"


@pytest.fixture(scope="module")
def run():
    yield from browser()


@pytest.fixture(scope="module")
def page(tmp_path_factory):
    return _write(tmp_path_factory.mktemp("review"), "review", _sample())


def test_the_latest_button_is_on_a_phones_screen(run, page):
    on = ("(() => { const j = document.querySelector('[data-k=\"talk-jump\"]'); if (!j || j.hidden) return null;"
          " const r = j.getBoundingClientRect(); return r.top >= 0 && r.bottom <= innerHeight; })()")
    got = run("engine", html=page, viewport=PHONE, clock=CLOCK, seed=_talk(), steps=[
        {"hash": "chat", "wait": 300},
        {"eval": "(window.scrollTo(0, 0), window.dispatchEvent(new Event('scroll')), 1)"},
        {"wait": 300, "eval": on}])
    assert not got["errors"], got["errors"]
    assert got["after"][2]["eval"] is True, got["after"][2]["eval"]


def test_on_a_phone_the_jobs_switch_is_whole_beside_the_search(run, tmp_path):
    m = copy.deepcopy(_sample())
    base = m["jobs"]["rows"][0]
    for i in range(12):
        r = dict(base, id="extra-%d" % i, rank=100 + i, status="new", draft=None, title="Data Analyst %d" % i)
        m["jobs"]["rows"].append(r)
    html = _write(tmp_path, "jobsphone", m)
    probe = ("(() => { const s = document.querySelector('#main .segctl'); const f = document.querySelector('#main .searchf');"
             " if (!s || !f) return {s: !!s, f: !!f}; const a = s.getBoundingClientRect(), b = f.getBoundingClientRect();"
             " return {s: true, f: true, whole: s.scrollWidth <= s.clientWidth + 1, apart: b.top >= a.bottom - 1}; })()")
    got = run("engine", html=html, viewport=PHONE, clock=CLOCK, steps=[{"hash": "jobs", "eval": probe}])
    assert not got["errors"], got["errors"]
    e = got["after"][0]["eval"]
    assert e.get("whole") and e.get("apart"), e


def test_not_confirmed_yet_is_a_small_pill(run, tmp_path):
    m = copy.deepcopy(_sample())
    m["upcoming"][1]["tentative"] = True
    html = _write(tmp_path, "tent", m)
    probe = ("[...document.querySelectorAll('#main .up-main > .state-word')].filter((e) => /Not confirmed/.test(e.textContent))"
             ".map((e) => e.getBoundingClientRect().width / e.parentElement.getBoundingClientRect().width)")
    got = run("engine", html=html, viewport=PHONE, clock=CLOCK, steps=[{"hash": "interviews", "eval": probe}])
    assert not got["errors"], got["errors"]
    ratios = got["after"][0]["eval"]
    assert ratios and all(r < 0.7 for r in ratios), ratios


def test_the_pencil_puts_the_cursor_in_its_box(run, page):
    got = run("engine", html=page, viewport=PHONE, clock=CLOCK, steps=[
        {"hash": "contacts", "open": "pen:msg-ash-1", "wait": 200,
         "eval": "(document.activeElement || {}).getAttribute ? document.activeElement.getAttribute('data-k') : null"}])
    assert not got["errors"], got["errors"]
    assert got["after"][0]["eval"] == "penask:msg-ash-1", got["after"][0]["eval"]


def test_a_downloaded_resume_is_named_for_its_reader(run, page):
    got = run("engine", html=page, viewport=WIDE, clock=CLOCK, steps=[
        # Get both files waits under its card's More: clicked as it is, wherever it sits.
        {"hash": "jobs", "eval": "(document.querySelector('[data-k=\"dl:app-ellerwick-insight\"]').click(), 1)"},
        {"wait": 800, "calls": "downloads"}])
    assert not got["errors"], got["errors"]
    names = [c["filename"] for c in got["after"][1]["calls"]]
    assert sorted(names) == ["Morgan_Ellis_CV_Ellerwick_Trust.pdf", "Morgan_Ellis_Cover_Letter_Ellerwick_Trust.pdf"], names
