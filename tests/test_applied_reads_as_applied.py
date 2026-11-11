"""A role applied to is in Applied, and Applied opens on the last day, said as a filter.

The maintainer, 2026-11-05: "why are jobs ive applied for showing at the bottom of the to apply
list? also lets have the applied list do a default filter of 24hrs but its made clear that its
a filter u can remove". Every person and employer here is the sample's, invented.
"""
from __future__ import annotations

import copy
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_the_page_journeys import PHONE, _go, _sample, browser  # noqa: E402
from test_the_page_works_in_a_browser import _write  # noqa: E402

WIDE = {"width": 1400, "height": 900}
CLOCK = "2026-10-25T18:30:00Z"


@pytest.fixture(scope="module")
def run():
    yield from browser()


def test_a_draft_marked_applied_leaves_to_apply_at_once(run, tmp_path):
    html = _write(tmp_path, "applied", _sample())
    tap = {"actions/act~app-copperleaf-payments~ready.applied~x": {"item": "app-copperleaf-payments", "action": "ready.applied",
                                                                    "value": {"on": "2026-10-25"}, "at": "2026-10-25T18:20:00Z", "_v": 1}}
    got = run("engine", html=html, viewport=WIDE, clock=CLOCK, seed=tap, steps=[
        {"hash": "jobs", "count": "#main [data-item=\"app-copperleaf-payments\"]"}])
    assert not got["errors"], got["errors"]
    assert got["after"][0]["count"] == 0


def test_applied_opens_on_the_last_day_as_a_filter_that_clears(run, tmp_path):
    m = copy.deepcopy(_sample())
    for a in m["applications"]:
        if a["id"] == "app-quayside-ops":
            a["applied_on"] = "2026-10-25"
    html = _write(tmp_path, "appliedday", m)
    cards = "#main .stack > [data-item^=\"app-\"]"
    got = run("engine", html=html, viewport=WIDE, clock=CLOCK, steps=[
        {"hash": "jobs", "eval": "(localStorage.setItem('ljs:jobs:tab', JSON.stringify('applied')), 1)"},
        {"hash": "jobs", "click": "Applied", "count": cards, "read": "#main .active-filters"},
        {"click": "Clear all", "count": cards}])
    assert not got["errors"], got["errors"]
    assert got["after"][1]["count"] == 1, got["after"][1]
    assert "Today or yesterday" in got["after"][1]["text"], got["after"][1]["text"]
    assert got["after"][2]["count"] > 1, got["after"][2]


NEXT = r"""(() => [...document.querySelectorAll('#main .card.app-record')].filter((c) => c.getClientRects().length).map((c) => ({
  pill: ((c.querySelector('.job-top .state-word') || {}).textContent || '').trim(), co: ((c.querySelector('.facts .co') || {}).textContent || '').trim(),
  role: ((c.querySelector('.job-top h3') || {}).textContent || '').trim(), next: ((c.querySelector('.facts .next') || {}).textContent || '').trim()})))()"""


@pytest.mark.parametrize("vp", [PHONE, WIDE], ids=["phone", "wide"])
def test_an_applied_cards_next_says_only_what_its_pill_and_title_do_not(run, tmp_path, vp):
    # "Interview Wed 4 Nov" over "Next: second interview on Wed 4 Nov", and "Quayside Foods ·
    # Next: follow up on the Quayside Foods Operations Analyst application" (the screen review,
    # 2026-11-11): the line says what is next, its day where the pill does not.
    got = _go(run, tmp_path, [{"hash": "jobs", "open": "jobsw:applied", "eval": NEXT}], vp, clock="2026-10-25T09:00:00Z")
    cards = [c for c in got["after"][0]["eval"] if c["next"].startswith("Next:")]
    assert any(c["pill"].startswith("Interview ") for c in cards) and len(cards) >= 2, cards
    for c in cards:
        if c["pill"].startswith("Interview "):
            assert c["pill"][len("Interview "):] not in c["next"], c
        assert c["co"] not in c["next"] and c["role"] not in c["next"], c
