"""Jobs holds one open role per employer, whichever search found it.

One search kept one role per employer (throttle.py), but nothing held the limit across the
list: three roles at one employer from three searches all reached Jobs, all scoring 98 to
100, and the top of the list stopped telling the best jobs apart (the maintainer,
2026-11-05). Now the page's own read of the list (app_model._jobs, run_round.extra_roles)
keeps the role that fits best at each employer among those nobody has decided on, and sets
each other aside with a plain reason, where Bring back returns it. A role the person added,
kept, drafted or applied for always stays.

Every employer and role here is invented.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import app_model  # noqa: E402
import run_round  # noqa: E402

TODAY = "2026-11-05"
NOW = dt.datetime(2026, 11, 5, 21, tzinfo=dt.timezone.utc)
LEEDS = "Leeds, England, United Kingdom"
FIRM = "Brackenridge Mutual"
REASON = f"Left out: Another role at {FIRM} is already on your list."


def _row(n, company, title, fit, seen):
    return {"title": title, "company": company, "date": seen, "first_seen": seen,
            "portal": "linkedin", "location": LEEDS, "fit": fit, "priority": fit,
            "url": f"https://www.linkedin.com/jobs/view/{7700 + n}/"}


# Three searches, three roles at one employer, each scoring 98 to 100; one other employer.
R6 = [_row(1, FIRM, "Risk Analyst", 98, "2026-10-30"),
      _row(2, "Brookvale Grocers", "Data Analyst", 81, "2026-10-30")]
R7 = [_row(3, f"{FIRM} Ltd", "Data Scientist", 99, "2026-11-02")]
R8 = [_row(4, FIRM, "Pricing Analyst", 100, TODAY),
      _row(5, "Fernhill Freight", "Planning Analyst", 77, TODAY)]


@pytest.fixture
def state(tmp_path, monkeypatch):
    st = tmp_path / "state"
    shutil.copytree(os.path.join(ROOT, "profile.example", "state"), st)
    monkeypatch.setenv("LJS_STATE", str(st))
    rounds = st / "documents" / "rounds"
    rounds.mkdir(parents=True)
    for name, rows in (("r6", R6), ("r7", R7), ("r8", R8)):
        (rounds / f"{name}.json").write_text(json.dumps(rows), encoding="utf-8")
    app_model._ROUND_DAY.clear()
    return st


def _jobs():
    return app_model._jobs(app_model.Ctx(dt.date.fromisoformat(TODAY), NOW), {})


def _by_title(jobs):
    return {r["title"]: r for r in jobs["rows"]}


def test_the_best_fitting_role_stays_and_the_others_are_set_aside(state):
    rows = _by_title(_jobs())
    assert rows["Pricing Analyst"]["status"] == "new"
    for title in ("Risk Analyst", "Data Scientist"):
        assert rows[title]["status"] == "dismissed", title
        assert rows[title]["notes"][-1] == REASON
        assert rows[title]["questions"] == []
    # Other employers are untouched.
    assert rows["Data Analyst"]["status"] == "new"
    assert rows["Planning Analyst"]["status"] == "new"


def test_bring_back_keeps_a_role_set_aside_for_another(state):
    import app_actions

    class _W:
        def add(self, *a, **k):
            pass

    t = {"kind": "job", "url": R6[0]["url"], "company": FIRM, "title": "Risk Analyst",
         "round": "r6", "rank": 1}
    run = app_actions.Run("a1", {"action": "job.bring_back", "at": "2026-11-05T21:00:00Z",
                                 "value": {}}, t, {"work": {}}, _W(), "cloud-1", "UTC", NOW)
    assert "is back" in app_actions._job_bring_back(run)["note"]
    rows = _by_title(_jobs())
    assert rows["Risk Analyst"]["status"] == "new"
    assert rows["Pricing Analyst"]["status"] == "new"
    assert rows["Data Scientist"]["status"] == "dismissed"


def test_a_role_the_person_added_or_kept_always_stays(state):
    added = state / "documents" / "rounds" / "added"
    added.mkdir()
    (added / "jobs.json").write_text(json.dumps([dict(
        _row(9, FIRM, "Credit Risk Analyst", 70, TODAY), added_on=TODAY)]), encoding="utf-8")
    kept = state / "documents" / "rounds" / "kept"
    kept.mkdir()
    (kept / "jobs.json").write_text(json.dumps({R7[0]["url"]: {
        "round": "r7", "rank": 1, "title": "Data Scientist", "company": FIRM,
        "kept_on": TODAY}}), encoding="utf-8")
    rows = _by_title(_jobs())
    assert rows["Credit Risk Analyst"]["status"] == "new"   # added, at fit 70
    assert rows["Data Scientist"]["status"] == "new"        # kept
    # Of the two nobody has decided on, the better fit stays.
    assert rows["Pricing Analyst"]["status"] == "new"
    assert rows["Risk Analyst"]["status"] == "dismissed"


def test_a_role_set_aside_comes_back_once_the_one_kept_is_decided(state):
    import exclude
    exclude.add(R8[0]["url"], "not for me (said on the page)", title="Pricing Analyst",
                company=FIRM, basis="person", today=TODAY,
                path=str(state / "job_scraper" / "seen_jobs.json"))
    rows = _by_title(_jobs())
    assert rows["Pricing Analyst"]["status"] == "dismissed"
    assert rows["Data Scientist"]["status"] == "new"
    assert rows["Risk Analyst"]["status"] == "dismissed"


def test_extra_roles_keeps_the_best_fit_then_priority_then_list_order():
    rows = [{"company": "Larkmoor Bank", "fit": 90, "priority": 80},
            {"company": "Larkmoor Bank plc", "fit": 95, "priority": 60},
            {"company": "Wexmoor Lending", "fit": 70, "priority": 70},
            {"company": "Wexmoor Lending", "fit": 70, "priority": 75},
            {"company": "Pellow Insurance", "fit": 88, "priority": 88},
            {"company": "Pellow Insurance", "fit": 88, "priority": 88},
            {"company": "", "fit": 50}, {"company": "", "fit": 40}]
    got = run_round.extra_roles(rows)
    assert got == {0: "another role at Larkmoor Bank plc is already on your list",
                   2: "another role at Wexmoor Lending is already on your list",
                   5: "another role at Pellow Insurance is already on your list"}
    # Never a ruling, nor another search's left-out list: the page decides it on every read.
    assert not run_round.ruled_by(rows[0], got[0])
