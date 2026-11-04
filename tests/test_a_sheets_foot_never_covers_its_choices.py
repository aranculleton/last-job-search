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
