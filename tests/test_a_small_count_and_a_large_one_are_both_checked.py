"""A count under ten, and one shaped like a year, are checked like any other figure.

`check_numbers.claim_key` dropped every count under ten with no unit, so "three retail
clients" rewritten as "nine retail clients" passed the code audit and the batch, even in a
sentence citing the one fact that says three. And the year test ran after the thousands
comma came off, so "2,000 suppliers" and "1,950 stores" were read as years and never
checked (the drafting audit, 2026-10-25).

The candidate is the example person; the sentences are invented.
"""
from __future__ import annotations

import copy
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import check_numbers as C  # noqa: E402

NINE = "At Saltmarsh Analytics I delivered footfall forecasts for nine retail clients."


def test_a_count_shaped_like_a_year_is_a_count():
    assert C.claims("Managed 2,000 suppliers across 40 depots") == {(2000.0, ""), (40.0, "")}
    assert C.claims("Cut costs for 1,950 stores") == {(1950.0, "")}
    assert C.claims("Ran 2050 experiments on the checkout") == {(2050.0, "")}
    # Years are still years.
    for year in ("In 2023 I joined the team", "BSc Mathematics (2016-2019)",
                 "the 2024 graduate scheme", "since 2019 forecasts", "2024 Weekend"):
        assert C.claims(year) == set(), year


def test_a_small_count_the_profile_counts_otherwise_is_a_finding():
    g = C.grounded()
    [f] = C.check(NINE, "letter", g)
    assert f["value"] == "nine" and f["normalised"] == "9" and "3" in f["hint"]
    assert C.check(NINE.replace("nine", "three"), "letter", g) == []
    # A small count of something the profile never counts is prose, as before.
    assert C.check("I would bring two habits to the role.", "letter", g) == []


def test_the_code_audit_reads_a_small_count_against_the_fact_it_cites():
    import draft_audit
    from test_one_drafting_call_per_posting import FIXTURE
    d = copy.deepcopy(FIXTURE["draft"])
    d["p4"] = NINE
    d["claim_map"] = [c for c in d["claim_map"] if c.get("field") != "p4"] + [
        {"field": "p4", "sentence": NINE, "cites": ["SA.2b2d"]}]
    flags = draft_audit.grounding_flags(d, {}, FIXTURE["posting"], FIXTURE["research"])
    hit = [f for f in flags if f["flag"] == "number-not-in-cited" and f["field"] == "p4"]
    assert hit and "nine counts what SA.2b2d counts as 3" in hit[0]["detail"], flags
    d["p4"] = NINE.replace("nine", "three")
    d["claim_map"][-1]["sentence"] = d["p4"]
    flags = draft_audit.grounding_flags(d, {}, FIXTURE["posting"], FIXTURE["research"])
    assert not [f for f in flags if f["flag"] == "number-not-in-cited" and f["field"] == "p4"]
