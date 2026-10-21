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
- **Then permanent wording read as a contract again.** "A long-term position" and "a long
  term role" are jobs meant to last, read as "a term position"; projects "with a typical
  duration of 6 months", "spot and day rate pricing" (a product), "every supplier contract
  until signature" and "our IR35 compliance reviews" are the work, not how the job is held;
  "Interim and Annual Reporting" in a title is a company's accounts. Each held a permanent
  job back with "is a fixed-term contract, the posting says".
- **Pay for the person's own area read as pay for somewhere else.** "£52,000 - £60,000
  (London) / £40,000 - £48,000 (national)" read the "(London)" after the first band as the
  second band's place too, and "plus London weighting of £4,000" read an allowance as the
  band's place: "elsewhere: london" for someone in Manchester, and for someone in London the
  two bands merged into one.

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


@pytest.mark.parametrize("text,title", [
    ("We are looking for someone for a long-term position in our analytics team.", "Data Analyst"),
    ("This is a long term role with clear progression.", "Data Analyst"),
    ("Join us in a long-term role where you will grow.", "Data Analyst"),
    ("You will lead improvement projects with a typical duration of 6 months.", "Data Analyst"),
    ("Typical project duration: 6 months.", "Data Analyst"),
    ("You will analyse spot and day rate pricing for our charter fleet.", "Freight Pricing Analyst"),
    ("You will own every supplier contract until signature, tracking renewal risk.", "Data Analyst"),
    ("You will price each contract until renewal.", "Data Analyst"),
    ("You will support our IR35 compliance reviews for the contractor workforce.",
     "Tax Data Analyst"),
    ("You will check whether each contractor sits inside or outside IR35.", "Tax Data Analyst"),
    ("A permanent analyst role in group finance.",
     "Financial Analyst - Interim and Annual Reporting"),
    ("You will prepare the group accounts.", "Financial Analyst, Interim Reporting"),
    ("Our people enjoy hybrid working and a mid-term review of goals.", "Data Analyst"),
    ("Employment type: Permanent. We offer a short-term incentive plan.", "Data Analyst"),
])
def test_permanent_wording_is_not_read_as_a_contract(text, title):
    t = PP.terms(text, title, TODAY)
    assert t["kind"] not in ("fixed-term", "contract", "contract to hire"), (text, title, t)
    row = {"company": "Quillmere Foods", "title": title, "location": "Manchester"}
    prof = PP.read(row, text, rows=[], today=TODAY)
    assert "contract" not in [q["id"] for q in PP.questions(prof, row)]


@pytest.mark.parametrize("text,title,months", [
    ("This is a term position ending March 31, 2027.", "Data Analyst", None),
    ("The duration of the contract is 6 months.", "Data Analyst", 6),
    ("The duration of this assignment will be twelve months.", "Data Analyst", 12),
    ("Assignment duration: 6 months.", "Data Analyst", 6),
    ("Location: Manchester | Duration: 6 months", "Data Analyst", 6),
    ("This is a short-term contract.", "Data Analyst", None),
    ("We are hiring on a long-term contract.", "Data Analyst", None),
    ("Day rate: £450 to £500.", "Data Analyst", None),
    ("£450-£500 per day.", "Data Analyst", None),
    ("IR35 status: outside.", "Data Analyst", None),
    ("This role sits outside IR35.", "Data Analyst", None),
    ("Contract until the end of March 2027.", "Data Analyst", None),
    ("Contract until further notice.", "Data Analyst", None),
    ("This is an interim role.", "Data Analyst", None),
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


_SPLIT = "Salary: £52,000 - £60,000 (London) / £40,000 - £48,000 (national)."
_WEIGHTING = "Pay: £45,000 - £50,000 plus London weighting of £4,000."


@pytest.mark.parametrize("text,band", [
    (_SPLIT, (40000, 48000)),
    (_WEIGHTING, (45000, 50000)),
    ("The salary is £52,000 to £60,000 in London, and £40,000 to £48,000 elsewhere in the UK.",
     (40000, 48000)),
])
def test_the_national_band_is_home_for_someone_outside_the_capital(text, band):
    # The example person lives in Greater Manchester.
    p = PP.pay(text)
    assert p["where"] == "home" and (p["low"], p["high"]) == band, p
    row = {"company": "Kestrel Mutual", "title": "Data Analyst", "location": "Manchester, UK"}
    prof = PP.read(row, text, rows=[], today=TODAY)
    assert "pay_elsewhere" not in [q["id"] for q in PP.questions(prof, row)]


@pytest.mark.parametrize("text,band", [
    (_SPLIT, (52000, 60000)),
    (_WEIGHTING, (45000, 50000)),
    ("The salary for this role is £40,000 to £48,000, or £52,000 to £60,000 for London-based "
     "colleagues.", (52000, 60000)),
    ("The salary is £52,000 to £60,000 for London.", (52000, 60000)),
])
def test_the_capital_band_is_home_for_someone_who_lives_there(monkeypatch, text, band):
    import places
    monkeypatch.setattr(places, "METRO", ("london", "camden", "islington"))
    outside = [x for x in (places.LOCATION or {}).get("outside") or () if x != "london"]
    monkeypatch.setattr(places, "LOCATION", dict(places.LOCATION or {},
                                                 outside=outside + ["manchester"]))
    p = PP.pay(text)
    assert p["where"] == "home" and (p["low"], p["high"]) == band, p
    # A band for another city alone is still somewhere else.
    assert PP.pay("Salary: £45,000 - £50,000 in Manchester.")["where"] == "elsewhere: manchester"


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
