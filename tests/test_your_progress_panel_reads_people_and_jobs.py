"""The Brief's Your progress draws the engine's glance: people and jobs, one line, two series.

The maintainer, 2026-11-10: "both jobs and people, not just jobs ... dont overwhelm but also
make it pretty, useful, and not make it look like im doing nothing". The engine chooses the
tiles and the line (app_model._glance, tested in test_your_progress_counts_people_and_jobs.py);
the page draws exactly those, the weeks as applications and messages sent in the two chart
colours, said in the line under them, and the panel still fits a laptop's Brief without
scrolling (the fit tests' own check), on a phone too, in light and dark. Progress, which the
numbers open, says the same. Every person and employer is invented (the sample's own).
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import test_the_page_journeys as journeys  # noqa: E402
from test_the_brief_fits_a_laptop_and_its_foot_reads_as_one_line import FIT, PERSON_ZONE, T, _full  # noqa: E402
from test_the_page_journeys import PHONE  # noqa: E402
from test_the_page_works_in_a_browser import _write  # noqa: E402

READY = "!!document.querySelector('#main .brief-grid > .bpanel')"
WORKING = "Recruiters answer most: 6 of 12 first notes; everyone else 3 of 28."
SMALL = [{"width": 1000, "height": 560}, {"width": 1280, "height": 720}, {"width": 1440, "height": 900},
         {"width": 960, "height": 600}]
_ids = lambda s: "%dx%d" % (s["width"], s["height"])  # noqa: E731


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


def _this_week(m, n=5):
    # Five sent this week: the sample's own newest week holds none since the screen review of
    # 2026-11-11 (row 40), its weeks counted from the applications it lists, not 24 over 14.
    m["done"]["weeks"][-1]["applied"] = n
    return m


def _networker():
    """Someone writing to many people and applying a little: four tiles, a line, two series."""
    m = _this_week(_full())
    d = m["done"]
    for i, w in enumerate(d["weeks"]):
        w["sent"] = [0, 3, 8, 12, 6, 14, 9, 11][i % 8]
    d["recent"] = {"days": 30, "counts": {"applied": 2, "interviews": 0, "offers": 0, "replies": 9, "sent": 40},
                   "funnel": [{"stage": "applied", "n": 2}, {"stage": "interview", "n": 0}, {"stage": "offer", "n": 0}]}
    d["counts"]["sent"] = 52
    d["glance"] = {"days": 30, "working": WORKING, "tiles": [
        {"k": "applied", "n": 2, "label": "applied", "short": "applied", "side": "jobs", "share": None},
        {"k": "sent", "n": 40, "label": "messages sent", "short": "messages sent", "side": "people", "share": None},
        {"k": "replies", "n": 9, "label": "people replied", "short": "replied", "side": "people", "share": "22% answered"},
        {"k": "calls", "n": 1, "label": "call", "short": "call", "side": "people", "share": None}]}
    return m


def _applier():
    """Someone applying a lot and writing to nobody: the chart is applications alone."""
    m = _this_week(_full())
    d = m["done"]
    for w in d["weeks"]:
        w["sent"] = 0
    d["glance"] = {"days": 30, "working": None, "tiles": [
        {"k": "applied", "n": 30, "label": "applied", "short": "applied", "side": "jobs", "share": None},
        {"k": "interviews", "n": 2, "label": "interviews", "short": "interviews", "side": "jobs", "share": "7% of applied"}]}
    return m


PANEL = r"""(() => {
  const p = document.querySelector('[data-k="bp:numbers"]');
  const vis = (e) => !!e && e.getClientRects().length > 0;
  const tiles = [...p.querySelectorAll('.bp-stats > .bp-stat')].map((t) => [t.getAttribute('data-k'), t.querySelector('.bp-n').textContent, t.querySelector('.bp-l').textContent]);
  const bars = (c) => [...p.querySelectorAll('.bp-spark .bp-bar.' + c)];
  const bg = (e) => e ? getComputedStyle(e).backgroundColor : null;
  const firstOn = (c) => bars(c).find((b) => !b.classList.contains('is-zero'));
  const w = p.querySelector('.bp-working');
  return {tiles, working: vis(w) ? w.textContent : null, applied: bars('is-applied').length, sent: bars('is-sent').length,
    cap: p.querySelector('.bp-spark-cap') ? p.querySelector('.bp-spark-cap').textContent : null,
    swatches: [...p.querySelectorAll('.bp-spark-cap .bp-sw')].map((s) => [s.getAttribute('data-k'), bg(s)]),
    colours: {applied: bg(firstOn('is-applied')), sent: bg(firstOn('is-sent')), panel: bg(p)},
    xscroll: document.documentElement.scrollWidth - innerWidth,
    inside: [...p.querySelectorAll('.bp-stat, .bp-spark')].every((e) => e.getBoundingClientRect().right <= p.getBoundingClientRect().right + 1)};
})()"""


def _lum(css):
    import re
    r, g, b = (int(x) / 255 for x in re.findall(r"\d+", css)[:3])
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4  # noqa: E731
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def _contrast(a, b):
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _look(run, tmp_path, model, size, scheme="light", name="m"):
    html = _write(tmp_path, name, model)
    got = run("engine", html=html, viewport=size, scheme=scheme, clock=T, timezoneId=PERSON_ZONE, fake={"canSend": "available"},
              steps=[{"hash": "brief", "ready": READY, "eval": PANEL}, {"eval": FIT}])
    assert not got["errors"], got["errors"]
    return got["after"][0]["eval"], got["after"][1]["eval"]


@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("size", [{"width": 1440, "height": 900}, PHONE], ids=["wide", "phone"])
def test_the_panel_draws_the_engines_tiles_line_and_two_series(run, tmp_path, size, scheme):
    r, _fit = _look(run, tmp_path, _networker(), size, scheme)
    assert [t[0] for t in r["tiles"]] == ["bp-stat:applied", "bp-stat:sent", "bp-stat:replies", "bp-stat:calls"], r["tiles"]
    # This week's own work leads the engine's tiles since the review of 2026-11-11 (U-7): the
    # same two kinds (applied, messages sent), counted for this week, then how it went.
    assert [t[1:] for t in r["tiles"]] == [["5", "applied this week"], ["11", "messages sent this week"], ["9", "people replied"], ["1", "call"]], [t[1:] for t in r["tiles"]]
    assert r["working"] == WORKING
    # Applications and messages sent each week, side by side, said in the line with a swatch each.
    assert r["applied"] == 8 and r["sent"] == 8, r
    assert r["cap"].startswith("Applications and messages sent each week"), r["cap"]
    assert [s[0] for s in r["swatches"]] == ["spark-sw:applied", "spark-sw:sent"]
    assert r["swatches"][0][1] == r["colours"]["applied"] and r["swatches"][1][1] == r["colours"]["sent"], r
    # Two colours a person can tell apart, each 3:1 against the panel in this look.
    assert r["colours"]["applied"] != r["colours"]["sent"]
    for k in ("applied", "sent"):
        assert _contrast(r["colours"][k], r["colours"]["panel"]) >= 3.0, (scheme, k, r["colours"])
    assert r["inside"] and r["xscroll"] <= 0, r


def test_someone_who_only_applies_sees_one_series_and_no_nought(run, tmp_path):
    r, _fit = _look(run, tmp_path, _applier(), {"width": 1440, "height": 900})
    # This week's applications lead since the review of 2026-11-11 (U-7); a week with none
    # would leave the engine's own tile, never a nought.
    assert [t[1:] for t in r["tiles"]] == [["5", "applied this week"], ["2", "interviews"]], r["tiles"]
    assert r["sent"] == 0 and r["applied"] == 8, r
    assert r["cap"].startswith("Applications each week"), r["cap"]
    assert r["working"] is None


@pytest.mark.parametrize("size", SMALL, ids=_ids)
def test_the_fuller_panel_still_fits_a_laptops_brief(run, tmp_path, size):
    _r, fit = _look(run, tmp_path, _networker(), size)
    assert fit["scroll"] <= 1 and not fit["out"] and not fit["spill"], (size, fit)


def test_a_short_window_says_the_glance_in_one_line(run, tmp_path):
    html = _write(tmp_path, "short", _networker())
    got = run("engine", html=html, viewport={"width": 1000, "height": 560}, clock=T, timezoneId=PERSON_ZONE, fake={"canSend": "available"},
              steps=[{"hash": "brief", "ready": READY, "eval": "(() => { const e = document.querySelector('#main .bp-head-numbers'); return e ? e.textContent : null; })()"}])
    assert not got["errors"], got["errors"]
    # This week's own work first since the review of 2026-11-11 (U-7).
    assert got["after"][0]["eval"].startswith("5 this week · 11 sent · 9 replied · 1 call"), got["after"][0]["eval"]


def test_progress_says_the_same_as_the_panel(run, tmp_path):
    html = _write(tmp_path, "progress", _networker())
    look = ("(() => { const s = document.querySelector('#main .sec'); return {sum: s.querySelector('.summary, .screen-sum, p').textContent,"
            " text: s.textContent, legend: [...s.querySelectorAll('.legend')].map((l) => l.textContent)}; })()")
    got = run("engine", html=html, viewport={"width": 1440, "height": 900}, clock=T, timezoneId=PERSON_ZONE, fake={"canSend": "available"},
              steps=[{"hash": "progress", "ready": "!!document.querySelector('#main .sec')", "eval": look}])
    assert not got["errors"], got["errors"]
    r = got["after"][0]["eval"]
    assert "40 messages sent" in r["text"] and WORKING in r["text"], r["text"][:400]
    assert r["legend"] and "Messages sent" in r["legend"][0], r["legend"]


def test_a_model_from_before_the_glance_draws_its_four_numbers(run, tmp_path):
    m = _this_week(_full())
    m["done"].pop("glance", None)
    r, _fit = _look(run, tmp_path, m, {"width": 1440, "height": 900}, name="old")
    # This week's applications first since the review of 2026-11-11 (U-7), then the rest.
    assert [t[2] for t in r["tiles"]][:1] == ["applied this week"] and len(r["tiles"]) == 4, r["tiles"]


