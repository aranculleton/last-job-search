"""Every public reading in the text screen and the place lists takes None and answers with
its empty answer.

`other_language_cut(None)` raised a TypeError, and so did four other public names that a
person's own tests may call: a posting with no body, or a sentence a caller could not
find, is nothing to cut, not a crash.
"""
from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import places  # noqa: E402
import text_screen as T  # noqa: E402

CALLS = {
    "other_language_cut": (lambda: T.other_language_cut(None), None),
    "other_language_named": (lambda: T.other_language_named(None), None),
    "resides_abroad": (lambda: T.resides_abroad(None), False),
    "residence_cut": (lambda: T.residence_cut(None), None),
    "designation_cut": (lambda: T.designation_cut(None, None), None),
    "research_ml_flag": (lambda: T.research_ml_flag(None), (None, 0)),
    "evidence": (lambda: T.evidence(None, None), ""),
    "under_minimum_qualifications": (lambda: T.under_minimum_qualifications(None, None), False),
    "eligibility_cut": (lambda: T.eligibility_cut(None), None),
    "internal_only": (lambda: T.internal_only(None, None), None),
    "sentences": (lambda: T.sentences(None), []),
    "years_bars": (lambda: T.years_bars(None), []),
    "salary_range": (lambda: T.salary_range(None), (None, None, "")),
    "cut_settings": (lambda: T.cut_settings(None), []),
    "ruling_refused": (lambda: T.ruling_refused(None), False),
    "pay_cut_top": (lambda: T.pay_cut_top(None), None),
    "places.subdivision_abroad": (lambda: places.subdivision_abroad(None), None),
    "places.region_takes_in_home": (lambda: places.region_takes_in_home(None), (None, "")),
    "places.known_country_in": (lambda: places.known_country_in(None), None),
}


@pytest.mark.parametrize("name", sorted(CALLS))
def test_none_reads_as_nothing(name):
    call, empty = CALLS[name]
    assert call() == empty


def test_a_posting_with_no_body_or_title_is_screened():
    out = T.screen({"title": None, "desc": None})
    assert out["cuts"] == [] and out["text_screen"] == "thin"
