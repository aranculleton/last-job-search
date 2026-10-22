"""A remote role anchored in a state or province of another country is flagged, not passed.

"Remote, CA", "Remote - CA" and "Remote, California" passed the location gate clean for
somebody in the UK, Germany, Australia or India, while "Remote (Canada)" was flagged or
failed: the gate knew countries and regions, and a state is neither. A state of the
person's own country is home ("Remote, TX" for somebody in the US), and a code that is also
their own country's code is theirs ("CA" for somebody in Canada, "IN" in India).
"""
from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import places  # noqa: E402
import prefilter  # noqa: E402


@pytest.mark.parametrize("loc", ["Remote, CA", "Remote - CA", "Remote, California",
                                 "Remote, NY", "Remote (Ontario)", "Remote, ON, CA"])
def test_a_state_abroad_beside_remote_is_flagged_for_somebody_in_the_uk(loc):
    verdict, why = prefilter.location_verdict(loc)
    assert verdict == "FLAG", (loc, why)
    assert "state or province" in why


@pytest.mark.parametrize("loc", ["Remote, UK", "Remote - England", "Remote", "Remote, Manchester"])
def test_home_beside_remote_still_passes(loc):
    assert prefilter.location_verdict(loc)[0] == "PASS"


def test_a_remote_country_abroad_still_fails():
    assert prefilter.location_verdict("Remote, Texas, United States")[0] == "FAIL"


@pytest.mark.parametrize("home,loc,abroad", [
    ("US", "Remote, TX", None), ("US", "Remote, California", None),
    ("US", "Remote (Ontario)", "Ontario"),
    ("CA", "Remote, CA", None), ("CA", "Remote, ON", None), ("CA", "Remote, California", "California"),
    ("IN", "Remote, IN", None), ("DE", "Remote, DE", None), ("DE", "Remote, CA", "CA"),
    ("AU", "Remote, WA", None), ("GB", "Remote, WA", "WA"),
])
def test_a_state_is_abroad_only_outside_the_persons_own_country(monkeypatch, home, loc, abroad):
    monkeypatch.setattr(places, "_own_code", lambda: home)
    assert places.subdivision_abroad(loc) == abroad


def test_a_code_is_read_only_in_capitals():
    """"in", "or" and "me" are words before they are states."""
    assert places.subdivision_abroad("Remote, working in or near Manchester") is None
