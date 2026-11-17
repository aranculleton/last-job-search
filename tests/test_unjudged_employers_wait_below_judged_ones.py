"""Employers nobody has judged against the person's bar wait below judged ones, are listed by
the round for judging in one batch, and a cut made again after the batch puts them where
their judgement says.

From one person's rounds (2026-11-16, issue #304): the top of a fresh list was employers
nobody had judged (an advertising agency, a small consultancy, a little-known AI firm at
priority 80 to 83, above the person's real targets), judged one at a time by a chat after
the round, so every "none" it recorded took a row off the list instead of refilling it.
Every employer is invented.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import bar  # noqa: E402
import run_round  # noqa: E402

TODAY = "2026-11-16"
LEEDS = "Leeds, England, United Kingdom"
UNKNOWN = ("Quorlan Media", "Tessaly Consulting", "Vintry Labs AI")
KNOWN = ("Ambleside Freight", "Bellingham Foods", "Carrow Retail")


def _row(n, company, priority):
    return {"title": "Data Analyst", "company": company, "location": LEEDS,
            "url": f"https://www.linkedin.com/jobs/view/{8900000 + n}/", "portal": "linkedin",
            "date": "2026-11-14", "first_seen": "2026-11-14", "fit": 78, "priority": priority,
            "opportunity": 70,
            "desc": f"About us: {company} helps businesses grow with data. "
                    "You will build SQL and Python reporting for the planning team."}


def _main(monkeypatch, argv):
    monkeypatch.setattr(sys, "argv", ["run_round.py", *argv])
    return run_round.main()


def test_unjudged_employers_wait_below_judged_ones_until_a_batch_judges_them(
        tmp_path, monkeypatch, capsys, judged):
    st = tmp_path / "state"
    shutil.copytree(os.path.join(ROOT, "profile.example", "state"), st)
    monkeypatch.setenv("LJS_STATE", str(st))
    monkeypatch.setattr(bar, "FRONTIER", {"frontier example labs"})
    monkeypatch.setattr(bar, "PUBLIC", re.compile(r"(?!x)x"))
    monkeypatch.setattr(run_round, "declined_now", lambda: {})
    monkeypatch.setattr(run_round, "_upgrades_line", lambda: "")
    judged(*KNOWN)
    ranked = ([_row(n, c, 95 - n) for n, c in enumerate(UNKNOWN)]
              + [_row(10 + n, c, 85 - n) for n, c in enumerate(KNOWN)])

    def stage(cmd, log, deadline=None, ok=(0,)):
        tool = os.path.basename(cmd[1])
        if tool == "fit.py":
            with open(cmd[cmd.index("--out") + 1], "w", encoding="utf-8") as fh:
                json.dump(ranked, fh)
        elif tool == "throttle.py":
            got = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
            assert got.returncode == 0, got.stderr
        return 0

    monkeypatch.setattr(run_round, "run", stage)
    scraped = tmp_path / "scraped.json"
    scraped.write_text("[]", encoding="utf-8")
    rounds = st / "documents" / "rounds"
    folder = st / "rounds" / "r7"
    common = ["--seen", str(st / "job_scraper" / "seen_jobs.json"),
              "--tracker", str(st / "job_search_tracker.csv"), "--summary-dir", str(rounds),
              "--today", TODAY, "--show", "3"]
    _main(monkeypatch, ["--out", str(folder), "--from-scraped", str(scraped), "--pages", "1",
                        *common])
    said = capsys.readouterr().out
    summary = json.loads((rounds / "r7.json").read_text(encoding="utf-8"))
    assert [r["company"] for r in summary] == list(KNOWN)
    assert "nobody has judged yet" in said and all(c in said for c in UNKNOWN)
    # What the round asks a chat to judge, in one batch: each employer once, with what its
    # own posting says about it.
    asked = json.loads((folder / run_round.UNJUDGED).read_text(encoding="utf-8"))
    assert [a["company"] for a in asked] == list(UNKNOWN)
    assert all(a["about"].startswith("About us:") for a in asked)

    # Judged in one go, then the round cut again: two clear the bar and rise to the top,
    # one clears none and is left out.
    for a, (what, why) in zip(asked, (("pay", "pays at the top of the market"),
                                      ("prestige", "a well-known consultancy"),
                                      ("none", "a two-person AI start-up"))):
        a.update(verdict=what, why=why)
    batch = tmp_path / "judged.json"
    batch.write_text(json.dumps(asked), encoding="utf-8")
    assert bar.main(["judge", "--file", str(batch)]) == 0
    stored = bar.judged()
    assert {r.get("by") for r in stored.values() if r.get("name") in UNKNOWN} == {"round"}
    assert _main(monkeypatch, ["--out", str(folder), "--recut", *common]) == 0
    again = json.loads((rounds / "r7.json").read_text(encoding="utf-8"))
    assert [r["company"] for r in again] == ["Quorlan Media", "Tessaly Consulting",
                                             "Ambleside Freight"]
