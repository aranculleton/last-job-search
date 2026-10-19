"""The employer-board map: --find uses the vendored openroles, and Lever bodies are whole.

Invented boards only. The network is replaced with canned answers.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import ats_boards  # noqa: E402
import openroles  # noqa: E402
from openroles import Board  # noqa: E402


def test_find_reads_each_board_it_detects_the_way_a_round_would(monkeypatch):
    monkeypatch.setattr(openroles, "detect", lambda target: [Board("lever", "fernhill")])
    monkeypatch.setitem(ats_boards.FETCH, "lever",
                        lambda employer, token: ([{"id": "lv-1"}], None))
    assert ats_boards.find("Fernhill Freight") == [("lever", "fernhill", 1, None)]
    from openroles import _http
    assert _http.USER_AGENT == ats_boards.UA and "Claude-User" in _http.AGENTS


def test_a_lever_body_carries_its_requirement_lists(boards_web):
    boards_web.routes["api.lever.co/v0/postings/fernhill"] = [
        {"id": "a", "text": "Planner", "hostedUrl": "u", "createdAt": 0,
         "categories": {"location": "Remote"},
         "descriptionPlain": "We move freight.",
         "lists": [{"text": "What you need", "content": "<li>SQL</li><li>Forecasting</li>"}],
         "additionalPlain": "Equal opportunity employer."},
        {"id": "b", "text": "Analyst", "hostedUrl": "u2", "createdAt": 0,
         "categories": {"location": "Remote"}}]
    full, empty = ats_boards.lever("Fernhill Freight", "fernhill")[0]
    assert full["desc"].startswith("We move freight.") and "SQL" in full["desc"]
    assert "Equal opportunity" in full["desc"]
    assert empty["desc"] is None


def test_a_workday_listing_with_no_location_takes_the_place_from_its_path(boards_web, monkeypatch):
    # Some tenants send no locationsText. A blank location is "nowhere" to the
    # place filter, and a whole board came back with nothing in range.
    import re
    from openroles.providers import workday as wd
    monkeypatch.setattr(ats_boards, "PLACES", re.compile(r"\bmanchester\b", re.I))
    monkeypatch.setattr(ats_boards, "title_verdict", lambda title: ("FAIL", "no body wanted"))
    monkeypatch.setattr(ats_boards, "location_verdict", lambda loc, title="": ("PASS", ""))
    boards_web.routes["/wday/cxs/fernhill/External/jobs"] = {"total": 2, "facets": [], "jobPostings": [
        {"title": "Demand Planner", "postedOn": "Posted Today",
         "externalPath": "/job/Manchester-1-Piccadilly-Corp/Demand-Planner_R7"},
        {"title": "Route Analyst", "postedOn": "Posted Today",
         "externalPath": "/job/Leeds-Hub/Route-Analyst_R8"}]}
    rows, note = ats_boards.workday("Fernhill Freight", "fernhill.wd3/External", queries=[],
                                    today=ats_boards.dt.date(2026, 10, 17))
    assert [r["location"] for r in rows] == ["Manchester 1 Piccadilly Corp"] and note is None
    assert not [u for u, _ in boards_web.calls if "/job/" in u]        # no body was worth a request
    assert wd.path_place("/job/S%C3%A3o-Paulo/Analyst_R9") == "São Paulo"
