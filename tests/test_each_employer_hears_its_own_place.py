"""A person who tells different employers different places is served for each one.

From a real repo on 2026-10-21: the person told one employer they were in another city
than the one their profile names. The interview pack, its small talk and the first-note
who-line ("now in <city> after <city>") all assumed the profile's one place, the pack
printed "You live in [CONFIRM: <the whole question>]", and the moved-recently question could
never be answered without naming one place, so it stayed pending and a no lasted a month.

Every person, employer and place here is invented; the candidate is the example person.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network"),
                os.path.dirname(os.path.abspath(__file__))]

import compose  # noqa: E402
import interview_pack as P  # noqa: E402
import person  # noqa: E402
import profile_upgrades as U  # noqa: E402
import told  # noqa: E402
import test_a_referral_process_is_prepared_from_what_was_said as referral  # noqa: E402
from test_a_referral_process_is_prepared_from_what_was_said import (  # noqa: E402
    FIRM, TODAY, _doc, _process)

case = referral.case


def _section(text, title):
    return text.split("## %s\n" % title, 1)[1].split("\n## ", 1)[0]


def test_a_place_told_to_one_employer_is_kept_for_it_alone(case, capsys):
    assert told.places() == {} and told.place(FIRM) == ""
    assert told.main([FIRM, "Leeds"]) == 0
    assert "Calder & Rook Consulting heard: Leeds" in capsys.readouterr().out
    # Joined by company key, never by spelling; another employer hears the person's own.
    assert told.place("Calder and Rook Consulting") == "Leeds"
    assert told.place("Oakmere Foods") == "" and told.differs(FIRM)
    assert not told.differs("Oakmere Foods")
    saved = json.load(open(person.path("person.json"), encoding="utf-8"))
    assert saved["identity"]["places_told"] == {FIRM: "Leeds"}
    # Told the person's own city, it is no different place.
    told.record(FIRM, "Manchester")
    assert not told.differs(FIRM)
    assert told.main([FIRM, "--clear"]) == 0 and told.places() == {}
    assert "places_told" not in json.load(open(person.path("person.json"), encoding="utf-8"))[
        "identity"]


def test_the_pack_says_what_this_employer_heard_and_drops_the_move(case):
    _process()
    told.record(FIRM, "Leeds")
    assert P.main(["pack", FIRM, "--today", TODAY, "--write"]) == 0
    doc = _doc()
    assert "You told Calder & Rook Consulting you are in Leeds" in doc
    assert "You live in Ancoats" not in doc
    # The move is the profile's, not something this employer was told: no settling-in.
    assert "How are you finding" not in doc and "You moved recently" not in doc
    told_section = _section(doc, "What they have been told")
    assert told_section.lstrip().startswith("- You told Calder & Rook Consulting you are in Leeds")


def test_another_employer_still_hears_the_persons_own_place(case):
    _process()
    told.record("Oakmere Foods", "Leeds")
    assert P.main(["pack", FIRM, "--today", TODAY, "--write"]) == 0
    doc = _doc()
    assert "You told" not in doc and "Ancoats" in doc


def test_a_draft_naming_the_persons_own_city_to_that_employer_is_warned(case):
    told.record(FIRM, "Leeds")
    note = ("Hi Ivo, I'm an operations analyst, now in Manchester after Leeds, and I'd like to "
            "hear how your team plans stock.")
    found = [a for a in compose.advise(note, "connection", company=FIRM)
             if a.rule == "place_not_what_they_heard"]
    assert found and found[0].text == "Manchester" and "Leeds" in found[0].fix
    assert not [a for a in compose.advise(note, "connection", company="Oakmere Foods")
                if a.rule == "place_not_what_they_heard"]
    assert not [a for a in compose.advise(note, "connection")
                if a.rule == "place_not_what_they_heard"]


def test_per_employer_answers_the_moved_question_for_good(case):
    path = person.path("person.json")
    data = json.load(open(path, encoding="utf-8"))
    data["identity"]["moved"] = "[CONFIRM: when you moved]"
    data["identity"]["area"] = "[CONFIRM: where you live]"
    json.dump(data, open(path, "w", encoding="utf-8"))
    person.reset()
    assert U.by_id("move-and-area").pending()
    data["identity"].update(moved=told.PER_EMPLOYER, area=told.PER_EMPLOYER)
    json.dump(data, open(path, "w", encoding="utf-8"))
    person.reset()
    assert U.by_id("move-and-area").pending() == ""
    # Kept per employer, "per employer" is nobody's place.
    assert told.home() == data["identity"]["location"]


def test_an_answer_naming_a_place_is_flagged_for_an_employer_told_another(case):
    """For one call the prep printed "my partner and I came over from <city> to build our
    life in <city>" to someone who believed the person was still in the first (2026-10-21)."""
    answer = "My partner and I came over to build our life in Manchester, and I want to stay."
    assert told.clash(answer, FIRM) == ""                       # one place for everyone
    told.record(FIRM, "Leeds")
    said = told.clash(answer, FIRM)
    assert "you told Calder & Rook Consulting you are in Leeds" in said
    # Another employer, with nothing recorded, now that places differ: checked, not trusted.
    other = told.clash(answer, "Oakmere Foods")
    assert "nothing is recorded for Oakmere Foods" in other
    assert told.clash("I build demand forecasts in Python.", "Oakmere Foods") == ""
    # The call prep's check fails it, for that employer only.
    text = ("- **Q.** Why are you looking?\n  **A.** %s\n" % answer)
    import prep
    assert any("Leeds" in why for _q, why in prep.check_answers(text, FIRM))
    assert not any("Leeds" in why for _q, why in prep.check_answers(text))
