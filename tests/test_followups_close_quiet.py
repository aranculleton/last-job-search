"""An application that has gone quiet is closed, with a dated note, by the brief.

Rows sat at `applied` for months: closing one waited on somebody running /outcome
about silence, which nobody notices. `followups.py --close-quiet` closes what the
chase already gave up on, and leaves alone anything that may still be alive.
"""
import csv
import datetime
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import followups  # noqa: E402

HEAD = ["company", "role", "date", "status", "notes", "cv_file"]
TODAY = datetime.date(2026, 6, 1)


def _write(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=HEAD)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in HEAD})


def _read(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def test_quiet_rows_close_and_live_ones_stay(tmp_path):
    path = tmp_path / "tracker.csv"
    _write(path, [
        {"company": "Fernhill Freight", "role": "Pricing Analyst", "date": "2026-03-01",
         "status": "applied"},                                          # 92 days: closes
        {"company": "Larkspur Retail", "role": "Data Analyst", "date": "2026-05-20",
         "status": "applied"},                                          # 12 days: stays
        {"company": "Kestrel Mutual", "role": "Risk Analyst", "date": "2026-03-01",
         "status": "applied"},                                          # live interview there
        {"company": "Kestrel Mutual", "role": "Data Scientist", "date": "2026-05-25",
         "status": "interview"},
        {"company": "Brindle Hart", "role": "Analyst", "date": "2026-03-01", "status": "applied",
         "notes": "2026-05-01: DO NOT CHASE until 2026-07-01, recruiter on leave"},
    ])
    gone = followups.close_quiet(str(path), TODAY, holds={})
    assert [it["company"] for it in gone] == ["Fernhill Freight"]
    rows = _read(path)
    assert [r["status"] for r in rows] == ["no_response", "applied", "applied", "interview",
                                           "applied"]
    assert rows[0]["notes"].startswith("2026-06-01: closed as no_response, no reply in 92 days")
    # Columns kept where they were; the close says it was the search's call, so it is
    # never read as the person's, and keeps the day it went for `confirm.py` to undo it.
    assert list(rows[0]) == HEAD + ["applied_on", "confirmed_by", "confirmed_at"]
    assert (rows[0]["applied_on"], rows[0]["confirmed_by"]) == ("2026-03-01", "the search")
    assert rows[0]["confirmed_at"].startswith("2026-06-01 ")
    assert rows[1]["confirmed_by"] == ""
    # Run again: nothing left to close, nothing written twice.
    assert followups.close_quiet(str(path), TODAY, holds={}) == []


def test_a_referral_in_flight_keeps_it_open_and_a_dry_run_writes_nothing(tmp_path):
    path = tmp_path / "tracker.csv"
    _write(path, [{"company": "Fernhill Freight", "role": "Pricing Analyst",
                   "date": "2026-03-01", "status": "applied"}])
    key = followups.company_key("Fernhill Freight")
    assert followups.close_quiet(str(path), TODAY, holds={key: "referral in flight"}) == []
    assert len(followups.close_quiet(str(path), TODAY, write=False, holds={})) == 1
    assert _read(path)[0]["status"] == "applied"
