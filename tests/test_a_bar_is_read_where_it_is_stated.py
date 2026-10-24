"""Three ways a posting's bars were misread, from the drafting chat of 2026-10-24.

A bachelor's offered with another way in, in words other than "or equivalent" ("or through
substantial technical work, research, or projects"), was read as required with no route.
A years bar whose sentence also said "preferably in tech" and "is a plus" about other
things was dropped as a nice-to-have. And "experience in business operations" read as a
company's age ("in business since..."), dropping its bar too. The postings are invented,
in the shapes the real ones were written in.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import posting_profile as pp  # noqa: E402
import text_screen as ts  # noqa: E402


def test_a_degree_with_another_way_in_named_in_its_own_words():
    for s in ("Demonstrated technical ability through a bachelor's degree in engineering, "
              "statistics or physics, or through substantial technical work, research, or "
              "projects.",
              "A bachelor's degree, or practical work experience in a data role.",
              "A university degree; strong experience in lieu of a degree is welcome."):
        d = pp.degree(s)
        assert d["level"] in ("a bachelor's degree", "a degree") and d["equivalence"], s
    for s in ("A bachelor's degree in computer science or physics is required.",
              "A PhD with research experience in NLP, or a master's degree."):
        assert not ts.ESCAPE.search(s) and not ts.DEGREE_ROUTE.search(s), s


def test_another_way_in_is_read_only_where_it_is_about_the_degree():
    # Read anywhere near the degree, an "or ... experience" about something else took a
    # required master's away (the review of 2026-10-24).
    import fit
    for body in ("A Master's degree in Statistics is required. 3+ years of academic or "
                 "industry experience with causal inference.",
                 "A Master's degree in Statistics is required. Strong SQL, or hands-on "
                 "experience with Spark.",
                 "A Master's degree in Statistics and 3+ years of academic or industry "
                 "experience."):
        assert fit._degree_ask(body) == 1.0, body
    assert fit._degree_ask("A Master's degree in Statistics, or through substantial "
                           "technical work, research, or projects.") == 0.0
    for s in ("Bachelor's degree in computer science required. 3+ years of analytics or "
              "related experience.",
              "Degree in Mathematics required. Proficiency in R or Python, or demonstrated "
              "experience with SAS."):
        d = pp.degree(s)
        assert d["required"] and not d["equivalence"], s


def test_a_years_bar_keeps_what_its_qualifiers_say_about_other_things():
    text = ("IN ORDER TO BE SUCCESSFUL, YOU MUST BRING\n\n"
            " - 6+ years of experience in a highly analytical role, preferably in tech; "
            "experience in a marketplace business is a plus\n\n"
            " - Proficiency using SQL and Python")
    assert pp.years(text)["asks"] == 6
    assert ts.years_bars("At least 8 years of work experience, preferably sales experience "
                         "with consumer apps.")[0][0] == 8
    assert ts.years_bars("Requirements: 3+ years of experience (5+ preferred).")[0][0] == 3
    assert ts.years_bars("5+ years of experience (preferred).") == []
    for nice in ("Ideally 5+ years of experience in analytics.",
                 "5+ years of experience preferred.",
                 "Preferred qualifications: 5+ years of experience in SQL.",
                 "Nice to have: 3+ years of experience with dbt."):
        assert ts.years_bars(nice) == [], nice


def test_experience_in_business_operations_is_not_a_company_boast():
    assert ts.years_bars("At least two years of relevant professional experience in "
                         "business operations, analytics, or a related field.")[0][0] == 2
    for boast in ("We have been in business since 1994 and bring 30 years of experience.",
                  "In business for over 40 years, our team has 25 years of experience."):
        assert ts.years_bars(boast) == [], boast
