"""A probe, never merged: where the focus goes in Safari after a Coming up row's More."""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pytest  # noqa: E402

import test_the_page_journeys as journeys  # noqa: E402
from test_the_page_journeys import WIDE, _go  # noqa: E402
from test_words_undo_and_focus_stay_in_reach_in_sheets_and_menus import EVENT, T  # noqa: E402

AE = r"""(() => { const a = document.activeElement; const d = document.querySelector('details[data-k="det:up-more:%s"]');
 const items = d ? [...d.querySelectorAll('.menu-panel button')].map((b) => b.getAttribute('data-k')) : [];
 return {ae: a ? (a.tagName + ' ' + (a.getAttribute('data-k') || a.className || '')) : null,
  open: d ? d.open : 'no details', dialogs: [...document.querySelectorAll('dialog[open]')].map((x) => x.className),
  sumFocusable: d ? (d.firstElementChild.tabIndex) : null, items}; })()""" % EVENT


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


def test_probe(run, tmp_path):
    got = _go(run, tmp_path, [
        {"hash": "interviews", "eval": AE},
        {"open": "up-more:" + EVENT, "eval": AE},
        {"press": ["Tab"], "eval": AE},
        {"press": ["Tab"], "eval": AE},
        {"press": ["Enter"], "eval": AE},
    ], WIDE, clock=T)
    raise AssertionError(json.dumps([s.get("eval") for s in got["after"]]))
