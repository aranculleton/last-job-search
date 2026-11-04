"""An application's follow-up reads like a person wrote it, and waits for the posting to close.

Two things the follow-ups assumed of one market. They wrote the date as the machine keeps it
("I applied for the role on 2026-11-03"), where a reader expects "3 November" or "November 3".
And they never read the posting's closing date, which the drafter records in the tracker:
an application sent five weeks before a public-sector closing date was nudged a week later,
nudged again, and closed as no reply weeks before the employer had shortlisted. Now the first
nudge is timed from the closing date where there is one, no row goes quiet before the closing
date plus the silence window, and a row the search closed before that is opened again by the
next close (the brief runs it every morning), so an older copy repairs itself.
"""
from __future__ import annotations

import csv
import datetime
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import followups  # noqa: E402
import throttle  # noqa: E402

D = datetime.date
ROW = {"company": "Quayside Foods", "role": "Lifecycle Marketing Manager",
       "date": "2026-11-03", "applied_on": "2026-11-03", "status": "applied",
       "contact_person": "Wren Castellan", "notes": "", "deadline": ""}


def _one(row, today):
    return followups.review([dict(row)], today, warm={}, holds={}, docs="/nonexistent")[0]


def test_the_message_writes_the_date_the_way_a_person_does(monkeypatch):
    it = _one(ROW, D(2026, 11, 14))
    assert it["state"] == "due"
    assert "on 3 November and wanted" in it["message"]          # the example's day-month order
    assert "2026-11-03" not in it["message"]
    monkeypatch.setattr(followups, "_DOCS", {"date_format": "month_day_year"})
    assert "on November 3 and wanted" in _one(ROW, D(2026, 11, 14))["message"]
    heard = dict(ROW, notes="2026-11-10: recruiter replied, reviewing next week")
    monkeypatch.setattr(followups, "_DOCS", {"date_format": "day_month_year"})
    assert "thank you for your note on 10 November." in _one(heard, D(2026, 11, 24))["message"]


def test_no_nudge_before_the_posting_closes():
    row = dict(ROW, deadline="2026-12-15")
    it = _one(row, D(2026, 11, 10))
    assert it["state"] == "waiting" and it["due_on"] == "2026-12-22"
    assert _one(row, D(2026, 12, 22))["state"] == "due"
    # No closing date: a week after applying, as before.
    assert _one(ROW, D(2026, 11, 10))["state"] == "due"


def test_nothing_goes_quiet_before_the_closing_date_and_the_silence_after_it(tmp_path):
    # Two nudges already sent before the closing date, as the old timing told them to.
    row = dict(ROW, deadline="2026-12-15", notes="followed up 2026-11-10 | followed up 2026-11-17")
    assert _one(row, D(2026, 11, 24))["state"] != "quiet"
    quiet = D(2026, 12, 15) + datetime.timedelta(days=followups.SILENCE_DAYS)
    assert _one(row, quiet - datetime.timedelta(days=1))["state"] != "quiet"
    assert _one(row, quiet)["state"] == "quiet"
    path = tmp_path / "tracker.csv"
    _write(path, [row])
    assert followups.close_quiet(str(path), D(2026, 11, 24), write=False, holds={}) == []
    # The throttle keeps counting it as live until the same day.
    assert not throttle.is_silent(row, D(2026, 12, 20))
    assert throttle.is_silent(dict(row, deadline=""), D(2026, 12, 20))
    assert throttle.is_silent(row, quiet)


def test_a_row_the_search_closed_before_its_closing_date_is_opened_again(tmp_path):
    closed = dict(ROW, deadline="2026-12-15", status="no_response", confirmed_by="the search",
                  confirmed_at="2026-11-24 07:56",
                  notes="followed up 2026-11-10 | followed up 2026-11-17 | 2026-11-24: closed "
                        "as no_response, no reply in 21 days (followups.py --close-quiet). If "
                        "they reply after all, /outcome records it.")
    after = dict(ROW, company="Fernhill Freight", deadline="2026-09-01", status="no_response",
                 confirmed_by="the search", applied_on="2026-08-01", date="2026-08-01",
                 notes="2026-10-20: closed as no_response, no reply in 80 days "
                       "(followups.py --close-quiet). If they reply after all, /outcome records it.")
    path = tmp_path / "tracker.csv"
    _write(path, [closed, after])
    followups.close_quiet(str(path), D(2026, 11, 30), holds={})
    rows = _read(path)
    assert rows[0]["status"] == "applied" and rows[0]["confirmed_by"] == ""
    assert "opened again" in rows[0]["notes"] and rows[0]["applied_on"] == "2026-11-03"
    assert rows[1]["status"] == "no_response"            # closed after its window: stays
    # Run again: nothing reopened twice, nothing closed.
    followups.close_quiet(str(path), D(2026, 11, 30), holds={})
    assert _read(path)[0]["notes"].count("opened again") == 1


HEAD = list(ROW) + ["confirmed_by", "confirmed_at"]


def _write(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=HEAD)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in HEAD})


def _read(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))
