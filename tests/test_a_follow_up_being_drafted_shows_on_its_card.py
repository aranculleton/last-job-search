"""A follow-up being drafted shows on its card, however its work was asked for.

A person's copy, 2026-11-06: eight follow-ups were being drafted while their card showed nothing
happening, so it looked idle and the person pressed Draft again. Their work had been asked for
another way (taken back from questions put to the person), with no due row named in it, and the
card looked for its work by the due row alone. The row now also finds the same work for that
person. Every name here is the sample's, invented.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_the_page_journeys import _sample, browser  # noqa: E402
from test_the_page_works_in_a_browser import _write  # noqa: E402

WIDE = {"width": 1400, "height": 900}
CLOCK = "2026-10-25T18:30:00Z"
WHO = "fernhill_freight_halloway"
ROW = ("(() => { const r = document.querySelector('#main [data-item=\"due-fernhill-nudge\"]');"
       " return r ? r.textContent : null; })()")


@pytest.fixture(scope="module")
def run():
    yield from browser()


def _work(status):
    return {"work/follow_up~" + WHO: {
        "kind": "follow_up", "title": "Follow up with Halloway at Fernhill Freight", "to": "either",
        "args": {"contact": WHO}, "asked_at": "2026-10-25T18:00:00Z", "asked_from": {"tab": "t0"},
        "status": status, "claimed_by": "cloud-1", "claimed_at": "2026-10-25T18:20:00Z",
        "lease_until": "2026-10-25T19:20:00Z", "stages": [], "stage": 0, "steps": [], "attempt": 1}}


def _row(run, tmp_path, seed):
    import copy
    m = copy.deepcopy(_sample())
    # Nothing drafted for them yet: the row offers its Draft until the work shows.
    m["messages"] = [x for x in m["messages"] if x.get("contact") != WHO]
    html = _write(tmp_path, "fu", m)
    got = run("engine", html=html, viewport=WIDE, clock=CLOCK, seed=seed,
              steps=[{"hash": "todo", "eval": ROW}])
    assert not got["errors"], got["errors"]
    return got["after"][0]["eval"]


def test_a_follow_up_claimed_without_its_due_row_shows_on_the_row(run, tmp_path):
    idle = _row(run, tmp_path, {})
    assert idle and "Draft the follow-up" in idle, idle
    busy = _row(run, tmp_path, _work("claimed"))
    assert busy and "Draft the follow-up" not in busy, busy
