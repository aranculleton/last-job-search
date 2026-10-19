"""An exclusion stands only while today's rules would still cut it.

`throttle.ruled_out()` let an old exclusion keep blocking whenever its reason
matched the "still cuts" vocabulary, and that vocabulary named three things
today's screen does not cut: a degree stated as required, every wording of a pay
range (the screen's own FLAG text, "stated range tops out at ... under the
target", matched as a cut), and any relocation or on-site wording. So a posting
the current screen would only rank lower stayed out for good. Each kind is now
judged as today's rules judge it.
"""
from __future__ import annotations

import pytest
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import throttle  # noqa: E402

URL = "https://careers.example.com/jobs/7001"


def blocks(reason, **entry):
    """Does an older exclusion, with no fingerprint, still block its posting?"""
    e = {"url": URL, "title": "Supply Chain Analyst", "company": "Fernhill Freight",
         "status": "excluded", "exclusion_reason": reason, "excluded_date": "2026-09-01",
         **entry}
    urls, pairs = throttle.ruled_out({URL: e})
    return bool(urls or pairs)


def test_todays_cuts_still_stand():
    for reason in ("eligibility gate: British nationality or a security clearance stated as a "
                   "condition: \"SC clearance required\"",
                   "eligibility gate: a requirement to live in another country: \"US only\"",
                   "Welsh stated as a requirement: \"fluent Welsh is essential\"",
                   "job title is in Welsh: \"dadansoddwr data\"",
                   "professional designation stated as a requirement: \"ACA qualified\"",
                   "requires a professional licence",
                   "research-grade ML is the core of the role (4): \"causal inference\"",
                   "open to the employer's own staff only: \"internal applicants only\"",
                   "posting closed"):
        assert blocks(reason), reason


def test_a_range_stands_only_below_the_cut_line():
    assert throttle.SALARY_CUT_BELOW == 32_000             # the example person's
    assert blocks("stated range tops out at £30,000, below £32,000: a different job level, "
                  "not a negotiation")
    assert blocks("salary range £24,000 - £28,000, below the floor")
    # Above the cut line the screen flags and ranks; its own flag text is not a cut.
    assert not blocks("stated range tops out at £40,000, under the £42,000 target; a "
                      "decision input, never a cut")
    assert not blocks("knockout at triage, blocker 5: the whole stated range tops out at 38,000")
    assert not blocks("range max 45k")


def test_a_place_stands_only_where_the_location_gate_still_fails_it():
    reason = "pre-filter: location: on-site outside the Greater Manchester (london)"
    assert blocks(reason, location="London, England, United Kingdom")
    assert not blocks(reason, location="Salford, England, United Kingdom")
    # No place recorded: nothing to re-judge, and the prefilter reads the place for free.
    assert not blocks("requires relocation to Leeds")


def test_a_degree_never_stands():
    for reason in ("blocker 1: Master's degree is explicitly required",
                   "requires a Master's in a quantitative discipline, not held",
                   "PhD required"):
        assert not blocks(reason), reason


def test_the_persons_own_call_stands_whatever_it_says():
    assert blocks("not a degree-heavy employer I want", basis="person")


def test_a_ruling_on_a_named_row_of_the_persons_card_stands_while_the_row_does(tmp_path):
    # Their own triage card is today's rule for a ruling that names its row:
    # CLAUDE.md counts a knockout on it as a hard cut. It lapses when the row changes.
    import json

    import exclude
    path = str(tmp_path / "seen.json")
    e = exclude.add(URL, "knockout at triage, blocker 5: the whole stated range tops out at "
                    "38,000", "Supply Chain Analyst", "Fernhill Freight", path=path)
    assert list(e["rests_on"]) == ["triage #5"]
    urls, _ = throttle.ruled_out(json.load(open(path))["seen"])
    assert urls


@pytest.fixture(autouse=True)
def _no_rescreen(monkeypatch):
    """These pin how a ruling holds. Whether a better screen re-judges it is
    tests/test_build_versions.py's, so the app's own re-run versions are held off."""
    monkeypatch.setenv("LJS_RESCREEN", "off")
