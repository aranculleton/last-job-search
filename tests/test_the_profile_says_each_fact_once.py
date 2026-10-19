"""The facts a recruiter checks first are said the same way everywhere in the profile.

One person's candidate profile gave one target band and the rubric another, so an interview
pack could quote either to a recruiter who already had the other from the form; and their
stock permit answer said to volunteer the expiry while their own rule was to name the permit
only when asked. tools/profile_consistency.py names each such place, against the source
screening_answers.py reads. The example person stands in; the edits are invented.
"""
from __future__ import annotations

import importlib
import json
import os
import shutil
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import company_research  # noqa: E402
import person  # noqa: E402
import profile_consistency as C  # noqa: E402
import screening_answers  # noqa: E402


@pytest.fixture
def profile(tmp_path, monkeypatch):
    p = tmp_path / "profile"
    shutil.copytree(os.path.join(ROOT, "profile.example"), p,
                    ignore=shutil.ignore_patterns("__pycache__", "state"))
    monkeypatch.setenv("LJS_PROFILE", str(p))
    person.reset()
    importlib.reload(screening_answers)
    yield p
    monkeypatch.undo()
    person.reset()
    importlib.reload(screening_answers)


def _add(profile, name, text):
    path = profile / name
    path.write_text(path.read_text(encoding="utf-8") + "\n" + text + "\n", encoding="utf-8")


def test_the_example_profile_is_consistent(profile):
    assert C.findings() == []
    assert C.main([]) == 0


def test_a_second_band_is_named_against_the_rubric(profile, capsys):
    _add(profile, "01-candidate-profile.md", "- Salary target: GBP 52,000 to 60,000.")
    found = C.findings()
    assert [(f["fact"], f["file"]) for f in found] == [("pay band", "profile/01-candidate-profile.md")]
    assert "48,000 to 58,000" in found[0]["source"]
    assert C.main([]) == 1 and "52,000 to 60,000" in capsys.readouterr().out


def test_what_they_earn_now_or_a_market_band_is_not_a_target(profile):
    _add(profile, "01-candidate-profile.md", "- Current salary: GBP 41,000 base.\n"
         "- Market band for the role: 45,000 to 62,000 (levels.fyi).")
    assert C.findings() == []


def test_a_different_floor_and_notice_are_named(profile):
    _add(profile, "CLAUDE.md", "- Walk-away floor is 45,000.\n- Notice period: two months.")
    facts = sorted(f["fact"] for f in C.findings())
    assert facts == ["notice period", "walk-away floor"]


def test_a_question_quoted_is_not_a_position_on_sponsorship(profile):
    _add(profile, "07-interview-prep.md", '### "Will you require sponsorship in future?"\n'
         '> No. I need no sponsorship.\n\n'
         'Answer "do you now or will you in the future require sponsorship?" with a plain no.')
    assert C.findings() == []
    _add(profile, "CLAUDE.md", "- I will need sponsorship after next year.")
    assert [f["fact"] for f in C.findings()] == ["sponsorship"]


def test_volunteering_the_expiry_contradicts_a_rule_to_wait_until_asked(profile):
    _add(profile, "01-candidate-profile.md", "- Name the visa or its dates only when asked "
         "directly.")
    _add(profile, "07-interview-prep.md", "> Confirm the right to work, state the expiry plainly, "
         "and say what the plan is.")
    found = C.findings()
    assert [f["fact"] for f in found] == ["permit disclosure"]
    assert found[0]["file"] == "profile/07-interview-prep.md"


def test_an_unreadable_source_is_said_never_passed(profile, capsys):
    ev = profile / "04-job-evaluation.md"
    ev.write_text(ev.read_text(encoding="utf-8").replace("**Target**", "Target"), encoding="utf-8")
    unread = []
    assert C.findings(unread) == []
    assert unread and unread[0].startswith("pay band")
    C.main([])
    assert "Not checked, pay band" in capsys.readouterr().out


def test_research_merges_teams_and_what_was_not_found(tmp_path):
    root = str(tmp_path)
    company_research.save("Calder & Rook", {"teams": {"Operations Practice": ["a"]},
                                            "not_found": ["interview_process"]}, root)
    company_research.save("Calder & Rook", {"teams": {"Data Platform": ["b"]},
                                            "not_found": ["team:Data Platform"]}, root)
    data, _age, _fresh = company_research.load("Calder & Rook", root=root)
    assert set(data["teams"]) == {"Operations Practice", "Data Platform"}
    assert data["not_found"] == ["interview_process", "team:Data Platform"]
    assert json.dumps(data)
