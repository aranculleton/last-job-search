"""A graduate degree offered beside a bachelor's is a bar a bachelor's clears.

stage_picks read "Bachelor’s or master’s degree" (a curly apostrophe, in a real posting for
a senior data scientist) as "a master's degree, required, no equivalence route" (2026-10-23).
The fit score already knew the rule; the profile of the posting and the screen did not, so
the three disagreed. One rule now, text_screen.BACHELOR_OR, and curly apostrophes read like
straight ones. The postings here are invented.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import fit  # noqa: E402
import posting_profile  # noqa: E402
import text_screen  # noqa: E402

BODY = ("We are hiring a data scientist to build pricing models with Python and SQL, and to "
        "work with the commercial team on what they mean. ")


def _flags(sentence):
    return text_screen.screen({"title": "Senior Data Scientist", "desc": BODY + sentence})["flags"]


def test_a_bachelors_or_a_masters_reads_as_a_bachelors_with_either_apostrophe():
    for s in ("Bachelor’s or master’s degree in statistics, economics or a "
              "related field.",
              "Bachelor's or Master's degree in Statistics or a related field is required.",
              "A BSc/MSc in a quantitative field."):
        got = posting_profile.degree(BODY + s)
        assert got["level"] == "a bachelor's degree", (s, got)
        assert not [f for f in _flags(s) if "graduate degree" in f], s
        assert fit._degree_ask(BODY + s) in (None, fit.DEMAND_NONE), s


def test_a_graduate_degree_asked_alone_is_still_a_graduate_bar():
    for s, level in (("Master’s degree in Statistics required.", "a master's degree"),
                     ("A Master's or PhD in a quantitative field is required.", "a master's degree"),
                     ("PhD in Physics required.", "a PhD")):
        got = posting_profile.degree(BODY + s)
        assert got["level"] == level and got["required"], (s, got)
        assert [f for f in _flags(s) if "graduate degree" in f], s


def test_master_data_with_a_curly_apostrophe_is_still_not_a_degree():
    s = "Experience with master’s data management tools is required."
    assert posting_profile.degree(BODY + s)["level"] == ""
    assert not [f for f in _flags(s) if "graduate degree" in f]
