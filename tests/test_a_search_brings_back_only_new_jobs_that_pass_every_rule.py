"""A search asked for N brings back N new jobs that pass every rule, or says it found fewer.

The maintainer's search of 20 on 4 November let through nine it should have caught: four
already on the list or already drafted, four staffing agencies their bar rules out, and one
that required French, none of them with a score. The number asked for (run_round.py --show)
is cut by one function, the shortlist's own (run_round.hard_rules), and it now holds the
language gate and every other hard cut of the stated-fact screen, the bar with the agency
rule, the jobs the person already has (applied, drafted, added, kept, or on the list from an
earlier search) and a row with no score. Every person and employer is invented.
"""
from __future__ import annotations

import csv
import json
import os
import re
import shutil
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import run_round  # noqa: E402
import sector  # noqa: E402

TODAY = "2026-11-04"
GOOD = "You will build SQL and Python reporting for the pricing team."


def _row(n, company, title="Data Analyst", desc=GOOD, url=None, score=True):
    r = {"title": title, "company": company, "date": "2026-11-02", "first_seen": "2026-11-02",
         "portal": "linkedin", "desc": desc, "location": "Leeds, England, United Kingdom",
         "url": url or f"https://www.linkedin.com/jobs/view/{n}/"}
    if score:
        r.update(fit=95 - n, priority=100 - n)
    return r


