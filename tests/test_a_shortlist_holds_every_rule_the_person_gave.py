"""A shortlist holds every rule the person gave, on every copy of a posting.

The 3 November audit replayed a real round and found the search letting through what the
person had ruled out: a 10-day window read as 14, a role already applied to six weeks
before back at rank 5, a provincial agency passed on a contract whose midpoint was 2%
over the target and then ranked up by its employer tier, the same agency back under a new
place name after the person cleared it, a closed posting holding one of the ten places,
every card saying pay was not stated beside a note quoting the range, a contact recorded as
"parked" or "not a hiring route" adding the referral bonus, and "Azure" asked of someone
holding Azure Data Factory read as "you have AWS". Each test replays one of those steps.
Every person and employer is invented.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import apply_link  # noqa: E402
import bar  # noqa: E402
import bridges  # noqa: E402
import fit  # noqa: E402
import opportunity  # noqa: E402
import run_round  # noqa: E402
import throttle  # noqa: E402
import tweak  # noqa: E402

TODAY = "2026-11-03"


# ------------------------------------------------------------------ the search window


@pytest.mark.parametrize("days", [3, 10, 21, 45])
def test_any_window_the_person_writes_is_the_one_searched(monkeypatch, days):
    """A chat wrote JOB_AGE_DAYS = 10 and the next search still used 14 (audit 1)."""
    import person
    search = type("search", (), {"JOB_AGE_DAYS": days})
    monkeypatch.setattr(person, "module", lambda name: search)
    assert run_round._job_age_days() == days


@pytest.mark.parametrize("bad", [0, -3, 400, "ten"])
def test_a_window_that_is_no_window_falls_back_to_14(monkeypatch, bad):
    import person
    search = type("search", (), {"JOB_AGE_DAYS": bad})
    monkeypatch.setattr(person, "module", lambda name: search)
    assert run_round._job_age_days() == 14


def test_the_setting_takes_a_window_asked_for_in_words():
    """"The last 10 days" is a setting the search keeps, not a choice refused."""
    row = tweak.BY_P["J6"]
    assert tweak._invalid(row, "10") == ""
    assert tweak._invalid(row, "14") == ""
    assert tweak._invalid(row, "0") and tweak._invalid(row, "ten")


# ------------------------------------------------------------------ applied already


def _applied(role, date, status="applied"):
    return {"date": date, "company": "Wexmoor Lending", "role": role, "status": status,
            "fit_rating": "80"}


def test_a_role_applied_to_that_went_quiet_is_not_surfaced_again():
    """Applied 16 Sept, no reply: past the 45 days it is neither open nor closed, and the
    same role came back at rank 5 with only a note (audit 3)."""
    tracker = [_applied("Senior Data Scientist, Growth", "2026-09-16")]
    today = dt.date(2026, 11, 3)
    silent = throttle.silent_applications(rows=tracker, today=today)
    assert silent, "the application is old enough to be quiet"
    rows = [{"title": "Senior Data Scientist, Growth", "company": "Wexmoor Lending",
             "url": "https://jobs.example/wexmoor/1", "fit": 95, "priority": 90},
            {"title": "Data Analyst, Payments", "company": "Wexmoor Lending",
             "url": "https://jobs.example/wexmoor/2", "fit": 80, "priority": 70}]
    kept, skipped = throttle.throttle(rows, throttle.open_applications(rows=tracker, today=today),
                                      {}, {}, TODAY, silent=silent,
                                      closed=throttle.closed_applications(rows=tracker))
    assert [r["title"] for r in kept] == ["Data Analyst, Payments"]
    why = skipped[0]["skip_reason"]
    assert why.startswith("already applied to this role on 2026-09-16 (applied, no reply in 45 "
                          "days)"), why
    # Another role at the employer still says the person applied there before, and the note
    # reaches the round file the page reads.
    assert "APPLIED HERE ALREADY" in kept[0]["silent_application_note"]
    assert "silent_application_note" in run_round.SUMMARY_FIELDS


# ------------------------------------------------------------------ public bodies


@pytest.fixture
def excludes_public(monkeypatch, judged):
    monkeypatch.setattr(bar, "PUBLIC", re.compile(r"\btransit authority\b", re.I))
    monkeypatch.setattr(bar, "_PUBLIC_WHY", "public sector unless well paid")
    monkeypatch.setattr(bar, "TARGET_MIDPOINT", 120_000)


CONTRACT = ("Data Scientist II, a 6-month term. You will build forecasting models in SQL and "
            "Python. Salary: £109,440 - £136,000 per year.")


def test_a_public_body_passes_only_when_the_bottom_of_its_range_reaches_the_target(
        excludes_public):
    """Its midpoint, 122,720, was 2% over a 120,000 target and the public rule's one
    exception let it through: the public rule is stricter than any other (audit 4)."""
    got, why = bar.verdict("Northmere Transit Authority", CONTRACT)
    assert got == bar.EXCLUDED, why
    # A private employer with the same range is well paid by its midpoint, as before.
    assert bar.verdict("Fernhill Freight", CONTRACT)[0] == bar.PAY
    paid = CONTRACT.replace("£109,440", "£121,000")
    got, why = bar.verdict("Northmere Transit Authority", paid)
    assert got == bar.PAY
    assert why.startswith("public body, but even the bottom of its stated range, ")


def test_a_public_body_gets_no_lift_from_an_employer_tier(excludes_public, monkeypatch):
    """A tier list naming a public body ranked it +10 beside the bodies named as hard nos."""
    monkeypatch.setattr(opportunity, "TIER_3", {"northmere transit authority", "fernhill freight"})
    job = {"title": "Data Scientist", "desc": "SQL and Python.", "location": "Leeds"}
    public = opportunity.score(dict(job, company="Northmere Transit Authority"))
    private = opportunity.score(dict(job, company="Fernhill Freight"))
    assert not any(w.startswith("+10 tier 3") for w in public["why"]), public["why"]
    assert any(w.startswith("+10 tier 3") for w in private["why"]), private["why"]


def test_a_posting_the_person_cleared_stays_cleared_under_every_copy():
    """Cleared as posted in "Canada", the same posting came back as posted in the "Greater
    Toronto Area": a ruling was kept under its city (audit 4)."""
    seen = {"https://board.example/metro/1": {
        "url": "https://board.example/metro/1", "title": "Data Scientist II",
        "company": "Northmere Transit", "location": "Canada", "status": "excluded",
        "exclusion_reason": "not this role", "basis": "person", "excluded_date": "2026-10-30",
        "first_seen": "2026-10-29"}}
    urls, pairs = throttle.ruled_out(seen, TODAY)
    copy = {"title": "Data Scientist II", "company": "Northmere Transit",
            "location": "Greater Toronto Area", "url": "https://www.linkedin.com/jobs/view/9"}
    assert throttle.ruled_pair(pairs, copy), "the person's call holds for every copy"
    # A ruling on the place holds only there.
    seen["https://board.example/metro/1"]["exclusion_reason"] = "place"
    urls, pairs = throttle.ruled_out(seen, TODAY)
    assert not throttle.ruled_pair(pairs, copy)


