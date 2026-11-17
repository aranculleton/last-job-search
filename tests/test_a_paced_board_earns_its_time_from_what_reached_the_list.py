"""A person's slow job board gets the time its jobs on the list have earned it.

Since issue 301 every paced board (a person's own job site, sent one request every few
seconds as it asks) stopped a minute after LinkedIn and freehire finished, whatever it had
done for the person before. One evening's four boards put 1, 19, 2 and 79 postings on the
list between them, 15 of them strong, all from the last: the board that paid and the boards
that never did were given the same minute (issue 327).

Now each round keeps, beside the board's place in its searches (the sweep cursor), how many
of its jobs reached the list scoring 60 or more, over its last few rounds. A board that pays
goes on longer after LinkedIn and freehire, up to its whole budget; one whose jobs have not
reached the list in several rounds is tried for its first minute only, so one that starts
paying is still noticed; a new board keeps the minute it had. A time the person set for a
board stands. The round's summary says each board's time and why. Fake boards only.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import ats_boards  # noqa: E402
import portals  # noqa: E402
import run_round  # noqa: E402
import scrape_wide  # noqa: E402

BOARDS = ("cityboard", "townboard", "newboard", "ownboard")
# What a person is never asked to understand (tests/test_a_beginner_is_told_in_plain_words.py).
JARGON = re.compile(r"\b(?:proxy|repo\w*|branch|CLI|config\w*|cursor|budget|yield|sweep|"
                    r"PORTAL_\w+|search\.py)\b", re.I)


def _portal(root, name, extra=""):
    d = root / name
    (d / "cli" / "dist").mkdir(parents=True)
    (d / "cli" / "dist" / "cli.mjs").write_text("// stand-in build\n")
    (d / "SKILL.md").write_text(f"---\nname: {name}\nenabled: true\n{extra}---\n\n# {name}\n")


@pytest.fixture
def boards(tmp_path, monkeypatch):
    root = tmp_path / "skills"
    for name in ("linkedin-search", "freehire-search"):
        _portal(root, name)
    for name in BOARDS:
        _portal(root, f"{name}-search", "contract: 1\ncrawl-delay: 0\npages: 1\n")
    monkeypatch.setattr(portals, "SKILLS", str(root))
    monkeypatch.setattr(ats_boards, "fetch_all", lambda **k: ([], {}))
    monkeypatch.setattr(scrape_wide, "QUERIES", ["analyst"])
    monkeypatch.setattr(scrape_wide, "LOCATIONS", [scrape_wide.DEEP + " area"])
    monkeypatch.setattr(scrape_wide, "PORTAL_LOCATIONS", {})
    monkeypatch.setattr(scrape_wide, "PORTAL_MINUTES", {})
    monkeypatch.setattr(scrape_wide, "REMOTE_LOCATIONS", [])
    monkeypatch.setattr(scrape_wide, "EMPLOYERS", [])
    monkeypatch.setattr(scrape_wide, "EMPLOYER_QUERIES", ["planner"])
    monkeypatch.setattr(scrape_wide, "_covered_by_ats", lambda: set())
    monkeypatch.setattr(scrape_wide, "SWEEP_STATE", str(tmp_path / "cursor.json"))
    monkeypatch.setattr(scrape_wide, "PROBE_SECONDS", {})
    portals.cli.cache_clear()
    yield tmp_path
    portals.cli.cache_clear()


def _cursor(path, listed: dict) -> None:
    """A cursor as earlier rounds left it: each board's place, and what reached the list."""
    state = {f"{name}-search": {"mode": "tail", "next": 0, "sent": 1, "date": "2026-11-10",
                                "yield": [{"date": f"2026-11-0{n + 1}", "round": f"r{n + 1}",
                                           "listed": got} for n, got in enumerate(counts)]}
             for name, counts in listed.items()}
    Path(path).write_text(json.dumps(state), encoding="utf-8")


def _answers(calls, slow=0.0, stamps=None):
    """Every search answered with one posting; each of the person's boards' requests taking
    `slow` seconds, LinkedIn's and freehire's none. `stamps`, when given, keeps when each
    board's requests were sent, by board."""
    def fake_run(cmd, timeout=90):
        skill = Path(cmd[2]).parts[-4]
        q = cmd[cmd.index("-q") + 1] if "-q" in cmd else ""
        page = cmd[cmd.index("--page") + 1] if "--page" in cmd else "1"
        calls.append((skill, q, page))
        if stamps is not None:
            stamps.setdefault(skill, []).append(time.monotonic())
        if skill not in ("linkedin-search", "freehire-search") and slow:
            time.sleep(slow)
        n = f"{skill}-{q}-{page}"
        return {"results": [{"id": n, "title": "Supply Chain Analyst", "company": "Oakmere Foods",
                             "url": f"https://jobs.example/{n}",
                             "location": "Manchester, England, United Kingdom",
                             "date": "2026-11-16"}]}, None
    return fake_run


def _scrape(out, monkeypatch, today="2026-11-17"):
    monkeypatch.setattr(sys, "argv", ["scrape_wide.py", "--out", str(out), "--pages", "1",
                                      "--workers", "2", "--today", today, "--skip-canary"])
    return scrape_wide.main()


