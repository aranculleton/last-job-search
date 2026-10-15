"""Employer boards are read through the vendored openroles; the search's own rules stay here.

Invented boards only. The network is replaced with canned answers.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import ats_boards  # noqa: E402
from openroles import _http  # noqa: E402


def test_requests_go_out_as_this_app_under_its_robots_agents():
    assert _http.USER_AGENT == ats_boards.UA
    assert "Claude-User" in _http.AGENTS and "last-job-search" in _http.AGENTS


def test_a_library_error_reads_without_its_board_prefix():
    assert ats_boards._why(Exception("lever:acme: not a posting list (HTTP 404)")) == \
        "not a posting list (HTTP 404)"
    assert ats_boards._why(Exception("plain message")) == "plain message"


def test_greenhouse_rows_keep_the_place_filter_and_the_body_cap(monkeypatch):
    monkeypatch.setattr(ats_boards, "PLACES", __import__("re").compile(r"manchester", __import__("re").I))
    board = {"jobs": [
        {"id": 1, "title": "Demand Planner", "absolute_url": "https://boards.example.com/1",
         "location": {"name": "Manchester, UK"}, "first_published": "2026-10-01T00:00:00Z",
         "content": "&lt;p&gt;" + "x" * 30_000 + "&lt;/p&gt;"},
        {"id": 2, "title": "Planner", "absolute_url": "https://boards.example.com/2",
         "location": {"name": "Lisbon"}, "first_published": "2026-10-01T00:00:00Z", "content": ""},
    ]}
    monkeypatch.setattr(_http, "request", lambda url, payload=None, accept="": (board, None))
    rows, err = ats_boards.greenhouse("Oakmere Foods", "oakmere")
    assert err is None and [r["id"] for r in rows] == ["gh-1"]
    row = rows[0]
    assert row["company"] == "Oakmere Foods" and row["date"] == "2026-10-01"
    assert len(row["desc"]) == ats_boards.BODY_CAP and row["portal"] == "greenhouse"


def test_a_board_that_does_not_answer_is_a_reason_not_a_crash(monkeypatch):
    monkeypatch.setattr(_http, "request", lambda url, payload=None, accept="": (None, "HTTP 500"))
    monkeypatch.setattr(_http, "RETRY_PAUSE", 0)
    rows, err = ats_boards.lever("Fernhill Freight", "fernhill")
    assert rows == [] and "HTTP 500" in err
