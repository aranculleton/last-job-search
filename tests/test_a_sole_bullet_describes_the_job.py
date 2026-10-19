"""An employer with one line on the page gets the line that describes the job.

`allocate._pick` gives an employer's only bullet to the one that best represents
the role (its WEIGHT) unless relevance to the posting beats it by a whole theme
match (SOLE_MARGIN). `fit_to_page.trim_resume` did not: it removed the globally
lowest-scoring bullet, and on a posting about something else that is usually the
one describing the job, so a page trimmed to fit left the role represented by a
sharper but truer-to-nothing line. The comment in allocate.py has always cited
this file; it did not exist.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import allocate  # noqa: E402
import bullet_library as LIB  # noqa: E402
import fit_to_page  # noqa: E402

GRAD = "Saltmarsh Analytics"          # the example person's one-year role, floor 1
DASHBOARDS = "We need dashboards and reporting for our operations team."


def _draft(posting):
    return {"company": "Larkspur Retail", "role": "Analyst", "posting": posting, "tools": "",
            "jobs": [{"employer": "Brindle & Hart Logistics", "bullets": ["BH_FORECAST", "BH_ROUTING"]},
                     {"employer": "Oakmere Foods", "bullets": ["OF_WASTE", "OF_SUPPLIER"]},
                     {"employer": GRAD, "bullets": ["SALT_FORECAST", "SALT_DASH"]}]}


def _sole(posting, a):
    taken = {b for j in a["jobs"] if j["employer"] != GRAD for b in j["bullets"]}
    return allocate._pick(GRAD, 1, allocate.bullet_scores(posting), taken)


def test_no_conflict_pair_crosses_employers():
    """A single pick ignores conflicts, which holds only while none crosses employers."""
    owner = {b: e for e, bullets in LIB.LIB.items() for b in bullets}
    crossing = [(k, v) for k, vs in LIB.CONFLICTS.items() for v in vs
                if k in owner and v in owner and owner[k] != owner[v]]
    assert crossing == []


def test_a_trim_to_one_line_keeps_the_line_that_describes_the_job():
    a = _draft(DASHBOARDS)
    scores = allocate.bullet_scores(DASHBOARDS)
    # The scenario: the describing line scores lowest, and relevance does not win.
    assert scores["SALT_FORECAST"] < scores["SALT_DASH"]
    assert scores["SALT_DASH"] - scores["SALT_FORECAST"] < allocate.SOLE_MARGIN
    gone = fit_to_page.trim_resume(a)
    left = next(j["bullets"] for j in a["jobs"] if j["employer"] == GRAD)
    assert left == _sole(DASHBOARDS, _draft(DASHBOARDS)) == ["SALT_FORECAST"]
    assert gone == "SALT_DASH"


def test_relevance_still_takes_the_only_line_when_it_wins_by_a_whole_theme():
    posting = ("Tableau, Power BI and Looker dashboards for business intelligence; "
               "weekly reporting and a monthly report.")
    a = _draft(posting)
    scores = allocate.bullet_scores(posting)
    assert scores["SALT_DASH"] - scores["SALT_FORECAST"] >= allocate.SOLE_MARGIN
    fit_to_page.trim_resume(a)
    left = next(j["bullets"] for j in a["jobs"] if j["employer"] == GRAD)
    assert left == _sole(posting, _draft(posting)) == ["SALT_DASH"]
