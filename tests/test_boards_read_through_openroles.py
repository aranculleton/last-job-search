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


def test_a_lever_body_carries_its_requirement_lists():
    job = {"descriptionPlain": "We move freight.",
           "lists": [{"text": "What you need", "content": "<li>SQL</li><li>Forecasting</li>"}],
           "additionalPlain": "Equal opportunity employer."}
    body = ats_boards._lever_body(job)
    assert body.startswith("We move freight.") and "SQL" in body and "Equal opportunity" in body
    assert ats_boards._lever_body({}) is None
