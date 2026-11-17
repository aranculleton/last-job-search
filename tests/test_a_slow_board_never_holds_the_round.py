"""A person's slow job board never holds the round, nor keeps asking for employers it never has.

Two rounds one evening waited 20 minutes for their scrape, LinkedIn and freehire done after
under seven: the person's own boards, sent one request every few seconds as they ask, spent
their whole 20-minute budget, the last 13 minutes adding about 1% of what reached the list
and nothing at fit 75 or more. Most of that was each board asked for every named employer by
name, round after round: 400 requests for 24 new postings, one board 59 requests for none
(issue 301).

Now a paced board stops a minute after LinkedIn and freehire finish (never sooner than a few
minutes in), page one of every search having gone first and the rest carried to the next
round by its cursor; and an employer a board had nothing from is not asked for there again
for EMPTY_DAYS. A board searched on its own (LinkedIn and freehire off) keeps its whole
budget. Fake boards only.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import ats_boards  # noqa: E402
import portals  # noqa: E402
import scrape_wide  # noqa: E402


def _portal(root, name, extra=""):
    d = root / name
    (d / "cli" / "dist").mkdir(parents=True)
    (d / "cli" / "dist" / "cli.mjs").write_text("// stand-in build\n")
    (d / "SKILL.md").write_text(f"---\nname: {name}\nenabled: true\n{extra}---\n\n# {name}\n")


@pytest.fixture
def board(tmp_path, monkeypatch):
    root = tmp_path / "skills"
    for name in ("linkedin-search", "freehire-search"):
        _portal(root, name)
    _portal(root, "cityboard-search", "contract: 1\ncrawl-delay: 0\npages: 1\n")
    monkeypatch.setattr(portals, "SKILLS", str(root))
    monkeypatch.setattr(ats_boards, "fetch_all", lambda **k: ([], {}))
    monkeypatch.setattr(scrape_wide, "QUERIES", ["analyst"])
    monkeypatch.setattr(scrape_wide, "LOCATIONS", [scrape_wide.DEEP + " area"])
    monkeypatch.setattr(scrape_wide, "PORTAL_LOCATIONS", {})
    monkeypatch.setattr(scrape_wide, "REMOTE_LOCATIONS", [])
    monkeypatch.setattr(scrape_wide, "EMPLOYERS", [])
    monkeypatch.setattr(scrape_wide, "EMPLOYER_QUERIES", ["planner"])
    monkeypatch.setattr(scrape_wide, "_covered_by_ats", lambda: set())
    monkeypatch.setattr(scrape_wide, "SWEEP_STATE", str(tmp_path / "cursor.json"))
    monkeypatch.setattr(scrape_wide, "PROBE_SECONDS", {})
    portals.cli.cache_clear()
    yield tmp_path
    portals.cli.cache_clear()


def _answers(calls, slow=0.0, at=None):
    """Every search answered with one posting; the board's at `at(q)` (the employer it is
    searched for, or another), each of its requests taking `slow` seconds."""
    def fake_run(cmd, timeout=90):
        skill = Path(cmd[2]).parts[-4]
        q = cmd[cmd.index("-q") + 1] if "-q" in cmd else ""
        page = cmd[cmd.index("--page") + 1] if "--page" in cmd else "1"
        calls.append((skill, q, page))
        if skill == "cityboard-search" and slow:
            time.sleep(slow)
        company = at(q) if (at and skill == "cityboard-search") else "Oakmere Foods"
        n = f"{skill}-{q}-{page}"
        return {"results": [{"id": n, "title": "Supply Chain Analyst", "company": company,
                             "url": f"https://jobs.example/{n}",
                             "location": "Manchester, England, United Kingdom",
                             "date": "2026-10-18"}]}, None
    return fake_run


def _scrape(out, monkeypatch, today="2026-10-19"):
    monkeypatch.setattr(sys, "argv", ["scrape_wide.py", "--out", str(out), "--pages", "1",
                                      "--workers", "2", "--today", today, "--skip-canary"])
    return scrape_wide.main()


def _board_calls(calls):
    return [q for s, q, _ in calls if s == "cityboard-search"]


# ------------------------------------------------------------------ the round is not held

def test_a_paced_board_stops_soon_after_linkedin_and_freehire_finish(board, monkeypatch,
                                                                      capsys):
    monkeypatch.setattr(scrape_wide, "QUERIES", [f"role {n}" for n in range(40)])
    monkeypatch.setattr(scrape_wide, "PACED_AFTER_POOL", 0.3)
    monkeypatch.setattr(scrape_wide, "PACED_MIN", 0)
    calls = []
    monkeypatch.setattr(scrape_wide, "run", _answers(calls, slow=0.05))
    began = time.monotonic()
    _scrape(board / "r1", monkeypatch)
    sent = _board_calls(calls)
    assert 1 <= len(sent) < 40 and time.monotonic() - began < 1.9
    assert sent == [f"role {n}" for n in range(len(sent))]       # page one, in order, first
    err = capsys.readouterr().err
    assert "portals: cityboard stopped, LinkedIn and freehire had finished" in err
    assert "Later rounds reach them" in err
    # What it did not send is the next rounds' (the cursor): a board too slow for its own
    # first pages goes round all of them, round after round.
    cursor = json.load(open(board / "cursor.json"))["cityboard-search"]
    assert cursor["sent"] == len(sent)
    scrape_wide.build_tasks(portals.enabled({}), 1)
    assert scrape_wide.PLAN["cityboard-search"][0] == "all"


def test_a_board_searched_on_its_own_keeps_its_whole_budget(board, monkeypatch):
    # LinkedIn and freehire off: the board is the search, and nothing finishes before it.
    for name in ("linkedin-search", "freehire-search"):
        p = board / "skills" / name / "SKILL.md"
        p.write_text(p.read_text().replace("enabled: true", "enabled: false"))
    portals.cli.cache_clear()
    monkeypatch.setattr(scrape_wide, "QUERIES", [f"role {n}" for n in range(12)])
    monkeypatch.setattr(scrape_wide, "PACED_AFTER_POOL", 0)
    monkeypatch.setattr(scrape_wide, "PACED_MIN", 0)
    calls = []
    monkeypatch.setattr(scrape_wide, "run", _answers(calls, slow=0.01))
    _scrape(board / "r1", monkeypatch)
    assert len(_board_calls(calls)) == 12


# ------------------------------------------------------------------ employers it never has

def test_an_employer_a_board_had_nothing_from_is_not_asked_for_there_for_a_month(board,
                                                                                monkeypatch):
    monkeypatch.setattr(scrape_wide, "EMPLOYERS", ["Oakmere Foods", "Fernhill Freight"])
    # The board has Oakmere's roles; asked for Fernhill it answers with someone else's.
    calls = []
    monkeypatch.setattr(scrape_wide, "run", _answers(
        calls, at=lambda q: "Kestrel Mutual" if "Fernhill" in q else "Oakmere Foods"))
    _scrape(board / "r1", monkeypatch, "2026-10-19")
    assert {"Oakmere Foods planner", "Fernhill Freight planner"} <= set(_board_calls(calls))
    cursor = json.load(open(board / "cursor.json"))["cityboard-search"]
    assert cursor["empty"] == {"Fernhill Freight planner": "2026-10-19"}
    # The next round asks the board for Oakmere again, and not for Fernhill.
    calls.clear()
    _scrape(board / "r2", monkeypatch, "2026-10-20")
    sent = _board_calls(calls)
    assert "Oakmere Foods planner" in sent and "Fernhill Freight planner" not in sent
    # LinkedIn and freehire still search for Fernhill by name: only this board never has it.
    assert any("Fernhill" in q for s, q, _ in calls if s != "cityboard-search")
    # A month on, the board is asked again.
    calls.clear()
    _scrape(board / "r3", monkeypatch, "2026-11-19")
    assert "Fernhill Freight planner" in _board_calls(calls)


def test_a_failed_employer_search_teaches_nothing(board, monkeypatch):
    monkeypatch.setattr(scrape_wide, "EMPLOYERS", ["Fernhill Freight"])
    answer = _answers([])

    def failing(cmd, timeout=90):
        if "Fernhill Freight planner" in cmd and "cityboard" in cmd[2]:
            return None, "exit 1: connection reset"
        return answer(cmd, timeout)
    monkeypatch.setattr(scrape_wide, "run", failing)
    _scrape(board / "r1", monkeypatch)
    cursor = json.load(open(board / "cursor.json"))["cityboard-search"]
    assert not cursor.get("empty")
