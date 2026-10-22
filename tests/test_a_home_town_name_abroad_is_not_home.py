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


def _new_york(monkeypatch):
    """An invented home in New York, whose metro holds Manhattan."""
    import places
    monkeypatch.setattr(prefilter, "METRO", ["manhattan", "brooklyn", "jersey city"])
    monkeypatch.setattr(prefilter, "_CC", "us")
    monkeypatch.setattr(prefilter, "_HOME_REGION", "NY")
    monkeypatch.setattr(prefilter, "REGIONS", {"ny": "NY", "new york": "NY", "nj": "NJ"})
    monkeypatch.setattr(places, "REGIONS", {"ny": "NY", "new york": "NY", "nj": "NJ"})


def test_a_home_town_name_beside_another_state_at_home_is_read_again(monkeypatch):
    # "Manhattan, KS" passed as home for somebody in New York.
    _new_york(monkeypatch)
    verdict, why = prefilter.location_verdict("Manhattan, KS")
    assert verdict == "FLAG" and "KS" in why
    assert prefilter.location_verdict("Manhattan, Kansas")[0] == "FLAG"
    assert prefilter.location_verdict("Manhattan, NY")[0] == "PASS"
    assert prefilter.location_verdict("Brooklyn, New York")[0] == "PASS"
    assert prefilter.location_verdict("Manhattan")[0] == "PASS"


def test_a_state_the_profile_places_is_read_as_it_always_was(monkeypatch):
    # New Jersey is on this profile's region list, so its verdict is the region's rule,
    # never the new one.
    _new_york(monkeypatch)
    assert "town name in" not in prefilter.location_verdict("Jersey City, NJ")[1]


@pytest.mark.parametrize("loc", ["Bury St Edmunds, England", "Bury St. Edmunds",
                                 "Bolton-on-Dearne, England", "Salford-upon-Somewhere"])
def test_a_longer_town_that_starts_with_a_home_towns_name_is_read_again(loc):
    # "Bury St Edmunds" passed as Bury, in Greater Manchester; it is in Suffolk.
    verdict, why = prefilter.location_verdict(loc)
    assert verdict == "FLAG" and "starts with" in why, (loc, why)


@pytest.mark.parametrize("loc", ["Bury", "Ashton-under-Lyne", "Ashton-under-Lyne, England",
                                 "Manchester Airport", "Sale, England, United Kingdom"])
def test_a_home_town_and_a_town_of_its_own_on_the_list_still_pass(loc):
    assert prefilter.location_verdict(loc)[0] == "PASS", loc


def test_a_bare_on_after_a_home_town_is_a_province_not_a_longer_town(monkeypatch):
    monkeypatch.setattr(prefilter, "METRO", ["toronto"])
    monkeypatch.setattr(prefilter, "_CC", "ca")
    assert "starts with" not in prefilter.location_verdict("Toronto ON")[1]


def test_a_province_code_between_hyphens_is_not_a_longer_town(monkeypatch):
    # "Toronto-ON-Canada" was read as a town that starts with Toronto, as "Bolton-on-Dearne"
    # is: a town's name joins with a lower-case word, and ON is the province.
    monkeypatch.setattr(prefilter, "METRO", ["toronto", "mississauga"])
    monkeypatch.setattr(prefilter, "_CC", "ca")
    for loc in ("Toronto-ON-Canada", "Toronto-ON-CA", "Mississauga-ON-Canada"):
        assert "starts with" not in prefilter.location_verdict(loc)[1], loc


def test_a_home_town_named_like_a_state_is_the_town(monkeypatch):
    # For somebody in DC, "Washington, D.C." was read as the state of Washington.
    import places
    regions = {"dc": "DC", "district of columbia": "DC", "va": "VA", "md": "MD"}
    monkeypatch.setattr(prefilter, "METRO", ["washington", "arlington", "bethesda"])
    monkeypatch.setattr(prefilter, "_CC", "us")
    monkeypatch.setattr(prefilter, "_HOME_REGION", "DC")
    monkeypatch.setattr(prefilter, "REGIONS", regions)
    monkeypatch.setattr(places, "REGIONS", regions)
    for loc in ("Washington, D.C.", "Washington", "Washington, DC"):
        assert "outside" not in prefilter.location_verdict(loc)[1], loc
    assert "starts with" not in prefilter.location_verdict("Toronto in office")[1]
