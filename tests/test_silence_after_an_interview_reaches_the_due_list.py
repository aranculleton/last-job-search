"""Silence after an interview reaches the due list.

`followups.review()` chases only `applied` rows, and a live process is never timed out,
on purpose: a wrong nudge mid-process costs more than a missed one. `open_actions` put
the pack before a stage and the thank-you for a week after it, and then said nothing for
good, so a final round three weeks past with no word from the employer never reached the
list, not even as a question. It does now, as a question, never a nudge: a short status
note or the outcome. After two status notes, the outcome only.
"""
from __future__ import annotations

import csv
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "network"))

import open_actions  # noqa: E402
import outreach  # noqa: E402

ROW = {"date": "2026-09-01", "company": "Kestrel Mutual", "role": "Pricing Analyst",
       "status": "interview", "notes": "2026-09-20: recruiter said a decision in a week"}
OUTCOME = """# Outcome: Kestrel Mutual - Pricing Analyst

**Status:** in_progress

## Interview stages reached
- [x] Phone screen (2026-09-10)
- [x] Final round (2026-09-24)
{booked}- [ ] Offer received
"""


def _state(tmp_path, monkeypatch, booked="", files=(), row=ROW):
    tmp_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("LJS_STATE", str(tmp_path))
    with open(tmp_path / "job_search_tracker.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(row))
        w.writeheader()
        w.writerow(row)
    folder = outreach.app_folder(row["company"], row["role"])
    os.makedirs(folder)
    with open(os.path.join(folder, "outcome.md"), "w", encoding="utf-8") as fh:
        fh.write(OUTCOME.format(booked=booked))
    for name in files:
        with open(os.path.join(folder, name), "w", encoding="utf-8") as fh:
            fh.write("x\n")


def test_two_weeks_of_silence_after_the_last_stage_is_asked_about(tmp_path, monkeypatch):
    _state(tmp_path, monkeypatch)
    assert open_actions.interview_items([ROW], "2026-10-07") == []      # 13 days
    (item,) = open_actions.interview_items([ROW], "2026-10-21")
    assert (item["due"], item["late"], item["kind"]) == ("2026-10-08", 13, "interview")
    assert item["what"].startswith("no word for 27 days since the Final round, 2026-09-24")
    assert "/outcome followup Kestrel Mutual" in item["what"] and item["text"] == ""
    out = open_actions.render_due([item], "2026-10-21")
    assert "Overdue, applications (1" in out and "0 application follow-ups with no recipient" in out


def test_a_stage_still_booked_is_not_silence(tmp_path, monkeypatch):
    _state(tmp_path, monkeypatch, booked="- [ ] Case interview (scheduled 2026-11-02)\n")
    assert open_actions.interview_items([ROW], "2026-10-21") == []


def test_a_status_note_restarts_the_wait_and_two_end_it(tmp_path, monkeypatch):
    _state(tmp_path, monkeypatch, files=("thank_you_2026-09-25.md", "followup_2026-10-09.md"))
    assert open_actions.interview_items([ROW], "2026-10-21") == []      # 12 days since
    (item,) = open_actions.interview_items([ROW], "2026-10-24")
    assert "since the last note you sent, 2026-10-09" in item["what"]
    folder = outreach.app_folder(ROW["company"], ROW["role"])
    with open(os.path.join(folder, "followup_2026-10-24.md"), "w", encoding="utf-8") as fh:
        fh.write("x\n")
    (item,) = open_actions.interview_items([ROW], "2026-11-09")
    assert "2 status notes have gone: record what happened" in item["what"]
    assert "/outcome followup" not in item["what"]


def test_a_do_not_chase_note_holds_it(tmp_path, monkeypatch):
    row = dict(ROW, notes="2026-09-26: DO NOT CHASE until 2026-11-15, panel on leave")
    _state(tmp_path, monkeypatch, row=row)
    (item,) = open_actions.interview_items([row], "2026-10-21")
    assert item["held"] and "DO NOT CHASE" in item["held"][0]


def test_an_offer_or_a_closed_row_is_not_asked_about(tmp_path, monkeypatch):
    for status in ("offer", "rejected"):
        row = dict(ROW, status=status)
        _state(tmp_path / status, monkeypatch, row=row)
        assert open_actions.interview_items([row], "2026-10-21") == [], status
