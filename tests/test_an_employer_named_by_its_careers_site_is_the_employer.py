"""An employer a job feed names by its careers site, its slug or a team is the employer the
person's records hold.

From one person's rounds (2026-11-16, issue #305): an aggregator named a bank by its careers
site ("jobs.<name>bank.com"), run together ("<name>bank"), as a slug with a number on
("<name>1"), by a team ("<Name> Engineering") and as "<Name> - Internal". None keyed as the
employer, so an open application at the bank held nothing back (its role was first on one
list), a role already applied for came back as new at rank 4 under the team's name, one
role came back twice, and an internal-only listing was ranked. Every name here is invented.
"""
from __future__ import annotations

import csv
import json
import os
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
sys.path.insert(0, TOOLS)

import company_key  # noqa: E402
import text_screen  # noqa: E402

TODAY = "2026-11-16"
TRACKER_FIELDS = ("date", "company", "sector", "role", "role_type", "channel", "status",
                  "contact_person", "fit_rating", "notes", "cv_file", "cover_letter_file",
                  "source", "deadline")


@pytest.fixture(autouse=True)
def _forget_what_was_known():
    """The employers these tests make known are forgotten after each, so no later test in
    the same worker keys its own names against them."""
    known = company_key._known()
    keys, joined = set(known["keys"]), {j: set(v) for j, v in known["joined"].items()}
    yield
    known.update(keys=keys, joined=joined, resolved={})


@pytest.mark.parametrize("given,on_record,expected", [
    ("jobs.northfieldbank.com", "Northfield Bank", "northfield bank"),
    ("careers.northfieldbank.co.uk", "Northfield Bank", "northfield bank"),
    ("northfieldbank", "Northfield Bank", "northfield bank"),
    ("northfieldbankcanadaltd", "Northfield Bank", "northfield bank"),
    ("pallister1", "Pallister", "pallister"),
    ("Tamberlin Engineering", "Tamberlin", "tamberlin"),
    ("Tamberlin Science", "Tamberlin", "tamberlin"),
    ("Brightmart - Internal", "Brightmart", "brightmart"),
    ("ostrander.wd3.myworkdayjobs.com", "Ostrander", "ostrander"),
    ("ostrander.taleo.net/1", "Ostrander", "ostrander"),
])
def test_each_form_a_feed_gives_keys_as_the_employer_on_record(given, on_record, expected):
    company_key.know([on_record])
    assert company_key.key(on_record) == expected
    assert company_key.key(given) == expected


@pytest.mark.parametrize("given,expected", [
    # A name the records do not hold is left as it is: no team or run-together form is
    # joined to an employer nobody named.
    ("Wexcombe Engineering", "wexcombe engineering"),
    ("wexcombebank", "wexcombebank"),
    # A number that is the name's own, and a name with a dot that is no web address.
    ("tallis360", "tallis360"),
    ("Tallis360", "tallis360"),
    ("Kestrel.Commerce", "kestrel commerce"),
])
def test_a_name_nothing_on_record_explains_keeps_its_own_key(given, expected):
    assert company_key.key(given) == expected


def _write_tracker(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=TRACKER_FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in TRACKER_FIELDS})


def _row(n, company, title, fit=80, priority=100):
    return {"company": company, "title": title, "url": f"https://jobs.example/{n}",
            "location": "Toronto, Ontario, Canada", "fit": fit, "priority": priority,
            "desc": f"{company} is hiring a {title}."}


@pytest.fixture
def records(tmp_path):
    tracker = tmp_path / "tracker.csv"
    _write_tracker(tracker, [
        # Applied three weeks ago and still open: holds the bank back.
        {"date": "2026-10-26", "company": "Northfield Bank", "role": "Credit Risk Analyst",
         "status": "applied", "fit_rating": "82"},
        # The role already applied for, at the company itself.
        {"date": "2026-10-26", "company": "Tamberlin", "role": "Sr. Data Scientist",
         "status": "applied", "fit_rating": "85"},
        # A closed application at a lender: other roles there are fair game.
        {"date": "2026-07-01", "company": "Lowmoor Lending", "role": "Pricing Analyst",
         "status": "rejected", "fit_rating": "70"},
    ])
    return tmp_path, tracker


