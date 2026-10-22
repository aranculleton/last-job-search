"""A notice period in a letter is flagged with how to ground it, and is clean once grounded.

"I could start within four weeks" was flagged as a number the profile does not hold, and
the finding read like a figure to take out. A notice period is a fact about the person:
the finding now says where to write it, and once it is in the profile it is grounded.
"""
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import check_numbers  # noqa: E402


def test_a_start_date_finding_says_where_to_write_it():
    found = check_numbers.check("I could start within four weeks.", "p4")
    assert [f["value"] for f in found] == ["four weeks"]
    assert "01-candidate-profile.md" in found[0]["hint"]


def test_a_period_of_work_gets_no_such_hint():
    found = check_numbers.check("I rebuilt the pipeline over four weeks of work.", "p4")
    assert found and "hint" not in found[0]


def test_written_in_the_profile_it_is_grounded(tmp_path):
    shutil.copy(os.path.join(ROOT, "profile.example", "01-candidate-profile.md"),
                tmp_path / "01.md")
    with open(tmp_path / "01.md", "a", encoding="utf-8") as fh:
        fh.write("\n- **Notice period:** four weeks\n")
    allowed = check_numbers.grounded([str(tmp_path / "01.md")])
    assert check_numbers.check("I could start within four weeks.", "p4", allowed) == []
