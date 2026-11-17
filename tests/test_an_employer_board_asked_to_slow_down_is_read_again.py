"""An employer board the site asked to slow down is read again, and the round says so.

Two rounds one evening skipped 21 and then 17 Workday boards whole, the person's named
targets among them: every tenant is its own host, so openroles' two-at-a-time per host held
nothing back, sixteen workers asked one Workday data centre for sixteen robots.txt files at
once, it answered 429, and each board was given up on the spot. The robots.txt was asked for
again from cold every round, a board whose posting pages failed lost those postings, and the
only word of any of it was a "quiet:" line deep in round.log (issue 302).

Now a data centre takes two boards at a time, a board the site asked to pause is read once
more when its pause is over, robots.txt is kept on disk for a day, a posting whose page
failed goes on without its body for the fetch stage, and the scrape writes which boards it
could not read in its per-source report, for the round to say. Invented boards only; nothing reaches the network.
"""
from __future__ import annotations

import json
import os
import re
import sys
import threading
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import ats_boards  # noqa: E402
from openroles import _http  # noqa: E402

HOST = "fernhill.wd3.myworkdayjobs.com"
TOKEN = "fernhill.wd3/External"
LISTING = "/wday/cxs/fernhill/External/jobs"


@pytest.fixture
def places(monkeypatch):
    monkeypatch.setattr(ats_boards, "PLACES", re.compile(r"\bmanchester\b", re.I))
    monkeypatch.setattr(ats_boards, "title_verdict", lambda title: ("PASS", ""))
    monkeypatch.setattr(ats_boards, "location_verdict", lambda loc, title="": ("PASS", ""))


def _listing(*postings):
    return {"total": len(postings), "facets": [], "jobPostings": [
        {"title": title, "postedOn": "Posted Today", "locationsText": where,
         "externalPath": f"/job/{where.split(',')[0]}/{title.replace(' ', '-')}_R{n}"}
        for n, (title, where) in enumerate(postings, 1)]}


def _detail(text="We plan freight."):
    return {"jobPostingInfo": {"title": "Demand Planner", "location": "Manchester",
                               "jobDescription": f"<p>{text}</p>"}}


# ------------------------------------------------------------------ read again after a pause

def test_a_board_whose_robots_txt_said_slow_down_is_read_once_its_pause_is_over(boards_web,
                                                                                  places,
                                                                                  monkeypatch):
    answers = [(429, ""), (200, "User-agent: *\nAllow: /\n")]
    asked = []

    def robots(host):
        asked.append(host)
        return answers.pop(0) if answers else (200, "User-agent: *\nAllow: /\n")
    monkeypatch.setattr(_http, "robots_txt", robots)
    boards_web.routes[LISTING] = _listing(("Demand Planner", "Manchester, UK"))
    boards_web.routes["/wday/cxs/fernhill/External/job/"] = _detail()
    report: dict = {}
    rows, quiet = ats_boards.fetch_all({"Fernhill Freight": ("workday", TOKEN)},
                                       report=report, sleep=lambda s: None)
    assert [r["title"] for r in rows] == ["Demand Planner"] and quiet == {}
    assert asked == [HOST, HOST]                   # asked again, once
    assert report["slowed"] == ["Fernhill Freight"]
    assert report["recovered"] == ["Fernhill Freight"]
    assert "Fernhill Freight" in report["read"]


def test_it_waits_for_the_pause_the_host_asked_for_and_no_longer_than_the_round_allows(
        boards_web, places, monkeypatch):
    monkeypatch.setattr(_http, "robots_txt", lambda host: (429, ""))
    now = [0.0]
    held_until = 30.0
    monkeypatch.setattr(ats_boards, "_held", lambda host: now[0] < held_until)
    waits = []

    def sleep(s):
        waits.append(s)
        now[0] += s
    report: dict = {}
    _, quiet = ats_boards.fetch_all({"Fernhill Freight": ("workday", TOKEN)}, report=report,
                                    retry_until=100.0, clock=lambda: now[0], sleep=sleep)
    assert now[0] >= held_until                    # nothing was sent before the pause ended
    assert report["retried"] == ["Fernhill Freight"] and "Fernhill Freight" in quiet
    # A pause past the round's time is not waited out.
    now[0], held_until, report = 0.0, 500.0, {}
    _, quiet = ats_boards.fetch_all({"Fernhill Freight": ("workday", TOKEN)}, report=report,
                                    retry_until=100.0, clock=lambda: now[0], sleep=sleep)
    assert report["retried"] == [] and now[0] <= 100.0 + 5
    assert "HTTP 429" in quiet["Fernhill Freight"]


