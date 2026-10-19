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


def _ctx(contacts, notes="", outcome="", date=""):
    return {"company": "Fernhill", "with": "", "stages": [], "contacts": contacts, "threads": [],
            "row": {"notes": notes, "channel": "referral", "cv_file": ""}, "outcome": outcome,
            "date": date, "folder": person.state("documents", "applications", "fernhill_x")}


def test_the_referrer_is_found_however_their_row_records_it():
    by_outcome = {"contact_id": "f_o", "name": "Tamsin Oyelaran", "company": "Fernhill",
                  "status": "awaiting_reply", "route": "cold",
                  "outcome": "referral_converted_to_interview",
                  "next_action": "Thank her after the interview."}
    lines = interview_pack.warm_lines(_ctx([by_outcome]))
    assert any("Tamsin Oyelaran put you forward" in ln and "Thank her after" in ln for ln in lines)
    assert lines[-1].startswith("- How did you hear about us: through Tamsin Oyelaran.")
    by_notes = dict(by_outcome, outcome="")
    lines = interview_pack.warm_lines(_ctx([by_notes], outcome=HAND_WRITTEN))
    assert any("put you forward" in ln for ln in lines)
    assert not any("put you forward" in ln for ln in interview_pack.warm_lines(_ctx([by_notes])))


@pytest.mark.parametrize("step", [
    "Keep warm, no action. Do not use him to chase the live role.",
    "HOLD: a live interview here. Ask before any new note goes.",
    "Wait for his reply before anything else goes.",
    "Awaiting her response to the update of 2026-10-02.",
    "Referral in. Waiting on their reply; leave him be until then."])
def test_a_row_that_says_to_leave_them_be_is_never_given_a_message(step):
    friend = {"contact_id": "f_h", "name": "Hal Okonedo", "company": "Fernhill",
              "status": "replied", "route": "referral", "next_action": step}
    lines = interview_pack.warm_lines(_ctx([friend], date="2026-10-30"))
    [line] = [ln for ln in lines if "Hal Okonedo" in ln and "hear about us" not in ln]
    assert "leave them be" in line and "booked" not in line
    # Still the route in, so still the answer to how they heard of the role.
    assert lines[-1].startswith("- How did you hear about us: through Hal Okonedo.")


@pytest.mark.parametrize("date,said", [("2026-10-30", "Tell them the interview is booked"),
                                       ("", "Tell them once the interview has a date")])
def test_booked_is_said_only_when_the_stage_has_a_date(date, said):
    referrer = {"contact_id": "f_r", "name": "Hal Okonedo", "company": "Fernhill",
                "status": "referral_in_progress", "route": "referral", "next_action": ""}
    talking = {"contact_id": "f_t", "name": "Juno Castellan", "company": "Fernhill",
               "status": "replied", "route": "cold", "next_action": ""}
    lines = interview_pack.warm_lines(_ctx([referrer, talking], date=date))
    assert any(said in ln for ln in lines)
    if not date:
        assert not any("is booked" in ln for ln in lines)


def test_a_row_is_quoted_whole_or_cut_at_a_word():
    step = ("HOLD until the round is done. " + "Then a short thank-you that names the team "
            "and the one thing he said about how the models reach the Connecting desk.")
    friend = {"contact_id": "f_h", "name": "Hal Okonedo", "company": "Fernhill",
              "status": "replied", "route": "cold", "next_action": step}
    [line] = [ln for ln in interview_pack.warm_lines(_ctx([friend])) if "Hal Okonedo" in ln]
    quoted = line.split('"')[1]
    assert quoted.endswith("...") and step.startswith(quoted[:-3])
    assert step[len(quoted) - 3] == " "                 # the cut falls between two words
    short = dict(friend, next_action="HOLD: ask first.")
    [line] = [ln for ln in interview_pack.warm_lines(_ctx([short])) if "Hal Okonedo" in ln]
    assert '"HOLD: ask first."' in line


def test_every_section_of_an_outcome_file_written_by_hand_reaches_the_pack():
    written = HAND_WRITTEN + """
### What was learned

1. **The team is two people.** The manager said so twice, and it changes
   what the technical round will test.
2. **Likely shape of the next round**, from the recruiter: SQL, then a case.

### Owed

- **Hal Okonedo:** an update after the call.
"""
    lines = interview_pack.earlier_lines(dict(_ctx([], outcome=written), earlier=[],
                                              stages=what_works.outcome_stages(written, "2026-10-19")))
    text = "\n".join(lines)
    assert "- Held: Recruiter screen 2026-09-10" in text
    assert "What the recruiter said, 2026-09-10: Two rounds remain." in text
    assert "What was learned: The team is two people. (source:" in text
    assert "What was learned: Likely shape of the next round, from the recruiter: SQL, then a case." in text
    assert "Owed: Hal Okonedo: an update after the call." in text
    assert "outcome log" not in text                    # the title is not a note


def test_the_notes_of_the_file_outcome_writes_still_come_through():
    written = ("# Outcome: Fernhill - Analyst\n\n**Status:** in_progress\n\n"
               "## Interview stages reached\n- [x] Phone screen (2026-09-02)\n\n## Notes\n"
               "<feedback received, what to do differently>\n"
               "- 2026-09-03: they pressed twice on SAP. Next time lead with the extracts.\n")
    lines = interview_pack.earlier_lines(dict(_ctx([], outcome=written), earlier=[],
                                              stages=what_works.outcome_stages(written)))
    assert any(ln.startswith("- 2026-09-03: they pressed twice on SAP. (source:") for ln in lines)
    assert not any("Phone screen (2026" in ln or "feedback received" in ln for ln in lines)


def test_a_long_record_says_how_much_more_there_is():
    written = "## Notes\n" + "".join("- Note number %d.\n" % n for n in range(30))
    lines = interview_pack.earlier_lines(dict(_ctx([], outcome=written), earlier=[], stages=[]))
    assert len([ln for ln in lines if ln.startswith("- Note number")]) == interview_pack.MAX_RECORD
    assert lines[-1].startswith("- And %d more in " % (30 - interview_pack.MAX_RECORD))


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
