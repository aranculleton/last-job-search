"""A late reply to an application closed on silence is seen.

`followups.py --close-quiet` closes a row as `no_response` after the chase ends, with a
note promising that a reply after all is recorded. `no_response` is final, so a reader
built from the rows that are not final never looks at one, and a recruiter writing back
on day 60 sits unread against a closed row. `--closed-quiet` lists them, and the note
sends a late reply to /outcome.
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
OUTCOME = Path(ROOT) / ".claude" / "commands" / "outcome.md"


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


def test_the_closing_note_says_where_a_late_reply_goes():
    assert "/outcome records it" in followups.CLOSED_NOTE
    text = OUTCOME.read_text(encoding="utf-8")
    assert "a reply after that is recorded here as usual" in text
