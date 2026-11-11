"""The brief's news finds each story once, from a round of searches that stays capped.

A run searched the same employer twice ("<employer> news" from those in play and a watched line
naming the same employer), kept the same story told by two publishers as two items, and its
searches ran to 26 against a cap of eight (second audit B6). Now a watched line that names an
employer already searched that morning is not searched again, a story told twice is kept once
(the first, both searches credited), and the reader is told the round's count and that no other
search is run. Invented employers and links.
"""
from __future__ import annotations

import datetime as dt
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import brief  # noqa: E402

DAY = dt.date(2026, 11, 20)


def test_an_employer_already_searched_is_not_searched_again_from_the_watch(monkeypatch):
    monkeypatch.setattr(brief, "home_place", lambda: "Toronto")
    watch = [{"what": "Larkspur Retail hiring in data", "every": "day"},
             {"what": "Ontario work permit changes", "every": "day"}]
    qs = brief.queries(DAY, ["Larkspur Retail"], watch, searched={})
    assert sum("Larkspur Retail" in q for q in qs) == 1, qs
    assert any("work permit" in q for q in qs)


def test_a_story_told_by_two_publishers_is_kept_once():
    a = ("[1] Larkspur Retail opens a Toronto data hub with 200 analytics jobs "
         "(Example Wire, 2026-11-19, https://example.com/a). A point for your call.")
    b = ("[3] Larkspur Retail opens Toronto data hub, 200 analytics jobs "
         "(Sample Times, 2026-11-19, https://example.org/b). A point for your call.")
    c = ("[2] Copperleaf Pay raises a new round "
         "(Example Wire, 2026-11-18, https://example.com/c). Worth a line to Sam.")
    kept = brief.one_story_once([a, b, c])
    assert kept == [(a, [1, 3]), (c, [2])]


def test_an_item_only_a_search_beyond_the_round_found_is_left_out(tmp_path, monkeypatch):
    import shutil
    state = tmp_path / "state"
    shutil.copytree(os.path.join(ROOT, "profile.example", "state"), state)
    monkeypatch.setenv("LJS_STATE", str(state))
    searches = [{"n": 1, "q": "Larkspur Retail Toronto news November 2026", "what": "",
                 "wider": False},
                {"n": 2, "q": "Larkspur Retail Toronto announces", "what": "", "wider": True}]
    brief.plan_searched([], DAY, searches)
    got = brief.take_news(
        "[1] Larkspur Retail opens a Toronto data hub (Example Wire, 2026-11-19, "
        "https://example.com/a). A point for your call.\n"
        "[7] Copperleaf Pay raises a new round (Example Wire, 2026-11-18, "
        "https://example.com/c). Worth a line to Sam.\n", DAY)
    assert len(got["kept"]) == 1 and "Larkspur" in got["kept"][0]
    reader = open(os.path.join(ROOT, ".claude", "agents", "news-reader.md"),
                  encoding="utf-8").read()
    assert "a search beyond them is never run" in " ".join(reader.split())


def test_the_reader_is_told_how_many_searches_to_run_and_no_more(monkeypatch):
    """Searches past the cap were still run and paid for; only their items were dropped
    (review of fix/helpers, item 17). The round's line gives the number to run, and the
    reader's file says a search beyond them is never run."""
    b = {"sync": {}, "page": "", "write_here": [], "profile_line": "", "since": "2026-11-13",
         "skip_links": [], "what_counts": "x", "pack": "", "date": DAY.isoformat(),
         "queries": ["Larkspur Retail Toronto news November 2026"],
         "wider": ["Larkspur Retail Toronto announces"], "watch": []}
    monkeypatch.setattr(brief, "_tidy_due", lambda: "")
    monkeypatch.setattr(brief, "_computer_lines", lambda b: [])
    monkeypatch.setattr(brief, "push_step", lambda b: "")
    line = next(ln for ln in brief.claude_lines(b) if ln.startswith("news, one round"))
    assert "only these 2 searches" in line
    reader = " ".join(open(os.path.join(ROOT, ".claude", "agents", "news-reader.md"),
                           encoding="utf-8").read().split())
    assert "a search beyond them is never run" in reader
