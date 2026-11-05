"""A sentence ends after an acronym, and an initial still does not end one.

The maintainer, 2026-11-05: verify_batch showed a summary sentence as UNAUDITED although
the claim map held it. The one sentence splitter the generator, the code audit and
verify_batch share (render_application.split_sentences) never split after a capital
before a full stop, so "on AWS. Built" was one sentence to the checks and two to the
drafter's claim map. An initial ("U.S.", "J. Smith") is a single capital at a word's start,
which is all the rule ever needed; tools/network/tone.py already split this way.
Invented text throughout.
"""
from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import draft_audit  # noqa: E402
import render_application as R  # noqa: E402
import tone  # noqa: E402,F401  (tools/network, on the path conftest sets)
import verify_batch  # noqa: E402

AWS = "Built the pipelines on AWS."
SQL = "Owned the reporting in SQL."
US = "Ran pricing for the U.S. market for a year."


@pytest.mark.parametrize("text, want", [
    # An acronym ends a sentence, mid-text and at the end.
    (f"{AWS} {SQL} {US}", [AWS, SQL, US]),
    (f"{SQL} {AWS}", [SQL, AWS]),
    (f"{US} {AWS}", [US, AWS]),
    (AWS, [AWS]),
    (SQL, [SQL]),
    # An initial does not, mid-text or at the end.
    ("Moved to the U.S. last year. Built models.", ["Moved to the U.S. last year.", "Built models."]),
    ("Worked for the U.S.", ["Worked for the U.S."]),
    ("Reported to J. Okafor in Leeds. Built models.", ["Reported to J. Okafor in Leeds.",
                                                       "Built models."]),
    ("Used e.g. dbt and SQL. Built models.", ["Used e.g. dbt and SQL.", "Built models."]),
])
def test_the_one_splitter(text, want):
    assert R.split_sentences(text) == want
    # And the network's tone check, which keeps its own copy, reads them the same.
    assert [s for s in tone._SENT_SPLIT.split(text) if s] == want


def test_a_summary_sentence_after_an_acronym_is_audited():
    summary = ("Data analyst with five years of pricing work on AWS. Built demand models in "
               "Python and SQL. Moved to the U.S. team in 2025.")
    entry = {"summary": summary, "claim_map": [
        {"field": "summary", "sentence": "Data analyst with five years of pricing work on AWS.",
         "cites": ["SUMMARY"]},
        {"field": "summary", "sentence": "Built demand models in Python and SQL.",
         "cites": ["SUMMARY"]},
        {"field": "summary", "sentence": "Moved to the U.S. team in 2025.", "cites": ["SUMMARY"]}]}
    assert [s for _f, s in draft_audit.field_sentences(entry)] == [
        c["sentence"] for c in entry["claim_map"]]
    assert verify_batch._unaudited(entry) == []
