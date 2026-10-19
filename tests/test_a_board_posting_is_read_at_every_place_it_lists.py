"""A posting on an employer's board is kept when any place it lists is wanted.

Greenhouse and Lever postings name one primary location, and the rest sit beside
it: Greenhouse's `offices` (with `content=true`, which a round asks for) and
Lever's `categories.allLocations`. The readers looked at the primary alone, so a
posting located "Hybrid", a time zone or another city, with the person's own city
among its offices or other locations, was dropped before anything scored it.
And an employer on Lever's EU instance answered the global host as a bad token
does, so its board read as empty every round.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import ats_boards  # noqa: E402

HOME = "Manchester, England, United Kingdom"     # the example person's city


def _gh(location, offices):
    return {"id": 1, "title": "Analyst", "absolute_url": "u", "location": {"name": location},
            "offices": [{"id": 9, "name": n, "location": loc} for n, loc in offices],
            "content": "", "first_published": "2026-10-01"}


def test_greenhouse_reads_the_offices_when_the_location_names_nowhere(monkeypatch):
    jobs = [_gh("Hybrid", [("North", HOME)]), _gh("US eastern time", [("NYC", "New York, NY")]),
            _gh(HOME, [])]
    monkeypatch.setattr(ats_boards, "_get", lambda url: {"jobs": jobs})
    rows, err = ats_boards.greenhouse("Acme", "acme")
    assert err is None and [r["location"] for r in rows] == [f"{HOME}; Hybrid", HOME]


def _lv(primary, others):
    return {"id": "x", "text": "Analyst", "hostedUrl": "u", "createdAt": 0,
            "categories": {"location": primary, "allLocations": [primary, *others]}}


def test_lever_reads_every_location_a_posting_lists(monkeypatch):
    data = [_lv("New York", [HOME]), _lv("New York", ["Austin"]),
            {"id": "y", "text": "Analyst", "hostedUrl": "u", "createdAt": 0,
             "categories": {"location": "New York",
                            "allLocations": [{"location": "Salford"}, {"name": "Austin"}]}}]
    monkeypatch.setattr(ats_boards, "_get", lambda url: data)
    rows, err = ats_boards.lever("Acme", "acme")
    assert err is None
    assert [r["location"] for r in rows] == [f"{HOME}; New York", "Salford; New York"]


def test_lever_tries_its_eu_host_when_the_global_one_does_not_know_the_board(monkeypatch):
    asked = []

    def get(url):
        asked.append(url)
        return [_lv(HOME, [])] if "api.eu.lever.co" in url else {"ok": False}
    monkeypatch.setattr(ats_boards, "_get", get)
    monkeypatch.setattr(ats_boards, "robots_allows", lambda host, paths: (True, "allowed"))
    rows, err = ats_boards.lever("Acme", "acme")
    assert err is None and len(rows) == 1 and "api.eu.lever.co" in asked[-1]
    # Refused by the EU host's robots.txt, it is not read, and the board reads as before.
    asked.clear()
    monkeypatch.setattr(ats_boards, "robots_allows", lambda host, paths: (False, "disallowed"))
    rows, err = ats_boards.lever("Acme", "acme")
    assert rows == [] and err and len(asked) == 1
