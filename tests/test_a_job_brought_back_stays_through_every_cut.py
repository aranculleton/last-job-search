"""A posting the person brings back after a rule filtered it stays on their list: through the
page's own search window, and through every cut of its round made again.

From one person's copy (2026-11-16, issue #298): a role left out only because it was 11 days
old under a 10-day window was brought back from the page. The page's Jobs list still left it
out (its age check spared only jobs added or kept), and the page's search steps cut the round
again, which rebuilt the list from the round's own folder: Bring back had written only the
saved list, never the round's folder, and the cut passed it over by its age again. A chat put
it back by hand twice. Every employer is invented.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import app_model  # noqa: E402
import filtered  # noqa: E402
import run_round  # noqa: E402

TODAY = "2026-11-16"
NOW = dt.datetime(2026, 11, 16, 20, tzinfo=dt.timezone.utc)
LEEDS = "Leeds, England, United Kingdom"
OLD = {"title": "Solutions Engineer", "company": "Harwood Systems", "location": LEEDS,
       "url": "https://www.linkedin.com/jobs/view/8800011/", "portal": "linkedin",
       "date": "2026-11-05",
       "prefilter_reason": "age: 11 days old (posted 2026-11-05), past the 10-day window"}


def _row(n, company):
    return {"title": "Data Analyst", "company": company, "location": LEEDS,
            "url": f"https://www.linkedin.com/jobs/view/{8800100 + n}/", "portal": "linkedin",
            "date": "2026-11-14", "first_seen": "2026-11-14", "fit": 80 - n,
            "priority": 90 - n, "opportunity": 70,
            "desc": "You will build SQL and Python reporting for the planning team."}


def _main(monkeypatch, argv):
    monkeypatch.setattr(sys, "argv", ["run_round.py", *argv])
    return run_round.main()


def test_a_posting_brought_back_from_the_search_window_stays_through_a_cut_and_the_page(
        tmp_path, monkeypatch):
    st = tmp_path / "state"
    shutil.copytree(os.path.join(ROOT, "profile.example", "state"), st)
    monkeypatch.setenv("LJS_STATE", str(st))
    monkeypatch.setattr(run_round, "declined_now", lambda: {})
    monkeypatch.setattr(run_round, "_upgrades_line", lambda: "")
    monkeypatch.setattr(run_round, "_job_age_days", lambda: 10)
    ranked = [_row(n, c) for n, c in enumerate(("Ashby Freight", "Brantwood Foods",
                                                "Coldwell Retail"), 1)]

    def stage(cmd, log, deadline=None, ok=(0,)):
        tool = os.path.basename(cmd[1])
        if tool == "scrape_wide.py":
            out = cmd[cmd.index("--out") + 1]
            os.makedirs(out, exist_ok=True)
            for name, rows in (("kept.json", []), ("dropped.json", [OLD])):
                with open(os.path.join(out, name), "w", encoding="utf-8") as fh:
                    json.dump(rows, fh)
        elif tool == "fit.py":
            with open(cmd[cmd.index("--out") + 1], "w", encoding="utf-8") as fh:
                json.dump(ranked, fh)
        elif tool == "throttle.py":
            got = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
            assert got.returncode == 0, got.stderr
        return 0

    monkeypatch.setattr(run_round, "run", stage)
    seen = st / "job_scraper" / "seen_jobs.json"
    rounds = st / "documents" / "rounds"
    folder = st / "rounds" / "r6"
    common = ["--seen", str(seen), "--tracker", str(st / "job_search_tracker.csv"),
              "--summary-dir", str(rounds), "--today", TODAY, "--show", "3"]
    _main(monkeypatch, ["--out", str(folder), "--pages", "1", *common])
    left = filtered.load("r6", str(rounds))["filtered"]
    assert any(e.get("url") == OLD["url"] for e in left)

    # Brought back from the page, as the page does it: by its link, with no round folder.
    got = filtered.back("r6", [OLD["url"]], today=TODAY, summary_dir=str(rounds),
                        seen_path=str(seen))
    assert got and got[0][1]
    staged = json.loads((folder / run_round.SHORTLIST).read_text(encoding="utf-8"))
    assert any(r.get("url") == OLD["url"] and r.get("brought_back") for r in staged)

    # The page's search steps cut the round again: the posting is still on the list.
    assert _main(monkeypatch, ["--out", str(folder), "--recut", *common]) == 0
    summary = json.loads((rounds / "r6.json").read_text(encoding="utf-8"))
    assert OLD["url"] in [r["url"] for r in summary]
    assert len([r for r in summary if r["url"] != OLD["url"]]) == 3

    # And the page lists it, past the person's window.
    jobs = app_model._jobs(app_model.Ctx(dt.date.fromisoformat(TODAY), NOW), {})
    row = next((r for r in jobs["rows"] if r["draft_work"]["args"]["url"] == OLD["url"]), None)
    assert row is not None and row["status"] == "new", jobs["rows"]
    assert "You brought this back after it was filtered out." in " ".join(row.get("notes") or [])


def test_a_brought_back_row_passes_the_rules_a_posting_decides_but_not_a_later_ruling(
        tmp_path):
    import exclude
    seen = tmp_path / "seen.json"
    seen.write_text('{"seen": {}}', encoding="utf-8")
    rules = run_round.hard_rules(10, TODAY, str(seen))
    back = dict(OLD, fit=70, priority=80, brought_back="brought back 2026-11-16: filtered")
    assert rules(back) == ""
    assert rules({k: v for k, v in back.items() if k != "brought_back"}).startswith("age:")
    # A ruling the person makes after bringing it back stands.
    exclude.add(OLD["url"], "not for me after all", OLD["title"], OLD["company"],
                basis="person", today=TODAY, path=str(seen))
    assert run_round.hard_rules(10, TODAY, str(seen))(back)