def _throttle(tmp_path, tracker, rows):
    ranked = tmp_path / "ranked.json"
    ranked.write_text(json.dumps(rows), encoding="utf-8")
    contacts = tmp_path / "contacts.csv"
    contacts.write_text("name,title,company\n", encoding="utf-8")
    seen = tmp_path / "seen.json"
    seen.write_text('{"seen": {}}', encoding="utf-8")
    out, skipped = tmp_path / "short.json", tmp_path / "skipped.json"
    got = subprocess.run(
        [sys.executable, os.path.join(TOOLS, "throttle.py"), str(ranked), "--out", str(out),
         "--skipped", str(skipped), "--tracker", str(tracker), "--seen", str(seen),
         "--contacts", str(contacts), "--do-not-target", str(tmp_path / "dnt.json"),
         "--today", TODAY, "--no-write"],
        capture_output=True, text=True, encoding="utf-8")
    assert got.returncode == 0, got.stderr
    return (json.loads(out.read_text(encoding="utf-8")),
            {r["company"]: r["skip_reason"]
             for r in json.loads(skipped.read_text(encoding="utf-8"))})


def test_an_open_application_holds_back_a_role_listed_under_its_careers_site(records):
    tmp_path, tracker = records
    kept, skipped = _throttle(tmp_path, tracker, [
        _row(1, "jobs.northfieldbank.com", "Senior Data Scientist, Risk", fit=84),
        _row(2, "Wexcombe Insurance", "Data Scientist", fit=70, priority=80)])
    assert [r["company"] for r in kept] == ["Wexcombe Insurance"]
    assert skipped["jobs.northfieldbank.com"].startswith(
        "company throttle: an application is already open at this employer "
        "(Credit Risk Analyst, applied")


def test_a_role_applied_for_comes_back_under_a_teams_name_as_the_same_role(records):
    tmp_path, tracker = records
    kept, skipped = _throttle(tmp_path, tracker, [
        _row(1, "Tamberlin Engineering", "Senior Data Scientist", fit=80)])
    assert kept == []
    assert skipped["Tamberlin Engineering"].startswith(
        "company throttle: the same role has already been applied to (Sr. Data Scientist")


def test_one_role_per_employer_holds_across_the_run_together_name(records):
    tmp_path, tracker = records
    kept, skipped = _throttle(tmp_path, tracker, [
        _row(1, "lowmoorlending", "Risk Strategy Analyst", fit=78, priority=95),
        _row(2, "Lowmoor Lending", "Risk Strategy Analyst", fit=78, priority=95)])
    assert len(kept) == 1
    assert list(skipped.values())[0].startswith("same-employer duplicate")


def test_the_cut_and_the_page_find_the_application_under_either_name(records, tmp_path):
    """The shortlist's own check (run_round.already_had) and the page's tracker match
    (app_model.tracker_match), each in a process of its own reading only these records."""
    _, tracker = records
    state = tmp_path / "state"
    shutil.copytree(os.path.join(ROOT, "profile.example", "state"), state)
    shutil.copyfile(tracker, state / "job_search_tracker.csv")
    asked = [["Tamberlin Engineering", "Senior Data Scientist"],
             ["jobs.northfieldbank.com", "Credit Risk Analyst"]]
    script = (
        "import datetime, json, sys\n"
        f"sys.path.insert(0, {TOOLS!r})\n"
        "import run_round, app_model\n"
        "asked = json.loads(sys.argv[1])\n"
        f"had = run_round.already_had(today={TODAY!r}, listed=False, drafts=False)\n"
        "ctx = app_model.Ctx(datetime.date(2026, 11, 16), datetime.datetime(2026, 11, 16, 9))\n"
        "found = [(app_model.tracker_match(ctx, c, t) or {}).get('company') for c, t in asked]\n"
        "print(json.dumps([had({'company': asked[0][0], 'title': asked[0][1]})] + found))\n")
    env = dict(os.environ, LJS_STATE=str(state))
    got = subprocess.run([sys.executable, "-c", script, json.dumps(asked)], capture_output=True,
                         text=True, encoding="utf-8", env=env)
    assert got.returncode == 0, got.stderr
    why, tracked, banked = json.loads(got.stdout.strip().splitlines()[-1])
    assert why.startswith("already in your applications: Sr. Data Scientist (applied")
    assert tracked == "Tamberlin" and banked == "Northfield Bank"


def test_an_internal_listing_is_cut_by_its_employer_field():
    job = {"company": "Brightmart - Internal", "title": "Senior Data Analyst",
           "desc": "Brightmart is hiring a Senior Data Analyst for its pricing team. " * 6}
    cuts = text_screen.screen(job).get("cuts") or []
    assert any(c.startswith("open to the employer's own staff only") and "Internal" in c
               for c in cuts), cuts
    # Internal Audit is a job, and an employer called after its own work is no listing mark.
    for company, title in (("Brightmart", "Internal Audit Analyst"),
                           ("Internal Systems Partners", "Data Analyst")):
        assert not any("own staff" in c for c in text_screen.screen(
            {"company": company, "title": title, "desc": job["desc"]}).get("cuts") or [])
