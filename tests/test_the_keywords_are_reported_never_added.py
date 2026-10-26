"""A report of the posting's terms against the page: on it, held but not on it, not held.

The checklist's "posting keywords covered or honestly absent" was a manual read. The
coverage report reads the resume's text layer, which is what a parser sees, and puts each
term the posting names in one of three buckets. It is a report and nothing more: it adds
nothing to any document, and a skill the profile does not hold is listed as not held,
never as one to add.

The posting is invented; the candidate is the example person.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import skills_block as S  # noqa: E402

POSTING = ("Supply Chain Analyst. Strong SQL and Python are essential; Power BI or Tableau a "
           "plus. Experience with SAP is desirable, and CIPS membership is required.")
PAGE = ("Morgan Ellis\nProfile\nOperations analyst working in Python and SQL.\nSkills\n"
        "Languages and modelling: SQL, Python, pandas\nBI, tooling and delivery: Power BI\n")


def test_each_term_is_in_one_bucket():
    report = S.coverage(POSTING, PAGE)
    assert report["on_page"] == ["SQL", "Python, pandas", "Power BI"]
    assert report["held_not_placed"] == ["Tableau"]
    names = [n for n, _near in report["not_held"]]
    # Named as the posting writes it, once, though the profile knows CIPS twice.
    assert names == ["CIPS", "SAP"]
    assert dict(report["not_held"])["SAP"] == "SQL over the warehouse-management system"


def test_a_skill_not_held_is_never_one_to_add():
    lines = S.coverage_lines(S.coverage(POSTING, PAGE))
    assert lines[0] == "on the page (3): SQL; Python, pandas; Power BI"
    assert lines[1] == ("held but not on the page (1): Tableau. Yours to add where it is true, "
                        "if there is room")
    assert lines[2] == ("not held, so never added (2): CIPS; SAP (the nearest you hold: SQL "
                        "over the warehouse-management system)")
    assert not any("add" in ln.lower() for ln in lines[2:] if "never added" not in ln)


def test_a_skill_they_said_yes_to_counts_as_theirs():
    page = PAGE + "SAP\n"
    report = S.coverage(POSTING, page, consented=["SAP"])
    assert "SAP" in report["on_page"]
    assert "SAP" not in [n for n, _ in report["not_held"]]


def test_the_report_changes_nothing(tmp_path):
    # Read from the PDF the batch checks; the draft file is left exactly as it was.
    draft = {"company": "Wrenfield Freight Ltd", "role": "Analyst", "posting": POSTING,
             "abbr": "Wrenfield"}
    path = tmp_path / "drafts.json"
    path.write_text(json.dumps([draft]), encoding="utf-8")
    before = path.read_text(encoding="utf-8")
    import verify_pdf
    from unittest import mock
    with mock.patch.object(verify_pdf, "extract_text_layer", lambda p: (PAGE, 1, "pypdf")):
        lines = verify_pdf.keywords_pdf("unused.pdf", str(path), "Wrenfield")
    assert lines == S.coverage_lines(S.coverage(POSTING, PAGE))
    assert path.read_text(encoding="utf-8") == before


def test_a_draft_with_no_posting_says_so(tmp_path):
    path = tmp_path / "drafts.json"
    path.write_text(json.dumps([{"company": "Wrenfield Freight Ltd", "role": "Analyst",
                                 "abbr": "Wrenfield"}]), encoding="utf-8")
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "verify_pdf.py"), "none.pdf",
                        "--keywords", str(path), "--abbr", "Wrenfield"], capture_output=True,
                       text=True, encoding="utf-8", errors="replace", env=dict(os.environ))
    assert r.returncode == 0
    assert r.stdout.strip() == "no posting kept with this draft, so nothing to measure against"
