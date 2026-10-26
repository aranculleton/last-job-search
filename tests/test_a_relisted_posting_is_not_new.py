"""A relisted posting is as old as the first time the search saw it.

The only date anything aged on was the portal's, and a portal relisting a posting
gives it a new one: LinkedIn's card shows the relist date. So a posting first seen
a month ago read as posted yesterday, passed the freshness rule and earned the
freshness bonus. Nothing could know better, because a round wrote only its skips
to seen_jobs.json and never the postings it surfaced.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import opportunity  # noqa: E402
import prefilter  # noqa: E402
import run_round  # noqa: E402
import throttle  # noqa: E402

TODAY = dt.date(2026, 10, 14)
ISO = TODAY.isoformat()
LOC = "Manchester, England, United Kingdom"


def _ago(days: int) -> str:
    return (TODAY - dt.timedelta(days=days)).isoformat()


def posting(url, title="Supply Chain Analyst", company="Kestrel Mutual", date=None, **kw):
    return {"url": url, "title": title, "company": company, "location": LOC,
            "date": date if date is not None else _ago(1), "portal": "linkedin", **kw}


def test_a_posting_is_aged_from_its_first_sighting_as_well_as_its_date():
    job = posting("https://www.linkedin.com/jobs/view/4100000001", first_seen=_ago(20))
    assert prefilter.age_days(job, TODAY) == 20
    ok, why = prefilter.decide(job, TODAY)
    assert not ok and "first seen 20 days ago" in why, why
    assert prefilter.age_days(posting("u", date=""), TODAY) is None


def test_freshness_is_earned_only_on_a_known_date_that_is_really_fresh():
    def bonus(job):
        return [w for w in opportunity.score({**job, "desc": "x" * 500}, TODAY)["why"]
                if "posted" in w]
    assert bonus(posting("u")) == ["+6 posted in the last 2 days"]
    assert bonus(posting("u", first_seen=_ago(20))) == []           # a relist
    assert bonus(posting("u", date=(TODAY + dt.timedelta(days=3)).isoformat())) == []
    assert bonus(posting("u", date="")) == []


def test_a_round_records_what_it_surfaced_and_a_relist_keeps_its_first_sighting(tmp_path):
    path = tmp_path / "seen.json"
    first = posting("https://www.linkedin.com/jobs/view/4100000001")
    data = {"seen": {}}
    throttle.write_back(str(path), data, [], _ago(20), [dict(first)])
    e = json.loads(path.read_text())["seen"][first["url"]]
    assert (e["status"], e["first_seen"], e["last_seen"]) == ("surfaced", _ago(20), _ago(20))
    assert e["status"] != "new"                     # /rank reads "new" as a hand-added backlog

    # Seen again under its own URL: first_seen stays, last_seen moves.
    data = json.loads(path.read_text())
    throttle.write_back(str(path), data, [], _ago(10), [dict(first)])
    e = json.loads(path.read_text())["seen"][first["url"]]
    assert (e["first_seen"], e["last_seen"]) == (_ago(20), _ago(10))

    # Relisted under a new URL: the same posting, as old as it was.
    relist = posting("https://www.linkedin.com/jobs/view/4100000999")
    data = json.loads(path.read_text())
    assert throttle.first_seen(data["seen"], ISO)(relist) == _ago(20)
    kept = [dict(relist)]
    throttle.write_back(str(path), data, [], ISO, kept)
    e = json.loads(path.read_text())["seen"][relist["url"]]
    assert (e["first_seen"], e["relisted_from"]) == (_ago(20), first["url"])
    assert kept[0]["first_seen"] == _ago(20)


def test_the_same_title_long_after_is_a_new_opening_and_another_city_is_another_posting():
    seen = {"https://example.com/old": {
        "url": "https://example.com/old", "title": "Supply Chain Analyst",
        "company": "Kestrel Mutual", "location": LOC, "status": "surfaced",
        "first_seen": _ago(90), "last_seen": _ago(60)}}
    of = throttle.first_seen(seen, ISO)
    assert of(posting("https://example.com/new")) == ""
    seen["https://example.com/old"]["last_seen"] = _ago(5)
    of = throttle.first_seen(seen, ISO)
    assert of(posting("https://example.com/new")) == _ago(90)
    assert of({**posting("https://example.com/new"), "location": "Leeds, England"}) == ""


def test_prefilter_drops_a_relist_by_its_first_sighting(tmp_path):
    seen = tmp_path / "seen.json"
    seen.write_text(json.dumps({"seen": {"https://www.linkedin.com/jobs/view/4100000001": {
        "url": "https://www.linkedin.com/jobs/view/4100000001", "title": "Supply Chain Analyst",
        "company": "Kestrel Mutual", "location": LOC, "status": "surfaced",
        "first_seen": _ago(25), "last_seen": _ago(3)}}}))
    src, out, dropped = tmp_path / "in.json", tmp_path / "out.json", tmp_path / "drop.json"
    src.write_text(json.dumps([
        posting("https://www.linkedin.com/jobs/view/4100000777"),
        posting("https://www.linkedin.com/jobs/view/4100000778", title="Inventory Analyst")]))
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "prefilter.py"), str(src),
                        "--out", str(out), "--dropped", str(dropped), "--today", ISO,
                        "--seen", str(seen)], capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode == 0, r.stderr
    assert [j["title"] for j in json.loads(out.read_text())] == ["Inventory Analyst"]
    gone = json.loads(dropped.read_text())
    assert gone[0]["first_seen"] == _ago(25) and "first seen 25 days ago" in gone[0]["prefilter_reason"]


def test_the_round_summary_carries_the_age():
    assert "first_seen" in run_round.SUMMARY_FIELDS and "age_days" in run_round.SUMMARY_FIELDS


def test_a_relist_under_a_tag_or_a_shortened_title_is_the_same_posting():
    # The relist and ruled-out keys read the exact lower-cased title, while the check
    # for a role already applied to folded posting tags and "Sr.". A relist retitled
    # "(Hybrid)" or "Sr." read as new: it earned the freshness bonus, passed the age
    # gate, and a ruling on the posting it relists did not hold. One key now.
    seen = {"https://boards.example.com/1": {
        "url": "https://boards.example.com/1", "title": "Senior Data Analyst",
        "company": "Kestrel Mutual", "location": LOC, "first_seen": _ago(25),
        "status": "surfaced"}}
    of = throttle.first_seen(seen, ISO)
    for title in ("Senior Data Analyst (Hybrid)", "Sr. Data Analyst", "Senior Data Analyst"):
        assert of(posting("https://boards.example.com/2", title=title)) == _ago(25), title
    assert of(posting("https://boards.example.com/2", title="Senior Data Analyst, Fraud")) == ""


def test_a_ruling_holds_for_the_same_role_under_a_tag_or_a_shortened_title():
    seen = {"https://boards.example.com/1": {
        "url": "https://boards.example.com/1", "title": "Senior Data Analyst",
        "company": "Kestrel Mutual", "location": LOC, "status": "excluded",
        "basis": "person", "exclusion_reason": "not a company I want to work for",
        "excluded_date": ISO}}
    urls, pairs = throttle.ruled_out(seen)
    for title in ("Senior Data Analyst (Hybrid)", "Sr. Data Analyst", "SENIOR DATA ANALYST"):
        assert throttle.ruled_pair(pairs, posting("https://boards.example.com/2", title=title)), title
    # A different role at that employer stays in scope.
    assert not throttle.ruled_pair(pairs, posting("https://boards.example.com/3",
                                                 title="Senior Data Analyst, Fraud Strategy"))
    # A title in another script is still a key.
    assert throttle.title_key("データアナリスト") == "データアナリスト"
