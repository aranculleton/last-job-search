"""A hold that waits for a role lifts while a role at their employer is on the person's list.

The review of 2026-11-10 found two ways the hold came back, or never lifted, with a role in
plain sight. It read only the newest saved search, so the hold went back on as soon as a newer
search was saved without the posting, though Jobs still listed it (R1-3). And it read only the
searches, so it said no role was posted at an employer where the person had applied and had an
interview booked (R1-4). The engine's half, on the real path (`app.py model` over a search's
own files); every person and employer is invented (tests/app_state.py's small search).
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network"),
                os.path.join(ROOT, "tests")]

import pytest  # noqa: E402

from test_people_on_hold_are_a_group_of_their_own import (  # noqa: E402
    WREN, _model, _person, _post_a_role, _set)
from test_a_tick_on_the_page_is_applied_once import Search  # noqa: E402


@pytest.fixture
def search(tmp_path):
    import state
    s = Search(str(tmp_path))
    _set(s, WREN, next_action=state.ROLE_HOLD % "Fernhill Freight"
         + ": they offered to refer you", next_action_due="")
    return s


def test_a_newer_search_saved_without_the_posting_leaves_the_hold_lifted(search):
    _post_a_role(search, "Fernhill Freight")
    assert _person(_model(search), WREN)["on_hold"] is None
    # A newer search, of other employers: the posting is still on the list, carried.
    path = os.path.join(search.state, "documents", "rounds", "r10.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump([{"company": "Brindle Hart Logistics", "title": "Planning Analyst", "fit": 70,
                    "first_seen": "2026-10-25", "url": "https://jobs.example/brindle/planning",
                    "location": "Manchester"}], fh)
    m = _model(search)
    assert ("Fernhill Freight", "Supply Chain Analyst") in [
        (r["company"], r["title"]) for r in m["jobs"]["rows"]], "the posting is still on the list"
    p = _person(m, WREN)
    assert p["on_hold"] is None and p["group"] == "now", p
    assert p["next"] == "Fernhill Freight has posted Supply Chain Analyst: ask them to refer you"


def _in_for(search, status, role="Transport Planner"):
    import csv
    path = os.path.join(search.state, "job_search_tracker.csv")
    with open(path, encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    head = list(rows[0])
    rows.append(dict.fromkeys(head, "") | {
        "date": "2026-10-20", "company": "Fernhill Freight", "role": role, "status": status,
        "source": "https://jobs.example/fernhill/transport-planner", "applied_on": "2026-10-20"})
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=head)
        w.writeheader()
        w.writerows(rows)


def test_an_interview_booked_at_their_employer_is_a_role_and_lifts_the_hold(search):
    _in_for(search, "interview")
    p = _person(_model(search), WREN)
    assert p["on_hold"] is None and p["group"] == "now", p
    assert p["next"] == ("You have an interview for Transport Planner at Fernhill Freight: ask "
                         "them to put in a word"), p["next"]
    assert p["owed"]["args"]["role"] == "Transport Planner"
    assert p["owed"]["args"]["url"] == "https://jobs.example/fernhill/transport-planner"


def test_an_application_that_closed_is_no_role(search):
    _in_for(search, "rejected")
    p = _person(_model(search), WREN)
    assert p["on_hold"] and p["on_hold"]["role"] is True, p


def test_an_application_already_there_when_the_hold_was_made_lifts_nothing(search):
    """The review of 2026-11-11: a hold made while an application at that employer was already
    open was made knowing it, so that application lifts nothing; one begun since the hold does.
    An offer is said as an offer."""
    import state
    _set(search, WREN, next_action=state.ROLE_HOLD % "Fernhill Freight"
         + ": they offered to refer you (since 2026-10-24)", next_action_due="")
    _in_for(search, "interview")                                   # from 2026-10-20
    p = _person(_model(search), WREN)
    assert p["on_hold"] and p["on_hold"]["role"] is True, p
    _in_for(search, "offer", role="Network Planner")              # also from 2026-10-20
    assert _person(_model(search), WREN)["on_hold"]


def test_an_offer_is_said_as_an_offer(search):
    _in_for(search, "offer")
    p = _person(_model(search), WREN)
    assert p["next"] == ("You have an offer for Transport Planner at Fernhill Freight: ask them "
                         "to put in a word"), p["next"]
