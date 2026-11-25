"""A table in an interview prep reads as a table, on a phone as on a wide screen (issue 368).

A prep holding an ordinary Markdown table (a header row, its "|---|" line, then rows) showed on
the page as raw lines of pipes: the engine reads the prep's parts line by line, and the page drew
each line as a bullet. The page now draws such a run of lines as a table with its cells, and on a
phone each row is stacked, every cell under its column's name, so nothing runs past the screen.

On the sample page (an invented search, every person and employer invented).
"""
from __future__ import annotations

import copy
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))

from test_the_page_journeys import PHONE, WIDE, _go, _sample, browser  # noqa: E402

IV = "int-larkspur-supply"
ADDR = "interviews/prep~" + IV + "/open"
CLOCK = "2026-10-27T09:00:00Z"
ROWS = ["| Story | Its home | Backup use |", "|---|---|---|",
        "| The bank holiday forecast | A forecast that was wrong | What you are proudest of |",
        "| The one-page regional plan | Explaining a model | |"]


@pytest.fixture(scope="module")
def run():
    yield from browser()


@pytest.fixture(params=[PHONE, WIDE], ids=["phone", "wide"])
def vp(request):
    return request.param


def _model(how):
    m = copy.deepcopy(_sample())
    for iv in m["interviews"]:
        if iv["id"] != IV:
            continue
        if how == "read":
            iv["prep_read"]["sections"].insert(0, {"key": "story_homes", "title": "Story homes",
                                                   "items": [{"text": t, "link": "", "sub": []} for t in ROWS] + [{"text": "Use each story once.", "link": "", "sub": []}]})
        else:
            iv.pop("round", None)
            iv["prep_read"] = None
            iv["one_screen"] = None
            iv["prep_text"] = "# Prep\n\n## Story homes\n\n" + "\n".join(ROWS) + "\n\nUse each story once.\n\n## Likely questions\n\n### Why us?\n\nThe store-level work.\n"
    return m


TABLE = ("(() => { const t = document.querySelector('dialog .prep-table'); if (!t) return null;"
         " const td = t.querySelector('tbody td'); const th = t.querySelector('thead');"
         " const b = document.querySelector('dialog .detail-body');"
         " return {head: [...t.querySelectorAll('thead th')].map((x) => x.textContent),"
         " rows: [...t.querySelectorAll('tbody tr')].map((r) => [...r.querySelectorAll('td')].map((x) => x.textContent)),"
         " stacked: getComputedStyle(td).display === 'block' && getComputedStyle(th).display === 'none',"
         " label: getComputedStyle(td, '::before').content,"
         " text: document.querySelector('dialog.detail').innerText, scroll: b.scrollWidth - b.clientWidth}; })()")


@pytest.mark.parametrize("how", ["read", "text"])
def test_a_markdown_table_in_a_prep_is_a_table(run, tmp_path, vp, how):
    got = _go(run, tmp_path, [{"hash": ADDR, "read": "dialog.detail", "eval": TABLE}], vp, model=_model(how), clock=CLOCK)
    t = got["after"][0]["eval"]
    assert t, "a table is drawn"
    assert t["head"] == ["Story", "Its home", "Backup use"], t["head"]
    assert t["rows"] == [["The bank holiday forecast", "A forecast that was wrong", "What you are proudest of"],
                         ["The one-page regional plan", "Explaining a model", ""]], t["rows"]
    assert "|---|" not in t["text"] and "| Story |" not in t["text"]
    assert "Use each story once." in t["text"]
    if vp is PHONE:
        assert t["stacked"] and "Story" in t["label"], t
    else:
        assert not t["stacked"], t
    assert t["scroll"] <= 0, "nothing wider than the screen"
