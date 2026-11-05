"""A laptop's Brief is one screen, and the privacy line at its foot reads as one tidy line.

The maintainer, 2026-11-05: at about 1000 by 560 a full Brief (Today, Coming up, Next, Waiting
on you, Jobs, News with three points, the numbers and a tip) still scrolled, and "Private to
you. Hide" opened a narrow block of two lines inside a wide empty strip. So on 1000 by 560,
1280 by 720 and 1440 by 900: the page does not scroll, every panel is inside the window, each
panel's own content stays inside it (nothing cut off, a list holding more says so), and the
privacy line opened is one paragraph across the column. A phone still scrolls.
Every person and employer is invented (the sample's own).
"""
from __future__ import annotations

import copy
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import test_the_page_journeys as journeys  # noqa: E402
from test_the_page_journeys import PHONE, _go, _sample  # noqa: E402

T = "2026-10-25T09:00:00.000Z"
LAPTOPS = [{"width": 1000, "height": 560}, {"width": 1280, "height": 720}, {"width": 1440, "height": 900}]


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


def _full():
    """The sample with a full Brief: three news points and a tip line."""
    m = copy.deepcopy(_sample())
    for s in m["brief"]["sections"]:
        if s["kind"] == "news":
            s["items"] = [
                {"what": "The central bank held its rate at 4% this week.", "use": "Planning teams expect steadier demand",
                 "src": "The bank", "url": "https://example.com/rates", "date": "2026-10-23"},
                {"what": "Two large grocers announced new distribution centres near the city.", "use": "Demand planning roles there may grow",
                 "src": "A trade report", "url": "https://example.com/report", "date": "2026-10-22"},
                {"what": "A regional freight firm is opening a planning office in the city centre.", "use": "Worth a note to anyone you know there",
                 "src": "Local business news", "url": "https://example.com/freight", "date": "2026-10-21"}]
    return m


FIT = r"""(() => {
  const g = document.querySelector('#main .brief-grid');
  const panels = [...g.children].filter((p) => p.getClientRects().length);
  const vh = innerHeight;
  // A panel's own content past its edge would be cut off: its body and foot stay inside it.
  const spill = panels.filter((p) => { const r = p.getBoundingClientRect();
    return [...p.querySelectorAll(':scope > .bp-body > *, :scope > .bp-foot')].some((c) => c.getClientRects().length && c.getBoundingClientRect().bottom > r.bottom + 1); })
    .map((p) => p.getAttribute('data-k'));
  const out = panels.filter((p) => p.getBoundingClientRect().bottom > vh + 1).map((p) => p.getAttribute('data-k'));
  const tip = document.querySelector('#main .bp-tip');
  const priv = [...document.querySelectorAll('.foot-line')].filter((e) => e.getClientRects().length);
  const lists = [...g.querySelectorAll('[data-fit]')].map((l) => [l.closest('.bpanel').getAttribute('data-k'), [...l.children].filter((x) => !x.hidden).length, l.children.length]);
  const more = [...g.querySelectorAll('[data-fit-more]')].filter((b) => !b.hidden).map((b) => b.textContent);
  return {scroll: document.documentElement.scrollHeight - vh, out, spill, panels: panels.length,
    tip: tip ? tip.getBoundingClientRect().bottom <= vh + 1 : null, priv: priv.map((e) => e.getBoundingClientRect().bottom <= vh + 1),
    lists, more};
})()"""


@pytest.mark.parametrize("size", LAPTOPS, ids=lambda s: "%dx%d" % (s["width"], s["height"]))
def test_a_full_brief_fits_a_laptop_window_without_scrolling(run, tmp_path, size):
    got = _go(run, tmp_path, [{"hash": "brief", "eval": FIT}], size, model=_full(), clock=T)
    r = got["after"][0]["eval"]
    assert r["scroll"] <= 1, ("the Brief scrolls on a laptop", size, r)
    assert not r["out"] and not r["spill"], r
    assert r["panels"] >= 6 and r["tip"] is True and r["priv"] == [True], r
    # Every list shows at least one, and News, with no screen of its own, says what it holds
    # past the window ("2 more") rather than dropping it.
    assert all(shown >= 1 or key == "bp:today" for key, shown, _n in r["lists"]), r["lists"]
    news = [(shown, n) for key, shown, n in r["lists"] if key == "bp:news"]
    assert news and (news[0][0] == news[0][1] or r["more"] == ["%d more" % (news[0][1] - news[0][0])]), (news, r["more"])


def test_news_more_opens_the_rest_in_place(run, tmp_path):
    size = LAPTOPS[0]
    look = "(() => [...document.querySelectorAll('#main .bp-news > li')].filter((l) => !l.hidden).length)()"
    got = _go(run, tmp_path, [{"hash": "brief", "eval": look},
                              {"eval": "(() => { const b = document.querySelector('[data-fit-more]'); if (b && !b.hidden) b.click(); return 1; })()"},
                              {"eval": look}], size, model=_full(), clock=T)
    before, after = got["after"][0]["eval"], got["after"][2]["eval"]
    assert after == 3 and before <= 3, (before, after)


def test_a_phone_still_scrolls_its_brief(run, tmp_path):
    got = _go(run, tmp_path, [{"hash": "brief", "eval": "document.documentElement.scrollHeight - innerHeight"}], PHONE, model=_full(), clock=T)
    assert got["after"][0]["eval"] > 200


FOOT = r"""(() => {
  const b = document.querySelector('[data-k="foot-details"]');
  if (b && b.getAttribute('aria-expanded') !== 'true') b.click();
  return 1;
})()"""
FOOT_READ = r"""(() => {
  const lines = [...document.querySelectorAll('.foot-line')].filter((e) => e.getClientRects().length);
  const p = lines[0];
  const col = document.querySelector('#main > .sec').getBoundingClientRect();
  const r = p.getBoundingClientRect();
  const lh = parseFloat(getComputedStyle(p).lineHeight) || 20;
  const z = parseFloat(document.body.style.zoom) || 1;
  // Where the paragraph's text ends on the right: a narrow block in a wide strip ends far short.
  const range = document.createRange(); range.selectNodeContents(p);
  const rights = [...range.getClientRects()].map((x) => x.right);
  const said = [...document.querySelectorAll('p')].filter((e) => e.getClientRects().length && e.textContent.includes('Only you can open'));
  return {n: lines.length, paragraphs: said.length, same: said[0] === p, text: p.textContent,
    lines: Math.round(r.height / (lh * z)), reach: (Math.max(...rights) - r.left) / (col.width), hide: !!p.querySelector('[data-k="foot-details"]')};
})()"""


@pytest.mark.parametrize("size", [{"width": 1000, "height": 560}, {"width": 1440, "height": 900}], ids=["1000", "1440"])
@pytest.mark.parametrize("screen", ["todo", "brief"])
def test_the_privacy_details_read_as_one_paragraph_across_the_column(run, tmp_path, size, screen):
    got = _go(run, tmp_path, [{"hash": screen, "eval": FOOT}, {"eval": FOOT_READ}], size, clock=T)
    r = got["after"][1]["eval"]
    assert r["n"] == 1 and "Private to you." in r["text"] and "Only you can open this page" in r["text"] and r["hide"], r
    # One paragraph: the words follow "Private to you." on its line, Hide at their end, and a
    # wrapped one reaches across the column rather than stopping at 70 characters.
    assert r["paragraphs"] == 1 and r["same"], r
    assert r["lines"] == 1 or r["reach"] > 0.7, r   # the Brief keeps the Chat button's room at its right
    if size["width"] == 1440 and screen == "todo":
        assert r["lines"] == 1, r
