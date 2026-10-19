"""A skill the profile says is not held is caught wherever a draft claims it.

`skills.NOT_HELD` kept an unheld skill off the Skills block and nowhere else: a
summary, a letter or a hand edit could still claim it, and check_claims never
looked. `skills_block.unheld_requested` existed to say out loud what the tools
line asked for and could not have, and nothing called it.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import check_claims  # noqa: E402
import fit_to_page  # noqa: E402

CLAIM = "Configured SAP ABAP reports for the planning team across six depots.\n"


def _found(path):
    return [(sev, name) for sev, name, _, _ in check_claims.check(str(path))
            if name == "unheld-skill"]


def test_an_unheld_skill_on_a_resume_is_an_error(tmp_path):
    (tmp_path / "cv").mkdir()
    resume = tmp_path / "cv" / "Morgan_Ellis_CV_Acme.tex"
    resume.write_text(CLAIM, encoding="utf-8")
    assert _found(resume) == [("ERROR", "unheld-skill")]


def test_on_a_letter_it_is_a_warning(tmp_path):
    (tmp_path / "cover_letters").mkdir()
    letter = tmp_path / "cover_letters" / "Morgan_Ellis_Cover_Letter_Acme.tex"
    letter.write_text(CLAIM, encoding="utf-8")
    assert _found(letter) == [("WARN", "unheld-skill")]


def test_a_resume_without_one_is_clean(tmp_path):
    resume = tmp_path / "Morgan_Ellis_CV_Acme.tex"
    resume.write_text("Built weekly demand forecasts in SQL and Python.\n", encoding="utf-8")
    assert _found(resume) == []


def test_the_fit_report_says_what_was_asked_for_and_dropped():
    lines = fit_to_page.unheld_report({"tools": "SQL, ABAP, Power BI",
                                       "posting": "ACCA or CIMA part-qualified; SAP ABAP a plus."})
    assert lines[0].startswith("tools line asked for skills not held, left off: SAP configuration")
    assert "chartered credential" in lines[1] and "SAP configuration" not in lines[1]
    assert fit_to_page.unheld_report({"tools": "SQL", "posting": "SQL and Python"}) == []
