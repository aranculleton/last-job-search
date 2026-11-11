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


def test_a_short_range_is_read_and_research_or_someone_elses_band_is_not(profile):
    _add(profile, "CLAUDE.md", "- Looking for 110 to 130k.")
    assert [f["said"] for f in C.findings()] == ["110 to 130k"]
    clean = profile / "CLAUDE.md"
    clean.write_text(clean.read_text(encoding="utf-8").replace("- Looking for 110 to 130k.", ""),
                     encoding="utf-8")
    _add(profile, "CLAUDE.md", "- Salary norms for senior analysts in Greater Manchester: "
         "£45,000 - £60,000 (a recruiter's guide).\n"
         '- The recruiter said "our band is £60,000 to £70,000".')
    assert C.findings() == []


def test_sponsorship_said_both_ways_is_caught_and_never_volunteer_is_the_rule(profile):
    _add(profile, "CLAUDE.md", "- Sponsorship required from 2027.")
    assert [f["fact"] for f in C.findings()] == ["sponsorship"]
    clean = profile / "CLAUDE.md"
    clean.write_text(clean.read_text(encoding="utf-8").replace("- Sponsorship required from 2027.", ""),
                     encoding="utf-8")
    _add(profile, "01-candidate-profile.md", "- Name the visa only when asked directly.")
    _add(profile, "07-interview-prep.md", "> Never volunteer the expiry.")
    assert C.findings() == []


def test_a_posting_cut_line_in_the_screening_rules_is_not_a_pay_band(profile):
    """A triage row holds a posting's stated range against a knockout line: "a range topping
    out between 41,000 and 43,999 is ranked down, not cut" is no band of the person's."""
    _add(profile, "10-triage-blockers.md", "| 9 | Pay | a salary range topping out between "
         "41,000 and 43,999 is ranked down, not cut |")
    _add(profile, "01-candidate-profile.md", "- A stated salary range whose top is under "
         "40,000 is cut.")
    assert C.findings() == []


def test_a_posting_maximum_held_below_the_floor_is_a_cut_line_not_the_floor(profile):
    """From a real repo on 2026-10-21: "a range whose maximum is below 100,000 is a cut" sat
    beside a 105,000 walk-away floor, set lower on purpose, and was flagged as a second
    floor. The person had to reword a correct line to clear the question."""
    _add(profile, "CLAUDE.md", "- A stated maximum below GBP 40,000 is a cut, while the floor "
         "stays 42,000.")
    assert C.findings() == []
    _add(profile, "CLAUDE.md", "- My walk-away floor is 45,000.")
    assert [f["fact"] for f in C.findings()] == ["walk-away floor"]


def test_how_to_answer_once_asked_keeps_the_rule_to_wait(profile):
    """"Asked directly how long it runs, state the expiry plainly" is the rule kept, not
    broken: it was flagged as volunteering the expiry."""
    _add(profile, "01-candidate-profile.md", "- Name the visa or its dates only when asked "
         "directly.")
    _add(profile, "07-interview-prep.md", "> Asked directly how long the permit runs, state the "
         "expiry plainly and say what the plan is.")
    assert C.findings() == []


def test_a_finding_the_person_reviewed_and_kept_is_not_raised_again(profile, capsys):
    _add(profile, "CLAUDE.md", "- Walk-away floor is 45,000.")
    [found] = C.findings()
    where = "%s:%d" % (found["file"], found["line"])
    assert C.main(["--reviewed", where]) == 0
    assert "kept as it is" in capsys.readouterr().out
    assert C.findings() == [] and C.main([]) == 0
    assert "reviewed and kept as they are" in capsys.readouterr().out
    saved = json.loads((profile / C.REVIEWED_FILE).read_text(encoding="utf-8"))
    assert saved["reviewed"][0]["said"] == "45,000"
    # A place with nothing raised records nothing; a changed sentence is checked again.
    assert "nothing was recorded" in C.keep(["profile/CLAUDE.md:1"])[0]
    clean = profile / "CLAUDE.md"
    clean.write_text(clean.read_text(encoding="utf-8").replace(
        "- Walk-away floor is 45,000.", "- Walk-away floor is now 45,000."), encoding="utf-8")
    assert [f["fact"] for f in C.findings()] == ["walk-away floor"]


def test_a_notice_the_profile_scopes_on_purpose_is_not_a_contradiction(profile):
    """A helper chat's report of 2026-11-10 (H-7): the contract's three months, written beside
    the line saying it applies with one employer only and every other employer hears the
    shorter notice, became a To do card calling it a contradiction. The explaining line is
    read; a second notice nothing explains is still named. The employer is invented."""
    _add(profile, "01-candidate-profile.md",
         "- Contract: notice of three months, and a restricted period after it.\n"
         "  That applies only with Ashgrove Ledger, the current employer; every other employer "
         "hears one month.")
    assert C.findings() == []
    _add(profile, "CLAUDE.md", "\n- Notice period: two months.")
    assert [(f["fact"], f["said"]) for f in C.findings()] == [("notice period", "two months")]


def test_a_file_outside_the_grounding_sources_ranked_above_the_profile_is_named(profile):
    """The 2026-11-10 audit (PD-4): one person's candidate profile called an old hand-made
    resume the "primary source for facts" and ranked it first, against the rule that the
    profile wins and an older resume is never a source. The file name is invented."""
    _add(profile, "01-candidate-profile.md",
         "Primary source for facts: documents/cv/Morgan_Ellis_Resume_2025.pdf, then this file.")
    got = [(f["fact"], f["said"]) for f in C.findings()]
    assert got == [("where facts come from", "documents/cv/Morgan_Ellis_Resume_2025.pdf")]
    # Naming the profile's own sources that way is the rule, never a finding.
    _add(profile, "CLAUDE.md", "\n01-candidate-profile.md is the source of truth for every fact.")
    assert [f["fact"] for f in C.findings()] == ["where facts come from"]


def test_only_the_notices_own_sentence_or_list_item_can_explain_it(profile):
    """The independent review of H-7 (2026-11-11): any scoping word within two lines, a
    heading included, hid a real second notice period. Only the sentence itself, or its own
    list item, explains it."""
    _add(profile, "CLAUDE.md", "\n## Applies only with recruiters\n- Notice period: two months.")
    assert [f["said"] for f in C.findings()] == ["two months"]


def test_a_neighbouring_list_item_does_not_explain_a_notice(profile):
    _add(profile, "CLAUDE.md", "\n- Notice period: two months.\n"
         "- Every other employer hears about the team only once they ask.")
    assert [f["said"] for f in C.findings()] == ["two months"]


def test_only_a_line_making_a_file_the_source_of_facts_is_named_never_a_negated_one(profile):
    """The independent review of PD-4 (2026-11-11): a bare "overrides", "takes precedence" or
    "outranks", and a line saying a file is never a source, were named as ranking a file
    above the profile."""
    _add(profile, "CLAUDE.md", "\n- The posting's own wording takes precedence over notes.md.\n"
         "- This rule overrides the one in setup.md.\n"
         "- documents/cv/Morgan_Ellis_Resume_2025.pdf is never a source of facts.\n"
         "- An older resume (old_resume.pdf) is not the source of truth.")
    assert C.findings() == []
    _add(profile, "01-candidate-profile.md",
         "Facts come from documents/cv/Morgan_Ellis_Resume_2025.pdf first.")
    assert [f["said"] for f in C.findings()] == ["documents/cv/Morgan_Ellis_Resume_2025.pdf"]
