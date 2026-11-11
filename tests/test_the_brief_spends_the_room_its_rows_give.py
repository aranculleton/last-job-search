"""A laptop's Brief spends the room each row gives its panels, at any window size and zoom.

The maintainer, 2026-11-07, on their laptop's Brief: every panel was as tall as its row, but its
content sat packed at the top with a big empty gap before its pills ("next 3 could definitely be
spaced better ... u see how its bunched at the top? be smart about this. same with the progress
one"), Jobs said "18 drafts ready to apply" over a list of eight new jobs, and "dynamic tho like i
dont want it to break based on screen size platform zoom etc.". So, on tall windows: no panel
leaves a hole of more than a step between what it shows and its pills, Next's steps and the rows
of a short list open out, Your progress's chart grows into its room with a cap, and Jobs says
what its list is. On the small windows, at 125% and 150% browser zoom (the window's own px get
fewer) and measured Safari's way, nothing scrolls or spills, and a phone scrolls as ever.
Every person and employer is invented (the sample's own, and "Employer 1" and the like).
"""
from __future__ import annotations

import copy
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import test_the_page_journeys as journeys  # noqa: E402
from test_the_brief_fits_a_laptop_and_its_foot_reads_as_one_line import FIT, PERSON_ZONE, T, _full  # noqa: E402
from test_the_page_journeys import PHONE  # noqa: E402
from test_the_page_works_in_a_browser import _write  # noqa: E402

TALL = [{"width": 1440, "height": 900}, {"width": 1920, "height": 1080}, {"width": 2560, "height": 1440}]
# The laptops the Brief fits, and the same windows at 125% and 150% browser zoom: a 1440 by 900
# window zoomed to 125% is 1152 by 720 of the page's own px, at 150% 960 by 600; a 1920 by 1080
# one at 150% is 1280 by 720.
SMALL = [{"width": 1000, "height": 560}, {"width": 1280, "height": 720}, {"width": 1440, "height": 900},
         {"width": 1152, "height": 720}, {"width": 960, "height": 600}, {"width": 1536, "height": 864}]
# The most a panel's content may sit above its pills, in the page's px: a step of 32 at the
# most, and the foot's own 16 (its 8px gap and 8px padding).
HOLE = 32 + 16
_ids = lambda s: "%dx%d" % (s["width"], s["height"])  # noqa: E731


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


def _many_drafts():
    """The maintainer's kind of day: eighteen drafts ready and eight new jobs, nothing else
    booked, nobody waiting, no "since your last brief"."""
    m = _full()
    m["upcoming"] = []
    base = m["ready"][0]
    m["ready"] = [dict(copy.deepcopy(base), id="app-d%d" % i, slug="d%d" % i, company="Employer %d" % (20 + i), role="Analyst %d" % i, rev="ad%d" % i)
                  for i in range(18)]
    row = next(r for r in m["jobs"]["rows"] if r["id"] == "r12-1")
    m["jobs"]["rows"] = [dict(copy.deepcopy(row), id="new-%d" % i, rank=i + 1, status="new", draft=None, title="Planning Analyst %d" % i,
                              company="Employer %d" % i, score=88 - i, rev="jn%d" % i) for i in range(8)]
    m["people"] = m["people"][:2]
    for s in m["brief"]["sections"]:
        if s["kind"] == "since":
            s["items"] = []
    return m


MODELS = {"sample": _full, "drafts": _many_drafts}

# Each panel with pills: how far its last content sits above them, in the page's px (the box as
# drawn, turned back by the page's own zoom so the bound reads the same at every text size).
HOLES = r"""(() => {
  const g = document.querySelector('#main .brief-grid');
  const z = parseFloat(document.body.style.zoom) || 1;
  const vis = (e) => e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden';
  const out = {};
  for (const p of [...g.children].filter(vis)) {
    const foot = p.querySelector(':scope > .bp-foot');
    const pills = foot ? [...foot.children].filter(vis) : [];
    if (!pills.length) continue;
    const kids = [...p.querySelectorAll(':scope > .bp-body *')].filter(vis);
    if (!kids.length) continue;
    const last = Math.max(...kids.map((x) => x.__drawnRect().bottom));
    const top = Math.min(...pills.map((x) => x.__drawnRect().top));
    out[p.getAttribute('data-k')] = Math.round((top - last) / z);
  }
  return out;
})()"""
READY = "!!document.querySelector('#main .brief-grid > .bpanel')"


@pytest.mark.parametrize("model", sorted(MODELS))
@pytest.mark.parametrize("size", TALL, ids=_ids)
def test_no_panel_leaves_a_hole_above_its_pills_on_a_tall_window(run, tmp_path, size, model):
    html = _write(tmp_path, model, MODELS[model]())
    got = run("engine", html=html, viewport=size, clock=T, timezoneId=PERSON_ZONE, fake={"canSend": "available"},
              steps=[{"hash": "brief", "ready": READY, "eval": HOLES}, {"eval": FIT}])
    assert not got["errors"], got["errors"]
    holes, fit = got["after"][0]["eval"], got["after"][1]["eval"]
    assert holes, "the Brief's panels were measured"
    assert all(v <= HOLE for v in holes.values()), ("content bunched at the top of its panel, a hole above its pills", size, model, holes)
    assert fit["scroll"] <= 1 and not fit["out"] and not fit["spill"], fit


