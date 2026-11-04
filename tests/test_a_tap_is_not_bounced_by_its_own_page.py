"""A tap is refused as "changed since you saw it" only when what it acts on really changed.

The helper chat's report of 2 November: four Set asides and two Stops came back refused.
Each was moved either by an earlier tap of the person's own in the same batch (Not applying,
then Set aside, on one job), or by the page being drawn again (a later day moved a contact's
group; a search ranked afresh moved a posting's place and score) while nothing the tap acts
on had changed. The safeguard stays: a tap from another window over an answer it did not
see is still refused. Every person and employer here is invented (tests/app_state.py).
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

from test_a_tick_on_the_page_is_applied_once import KESTREL, Search  # noqa: E402

LATER = "2026-11-20T18:00:00Z"


@pytest.fixture
def search(tmp_path):
    return Search(str(tmp_path))


def _seen(s: Search) -> dict:
    with open(os.path.join(s.state, "job_scraper", "seen_jobs.json"), encoding="utf-8") as fh:
        return json.load(fh).get("seen") or {}


def _excluded(s: Search, url: str) -> bool:
    return any(isinstance(e, dict) and e.get("url") == url and e.get("status") == "excluded"
               for e in _seen(s).values())


def test_not_applying_then_set_aside_on_one_job_in_one_batch_both_apply(search):
    job = search.item("r9-2")                       # Kestrel's posting, drafted
    draft = search.item(KESTREL)
    no = search.act("ready.not_applying", KESTREL, rev=draft["rev"], value={"why": "not this role"})
    aside = search.act("job.dismiss", "r9-2", rev=job["rev"], value={"why": "not this role"})
    got = search.apply()
    assert got["ok"] == [no, aside], got
    assert _excluded(search, "https://jobs.example/kestrel/claims-forecasting")


def test_the_same_two_taps_from_two_windows_still_never_overwrite_each_other(search):
    old = search.item(KESTREL)["rev"]
    phone = search.act("ready.applied", KESTREL, rev=old, tab="phone")
    laptop = search.act("ready.not_applying", KESTREL, rev=old, tab="laptop")
    got = search.apply()
    assert got["ok"] == [phone] and got["stale"] == [laptop], got
    assert search.tracker_row("Kestrel Mutual")["status"] == "applied"


def test_a_stop_made_before_the_page_was_drawn_on_a_later_day_applies(search):
    """The day moved the contact from one group to another; nothing about them changed."""
    seen = search.item("fernhill_freight_halloway")
    later = json.loads(search.run("model", "--now", LATER))
    now = next(p for p in later["people"] if p["id"] == "fernhill_freight_halloway")
    assert now["group"] != seen["group"]            # the page drawn again looks different
    aid = search.act("person.stop", "fernhill_freight_halloway", rev=seen["rev"],
                     value={"why": "not right now"})
    got = json.loads(search.run("apply", search.dump, "--chat", "cloud-1", "--now", LATER))
    assert got["ok"] == [aid], search.receipt(aid)


def test_a_set_aside_on_a_search_ranked_afresh_reaches_the_posting_tapped(search):
    """The round saved again with a new posting first and the scores redone: the posting the
    person set aside moved from first to second, and that posting is the one set aside."""
    seen = search.item("r9-1")
    assert seen["company"] == "Brindle Hart Logistics"
    path = os.path.join(search.state, "documents", "rounds", "r9.json")
    with open(path, encoding="utf-8") as fh:
        rows = json.load(fh)
    for r in rows:
        r["fit"] = r["fit"] - 1
    rows.insert(0, {"priority": 95, "fit": 93, "title": "Network Planner",
                    "company": "Wexmoor Analytics", "location": "Manchester",
                    "url": "https://jobs.example/wexmoor/planner", "portal": "linkedin"})
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(rows, fh)
    aid = search.act("job.dismiss", "r9-1", rev=seen["rev"], value={"why": "too far"})
    got = search.apply()
    assert got["ok"] == [aid], search.receipt(aid)
    assert _excluded(search, "https://jobs.example/brindle/demand")
    assert not _excluded(search, "https://jobs.example/wexmoor/planner")


def test_a_posting_that_really_changed_is_still_refused(search):
    """Applied for in a chat since the person saw it: a Set aside made before is refused."""
    seen = search.item("r9-1")
    path = os.path.join(search.state, "job_search_tracker.csv")
    with open(path, encoding="utf-8") as fh:
        head = fh.readline()
    cols = head.strip().split(",")
    row = dict.fromkeys(cols, "") | {
        "date": "2026-10-24", "company": "Brindle Hart Logistics",
        "role": "Demand Planning Analyst", "status": "applied", "applied_on": "2026-10-24",
        "confirmed_by": "chat", "source": "https://jobs.example/brindle/demand"}
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(",".join(row[c] for c in cols) + "\n")
    aid = search.act("job.dismiss", "r9-1", rev=seen["rev"], value={"why": "too far"})
    got = search.apply()
    assert got["stale"] == [aid], got
    assert not _excluded(search, "https://jobs.example/brindle/demand")
