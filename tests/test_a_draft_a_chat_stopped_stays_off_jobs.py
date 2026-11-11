"""A draft a chat stopped because the job is not one the person can take stays off Jobs.

`app.py done --left-out` is that chat's judgement on one posting. It was written as a ruling
by the search's rules, and the page now asks every such ruling, on every build, whether
today's rules still uphold it: a stop because the job needs a PhD, is where they cannot work
or pays below their floor was upheld by none, and was back on Jobs at the next build, the
"10 jobs to look at" of 2026-10-30 again (the engine review, 2026-11-11). It now holds as a
role the person set aside does: dated, ending, for that posting alone, shown under Held back
for now and lifted there. Every person, employer and posting here is invented.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

from test_a_tick_on_the_page_is_applied_once import NOW, Search  # noqa: E402

REASONS = ("the posting requires a PhD in statistics",
           "based in Chicago with no remote option, not where they can work",
           "pay tops out at 25,000, below their floor",
           "never a role they could take: it needs a US security clearance")


def _row(i):
    return {"priority": 90 - i, "fit": 85 - i, "title": f"Pricing Analyst {i}",
            "company": f"Fernway {i} Insurance", "location": "Manchester", "portal": "linkedin",
            "url": f"https://boards.example.com/fernway/jobs/{i}", "first_seen": "2026-10-25",
            "date": "2026-10-24"}


@pytest.fixture(scope="module")
def stopped(tmp_path_factory):
    s = Search(str(tmp_path_factory.mktemp("left")))
    rows = [_row(i) for i in range(len(REASONS))]
    with open(os.path.join(s.state, "documents", "rounds", "r9.json"), "w", encoding="utf-8") as fh:
        json.dump(rows, fh)
    before = s.model()
    for i, why in enumerate(REASONS):
        s.put("work", f"draft~{i}", {
            "kind": "draft", "status": "running", "claimed_by": "cloud-1",
            "claimed_at": "2026-10-25T17:00:00Z", "lease_until": "2026-10-25T18:30:00Z",
            "asked_at": "2026-10-25T16:00:00Z",
            "args": {k: rows[i][k] for k in ("url", "title", "company")}}, version=3)
        s.run("done", s.dump, "--work", f"draft~{i}", "--chat", "cloud-1", "--left-out", why,
              "--now", NOW)
    return s, before, s.model()


def _rows(model):
    return {r["company"]: r for r in model["jobs"]["rows"] if r["company"].startswith("Fernway")}


def test_every_stop_leaves_jobs_whatever_todays_rules_say(stopped):
    _, before, after = stopped
    assert {r["status"] for r in _rows(before).values()} == {"new"}
    rows = _rows(after)
    assert len(rows) == len(REASONS)
    for i, why in enumerate(REASONS):
        r = rows[f"Fernway {i} Insurance"]
        assert r["status"] == "dismissed", (why, r["status"])
        assert r["notes"][-1].startswith("Left out: ") and why[5:30] in r["notes"][-1]
    assert after["jobs"]["summary"].startswith("0 roles"), after["jobs"]["summary"]


def test_each_is_dated_ending_and_shown_under_held_back_for_now(stopped):
    _, _, after = stopped
    held = [h for h in after["rules"]["held"] if h["rule"] == "job_left_out"]
    assert len(held) == len(REASONS)
    # 182 days from the day the chat stopped it, even where its words say "never": the
    # words are the chat's, not the person's.
    assert {h["until"] for h in held} == {"2027-04-25"}, held
    assert all(h["lift"] == "Look again now" and "not drafted" in h["line"] for h in held)
    # Never among the roles the person set aside themselves.
    mine = [r for r in after["rules"]["rows"] if r.get("kind") == "set_aside"]
    assert not [r for r in mine if "Fernway" in r.get("sentence", "")], mine


def test_it_holds_that_posting_alone_and_a_tap_brings_it_back(stopped):
    import throttle
    s, _, after = stopped
    with open(os.path.join(s.state, "job_scraper", "seen_jobs.json"), encoding="utf-8") as fh:
        seen = json.load(fh)["seen"]
    urls, pairs = throttle.ruled_out(seen, "2026-10-25")
    assert all(any(_row(i)["url"].split("//")[1] in u for u in urls) for i in range(len(REASONS)))
    assert not [p for p in pairs if "fernway" in p[1]], pairs
    hold = next(h for h in after["rules"]["held"] if "Fernway 1 Insurance" in h["what"])
    env = dict(os.environ, LJS_PROFILE=s.profile, LJS_STATE=s.state, LJS_COPY="private")
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "holds.py"), "lift",
                        hold["id"], "--today", "2026-10-25"], env=env, capture_output=True,
                       text=True, encoding="utf-8")
    assert r.returncode == 0 and "back on Jobs" in r.stdout, r.stdout + r.stderr
    rows = _rows(s.model())
    assert rows["Fernway 1 Insurance"]["status"] == "new"
    assert rows["Fernway 0 Insurance"]["status"] == "dismissed"