STEPS = r"""(() => {
  const l = document.querySelector('[data-k="bp:next"] .bp-steps');
  const li = [...l.children].filter((x) => !x.hidden);
  const rs = li.map((x) => x.__drawnRect());
  const z = parseFloat(document.body.style.zoom) || 1;
  return {n: li.length, apart: Math.min(...rs.slice(1).map((r, i) => r.top - rs[i].bottom)) / z,
    boxed: li.every((x) => getComputedStyle(x).backgroundColor !== getComputedStyle(l).backgroundColor && parseFloat(getComputedStyle(x).paddingTop) >= 8)};
})()"""


def test_next_threes_steps_read_as_three_where_there_is_room(run, tmp_path):
    html = _write(tmp_path, "sample", _full())
    got = run("engine", html=html, viewport={"width": 1440, "height": 900}, clock=T, timezoneId=PERSON_ZONE, fake={"canSend": "available"},
              steps=[{"hash": "brief", "ready": READY, "eval": STEPS}])
    assert not got["errors"], got["errors"]
    r = got["after"][0]["eval"]
    # Three steps, each its own soft box as Coming up's rows are, apart by a step of the scale
    # (the 8px they had read as one block at the top of the panel).
    assert r["n"] == 3 and (r["boxed"] or r["apart"] >= 12), r
    assert r["apart"] <= 24 + 1, ("the steps were stretched apart past a sensible rhythm", r)


CHART = r"""(() => {
  const c = document.querySelector('[data-k="bp:numbers"] .bp-spark');
  const z = parseFloat(document.body.style.zoom) || 1;
  return {h: Math.round(c.__drawnRect().height / z), filled: document.querySelector('#main .brief-grid').classList.contains('is-filled')};
})()"""


@pytest.mark.parametrize("size", TALL, ids=_ids)
def test_your_progress_chart_grows_into_its_room_with_a_cap(run, tmp_path, size):
    # 1920 by 1080 and 2560 by 1440 are tall enough that the Brief is not stretched to the
    # window's foot: its chart sat at 48px over half a panel of nothing there.
    html = _write(tmp_path, "drafts", _many_drafts())
    got = run("engine", html=html, viewport=size, clock=T, timezoneId=PERSON_ZONE, fake={"canSend": "available"},
              steps=[{"hash": "brief", "ready": READY, "eval": CHART}])
    assert not got["errors"], got["errors"]
    r = got["after"][0]["eval"]
    assert 96 <= r["h"] <= 160 + 1, ("the chart did not take its panel's room, or ran past its cap", size, r)


JOBS = r"""(() => {
  const p = document.querySelector('[data-k="bp:jobs"]');
  const vis = (e) => !!e && e.getClientRects().length > 0;
  const nav = document.querySelector('[data-k="side:jobs"] .navcount');
  return {lead: p.querySelector('.bp-send').textContent, sub: vis(p.querySelector('.bp-sub')) ? p.querySelector('.bp-sub').textContent : null,
    all: [...p.querySelectorAll('.bp-foot a, .bp-foot button')].map((a) => a.textContent), nav: nav ? parseInt(nav.textContent, 10) : null};
})()"""


def test_jobs_says_what_its_list_is_under_the_drafts_line(run, tmp_path):
    html = _write(tmp_path, "drafts", _many_drafts())
    got = run("engine", html=html, viewport={"width": 1440, "height": 900}, clock=T, timezoneId=PERSON_ZONE, fake={"canSend": "available"},
              steps=[{"hash": "brief", "ready": READY, "eval": JOBS}])
    assert not got["errors"], got["errors"]
    r = got["after"][0]["eval"]
    # The drafts' line and the new jobs under it each say what they are, and the two add up to
    # the menu's count: "18 drafts ready to apply" over the list of new jobs read as its heading.
    assert r["lead"] == "18 drafts ready to apply" and r["sub"] == "New, best fit first", r
    assert "All 8 new" in r["all"] and r["nav"] == 18 + 8, r


