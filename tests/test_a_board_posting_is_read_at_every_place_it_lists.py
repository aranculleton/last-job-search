"""A posting on an employer's board is kept when any place it lists is wanted.

Greenhouse and Lever postings name one primary location, and the rest sit beside
it: Greenhouse's `offices` (with `content=true`, which a round asks for) and
Lever's `categories.allLocations`. The readers looked at the primary alone, so a
posting located "Hybrid", a time zone or another city, with the person's own city
among its offices or other locations, was dropped before anything scored it.
And an employer on Lever's EU instance answered the global host as a bad token
does, so its board read as empty every round.

Every place a posting lists now goes through `_choose`, the same judge an Ashby
or Workday posting gets, so the location kept is the wanted one.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import ats_boards  # noqa: E402

HOME = "Manchester, England, United Kingdom"     # the example person's city


def _gh(n, location, offices):
    return {"id": n, "title": "Analyst", "absolute_url": f"u{n}", "location": {"name": location},
            "offices": [{"id": 9, "name": name, "location": loc} for name, loc in offices],
            "content": "", "first_published": "2026-10-01"}


def test_greenhouse_reads_the_offices_when_the_location_names_nowhere(boards_web):
    boards_web.routes["boards-api.greenhouse.io/v1/boards/acme/jobs"] = {"jobs": [
        _gh(1, "Hybrid", [("North", HOME)]),
        _gh(2, "US eastern time", [("NYC", "New York, NY")]),
        _gh(3, HOME, [])]}
    rows, err = ats_boards.greenhouse("Acme", "acme")
    assert err is None and [(r["id"], r["location"]) for r in rows] == [("gh-1", HOME), ("gh-3", HOME)]


def _lv(n, primary, others, **kw):
    return dict({"id": n, "text": "Analyst", "hostedUrl": f"u{n}", "createdAt": 0,
                 "categories": {"location": primary, "allLocations": [primary, *others]}}, **kw)


def test_lever_reads_every_location_a_posting_lists(boards_web):
    boards_web.routes["api.lever.co/v0/postings/acme"] = [
        _lv("a", "New York", [HOME]), _lv("b", "New York", ["Austin"]),
        _lv("c", "New York", [{"location": "Salford"}, {"name": "Austin"}])]
    rows, err = ats_boards.lever("Acme", "acme")
    assert err is None
    assert [(r["id"], r["location"]) for r in rows] == [("lv-a", HOME), ("lv-c", "Salford")]


def test_a_remote_lever_posting_says_so_in_its_location(boards_web):
    boards_web.routes["api.lever.co/v0/postings/acme"] = [
        _lv("a", HOME, [], workplaceType="remote")]
    [row], _ = ats_boards.lever("Acme", "acme")
    assert row["location"] == f"Remote - {HOME}"


def test_lever_tries_its_eu_host_when_the_global_one_does_not_know_the_board(boards_web):
    boards_web.routes["api.eu.lever.co/v0/postings/acme"] = [_lv("a", HOME, [])]
    boards_web.routes["api.lever.co/v0/postings/acme"] = ({"ok": False}, None)
    rows, err = ats_boards.lever("Acme", "acme")
    assert err is None and len(rows) == 1
    assert boards_web.calls[-1][0].startswith("https://api.eu.lever.co/")
    # Refused by the EU host's robots.txt, it is not read, and the board reads as before.
    boards_web.calls.clear()
    boards_web.robots["api.eu.lever.co"] = (200, "User-agent: *\nDisallow: /\n")
    rows, err = ats_boards.lever("Acme", "acme")
    assert rows == [] and err and len(boards_web.calls) == 1


def test_a_bare_remote_beside_foreign_offices_is_remote_there():
    # "Remote" with offices only in New York and Austin is a US remote role: it reaches
    # the gate anchored, to be flagged, never as remote from anywhere.
    location, _ = ats_boards._choose(["Remote", "New York, NY", "Austin, TX"], "Data Analyst")
    assert location == "Remote - New York, NY; Austin, TX"
    # Beside a wanted place it is just remote, and the wanted place speaks for itself.
    location, verdict = ats_boards._choose(["Remote", HOME], "Data Analyst")
    assert verdict == "PASS" and "New York" not in location
    # Alone, it is what it always was.
    assert ats_boards._choose(["Remote"], "Data Analyst")[0] == "Remote"


def test_one_place_written_twice_is_kept_once():
    assert ats_boards._choose(["Manchester, England", "Manchester"], "Data Analyst")[0] == "Manchester, England"


def test_anchoring_never_says_remote_twice(monkeypatch):
    # A market whose gate flags a US remote role, which the example person's does not.
    monkeypatch.setattr(ats_boards, "location_verdict",
                        lambda loc, title="": ("PASS", "") if loc == "Remote" else ("FLAG", "US"))
    location, _ = ats_boards._choose(["Remote", "Remote - New York, NY"], "Data Analyst")
    assert location == "Remote - New York, NY"