# ------------------------------------------------------------------ a data centre at a time

def test_workday_boards_on_one_data_centre_are_read_two_at_a_time(monkeypatch):
    lock, active, most = threading.Lock(), {"wd3": 0, "wd5": 0}, {"wd3": 0, "wd5": 0}

    def read(employer, token, queries=None, today=None):
        dc = token.split(".")[1].split("/")[0]
        with lock:
            active[dc] += 1
            most[dc] = max(most[dc], active[dc])
        time.sleep(0.05)
        with lock:
            active[dc] -= 1
        return [{"title": "x", "url": f"https://{token}/{employer}"}], None
    monkeypatch.setitem(ats_boards.FETCH, "workday", read)
    boards = {f"Tenant {n} {dc}": ("workday", f"t{n}{dc}.{dc}/External")
              for n in range(8) for dc in ("wd3", "wd5")}
    rows, quiet = ats_boards.fetch_all(boards)
    assert len(rows) == 16 and quiet == {}
    assert most == {"wd3": ats_boards.WORKDAY_PER_DC, "wd5": ats_boards.WORKDAY_PER_DC}


# ------------------------------------------------------------------ robots.txt for a day

class _Answer:
    def __init__(self, status, body):
        self.status, self._body = status, body.encode()

    def read(self, n=-1):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_robots_txt_is_kept_on_disk_for_a_day_and_a_pause_is_never_kept(tmp_path, monkeypatch):
    import urllib.error
    import urllib.request
    fetched = []
    status = [200]

    def urlopen(req, timeout=None):
        fetched.append(req.full_url)
        if status[0] != 200:
            raise urllib.error.HTTPError(req.full_url, status[0], "slow down", {}, None)
        return _Answer(200, "User-agent: *\nCrawl-delay: 2\nAllow: /\n")
    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(_http, "_ROBOTS", {})
    monkeypatch.setattr(_http, "_DELAYS", {})
    monkeypatch.setattr(_http, "_QUIET", {})
    cache = str(tmp_path / ".cache")
    wall = [1_000_000.0]
    # One round reads it and keeps it.
    assert ats_boards.prime_robots(cache, now=wall[0]) == 0
    assert _http.robots_allows(HOST, ["/x"])[0]
    ats_boards.keep_robots(cache, now=wall[0])
    assert len(fetched) == 1
    # The next round, an hour on, in a new process: read from disk, its crawl-delay kept.
    monkeypatch.setattr(_http, "_ROBOTS", {})
    monkeypatch.setattr(_http, "_DELAYS", {})
    assert ats_boards.prime_robots(cache, now=wall[0] + 3600) == 1
    assert _http.robots_allows(HOST, ["/x"])[0] and len(fetched) == 1
    assert _http._DELAYS[HOST] == 2
    # A day on, it is asked again.
    monkeypatch.setattr(_http, "_ROBOTS", {})
    assert ats_boards.prime_robots(cache, now=wall[0] + 25 * 3600) == 0
    # A 429 is a pause, never kept for a day.
    status[0] = 429
    assert not _http.robots_allows(HOST, ["/x"])[0]
    ats_boards.keep_robots(cache, now=wall[0] + 25 * 3600)
    kept = json.load(open(os.path.join(cache, ats_boards.ROBOTS_FILE)))
    assert HOST not in kept


# ------------------------------------------------------------------ a body that failed

def test_a_posting_whose_page_failed_goes_on_without_its_body(boards_web, places):
    boards_web.routes[LISTING] = _listing(("Demand Planner", "Manchester, UK"),
                                          ("Route Analyst", "Manchester, UK"))
    boards_web.routes["Route-Analyst_R2"] = (None, "HTTP 429")
    boards_web.routes["Demand-Planner_R1"] = _detail()
    rows, note = ats_boards.workday("Fernhill Freight", TOKEN, queries=[])
    by = {r["title"]: r for r in rows}
    assert set(by) == {"Demand Planner", "Route Analyst"}
    assert by["Demand Planner"]["desc"] == "We plan freight."
    assert by["Route Analyst"]["desc"] is None
    assert "left out" not in note and "without" in note


