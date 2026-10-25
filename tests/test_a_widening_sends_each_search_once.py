"""A widened round sends only the searches the round before did not have answered.

`run_round.py --expand` asks for more pages when the yield target is missed. Each widening
sent every request of the round before again, from page one: at twice the pages, nine in
ten of its LinkedIn requests repeated the first round's, and on a person's own computer,
under the request cap, it sent the same 300 again and searched nothing new. Now each
scrape writes the requests that were answered beside its postings, and the wider round
carries the postings over and sends the rest. A request that failed is asked again.

Fake portals only: nothing here reaches a job board.
"""
from __future__ import annotations

import json
import os
import sys

from pathlib import Path

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import ats_boards  # noqa: E402
import portals  # noqa: E402
import run_round  # noqa: E402
import scrape_wide  # noqa: E402


def _portal(root, name):
    d = root / name
    (d / "cli" / "dist").mkdir(parents=True)
    (d / "cli" / "dist" / "cli.mjs").write_text("// stand-in build\n")
    (d / "SKILL.md").write_text(f"---\nname: {name}\nenabled: true\n---\n\n# {name}\n")


@pytest.fixture
def portals_on(tmp_path, monkeypatch):
    root = tmp_path / "skills"
    for name in ("linkedin-search", "freehire-search"):
        _portal(root, name)
    monkeypatch.setattr(portals, "SKILLS", str(root))
    monkeypatch.setenv("LJS_STATE", str(tmp_path / "state"))
    monkeypatch.setattr(ats_boards, "fetch_all", lambda **k: ([], {}))
    monkeypatch.setattr(scrape_wide, "QUERIES", ["analyst", "planner"])
    monkeypatch.setattr(scrape_wide, "LOCATIONS", [scrape_wide.DEEP + " area"])
    monkeypatch.setattr(scrape_wide, "REMOTE_LOCATIONS", [])
    monkeypatch.setattr(scrape_wide, "EMPLOYERS", [])
    portals.cli.cache_clear()
    yield root
    portals.cli.cache_clear()


def _answers(calls, fail=()):
    """scrape_wide.run, answering every search with one posting of its own, or an error for
    the (portal, query, page) in `fail`."""
    def fake_run(cmd, timeout=90):
        skill = Path(cmd[2]).parts[-4]
        q = cmd[cmd.index("-q") + 1] if "-q" in cmd else ""
        page = cmd[cmd.index("--page") + 1] if "--page" in cmd else "1"
        calls.append((skill, q, page))
        if (skill, q, page) in fail:
            return None, "exit 1: connection reset"
        n = f"{skill}-{q}-{page}"
        return {"results": [{"id": n, "title": "Supply Chain Analyst", "company": "Oakmere Foods",
                             "url": f"https://jobs.example/{n}",
                             "location": "Manchester, England, United Kingdom",
                             "date": "2026-10-18"}]}, None
    return fake_run


def _scrape(out, monkeypatch, pages, *extra):
    monkeypatch.setattr(sys, "argv", ["scrape_wide.py", "--out", str(out), "--pages", str(pages),
                                      "--workers", "2", "--today", "2026-10-19", "--skip-canary",
                                      *extra])
    code = scrape_wide.main()
    return code, {r["url"] for r in json.load(open(out / "scraped.json"))}


def test_a_wider_scrape_sends_only_the_pages_the_round_before_did_not(portals_on, tmp_path,
                                                                      monkeypatch):
    first, wider, alone = [], [], []
    monkeypatch.setattr(scrape_wide, "run", _answers(first))
    _, before = _scrape(tmp_path / "r1", monkeypatch, 2)
    monkeypatch.setattr(scrape_wide, "run", _answers(wider))
    _, widened = _scrape(tmp_path / "r2", monkeypatch, 4, "--before", str(tmp_path / "r1"))
    monkeypatch.setattr(scrape_wide, "run", _answers(alone))
    _, whole = _scrape(tmp_path / "r3", monkeypatch, 4)
    # Every request of the wider plan went once across the two scrapes, never twice.
    assert not set(first) & set(wider)
    assert sorted(first + wider) == sorted(alone)
    assert {page for _, _, page in wider} == {"3", "4"}
    # And the wider round holds what a whole wider scrape finds.
    assert widened == whole and before < widened


def test_a_request_that_failed_is_asked_again(portals_on, tmp_path, monkeypatch):
    first, wider = [], []
    monkeypatch.setattr(scrape_wide, "run", _answers(first, fail={("freehire-search", "planner", "2")}))
    _scrape(tmp_path / "r1", monkeypatch, 2)
    monkeypatch.setattr(scrape_wide, "run", _answers(wider))
    _scrape(tmp_path / "r2", monkeypatch, 3, "--before", str(tmp_path / "r1"))
    assert ("freehire-search", "planner", "2") in wider
    answered = json.load(open(tmp_path / "r2" / scrape_wide.SENT))
    assert json.dumps(["fh", "planner", None, 2, 14]) in answered


