"""A round that runs long keeps what it found, and a portal that pushes back is
asked for less.

On a person's own computer a round was rate-limited by LinkedIn, ran into the scrape
stage's 45-minute limit, and was killed with everything in memory: no shortlist, no
files, and nothing in the log about LinkedIn or freehire. The pool now has a clock of
its own, backs off a portal that answers 429, writes what arrives as it arrives, and
prints a line a minute. Fake portals only: nothing here reaches a job board.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import scrape_wide  # noqa: E402

LIMITED = 'exit 1: {"error": "Request failed: 429 Too Many Requests", "code": "HTTP"}'


class FakeClock:
    """Time that moves only when something sleeps, shared by every worker."""

    def __init__(self):
        self.now, self.lock = 0.0, threading.Lock()

    def __call__(self):
        with self.lock:
            return self.now

    def sleep(self, seconds):
        with self.lock:
            self.now += seconds


def _row(n):
    return [{"url": f"https://jobs.example/{n}", "title": "Analyst", "portal": "fake"}]


def test_a_portal_that_hangs_is_stopped_by_the_budget_and_what_arrived_is_kept():
    done = []

    def slow(n):
        time.sleep(0.4)                      # a portal that answers, slowly
        done.append(n)
        return _row(n), None

    jobs = [("linkedin", slow, (n,)) for n in range(40)]
    started = time.monotonic()
    rows, tallies = scrape_wide.pool(jobs, workers=2, budget=1.0)
    took = time.monotonic() - started
    t = tallies["linkedin"]
    assert took < 3, "the pool ran past its budget"
    assert rows and len(rows) == len(done) < 40
    assert "budget ran out" in t.stopped
    assert any("not sent" in f for f in t.failed)


def test_a_portal_that_answers_429_backs_off_and_stops_and_the_other_carries_on():
    clock = FakeClock()
    calls = {"linkedin": 0, "freehire": 0}

    def limited(n):
        calls["linkedin"] += 1
        return [], LIMITED

    def fine(n):
        calls["freehire"] += 1
        return _row(f"f{n}"), None

    jobs = [("linkedin", limited, (n,)) for n in range(30)] + \
           [("freehire", fine, (n,)) for n in range(10)]
    rows, tallies = scrape_wide.pool(jobs, workers=4, budget=10_000, clock=clock, sleep=clock.sleep)
    li, fh = tallies["linkedin"], tallies["freehire"]
    assert li.limited == scrape_wide.POOL_MAX_LIMITED == calls["linkedin"]
    assert "429" in li.stopped and li.limit == 1              # its share halved, then stopped
    assert clock() >= scrape_wide.BACKOFF_SECONDS             # it waited before asking again
    assert calls["freehire"] == 10 and len(rows) == 10 and not fh.stopped
    assert "rate-limited (429)" in li.line()


def test_retry_after_is_honoured_when_the_portal_gives_it():
    assert scrape_wide.retry_after('Request failed: 429 Too Many Requests; Retry-After: 120') == 120
    assert scrape_wide.retry_after(LIMITED) is None
    assert scrape_wide.rate_limited(LIMITED) and not scrape_wide.rate_limited("timeout after 90s")


def test_a_cap_is_the_plan_not_a_failure():
    jobs = [("linkedin", lambda n: (_row(n), None), (n,)) for n in range(12)]
    rows, tallies = scrape_wide.pool(jobs, workers=3, cap=5)
    t = tallies["linkedin"]
    assert t.sent == 5 and len(rows) == 5 and t.capped == 7
    assert not t.stopped and not t.failed


def test_off_the_cloud_a_round_is_gentler_unless_the_person_says_otherwise(monkeypatch):
    assert scrape_wide.defaults(cloud=True) == (5, 10, None)
    pages, workers, cap = scrape_wide.defaults(cloud=False)
    assert pages <= 2 and workers <= 6 and cap and cap <= 500
    monkeypatch.setattr(scrape_wide._S, "SCRAPE_PAGES", 4, raising=False)
    monkeypatch.setattr(scrape_wide._S, "SCRAPE_MAX_REQUESTS", 900, raising=False)
    assert scrape_wide.defaults(cloud=False)[0] == 4 and scrape_wide.defaults(cloud=False)[2] == 900


def test_a_killed_scrape_leaves_files_the_round_can_go_on_with(tmp_path):
    out = tmp_path / "00_scrape"
    out.mkdir()
    today = "2026-10-19"
    rows = [{"url": f"https://jobs.example/{n}", "title": "Data Analyst", "company": "Kestrel Mutual",
             "location": "Manchester, England, United Kingdom", "date": today, "portal": "linkedin",
             "desc": None} for n in range(3)]
    (out / scrape_wide.PARTIAL).write_text(json.dumps(rows), encoding="utf-8")
    env = dict(os.environ, LJS_PROFILE=os.path.join(ROOT, "profile.example"))
    p = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "scrape_wide.py"), "--out",
                        str(out), "--finish", "--today", today], capture_output=True, text=True,
                       env=env)
    assert p.returncode == 2, p.stderr
    assert "PARTIAL" in p.stdout and "3 postings had arrived" in p.stdout
    assert (out / "kept.json").exists() and (out / "scraped.json").exists()
    assert len(json.loads((out / "scraped.json").read_text())) == 3
    assert not (out / scrape_wide.PARTIAL).exists()


def test_the_progress_line_says_how_far_along_a_portal_is():
    t = scrape_wide.Tally("linkedin", 400)
    t.sent, t.limited, t.timeouts = 120, 2, 1
    t.failed = ["x"] * 3
    line = t.line(left=14 * 60)
    assert line.startswith("progress: linkedin 120/400 sent, 3 failed")
    assert "2 rate-limited (429), 1 timed out" in line and "14 min left" in line