def test_the_fetch_stage_reads_a_workday_posting_kept_without_its_body(boards_web):
    import hydrate
    boards_web.routes["/wday/cxs/fernhill/External/job/Manchester/Route-Analyst_R2"] = _detail(
        "We route freight.")
    row = {"title": "Route Analyst", "company": "Fernhill Freight", "portal": "workday",
           "url": f"https://{HOST}/External/job/Manchester/Route-Analyst_R2", "desc": None}
    got = hydrate.fetch(row)
    assert got["desc"] == "We route freight." and not got.get("hydrate_error")


# ------------------------------------------------------------------ the round says so

@pytest.fixture
def boards_only(tmp_path, monkeypatch):
    """A scrape with no job site on: the employer boards alone."""
    import portals
    import scrape_wide
    (tmp_path / "skills").mkdir()
    monkeypatch.setattr(portals, "SKILLS", str(tmp_path / "skills"))
    monkeypatch.setattr(scrape_wide, "QUERIES", ["planner"])
    monkeypatch.setattr(scrape_wide, "LOCATIONS", [scrape_wide.DEEP + " area"])
    monkeypatch.setattr(ats_boards, "BOARDS", {
        "Fernhill Freight": ("workday", TOKEN), "Oakmere Foods": ("greenhouse", "oakmere"),
        "Kestrel Mutual": ("workday", "kestrel.wd3/Careers")})
    portals.cli.cache_clear()
    yield scrape_wide
    portals.cli.cache_clear()


def _scrape(out, monkeypatch, scrape_wide):
    monkeypatch.setattr(sys, "argv", ["scrape_wide.py", "--out", str(out), "--today",
                                      "2026-11-16", "--skip-canary", "--workers", "2"])
    return scrape_wide.main()


def test_a_scrape_that_could_not_read_most_employer_sites_says_which_and_is_partial(
        boards_only, tmp_path, monkeypatch, capsys):
    def fetch_all(notes=None, today=None, report=None, **k):
        report["read"].add("Oakmere Foods")
        report.update(slowed=["Fernhill Freight", "Kestrel Mutual"],
                      retried=["Fernhill Freight", "Kestrel Mutual"], recovered=[])
        why = (f"robots.txt on {HOST} could not be read (HTTP 429), so permission is "
               "unconfirmed")
        return [], {"Fernhill Freight": why, "Kestrel Mutual": why,
                    "Oakmere Foods": "resolved, but nothing matching the location filter"}
    monkeypatch.setattr(ats_boards, "fetch_all", fetch_all)
    out = tmp_path / "00_scrape"
    assert _scrape(out, monkeypatch, boards_only) == 2
    said = json.load(open(out / "sources.json"))["boards"]
    assert set(said["not_read"]) == {"Fernhill Freight", "Kestrel Mutual"} and said["cut_short"]
    assert said["line"].startswith("employer job sites not read: 2 of 3 (Fernhill Freight, "
                                   "Kestrel Mutual): 2 asked us to slow down")
    assert "tried again after the pause they asked for: 2, read then: 0" in said["line"]
    err = capsys.readouterr().err
    assert said["line"] in err
    # And the round passes the line on, before its prune.
    import run_round
    assert run_round._boards_unread(str(tmp_path)) == said["line"]


def test_a_board_read_with_nothing_in_range_is_read_and_an_old_stand_in_still_works(
        boards_only, tmp_path, monkeypatch):
    monkeypatch.setattr(ats_boards, "fetch_all", lambda notes=None, today=None: (
        [], {"Oakmere Foods": "resolved, but nothing matching the location filter",
             "Kestrel Mutual": f"robots.txt on {HOST} disallows /Careers/"}))
    out = tmp_path / "00_scrape"
    assert _scrape(out, monkeypatch, boards_only) == 0
    said = json.load(open(out / "sources.json"))["boards"]
    assert said["not_read"] == {} and said["line"] == "" and not said["cut_short"]
