"""Deeper prep written into the living document reaches the page, follow-ups and all (issue 362).

Hours before an interview a chat added new `### Question?` sections, each with
`**If they follow up: "..."**` lines, to the stage's interview_prep.md and brought the page up
to date. Edits to answers already there reached the page; the new questions and their
follow-ups did not, because the page read only the questions the pack listed under Likely
questions, and the follow-up lines were read as part of the answer above them. The pack
itself gave technical answers one layer, no follow-ups, and described a modelling story by
the language it was written in rather than the model and method the profile records.

Every person, employer and answer here is invented: the example person, and the made-up
application `tests/test_interview_pack.py` builds.
"""
from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network"),
                os.path.dirname(os.path.abspath(__file__))]

import interview_pack as P  # noqa: E402
from test_interview_pack import _ctx, app  # noqa: E402,F401

pytestmark = pytest.mark.usefixtures("app")

ADDED = """### Why did you pick that forecasting approach?
I started with the simplest seasonal baseline, because the planners needed something they could check by hand.

**If they follow up: "What did you compare it against?"**
Last year's same week, and the planners' own numbers, site by site.

  **If they follow up: "How did you decide it was better?"**
  I tracked the error by distribution centre for six weeks before anyone relied on it.

**If they follow up: "What would you change now?"**
"""



def _read(path) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()

def _add(path, block):
    text = _read(path)
    head, rest = text.split("## Your answers\n", 1)
    body, tail = rest.split("\n## ", 1)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(head + "## Your answers\n" + body.rstrip("\n") + "\n\n" + block + "\n## " + tail)


def test_a_question_added_under_your_answers_is_shown_with_its_follow_ups():
    path = P.write_pack(_ctx())
    _add(path, ADDED)
    read = P.reading(_read(path), "Fernhill Freight")
    got = {q["question"]: q for q in read["questions"]}
    q = got.get("Why did you pick that forecasting approach?")
    assert q is not None, "a question added under Your answers never reached the page"
    assert q["added"] is True
    # The answer is the answer: never the follow-ups' words run into it.
    assert q["answer"].startswith("I started with the simplest seasonal baseline")
    assert "Last year's same week" not in q["answer"]
    first, second = q["follow"]
    assert first["question"] == "What did you compare it against?"
    assert first["answer"].startswith("Last year's same week")
    # The follow-up to the follow-up, nested under it.
    assert first["follow"][0]["question"] == "How did you decide it was better?"
    assert first["follow"][0]["answer"].startswith("I tracked the error")
    # One still to write is shown as a question with no answer yet.
    assert second["question"] == "What would you change now?" and second["answer"] is None
    # And a rebuild keeps it, as the person's own.
    P.write_pack(_ctx())
    again = P.reading(_read(path), "Fernhill Freight")
    assert "Why did you pick that forecasting approach?" in {x["question"] for x in again["questions"]}


def test_a_technical_question_has_follow_ups_two_deep_to_answer():
    path = P.write_pack(_ctx())
    text = _read(path)
    block = text.split("### Tell me about your experience with demand forecasting.\n", 1)[1]
    block = block.split("\n### ", 1)[0]
    tree = P.split_follow(block.splitlines())[1]
    assert len(tree) >= 2, block
    assert all(node["follow"] for node in tree), "each follow-up has the one asked after it"
    # The page has them as questions to answer, two deep.
    read = P.reading(text, "Fernhill Freight")
    q = next(x for x in read["questions"]
             if x["question"] == "Tell me about your experience with demand forecasting.")
    assert q["follow"] and q["follow"][0]["follow"]
    # Never words to say: the answer is still unwritten, and the check still says so.
    assert q["answer"] is None
    # A question that is not technical has none.
    motive = text.split("### Tell me about yourself.\n", 1)[1].split("\n## ", 1)[0]
    assert not P.split_follow(motive.splitlines())[1]


def test_a_modelling_answer_is_said_from_the_model_and_method_the_profile_records(tmp_path,
                                                                                    monkeypatch):
    # The example person's story records only the language ("in Python and SQL"): the pack
    # says so, and asks for the model rather than letting the answer stop at the language.
    text = _read(P.write_pack(_ctx()))
    assert P.NO_METHOD_MARK in text
    # A profile that records the model for the same work (a line sharing its figures): the
    # pack names it for the answer to say.
    profile = tmp_path / "profile.md"
    profile.write_text("- Built weekly demand forecasts as gradient-boosted trees (LightGBM), "
                       "validated with a rolling backtest, cutting forecast error from 22% to "
                       "14%\n", encoding="utf-8")
    real = P.person.file
    monkeypatch.setattr(P.person, "file", lambda key, default: str(profile)
                        if key == "candidate_profile" else real(key, default))
    text = P.pack_markdown(_ctx(), never_say=[])
    line = next(ln for ln in text.splitlines() if P.METHOD_MARK in ln)
    assert "gradient-boosted trees" in line and "LightGBM" in line and "backtest" in line
    assert P.language_only("I rebuilt it in Python and SQL.", ["LightGBM"])
    assert not P.language_only("I built it as gradient-boosted trees in Python.", ["LightGBM"])
