"""The counts a round prints name what they count.

The throttle counted its skips by each reason up to its first colon or comma, so a
reason with neither (an application already made to the same role) was its own
category, a whole sentence long. The prefilter reported a referral in flight,
do_not_target.json and the candidate's bar as rulings "already ruled out in
seen_jobs.json", which they are not: they are today's state, and lift when it does.
"""
from __future__ import annotations

import csv
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
sys.path.insert(0, TOOLS)

import throttle  # noqa: E402

TRACKER = ["date", "company", "sector", "role", "role_type", "channel", "status",
           "contact_person", "fit_rating", "notes", "cv_file", "cover_letter_file", "source",
           "deadline"]


def _row(n, company, title="Demand Planning Analyst"):
    return {"url": f"https://careers.example.com/jobs/{n}", "title": title, "company": company,
            "location": "Salford, England, United Kingdom", "priority": 70 - n, "fit": 80 - n,
            "opportunity": 50, "desc": "You will own demand forecasting for the network."}


def test_the_throttle_counts_an_application_already_made_as_one_kind(tmp_path):
    tracker = tmp_path / "tracker.csv"
    with open(tracker, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=TRACKER)
        w.writeheader()
        for company in ("Hollowmere Foods", "Quenby Freight"):
            w.writerow({"date": "2026-09-01", "company": company, "role": "Demand Planning Analyst",
                        "status": "rejected", "fit_rating": "70"})
    ranked = tmp_path / "ranked.json"
    ranked.write_text(json.dumps([_row(1, "Hollowmere Foods"), _row(2, "Quenby Freight"),
                                  _row(3, "Tarnwick Mills")]), encoding="utf-8")
    seen = tmp_path / "seen_jobs.json"
    seen.write_text('{"seen": {}}', encoding="utf-8")
    r = subprocess.run([sys.executable, os.path.join(TOOLS, "throttle.py"), str(ranked),
                        "--out", str(tmp_path / "out.json"), "--tracker", str(tracker),
                        "--seen", str(seen), "--today", "2026-10-21", "--no-write",
                        "--contacts", str(tmp_path / "none.csv"),
                        "--do-not-target", str(tmp_path / "none.json")],
                       capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stderr
    assert "{'already applied to this role': 2}" in r.stderr, r.stderr


def test_each_kind_of_skip_reads_as_its_kind():
    assert throttle.skip_kind("already applied to this role on 2026-09-01 (withdrawn); a "
                              "relisted posting is the same job") == "already applied to this role"
    assert throttle.skip_kind("company throttle: an application is already open at this "
                              "employer (Analyst, applied, 2026-10-01)") == "company throttle"
    assert throttle.skip_kind("already ruled out, excluded in seen_jobs.json: x") == \
        "already ruled out"
    assert throttle.skip_kind("something new, with a comma") == "something new"


def test_the_prefilter_counts_todays_holds_apart_from_past_rulings(tmp_path):
    today = "2026-10-21"
    seen = tmp_path / "seen_jobs.json"
    seen.write_text(json.dumps({"seen": {"https://careers.example.com/jobs/1": {
        "url": "https://careers.example.com/jobs/1", "title": "Data Analyst",
        "company": "Hollowmere Foods", "status": "excluded", "basis": "person",
        "exclusion_reason": "not this kind of company", "excluded_date": "2026-10-20"}}}),
        encoding="utf-8")
    dnt = tmp_path / "do_not_target.json"
    dnt.write_text(json.dumps({"companies": {"Quenby Freight": {
        "reason": "only a sales office here", "recorded": "2026-10-01",
        "review_after": "2027-04-01"}}}), encoding="utf-8")
    rows = [{"url": f"https://careers.example.com/jobs/{n}", "title": "Data Analyst",
             "company": c, "location": "Manchester, England, United Kingdom", "date": today}
            for n, c in ((1, "Hollowmere Foods"), (2, "Quenby Freight"), (3, "Tarnwick Mills"),
                         (4, "Royal Casino Group"))]
    new = tmp_path / "new.json"
    new.write_text(json.dumps(rows), encoding="utf-8")
    r = subprocess.run([sys.executable, os.path.join(TOOLS, "prefilter.py"), str(new),
                        "--out", str(tmp_path / "kept.json"), "--seen", str(seen),
                        "--dropped", str(tmp_path / "dropped.json"), "--today", today,
                        "--do-not-target", str(dnt), "--contacts", str(tmp_path / "none.csv")],
                       capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stderr
    assert "1 of the dropped were already ruled out in seen_jobs.json" in r.stderr, r.stderr
    assert "2 are held back today" in r.stderr, r.stderr
