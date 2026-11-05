"""A plain thank-you is not refused for what every thank-you says, and a note naming no place
is not warned that it named the wrong one (the maintainer's notes, 2026-11-04).

Every person, employer and place here is invented.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(ROOT, "..", "tools"), os.path.join(ROOT, "..", "tools", "network"), ROOT]

import compose  # noqa: E402
import person  # noqa: E402
import told  # noqa: E402
import test_a_referral_process_is_prepared_from_what_was_said as referral  # noqa: E402
from test_a_referral_process_is_prepared_from_what_was_said import FIRM  # noqa: E402

case = referral.case

THEIRS = ("Hi Morgan, thanks for reaching out. Happy to help where I can: Calder Consulting is "
          "hiring analysts this quarter. Best, Wrenley Ashdown, Calder Consulting")
THANKS = ("Thank you Wrenley, I really appreciate the quick reply. Thanks for the pointers on "
          "Calder Consulting, I will take a look.")


def test_a_short_thank_you_naming_them_and_their_employer_passes(case):
    """Refused before: their name, their employer and "thank" counted as copied words."""
    rules = [v.rule for v in compose.validate(THANKS, "reply", name="Wrenley",
                                              their_message=THEIRS,
                                              employers=["Calder Consulting"])]
    assert "restates_their_points" not in rules


def test_copying_their_own_points_is_still_caught(case):
    copy = ("Hiring analysts this quarter sounds exciting, and reaching out where analysts "
            "are hiring suits me.")
    assert "restates_their_points" in [v.rule for v in compose.validate(
        copy, "reply", name="Wrenley", their_message=THEIRS, employers=["Calder Consulting"])]


def _place_rules(note):
    return [a for a in compose.advise(note, "reply", company=FIRM)
            if a.rule == "place_not_what_they_heard"]


def _area(case):
    path = person.path("person.json")
    data = json.load(open(path, encoding="utf-8"))
    data["identity"]["area"] = "Greater Manchester Area"
    json.dump(data, open(path, "w", encoding="utf-8"))
    person.reset()
    told.record(FIRM, "Leeds")


def test_a_note_naming_no_place_gets_no_place_warning(case):
    _area(case)
    assert not _place_rules("Hi Ivo, thanks for the tip about the area, much appreciated.")


def test_a_note_naming_the_wrong_place_still_does(case):
    _area(case)
    assert _place_rules("Hi Ivo, I'm settled in Manchester now and would love to hear more.")
