"""A search brings back as many of the strongest as the person chose, a few by default.

Each search kept its best 60, and with the searches of a week carried on the list it reached
215 jobs, 176 called strong (the maintainer, 2026-10-30: "surely ... we should have some
settings ... the default should be something realistic and modest"). The page asks how many
(10, 25, or every one that fits) and the search keeps only those.
"""
from __future__ import annotations

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import run_round  # noqa: E402


def _shortlist(tmp_path, n=70):
    rows = [{"url": f"https://jobs.example.com/{i}", "title": f"Analyst {i}", "company": "Example Co",
             "priority": 200 - i, "fit": 90} for i in range(n)]
    p = tmp_path / "06_shortlist.json"
    p.write_text(json.dumps(rows), encoding="utf-8")
    return str(p)


def test_the_search_keeps_only_as_many_as_were_asked_for_the_strongest_first(tmp_path):
    path = run_round.write_summary(_shortlist(tmp_path), str(tmp_path / "out"), "r1", show=10)
    rows = json.load(open(path, encoding="utf-8"))
    assert [r["title"] for r in rows] == [f"Analyst {i}" for i in range(10)]


def test_every_one_that_fits_is_the_old_sixty_and_none_is_unchanged(tmp_path):
    assert run_round.shown(0) == run_round.KEEP_TOP == run_round.shown(None) == 60
    assert run_round.shown(25) == 25 and run_round.shown(500) == 60


def test_the_page_asks_how_many_and_says_ten_first_and_the_chat_passes_it_on():
    js = open(os.path.join(ROOT, "templates", "app", "app.js"), encoding="utf-8").read()
    assert re.search(r'label: "How many to bring back", value: "10"', js)
    assert "The best 10 (recommended)" in js and "size: Number(v.size || 10)" in js
    skill = open(os.path.join(ROOT, ".claude", "skills", "app", "SKILL.md"), encoding="utf-8").read()
    assert "`run_round.py --show <args.size>` (10 when it is not given" in skill


def test_find_people_asks_how_many_too_and_the_run_keeps_to_it():
    js = open(os.path.join(ROOT, "templates", "app", "app.js"), encoding="utf-8").read()
    assert 'label: "How many people", value: "5"' in js and "args: Object.assign({count}" in js
    net = open(os.path.join(ROOT, ".claude", "commands", "network.md"), encoding="utf-8").read()
    assert "brings back `args.count` people at most (5 when not given)" in net


def test_the_job_sites_step_is_timed_as_it_runs_and_says_it_is_the_long_part():
    """31 minutes of job sites against a 15-minute estimate, and the person asked whether
    the search had stuck (2026-10-30)."""
    import page_db
    (key, name, secs) = page_db.STAGES["search"][1]
    assert key == "scrape" and secs >= 1800 and "the long part" in name


def test_a_long_document_scrolls_inside_its_own_body_on_a_phone():
    """A prep stopped drawing part way down on an iPhone, in a dialog that scrolled as one
    (2026-10-30): the header stays, and the body is the one thing that scrolls."""
    css = open(os.path.join(ROOT, "templates", "app", "app.css"), encoding="utf-8").read()
    assert "dialog.detail[open] { overflow: hidden; }" in css
    assert re.search(r"dialog\.detail \.detail-body \{ flex: 1 1 auto; min-height: 0; overflow-y: auto;", css)


def test_drafts_asked_for_together_are_one_job_not_one_chat_each():
    """Resumes for ten jobs from one search should not need ten chats or wait three at a time
    (the maintainer, 2026-10-30): queued drafts are one batch, each at its own employer."""
    import datetime as dt
    import page_db
    now = dt.datetime(2026, 10, 30, 12, 0, tzinfo=dt.timezone.utc)

    def draft(company, minute):
        return {"data": {"kind": "draft", "status": "queued", "to": "either",
                         "asked_at": f"2026-10-30T11:{minute:02d}:00Z", "args": {"company": company}},
                "version": 1}
    work = {f"d{i}": draft(c, i) for i, c in enumerate(
        ("Harbourline Bank", "Larkspur Retail", "Copperleaf Pay", "Larkspur Retail"))}
    got = page_db.next_item({"work": work, "locks": {}, "chats": {}}, "cloud", now)
    assert got["kind"] == "draft" and got["work"] == "d0"
    assert [w["work"] for w in got["with"]] == ["d1", "d2"], "one job; the second Larkspur draft waits its turn"
    assert len(got["locks"]) == 3
