"""A closed application holds back the same role, never a role whose title starts the same.

`throttle._same_title` matched on prefixes, so a closed "Data Analyst" was the
same role as "Data Analyst, Fraud Strategy". The skip it produced ("already
applied to this role") is not re-evaluated, so the second role stayed out for
good. Titles are compared whole, after spelling and posting tags are folded.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import throttle  # noqa: E402

CLOSED = {"kestrelmutual": [{"company": "Kestrel Mutual", "role": "Data Analyst",
                             "status": "rejected", "date": "2026-08-01"}]}


def test_a_longer_title_is_another_role():
    assert not throttle._same_title("Data Analyst, Fraud Strategy", "Data Analyst")
    assert not throttle._same_title("Data Analyst", "Data Analyst II")


def test_the_same_role_spelled_differently_is_still_the_same_role():
    assert throttle._same_title("Sr. Analyst, Supply Chain",
                                "Senior Analyst, Supply Chain (Future Opportunities)")
    assert throttle._same_title("Data Analyst (Remote)", "data analyst")
    assert not throttle._same_title("", "")


def test_the_throttle_lets_the_other_role_through(monkeypatch):
    monkeypatch.setattr(throttle, "key", lambda name: "kestrelmutual" if name else "")
    rows = [{"title": "Data Analyst, Fraud Strategy", "company": "Kestrel Mutual",
             "url": "https://careers.example.com/jobs/9", "priority": 70, "fit": 82}]
    kept, skipped = throttle.throttle(rows, {}, {}, {}, "2026-10-14", closed=CLOSED)
    assert kept and not skipped
    rows[0]["title"] = "Data Analyst"
    kept, skipped = throttle.throttle(rows, {}, {}, {}, "2026-10-14", closed=CLOSED)
    assert skipped and "already applied to this role" in skipped[0]["skip_reason"]