# ------------------------------------------------------------------ the cut


def _boards(monkeypatch):
    monkeypatch.setattr(apply_link, "board_for", lambda company: (
        "Oakmere Foods", "greenhouse", "oakmere") if "oakmere" in str(company).lower() else None)


def test_a_closed_posting_is_passed_over_and_the_next_taken(monkeypatch, tmp_path):
    """The link check ran after the cut to 10, so a closed posting held a place and nothing
    refilled it (audit 6, 15)."""
    _boards(monkeypatch)
    rows = [{"priority": 90, "fit": 90, "company": "Oakmere Foods", "title": "Data Analyst",
             "portal": "greenhouse", "url": "https://boards.greenhouse.io/oakmere/jobs/1"},
            {"priority": 80, "fit": 80, "company": "Fernhill Freight", "title": "Data Analyst",
             "portal": "linkedin", "url": "https://www.linkedin.com/jobs/view/2/"},
            {"priority": 70, "fit": 70, "company": "Larkspur Retail", "title": "Data Analyst",
             "portal": "linkedin", "url": "https://www.linkedin.com/jobs/view/3/"}]
    short = tmp_path / "06_shortlist.json"
    short.write_text(json.dumps(rows), encoding="utf-8")
    scraped = tmp_path / "kept.json"
    scraped.write_text(json.dumps([{"company": "Oakmere Foods", "portal": "greenhouse",
                                    "title": "Planner",
                                    "url": "https://boards.greenhouse.io/oakmere/jobs/7"}]),
                       encoding="utf-8")
    report = {}
    path = run_round.write_summary(str(short), str(tmp_path / "out"), "r1", str(scraped),
                                   show=2, report=report)
    got = [r["company"] for r in json.loads(open(path, encoding="utf-8").read())]
    assert got == ["Fernhill Freight", "Larkspur Retail"]
    assert report["found"] == 2
    assert report["passed_over"][0]["skip_reason"].startswith("closed")


