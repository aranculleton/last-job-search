"""The Brief's panels use their room, and its numbers open where those things are.

The maintainer, 2026-11-06, on their own Brief: News was "too much of a wall of text, maybe 3
bullets max" (it showed up to five, whatever Edit the brief's News items said, and a point
written "<what>. Use it: <how>. [source](...)" was one long paragraph); Jobs listed five over
half a panel of empty space ("list a couple more, but dont cramp them"); Your progress's chart
sat short over empty space ("are the panels actually dynamic and filling the room"); and its
numbers opened nothing ("applied went to jobs page applied, contacts went to contacts,
interviews went to interviews part of coming up").
Every person and employer is invented (the sample's own).
"""
from __future__ import annotations

import copy
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import pytest  # noqa: E402

import test_the_page_journeys as journeys  # noqa: E402
from test_the_brief_fits_a_laptop_and_its_foot_reads_as_one_line import PERSON_ZONE, T, _full  # noqa: E402
from test_the_page_journeys import _go, _sample  # noqa: E402

WIDE = {"width": 1440, "height": 900}


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


def _five_news():
    m = _full()
    for s in m["brief"]["sections"]:
        if s["kind"] == "news":
            s["items"] = s["items"] + [dict(s["items"][0], what="A fourth point about a planning team.", url="https://example.com/4"),
                                       dict(s["items"][0], what="A fifth point about a freight firm.", url="https://example.com/5")]
    return m


NEWS = "[...document.querySelectorAll('#main .bp-news > li')].length"


def test_news_shows_three_points_unless_the_person_chose_more(run, tmp_path):
    got = _go(run, tmp_path, [{"hash": "brief", "eval": NEWS}], WIDE, model=_five_news(), clock=T, zone=PERSON_ZONE)
    assert got["after"][0]["eval"] == 3
    m = _five_news()
    m["brief"]["news_max"] = 5
    got = _go(run, tmp_path, [{"hash": "brief", "eval": NEWS}], WIDE, model=m, clock=T, zone=PERSON_ZONE)
    assert got["after"][0]["eval"] == 5


def test_a_use_it_point_is_set_apart_from_what_happened():
    import app_model
    got = app_model.news_parts("Kestrel Mutual says a fifth of its return now comes from pricing models. "
                               "Use it: your pricing work is the story to lead with there. [source](https://example.com/k)")
    assert got["what"] == "Kestrel Mutual says a fifth of its return now comes from pricing models."
    assert got["use"] == "Your pricing work is the story to lead with there."
    assert got["url"] == "https://example.com/k" and got["src"] == ""


def test_the_jobs_panel_lists_more_where_it_has_room(run, tmp_path):
    m = _full()
    base = next(r for r in m["jobs"]["rows"] if r.get("status") in ("new", None) and not r.get("draft"))
    for i in range(10):
        m["jobs"]["rows"].append(dict(base, id="extra-%d" % i, rank=100 + i, status="new", draft=None, title="Planning Analyst %d" % i, score=70 - i))
    look = ("(() => { const l = document.querySelector('[data-k=\"bp:jobs\"] [data-fit]');"
            " return {shown: [...l.children].filter((x) => !x.hidden).length, all: [...document.querySelectorAll('[data-k=\"bp:jobs\"] a.navlink')].map((a) => a.textContent)}; })()")
    got = _go(run, tmp_path, [{"hash": "brief", "eval": look}], WIDE, model=m, clock=T, zone=PERSON_ZONE)
    r = got["after"][0]["eval"]
    assert r["shown"] > 5, r
    assert any(t.startswith("All ") for t in r["all"]), r


TILES = "[...document.querySelectorAll('#main .bp-stats > .bp-stat')].map((t) => [t.tagName, t.getAttribute('data-k')])"


def test_each_number_opens_where_those_things_are(run, tmp_path):
    m = copy.deepcopy(_sample())
    counts = (m["done"].get("recent") or {}).get("counts") or m["done"].setdefault("counts", {})
    counts.update({"applied": 12, "replies": 4, "interviews": 2, "offers": 0})
    where = "[location.hash, document.querySelector('#main .seg-btn[aria-pressed=\"true\"], #main [aria-checked=\"true\"][data-k^=\"seg\"]') ? 1 : 0, localStorage.getItem('ljs:jobs:tab') || '', localStorage.getItem('ljs:up:view') || '']"
    got = _go(run, tmp_path, [{"hash": "brief", "eval": TILES},
                              {"eval": "(document.querySelector('[data-k=\"bp-stat:applied\"]').click(), 1)", "wait": 300},
                              {"eval": "location.hash"},
                              {"hash": "brief", "eval": "(document.querySelector('[data-k=\"bp-stat:interviews\"]').click(), 1)", "wait": 300},
                              {"eval": "location.hash"},
                              {"hash": "brief", "eval": "(document.querySelector('[data-k=\"bp-stat:replies\"]').click(), 1)", "wait": 300},
                              {"eval": "location.hash"}], WIDE, model=m, clock=T, zone=PERSON_ZONE)
    tiles = dict((k, tag) for tag, k in got["after"][0]["eval"])
    assert tiles.get("bp-stat:applied") == "A" and tiles.get("bp-stat:interviews") == "A" and tiles.get("bp-stat:replies") == "A", tiles
    assert None in tiles and tiles[None] == "DIV", ("a nought opens nothing", tiles)
    assert got["after"][2]["eval"].startswith("#jobs"), got["after"][2]["eval"]
    assert got["after"][4]["eval"].startswith("#interviews"), got["after"][4]["eval"]
    assert got["after"][6]["eval"].startswith("#contacts"), got["after"][6]["eval"]
    del where


def test_applied_opens_jobs_on_its_applied_tab(run, tmp_path):
    m = copy.deepcopy(_sample())
    counts = (m["done"].get("recent") or {}).get("counts") or m["done"].setdefault("counts", {})
    counts.update({"applied": 12})
    tab = "(() => { const b = [...document.querySelectorAll('#main [role=\"tab\"], #main .segctl button')].find((x) => x.getAttribute('aria-selected') === 'true' || x.getAttribute('aria-pressed') === 'true' || x.getAttribute('aria-checked') === 'true'); return b ? b.textContent : null; })()"
    got = _go(run, tmp_path, [{"hash": "brief", "eval": "(document.querySelector('[data-k=\"bp-stat:applied\"]').click(), 1)", "wait": 300},
                              {"eval": tab}], WIDE, model=m, clock=T, zone=PERSON_ZONE)
    assert "Applied" in (got["after"][1]["eval"] or ""), got["after"][1]["eval"]


def test_a_filled_brief_gives_progress_its_room(run, tmp_path):
    look = ("(() => { const p = document.querySelector('[data-k=\"bp:numbers\"]'); const c = p.querySelector('.bp-spark');"
            " const kids = [...p.querySelectorAll('.bp-body *')].filter((x) => x.getClientRects().length);"
            " const last = Math.max(...kids.map((x) => x.getBoundingClientRect().bottom));"
            " return {chart: Math.round(c.getBoundingClientRect().height), empty: Math.round(p.getBoundingClientRect().bottom - last),"
            " filled: document.querySelector('#main .brief-grid').classList.contains('is-filled')}; })()")
    got = _go(run, tmp_path, [{"hash": "brief", "eval": look}], WIDE, model=_full(), clock=T, zone=PERSON_ZONE)
    r = got["after"][0]["eval"]
    assert r["filled"] and r["empty"] <= 40, ("Your progress has empty room under its chart", r)
