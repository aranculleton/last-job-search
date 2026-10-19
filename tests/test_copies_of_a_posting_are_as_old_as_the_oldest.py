"""One round finds a posting more than once, and every copy is as old as the oldest.

Ashby publishes no first-posted date, only when a posting was last published, so a
role reposted yesterday after a month open reads as new on the employer's own board
while an aggregator's copy of it says a month. Read alone, the board copy earned the
freshness bonus. Invented employers only.
"""
from __future__ import annotations

import datetime as dt
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import prefilter  # noqa: E402

TODAY = dt.date(2026, 10, 19)
HOME = "Manchester, England, United Kingdom"


def _job(portal, date, title="Data Analyst", company="Fernhill Freight", location=HOME, **kw):
    return dict({"title": title, "company": company, "location": location, "portal": portal,
                 "date": date, "url": f"https://{portal}.example/{date}"}, **kw)


def test_a_board_copy_reposted_yesterday_is_as_old_as_its_aggregator_copy():
    board, portal = prefilter.stamp_copies(
        [_job("ashby", "2026-10-18"), _job("linkedin", "2026-09-25", company="Fernhill Freight Ltd")],
        TODAY)
    assert board["copy_date"] == "2026-09-25" and "copy_date" not in portal
    assert prefilter.age_days(board, TODAY) == 24


def test_a_different_role_city_or_employer_is_not_a_copy():
    rows = prefilter.stamp_copies([
        _job("ashby", "2026-10-18"),
        _job("linkedin", "2026-09-25", title="Senior Data Analyst"),
        _job("linkedin", "2026-09-25", location="Leeds, England, United Kingdom"),
        _job("linkedin", "2026-09-25", company="Brackenhollow Mutual")], TODAY)
    assert all("copy_date" not in r for r in rows)


def test_a_copy_older_than_the_relist_window_is_another_opening():
    board, _ = prefilter.stamp_copies([_job("ashby", "2026-10-18"), _job("linkedin", "2026-08-01")],
                                      TODAY)
    assert "copy_date" not in board


def test_every_system_openroles_reads_is_a_live_employer_board():
    from openroles.models import ATS
    assert prefilter.LIVE_BOARDS == frozenset(ATS)
    assert {"personio", "careersite"} <= prefilter.LIVE_BOARDS
