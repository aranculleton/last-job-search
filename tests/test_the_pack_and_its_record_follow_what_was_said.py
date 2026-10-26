"""The interview pack and its record follow what the person said and booked.

Three things the interview audit found (2026-10-25): the one screen went on saying "ask
you first" over a reason the person had already written under the question; a question
recorded with `asked` and no --role went into the bank with a blank role, and was never
matched to its stage's pack again; and a stage given to `pack --write` with its date was
used for that one pack and recorded nowhere, so the brief could not remind of it. Every
person and employer is invented (tests/test_interview_pack.py's fixture).
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tests"), os.path.join(ROOT, "tools"),
                os.path.join(ROOT, "tools", "network")]

import interview_pack as P  # noqa: E402
import what_works  # noqa: E402
from test_interview_pack import COMPANY, ROLE, TODAY, _ctx  # noqa: E402
from test_interview_pack import app as app  # noqa: E402,F401  the fixture, by name


def _screen(text):
    return text.split("**Likely questions, and what to answer with**")[1].split("**Hooks**")[0]


def test_a_reason_they_wrote_is_no_longer_asked_for_on_the_one_screen(app):
    before = _screen(P.pack_markdown(_ctx(stage="Final round"), never_say=[]))
    assert "Why Fernhill Freight? -> ask you first" in before
    with open(os.path.join(app, P.LIVING), "w", encoding="utf-8") as fh:
        fh.write("# Interview prep\n\n## Your answers\n\n### Why Fernhill Freight?\n"
                 "I want to plan stock for a network that is still growing, and the "
                 "Warrington site shows it is.\n")
    after = _screen(P.pack_markdown(_ctx(stage="Final round"), never_say=[]))
    assert "Why Fernhill Freight? -> your answer, below" in after
    # A reason still unwritten is still asked for.
    assert "Where do you see yourself in five years? -> ask you first" in after


def test_a_question_recorded_without_a_role_takes_the_applications(app, capsys):
    assert P.main(["asked", "--company", COMPANY, "--stage", "Phone screen",
                   "--question", "Why planning, not finance?", "--date", TODAY]) == 0
    rows = [r for r in what_works.bank() if r["question"] == "Why planning, not finance?"]
    assert [r["role"] for r in rows] == [ROLE]


def test_a_question_at_an_employer_with_no_application_says_no_role_was_kept(app, capsys):
    assert P.main(["asked", "--company", "Quayside Foods", "--stage", "Phone screen",
                   "--question", "Why food?", "--source", "a contact who interviewed there",
                   "--date", TODAY]) == 0
    assert "no role is recorded with it: --role names one" in capsys.readouterr().out


def test_a_stage_given_to_a_written_pack_is_booked_in_outcome_md(app, capsys):
    assert P.main(["pack", COMPANY, "--stage", "Final round", "--date", "2026-03-20",
                   "--with", "Shirin Example", "--today", TODAY, "--write"]) == 0
    out = capsys.readouterr().out
    assert "booked in" in out and "Final round (scheduled 2026-03-20, with Shirin Example)" in out
    with open(os.path.join(app, "outcome.md"), encoding="utf-8") as fh:
        record = fh.read()
    assert "- [ ] Final round (scheduled 2026-03-20, with Shirin Example)" in record
    assert record.count("Final round") == 1
    # The brief and the next pack read it back as booked.
    stages = what_works.outcome_stages(record, TODAY)
    assert any(s["label"] == "Final round" and s["date"] == "2026-03-20" for s in stages)


def test_a_pack_shown_but_not_written_books_nothing(app, capsys):
    with open(os.path.join(app, "outcome.md"), encoding="utf-8") as fh:
        before = fh.read()
    assert P.main(["pack", COMPANY, "--stage", "Final round", "--date", "2026-03-20",
                   "--today", TODAY]) == 0
    with open(os.path.join(app, "outcome.md"), encoding="utf-8") as fh:
        assert fh.read() == before