def _sent(calls, board):
    return [q for s, q, _ in calls if s == f"{board}-search"]


# What stops a board is time, so what it was given is read in time, from when its first and
# last requests were sent, never from how many fitted: a slow machine fits fewer in the same
# time (CI's macOS, 2026-11-17: 4, 13 and 18 requests where Linux sent 9, 39 and 68). A
# request is sent a moment after the check that let it go, so a board's last one may start a
# little past its time: LAG.
LAG = 0.15


def _span(stamps, board):
    got = stamps.get(f"{board}-search") or [0.0]
    return got[-1] - got[0]


# ------------------------------------------------------------------ what each board is given

def test_the_round_says_each_boards_time_and_why(boards, monkeypatch):
    _cursor(boards / "cursor.json", {"cityboard": [2, 3, 1], "townboard": [0, 0, 0],
                                     "ownboard": [0, 0, 0, 0]})
    monkeypatch.setattr(scrape_wide, "PORTAL_MINUTES", {"ownboard": 10})
    monkeypatch.setattr(scrape_wide, "run", _answers([]))
    _scrape(boards / "r1" / "00_scrape", monkeypatch)
    text = "\n".join(run_round.say_sources(str(boards / "r1")))
    # A board that pays: a minute, and a minute more for each of its jobs on the list in an
    # average search (2 over its last 3).
    assert ("  cityboard's time: 3 minutes after LinkedIn and freehire finish (3 minutes at "
            "least): a minute, and a minute more for each of its jobs scoring 60 or more that "
            "reached your list in an average search (2 over its last 3)") in text, text
    assert ("  townboard's time: its first minute only: none of its jobs reached your list in "
            "its last 3 searches, and it is still tried each search, so a board that starts "
            "finding them is noticed") in text, text
    assert ("  newboard's time: a minute after LinkedIn and freehire finish (3 minutes at "
            "least), as for any new board: no searches of it to judge by yet") in text, text
    # The person's own time stands, whatever the board has found.
    assert "  ownboard's time: 10 minutes, the time you set for it" in text, text
    for line in text.splitlines():
        if "'s time: " in line:
            assert not JARGON.search(line), (JARGON.search(line).group(0), line)
            assert "\u2014" not in line


def test_a_board_searched_on_its_own_keeps_its_whole_time_whatever_it_found(boards,
                                                                          monkeypatch):
    for name in ("linkedin-search", "freehire-search"):
        p = boards / "skills" / name / "SKILL.md"
        p.write_text(p.read_text().replace("enabled: true", "enabled: false"))
    portals.cli.cache_clear()
    _cursor(boards / "cursor.json", {"townboard": [0, 0, 0]})
    monkeypatch.setattr(scrape_wide, "run", _answers([]))
    _scrape(boards / "r1" / "00_scrape", monkeypatch)
    text = "\n".join(run_round.say_sources(str(boards / "r1")))
    assert ("  townboard's time: its whole 20 minutes: LinkedIn and freehire are not "
            "searched, so it is the search") in text, text


@pytest.mark.timing
def test_a_board_whose_jobs_never_reach_the_list_is_tried_for_its_first_minute_only(
        boards, monkeypatch, capsys):
    # The minute and the minute after LinkedIn and freehire, made short enough to watch.
    monkeypatch.setattr(scrape_wide, "PACED_FLOOR", 0.3)
    monkeypatch.setattr(scrape_wide, "PACED_AFTER_POOL", 2.0)
    monkeypatch.setattr(scrape_wide, "PACED_MIN", 0)
    monkeypatch.setattr(scrape_wide, "QUERIES", [f"role {n}" for n in range(200)])
    # townboard has put nothing on the list in three searches; ownboard neither, but the
    # person gave it a time of their own (a fiftieth of a minute, 1.2 seconds).
    _cursor(boards / "cursor.json", {"townboard": [4, 0, 0, 0], "ownboard": [0, 0, 0]})
    monkeypatch.setattr(scrape_wide, "PORTAL_MINUTES", {"ownboard-search": 0.02})
    calls, stamps = [], {}
    monkeypatch.setattr(scrape_wide, "run", _answers(calls, slow=0.03, stamps=stamps))
    _scrape(boards / "r1" / "00_scrape", monkeypatch)
    town = _sent(calls, "townboard")
    # Its first requests, the most valuable, still go: one that starts paying is noticed.
    assert town and town == [f"role {n}" for n in range(len(town))]
    # townboard its first 0.3 seconds, ownboard the 1.2 the person set, newboard 2 after
    # LinkedIn and freehire.
    span = {b: round(_span(stamps, b), 2) for b in ("townboard", "ownboard", "newboard")}
    assert span["townboard"] < 0.3 + LAG, span
    assert 0.6 < span["ownboard"] < 1.2 + LAG, span
    assert span["newboard"] > 1.2, span
    err = capsys.readouterr().err
    assert ("portals: townboard stopped, its first minute was up: none of its jobs reached "
            "your list in its last 3 searches") in err, err
    assert "portals: ownboard stopped, the 1 minute you set for it was up" in err, err
    # What it did not send is the next rounds', as for every board.
    cursor = json.load(open(boards / "cursor.json"))["townboard-search"]
    assert cursor["sent"] == len(town) and cursor["mode"] == "all"


