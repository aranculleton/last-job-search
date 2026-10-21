"""A sentence ending on "the U.S." is a place, and the next sentence is its own.

The eligibility gate joins a sentence ending on an initialism to the next one, so that
"Applicants must be a U.S." and "Citizen or Permanent Resident." are read as the status
they state. It joined everything that way, and took the condition from the first sentence
and the status from the second: "Candidates must be able to work in the U.S. Citizenship is
not a requirement for this role." was cut, and an eligibility cut is written to
seen_jobs.json for good. The join now needs the status to run across it, the initialism not
to be the place itself, and nothing in the second sentence to excuse it. A saved ruling
today's screen would not make is released.
"""
from __future__ import annotations

import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import text_screen as T  # noqa: E402

BODY = " You will build forecasts in SQL and Python for our planning team."


@pytest.fixture
def us_status(monkeypatch):
    """An invented profile's eligibility pattern naming a US status."""
    monkeypatch.setattr(T, "ELIGIBILITY", re.compile(
        r"\bu\.?s\.? (citizen\w*|persons?|nationals?)\b|\bsecurity clearance\b", re.I))
    monkeypatch.setattr(T, "_STATUS_TERMS", re.compile(r"\bu\.?s\.? citizen\w*", re.I))


NOT_A_CONDITION = (
    "Candidates must be able to work in the U.S. Citizenship is not a requirement for this role.",
    "You must be based in the U.S. Citizens of Canada and Mexico may apply under TN status.",
    "This role must be performed in the U.S. Citizenship of any country is accepted.",
    "Must be eligible to work in the U.S. Citizenship is not a requirement.",
    "Must be authorized to work in U.S. Citizenship is not a requirement.",
    "U.S. Citizenship is not a requirement for this role.",
)
A_CONDITION = (
    "Applicants must be a U.S. Citizen or Permanent Resident.",
    "This role requires U.S. Citizenship.",
    "Must be a U.S. Person as defined by ITAR.",
    "Applicants must be U.S. Citizens. We are an equal opportunity employer.",
    "We hire across the U.S. U.S. Citizenship required.",
    "U.S. citizenship is required, but a degree is not necessary.",
)


@pytest.mark.parametrize("sentence", NOT_A_CONDITION)
def test_a_place_or_a_status_said_not_to_be_needed_is_not_cut(us_status, sentence):
    assert T.eligibility_cut(sentence + BODY) is None


@pytest.mark.parametrize("sentence", A_CONDITION)
def test_a_status_stated_as_a_condition_is_still_cut(us_status, sentence):
    assert T.eligibility_cut(sentence + BODY)


def test_a_saved_ruling_today_s_screen_would_not_make_is_released(us_status):
    reason = T.CUTS["eligibility"][0]
    for sentence in NOT_A_CONDITION[:3]:
        assert T.ruling_refused(f'{reason}: "{sentence}"'), sentence
    for sentence in A_CONDITION:
        cut = T.eligibility_cut(sentence + BODY)
        assert not T.ruling_refused(f'{reason}: "{cut}"'), cut
    # A quote at the length the cut keeps may have lost its end, and is never re-judged.
    long = "Candidates must be able to work in the U.S. " + "x" * 200
    assert not T.ruling_refused(f'{reason}: "{long[:220]}"')
