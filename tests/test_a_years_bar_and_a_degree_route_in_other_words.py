"""Bars written in shapes the screen did not read, from the live-page audit of 2026-10-25.

"You have 4 or more years" and "3 years' experience" said a years bar the screen missed,
"7+ years in data science" named the field instead of the word experience, and "or a
combination of education and experience" offered a way round a degree in words other
than "or equivalent". The other side is pinned too: a firm's own age ("20+ years in
business") and an age limit are never a bar. The postings are invented.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import posting_profile as pp  # noqa: E402
import text_screen as ts  # noqa: E402


def _years(s):
    return [n for n, _ in ts.years_bars(s)]


def test_a_years_bar_in_more_words():
    for s, n in (("You have 4 or more years of experience in analytics.", 4),
                 ("Must have 3 years' experience in SQL.", 3),
                 ("Must have 3 years’ experience in SQL.", 3),
                 ("Requirements: 5 or more years of relevant experience.", 5),
                 ("Minimum 3 to 5 years in a data role.", 3)):
        assert _years(s) == [n], s


def test_years_in_a_field_count_only_where_they_are_asked_for():
    # The field in place of the word experience is how a requirement is often written
    # ("7+ years in data science"), so it counts, but only beside a requirement cue,
    # the gate years_bars already keeps.
    for s, n in (("We are looking for someone with 7+ years in data science.", 7),
                 ("Requirements: 5+ years in the industry is a must.", 5),
                 ("Candidates with 6+ years in analytics engineering will stand out.", 6)):
        assert _years(s) == [n], s
    for s in ("Acme brings 7+ years in data science to every client.",
              "Our team has 12 years in analytics between them."):
        assert _years(s) == [], s


def test_a_firms_own_age_and_an_age_limit_are_never_a_bar():
    for s in ("We have 20+ years in business and you will love it here.",
              "We have 20+ years in the industry and you will love it.",
              "Acme has been 30 years in business; you have strong SQL.",
              "Requirements: 25 years in operation means a stable team.",
              "Applicants must be 18 years or older and pass a criminal background check."):
        assert _years(s) == [], s


def test_a_combination_of_education_and_experience_is_another_way_in():
    for s in ("A bachelor's degree in statistics, or a combination of education and "
              "experience, is required.",
              "Bachelor's degree or an equivalent combination of education, training and "
              "experience.",
              "A degree in a quantitative field or any combination of relevant training "
              "and experience."):
        assert ts.ESCAPE.search(s), s
        assert pp.degree(s)["equivalence"], s
    for s in ("A bachelor's degree in finance is required.",
              "A combination of SQL and Python is essential; a bachelor's degree is "
              "required."):
        assert not pp.degree(s)["equivalence"], s
