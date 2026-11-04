"""A recruiter at a recruitment agency is never hidden from Messages because the person's bar
turns the agency down: the agency is not where they would work. An in-house recruiter at an
employer the bar turns down is still held, and so is an agency the person named by name
("no more from"): their own words win. Every person and employer here is invented."""
from __future__ import annotations

import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "network"))

import bar  # noqa: E402
import sector  # noqa: E402
import throttle  # noqa: E402
from company_key import key  # noqa: E402
from network import surface  # noqa: E402

AGENCY = "Marlowe Staffing Partners"
IN_HOUSE = "Quillfeather Bank"


@pytest.fixture
def rules(monkeypatch):
    """A person whose bar states one (so an unlisted employer clears none of it) and whose
    employers file names agencies."""
    monkeypatch.setattr(sector, "AGENCY", re.compile(r"\bstaffing\b"))
    monkeypatch.setattr(bar, "applies", lambda: True)
    monkeypatch.setattr(bar, "listed", lambda c: True)

    def verdict(company, posting=""):
        if "declined" in str(company).lower():
            return bar.EXCLUDED, "declined by name"
        return bar.NONE, "clears none of pay, prestige or signal"
    monkeypatch.setattr(bar, "verdict", verdict)
    monkeypatch.setattr(throttle, "load_do_not_target", lambda *a, **k: {})
    return monkeypatch


def held(company, title):
    return surface.held({"company": company, "title": title}, [], "replied", replying=True)


def test_an_agency_recruiter_who_asked_for_a_resume_is_not_held(rules):
    assert held(AGENCY, "Senior Recruiter") is None


def test_an_in_house_recruiter_at_a_turned_down_employer_is_held(rules):
    got = held(IN_HOUSE, "Talent Acquisition Partner")
    assert got and got["why"] == "employer"


def test_someone_at_an_agency_who_is_not_a_recruiter_is_still_held(rules):
    assert held(AGENCY, "Data Analyst")["why"] == "employer"


def test_an_agency_the_person_named_no_more_from_is_held(rules):
    rules.setattr(throttle, "load_do_not_target",
                  lambda *a, **k: {key(AGENCY): "no more from them"})
    assert held(AGENCY, "Senior Recruiter")["why"] == "employer"


def test_an_agency_declined_by_name_in_the_bar_is_held(rules):
    assert held("Declined Staffing Group", "Recruiter")["why"] == "employer"
