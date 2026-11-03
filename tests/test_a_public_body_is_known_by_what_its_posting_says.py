"""A public body the profile's names miss is still out, by what its own posting says.

The bar's public rule read only the employer's name against the profile's list. A
provincial agency named on none of them came back "none", which is a flag and never a cut,
and reached a shortlist although the profile excludes public bodies (2026-11-03). Its
posting said what it was. Only the employer describing itself counts, the paid exception
holds as it does for a name, and a profile that does not exclude public bodies reads
nothing. Invented employers only.
"""
from __future__ import annotations

import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import bar  # noqa: E402
import throttle  # noqa: E402

AGENCY = ("The Northmere Energy Board is a provincial agency of the Government of "
          "Exampleshire. You will build forecasting models in SQL and Python.")
CONSULTANCY = ("Fernhill Advisory works with government agencies and public bodies across "
               "the region. You will build forecasting models in SQL and Python.")


@pytest.fixture
def excludes_public(monkeypatch, judged):
    """A profile that excludes public bodies by name (BAR_PUBLIC), as a real one does."""
    monkeypatch.setattr(bar, "PUBLIC", re.compile(r"\bcouncil\b", re.I))
    monkeypatch.setattr(bar, "_PUBLIC_WHY", "public sector unless well paid")
    monkeypatch.setattr(bar, "_PUBLIC_PAID", "public body, but paid {cur}{mid:,}")


def test_an_agency_named_on_no_list_is_out_by_its_posting(excludes_public):
    got, why = bar.verdict("Northmere Energy Board", AGENCY)
    assert got == bar.EXCLUDED
    assert why == 'public sector unless well paid (the posting says it: "is a provincial agency")'


def test_a_posting_about_public_clients_is_not_a_public_body(excludes_public):
    assert bar.verdict("Fernhill Advisory", CONSULTANCY)[0] != bar.EXCLUDED
    assert bar.public_said("Our public sector clients include several ministries.") == ""
    assert bar.public_said("Fernhill is a public company listed on the exchange.") == ""


def test_the_paid_exception_holds(excludes_public, monkeypatch):
    monkeypatch.setattr(bar, "TARGET_MIDPOINT", 60_000)
    paid = AGENCY + " Salary: £70,000 - £80,000 per year."
    assert bar.verdict("Northmere Energy Board", paid)[0] == bar.PAY


def test_a_profile_that_keeps_public_bodies_reads_nothing(judged):
    assert bar.PUBLIC is bar._NEVER          # the example person sets no BAR_PUBLIC
    assert bar.public_said(AGENCY) == ""
    assert bar.verdict("Northmere Energy Board", AGENCY)[0] != bar.EXCLUDED


def test_the_round_skips_it_before_the_shortlist(excludes_public):
    """Through the throttle, which every source passes before the shortlist is cut."""
    rows = [{"title": "Data Analyst", "company": "Northmere Energy Board", "desc": AGENCY,
             "url": "https://jobs.example/northmere/1", "fit": 90, "priority": 80},
            {"title": "Data Analyst", "company": "Fernhill Advisory", "desc": CONSULTANCY,
             "url": "https://jobs.example/fernhill/1", "fit": 80, "priority": 70}]
    kept, skipped = throttle.throttle(rows, {}, {}, {}, "2026-11-03")
    assert [r["company"] for r in kept] == ["Fernhill Advisory"]
    assert skipped[0]["skip_reason"].startswith("candidate's bar: public sector unless well paid")
