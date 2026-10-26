"""A job row says where to apply and whether the posting is still listed, from what the round
itself read, with no request of its own; and every check carries its zone.

The round reads the employers' own boards during the scrape. A LinkedIn posting at an
employer with a board on file is matched there by title, and a board's own posting is open
by being on the board the round just read. Every name here is invented.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import apply_link  # noqa: E402
import app_model  # noqa: E402
import run_round  # noqa: E402

NOW = dt.datetime(2026, 10, 25, 9, 30, tzinfo=dt.timezone.utc)
BOARD = ("Oakmere Foods", "greenhouse", "oakmere")


def _boards(monkeypatch):
    monkeypatch.setattr(apply_link, "board_for",
                        lambda company: BOARD if "oakmere" in str(company).lower() else None)


def test_a_linkedin_posting_is_matched_to_the_board_the_round_read(monkeypatch):
    _boards(monkeypatch)
    scraped = [{"company": "Oakmere Foods", "portal": "greenhouse", "title": "Data Analyst",
                "url": "https://boards.greenhouse.io/oakmere/jobs/456"}]
    rows = [{"company": "Oakmere Foods", "title": "Data Analyst", "portal": "linkedin",
             "url": "https://www.linkedin.com/jobs/view/4012345678/?trk=x"},
            {"company": "Oakmere Foods", "title": "Data Analyst", "portal": "greenhouse",
             "url": "https://boards.greenhouse.io/oakmere/jobs/456"},
            {"company": "Quayside Foods", "title": "Planner", "portal": "linkedin",
             "url": "https://www.linkedin.com/jobs/view/4012345679/"}]
    got = run_round.link_checks(rows, scraped, NOW)
    assert got[0]["url"] == rows[0]["url"]                      # the row's own url is kept
    assert got[0]["apply_url"] == "https://boards.greenhouse.io/oakmere/jobs/456"
    assert got[0]["link_status"] == "open"
    assert got[0]["link_check"].endswith("checked 2026-10-25 09:30 UTC")
    assert got[1]["link_status"] == "open"
    assert got[2]["link_check"] == "not checked: LinkedIn is never fetched"


def test_the_round_summary_keeps_the_link_fields(monkeypatch, tmp_path):
    _boards(monkeypatch)
    short = tmp_path / "06_shortlist.json"
    short.write_text(json.dumps([{"priority": 80, "fit": 80, "company": "Oakmere Foods",
                                  "title": "Data Analyst", "portal": "linkedin",
                                  "url": "https://www.linkedin.com/jobs/view/1/"}]),
                     encoding="utf-8")
    kept = tmp_path / "kept.json"
    kept.write_text(json.dumps([{"company": "Oakmere Foods", "portal": "greenhouse",
                                 "title": "Data Analyst",
                                 "url": "https://boards.greenhouse.io/oakmere/jobs/9"}]),
                    encoding="utf-8")
    path = run_round.write_summary(str(short), str(tmp_path / "out"), "r1", scraped_path=str(kept))
    (row,) = json.loads(open(path, encoding="utf-8").read())
    assert row["apply_url"] == "https://boards.greenhouse.io/oakmere/jobs/9"
    assert row["link_status"] == "open" and row["link_check"].endswith(" UTC")
    shown = app_model.apply_link(row)
    assert shown["status"] == "open" and shown["kind"] == "employer"
    assert shown["checked_at"].endswith("Z") and shown["checked_on"] == shown["checked_at"][:10]


def test_a_stamp_is_in_utc_and_an_old_one_keeps_its_day_only():
    local = dt.datetime(2026, 10, 25, 9, 30)                      # this computer's own clock
    want = local.astimezone(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    assert apply_link._stamp(local) == want
    old = app_model.apply_link({"url": "https://jobs.example/a",
                                "link_check": "open on Acme's own board, checked 2026-10-24 18:00"})
    assert (old["status"], old["checked_on"], old["checked_at"]) == ("open", "2026-10-24", None)
    new = app_model.apply_link({"url": "https://jobs.example/a",
                                "link_check": "open on Acme's own board, checked 2026-10-24 18:00 UTC"})
    assert new["checked_at"] == "2026-10-24T18:00:00Z"
