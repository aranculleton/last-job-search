"""The screen reads pay and requirements the way postings in every market write them.

Three ways a stated fact was read as silence, all found by setting up a second
person, in Dublin, end to end:

- A credential stated as "essential", "mandatory" or "must be registered" was
  not a credential gate, so a full application could be drafted for a job the
  candidate cannot legally hold. "A recognised accounting qualification (ACA,
  ACCA or CIMA) is essential for this position" passed.
- Pay needed the currency symbol in front of every figure and a comma or dot
  thousands separator. "EUR 35,000", "45 000 €", "GBP 45,000 to 52,000",
  "€45-55k" and "₹12,50,000" were read as no salary stated, so a range under the
  floor was never flagged and a high one never earned its points. And
  tools/opportunity.py had its own, narrower pattern, so the two could
  disagree about one posting.
- A body under 400 characters skipped every gate. A snippet saying "Active SC
  clearance required" is the whole bar in one line, and it went through.
"""
from __future__ import annotations

import datetime as dt
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import opportunity  # noqa: E402
import text_screen as T  # noqa: E402


# ---- the credential gate -----------------------------------------------------

@pytest.mark.parametrize("sentence", [
    "A recognised accounting qualification (ACA, ACCA or CIMA) is essential for this position.",
    "Applicants must be registered with the IFoA.",
    "CIMA membership is mandatory.",
    "Essential: ACCA or CIMA qualified.",
    "Must be eligible for registration with ICAEW (ACA).",
])
def test_a_credential_stated_as_a_condition_is_a_gate(sentence):
    assert T.designation_cut(sentence)


@pytest.mark.parametrize("sentence", [
    "CIMA qualification desirable.",
    "We support CIMA study.",
    "Reporting to our Chartered Accountant, you will run the forecast.",
    "Registered as a charity, we fund CIMA study for staff.",
])
def test_a_credential_that_is_not_a_condition_is_not_a_gate(sentence):
    assert not T.designation_cut(sentence)


# ---- short bodies ------------------------------------------------------------

@pytest.mark.parametrize("desc,why", [
    ("Operations analyst for a haulage firm. SQL, Excel. Active SC clearance required.",
     "eligibility gate"),
    ("Inventory analyst, Salford. Python and SQL. Fluency in Welsh is essential.",
     "Welsh stated as a requirement"),
])
def test_a_short_body_is_still_read_for_its_bars(desc, why):
    out = T.screen({"desc": desc})
    assert out["text_screen"] == "cut" and why in out["cuts"][0]


def test_a_short_body_with_no_bar_is_marked_thin_not_cut():
    out = T.screen({"desc": "Inventory analyst, Salford. Python and SQL."})
    assert out["text_screen"] == "thin" and out["cuts"] == []
    assert any("too short" in f for f in out["flags"])


# ---- pay, in the example's market (GBP, £) ------------------------------------

@pytest.mark.parametrize("sentence,rng", [
    ("Salary: £50,000 - £58,000 per year plus bonus.", (50_000, 58_000)),
    ("We offer GBP 45,000 to 52,000 depending on experience.", (45_000, 52_000)),
    ("Salary 45 000 £ to 55 000 £ depending on experience.", (45_000, 55_000)),
    ("Pay band £38k-£44k.", (38_000, 44_000)),
    ("Salary £45-55k.", (45_000, 55_000)),
    ("£45,000 - £52,000 per annum", (45_000, 52_000)),
    ("Salary £45,000.00 - £50,000.00", (45_000, 50_000)),
    ("£45k-50k pa", (45_000, 50_000)),
    ("Salary: £35,000 per annum.", (35_000, 35_000)),
    ("Salary of circa £48,000", (48_000, 48_000)),
    ("Salary up to £62,000 for the right person.", (None, 62_000)),
    ("Salary from £40,000.", (40_000, None)),
    ("Salary £45,000 plus £5,000 car allowance.", (45_000, 45_000)),
])
def test_pay_is_read_however_it_is_written(sentence, rng):
    assert T.salary_range(sentence)[:2] == rng


@pytest.mark.parametrize("sentence", [
    "Annual leave 25 days and a £1,000 learning budget.",
    "Salary up to EUR 62,000 for the right person.",          # another currency
    "Salary 45.000 € - 55.000 €",
    "The company has 45 000 customers and 52,000 orders a year.",
])
def test_what_is_not_pay_in_this_market_is_not_read_as_pay(sentence):
    assert T.salary_range(sentence)[:2] == (None, None)


@pytest.mark.parametrize("cur,code,sentence,values", [
    ("€", "EUR", "Salary 45.000 € - 55.000 €", [45_000, 55_000]),
    ("€", "EUR", "Salary up to EUR 62,000", [62_000]),
    ("€", "EUR", "€45-55k DOE", [45_000, 55_000]),
    ("₹", "INR", "CTC ₹12,50,000 - ₹18,00,000 per annum", [1_250_000, 1_800_000]),
    ("₹", "INR", "12-18 LPA", [1_200_000, 1_800_000]),
    ("₹", "INR", "₹12L to ₹18L", [1_200_000, 1_800_000]),
    ("$", "CAD", "C$90k-110k", [90_000, 110_000]),
    ("$", "CAD", "USD 120,000", []),
])
def test_every_market_writes_its_own_money(cur, code, sentence, values):
    assert T.money_parser(cur, code)[0](sentence) == values


def test_the_scorer_reads_the_range_the_screen_reads():
    desc = ("Greyloch runs 140 convenience stores. The demand planning analyst builds weekly "
            "forecasts for fresh categories and works with buyers on promotions. You will "
            "use SQL and Excel daily and Python where it helps. We offer GBP 45,000 to 52,000 "
            "depending on experience, 25 days holiday and a pension. The team is growing and "
            "this is a permanent role based in Leeds with two days a week in the office.")
    out = opportunity.score({"title": "Demand Planning Analyst", "company": "Greyloch",
                             "desc": desc}, dt.date(2026, 10, 14))
    assert any("stated top of band £52,000" in w for w in out["why"]), out["why"]


def test_a_minimum_is_not_scored_as_a_top():
    desc = ("Salary from £30,000. " + "The analyst builds weekly forecasts for fresh "
            "categories and works with buyers. " * 12)
    out = opportunity.score({"title": "Analyst", "company": "Greyloch", "desc": desc},
                            dt.date(2026, 10, 14))
    assert not any("stated top of band" in w for w in out["why"]), out["why"]
