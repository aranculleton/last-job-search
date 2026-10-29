"""The page's newest search is the one that ran last, and a posting's age counts to today.

Round numbers restart, so the highest number is not the newest: Jobs said "Searched on 14
Oct" from r29 while r11 from the 24th held the real latest search, and its rows read "From
an earlier search". A search's own count of days also stayed as it was, so a row found on
the 21st said "posted 1 day ago" a week on (the maintainer's copy, 2026-10-29).
"""
import datetime as dt
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import app_model  # noqa: E402


def _round(d, name, rows):
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.json").write_text(json.dumps(rows), encoding="utf-8")


def test_the_newest_search_is_the_latest_day_not_the_highest_number(tmp_path, monkeypatch):
    rounds = tmp_path / "documents" / "rounds"
    _round(rounds, "r29", [{"url": "https://example.com/a", "first_seen": "2026-10-14"}])
    _round(rounds, "r11", [{"url": "https://example.com/b", "first_seen": "2026-10-24"},
                           {"url": "https://example.com/c", "first_seen": "2026-10-19"}])
    monkeypatch.setattr(app_model.person, "state", lambda *p: str(tmp_path.joinpath(*p)))
    app_model._ROUND_DAY.clear()
    assert os.path.basename(app_model.newest_round()) == "r11.json"
    assert app_model.round_day(str(rounds / "r11.json")) == dt.date(2026, 10, 24)
