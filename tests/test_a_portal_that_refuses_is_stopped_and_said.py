"""A portal that refuses is stopped, named before the sweep, and said why, once.

From one person's own computer, on one round: freehire answered every request with
403 Forbidden and the pool sent all 300 of them anyway ("300/300 sent, 300 failed",
with no cause); a board of their own answered the health probe and then, mid-sweep,
said it was redirecting searches to a page its robots.txt disallows, a thing the probe
could have caught before any sweep time was spent; the probe's report never reached the
round's log while the scrape ran; and a progress line for every portal, finished or not,
was printed every minute with a countdown that meant nothing to the finished ones, so
after 77 lines the log was mostly repeats.

Fake portals only, the pattern of tests/test_a_round_that_runs_long_keeps_what_it_found.py:
nothing here reaches a job board.
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

FORBIDDEN = 'exit 1: {"error":"freehire API request failed: 403 Forbidden","code":"SEARCH_FAILED"}'
LIMITED = 'exit 1: {"error": "Request failed: 429 Too Many Requests", "code": "HTTP"}'
SANDBOX = ("THROTTLED: Cityboard is redirecting searches to /sandbox (robots.txt "
           "disallows it); not followed.")


def _row(n):
    return [{"url": f"https://jobs.example/{n}", "title": "Analyst", "portal": "fake"}]


# ------------------------------------------------------------- M1: the pool's stop

def test_a_portal_that_answers_403_every_time_is_stopped_and_the_cause_is_said():
    calls = {"freehire": 0, "linkedin": 0}

    def refused(n):
        calls["freehire"] += 1
        return [], FORBIDDEN

    def fine(n):
        calls["linkedin"] += 1
        return _row(n), None

    jobs = [("freehire", refused, (n,)) for n in range(300)] + \
           [("linkedin", fine, (n,)) for n in range(20)]
    rows, tallies = scrape_wide.pool(jobs, workers=4, budget=10_000)
    fh = tallies["freehire"]
    # What was in flight when the streak was reached still lands; nothing after it goes.
    assert calls["freehire"] <= scrape_wide.POOL_MAX_FAILS + 4, calls
    assert 3 <= scrape_wide.POOL_MAX_FAILS <= 5
    assert "in a row" in fh.stopped and "403 Forbidden" in fh.stopped
    assert "403 Forbidden" in fh.line()
    assert calls["linkedin"] == 20 and len(rows) == 20 and not tallies["linkedin"].stopped


def test_failures_with_a_success_between_them_never_stop_a_portal():
    def flaky(n):
        return (_row(n), None) if n % 3 == 2 else ([], "timeout after 90s")

    rows, tallies = scrape_wide.pool([("linkedin", flaky, (n,)) for n in range(40)], workers=1)
    t = tallies["linkedin"]
    assert t.sent == 40 and not t.stopped and len(rows) == 13


def test_a_run_of_different_failures_is_not_a_run_of_identical_ones():
    errors = [FORBIDDEN, "timeout after 90s"]
    rows, tallies = scrape_wide.pool(
        [("linkedin", lambda n: ([], errors[n % 2]), (n,)) for n in range(12)], workers=1)
    assert tallies["linkedin"].sent == 12 and not tallies["linkedin"].stopped


class FakeClock:
    """Time that moves only when something sleeps, as in the long-round test."""

    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def test_the_429_backoff_is_unchanged_by_the_streak_stop():
    clock = FakeClock()
    rows, tallies = scrape_wide.pool([("linkedin", lambda n: ([], LIMITED), (n,))
                                      for n in range(30)], workers=1, budget=10_000,
                                     clock=clock, sleep=clock.sleep)
    t = tallies["linkedin"]
    assert t.sent == scrape_wide.POOL_MAX_LIMITED and "429" in t.stopped


@pytest.mark.parametrize("err,want", [
    (FORBIDDEN, "403 Forbidden"),
    (LIMITED, "429 Too Many Requests"),
    ("timeout after 90s", "timeout"),
    ("exit 1: " + SANDBOX, SANDBOX),
    ("JSONDecodeError: Unterminated string starting at: line 363 column 412 (char 65381)",
     "JSONDecodeError"),
    ('exit 1: {"error": "blocked", "code": "HTTP"}', "blocked"),
    ("empty output", "empty output"),
])
def test_a_failure_is_named_by_its_cause(err, want):
    assert scrape_wide.cause(err) == want


def test_only_an_answer_that_will_not_change_this_round_is_a_refusal():
    assert scrape_wide.refused(FORBIDDEN) == "403 Forbidden"
    assert scrape_wide.refused("exit 1: " + SANDBOX) == SANDBOX
    assert scrape_wide.refused('exit 1: {"error":"Request failed: 401 Unauthorized"}') \
        == "401 Unauthorized"
    for passing in (LIMITED, "timeout after 90s", "exit 1: 503", "empty output",
                    "JSONDecodeError: Unterminated string starting at: line 403 column 2"):
        assert scrape_wide.refused(passing) == "", passing


def test_the_cli_line_that_says_why_is_kept_over_its_last_line():
    """A board's CLI that says THROTTLED and then writes its JSON error last lost the
    THROTTLED line: run() kept only the last line of stderr."""
    say = ("import sys; sys.stderr.write(%r + chr(10) + '{\"error\": \"search failed\", "
           "\"code\": \"HTTP\"}' + chr(10)); sys.exit(1)" % SANDBOX)
    got, err = scrape_wide.run([sys.executable, "-c", say])
    assert got is None and SANDBOX in err and scrape_wide.refused(err) == SANDBOX
    # Exit 0 with nothing found and the refusal said is a refusal, not an empty market.
    quiet = ("import sys; sys.stderr.write(%r + chr(10)); print('{\"results\": []}')" % SANDBOX)
    got, err = scrape_wide.run([sys.executable, "-c", quiet])
    assert got is None and scrape_wide.refused(err) == SANDBOX
    found = ("import sys; sys.stderr.write(%r + chr(10)); "
             "print('{\"results\": [{\"id\": 1}]}')" % SANDBOX)
    got, err = scrape_wide.run([sys.executable, "-c", found])
    assert err is None and got["results"] == [{"id": 1}]


# --------------------------------------------- M4: the probe catches a refusal first

def _portal(root, name, front):
    d = root / name
    (d / "cli" / "dist").mkdir(parents=True)
    (d / "cli" / "dist" / "cli.mjs").write_text("// stand-in build\n")
    lines = "\n".join(f"{k}: {v}" for k, v in front.items())
    (d / "SKILL.md").write_text(f"---\nname: {name}\n{lines}\n---\n\n# {name}\n")


@pytest.fixture
def skills(tmp_path, monkeypatch):
    root = tmp_path / "skills"
    for name in ("linkedin-search", "freehire-search"):
        _portal(root, name, {"enabled": "true"})
    _portal(root, "cityboard-search", {"enabled": "true", "contract": "1", "crawl-delay": "0",
                                       "canary-query": "planner"})
    monkeypatch.setattr(portals, "SKILLS", str(root))
    monkeypatch.setattr(scrape_wide, "PORTAL_LOCATIONS", {"cityboard-search": ["Townsville, QX"]})
    monkeypatch.setenv("LJS_STATE", str(tmp_path / "state"))
    monkeypatch.setattr(ats_boards, "fetch_all", lambda **k: ([], {}))
    monkeypatch.setattr(scrape_wide, "PROBE_SECONDS", {})     # the probe fills it
    portals.cli.cache_clear()
    yield root
    portals.cli.cache_clear()


def test_the_probe_marks_a_portal_that_refuses_down_with_what_it_said(skills, monkeypatch):
    monkeypatch.setattr(scrape_wide, "linkedin", lambda *a, **k: ([{"url": "u"}], None))
    monkeypatch.setattr(scrape_wide, "freehire", lambda *a, **k: ([], FORBIDDEN))
    monkeypatch.setattr(scrape_wide, "contract", lambda *a, **k: ([], "exit 1: " + SANDBOX))
    health = scrape_wide.canary(30, portals.enabled({}))
    assert health["linkedin"][0] is True
    assert health["freehire"][0] is False and "403 Forbidden" in health["freehire"][1]
    assert health["cityboard"][0] is False and SANDBOX in health["cityboard"][1]
    assert scrape_wide.not_searched(health) == {"freehire": "403 Forbidden",
                                                "cityboard": SANDBOX}
    report, ok = scrape_wide.canary_report(health)
    assert not ok and SANDBOX in report and "403 Forbidden" in report


def test_a_probe_that_times_out_or_is_rate_limited_is_still_left_to_the_sweep(skills,
                                                                               monkeypatch):
    monkeypatch.setattr(scrape_wide, "linkedin", lambda *a, **k: ([], LIMITED))
    monkeypatch.setattr(scrape_wide, "freehire", lambda *a, **k: ([], "timeout after 90s"))
    monkeypatch.setattr(scrape_wide, "contract", lambda *a, **k: ([{"url": "u"}], None))
    health = scrape_wide.canary(30, portals.enabled({}))
    assert all(h for h, _ in health.values()) and scrape_wide.not_searched(health) == {}


def _fake_portals(calls, answers, wait=None):
    """scrape_wide.run, answering by which portal's CLI the command names: an error
    string for a portal in `answers`, one posting for the rest, after `wait` seconds."""
    def fake_run(cmd, timeout=90):
        skill = Path(cmd[2]).parts[-4]
        calls.append(skill)
        time.sleep((wait or {}).get(skill, 0))
        answer = answers.get(skill)
        if isinstance(answer, str):
            return None, answer
        n = len(calls)
        return {"results": [{"id": str(n), "title": "Supply Chain Analyst",
                             "company": "Oakmere Foods", "url": f"https://jobs.example/{n}",
                             "location": "Manchester, England, United Kingdom",
                             "date": "2026-10-18"}]}, None
    return fake_run


def _main(tmp_path, monkeypatch, *extra):
    out, log = tmp_path / "out", tmp_path / "progress.log"
    monkeypatch.setattr(sys, "argv", ["scrape_wide.py", "--out", str(out), "--pages", "1",
                                      "--workers", "2", "--max-requests", "6",
                                      "--today", "2026-10-19", "--log", str(log), *extra])
    return scrape_wide.main(), out, log


def test_a_refused_portal_is_named_before_the_sweep_and_sent_nothing_more(skills, tmp_path,
                                                                          monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(scrape_wide, "run", _fake_portals(
        calls, {"freehire-search": FORBIDDEN, "cityboard-search": "exit 1: " + SANDBOX}))
    code, out, log = _main(tmp_path, monkeypatch)
    said = capsys.readouterr()
    # The probe, and nothing after it.
    assert calls.count("freehire-search") == 1 and calls.count("cityboard-search") == 1
    assert calls.count("linkedin-search") == 1 + 6
    # M5: named in the round's log and on the stream run_round passes on as it arrives,
    # before any portal's sweep is reported, with what each portal said.
    for text in (said.err, log.read_text(encoding="utf-8")):
        first = text.find("progress:")
        assert first > 0, text
        for what in ("403 Forbidden", SANDBOX):
            assert -1 < text.find(what) < first, (what, text)
    health = json.loads((out / "00_portal_health.json").read_text())
    assert set(health["not_searched"]) == {"freehire", "cityboard"}
    # A round without two of its portals is not a full picture, and says so.
    assert code == 2 and "not searched" in said.out


def test_the_round_summary_says_what_each_down_portal_did(tmp_path):
    """run_round said every down portal had "0 results", the 403 one too."""
    import run_round
    (tmp_path / "00_scrape").mkdir()
    (tmp_path / "00_scrape" / "00_portal_health.json").write_text(json.dumps({
        "portals_down": ["freehire", "quietboard"],
        "detail": {"freehire": scrape_wide.REFUSED + "403 Forbidden",
                   "quietboard": "0 results for the probe query in its search"}}))
    assert run_round._portals_down(str(tmp_path)) == ["freehire", "quietboard"]
    assert run_round._down_detail(str(tmp_path), "freehire").endswith("403 Forbidden")
    assert run_round._down_detail(str(tmp_path), "quietboard").startswith("0 results")
    assert "0 results" in run_round._down_detail(str(tmp_path / "nowhere"), "freehire")


# ----------------------------------------------------- M2: progress, said once

def test_a_finished_portal_is_said_once_more_and_never_with_a_countdown(skills, tmp_path,
                                                                        monkeypatch, capsys):
    """linkedin finishes at once; the paced board takes about a second. The ticker runs
    every 50ms, so before this every tick reprinted linkedin with "N min left"."""
    calls = []
    _portal(skills, "slowboard-search", {"enabled": "true", "contract": "1",
                                         "crawl-delay": "0.1", "canary-query": "planner"})
    monkeypatch.setattr(scrape_wide, "PORTAL_LOCATIONS", {"slowboard-search": ["Townsville, QX"],
                                                          "cityboard-search": ["Townsville, QX"]})
    monkeypatch.setattr(scrape_wide, "PROGRESS_SECONDS", 0.05)
    monkeypatch.setattr(scrape_wide, "run", _fake_portals(
        calls, {"freehire-search": FORBIDDEN, "cityboard-search": "exit 1: " + SANDBOX},
        wait={"slowboard-search": 0.02}))
    _main(tmp_path, monkeypatch)
    lines = [ln for ln in capsys.readouterr().err.splitlines() if ln.startswith("progress:")]
    li = [ln for ln in lines if ln.startswith("progress: linkedin ")]
    slow = [ln for ln in lines if ln.startswith("progress: slowboard ")]
    # At most one line per change (0 to 6 sent) and the last; before, one every tick.
    assert 1 <= len(li) <= 8, li
    for mine in (li, slow):
        assert mine and mine[-1].endswith("done") and sum("done" in ln for ln in mine) == 1
        assert len(mine) == len(set(mine)), f"a line repeated while nothing changed: {mine}"
    for ln in lines:
        assert not ("min left" in ln and ("done" in ln or "stopped" in ln)), ln


def test_progress_prints_a_line_when_it_changes_and_a_still_portal_now_and_then():
    t = scrape_wide.Tally("linkedin", 10)
    t.ends = 1200.0
    shown: dict = {}
    assert scrape_wide.progress_lines([t], shown, now=60) == ["progress: linkedin 0/10 sent, "
                                                              "0 failed, 19 min left"]
    assert scrape_wide.progress_lines([t], shown, now=120) == []          # nothing changed
    t.sent = 4
    assert scrape_wide.progress_lines([t], shown, now=180)[0].startswith(
        "progress: linkedin 4/10 sent")
    # Silence is ambiguous, so a portal still sending that has not moved is said again
    # after HEARTBEAT_SECONDS: a hung portal is told from a finished one.
    later = 180 + scrape_wide.HEARTBEAT_SECONDS
    assert scrape_wide.progress_lines([t], shown, now=later)[0].endswith("min left")
    t.sent, t.finished = 10, True
    assert scrape_wide.progress_lines([t], shown, now=later + 60) == [
        "progress: linkedin 10/10 sent, 0 failed, done"]
    assert scrape_wide.progress_lines([t], shown, now=later + 9999) == []
