"""A ruling on one posting holds for that title at that employer in that city, not everywhere.

`throttle.ruled_out()` also blocks a posting by its (title, employer) pair, so a
relisted posting under a new URL stays out. The pair ignored the place: a posting
cut for its language in one city, or for a place the location gate fails, blocked
the same title at that employer in every other city, the person's own included.
"""
from __future__ import annotations

import pytest
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import throttle  # noqa: E402


def _ruled(**entry):
    e = {"url": "https://careers.example.com/jobs/51", "title": "Data Analyst",
         "company": "Kestrel Mutual", "status": "excluded", "excluded_date": "2026-09-20",
         "exclusion_reason": "Welsh stated as a requirement: \"fluent Welsh is essential\"",
         **entry}
    return throttle.ruled_out({e["url"]: e})


def _job(location):
    return {"url": "https://careers.example.com/jobs/77", "title": "Data Analyst",
            "company": "Kestrel Mutual", "location": location}


def test_the_same_title_elsewhere_is_judged_on_its_own():
    _, pairs = _ruled(location="Cardiff, Wales, United Kingdom")
    assert throttle.ruled_pair(pairs, _job("Cardiff, Wales, United Kingdom"))
    assert not throttle.ruled_pair(pairs, _job("Manchester, England, United Kingdom"))


def test_a_ruling_that_recorded_no_place_holds_everywhere_as_before():
    _, pairs = _ruled()
    assert throttle.ruled_pair(pairs, _job("Manchester, England, United Kingdom"))


def test_the_throttle_reads_the_place_too():
    urls, pairs = _ruled(location="Cardiff, Wales, United Kingdom")
    row = {**_job("Salford, England, United Kingdom"), "priority": 70, "fit": 80}
    kept, skipped = throttle.throttle([row], {}, urls, pairs, "2026-10-14")
    assert kept and not skipped
    row = {**_job("Cardiff, Wales, United Kingdom"), "priority": 70, "fit": 80}
    kept, skipped = throttle.throttle([row], {}, urls, pairs, "2026-10-14")
    assert skipped and skipped[0]["skip_reason"].startswith("already ruled out")


@pytest.fixture(autouse=True)
def _no_rescreen(monkeypatch):
    """These pin how a ruling holds. Whether a better screen re-judges it is
    tests/test_build_versions.py's, so the app's own re-run versions are held off."""
    monkeypatch.setenv("LJS_RESCREEN", "off")
