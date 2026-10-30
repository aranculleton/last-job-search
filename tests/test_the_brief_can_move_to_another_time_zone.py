"""The brief's time zone is the person's to change on the page, and its time is picked, not
typed (the maintainer, 2026-10-30: "this wouldnt let me edit the timezone. also manually
typing in the time seems weird")."""
from __future__ import annotations

import copy
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import person  # noqa: E402
import routines  # noqa: E402


@pytest.fixture
def reg(tmp_path):
    got = copy.deepcopy(json.load(open(person.path("routines.json"), encoding="utf-8")))
    p = tmp_path / "routines.json"
    p.write_text(json.dumps(got), encoding="utf-8")
    return str(p)


def test_a_new_zone_moves_the_brief_and_keeps_its_days_and_time(reg):
    got = routines.move(time="08:15", path=reg, zone="America/Toronto")
    saved = json.load(open(reg, encoding="utf-8"))
    assert saved["timezone"] == "America/Toronto"
    assert got["cron"].startswith("CRON_TZ=America/Toronto 15 8 ")


def test_a_zone_that_is_not_one_is_refused_and_nothing_changes(reg):
    before = open(reg, encoding="utf-8").read()
    with pytest.raises(ValueError):
        routines.move(time="08:15", path=reg, zone="Mars/Olympus")
    assert open(reg, encoding="utf-8").read() == before


def test_the_page_picks_the_time_and_lists_the_zones():
    js = open(os.path.join(ROOT, "templates", "app", "app.js"), encoding="utf-8").read()
    assert '{id: "time", type: "time", label: "Time"' in js
    assert '{id: "zone", type: "select", label: "Time zone"' in js and '"America/Toronto"' in js
