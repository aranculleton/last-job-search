"""A checklist card in To do says its count once, in its title.

The screen review of 2026-11-11 (row 28): the pill "7 to send" stood over the title "Messages
to send (7)", the same number twice in two lines. The title keeps its count (Contacts says
"N to send" the same way, DESIGN.md); the pill says only what the title cannot: how many are
overdue, where any are, and once one is done, how far the card has gone ("1 of 7 done"). The
quick answers' "1 of 4" over "4 quick answers" stays: it says which question you are on.
Every person and employer is the sample's, invented.
"""
from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest  # noqa: E402

import test_the_page_journeys as journeys  # noqa: E402
from test_the_page_journeys import PHONE, WIDE, _go  # noqa: E402

T = "2026-10-25T09:00:00Z"
CARDS = ("[...document.querySelectorAll('#main .group-card')].map((g) => ({title: (g.querySelector('.card-title') || {}).textContent || '',"
         " pills: [...g.querySelectorAll('.todo-state .chip')].map((c) => c.textContent)}))")
QUICK = "(document.querySelector('#main [data-k^=\"qa-at:\"]') || {}).textContent || ''"


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


@pytest.mark.parametrize("vp", [PHONE, WIDE], ids=["phone", "wide"])
def test_the_title_says_the_count_and_the_pill_never_repeats_it(run, tmp_path, vp):
    juno = '[data-item="larkspur_retail_castellan"]'
    got = _go(run, tmp_path, [
        {"hash": "todo", "eval": "[" + CARDS + ", " + QUICK + "]"},
        {"hash": "contacts", "click": "Copy", "within": juno},
        {"click": "I sent it", "within": juno},
        {"hash": "todo", "eval": CARDS},
    ], vp, clock=T)
    cards, quick = got["after"][0]["eval"]
    send = [c for c in cards if c["title"].startswith("Messages to send")]
    assert send and re.fullmatch(r"Messages to send \(\d+\)", send[0]["title"]), cards
    for c in cards:
        # Nothing done yet: no pill counting what the title counts, only what is overdue.
        assert all(re.fullmatch(r"\d+ overdue", p) for p in c["pills"]), c
    # Which question you are on is not the title's count: it stays.
    assert re.fullmatch(r"1 of \d+", quick), quick
    after = [c for c in got["after"][3]["eval"] if c["title"].startswith("Messages to send")][0]
    # One sent: how far the card has gone, which the title does not say.
    assert after["pills"][-1:] == ["1 of 7 done"], after
