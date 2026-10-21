"""A ruling on one posting does not rule out a new opening months later, and a score never blocks.

`throttle.ruled_out` keeps a ruling by the posting's address and by its title, employer
and city, so a posting relisted under a new address stays out. The second key had no
time limit: a new requisition for the same title, opened many months later under its own
address, was dropped at the prefilter on its predecessor's ruling, before anything read
its own body, while the relist rule beside it (RELIST_WINDOW) said that far out the same
title is more likely a new opening. And a "skipped" entry whose reason was a score
blocked for good, though the same reason as an exclusion is released.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import exclude  # noqa: E402
import prefilter  # noqa: E402
import throttle  # noqa: E402

MCR = "Manchester, England, United Kingdom"


@pytest.fixture(autouse=True)
def _no_rescreen(monkeypatch):
    monkeypatch.setenv("LJS_RESCREEN", "off")


def _job(n, day):
    return {"url": f"https://jobs.example.com/quillfield/{n}", "title": "Data Analyst",
            "company": "Quillfield Foods", "location": MCR, "date": day}


@pytest.fixture
def seen(tmp_path):
    path = str(tmp_path / "seen_jobs.json")
    exclude.add_many([{"url": _job(1, "")["url"], "title": "Data Analyst",
                       "company": "Quillfield Foods", "location": MCR,
                       "reason": 'Welsh stated as a requirement: "Fluency in Welsh is essential."'}],
                     today="2026-10-22", path=path)
    return path


def test_a_new_requisition_months_later_is_judged_on_its_own(seen):
    check = prefilter.already_ruled_out(seen, today=dt.date(2027, 6, 1))
    assert check(_job(977, "2027-05-30")) == ""


def test_a_relist_within_the_window_is_still_that_posting(seen):
    check = prefilter.already_ruled_out(seen, today=dt.date(2026, 11, 10))
    assert check(_job(978, "2026-11-09")).startswith("excluded in seen_jobs.json")


def test_the_ruled_address_itself_stays_out_for_good(seen):
    check = prefilter.already_ruled_out(seen, today=dt.date(2027, 6, 1))
    assert check(_job(1, "2027-05-30")).startswith("excluded in seen_jobs.json")


def test_a_ruling_in_the_persons_own_words_holds_for_the_title_whenever(tmp_path):
    path = str(tmp_path / "seen_jobs.json")
    exclude.add(_job(1, "")["url"], "not a team I want to join", "Data Analyst",
                "Quillfield Foods", basis="person", today="2026-10-22", path=path,
                location=MCR)
    check = prefilter.already_ruled_out(path, today=dt.date(2027, 6, 1))
    assert check(_job(977, "2027-05-30")).startswith("excluded in seen_jobs.json")


def test_a_skip_whose_reason_is_a_score_does_not_block():
    reason = "scored 58 (moderate fit), below the 60 pass bar"
    for status in ("skipped", "excluded"):
        e = {"url": "https://jobs.example.com/9", "status": status, "skip_reason": reason,
             "exclusion_reason": reason, "title": "Demand Planning Analyst",
             "company": "Quillfield Foods", "location": "Salford, England, United Kingdom",
             "skipped_date": "2026-10-22", "excluded_date": "2026-10-22"}
        urls, pairs = throttle.ruled_out({e["url"]: e}, "2026-10-23")
        assert urls == {} and pairs == {}, status


def test_a_skip_for_a_fact_still_blocks():
    e = {"url": "https://jobs.example.com/10", "status": "skipped",
         "skip_reason": "a duplicate of a posting already on the shortlist",
         "title": "Demand Planning Analyst", "company": "Quillfield Foods",
         "skipped_date": "2026-10-22"}
    urls, _ = throttle.ruled_out({e["url"]: e}, "2026-10-23")
    assert urls


def test_the_throttle_reads_the_window_on_its_own_day(seen, tmp_path):
    with open(seen, encoding="utf-8") as fh:
        entries = json.load(fh)["seen"]
    _, pairs = throttle.ruled_out(entries, "2027-06-01")
    assert throttle.ruled_pair(pairs, _job(977, "2027-05-30")) == ""
    _, pairs = throttle.ruled_out(entries, "2026-11-10")
    assert throttle.ruled_pair(pairs, _job(978, "2026-11-09"))
