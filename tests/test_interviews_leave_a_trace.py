"""A booked interview is written down, shows on the due list, and counts afterwards.

/interview asked for the stage, the date and who it was with, "skipping anything
outcome.md records", but outcome.md had nowhere to record a stage that was booked
and not yet held, and /outcome was told not to write one. So nothing on disk knew
an interview was coming: the brief could not say "interview on Thursday, no pack
yet", nothing asked for a thank-you afterwards, and how far applications got was
never counted. outcome.md now carries the booked stage as an unticked line,
`- [ ] Phone screen (scheduled 2026-03-14, with Head of Planning)`, and these pin
what reads it.
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
import what_works as W  # noqa: E402

TODAY = "2026-03-11"
ROW = {"date": "2026-02-20", "company": "Kestrel Mutual", "role": "Pricing Analyst",
       "status": "interview", "cv_file": "cv/Morgan_Ellis_CV_Kestrel.tex"}

OUTCOME = """# Outcome: Kestrel Mutual - Pricing Analyst

**Status:** in_progress

## Interview stages reached
- [x] Phone screen (2026-03-02)
- [ ] Technical interview (scheduled {date}, with Head of Pricing)
- [ ] Final round
- [ ] Offer received

## Notes
- 2026-03-02: asked about forecasting under promotions.
"""


def _state(tmp_path, monkeypatch, booked="2026-03-14", files=(), rows=(ROW,)):
    monkeypatch.setenv("LJS_STATE", str(tmp_path))
    with open(tmp_path / "job_search_tracker.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=sorted({k for r in rows for k in r}))
        w.writeheader()
        w.writerows(rows)
    folder = outreach.app_folder(ROW["company"], ROW["role"])
    os.makedirs(folder)
    with open(os.path.join(folder, "outcome.md"), "w", encoding="utf-8") as fh:
        fh.write(OUTCOME.format(date=booked))
    for name in files:
        with open(os.path.join(folder, name), "w", encoding="utf-8") as fh:
            fh.write("x\n")
    return folder


def test_the_stage_lines_are_read_with_their_dates_and_who_they_are_with():
    stages = W.outcome_stages(OUTCOME.format(date="2026-03-14"))
    assert [(s["label"], s["step"], s["done"], s["date"], s["scheduled"], s["with"])
            for s in stages] == [
        ("Phone screen", "screen", True, "2026-03-02", False, ""),
        ("Technical interview", "technical", False, "2026-03-14", True, "Head of Pricing"),
        ("Final round", "final", False, "", False, ""),
        ("Offer received", "offer", False, "", False, ""),
    ]
    assert W.stage_step("Hiring manager interview") == "technical"
    assert W.stage_step("Recruiter call") == "screen"


def test_a_booked_interview_with_no_pack_is_due_today(tmp_path, monkeypatch):
    _state(tmp_path, monkeypatch)
    items = open_actions.interview_items([ROW], TODAY)
    assert [(i["due"], i["late"], i["kind"]) for i in items] == [(TODAY, 0, "interview")]
    assert items[0]["what"] == ("interview in 3 days (Technical interview, 2026-03-14, with Head "
                                "of Pricing), no pack yet: /interview Kestrel Mutual")
    out = open_actions.render_due(items, TODAY)
    head = out.splitlines()
    assert "1 due today" in head[0] and "0 application follow-ups with no recipient" in head[0]
    assert head[3].startswith("Due today (1): Kestrel Mutual (Pricing Analyst)")


def test_a_pack_for_that_stage_closes_it(tmp_path, monkeypatch):
    _state(tmp_path, monkeypatch, files=("interview_prep_technical_interview.md",))
    assert open_actions.interview_items([ROW], TODAY) == []


def test_another_stages_pack_does_not(tmp_path, monkeypatch):
    _state(tmp_path, monkeypatch, files=("interview_prep_phone_screen.md",))
    assert len(open_actions.interview_items([ROW], TODAY)) == 1


def test_a_date_beyond_the_window_waits(tmp_path, monkeypatch):
    _state(tmp_path, monkeypatch, booked="2026-03-30")
    assert open_actions.interview_items([ROW], TODAY) == []


def test_after_the_interview_a_thank_you_is_owed_until_one_is_on_file(tmp_path, monkeypatch):
    _state(tmp_path, monkeypatch, booked="2026-03-09")
    items = open_actions.interview_items([ROW], TODAY)
    assert [(i["due"], i["late"]) for i in items] == [("2026-03-10", 1)]
    assert items[0]["what"].startswith("thank-you not logged after the Technical interview, "
                                       "2026-03-09, with Head of Pricing")


def test_a_thank_you_on_file_closes_it(tmp_path, monkeypatch):
    _state(tmp_path, monkeypatch, booked="2026-03-09", files=("followup_2026-03-09.md",))
    assert open_actions.interview_items([ROW], TODAY) == []


def test_a_closed_application_owes_nothing(tmp_path, monkeypatch):
    rejected = dict(ROW, status="rejected")
    _state(tmp_path, monkeypatch, rows=(rejected,))
    assert open_actions.interview_items([rejected], TODAY) == []


def test_the_employer_view_names_the_booked_stage(tmp_path, monkeypatch):
    _state(tmp_path, monkeypatch)
    entries = open_actions.build([], [], [ROW], TODAY)
    out = open_actions.render(entries, TODAY)
    assert "  - booked: Technical interview 2026-03-14, with Head of Pricing, no pack yet" in out


def test_how_far_applications_get_is_counted_from_the_stages(tmp_path, monkeypatch):
    rows = [ROW,
            {"date": "2026-02-01", "company": "Fernhill Freight", "role": "Operations Analyst",
             "status": "rejected"},
            {"date": "2026-02-03", "company": "Larkspur Retail", "role": "Demand Planner",
             "status": "drafted"}]
    _state(tmp_path, monkeypatch, rows=rows)
    out = W.brief_interviews(rows, rows=[])
    assert "- Of 2 sent: a screen 1 of 2 (50%), a technical or second round 0, a final 0, " \
           "an offer 0." in out
    assert "- Where they stop most: after a screen (1 of 1 went no further)." in out


def test_the_question_bank_names_what_comes_up_again_and_what_landed():
    bank = [
        {"date": "2026-02-02", "company": "Fernhill Freight", "stage": "Phone screen",
         "question": "Why are you leaving?", "story": "", "landed": ""},
        {"date": "2026-03-02", "company": "Kestrel Mutual", "stage": "Phone screen",
         "question": "Why are you leaving ", "story": "", "landed": ""},
        {"date": "2026-03-02", "company": "Kestrel Mutual", "stage": "Phone screen",
         "question": "Tell me about a model you built.", "story": "The forecast that freed safety stock",
         "landed": "yes"},
        {"date": "2026-02-02", "company": "Fernhill Freight", "stage": "Phone screen",
         "question": "How do you handle conflicting numbers?",
         "story": "Replacing eleven spreadsheets with one dataset", "landed": "no"},
    ]
    out = W.brief_interviews([], rows=bank)
    assert '- Asked 2 times: "Why are you leaving" (last at Kestrel Mutual, Phone screen).' in out
    assert "- Stories that landed: The forecast that freed safety stock (1 of 1 times told)." in out
    assert "- Stories that fell flat: Replacing eleven spreadsheets with one dataset" in out


def test_the_brief_runs_on_the_example_person(capsys):
    assert W.main(["brief", "interviews"]) == 0
    assert capsys.readouterr().out.strip()
