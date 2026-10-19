"""An interview pack built from the application as the person actually wrote it down.

From one person's live interview: the tracker named the role with its requisition
number, so the pack looked for a folder that did not exist and built from nothing; the
outcome file was written by hand, one heading per round, so it found no stages; it
missed the referrer, whose row recorded the referral in its outcome; and it told the
candidate to message someone whose row said to leave him be. Saving one contact
rewrote the whole contact book. Invented people and employers only.
"""
from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "network"))

import csv_store  # noqa: E402
import interview_pack  # noqa: E402
import outreach  # noqa: E402
import person  # noqa: E402
import what_works  # noqa: E402

ROLE = "Data Scientist II (R_1234567)"
HAND_WRITTEN = """# Fernhill - Data Scientist II - outcome log

## Round 1 - 2026-09-10 - Recruiter screen

### What the recruiter said, 2026-09-10

Two rounds remain. The referral from Tamsin Oyelaran was named as the route in.

## Round 2 - 2026-10-30 - Technical interview
"""


@pytest.mark.parametrize("role,bare", [
    (ROLE, "Data Scientist II"), ("Analyst [JR166447]", "Analyst"),
    ("Planner - REQ-20931", "Planner"), ("Data Scientist II", "Data Scientist II"),
    ("Analyst (Remote)", "Analyst (Remote)")])
def test_a_requisition_number_is_not_part_of_the_role(role, bare):
    assert outreach.without_ref(role) == bare


def test_the_folder_named_before_the_number_was_written_is_found():
    folder = person.state("documents", "applications", "fernhill_data_scientist_ii")
    os.makedirs(folder, exist_ok=True)
    assert outreach.app_folder("Fernhill", ROLE) == folder


def test_no_pack_is_built_from_a_folder_that_is_not_there():
    os.makedirs(person.state("documents", "applications", "kestrel_pricing_analyst"), exist_ok=True)
    tracker = [{"company": "Kestrel", "role": "Demand Planner (R_998877)", "status": "interview"}]
    with pytest.raises(LookupError, match="kestrel_pricing_analyst"):
        interview_pack.gather("Kestrel", tracker=tracker, contacts=[], threads=[])


def test_stages_written_by_hand_are_read_from_their_headings():
    stages = what_works.outcome_stages(HAND_WRITTEN, today="2026-10-19")
    assert [(s["label"], s["done"], s["scheduled"], s["date"]) for s in stages] == [
        ("Recruiter screen", True, False, "2026-09-10"),
        ("Technical interview", False, True, "2026-10-30")]
    ticked = "## Interview stages reached\n- [x] Phone screen (2026-09-10)\n" + HAND_WRITTEN
    assert [s["label"] for s in what_works.outcome_stages(ticked)] == ["Phone screen"]


def test_after_every_stage_on_record_the_next_is_the_next_round():
    held = [{"label": "Screen", "done": True, "scheduled": False, "date": "2026-09-10", "with": ""}]
    assert interview_pack._next_stage(held)["label"] == "Round 2"
    assert interview_pack._next_stage([]) == {}


def _ctx(contacts, notes="", outcome=""):
    return {"company": "Fernhill", "with": "", "stages": [], "contacts": contacts, "threads": [],
            "row": {"notes": notes, "channel": "referral", "cv_file": ""}, "outcome": outcome}


def test_the_referrer_is_found_however_their_row_records_it():
    by_outcome = {"contact_id": "f_o", "name": "Tamsin Oyelaran", "company": "Fernhill",
                  "status": "awaiting_reply", "route": "cold",
                  "outcome": "referral_converted_to_interview", "next_action": "Wait for her reply."}
    lines = interview_pack.warm_lines(_ctx([by_outcome]))
    assert any("Tamsin Oyelaran put you forward" in ln and "Wait for her reply." in ln for ln in lines)
    assert lines[-1].startswith("- How did you hear about us: through Tamsin Oyelaran.")
    by_notes = dict(by_outcome, outcome="")
    lines = interview_pack.warm_lines(_ctx([by_notes], outcome=HAND_WRITTEN))
    assert any("put you forward" in ln for ln in lines)
    assert not any("put you forward" in ln for ln in interview_pack.warm_lines(_ctx([by_notes])))


@pytest.mark.parametrize("step", [
    "Keep warm, no action. Do not use him to chase the live role.",
    "HOLD: a live interview here. Ask before any new note goes."])
def test_a_row_that_says_to_leave_them_be_is_never_given_a_message(step):
    friend = {"contact_id": "f_h", "name": "Hal Okonedo", "company": "Fernhill",
              "status": "replied", "route": "alumni_school", "next_action": step}
    [line] = [ln for ln in interview_pack.warm_lines(_ctx([friend])) if "Hal Okonedo" in ln]
    assert "leave them be" in line and "tell them it is booked" not in line


def test_saving_one_row_changes_one_line(tmp_path):
    path = tmp_path / "book.csv"
    path.write_text("id,name\n" + "".join(f"{n},Person {n}\n" for n in range(50)))
    rows = csv_store.read_rows(str(path), ["id", "name", "found_via"])
    before = path.read_text().splitlines()
    csv_store.write_rows(str(path), rows + [{"id": "50", "name": "Person 50"}], ["id", "name", "found_via"])
    after = path.read_text().splitlines()
    assert after[:-1] == before and after[-1] == "50,Person 50"      # no empty column added
    rows = csv_store.read_rows(str(path), ["id", "name", "found_via"])
    rows[0]["found_via"] = "export"
    csv_store.write_rows(str(path), rows, ["id", "name", "found_via"])
    assert path.read_text().splitlines()[0] == "id,name,found_via"   # added once it is used