@pytest.mark.timing
def test_a_board_whose_jobs_reach_the_list_goes_on_longer_after_linkedin_and_freehire(
        boards, monkeypatch, capsys):
    monkeypatch.setattr(scrape_wide, "PACED_AFTER_POOL", 0.3)
    monkeypatch.setattr(scrape_wide, "PACED_PER_LISTED", 1.0)
    monkeypatch.setattr(scrape_wide, "PACED_MIN", 0)
    monkeypatch.setattr(scrape_wide, "QUERIES", [f"role {n}" for n in range(200)])
    # cityboard put three jobs on the list in each of its last three searches: 0.3 seconds
    # after LinkedIn and freehire, and 3 more. newboard has no searches to judge it by.
    _cursor(boards / "cursor.json", {"cityboard": [3, 3, 3]})
    calls, stamps = [], {}
    monkeypatch.setattr(scrape_wide, "run", _answers(calls, slow=0.03, stamps=stamps))
    _scrape(boards / "r1" / "00_scrape", monkeypatch)
    assert _sent(calls, "newboard") and _sent(calls, "cityboard")
    # How long each went on after LinkedIn's and freehire's last request: newboard 0.3
    # seconds, cityboard 3.3.
    pool = max(stamps["linkedin-search"][-1], stamps["freehire-search"][-1])
    after = {b: round(stamps[f"{b}-search"][-1] - pool, 2) for b in ("cityboard", "newboard")}
    assert after["newboard"] < 0.3 + LAG + 0.3, after
    assert after["cityboard"] > 0.3 + 1.5, after
    err = capsys.readouterr().err
    assert ("portals: cityboard stopped, LinkedIn and freehire had finished, and the time its "
            "jobs on your list earn it was up") in err, err
    assert "portals: newboard stopped, LinkedIn and freehire had finished" in err, err


# ------------------------------------------------------------------ what each board earned

def _round(tmp_path, shortlist, sites) -> str:
    out = tmp_path / "r7"
    (out / "00_scrape").mkdir(parents=True)
    (out / "00_scrape" / "sources.json").write_text(json.dumps(
        {"sites": [{"source": s, "requests": 3, "failed": 0, "found": 3, "kept": 3}
                   for s in sites], "boards": {}, "stopped": ""}), encoding="utf-8")
    (out / "06_shortlist.json").write_text(json.dumps(shortlist), encoding="utf-8")
    return str(out)


def _row(n, portal, fit, company="Oakmere Foods"):
    return {"url": f"https://jobs.example/{portal}/{n}", "title": "Supply Chain Analyst",
            "company": company, "portal": portal, "fit": fit, "priority": fit}


def test_each_round_keeps_how_many_of_a_boards_jobs_reached_the_list(boards):
    _cursor(boards / "cursor.json", {"cityboard": [1, 0, 2, 0, 5], "townboard": []})
    out = _round(boards, [_row(1, "cityboard", 72), _row(2, "cityboard", 64),
                          _row(3, "cityboard", 41),                     # below 60: not counted
                          _row(4, "cityboard", 80, "Fernhill Freight"),  # a rule leaves it out
                          _row(5, "linkedin", 90)],
                 ["linkedin", "cityboard", "townboard"])
    rules = lambda r: "an employer you turned down" if r["company"] == "Fernhill Freight" else ""
    run_round.record_board_yield(out, "2026-11-17", "r7", rules)
    cursor = json.load(open(boards / "cursor.json"))
    # The last five searches are kept, the newest last.
    assert [y["listed"] for y in cursor["cityboard-search"]["yield"]] == [0, 2, 0, 5, 2]
    assert cursor["cityboard-search"]["yield"][-1] == {"date": "2026-11-17", "round": "r7",
                                                       "listed": 2}
    assert [y["listed"] for y in cursor["townboard-search"]["yield"]] == [0]
    # The same search recorded again replaces its own record rather than adding a second.
    run_round.record_board_yield(out, "2026-11-17", "r7", rules)
    cursor = json.load(open(boards / "cursor.json"))
    assert [y["round"] for y in cursor["cityboard-search"]["yield"]][-2:] == ["r5", "r7"]
    # LinkedIn has no place in the cursor: it is never paced.
    assert "linkedin-search" not in cursor and "linkedin" not in cursor


def test_what_a_board_earned_survives_the_next_rounds_place_in_its_searches(boards,
                                                                            monkeypatch):
    _cursor(boards / "cursor.json", {"cityboard": [2, 3, 1]})
    monkeypatch.setattr(scrape_wide, "run", _answers([]))
    _scrape(boards / "r1" / "00_scrape", monkeypatch)
    cursor = json.load(open(boards / "cursor.json"))["cityboard-search"]
    assert cursor["date"] == "2026-11-17"
    assert [y["listed"] for y in cursor["yield"]] == [2, 3, 1]
