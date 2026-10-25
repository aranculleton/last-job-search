"""One role per employer keeps the role that fits the person best.

Where a round finds several roles at one employer, the job-scraper skill surfaces only the
highest scorer. The throttle kept the higher priority (fit times opportunity), so a fit-82
role was skipped as "scored higher" behind a fit-66 one with a fresher date, and the round
counted its yield on a shortlist with its best role hidden. Every employer is invented.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import throttle  # noqa: E402


def _row(n, company, title, fit, priority):
    return {"company": company, "title": title, "url": f"https://jobs.example/{n}",
            "fit": fit, "priority": priority}


def test_the_better_fit_is_kept_and_the_shortlist_stays_in_priority_order():
    rows = [_row(1, "Acme Freight", "Supply Chain Analyst", 82, 57),
            _row(2, "Acme Freight", "Data Analyst", 66, 102),
            _row(3, "Oakmere Foods", "Demand Planner", 70, 90)]
    kept, skipped = throttle.throttle(rows, {}, {}, {}, "2026-10-25")
    assert [r["title"] for r in kept] == ["Demand Planner", "Supply Chain Analyst"]
    assert [r["skip_reason"] for r in skipped] == [
        "same-employer duplicate: Supply Chain Analyst scored higher this run (fit 82 vs 66)"]


def test_a_tie_on_fit_keeps_the_higher_priority():
    rows = [_row(1, "Acme Freight", "Supply Chain Analyst", 75, 60),
            _row(2, "Acme Freight", "Data Analyst", 75, 80)]
    kept, skipped = throttle.throttle(rows, {}, {}, {}, "2026-10-25")
    assert [r["title"] for r in kept] == ["Data Analyst"] and len(skipped) == 1


def test_a_best_fit_held_for_another_reason_leaves_the_next_one_surfaced():
    rows = [_row(1, "Acme Freight", "Supply Chain Analyst", 82, 57),
            _row(2, "Acme Freight", "Data Analyst", 66, 102)]
    urls = {throttle.norm(rows[0]["url"]): "excluded in seen_jobs.json: closed"}
    kept, skipped = throttle.throttle(rows, {}, urls, {}, "2026-10-25")
    assert [r["title"] for r in kept] == ["Data Analyst"]
    assert skipped[0]["skip_reason"].startswith("already ruled out")
