"""The search window holds for every source, the employer's own board included.

An employer's board was let past the age rule because a posting still listed there is
still open. A search with a 14-day window then brought back an Ashby posting published
148 days before and a Greenhouse one 82 days before, at the top of its shortlist
(2026-11-03). The window is how old a posting may be, so it holds for every source, read
from the posting's own date where the board gives one. Invented employers only.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import prefilter  # noqa: E402
from openroles.models import ATS  # noqa: E402

TODAY = dt.date(2026, 11, 3)
HOME = "Manchester, England, United Kingdom"


def _job(portal, date, title="Data Analyst", company="Fernhill Freight"):
    return {"title": title, "company": company, "location": HOME, "portal": portal,
            "date": date, "url": f"https://{portal}.example/{company}/{date}"}


@pytest.mark.parametrize("portal", sorted(ATS))
def test_a_board_posting_past_the_window_is_dropped_whichever_board(portal):
    ok, why = prefilter.decide(_job(portal, "2026-06-08"), TODAY, 14)
    assert not ok
    assert why.startswith("age: posted 148 days ago on the employer's own board"), why


def test_a_fresh_board_posting_and_one_with_no_date_are_kept():
    ok, why = prefilter.decide(_job("greenhouse", "2026-10-30"), TODAY, 14)
    assert ok and why.startswith("4d old;"), why
    ok, why = prefilter.decide(_job("ashby", ""), TODAY, 14)
    assert ok and why.startswith("no date from the portal"), why


def test_the_persons_window_is_the_one_applied():
    """A 30-day window keeps what a 14-day window drops, on a board as anywhere else."""
    job = _job("greenhouse", "2026-10-13")
    assert not prefilter.decide(job, TODAY, 14)[0]
    assert prefilter.decide(job, TODAY, 30)[0]


def test_the_round_stage_drops_them_from_the_file(tmp_path):
    """Through the stage a round runs: the old board rows land in the dropped file."""
    rows = [_job("ashby", "2026-06-08", company="Wexmoor Analytics"),
            _job("greenhouse", "2026-08-13", company="Brackenhollow Mutual"),
            _job("greenhouse", "2026-10-31", company="Larkspur Retail"),
            _job("linkedin", "2026-10-30", company="Kestrel Freight")]
    src = tmp_path / "kept.json"
    src.write_text(json.dumps(rows))
    out, dropped = tmp_path / "out.json", tmp_path / "dropped.json"
    subprocess.run([sys.executable, os.path.join(ROOT, "tools", "prefilter.py"), str(src),
                    "--out", str(out), "--dropped", str(dropped), "--jobage", "14",
                    "--today", TODAY.isoformat()], check=True, capture_output=True)
    kept = {r["company"] for r in json.loads(out.read_text())}
    gone = {r["company"]: r["age_days"] for r in json.loads(dropped.read_text())}
    assert kept == {"Larkspur Retail", "Kestrel Freight"}
    assert gone == {"Wexmoor Analytics": 148, "Brackenhollow Mutual": 82}
