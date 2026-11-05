"""A sheet's foot, the row with Cancel, never covers its choices (the maintainer's iPhone,
2026-11-04).

The Brief's "Add something" sheet drew its second choice ("Something else: a call, a test, a
careers fair") half hidden behind the foot holding Cancel, with empty space under Cancel. The
foot sits in the sheet's padding and sticks to its bottom edge so a long list keeps Cancel in
reach; stuck at bottom 0, it was lifted out of its place by that padding even when everything
fitted. Every person and employer is invented (tests/fixtures/app_model_sample.json).
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import test_the_page_journeys as journeys  # noqa: E402
from test_the_page_journeys import PHONE, WIDE, _go  # noqa: E402


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


# Each choice measured against the foot and the sheet's own bottom edge, as drawn.
MEASURE = r"""(() => {
  const d = document.querySelector('dialog.sheet[open]');
  if (!d) return null;
  const box = (e) => e.getBoundingClientRect();
  const foot = box(d.querySelector('.sheet-actions')), sheet = box(d);
  return {choices: [...d.querySelectorAll('.choice-btn')].map((b) => ({name: b.textContent.trim(), bottom: box(b).bottom})),
    footTop: foot.top, footBottom: foot.bottom, sheetBottom: sheet.bottom, scrolls: d.scrollHeight > d.clientHeight + 1};
})()"""


@pytest.mark.parametrize("vp", [PHONE, WIDE], ids=["phone", "wide"])
def test_every_choice_in_add_something_shows_whole_above_the_foot(run, tmp_path, vp):
    got = _go(run, tmp_path, [{"hash": "brief", "open": "bp-up-add", "eval": MEASURE}], vp, clock="2026-10-25T09:00:00.000Z")
    m = got["after"][0]["eval"]
    assert m and [c["name"] for c in m["choices"]] == ["An interview", "Something else: a call, a test, a careers fair"], m
    assert not m["scrolls"], ("two choices fit: nothing to scroll", m)
    for c in m["choices"]:
        assert c["bottom"] <= m["footTop"], ("the foot with Cancel covers a choice", c, m)
    # The foot stands at the sheet's own foot, with no empty band under Cancel.
    assert m["sheetBottom"] - m["footBottom"] <= 2, m


# Every sheet of four or more choices (the bins), at the laptop sizes the maintainer's page
# was drawn at (2026-11-05: the fourth choice of "Not Wren?" cut in half by the foot's line,
# dark, on a laptop) and a phone: all fit above the foot, or the list scrolls with a fade
# saying so and, scrolled to its end, its last choice whole above the foot. Cancel is a
# soft pill, never underlined text (DESIGN.md, "Buttons, links and taps").
BINS = [("todo", "Not Wren at Fernhill Freight?"), ("jobs", "Not for me: Harbourline Bank, Pricing Analyst"),
        ("drafts", "Not sending: Quayside Foods, Demand Planning Analyst")]
SIZES = [{"width": 1000, "height": 630}, {"width": 1280, "height": 700}, PHONE, {"width": 1000, "height": 420}, {"width": 375, "height": 520}]
SCROLLED = r"""(() => {
  const d = document.querySelector('dialog.sheet[open]');
  if (!d) return null;
  const fade = d.classList.contains('more-below');
  d.scrollTop = d.scrollHeight;
  d.dispatchEvent(new Event('scroll'));
  const box = (e) => e.getBoundingClientRect();
  const c = getComputedStyle(d.querySelector('[data-k="sheet-cancel"]'));
  return {fadeAtTop: fade, fadeAtEnd: d.classList.contains('more-below'), lastBottom: box([...d.querySelectorAll('.choice-btn')].pop()).bottom,
    footTop: box(d.querySelector('.sheet-actions')).top, n: d.querySelectorAll('.choice-btn').length,
    cancel: {line: c.textDecorationLine, radius: parseFloat(c.borderTopLeftRadius), bg: c.backgroundColor}};
})()"""


@pytest.mark.parametrize("vp", SIZES, ids=["1000x630", "1280x700", "phone", "1000x420", "375x520"])
@pytest.mark.parametrize("where,label", BINS, ids=["person", "job", "draft"])
def test_a_bins_choices_are_whole_above_its_foot_or_scroll_clear_of_it_with_a_fade(run, tmp_path, vp, where, label):
    got = _go(run, tmp_path, [{"hash": where, "click": label, "exact": True, "eval": MEASURE}, {"eval": SCROLLED}], vp,
              clock="2026-10-25T09:00:00.000Z")
    m, s = got["after"][0]["eval"], got["after"][1]["eval"]
    assert m and s and s["n"] >= 4, (m, s)
    if not m["scrolls"]:
        for c in m["choices"]:
            assert c["bottom"] <= m["footTop"] + 0.5, ("the foot covers a choice that fits", c, m)
        assert not s["fadeAtTop"], ("nothing more to scroll to: no fade", s)
    else:
        assert s["fadeAtTop"] and not s["fadeAtEnd"], ("a fade says there is more, and goes at the end", s)
    assert s["lastBottom"] <= s["footTop"] + 0.5, ("scrolled to its end, the last choice stands whole above the foot", s)
    assert s["cancel"]["line"] == "none" and s["cancel"]["radius"] >= 12 and s["cancel"]["bg"] not in ("rgba(0, 0, 0, 0)", "transparent"), s
