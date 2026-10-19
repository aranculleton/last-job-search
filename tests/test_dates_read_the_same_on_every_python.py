"""A date is read the same on every Python the app runs on.

`date.fromisoformat` took "20261017" from Python 3.11 and refused it on 3.10 and
3.9, a Mac's own python3. Three readers still called it on a sliced string, so
what they read depended on the Python running them. They read through
tools/dates.py, which takes neither form as an ISO date on any of them.
"""
from __future__ import annotations

import datetime as dt
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import company_research  # noqa: E402
import job_alerts  # noqa: E402
import opportunity  # noqa: E402

TODAY = dt.date(2026, 10, 19)


def test_a_compact_date_is_no_date_to_every_reader():
    row = {"title": "Data Analyst", "company": "Kestrel Mutual", "date": "20261018",
           "desc": "x" * 500}
    assert not [w for w in opportunity.score(row, TODAY)["why"] if "posted" in w]
    assert company_research.age_days({"fetched_date": "20261017"}, TODAY) is None
    assert job_alerts.day("20261017") == ""


def test_an_iso_date_and_a_timestamp_still_read():
    assert company_research.age_days({"fetched_date": "2026-10-17T09:00:00Z"}, TODAY) == 2
    assert company_research.age_days({"fetched_date": "2026-10-17"}, "2026-10-19") == 2
    row = {"title": "Data Analyst", "company": "Kestrel Mutual", "date": "2026-10-18",
           "desc": "x" * 500}
    assert [w for w in opportunity.score(row, TODAY)["why"] if "posted" in w]
