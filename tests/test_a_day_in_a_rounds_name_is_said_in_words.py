"""A day in a round's name is said in words in its title, as the page says every day.

A round paused on a day was titled "Paused 2026-10-20 with ..." in Coming up and To do (the
screen review, 2026-11-11): the engine wrote the stage's name as it stood into `stage_title`,
and the page printed it. Now the engine says the day in words there ("Paused Tue 20 Oct"),
keeping the name as written in `next_stage`, which is what an action names the round by; and
the page says any such day in words too, whatever wrote it (the extremes of
tests/test_no_words_are_drawn_over_other_words_or_buttons.py, the drawing probe's "date").
Every person and employer here is invented (tests/app_state.py, the sample page model).
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

from test_a_tick_on_the_page_is_applied_once import Search  # noqa: E402

LARKSPUR = "app-larkspur_retail_senior_supply_chain_analyst"


@pytest.fixture
def search(tmp_path):
    return Search(str(tmp_path))


def test_a_round_named_with_a_day_is_titled_with_the_day_in_words(search):
    app = next(a for a in search.model()["applications"] if a["id"] == LARKSPUR)
    aid = search.act("outcome.interview", LARKSPUR, rev=app["rev"], value={"stage": "Paused 2026-10-20", "on": ""})
    assert search.apply()["ok"] == [aid], search.receipt(aid)
    (iv,) = [i for i in search.model()["interviews"] if i["company"] == "Larkspur Retail"]
    assert iv["stage_title"] == "Paused Tue 20 Oct", iv
    # What an action names the round by is kept as it was written.
    assert iv["next_stage"] == "Paused 2026-10-20", iv
