"""A told place is checked where an answer says where the person lives, and nowhere else.

From the sync audit, 2026-10-21, once one employer was recorded as told another city:
- "I moved our weekly reporting from spreadsheets to dbt", "the dashboards live in Power
  BI", "moving fast" and "relocated the team to the new platform" were flagged as saying
  the wrong place, at that employer and at every other one, so an answer that passed its
  check failed it the day a place was recorded somewhere else.
- "I would like to be based in Leeds" was flagged at the very employer told Leeds.
- Any word of the home place counted: a home in the North West or New York made "north"
  and "new" a clash.
- The stock answer under "Where they will push" was printed with no check, while the same
  answer under Your answers was marked Careful; and an answer under a heading of the
  person's own was checked for everything but the place.
- Two places sharing a word (a city and its namesake in another country) were one place.

Every person, employer, place and answer here is invented; the candidate is the example
person.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network"),
                os.path.dirname(os.path.abspath(__file__))]

import interview_pack as P  # noqa: E402
import outreach  # noqa: E402
import person  # noqa: E402
import told  # noqa: E402
import test_a_referral_process_is_prepared_from_what_was_said as referral  # noqa: E402
from test_a_referral_process_is_prepared_from_what_was_said import (  # noqa: E402
    FIRM, ROLE, TODAY, _doc, _process)

case = referral.case
OTHER = "Oakmere Foods"


@pytest.mark.parametrize("answer", [
    "I moved our weekly reporting from spreadsheets to dbt, which cut the refresh to an hour.",
    "The dashboards live in Power BI, and I own the models behind them.",
    "Our team was moving fast, so I wrote the validation tests first.",
    "My manager relocated the whole team to the new platform in a quarter.",
    "I moved it to dbt and Power BI so the numbers matched.",
    "We moved to Snowflake in 2024, and I rebuilt the loads.",
    "I moved to Brindle & Hart Logistics after two years at the agency.",
    "I'd join the Manchester planning team in its first year.",
])
def test_a_sentence_about_work_is_never_a_place(case, answer):
    told.record(FIRM, "Leeds")
    assert told.clash(answer, FIRM) == ""
    assert told.clash(answer, OTHER) == ""


@pytest.mark.parametrize("answer, said", [
    ("My partner and I came over to build our life in Manchester, and I want to stay.",
     "Manchester"),
    ("I moved to Manchester two years ago.", "Manchester"),
    ("I live in Ancoats now, close to the river.", "Ancoats"),
    ("We've settled in London and we love it.", "London"),
    ("Since moving to Manchester, I've joined a running club.", "Manchester"),
])
def test_a_sentence_saying_where_they_live_is_checked(case, answer, said):
    told.record(FIRM, "Leeds")
    why = told.clash(answer, FIRM)
    assert why.startswith("you told %s you are in Leeds, and this answer says \"%s\"" % (FIRM, said))
    assert "nothing is recorded for %s" % OTHER in told.clash(answer, OTHER)


def test_the_place_that_employer_heard_is_never_a_clash(case):
    told.record(FIRM, "Leeds")
    for answer in ("I would like to be based in Leeds, close to the team.",
                   "I'm based in Leeds.", "We live in Leeds, UK."):
        assert told.clash(answer, FIRM) == "", answer


def _home(where):
    path = person.path("person.json")
    data = json.load(open(path, encoding="utf-8"))
    data["identity"].update(area=where, location=where)
    json.dump(data, open(path, "w", encoding="utf-8"))
    person.reset()


def test_a_place_is_matched_by_its_whole_name_never_a_word(case):
    _home("North West")
    told.record(FIRM, "New York")
    assert told.differs(FIRM)
    for answer in ("We started a new project to the north of the river.",
                   "Our area team moved fast in the new year."):
        assert told.clash(answer, FIRM) == "", answer
    assert "North West" in told.clash("I live in the North West with my partner.", FIRM)
    assert told.clash("I'm based in New York.", FIRM) == ""


def test_a_city_and_its_namesake_are_two_places(case):
    _home("London, Ontario")
    told.record(FIRM, "London, UK")
    assert told.differs(FIRM)
    assert told.same_place("Leeds", "Leeds, UK") and told.same_place("Manchester",
                                                                     "Chorlton, Manchester")
    assert not told.same_place("York", "New York")
    told.record(FIRM, "London, Ontario")
    assert not told.differs(FIRM)


STOCK = {"question": "Why did you leave Saltmarsh Analytics so soon?", "alternatives": [],
         "use_for": [], "confirm": False, "source": "profile/07-interview-prep.md", "fill_in": "",
         "suits": (), "not_for": (),
         "answer": "I moved to Manchester for my partner's job, and Saltmarsh had no office "
                   "there, so I made the move to Oakmere Foods."}


def test_where_they_will_push_marks_the_answer_as_your_answers_does(case):
    _process()
    told.record(FIRM, "Leeds")
    ctx = P.gather(FIRM, ROLE, stage="Recruiter screen", today=TODAY)
    ctx["facts"] = dict(ctx["facts"], employers=[
        {"company": "Oakmere Foods", "title": "Supply Chain Data Analyst",
         "dates": "Apr 2020 - Present"},
        {"company": "Saltmarsh Analytics", "title": "Analyst", "dates": "Sep 2019 - Mar 2020"}])
    ctx["answers"] = [STOCK]
    push = next(m for m in P.landmines(ctx) if "Saltmarsh" in m["what"])
    assert push["framing"][0].startswith("Careful: you told %s you are in Leeds" % FIRM)
    assert push["framing"][1].startswith("Prepared: I moved to Manchester")


def test_an_answer_under_a_heading_of_their_own_is_checked_for_the_place(case):
    _process()
    told.record(FIRM, "Leeds")
    path = os.path.join(outreach.app_folder(FIRM, ROLE), P.LIVING)
    text = _doc().rstrip() + ("\n\n## If it goes to a panel\n\n### Why did you move cities?\n"
                              "I moved to Manchester for my partner's job, and I'm settled "
                              "here now.\n")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    found = dict(P.check(path))
    assert found["Why did you move cities?"].startswith("you told %s you are in Leeds" % FIRM)