@pytest.fixture
def state(tmp_path, monkeypatch, judged):
    """The example person's state, copied, with what they already have: a draft in the
    tracker, an earlier search's job still on the list, a job they added and one they kept."""
    st = tmp_path / "state"
    shutil.copytree(os.path.join(ROOT, "profile.example", "state"), st)
    monkeypatch.setenv("LJS_STATE", str(st))
    tracker = st / "job_search_tracker.csv"
    with open(tracker, encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
        head = list(rows[0].keys())
    rows.append({**{k: "" for k in head}, "date": "2026-11-01", "company": "Kestrel Mutual",
                 "role": "Data Analyst", "status": "drafted", "fit_rating": "81",
                 "cv_file": "cv/Morgan_Ellis_CV_Kestrel.tex"})
    with open(tracker, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=head)
        w.writeheader()
        w.writerows(rows)
    rounds = st / "documents" / "rounds"
    (rounds / "kept").mkdir(parents=True)
    (rounds / "added").mkdir(parents=True)
    (rounds / "r3.json").write_text(json.dumps([dict(
        _row(30, "Ottergate Foods", url="https://boards.example/ottergate/7"),
        first_seen="2026-11-01")]), encoding="utf-8")
    (rounds / "added" / "jobs.json").write_text(json.dumps([{
        "title": "Data Analyst", "company": "Wexmoor Lending",
        "url": "https://careers.example/wexmoor/12", "fit": 77}]), encoding="utf-8")
    (rounds / "kept" / "jobs.json").write_text(json.dumps({
        "https://www.linkedin.com/jobs/view/40/": {"round": "r2", "rank": 3,
                                                   "title": "Pricing Analyst",
                                                   "company": "Brackenhollow Foods",
                                                   "kept_on": "2026-10-30"}}),
        encoding="utf-8")
    monkeypatch.setattr(sector, "AGENCY", re.compile(r"\bstaffing\b"))
    return tracker


def _search(tmp_path, monkeypatch, rows, show, tracker):
    """run_round.main() as a search of `show` runs it, every stage stood in and the ranked
    shortlist `rows`; the jobs it brings back and what it printed."""
    def stage(cmd, log, deadline=None, ok=(0,)):
        if os.path.basename(cmd[1]) == "throttle.py":
            with open(cmd[cmd.index("--out") + 1], "w", encoding="utf-8") as fh:
                json.dump(rows, fh)

    monkeypatch.setattr(run_round, "run", stage)
    monkeypatch.setattr(run_round.subprocess, "call", lambda cmd: 0)
    monkeypatch.setattr(run_round, "_upgrades_line", lambda: "")
    scraped = tmp_path / "scraped.json"
    scraped.write_text("[]")
    seen = tmp_path / "seen_jobs.json"
    seen.write_text('{"seen": {}}', encoding="utf-8")
    monkeypatch.setattr(sys, "argv", [
        "run_round.py", "--out", str(tmp_path / "r4"), "--from-scraped", str(scraped),
        "--seen", str(seen), "--tracker", str(tracker), "--summary-dir", str(tmp_path / "summ"),
        "--today", TODAY, "--jobage", "14", "--show", str(show)])
    run_round.main()
    return json.loads((tmp_path / "summ" / "r4.json").read_text(encoding="utf-8"))


def test_a_search_of_n_brings_back_only_new_jobs_that_pass_every_rule(
        tmp_path, monkeypatch, capsys, state):
    rows = [_row(1, "Harrowgate Insurance",
                 desc=GOOD + " Fluency in French is required for this role."),
            _row(2, "Brightpath Staffing"),
            _row(3, "Kestrel Mutual", title="Data Analyst (Hybrid)"),
            _row(4, "Ottergate Foods", url="https://boards.example/ottergate/7"),
            _row(5, "Wexmoor Lending", url="https://careers.example/wexmoor/12/?trk=feed"),
            _row(6, "Brackenhollow Foods", title="Pricing Analyst", url="https://www.linkedin.com/jobs/view/40/"),
            _row(7, "Fernhill Freight"),
            _row(8, "Northmere Analytics"),
            _row(9, "Quillfield Retail", score=False)]
    got = _search(tmp_path, monkeypatch, rows, 10, state)
    assert [r["company"] for r in got] == ["Fernhill Freight", "Northmere Analytics"]
    out = capsys.readouterr().out
    assert "found 2 of the 10 asked for that pass every rule" in out
    # Each one passed over says why, in the words the person reads.
    assert "French stated as a requirement" in out
    assert "a recruitment or staffing agency" in out


def test_each_job_the_person_already_has_is_passed_over_with_its_reason(state):
    check = run_round.hard_rules(14, TODAY, name="r4", tracker=str(state))
    said = {r["company"]: check(r) for r in [
        _row(3, "Kestrel Mutual", title="Data Analyst (Hybrid)"),
        _row(4, "Ottergate Foods", url="https://boards.example/ottergate/7"),
        _row(5, "Wexmoor Lending", url="https://careers.example/wexmoor/12"),
        _row(6, "Brackenhollow Foods", title="Pricing Analyst",
             url="https://www.linkedin.com/jobs/view/40/"),
        _row(7, "Larkspur Retail", title="Senior Supply Chain Analyst"),
        _row(9, "Quillfield Retail", score=False),
        _row(8, "Northmere Analytics")]}
    assert said["Kestrel Mutual"] == "already drafted: Data Analyst, 2026-11-01"
    assert said["Ottergate Foods"] == "already on your list, from search r3"
    assert said["Wexmoor Lending"] == "already on your list: you added it"
    assert said["Brackenhollow Foods"] == "already on your list: kept for later"
    assert said["Larkspur Retail"].startswith("already in your applications: Senior Supply "
                                              "Chain Analyst (applied, 2026-09-08)")
    assert said["Quillfield Retail"] == "no score: a job is never shown unscored"
    assert said["Northmere Analytics"] == ""


def test_a_draft_saved_for_a_job_counts_though_the_tracker_never_got_it(state):
    folder = state.parent / "documents" / "applications" / "harrowgate_data_analyst"
    folder.mkdir(parents=True)
    (folder / "draft.json").write_text(json.dumps([{
        "company": "Harrowgate Insurance", "role": "Data Analyst", "abbr": "Harrowgate"}]),
        encoding="utf-8")
    check = run_round.hard_rules(14, TODAY, name="r4", tracker=str(state))
    assert check(_row(1, "Harrowgate Insurance")) == "already drafted: Data Analyst"


def test_a_widened_round_does_not_pass_over_what_its_first_round_found(state):
    """r3 widened is r3_round2: the same search, so r3's jobs are its own, not the list's."""
    rounds = state.parent / "documents" / "rounds"
    row = _row(4, "Ottergate Foods", url="https://boards.example/ottergate/7")
    assert run_round.hard_rules(14, TODAY, name="r3_round2", tracker=str(state))(row) == ""
    (rounds / "r3_round2.json").write_text("[]", encoding="utf-8")
    assert run_round.family("r3_round2") == {"r3", "r3_round2"}
    assert run_round.hard_rules(14, TODAY, name="r5", tracker=str(state))(row) \
        == "already on your list, from search r3"


def test_a_cut_made_again_keeps_the_jobs_its_last_cut_kept(state):
    """--recut after the person drafted one of the round's own jobs: it stays where it was."""
    row = _row(3, "Kestrel Mutual", title="Data Analyst (Hybrid)")
    check = run_round.hard_rules(14, TODAY, name="r4", tracker=str(state), own=[row["url"]])
    assert check(row) == ""