def test_the_pay_a_posting_states_reaches_the_round_file(tmp_path):
    """Every row said "not stated" while its note quoted the range (audit 7)."""
    rows = [{"priority": 90, "fit": 90, "company": "Fernhill Freight", "title": "Data Analyst",
             "url": "https://jobs.example/1",
             "desc": "SQL and Python. Salary: £44,000 - £52,000 per year."},
            {"priority": 80, "fit": 80, "company": "Larkspur Retail", "title": "Data Analyst",
             "url": "https://jobs.example/2", "desc": "SQL and Python."}]
    short = tmp_path / "06_shortlist.json"
    short.write_text(json.dumps(rows), encoding="utf-8")
    path = run_round.write_summary(str(short), str(tmp_path / "out"), "r1", show=10)
    got = json.loads(open(path, encoding="utf-8").read())
    assert got[0]["salary"] == "GBP 44,000 to 52,000"
    assert "salary" not in got[1]


# ------------------------------------------------------------------ who is a way in


def _contact(cid, status, next_action="", notes=""):
    return {"contact_id": cid, "name": "Wren Halloway", "company": "Wexmoor Lending",
            "status": status, "next_action": next_action, "notes": notes}


@pytest.mark.parametrize("said", [
    "Parked (candidate, 2026-10-22). Offered a chat but is not hiring. Nothing owed.",
    "Not a hiring route; do not use him to chase.",
])
def test_a_reply_recorded_as_no_way_in_is_not_a_warm_route(said):
    """A parked contact added +12 until a fraud-ops role scored 100, and the card said
    "ask them first" against the record (audit 5, 8, 22)."""
    rows = [_contact("wexmoor_wren", "in_conversation", next_action=said)]
    assert throttle.warm_routes(rows=rows, live={}) == {}
    rows.append(dict(_contact("wexmoor_ash", "in_conversation", "Happy to refer: send the CV"),
                     name="Ash Penrose"))
    got = throttle.warm_routes(rows=rows, live={})
    assert [p["name"] for p in got["wexmoor lending"]] == ["Ash Penrose"]


# ------------------------------------------------------------------ skills held by another name


def test_a_skill_held_under_another_name_is_never_a_near_match(monkeypatch):
    """"Azure" asked of someone holding Azure Data Factory read "you have AWS" (audit 9)."""
    # The inventory as a person's skills.py names it: each item and the words that are it.
    monkeypatch.setattr(bridges, "_HELD_RX", [
        ("Azure Data Factory", re.compile(r"\bazure data factory\b", re.I)),
        ("AWS S3", re.compile(r"\baws\b|\bs3\b", re.I)),
        ("Tableau", re.compile(r"\btableau\b", re.I))])
    got = fit.near_matches("Experience with Azure cloud services is required.")
    assert not any(n["asked"] == "Azure" for n in got), got
    # A tool of the same kind held under no other name is still a near match.
    got = fit.near_matches("Experience with Google Cloud is required.")
    assert got == [{"asked": "Google Cloud", "have": "AWS S3"}], got


def test_a_parked_contact_adds_nothing_to_the_score_through_the_stage(tmp_path, monkeypatch):
    """Through fit.py as a round runs it: a fraud-ops role scored 100 on +12 from a contact
    recorded as parked (audit 5)."""
    import csv
    contacts = tmp_path / "network_contacts.csv"
    with open(contacts, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["contact_id", "name", "company", "status",
                                           "next_action", "notes"])
        w.writeheader()
        w.writerow({"contact_id": "wexmoor_wren", "name": "Wren Halloway",
                    "company": "Wexmoor Lending", "status": "in_conversation",
                    "next_action": "Parked (candidate, 2026-10-22). Not hiring. Nothing owed."})
        w.writerow({"contact_id": "fernhill_ash", "name": "Ash Penrose",
                    "company": "Fernhill Freight", "status": "in_conversation",
                    "next_action": "Happy to refer: send the CV"})
    job = {"title": "Fraud Analyst", "location": "Manchester, England, United Kingdom",
           "desc": "SQL and Python reporting."}
    src, out = tmp_path / "in.json", tmp_path / "out.json"
    src.write_text(json.dumps([dict(job, company="Wexmoor Lending"),
                               dict(job, company="Fernhill Freight")]))
    monkeypatch.setattr(sys, "argv", ["fit.py", str(src), "--out", str(out),
                                      "--contacts", str(contacts)])
    assert fit.main() == 0
    got = {r["company"]: r for r in json.loads(out.read_text())}
    assert not got["Wexmoor Lending"].get("warm_route")
    assert not any("live contact" in w for w in got["Wexmoor Lending"]["fit_why"])
    assert got["Fernhill Freight"]["warm_route"], "a real way in still counts"
    assert got["Fernhill Freight"]["fit"] == got["Wexmoor Lending"]["fit"] + fit.REFERRAL_BONUS
