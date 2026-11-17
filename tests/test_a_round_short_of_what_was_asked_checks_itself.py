"""A round asked for N that comes up short checks itself before it reports, widening by itself
where the search's own time allows, and says so either way.

From one person's evening (2026-11-16, issue #299): asked for 10, a round gave 7 and said the
market had no more, again and again. Every employer here is invented.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import run_round  # noqa: E402

TODAY = "2026-11-16"


def _row(n, company):
    return {"title": "Data Analyst", "company": company, "portal": "linkedin",
            "location": "Leeds, England, United Kingdom", "date": "2026-11-14",
            "first_seen": "2026-11-14", "url": f"https://www.linkedin.com/jobs/view/{8700000 + n}/",
            "fit": 80 - n, "priority": 90 - n, "opportunity": 70,
            "desc": "You will build SQL and Python reporting for the planning team."}


def _short_round(tmp_path, monkeypatch, capsys, scrape_secs):
    """A live round asked for 5 that finds 2, its scrape having taken `scrape_secs`; the
    command of the wider round it starts by itself, or None."""
    monkeypatch.setattr(run_round, "declined_now", lambda: {})
    monkeypatch.setattr(run_round, "_upgrades_line", lambda: "")
    ranked = [_row(1, "Ashby Freight"), _row(2, "Brantwood Foods")]

    def stage(cmd, log, deadline=None, ok=(0,)):
        tool = os.path.basename(cmd[1])
        if tool == "scrape_wide.py":
            folder = cmd[cmd.index("--out") + 1]
            os.makedirs(folder, exist_ok=True)
            for name in ("kept.json", "dropped.json"):
                with open(os.path.join(folder, name), "w", encoding="utf-8") as fh:
                    json.dump([], fh)
            with open(os.path.join(folder, "sources.json"), "w", encoding="utf-8") as fh:
                json.dump({"sites": [{"source": "cityboard", "requests": 57, "failed": 12,
                                      "why": ["12x HTTP 503"], "found": 0, "kept": 0}],
                           "boards": {"read": 3, "found": {}, "partial": {},
                                      "quiet": {"Quarrelwood Bank": "robots.txt answered 429"}},
                           "stopped": ""}, fh)
            run_round.TIMES.append(("scrape_wide.py", scrape_secs))
        elif tool == "fit.py":
            with open(cmd[cmd.index("--out") + 1], "w", encoding="utf-8") as fh:
                json.dump(ranked, fh)
        elif tool == "throttle.py":
            with open(cmd[cmd.index("--out") + 1], "w", encoding="utf-8") as fh:
                json.dump(ranked, fh)
        return 0

    widened = []
    monkeypatch.setattr(run_round, "run", stage)
    monkeypatch.setattr(run_round.subprocess, "call", lambda cmd: widened.append(list(cmd)) or 0)
    seen = tmp_path / "seen_jobs.json"
    seen.write_text('{"seen": {}}', encoding="utf-8")
    monkeypatch.setattr(sys, "argv", [
        "run_round.py", "--out", str(tmp_path / "r1"), "--seen", str(seen),
        "--summary-dir", str(tmp_path / "summ"), "--today", TODAY, "--jobage", "14",
        "--show", "5", "--pages", "1", "--no-seen-write"])
    run_round.main()
    return (widened[0] if widened else None), capsys.readouterr().out


def test_a_round_short_of_what_was_asked_widens_by_itself_inside_its_time(tmp_path, monkeypatch,
                                                                           capsys):
    cmd, said = _short_round(tmp_path, monkeypatch, capsys, 60)
    assert "self-check: found 2 of the 5 asked for" in said
    assert "self-check: 2 sources could not be read in full" in said
    assert "cityboard" in said and "Quarrelwood Bank" in said
    assert "self-check: searching wider by itself" in said
    assert cmd is not None and "--until" in cmd
    assert float(cmd[cmd.index("--until") + 1]) > 0


def test_a_round_with_no_time_for_another_scrape_says_so_and_stops(tmp_path, monkeypatch,
                                                                   capsys):
    cmd, said = _short_round(tmp_path, monkeypatch, capsys, run_round.ROUND_BUDGET_SEC - 60)
    assert cmd is None
    assert "self-check: no wider search:" in said and "this round's scrape took" in said
