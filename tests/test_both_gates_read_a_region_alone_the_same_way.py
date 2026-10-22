"""The location gate and the residence cut agree on a region named alone.

The location gate fails "Remote - APAC" and "Remote - North America" for somebody in the
UK, because neither region takes in the UK (places.region_takes_in_home), and passes
"Remote - EMEA", which does. The residence cut read a region only beside a word about
living there, so "This role is remote and open to candidates in APAC only." passed the
screen for the same person. Both read it the same way now: a region that leaves home out
cuts, one that takes it in passes.
"""
from __future__ import annotations

import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import places  # noqa: E402
import prefilter  # noqa: E402
import text_screen  # noqa: E402

BODY = " You will build planning models in SQL and Python."
PAIRS = [("Remote - APAC", "This role is remote and open to candidates in APAC only."),
         ("Remote - North America", "This role is remote and open to candidates in North America only."),
         ("Remote - LATAM", "We only hire in LATAM for this team."),
         ("Remote - EMEA", "This role is remote and open to candidates in EMEA only."),
         ("Remote (Europe)", "This role is remote within Europe.")]


def _agree():
    for loc, sentence in PAIRS:
        gate = prefilter.location_verdict(loc)[0]
        cut = bool(text_screen.residence_cut(sentence + BODY))
        assert gate in ("PASS", "FAIL"), (loc, gate)
        assert cut is (gate == "FAIL"), (loc, gate, sentence)
    return {loc: prefilter.location_verdict(loc)[0] for loc, _ in PAIRS}


def test_the_two_gates_agree_for_somebody_in_the_uk():
    seen = _agree()
    assert seen["Remote - APAC"] == "FAIL" and seen["Remote - EMEA"] == "PASS"


def test_the_two_gates_agree_for_somebody_inside_apac(monkeypatch):
    """An invented home in Australia: APAC takes it in, EMEA and North America do not."""
    monkeypatch.setattr(places, "HOME_COUNTRY_RX", re.compile(r"\baustralia\b"))
    seen = _agree()
    assert seen["Remote - APAC"] == "PASS" and seen["Remote - EMEA"] == "FAIL"


@pytest.mark.parametrize("sentence", [
    "Our APAC team works remotely across the region.",
    "We only sell in APAC.",
    "This role is remote within APAC time zones.",
])
def test_a_region_not_named_as_where_people_are_hired_is_not_cut(sentence):
    assert text_screen.residence_cut(sentence + BODY) is None
