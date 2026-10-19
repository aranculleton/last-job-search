"""One application is one result, and its draft is found by the name it was sent under.

Two defects in `tools/what_works.py`, both in what it learns from:

- The tracker appends a row when an application moves on rather than editing the
  old one, so a role can sit in it as "applied" and, later, "interview". Both
  were counted: the old row, quiet for 45 days, as a loss and the new one as a
  win, so every interview also recorded a failure and the interview rate halved.
  `followups.superseded` already says which row is the application now.
- `draft_for` read the abbreviation off the resume's filename with a pattern that
  took everything after the first underscore, `Ellis_CV_Larkspur` for
  `cv/Morgan_Ellis_CV_Larkspur.tex`, so it never matched a draft by its
  abbreviation and only found one whose role was spelled exactly as the tracker's.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "network"))

import throttle  # noqa: E402
import what_works as W  # noqa: E402

TODAY = "2026-10-15"


def test_an_application_that_moved_on_is_counted_once_as_what_it_became():
    tracker = [
        {"date": "2026-08-01", "company": "Larkspur Retail", "role": "Senior Supply Chain Analyst",
         "status": "applied", "fit_rating": "81"},
        {"date": "2026-08-20", "company": "Larkspur Retail", "role": "Senior Supply Chain Analyst",
         "status": "interview", "fit_rating": "81"},
    ]
    cases = W.application_cases(tracker, TODAY)
    assert [(c["date"], c["won"]) for c in cases] == [("2026-08-20", True)]
    assert W.brief_search(tracker, TODAY).startswith(
        "Interviews from your applications: 1 of 1 (100%).")


def test_an_application_that_moved_on_is_not_also_still_waiting():
    tracker = [
        {"date": "2026-10-01", "company": "Kestrel Mutual", "role": "Pricing Analyst",
         "status": "applied"},
        {"date": "2026-10-09", "company": "Kestrel Mutual", "role": "Pricing Analyst",
         "status": "interview"},
    ]
    out = W.brief_documents(tracker, [], TODAY)
    assert "Reached an interview: 1 of 1 (100%); 0 sent in the last 45 days" in out


def test_a_different_role_at_the_same_employer_is_still_its_own_application():
    tracker = [
        {"date": "2026-08-01", "company": "Larkspur Retail", "role": "Demand Planner",
         "status": "applied"},
        {"date": "2026-08-20", "company": "Larkspur Retail", "role": "Senior Supply Chain Analyst",
         "status": "interview"},
    ]
    assert sorted(c["won"] for c in W.application_cases(tracker, TODAY)) == [False, True]


def test_silence_is_the_throttles_number_not_a_copy_of_it():
    assert W.SILENT_DAYS == throttle.SILENCE_DAYS


def test_the_draft_is_found_by_the_abbreviation_in_the_resume_filename():
    row = {"company": "Larkspur Retail", "role": "Senior Supply Chain Analyst",
           "cv_file": "cv/Morgan_Ellis_CV_Larkspur.tex"}
    sent = {"company": "Larkspur Retail", "role": "Senior Supply Chain Analyst, Hybrid",
            "abbr": "Larkspur"}
    other = {"company": "Larkspur Retail", "role": "Senior Supply Chain Analyst",
             "abbr": "Larkspur_Planning"}
    assert W.draft_for(row, [sent]) is sent
    # Two drafts for the same title: the one the resume was sent under, not the last.
    assert W.draft_for(row, [sent, other]) is sent
    # With no abbreviation on file, the same role is still found, and never another.
    assert W.draft_for(dict(row, cv_file=""), [other]) is other
    assert W.draft_for(dict(row, cv_file="", role="Demand Planner"), [sent, other]) is None
