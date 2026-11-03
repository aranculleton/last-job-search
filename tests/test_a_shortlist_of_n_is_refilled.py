"""A shortlist of N keeps taking the next row that passes every hard rule until it has N.

A search asked for 10. The cut took the first 10 ranked rows and nothing after, so rows
failing a hard rule (a posting past the search window, a public body the profile
excludes, one ruled out since) were cut from those 10 and 7 came back, with good rows left
below them (2026-11-03). The cut now passes over a row that fails a rule and takes the next,
and says how many it found when the round runs out. A ruling made after the round
(exclude.py add) is applied by cutting the round again (run_round.py --recut), never by
dropping a row from the table by hand. Invented employers only.
"""
from __future__ import annotations

import json
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import bar  # noqa: E402
import exclude  # noqa: E402
import run_round  # noqa: E402

TODAY = "2026-11-03"


def _row(n, company, date="2026-10-30", desc="SQL and Python.", portal="linkedin"):
    return {"title": "Data Analyst", "company": company, "date": date, "first_seen": date,
            "portal": portal, "desc": desc, "location": "Manchester, England, United Kingdom",
            "url": f"https://jobs.example/{n}", "fit": 90 - n, "priority": 100 - n}


@pytest.fixture
def round_dir(tmp_path, monkeypatch, judged):
    """A ranked shortlist whose top rows fail a hard rule, in a round's own folder."""
    monkeypatch.setattr(bar, "PUBLIC", re.compile(r"\bcouncil\b", re.I))
    monkeypatch.setattr(bar, "_PUBLIC_WHY", "public sector unless well paid")
    rows = [_row(1, "Wexmoor Analytics", date="2026-06-08", portal="ashby"),
            _row(2, "Northmere Council"),
            _row(3, "Fernhill Freight"),
            _row(4, "Larkspur Retail"),
            _row(5, "Kestrel Mutual"),
            _row(6, "Brackenhollow Foods")]
    d = tmp_path / "rounds" / "r9"
    d.mkdir(parents=True)
    (d / run_round.SHORTLIST).write_text(json.dumps(rows), encoding="utf-8")
    seen = tmp_path / "seen_jobs.json"
    seen.write_text('{"seen": {}}', encoding="utf-8")
    return d, seen, tmp_path / "summaries"


def _cut(d, seen, out, show):
    report = {}
    path = run_round.write_summary(str(d / run_round.SHORTLIST), str(out), "r9", show=show,
                                   rules=run_round.hard_rules(14, TODAY, str(seen)),
                                   report=report)
    return [r["company"] for r in json.loads(open(path, encoding="utf-8").read())], report


def test_rows_failing_a_rule_are_passed_over_and_the_next_taken(round_dir):
    d, seen, out = round_dir
    got, report = _cut(d, seen, out, 3)
    assert got == ["Fernhill Freight", "Larkspur Retail", "Kestrel Mutual"]
    assert report["asked"] == 3 and report["found"] == 3
    why = {r["company"]: r["skip_reason"] for r in report["passed_over"]}
    assert why["Wexmoor Analytics"].startswith("age: 148 days old, past the 14-day window")
    assert why["Northmere Council"].startswith("candidate's bar: public sector")


def test_a_round_that_runs_out_says_how_many_it_found(round_dir):
    d, seen, out = round_dir
    got, report = _cut(d, seen, out, 10)
    assert len(got) == 4
    lines = run_round.say_cut(report, 10)
    assert lines[-1] == ("shortlist: found 4 of the 10 asked for that pass every rule; "
                         "the round had no more")


def test_a_ruling_made_after_the_round_is_refilled_by_a_recut(round_dir, monkeypatch, capsys):
    """Through the command: --recut cuts the round's own shortlist again and keeps N."""
    d, seen, out = round_dir
    _cut(d, seen, out, 3)
    first = json.loads((out / "r9.json").read_text(encoding="utf-8"))
    first[0].update(apply_url="https://careers.example/fernhill/3", link_status="open")
    (out / "r9.json").write_text(json.dumps(first), encoding="utf-8")
    exclude.add("https://jobs.example/4", "not this kind of company", "Data Analyst",
                "Larkspur Retail", basis="person", today=TODAY, path=str(seen))
    monkeypatch.setattr(sys, "argv", ["run_round.py", "--out", str(d), "--recut", "--show", "3",
                                      "--seen", str(seen), "--summary-dir", str(out),
                                      "--today", TODAY, "--jobage", "14"])
    assert run_round.main() == 0
    rows = json.loads((out / "r9.json").read_text(encoding="utf-8"))
    assert [r["company"] for r in rows] == ["Fernhill Freight", "Kestrel Mutual",
                                            "Brackenhollow Foods"]
    # The apply link the round checked stays with its row: the scrape it was checked
    # against is gone by the time a round is cut again.
    assert rows[0]["apply_url"] == "https://careers.example/fernhill/3"
    assert rows[0]["link_status"] == "open"
    assert "passed over 3 that fail a rule now" in capsys.readouterr().out
