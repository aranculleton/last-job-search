"""A Greenhouse posting is judged by its own location, and its offices only when it names
none.

Figma filed a role "San Francisco, CA • New York, NY • United States", held "from one of our
US hubs or remotely in the United States", under the offices "Canada" and "US". The search read
the office tag as a place the job could be done, passed it as a Canada role, and a draft was
started for it (2026-10-30). The offices stay the place for a posting that says only "Hybrid".
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import ats_boards  # noqa: E402
from openroles.providers import READERS  # noqa: E402


def _greenhouse(boards_web, location, offices):
    """One Greenhouse posting read through the reader, as a round reads it."""
    boards_web.routes["boards-api.greenhouse.io/v1/boards/example/jobs"] = {"jobs": [
        {"id": 1, "title": "Data Scientist", "absolute_url": "https://example.com/1",
         "location": {"name": location},
         "offices": [{"name": o, "location": o} for o in offices]}]}
    [job] = READERS["greenhouse"].fetch("example")
    return job


def test_a_posting_that_names_its_place_is_judged_there_not_at_its_office_tags(boards_web):
    job = _greenhouse(boards_web, "San Francisco, CA • New York, NY • United States",
                      ["Canada", "US"])
    assert ats_boards._labels(job) == ["San Francisco, CA • New York, NY • United States"]


def test_a_posting_that_names_no_place_is_where_its_offices_are(boards_web):
    for own in ("Hybrid", "Remote", "", "Eastern Time Zone", "UTC+1"):
        job = _greenhouse(boards_web, own, ["Toronto, ON", "New York, NY"])
        assert "Toronto, ON" in ats_boards._labels(job), own


def test_another_system_s_second_locations_are_still_sites_of_the_job(boards_web):
    boards_web.routes["api.lever.co/v0/postings/example"] = [{
        "id": "a", "text": "Data Scientist", "hostedUrl": "https://jobs.lever.co/example/a",
        "createdAt": 0, "categories": {"location": "Toronto, ON",
                                       "allLocations": ["Toronto, ON", "Montreal, QC"]},
        "descriptionPlain": "Our analytics team."}]
    [job] = READERS["lever"].fetch("example")
    assert ats_boards._labels(job) == ["Toronto, ON", "Montreal, QC"]
