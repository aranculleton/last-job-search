"""A board's card text after a title is not the title.

A row read from a card carried what the card shows after the title: a badge ("New",
"Promoted", "Actively hiring", "Easy Apply", "Reposted", "Be an early applicant") and the
row's own place again ("Senior Analytics Engineer New Toronto, Ontario, Canada"). Such a
title matched nothing it should: not the tracker's own role, not a dedupe, not a search of
the employer's board. It is cleaned where every row enters a round, and the board's own is
kept beside it. Nothing that is a word of the title is cut. Fake portals only.
"""
from __future__ import annotations

import json
import os
import sys

from pathlib import Path

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import ats_boards  # noqa: E402
import portals  # noqa: E402
import scrape_wide  # noqa: E402
from scrape_wide import clean_row, clean_title  # noqa: E402


@pytest.mark.parametrize("title,location,clean", [
    ("Senior Analytics Engineer New Toronto, Ontario, Canada", "Toronto, Ontario, Canada",
     "Senior Analytics Engineer"),
    ("Senior Analytics Engineer New Toronto, Ontario, Canada", "Toronto, ON",
     "Senior Analytics Engineer"),
    ("Data Analyst Promoted", "Leeds", "Data Analyst"),
    ("Data Analyst · Actively hiring", "Leeds", "Data Analyst"),
    ("Data Analyst Easy Apply", "Leeds", "Data Analyst"),
    ("Data Analyst Reposted 2 weeks ago", "Leeds", "Data Analyst"),
    ("Data Analyst Be an early applicant", "Leeds", "Data Analyst"),
    ("Data Analyst (New)", "Leeds", "Data Analyst"),
    ("Data Analyst Data Analyst with verification", "Leeds", "Data Analyst"),
    ("Data Engineer - Greater Toronto Area", "Toronto, ON", "Data Engineer"),
    ("Data Analyst - Austin, TX", "Austin, Texas, United States", "Data Analyst"),
])
def test_a_badge_and_the_rows_own_place_are_cut(title, location, clean):
    assert clean_title(title, location) == clean


@pytest.mark.parametrize("title,location", [
    ("Software Engineer, New Grad", "Toronto, ON"),
    ("New Grad Data Analyst", "Toronto, ON"),
    ("Data Scientist (New Grad)", "Toronto, ON"),
    ("Machine Learning Engineer, Applied", "Toronto, ON"),
    ("Senior Analyst - What's New", "Toronto, ON"),
    ("Analyst, New Business", "Toronto, ON"),
    ("Brand New", "Toronto, ON"),
    # A place that is not the row's own is the posting's to say.
    ("Data Analyst - Austin, TX", "Toronto, ON"),
    # A place that is a word of the title is not a repeat of the row's.
    ("Teacher of Reading", "Reading, UK"),
    ("Store Manager Toronto Eaton Centre", "Toronto, ON"),
    # Remote is the gate's to read where the location does not say it.
    ("Data Analyst - Toronto (Remote)", "Toronto, ON"),
    # Nothing left would be no title at all.
    ("Toronto", "Toronto"),
    ("New", ""),
])
def test_nothing_that_is_the_title_is_cut(title, location):
    assert clean_title(title, location) == title


def test_the_boards_own_title_is_kept_beside_it():
    row = clean_row({"title": "Data Analyst Promoted", "location": "Leeds"})
    assert row == {"title": "Data Analyst", "location": "Leeds",
                   "title_seen": "Data Analyst Promoted"}
    same = {"title": "Data Analyst", "location": "Leeds"}
    assert clean_row(same) == same
    assert clean_row({"title": None}) == {"title": None}


def _portal(root, name):
    d = root / name
    (d / "cli" / "dist").mkdir(parents=True)
    (d / "cli" / "dist" / "cli.mjs").write_text("// stand-in build\n", encoding="utf-8")
    (d / "SKILL.md").write_text(f"---\nname: {name}\nenabled: true\n---\n\n# {name}\n",
                                encoding="utf-8")


def test_every_row_a_round_takes_in_is_cleaned(tmp_path, monkeypatch):
    root = tmp_path / "skills"
    for name in ("linkedin-search", "freehire-search"):
        _portal(root, name)
    monkeypatch.setattr(portals, "SKILLS", str(root))
    monkeypatch.setenv("LJS_STATE", str(tmp_path / "state"))
    board = [{"id": "b1", "title": "Planner Actively hiring", "company": "Oakmere Foods",
              "url": "https://boards.example/oakmere/b1", "location": "Leeds",
              "date": "2026-10-18", "portal": "ats", "desc": "A posting."}]
    monkeypatch.setattr(ats_boards, "fetch_all", lambda **k: (board, {}))
    monkeypatch.setattr(scrape_wide, "QUERIES", ["analyst"])
    monkeypatch.setattr(scrape_wide, "LOCATIONS", [scrape_wide.DEEP + " area"])
    monkeypatch.setattr(scrape_wide, "REMOTE_LOCATIONS", [])
    monkeypatch.setattr(scrape_wide, "EMPLOYERS", [])
    portals.cli.cache_clear()

    def fake_run(cmd, timeout=90):
        skill = Path(cmd[2]).parts[-4]
        return {"results": [{"id": skill, "title": "Supply Chain Analyst New Leeds, England",
                             "company": "Oakmere Foods", "url": f"https://jobs.example/{skill}",
                             "location": "Leeds, England", "date": "2026-10-18"}]}, None
    monkeypatch.setattr(scrape_wide, "run", fake_run)
    out = tmp_path / "r1"
    monkeypatch.setattr(sys, "argv", ["scrape_wide.py", "--out", str(out), "--pages", "1",
                                      "--workers", "1", "--today", "2026-10-19", "--skip-canary"])
    try:
        scrape_wide.main()
    finally:
        portals.cli.cache_clear()
    rows = json.load(open(out / "scraped.json", encoding="utf-8"))
    titles = {r["title"] for r in rows}
    assert titles == {"Supply Chain Analyst", "Planner"}, titles
    assert {r.get("title_seen") for r in rows} == {"Supply Chain Analyst New Leeds, England",
                                                   "Planner Actively hiring"}
