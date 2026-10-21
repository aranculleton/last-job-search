"""An on-site place abroad that shares a home town's name is that place, not home.

The location gate passed "Manchester, NH" as Greater Manchester for the example person in
the UK, and "Sale, VIC", "Bury, QC", "Stockport, OH" and "Salford, ON" the same way: the
home town's name was matched and the state beside it was never read. A home town's name
beside another country's state or province now fails as on-site abroad. A state of the
person's own country is still home ("Sydney, NSW" for somebody in Australia).
"""
from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import prefilter  # noqa: E402


@pytest.mark.parametrize("loc", ["Manchester, NH", "Manchester, New Hampshire", "Sale, VIC",
                                 "Bury, QC", "Stockport, OH", "Salford, ON", "Manchester, NH, US"])
def test_a_home_town_name_beside_a_state_abroad_fails(loc):
    verdict, why = prefilter.location_verdict(loc)
    assert verdict == "FAIL", (loc, why)


@pytest.mark.parametrize("loc", ["London, ON", "Cambridge, MA", "Birmingham, AL"])
def test_a_place_abroad_named_like_a_town_outside_the_metro_still_fails(loc):
    assert prefilter.location_verdict(loc)[0] == "FAIL"


@pytest.mark.parametrize("loc", ["Manchester", "Manchester, England", "Manchester, UK",
                                 "Manchester, England, United Kingdom", "Salford (Hybrid)",
                                 "Stockport, Cheshire"])
def test_home_is_still_home(loc):
    assert prefilter.location_verdict(loc)[0] == "PASS"


def test_a_state_of_the_persons_own_country_is_home(monkeypatch):
    """An invented home in Australia, whose metro holds Sydney."""
    monkeypatch.setattr(prefilter, "METRO", ["sydney", "parramatta"])
    monkeypatch.setattr(prefilter, "_CC", "au")
    assert prefilter.location_verdict("Sydney, NSW")[0] == "PASS"
    assert prefilter.location_verdict("Parramatta, NSW")[0] == "PASS"
    assert prefilter.location_verdict("Sydney, NS")[0] == "FAIL"     # a Canadian province
