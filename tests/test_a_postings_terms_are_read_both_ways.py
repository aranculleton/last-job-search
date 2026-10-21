"""What a posting says about how the job is held and what it pays, read right both ways.

Staging asks the person before drafting a fixed-term contract or pay stated for another
place, so a wrong reading is a false question, and a person can decline a permanent job on
it. The reader got both directions wrong:

- **Permanent jobs read as contracts.** "This is a permanent, full-time role" lost to a
  health benefit's "family coverage", to "100% parental leave coverage for 6 months", to a
  secondment the employer offers its staff; "Contract Pricing" and "Contract Management" in
  a title, "a contract research organisation" and "contract length and renewal risk" in the
  work all read as a contract.
- **Contracts read as nothing, or as permanent.** "a term position", "Temporary full-time",
  "Duration: 6 months", "Initial 6-month term", IR35 and a day rate, "Contract until June
  2027", maternity leave cover, a contractor, freelance and interim were "not stated", and
  "Employment type: Full-time" beside "Duration: 6 months" printed permanent, as did a
  company's "permanent home for software teams".
- **"The only pay ... is for london"** when the same sentence gave the home band first.

Every employer and posting here is invented.
"""
from __future__ import annotations

import datetime as dt
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import pytest  # noqa: E402

import posting_profile as PP  # noqa: E402

TODAY = dt.date(2026, 10, 21)


@pytest.mark.parametrize("text,title", [
    ("This is a permanent, full-time role. We offer health and dental benefits with family "
     "coverage from day one.", "Data Analyst"),
    ("A permanent position in our claims team. We offer 100% parental leave coverage for 6 "
     "months.", "Data Analyst"),
    ("This is a permanent role. Many of our analysts go on secondment to the group.", "Analyst"),
])
def test_a_stated_permanent_job_stays_permanent(text, title):
    assert PP.terms(text, title, TODAY)["kind"] == "permanent"


@pytest.mark.parametrize("text,title", [
    ("You will price renewals for our motor book.", "Commercial Analyst, Contract Pricing"),
    ("You will manage supplier agreements.", "Senior Analyst - Contract Management"),
    ("You will work for a contract research organisation on trial data.", "Data Analyst"),
    ("You will analyse supplier spend, contract length and renewal risk.", "Procurement Analyst"),
    ("Employment type: Full-time. We are the permanent home for software teams.", "Data Analyst"),
    ("We offer secondment opportunities across the group.", "Analyst"),
    ("Health and dental benefits with family coverage from day one.", "Analyst"),
])
def test_contract_words_that_are_not_how_the_job_is_held_ask_nothing(text, title):
    t = PP.terms(text, title, TODAY)
    assert t["kind"] == "not stated", (text, title, t)
    prof = PP.read({"company": "Kestrel Mutual", "title": title, "location": "Manchester"},
                   text, rows=[], today=TODAY)
    assert "contract" not in [q["id"] for q in PP.questions(prof, {"company": "Kestrel Mutual",
                                                                    "title": title})]


@pytest.mark.parametrize("text,title,months", [
    ("This is a term position ending March 31, 2027.", "Data Analyst", None),
    ("Temporary full-time, 9 months.", "Data Analyst", 9),
    ("Duration: 6 months.", "Data Analyst", 6),
    ("Initial 6-month term, with a view to extending.", "Data Analyst", 6),
    ("Day rate £450, outside IR35.", "Data Analyst", None),
    ("Inside IR35, 6 months initially.", "Data Analyst", 6),
    ("Contract until June 2027.", "Data Analyst", None),
    ("This is a maternity leave contract for 12 months.", "Data Analyst", 12),
    ("", "Data Analyst - Maternity Leave Cover", None),
    ("", "Data Analyst Contractor", None),
    ("A freelance engagement, two days a week.", "Data Analyst", None),
    ("", "Interim Finance Analyst", None),
    ("Employment type: Full-time. Duration: 6 months.", "Data Analyst", 6),
])
def test_the_common_contract_forms_are_found(text, title, months):
    t = PP.terms(text, title, TODAY)
    assert t["kind"] in ("fixed-term", "contract"), (text, title, t)
    if months is not None:
        assert t["months"] == months


def test_the_home_band_in_the_same_sentence_is_the_persons_pay():
    text = ("The salary for this role is £40,000 to £48,000, or £52,000 to £60,000 for "
            "London-based colleagues.")
    p = PP.pay(text)
    assert p["where"] == "home" and (p["low"], p["high"]) == (40000, 48000)
    row = {"company": "Kestrel Mutual", "title": "Data Analyst", "location": "Manchester, UK"}
    prof = PP.read(row, text, rows=[], today=TODAY)
    assert [q["id"] for q in PP.questions(prof, row)] == []
    # Pay for another place alone is still asked about, the place written as people write it.
    text = "Salary: £60,000 - £70,000 per annum for this role in London."
    prof = PP.read(row, text, rows=[], today=TODAY)
    [q] = PP.questions(prof, row)
    assert "is for London (" in q["question"]


def test_the_location_line_is_in_plain_words():
    prof = PP.read({"company": "Kestrel Mutual", "title": "Data Analyst", "location": ""},
                   "Hybrid.", rows=[], today=TODAY)
    where = next(x for x in PP.lines(prof) if x.startswith("where:"))
    assert "Tier 2" not in where and "FLAG" not in where and "check: no location stated" in where


def test_staging_a_blank_or_empty_posting_says_what_to_do(tmp_path):
    empty = tmp_path / "posting.txt"
    empty.write_text("   \n", encoding="utf-8")
    run = [sys.executable, os.path.join(ROOT, "tools", "stage_picks.py"), "single", str(tmp_path)]
    out = subprocess.run(run + ["--company", "Kestrel Mutual", "--role", "Data Analyst",
                                "--posting-file", str(empty)], capture_output=True, text=True)
    assert out.returncode != 0 and "is empty" in out.stderr and "Traceback" not in out.stderr
    assert "detail CLI" not in out.stderr
    empty.write_text("A posting.", encoding="utf-8")
    out = subprocess.run(run + ["--company", "   ", "--role", "Data Analyst",
                                "--posting-file", str(empty)], capture_output=True, text=True)
    assert out.returncode != 0 and "--company" in out.stderr and "Traceback" not in out.stderr
