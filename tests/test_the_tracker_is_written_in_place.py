"""The tracker is written in place, and an application is found under any form of its name.

`record_drafts.py` wrote the tracker with a plain DictWriter: every "\\n" line
ending became "\\r\\n", so one new row changed every line and two chats' work
collided on all of them, and a column someone added after `deadline` earned a
second `deadline`. It kept its own copy of the final statuses, without
`declined`, and matched company and role as raw lower-case strings, while every
other reader of the state matches on the employer's key and the throttle's title
rule. `lookup_score.py`, the check /apply runs before drafting, compared raw
names too, so "Acme Analytics" never saw an application to "Acme Analytics Inc.".
"""
from __future__ import annotations

import csv
import datetime
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import ats_boards  # noqa: E402
import followups  # noqa: E402
import lookup_score  # noqa: E402
import record_drafts  # noqa: E402

HEAD = record_drafts.HEADER


def _tracker(path, rows, header=HEAD, ending="\n"):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=header, lineterminator=ending)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in header})


def _draft(company="Acme Analytics", role="Senior Data Analyst", abbr="AcmeAnalytics", **kw):
    return dict({"company": company, "role": role, "abbr": abbr}, **kw)


def _rows(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.reader(fh))


def test_a_new_row_changes_one_line_and_keeps_the_line_endings(tmp_path):
    path = tmp_path / "tracker.csv"
    _tracker(path, [{"date": "2026-09-01", "company": "Larkspur Retail", "role": "Analyst",
                     "status": "applied"}])
    before = path.read_bytes()
    record_drafts.record([_draft()], {"ACMEANALYTICS": {"fit": 70}}, "2026-10-19", path=str(path))
    after = path.read_bytes()
    assert b"\r\n" not in after
    assert after.startswith(before)                  # the rows already there, byte for byte
    assert after.count(b"\n") == before.count(b"\n") + 1


def test_a_column_added_by_hand_keeps_its_place_and_deadline_is_not_doubled(tmp_path):
    path = tmp_path / "tracker.csv"
    header = HEAD + ["my_notes"]
    _tracker(path, [{"date": "2026-09-01", "company": "Larkspur Retail", "role": "Analyst",
                     "status": "applied", "my_notes": "called them"}], header=header)
    record_drafts.record([_draft(deadline="2026-11-01")], {"ACMEANALYTICS": {"fit": 70}},
                         "2026-10-19", path=str(path))
    rows = _rows(path)
    assert rows[0] == header
    assert rows[1][header.index("my_notes")] == "called them"
    assert rows[2][header.index("deadline")] == "2026-11-01"


def test_a_spreadsheet_saved_tracker_keeps_its_crlf(tmp_path):
    path = tmp_path / "tracker.csv"
    _tracker(path, [{"company": "Larkspur Retail", "role": "Analyst", "status": "applied"}],
             ending="\r\n")
    record_drafts.record([_draft()], {}, "2026-10-19", path=str(path))
    assert path.read_bytes().count(b"\r\n") == 3


def test_a_declined_application_is_final_and_keeps_its_row(tmp_path):
    path = tmp_path / "tracker.csv"
    _tracker(path, [{"date": "2026-08-01", "company": "Acme Analytics", "status": "declined",
                     "role": "Senior Data Analyst", "notes": "offer declined by phone"}])
    [(action, _)] = record_drafts.record([_draft()], {}, "2026-10-19", path=str(path))
    assert action == "added"
    rows = _rows(path)
    assert rows[1][HEAD.index("status")] == "declined" and len(rows) == 3


def test_the_same_application_under_another_spelling_is_updated_not_duplicated(tmp_path):
    path = tmp_path / "tracker.csv"
    _tracker(path, [{"date": "2026-10-01", "company": "Acme Analytics Inc.",
                     "role": "Sr. Data Analyst", "status": "drafted"}])
    [(action, row)] = record_drafts.record([_draft()], {"ACMEANALYTICS": {"fit": 71}},
                                           "2026-10-19", path=str(path))
    assert action == "updated" and row["fit_rating"] == "71"
    assert len(_rows(path)) == 2


def test_an_employer_board_posting_is_applied_to_online():
    assert record_drafts.EMPLOYER_BOARDS == frozenset(ats_boards.FETCH)
    assert record_drafts._channel("greenhouse") == "online"
    assert record_drafts._channel("Workday") == "online"
    assert record_drafts._channel("linkedin") == "portal"
    assert record_drafts._channel("pasted") == "" and record_drafts._channel(None) == ""
    row = record_drafts._row_for(_draft(), {"portal": "lever"}, "2026-10-19", "")
    assert row["channel"] == "online"


def test_closing_a_quiet_application_keeps_the_line_endings(tmp_path):
    path = tmp_path / "tracker.csv"
    _tracker(path, [{"company": "Fernhill Freight", "role": "Pricing Analyst",
                     "date": "2026-03-01", "status": "applied"},
                    {"company": "Larkspur Retail", "role": "Data Analyst",
                     "date": "2026-05-20", "status": "applied"}])
    gone = followups.close_quiet(str(path), datetime.date(2026, 6, 1), holds={})
    assert [g["company"] for g in gone] == ["Fernhill Freight"]
    data = path.read_bytes()
    assert b"\r\n" not in data and data.count(b"\n") == 3


def test_the_pre_draft_check_finds_the_employer_under_its_legal_name(tmp_path, monkeypatch):
    path = tmp_path / "tracker.csv"
    _tracker(path, [{"date": "2026-10-01", "company": "Acme Analytics Inc.",
                     "role": "Data Analyst", "status": "applied"}])
    monkeypatch.setattr(lookup_score, "TRACKER", str(path))
    assert [r["role"] for r in lookup_score.tracker_rows_for(None, "Acme Analytics")] == [
        "Data Analyst"]
    assert lookup_score.tracker_rows_for(None, "Larkspur Retail") == []


def test_a_stored_score_is_found_under_the_legal_name_and_ambiguity_still_refuses(monkeypatch):
    seen = {"https://example.com/a": {"company": "Acme Analytics Inc.", "title": "Data Analyst",
                                       "rank_score": 70},
            "https://example.com/b": {"company": "Larkspur Retail", "title": "Analyst"}}
    monkeypatch.setattr(lookup_score, "load_seen", lambda: seen)
    url, rec = lookup_score.find(None, "Acme Analytics", "Data Analyst")
    assert url == "https://example.com/a"
    seen["https://example.com/c"] = {"company": "ACME ANALYTICS LTD", "title": "Data Analyst II"}
    try:
        lookup_score.find(None, "Acme Analytics", "Data Analyst")
    except lookup_score.Ambiguous as e:
        assert len(e.hits) == 2
    else:
        raise AssertionError("two stored entries matched and one was guessed")
