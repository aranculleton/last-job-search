"""A heading word in a sentence is not a heading; a heading in a run-together body still is.

The splitter breaks a body whose line breaks were lost at the headings in it ("Who We're
Looking For", "Requirements", "Preferred Qualifications"), and it took the words alone as
a heading wherever they stood: "Actuarial qualifications are not required" was split at
"qualifications", and "Candidates who meet the requirements will be invited" at
"requirements", so each half was read as a sentence of its own. "Preferred
Qualifications" was split too, leaving "Preferred" on its own and the list under it read
as required. A heading inside a piece is now one written as a heading: a capital to open
it, and after it a colon, a dash, a capital, a figure or the end. Sentence ends are split
as they were.
"""
from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import text_screen as T  # noqa: E402

PROSE = (
    "Actuarial qualifications are not required, but you will be supported to study.",
    "Candidates who meet the requirements will be invited to a first interview.",
    "You will own the responsibilities of the outgoing analyst from day one.",
    "We review your experience with SQL and Python at the first stage.",
    "Tell us about you and your experience in a short cover note.",
    "Formal Qualifications matter less to us than what you have built.",
    "Strong SQL is one of the key qualifications for this role.",
    "We know what you need to grow, and we will support your development.",
)
BLOBS = (
    ("We have been in business since 1994 and serve customers nationwide Who We're Looking "
     "For 5+ years of experience in data science",
     ["We have been in business since 1994 and serve customers nationwide",
      "Who We're Looking For 5+ years of experience in data science"]),
    ("Build demand forecasts for the planning team Qualifications Bachelor's degree in "
     "statistics 3+ years of SQL",
     ["Build demand forecasts for the planning team",
      "Qualifications Bachelor's degree in statistics 3+ years of SQL"]),
    ("We are a leading provider of freight services Preferred Qualifications Fluent Spanish "
     "Experience with Tableau",
     ["We are a leading provider of freight services",
      "Preferred Qualifications Fluent Spanish Experience with Tableau"]),
    ("Analytics team in Leeds MINIMUM QUALIFICATIONS 5+ years in analytics",
     ["Analytics team in Leeds", "MINIMUM QUALIFICATIONS 5+ years in analytics"]),
    ("Great team culture and flexible working Responsibilities: own the weekly forecast",
     ["Great team culture and flexible working",
      "Responsibilities: own the weekly forecast"]),
)
# Sentence ends split exactly as they did.
ENDS = (
    ("Fluent Spanish is required. We are an equal opportunity employer.", 2),
    ("5+ yrs. of experience is required.", 1),
    ("Ph.D. in statistics required.", 1),
    ("Applicants must be U.S. citizens.", 1),
    ("Based in the U.S. We are an equal opportunity employer.", 2),
    ("Requirements:\n- SQL\n- Python", 3),
    ("You will use Python or R. Our team is small.", 2),
)


@pytest.mark.parametrize("sentence", PROSE)
def test_a_heading_word_in_prose_does_not_split_the_sentence(sentence):
    assert T.sentences(sentence) == [sentence]


@pytest.mark.parametrize("blob,pieces", BLOBS)
def test_a_heading_in_a_run_together_body_still_splits_it(blob, pieces):
    assert T.sentences(blob) == pieces


@pytest.mark.parametrize("text,count", ENDS)
def test_sentence_ends_split_as_they_did(text, count):
    assert len(T.sentences(text)) == count


def test_what_the_split_lost_is_read_again():
    """The halves the split made each lost the words that decide them."""
    body = ("As an Actuarial Analyst you will price motor policies. You will progress through "
            "your actuarial exams with study leave. Our actuarial function reports to the "
            "Chief Actuary. Actuarial qualifications are not required, but you will be "
            "supported to study.")
    assert not [c for c in T.screen({"title": "Actuarial Analyst", "desc": body})["cuts"]
                if "professional designation" in c]
    blob = ("We are a leading provider of freight services Preferred Qualifications Fluent "
            "Spanish Experience with Tableau")
    assert T.screen({"title": "Planning Analyst", "desc": blob})["cuts"] == []
