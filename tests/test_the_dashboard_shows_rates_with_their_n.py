"""The dashboard shows a rate with the number it rests on, never a bare count.

/html-report drew "by channel" and "by sector" as counts: 12 portal, 3 referral. That says
nothing about which route works, and `what_works.py brief search` already computed rates
by route with sample floors that the dashboard never used. `what_works.rates()` is that
counting as a table a dashboard can draw, and /html-report reads it.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "network"))

import what_works as W  # noqa: E402
# Imported here, at the suite's state: the command imports it, and a first import
# under this file's temporary state would bind every later test to that folder.
import state  # noqa: E402,F401

TODAY = "2026-10-21"


def _app(i, channel, status, date="2026-06-01"):
    return {"date": date, "company": "Employer %d" % i, "role": "Analyst %d" % i,
            "status": status, "channel": channel, "sector": "retail", "notes": ""}


TRACKER = ([_app(i, "referral", "interview" if i < 3 else "rejected") for i in range(5)]
           + [_app(10 + i, "portal", "interview" if i < 2 else "rejected") for i in range(21)]
           + [_app(40, "portal", "applied", date="2026-10-15"),      # sent, no answer yet
              _app(41, "portal", "drafted")])                        # never sent


def test_each_channel_is_a_rate_with_its_n():
    got = W.rates(TRACKER, "channel", TODAY)
    assert got["groups"] == [
        {"group": "portal", "reached": 2, "decided": 21, "rate": 0.095, "enough": True},
        {"group": "referral", "reached": 3, "decided": 5, "rate": 0.6, "enough": False}]
    assert got["waiting"] == 1 and got["min_group"] == W.MIN_GROUP


def test_the_same_counting_as_brief_search():
    total = W.rates(TRACKER, "sector", TODAY)["groups"]
    cases = W.application_cases(TRACKER, TODAY)
    assert [(g["reached"], g["decided"]) for g in total] == [
        (sum(c["won"] for c in cases), len(cases))]


def test_the_command_prints_it_as_json(capsys, tmp_path, monkeypatch):
    import csv
    monkeypatch.setenv("LJS_STATE", str(tmp_path))
    with open(tmp_path / "job_search_tracker.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(TRACKER[0]))
        w.writeheader()
        w.writerows(TRACKER)
    assert W.main(["rates", "--by", "channel", "--today", TODAY]) == 0
    assert json.loads(capsys.readouterr().out)["groups"][0]["group"] == "portal"


def test_html_report_draws_the_rates_not_counts():
    text = (Path(ROOT) / ".claude" / "commands" / "html-report.md").read_text(encoding="utf-8")
    assert "python3 tools/what_works.py rates --by channel" in text
    assert "python3 tools/what_works.py rates --by sector" in text
    assert "too few to compare" in text
    assert "company count per sector" not in text
