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


def test_an_achievement_after_joining_gets_no_such_hint():
    # Grounding "six weeks" by writing it in the profile would ground an achievement figure.
    found = check_numbers.check("Within six weeks of joining, I rebuilt the pipeline and cut "
                                "the run from three days to four hours.", "p4")
    assert found and all("hint" not in f for f in found)


def test_notice_wording_in_its_usual_forms_gets_the_hint():
    for text in ("I am available to start in four weeks.", "I can join within six weeks.",
                 "My notice period is four weeks.", "I would need four weeks' notice."):
        found = check_numbers.check(text, "p4")
        assert found and "hint" in found[0], text


def test_the_audit_keeps_its_own_advice_beside_the_hint():
    import draft_audit
    src = open(draft_audit.__file__, encoding="utf-8").read()
    assert 'f"{said}; or, {f[\'hint\']}"' in src


def test_written_in_the_profile_it_is_grounded(tmp_path):
    shutil.copy(os.path.join(ROOT, "profile.example", "01-candidate-profile.md"),
                tmp_path / "01.md")
    with open(tmp_path / "01.md", "a", encoding="utf-8") as fh:
        fh.write("\n- **Notice period:** four weeks\n")
    allowed = check_numbers.grounded([str(tmp_path / "01.md")])
    assert check_numbers.check("I could start within four weeks.", "p4", allowed) == []
