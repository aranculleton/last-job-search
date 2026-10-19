"""A paced board's budget is spent on what matters first, and what it leaves is named.

One person's board had 243 requests planned at a crawl-delay of 5 seconds. At the 7 or so
requests a minute it managed, its 20-minute budget held about 150 of them, whatever
happened; another board sent 43 of 174. Which ones went was decided by the order the list
happened to be built in: every page of the first search before page one of the second,
and nothing said which searches never ran. Now page one of every search at the first
place goes first, the places further out last, the round says up front how much will fit,
and when it stops it names what it did not send. Fake boards only.
"""
from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import portals  # noqa: E402
import scrape_wide  # noqa: E402

HOME, NEXT, FAR = "Home City, R, C", "Next Town, R, C", "Far Town, R, C"


@pytest.fixture
def board(tmp_path, monkeypatch):
    for name in ("linkedin-search", "freehire-search"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "SKILL.md").write_text(f"---\nname: {name}\nenabled: true\n---\n")
    d = tmp_path / "cityboard-search"
    (d / "cli" / "dist").mkdir(parents=True)
    (d / "cli" / "dist" / "cli.mjs").write_text("// stand-in build\n")
    (d / "SKILL.md").write_text("---\nname: cityboard-search\nenabled: true\ncontract: 1\n"
                                "crawl-delay: 5\npages: 3\nremote: true\n---\n")
    monkeypatch.setattr(portals, "SKILLS", str(tmp_path))
    monkeypatch.setattr(scrape_wide, "LOCATIONS", [HOME, NEXT, FAR])
    monkeypatch.setattr(scrape_wide, "PORTAL_LOCATIONS", {})
    monkeypatch.setattr(scrape_wide, "QUERIES", ["planner", "buyer", "analyst"])
    monkeypatch.setattr(scrape_wide, "EMPLOYERS", ["Oakmere Foods"])
    monkeypatch.setattr(scrape_wide, "EMPLOYER_QUERIES", ["planner"])
    monkeypatch.setattr(scrape_wide, "_covered_by_ats", lambda: set())
    monkeypatch.setattr(scrape_wide, "_cursor", lambda: {})
    portals.cli.cache_clear()
    yield "cityboard-search"
    portals.cli.cache_clear()


def _city():
    return [t for t in scrape_wide.build_tasks(portals.enabled({}), 5)
            if t[0] == "cityboard-search"]


def test_page_one_of_every_search_at_home_goes_before_any_deeper_page(board):
    city = _city()
    assert [t[1:4] for t in city[:3]] == [("planner", HOME, 1), ("buyer", HOME, 1),
                                          ("analyst", HOME, 1)]
    home = [t[3] for t in city if t[2] == HOME and len(t) == 4 and "Oakmere" not in t[1]]
    assert home == sorted(home) and max(home) == 3      # page-major, as deep as it says


def test_the_places_further_out_come_last_and_page_one_before_page_two(board):
    city = _city()
    where = [(i, t) for i, t in enumerate(city) if t[2] in (NEXT, FAR)]
    assert all(t[3] == 1 for _, t in where[:6]) and all(t[3] == 2 for _, t in where[6:])
    first_page = [t[2] for _, t in where[:6]]
    assert first_page == [NEXT] * 3 + [FAR] * 3          # nearer first, as the person lists them
    # The named employers and page one of the remote search go before any other place.
    first_wide = where[0][0]
    assert all(i < first_wide for i, t in enumerate(city)
               if "Oakmere" in t[1] or (len(t) > 4 and t[3] == 1))
    assert city[-1][2] == FAR                            # the long tail is last


def test_every_request_is_still_planned(board):
    """Reordering only: the same requests as before, none added, none dropped."""
    city = _city()
    assert len(city) == len(set(city)) == 9 + 1 + 6 + 12   # core, employer, remote, two towns


def _clocked(per):
    now = [0.0]

    def sleep(s):
        now[0] += per                    # a wait and the request after it, together
    return now, sleep


def test_a_sweep_says_up_front_how_much_fits_its_budget(board, monkeypatch, capsys):
    monkeypatch.setattr(scrape_wide, "_cursor", lambda: {"cityboard-search": {"secs": 8.5}})
    monkeypatch.setattr(scrape_wide, "contract", lambda *a, **k: ([{"url": "u"}], None))
    now, sleep = _clocked(8.5)
    tasks = [("cityboard-search", f"q{n}", HOME, 1) for n in range(243)]
    scrape_wide.sweep("cityboard-search", tasks, 14, sleep=sleep, clock=lambda: now[0])
    err = capsys.readouterr().err
    fits = int(scrape_wide.SWEEP_BUDGET // 8.5)
    assert "243 requests" in err and f"about {fits} fit" in err, err


def test_a_sweep_that_stops_names_what_it_did_not_send(board, monkeypatch, capsys):
    monkeypatch.setattr(scrape_wide, "contract", lambda *a, **k: ([{"url": "u"}], None))
    now, sleep = _clocked(500)
    tasks = [("cityboard-search", f"q{n}", NEXT, 2) for n in range(30)]
    rows, n, failed = scrape_wide.sweep("cityboard-search", tasks, 14, sleep=sleep,
                                        clock=lambda: now[0])
    err = capsys.readouterr().err
    assert n < 30 and f"{30 - n} of 30" in err
    assert f'"q{n}" ({NEXT}, page 2)' in err and f'"q{n + 1}"' in err   # the first unsent
    assert f"and {30 - n - 3} more" in err


def test_a_sweep_stopped_by_failures_names_what_it_did_not_send_and_why(board, monkeypatch,
                                                                         capsys):
    monkeypatch.setattr(scrape_wide, "contract", lambda *a, **k: ([], "timeout after 90s"))
    tasks = [("cityboard-search", f"q{n}", None, 1, True) for n in range(10)]
    t = scrape_wide.Tally("cityboard", len(tasks))
    scrape_wide.sweep("cityboard-search", tasks, 14, sleep=lambda s: None, tally=t)
    err = capsys.readouterr().err
    assert "7 of 10" in err and '"q3" (remote, page 1)' in err and "timeout" in err
    assert "timeout" in t.stopped and t.finished


def test_the_measured_pace_is_kept_for_the_next_round(monkeypatch, tmp_path):
    monkeypatch.setenv("LJS_STATE", str(tmp_path))
    monkeypatch.setattr(scrape_wide, "PLAN", {"cityboard-search": ("tail", 9, 19, 0)})
    scrape_wide.save_cursor({"cityboard-search": 12}, "2026-10-19", {"cityboard-search": 8.46})
    assert scrape_wide._cursor()["cityboard-search"]["secs"] == 8.5
    assert scrape_wide.request_seconds("cityboard-search") == 8.5
    # Nothing measured yet: the probe's time, then a guess, on top of the crawl-delay.
    monkeypatch.setattr(scrape_wide, "PROBE_SECONDS", {"freshboard": 2.0})
    assert scrape_wide.request_seconds("freshboard-search") == portals.DEFAULT_DELAY + 2.0
    assert scrape_wide.request_seconds("otherboard-search") == \
        portals.DEFAULT_DELAY + scrape_wide.DEFAULT_REQUEST_SECONDS
