"""Progress leads with what the person did this week, and how far applications got comes second.

The UX review of 2026-11-10 (U-7): Progress led on outcomes ("Offer 0 of 24", a verdict from the
funnel) with no base rate, the week's own work folded away, so a person doing the right things
read only that they were failing. Its line now says this week's applications and messages sent,
and the funnel carries the outcomes with one line of what is usual; a finding is worded as a
next step. Every person and employer is invented.
"""
from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest  # noqa: E402

import test_the_page_journeys as journeys  # noqa: E402
from test_the_page_journeys import PHONE, WIDE, _go, _sample  # noqa: E402

T = "2026-10-25T09:00:00Z"            # the sample's newest week, 2026-W43, is this week
LOOK = ("(() => { const m = document.querySelector('#main'); const f = m.querySelector('#h-funnel');"
        " const w = m.querySelector('details.chart, .chart summary');"
        " return {sum: m.querySelector('.sum').textContent, small: (m.querySelector('.sum-small') || {}).textContent || '',"
        " funnel: f ? f.closest('.chart').textContent : '', words: (m.querySelector('.fun-sum') || {}).textContent || '',"
        " pills: f ? [...f.closest('.chart').querySelectorAll('summary, button')].length : -1, weeksFirst: !!(w && f && (w.compareDocumentPosition(f) & Node.DOCUMENT_POSITION_FOLLOWING))}; })()")


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


def _busy_week():
    m = _sample()
    m["done"]["weeks"] = [{"week": "2026-W42", "applied": 2, "sent": 4, "replies": 0},
                          {"week": "2026-W43", "applied": 5, "sent": 3, "replies": 2}]
    m["done"]["funnel"] = [{"stage": "applied", "n": 24}, {"stage": "replied", "n": 3},
                           {"stage": "interview", "n": 1}, {"stage": "offer", "n": 0}]
    return m


@pytest.mark.parametrize("vp", [PHONE, WIDE], ids=["phone", "wide"])
def test_this_weeks_work_leads_and_the_funnel_is_said_with_what_is_usual(run, tmp_path, vp):
    got = _go(run, tmp_path, [{"hash": "progress", "eval": LOOK}], vp, model=_busy_week(), clock=T)
    seen = got["after"][0]["eval"]
    assert seen["sum"] == "This week: 5 applied, 3 messages sent.", seen
    assert seen["small"].startswith("Next step:"), seen
    assert "a few in every 100 reach an interview" in seen["funnel"], seen
    # What is usual, under the funnel; its numbers are the funnel's own, said once there:
    # "24 applied, 7 replies, 3 interviews, no offers yet" under the bars repeated them (the
    # screen review, 2026-11-11).
    assert "Most applications get no reply" in seen["words"], seen
    assert not re.search(r"\d+ (applied|repl|interview)", seen["words"]), seen
    # Nothing folded inside the card: a "More" there drew as an empty pill (the review, 2026-11-11).
    assert seen["pills"] == 0, seen
    assert "practise interviews with Claude. You are reaching them" in seen["small"] or "few interviews" in seen["small"], seen


def test_the_briefs_tiles_lead_with_this_weeks_own_work(run, tmp_path):
    """The review of 2026-11-11: the Brief's tiles, which U-7 names, still led on outcomes."""
    look = "[...document.querySelectorAll('#main .bp-l')].map((e) => e.textContent)"
    got = _go(run, tmp_path, [{"hash": "brief", "eval": look}], WIDE, model=_busy_week(), clock=T)
    labels = got["after"][0]["eval"]
    assert labels[:2] == ["applied this week", "messages sent this week"], labels


def test_the_weeks_axis_reads_at_the_pages_small_size_on_a_phone(run, tmp_path):
    # Its labels were drawn about 7px high on a phone, the chart's width scaled down to the
    # screen (the screen review, 2026-11-11). They read at the page's small size, and the
    # week labels do not crowd.
    look = ("(() => { const t = [...document.querySelectorAll('#main .weeks-svg .tick')]; const h = t.map((e) => e.getBoundingClientRect().height);"
            " const xs = t.filter((e) => e.getAttribute('text-anchor') === 'middle').map((e) => e.getBoundingClientRect()).sort((a, b) => a.left - b.left);"
            " return {min: Math.min(...h), overlap: xs.slice(1).some((r, i) => r.left < xs[i].right + 2)}; })()")
    got = _go(run, tmp_path, [{"hash": "progress", "eval": look}], PHONE, clock=T)
    seen = got["after"][0]["eval"]
    assert seen["min"] >= 11 and not seen["overlap"], seen
