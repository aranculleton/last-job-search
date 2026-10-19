"""A round replayed with --today reads every date from that day, not from the clock.

Two readers ignored it: the employer boards dated Workday's "Posted N days ago"
from the real today, and the prefilter read do_not_target.json's review dates
against the real today. A replay of an earlier round misdated its postings and
lifted holds that were still in force on the day it replays.
"""
from __future__ import annotations

import datetime as dt
import functools
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import ats_boards  # noqa: E402
import prefilter  # noqa: E402
import throttle  # noqa: E402

DAY = dt.date(2026, 8, 15)


def test_the_employer_boards_date_workday_from_the_rounds_day(monkeypatch):
    seen = {}

    def workday(employer, token, queries=None, today=None):
        seen["today"] = today
        return [{"url": "https://careers.example.com/jobs/4", "title": "Data Analyst"}], None

    monkeypatch.setitem(ats_boards.FETCH, "workday", workday)
    rows, _ = ats_boards.fetch_all({"Kestrel Mutual": ("workday", "kestrel.wd3/External")},
                                   today=DAY)
    assert rows and seen["today"] == DAY


def test_the_prefilter_reads_review_dates_on_the_rounds_day(tmp_path, monkeypatch):
    dnt = tmp_path / "do_not_target.json"
    dnt.write_text(json.dumps({"companies": {"Fernhill Freight": {
        "reason": "a sales office only in this city", "recorded": "2026-06-01",
        "review_after": "2026-09-01"}}}))
    monkeypatch.setattr(throttle, "load_do_not_target",
                        functools.partial(throttle.load_do_not_target, str(dnt)))
    monkeypatch.setattr(throttle, "referral_holds", lambda *a, **k: {})
    seen = tmp_path / "seen.json"
    seen.write_text('{"seen": {}}')
    job = {"company": "Fernhill Freight", "title": "Data Analyst",
           "url": "https://careers.example.com/jobs/5"}
    assert prefilter.already_ruled_out(str(seen), today=DAY)(job).startswith("do not target")
    assert prefilter.already_ruled_out(str(seen), today=dt.date(2026, 10, 19))(job) == ""