def test_with_nothing_from_the_round_before_everything_is_sent(portals_on, tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(scrape_wide, "run", _answers(calls))
    (tmp_path / "empty").mkdir()
    _scrape(tmp_path / "r1", monkeypatch, 2, "--before", str(tmp_path / "empty"))
    assert len(calls) == 2 * 2 * 2           # two queries, two pages, two portals
    assert scrape_wide.before(None) == ([], set())


def test_a_request_is_told_apart_by_portal_place_page_and_freshness():
    li, fh = scrape_wide.linkedin, scrape_wide.freehire
    keys = {scrape_wide.request_key(j) for j in (
        ("linkedin", li, ("analyst", "Manchester", 1, 14)),
        ("linkedin", li, ("analyst", "Manchester", 1, 14, True)),
        ("linkedin", li, ("analyst", "Manchester", 2, 14)),
        ("linkedin", li, ("analyst", "Leeds", 1, 14)),
        ("linkedin", li, ("analyst", "Manchester", 1, 7)),
        ("freehire", fh, ("analyst", 1, 14)))}
    assert len(keys) == 6


def test_the_pool_names_only_the_requests_that_were_answered():
    answered = []
    jobs = [("p", lambda n: ([], None) if n % 2 else ([], "exit 1: no"), (n,)) for n in range(6)]
    scrape_wide.pool(jobs, workers=2, budget=60, on_sent=lambda job: answered.append(job[2][0]))
    assert sorted(answered) == [1, 3, 5]


def test_a_round_that_widens_hands_its_scrape_on_and_clears_it_after(tmp_path, monkeypatch):
    widened = []

    def stage(cmd, log, deadline=None, ok=(0,)):
        if os.path.basename(cmd[1]) == "hydrate.py":
            with open(cmd[cmd.index("--out") + 1], "w") as fh:
                json.dump([{"url": "https://careers.example.com/jobs/1", "desc": "body"}], fh)

    monkeypatch.setattr(run_round, "run", stage)
    monkeypatch.setattr(run_round.subprocess, "call", lambda cmd: widened.append(list(cmd)) or 2)
    scraped = tmp_path / "scraped.json"
    scraped.write_text("[]")
    out = tmp_path / "r1"
    monkeypatch.setattr(sys, "argv", ["run_round.py", "--out", str(out), "--from-scraped",
                                      str(scraped), "--summary-dir", str(tmp_path / "summ"),
                                      "--pages", "5", "--expand"])
    run_round.main()
    (cmd,) = widened
    held = cmd[cmd.index("--scrape-before") + 1]
    assert held == str(out / run_round.SCRAPED) and not os.path.exists(held)


def test_a_widened_round_passes_the_scrape_it_was_handed_to_the_portals(tmp_path, monkeypatch):
    stages = []

    def stage(cmd, log, deadline=None, ok=(0,)):
        stages.append(cmd)
        name = os.path.basename(cmd[1])
        if name == "scrape_wide.py":
            d = cmd[cmd.index("--out") + 1]
            os.makedirs(d, exist_ok=True)
            for f in ("kept.json", "scraped.json", "dropped.json"):
                with open(os.path.join(d, f), "w") as fh:
                    fh.write("[]")
        elif name == "hydrate.py":
            with open(cmd[cmd.index("--out") + 1], "w") as fh:
                fh.write("[]")

    monkeypatch.setattr(run_round, "run", stage)
    monkeypatch.setattr(run_round, "keep_requests", lambda *a, **k: None)
    monkeypatch.setattr(sys, "argv", ["run_round.py", "--out", str(tmp_path / "r2"),
                                      "--summary-dir", str(tmp_path / "summ"), "--pages", "10",
                                      "--round", "2", "--scrape-before", str(tmp_path / "held")])
    run_round.main()
    (scrape,) = [c for c in stages if os.path.basename(c[1]) == "scrape_wide.py"]
    assert scrape[scrape.index("--before") + 1] == str(tmp_path / "held")


def _runs_out(calls):
    """scrape_wide.run: "analyst" has one posting, on page one, and nothing after; "planner"
    answers every page with the same posting, as a board past its last page does."""
    def fake_run(cmd, timeout=90):
        skill = Path(cmd[2]).parts[-4]
        q = cmd[cmd.index("-q") + 1] if "-q" in cmd else ""
        page = cmd[cmd.index("--page") + 1] if "--page" in cmd else "1"
        calls.append((skill, q, page))
        if q == "analyst" and page != "1":
            return {"results": []}, None
        n = f"{skill}-{q}"
        return {"results": [{"id": n, "title": "Supply Chain Analyst", "company": "Oakmere Foods",
                             "url": f"https://jobs.example/{n}",
                             "location": "Manchester, England, United Kingdom",
                             "date": "2026-10-18"}]}, None
    return fake_run


def test_a_search_stops_at_the_page_where_it_runs_out(portals_on, tmp_path, monkeypatch, capsys):
    """Rule 12: a search walks its pages until one comes back empty or wholly duplicated. They
    were planned instead, and pages two to five went after page one held one posting."""
    calls = []
    monkeypatch.setattr(scrape_wide, "run", _runs_out(calls))
    monkeypatch.setattr(sys, "argv", ["scrape_wide.py", "--out", str(tmp_path / "r1"), "--pages",
                                      "5", "--workers", "1", "--today", "2026-10-19",
                                      "--skip-canary"])
    scrape_wide.main()
    for skill in ("linkedin-search", "freehire-search"):
        for q in ("analyst", "planner"):
            assert sorted(p for s, w, p in calls if (s, w) == (skill, q)) == ["1", "2"], (skill, q)
    assert "6 deeper page(s) not needed, their search had run out" in capsys.readouterr().err
