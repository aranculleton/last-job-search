"""A late reply to an application closed on silence is seen.

`followups.py --close-quiet` closes a row as `no_response` after the chase ends, with a
note promising that a reply after all is recorded. /gmail-sync built its search from the
rows that are not final, and `no_response` is final, so no late reply to one was ever
looked for, and a recruiter writing back on day 60 sat unread against a closed row.
"""
from __future__ import annotations

import datetime
import os
import sys
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import followups  # noqa: E402

TODAY = datetime.date(2026, 10, 21)
GMAIL_SYNC = Path(ROOT) / ".claude" / "commands" / "gmail-sync.md"


def _row(company, status, notes):
    return {"company": company, "role": "Planning Analyst", "date": "2026-06-01",
            "status": status, "notes": notes}


def _closed(day, why="no reply in 45 days"):
    return followups.CLOSED_NOTE % (day, why)


def test_rows_closed_on_silence_are_listed_for_a_while():
    rows = [_row("Larkspur Retail", "no_response", "applied via site | " + _closed("2026-09-01")),
            _row("Quayside Foods", "no_response", _closed("2026-03-01")),       # too long ago
            _row("Fernhill Freight", "no_response", "2026-08-01: they said no by phone"),
            _row("Oakmere Foods", "rejected", _closed("2026-09-10")),
            _row("Brindle Hart", "applied", "")]
    got = followups.closed_quiet(rows, TODAY)
    assert [(g["company"], g["closed_on"]) for g in got] == [("Larkspur Retail", "2026-09-01")]
    assert followups.REOPEN_WINDOW_DAYS >= 90


def test_a_row_the_brief_just_closed_is_on_that_list(tmp_path):
    path = tmp_path / "job_search_tracker.csv"
    path.write_text("company,role,date,status,notes,cv_file\n"
                    "Larkspur Retail,Planning Analyst,2026-06-01,applied,,\n", encoding="utf-8")
    closed = followups.close_quiet(str(path), today=TODAY, holds={})
    assert len(closed) == 1
    rows = followups._rows(str(path))
    assert [g["company"] for g in followups.closed_quiet(rows, TODAY)] == ["Larkspur Retail"]


def test_gmail_sync_searches_them_and_proposes_reopening_on_a_reply():
    text = GMAIL_SYNC.read_text(encoding="utf-8")
    assert "python3 tools/followups.py --closed-quiet" in text
    assert "no_response -> interview" in text and "no_response -> rejected" in text
    assert "reopened: they replied" in text
