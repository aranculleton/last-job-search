"""Three readings the text screen got wrong, each on how a posting is ordinarily written.

- "Applicants must be a U.S. Citizen" was split after the initialism, because the next
  word is capitalised, and the eligibility gate never saw the status whole: the lower-case
  form cut and the capitalised one passed.
- "Data Analyst to support our actuarial pricing team" was cut as a credential gate: a
  credential word near the top and three uses anywhere were read as the role being the
  profession, though the title names a data role and the posting says no exams are needed.
- "Master Production Schedule" and "Master Black Belt" read as a graduate degree, a flag
  on the screen and points off the fit.
"""
from __future__ import annotations

import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import fit  # noqa: E402
import text_screen as T  # noqa: E402


@pytest.fixture
def us_status(monkeypatch):
    """An invented profile's eligibility pattern naming a US status."""
    monkeypatch.setattr(T, "ELIGIBILITY", re.compile(r"\bu\.?s\.? (citizen\w*|persons?)\b", re.I))


@pytest.mark.parametrize("sentence", ["Applicants must be a U.S. citizen.",
                                      "Applicants must be a U.S. Citizen.",
                                      "This role requires U.S. Citizenship.",
                                      "Must be a U.S. Person as defined by ITAR.",
                                      "Applicants must be a U.S. Citizen or Permanent Resident."])
def test_a_status_written_in_capitals_after_an_initialism_is_read_whole(us_status, sentence):
    assert T.eligibility_cut(sentence + " You will build forecasts in SQL.")


def test_a_line_after_the_initialism_still_never_excuses_it(us_status):
    assert T.eligibility_cut("Must be a U.S. Citizen. We are an equal opportunity employer.")
    assert not T.eligibility_cut("Based in the U.S. We are an equal opportunity employer.")


TEAM = ("Data Analyst to support our actuarial pricing team in the city.\n"
        "You will build SQL pipelines that feed the actuarial models, automate reporting for "
        "the actuarial function, and work with actuaries on data quality. Strong SQL and "
        "Python are required.")


def test_a_data_role_beside_the_profession_is_not_a_credential_gate():
    assert T.screen({"title": "Data Analyst, Pricing", "desc": TEAM})["cuts"] == []
    said = TEAM + " No actuarial exams are needed: this is a data role."
    assert T.screen({"title": "Data Analyst, Pricing", "desc": said})["cuts"] == []


def test_a_role_that_is_the_profession_is_still_a_credential_gate():
    cuts = T.screen({"title": "Actuarial Analyst", "desc": "Actuarial Analyst. " + TEAM})["cuts"]
    assert cuts and "professional designation" in cuts[0]


BASE = ("A logistics firm is hiring a Supply Chain Planning Analyst in Manchester. You will own "
        "demand forecasting and inventory analytics with SQL and Python, working with "
        "operations teams. ")


@pytest.mark.parametrize("extra", [
    "Experience maintaining the Master Production Schedule (MPS) is required.",
    "You will work closely with our Master Scheduler on weekly plans; strong SQL required.",
    "A Master Black Belt in Lean Six Sigma is required.",
])
def test_a_supply_chain_term_is_not_a_degree(extra):
    job = {"title": "Supply Chain Planning Analyst", "company": "Brindlehart Freight",
           "location": "Manchester, England, United Kingdom", "desc": BASE + extra}
    assert not [f for f in T.screen(job)["flags"] if "degree" in f]
    assert not [w for w in fit.fit(job)["fit_why"] if "degree" in w]


def test_a_masters_degree_is_still_a_degree():
    job = {"title": "Supply Chain Planning Analyst", "company": "Brindlehart Freight",
           "location": "Manchester, England, United Kingdom",
           "desc": BASE + "A Master's degree is required."}
    assert [f for f in T.screen(job)["flags"] if "degree" in f]
