"""Your profile on the page (Settings, model `you`): what the profile holds, read the way the
person would list it, and what it still lacks. Every change is `profile` work for a chat; this
only reads. The example person is invented (profile.example/)."""
from __future__ import annotations

import os
import shutil
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import app_model  # noqa: E402
import page_db  # noqa: E402
import person  # noqa: E402


@pytest.fixture
def profile(tmp_path, monkeypatch):
    d = tmp_path / "profile"
    shutil.copytree(os.path.join(ROOT, "profile.example"), d, ignore=shutil.ignore_patterns("state", "tests"))
    monkeypatch.setenv("LJS_PROFILE", str(d))
    person._modules.clear()
    yield d
    person._modules.clear()


def test_latex_in_the_profile_reads_as_plain_words():
    got = app_model._plain_list(r"Forecasting certificate (2026) \textbullet{} A\kern0pt WS certificate (2026) "
                                r"\textbullet{} \textbf{dbt} certificate (in progress)")
    assert got == ["Forecasting certificate (2026)", "AWS certificate (2026)", "dbt certificate (in progress)"]
    assert app_model.tex_plain(r"\textbf{BSc Mathematics}, University of Leeds (2016--2019).") == \
        "BSc Mathematics, University of Leeds (2016-2019)"


def test_the_example_profile_lists_its_jobs_skills_and_education_with_nothing_missing(profile):
    you = app_model._you(None, {})
    assert [j["employer"] for j in you["jobs"]] == ["Brindle & Hart Logistics", "Oakmere Foods",
                                                    "Saltmarsh Analytics"]
    assert all(j["lines"] > 0 for j in you["jobs"])
    assert "SQL" in you["skills"] and you["education"] and you["certificates"]
    assert you["missing"] == []


def test_a_half_finished_profile_says_what_is_missing(profile):
    # A job added with nothing yet on what was done there, no skills, and a fact to confirm.
    roles = profile / "roles.py"
    roles.write_text(roles.read_text(encoding="utf-8").replace(
        "ROLES = [", 'ROLES = [\n    dict(employer="Fenwick Mills", title="Planner", dates="2018 - 2019", loc="York, UK"),', 1),
        encoding="utf-8")
    (profile / "skills.py").write_text(
        (profile / "skills.py").read_text(encoding="utf-8").replace("ITEMS = [", "ITEMS = [] and [", 1),
        encoding="utf-8")
    md = profile / "01-candidate-profile.md"
    md.write_text(md.read_text(encoding="utf-8") + "\n- Notice period [CONFIRM: one month?]\n", encoding="utf-8")
    person._modules.clear()
    missing = {m["part"]: m for m in app_model._you(None, {})["missing"]}
    assert missing["lines"]["say"] == "What you did as Planner at Fenwick Mills"
    assert "skills" in missing and missing["confirm"]["say"] == "1 detail to check"


def test_a_profile_change_is_work_a_chat_can_take():
    assert "profile" in page_db.WORK_KINDS and page_db.WORK_KINDS["profile"]["heavy"] is False
