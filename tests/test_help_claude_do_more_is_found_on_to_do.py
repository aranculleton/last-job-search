"""Help Claude do more is found on To do, without crowding today's five or its counts.

The maintainer, 2026-11-07: "i feel like help claude do more is more important but its a bit
too tucked away here": it sat at the foot of To do as a quiet fold after "Not due yet", among
the hidden and done lines. Now it is one line right after today's things and above Not due
yet, saying what it gives; with nothing due today, its first card shows under its own
heading. It is never counted among today's things (DESIGN.md, Places). The sample (tests/
fixtures/app_model_sample.json) is an invented search.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

from test_the_page_journeys import PHONE, WIDE, _go, _sample  # noqa: E402

T = "2026-10-25T09:00:00Z"
READ = ("(() => { document.querySelectorAll('details.band-more').forEach((d) => { d.open = false; }); const m = document.querySelector('#main');"
        " const folds = [...m.querySelectorAll('details.band-more > summary')].map((s) => s.textContent.trim());"
        " const open = (c) => !c.closest('details:not([open])');"
        " const cards = [...m.querySelectorAll('.band [data-card]')].filter(open).map((c) => ((c.closest('.band').querySelector('h3') || {}).textContent || '') + ': ' + ((c.querySelector('.card-title') || {}).textContent || ''));"
        " const you = m.querySelector('[data-item=\"you\"]');"
        " return {folds, cards, sum: (m.querySelector('.sec-head p, .screen-sum, header p') || {}).textContent || '', youOpen: !!you && open(you)}; })()")


@pytest.fixture(scope="module")
def run():
    from test_the_page_journeys import browser
    yield from browser()


@pytest.mark.parametrize("vp", [PHONE, WIDE], ids=["phone", "wide"])
def test_help_is_one_line_after_todays_things_and_above_not_due_yet(run, tmp_path, vp):
    got = _go(run, tmp_path, [{"hash": "todo", "eval": READ}], vp, clock=T)
    r = got["after"][0]["eval"]
    helps = [f for f in r["folds"] if f.startswith("Help Claude do more")]
    assert len(helps) == 1, r["folds"]
    # It says what it gives, in a line.
    assert "built from it" in helps[0], helps[0]
    later = [i for i, f in enumerate(r["folds"]) if f.startswith(("Not due yet", "1 hidden", "Done today", "1 put off"))]
    assert all(r["folds"].index(helps[0]) < i for i in later), r["folds"]
    # Today's five are still today's things only, and the help is no card among them.
    assert len(r["cards"]) <= 5, r["cards"]
    assert not any("Finish your profile" in c for c in r["cards"]) and not r["youOpen"], r


def test_with_nothing_due_today_its_first_card_shows(run, tmp_path):
    m = _sample()
    for k in ("due", "needs_you", "messages", "interviews", "upcoming", "ready"):
        m[k] = []
    m["to_send"] = {"n": 0, "ids": []}
    for row in m["jobs"]["rows"]:
        row["alerts"] = []
    m["linkedin_export"] = None
    got = _go(run, tmp_path, [{"hash": "todo", "eval": READ, "read": "#main"}], PHONE, model=m, clock=T)
    r = got["after"][0]["eval"]
    text = got["after"][0]["text"]
    assert r["youOpen"], (r, text[:800])
    assert "Help Claude do more" in text
    # Never counted as something to do today.
    assert "1 thing today" not in text and "things today" not in text, text[:400]
