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
from test_the_page_journeys import _sample, browser  # noqa: E402
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