@pytest.mark.parametrize("model", sorted(MODELS))
@pytest.mark.parametrize("safari", [False, True], ids=["as-drawn", "safari-measure"])
@pytest.mark.parametrize("size", SMALL, ids=_ids)
def test_nothing_scrolls_or_spills_on_a_small_or_zoomed_window(run, tmp_path, size, safari, model):
    html = _write(tmp_path, model, MODELS[model]())
    got = run("engine", html=html, viewport=size, clock=T, timezoneId=PERSON_ZONE, measureBeforeZoom=safari, fake={"canSend": "available"},
              steps=[{"hash": "brief", "ready": READY, "eval": FIT}])
    assert not got["errors"], got["errors"]
    r = got["after"][0]["eval"]
    assert r["scroll"] <= 1 and not r["out"] and not r["spill"], (size, model, r)
    # Next three keeps its three steps wherever it had them: the Jobs line under the drafts
    # is drawn only where there is room for it.
    nxt = [shown for key, shown, _n in r["lists"] if key == "bp:next"]
    assert nxt and nxt[0] >= (3 if size["height"] >= 600 else 2), r["lists"]


KEPT = r"""(() => {
  const g = document.querySelector('#main .brief-grid');
  const marks = [...g.querySelectorAll('[data-air], [data-gap]')].map((e) => (e.getAttribute('data-k') || e.className) + '=' + (e.getAttribute('data-air') || e.getAttribute('data-gap')));
  if (!window.__briefPanels) window.__briefPanels = [...g.children];
  return {marks, same: window.__briefPanels.every((p) => p.isConnected)};
})()"""


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_the_room_is_kept_across_a_redraw(run, tmp_path, scheme):
    # The minute's redraw draws the Brief afresh and compares it with the one on screen: the
    # room's marks are put on the fresh one first, so nothing is torn down and built again.
    html = _write(tmp_path, "sample", _full())
    got = run("engine", html=html, viewport={"width": 1440, "height": 900}, scheme=scheme, clock=T, timezoneId=PERSON_ZONE, fake={"canSend": "available"},
              steps=[{"hash": "brief", "ready": READY, "eval": KEPT}, {"tick": 61000, "eval": KEPT}])
    assert not got["errors"], got["errors"]
    before, after = got["after"][0]["eval"], got["after"][1]["eval"]
    assert before["marks"], "the tall window's panels took their room"
    assert after["marks"] == before["marks"] and after["same"], (before, after)


def test_a_phone_keeps_its_brief_as_it_was(run, tmp_path):
    html = _write(tmp_path, "sample", _full())
    got = run("engine", html=html, viewport=PHONE, clock=T, timezoneId=PERSON_ZONE, fake={"canSend": "available"},
              steps=[{"hash": "brief", "ready": READY,
                      "eval": "[document.documentElement.scrollHeight - innerHeight, document.querySelectorAll('#main [data-air], #main [data-gap]').length]"}])
    assert not got["errors"], got["errors"]
    scroll, marks = got["after"][0]["eval"]
    assert scroll > 200 and marks == 0, (scroll, marks)


WEEK = r"""(() => [...document.querySelectorAll('#main .bp-week > .bp-day')].filter((d) => d.getClientRects().length)
  .map((d) => Math.round(d.getBoundingClientRect().width)))()"""


@pytest.mark.parametrize("size", [{"width": 960, "height": 600}, {"width": 1000, "height": 560}, {"width": 1100, "height": 620},
                                  {"width": 1280, "height": 800}, {"width": 1440, "height": 900}], ids=_ids)
def test_coming_ups_week_gives_each_day_its_room(run, tmp_path, size):
    # At 960 wide the strip drew five days in five of fourteen columns, 13px each, their letters
    # and numbers run together ("SuMoTuWeTh"): the rules that show fewer days in a narrow panel
    # came before the strip's own fourteen columns in the stylesheet, and lost to them.
    html = _write(tmp_path, "sample", MODELS["sample"]())
    got = run("engine", html=html, viewport=size, clock=T, timezoneId=PERSON_ZONE, fake={"canSend": "available"},
              steps=[{"hash": "brief", "ready": READY, "eval": WEEK}])
    days = got["after"][0]["eval"]
    assert len(days) >= 5 and min(days) >= 26, (size, days)


NAMES = r"""(() => [...document.querySelectorAll('#main .bp-people .bp-who strong, #main .bp-people .bp-at')].filter((e) => e.getClientRects().length)
  .map((e) => [e.textContent, e.scrollWidth - e.clientWidth]))()"""


@pytest.mark.parametrize("size", [{"width": 960, "height": 600}, {"width": 1000, "height": 560}, {"width": 1100, "height": 620},
                                  {"width": 1280, "height": 800}, {"width": 1440, "height": 900}], ids=_ids)
def test_waiting_on_you_says_each_name_whole(run, tmp_path, size):
    # At 960 wide "Mari..." and "Ellerw..." stood beside "Thank-you note": the step kept its
    # width and the name gave way. In a narrow panel the step goes under the name.
    html = _write(tmp_path, "sample", MODELS["sample"]())
    got = run("engine", html=html, viewport=size, clock=T, timezoneId=PERSON_ZONE, fake={"canSend": "available"},
              steps=[{"hash": "brief", "ready": READY, "eval": NAMES}])
    names = got["after"][0]["eval"]
    assert names and all(cut <= 1 for _t, cut in names), (size, names)
