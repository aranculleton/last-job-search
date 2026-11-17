"""A search run again soon after asks the job sites for nothing they have just answered.

Nothing a round scraped was kept for the next one: the round prunes its scrape, so a search
run again nine minutes later, with only how jobs are scored changed, sent its 5,910 requests
again and took 24 minutes, though LinkedIn and freehire answer the same search much the same
an hour on (issue 309). Now what each search was answered is kept a short while beside the
rounds (never with the person's saved files), keyed by the site, the words, the place, the
page and how recent the jobs must be: a round within REQUEST_TTL sends only what is new or
gone stale, never serves an answer past it, and the fetch stage keeps each job's text for
BODY_TTL the same way. Fake job sites only; nothing here reaches the network.
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
import hydrate  # noqa: E402
import portals  # noqa: E402
import run_round  # noqa: E402
import scrape_wide  # noqa: E402


def _portal(root, name, extra=""):
    d = root / name
    (d / "cli" / "dist").mkdir(parents=True)
    (d / "cli" / "dist" / "cli.mjs").write_text("// stand-in build\n")
    (d / "SKILL.md").write_text(f"---\nname: {name}\nenabled: true\n{extra}---\n\n# {name}\n")


@pytest.fixture
def sites(tmp_path, monkeypatch):
    root = tmp_path / "skills"
    for name in ("linkedin-search", "freehire-search"):
        _portal(root, name)
    _portal(root, "cityboard-search", "contract: 1\ncrawl-delay: 0\npages: 1\n")
    monkeypatch.setattr(portals, "SKILLS", str(root))
    monkeypatch.setattr(ats_boards, "fetch_all", lambda **k: ([], {}))
    monkeypatch.setattr(scrape_wide, "QUERIES", ["analyst", "planner"])
    monkeypatch.setattr(scrape_wide, "LOCATIONS", [scrape_wide.DEEP + " area"])
    monkeypatch.setattr(scrape_wide, "PORTAL_LOCATIONS", {})
    monkeypatch.setattr(scrape_wide, "REMOTE_LOCATIONS", [])
    monkeypatch.setattr(scrape_wide, "EMPLOYERS", [])
    monkeypatch.setattr(scrape_wide, "SWEEP_STATE", str(tmp_path / "cursor.json"))
    monkeypatch.setattr(scrape_wide, "PROBE_SECONDS", {})
    portals.cli.cache_clear()
    yield tmp_path
    portals.cli.cache_clear()


def _answers(calls):
    def fake_run(cmd, timeout=90):
        skill = Path(cmd[2]).parts[-4]
        q = cmd[cmd.index("-q") + 1] if "-q" in cmd else ""
        page = cmd[cmd.index("--page") + 1] if "--page" in cmd else "1"
        calls.append((skill, q, page))
        n = f"{skill}-{q}-{page}"
        return {"results": [{"id": n, "title": "Supply Chain Analyst", "company": "Oakmere Foods",
                             "url": f"https://jobs.example/{n}",
                             "location": "Manchester, England, United Kingdom",
                             "date": "2026-10-18", "description": "We plan freight."}]}, None
    return fake_run


def _scrape(out, monkeypatch, *extra, cache=None):
    monkeypatch.setattr(sys, "argv", ["scrape_wide.py", "--out", str(out), "--pages", "2",
                                      "--workers", "2", "--today", "2026-10-19", "--skip-canary",
                                      *(["--cache", str(cache)] if cache else []), *extra])
    code = scrape_wide.main()
    return code, sorted(r["url"] for r in json.load(open(out / "scraped.json")))


def test_a_search_run_again_within_the_window_sends_nothing_it_was_just_answered(
        sites, monkeypatch):
    cache = sites / "rounds" / ".cache"
    first, again = [], []
    monkeypatch.setattr(scrape_wide, "run", _answers(first))
    _, found = _scrape(sites / "r1", monkeypatch, cache=cache)
    assert len(first) == 2 * 2 * 2 + 2                # two portals, two queries, two pages; the board
    monkeypatch.setattr(scrape_wide, "run", _answers(again))
    _, found_again = _scrape(sites / "r2", monkeypatch, cache=cache)
    assert again == [] and found_again == found       # the same postings, nothing sent


def test_nothing_is_served_past_the_window_and_a_new_search_is_asked(sites, monkeypatch):
    cache = sites / "rounds" / ".cache"
    now = [1_000_000.0]
    monkeypatch.setattr(scrape_wide, "_wall", lambda: now[0])
    calls = []
    monkeypatch.setattr(scrape_wide, "run", _answers(calls))
    _scrape(sites / "r1", monkeypatch, cache=cache)
    # A search added since is the only thing asked.
    calls.clear()
    monkeypatch.setattr(scrape_wide, "QUERIES", ["analyst", "planner", "buyer"])
    _scrape(sites / "r2", monkeypatch, cache=cache)
    assert {q for _, q, _ in calls} == {"buyer"}
    # Another window for how recent jobs must be is another search.
    calls.clear()
    _scrape(sites / "r3", monkeypatch, "--jobage", "7", cache=cache)
    assert len(calls) == 3 * 2 * 2 + 3
    # Past the window, LinkedIn and freehire are asked again; the paced board keeps its answer
    # longer, as it asks to be sent less.
    calls.clear()
    now[0] += scrape_wide.REQUEST_TTL + 1
    _scrape(sites / "r4", monkeypatch, cache=cache)
    assert {s for s, _, _ in calls} == {"linkedin-search", "freehire-search"}
    calls.clear()
    now[0] += scrape_wide.PACED_TTL
    _scrape(sites / "r5", monkeypatch, cache=cache)
    assert "cityboard-search" in {s for s, _, _ in calls}


def test_asked_for_fresh_answers_every_site_is_asked_again(sites, monkeypatch):
    cache = sites / "rounds" / ".cache"
    calls = []
    monkeypatch.setattr(scrape_wide, "run", _answers(calls))
    _scrape(sites / "r1", monkeypatch, cache=cache)
    calls.clear()
    _scrape(sites / "r2", monkeypatch, "--fresh", cache=cache)
    assert len(calls) == 2 * 2 * 2 + 2


def test_a_failed_request_is_never_kept():
    jobs = [("p", lambda n: ([{"url": f"u{n}"}], None) if n % 2 else ([], "exit 1: no"), (n,))
            for n in range(4)]
    answered = []
    scrape_wide.pool(jobs, workers=2, budget=60,
                     on_answer=lambda job, rows: answered.append((job[2][0], rows)))
    assert sorted(n for n, _ in answered) == [1, 3]


# ------------------------------------------------------------------ the fetch stage's bodies

def test_a_jobs_text_fetched_once_is_not_fetched_again_within_its_window(tmp_path, monkeypatch):
    fetched = []

    def fake_fetch(job, timeout=60):
        fetched.append(job["url"])
        return {**job, "desc": f"The text of {job['url']}.", "employment_type": "Full-time"}
    monkeypatch.setattr(hydrate, "_fetch", fake_fetch)
    rows = [{"url": f"https://www.linkedin.com/jobs/view/{n}", "portal": "linkedin",
             "title": "Planner", "desc": None} for n in range(3)]
    (tmp_path / "in.json").write_text(json.dumps(rows))
    keep = tmp_path / "rounds" / ".cache" / "bodies"
    now = [2_000_000.0]
    monkeypatch.setattr(hydrate, "_wall", lambda: now[0])

    def run(out):
        monkeypatch.setattr(sys, "argv", ["hydrate.py", str(tmp_path / "in.json"), "--out",
                                          str(tmp_path / out), "--keep-bodies", str(keep)])
        assert hydrate.main() == 0
        return json.load(open(tmp_path / out))
    first = run("a.json")
    assert len(fetched) == 3
    again = run("b.json")
    assert len(fetched) == 3 and again == first          # nothing fetched, the same rows
    now[0] += hydrate.BODY_TTL + 1
    run("c.json")
    assert len(fetched) == 6                             # past its window, fetched again


# ------------------------------------------------------------------ kept out of the saved files

def test_the_round_keeps_it_beside_the_rounds_never_among_the_saved_files(drive_round, tmp_path):
    import save_state
    calls, _ = drive_round()
    scrape = next(c for c, _ in calls if c[1].endswith("scrape_wide.py"))
    fetch = next(c for c, _ in calls if c[1].endswith("hydrate.py"))
    kept = scrape[scrape.index("--cache") + 1]
    assert kept == str(tmp_path / run_round.CACHE)
    assert fetch[fetch.index("--keep-bodies") + 1] == os.path.join(kept, "bodies")
    assert "--fresh" not in scrape
    calls, _ = drive_round("--fresh")
    scrape = next(c for c, _ in calls if c[1].endswith("scrape_wide.py"))
    assert "--fresh" in scrape
    # The person's rounds folder is never saved: what is kept beside it is not either.
    assert "rounds/**" in save_state.NEVER
    assert os.path.dirname(run_round.cache_dir(os.path.join("rounds", "r12"))).endswith("rounds")
