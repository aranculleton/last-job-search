"""What a round filtered out is kept, with why, and the person can bring one back.

A round drops most of what it finds, and the stage files that said what and why were
deleted by every round that met its target, the 14-day relist rule's drops included: the
person could neither see what was left out nor overrule it. Every round now keeps the
list at documents/rounds/filtered/<round>.json, and `filtered.py back` lifts the ruling
and puts the posting on the round's shortlist to stage. Every posting here is invented.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import filtered  # noqa: E402

RELIST = ("age: first seen 49 days ago, past the 14-day hard limit; the portal's 5 days is "
          "a relist")


def _write(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(rows, fh)


def _round(rd):
    _write(os.path.join(rd, "00_scrape", "dropped.json"), [
        {"title": "Data Analyst", "company": "Acme Analytics", "location": "London",
         "url": "https://jobs.example/1?utm_source=x", "portal": "linkedin",
         "prefilter_reason": "location: on-site outside the Greater Manchester (london)",
         "desc": "a body that is never kept"}])
    _write(os.path.join(rd, "01_dropped.json"), [
        {"title": "Risk Analyst", "company": "Thornbury Bank", "location": "Manchester",
         "url": "https://jobs.example/2", "portal": "nationalboard", "prefilter_reason": RELIST},
        # The same posting the search already dropped is listed once.
        {"title": "Data Analyst", "company": "Acme Analytics", "url": "https://jobs.example/1",
         "prefilter_reason": "already ruled out"}])
    _write(os.path.join(rd, "03_screened_all.json"), [
        {"title": "Inventory Analyst", "company": "Dovecote Freight", "url": "https://jobs.example/3",
         "text_screen": "cut", "cuts": json.dumps(['professional designation stated as a '
                                                   'requirement: "You must be ACCA qualified."'])},
        {"title": "Planner", "company": "Dovecote Freight", "url": "https://jobs.example/4",
         "text_screen": "pass", "cuts": "[]"}])
    _write(os.path.join(rd, "06_skipped.json"), [
        {"title": "Data Analyst", "company": "Brindle Hart Logistics", "url": "https://jobs.example/5",
         "skip_reason": "same-employer duplicate: Logistics Analyst scored higher this run (73 vs 68)"}])
    _write(os.path.join(rd, "06_shortlist.json"), [
        {"title": "Logistics Analyst", "company": "Brindle Hart Logistics",
         "url": "https://jobs.example/6", "fit": 73}])


def test_every_stage_that_filters_is_kept_with_its_rule_and_reason(tmp_path):
    rd, sd = str(tmp_path / "r7"), str(tmp_path / "summary")
    _round(rd)
    path = filtered.write(rd, sd, "r7")
    assert path == os.path.join(sd, "filtered", "r7.json")
    data = json.load(open(path, encoding="utf-8"))
    got = [(e["stage"], e["rule"], e["company"]) for e in data["filtered"]]
    assert got == [("search", "location", "Acme Analytics"),
                   ("already seen", "age (relist)", "Thornbury Bank"),
                   ("screen", "screen", "Dovecote Freight"),
                   ("throttle", "same-employer duplicate", "Brindle Hart Logistics")]
    relist = data["filtered"][1]
    assert relist["reason"] == RELIST and relist["url"] == "https://jobs.example/2"
    assert "ACCA" in data["filtered"][2]["reason"]
    assert data["counts"] == {"location": 1, "age (relist)": 1, "screen": 1,
                              "same-employer duplicate": 1}
    assert "desc" not in json.dumps(data) and "never kept" not in json.dumps(data)


def test_the_list_is_not_where_shortlists_are_read(tmp_path):
    # Every reader of documents/rounds/*.json takes each file there as a shortlist.
    rd, sd = str(tmp_path / "r7"), str(tmp_path / "summary")
    _round(rd)
    filtered.write(rd, sd, "r7")
    assert os.listdir(sd) == ["filtered"]


def test_a_round_writes_it_beside_its_summary(tmp_path):
    import round_fixture as rf
    work = str(tmp_path / "work")
    r = rf.free_stages(rf.KEPT, os.path.join(work, "r1"), work)
    assert r.returncode in (0, 2), r.stdout[-800:] + r.stderr[-800:]
    data = json.load(open(os.path.join(work, "summary", "filtered", "r1.json"), encoding="utf-8"))
    rules = {e["rule"] for e in data["filtered"]}
    assert {"age (relist)", "screen", "same-employer duplicate"} <= rules
    assert "filtered out:" in r.stdout


def test_bring_back_lifts_the_ruling_and_puts_it_on_the_shortlist(tmp_path):
    import exclude
    rd, sd = str(tmp_path / "r7"), str(tmp_path / "summary")
    _round(rd)
    _write(os.path.join(sd, "r7.json"), [{"title": "Logistics Analyst",
                                         "company": "Brindle Hart Logistics",
                                         "url": "https://jobs.example/6"}])
    filtered.write(rd, sd, "r7")
    seen = str(tmp_path / "seen_jobs.json")
    exclude.add("https://jobs.example/3", "screen: ACCA stated as a requirement",
                title="Inventory Analyst", company="Dovecote Freight", path=seen)
    [(e, rank)] = filtered.back("r7", ["Dovecote::inventory"], why="I am part-qualified",
                                round_dir=rd, summary_dir=sd, today="2026-10-25", seen_path=seen)
    assert rank == 2 and e["company"] == "Dovecote Freight"
    for path in (os.path.join(rd, "06_shortlist.json"), os.path.join(sd, "r7.json")):
        rows = json.load(open(path, encoding="utf-8"))
        assert rows[1]["url"] == "https://jobs.example/3"
        assert rows[1]["brought_back"].startswith("brought back 2026-10-25: filtered at the "
                                                  "screen (professional designation")
        assert rows[1]["brought_back"].endswith("; the person: I am part-qualified")
    entry = next(v for v in json.load(open(seen, encoding="utf-8"))["seen"].values())
    assert entry["status"] == "lifted"
    # Twice is once: the posting already on the shortlist keeps its rank.
    [(_, again)] = filtered.back("r7", ["3"], round_dir=rd, summary_dir=sd, seen_path=seen)
    assert again == 2 and len(json.load(open(os.path.join(sd, "r7.json"), encoding="utf-8"))) == 2


def test_a_relisted_posting_comes_back_by_its_link_and_stages(tmp_path):
    import stage_picks
    rd, sd = str(tmp_path / "r7"), str(tmp_path / "summary")
    _round(rd)
    filtered.write(rd, sd, "r7")
    [(e, rank)] = filtered.back("r7", ["https://jobs.example/2"], round_dir=rd, summary_dir=sd,
                                seen_path=str(tmp_path / "seen.json"))
    assert e["rule"] == "age (relist)" and rank == 2
    body = ("Thornbury Bank is hiring a Risk Analyst in Manchester to model credit risk in "
            "Python and SQL. Permanent, full time, hybrid.")
    [p] = stage_picks.stage(rd, [str(rank)], rows=[], fetch=lambda r: {"desc": body},
                            root=str(tmp_path))
    assert p["company"] == "Thornbury Bank" and p["role"] == "Risk Analyst"


def test_a_pick_that_is_not_one_posting_is_refused_with_the_candidates(tmp_path):
    rd, sd = str(tmp_path / "r7"), str(tmp_path / "summary")
    _round(rd)
    filtered.write(rd, sd, "r7")
    found = filtered.load("r7", sd)["filtered"]
    with pytest.raises(SystemExit, match=r"matched 2 postings \(Acme Analytics \| Data Analyst; "
                                         r"Brindle Hart Logistics \| Data Analyst\)"):
        filtered.find(found, "a::data analyst")
    with pytest.raises(SystemExit, match="outside the list"):
        filtered.find(found, "9")
    with pytest.raises(SystemExit, match="not a number"):
        filtered.find(found, "Dovecote")


def test_show_prints_the_list_numbered(tmp_path, monkeypatch, capsys):
    rd, sd = str(tmp_path / "r7"), str(tmp_path / "summary")
    _round(rd)
    filtered.write(rd, sd, "r7")
    monkeypatch.setattr(filtered, "_summary_dir", lambda: sd)
    assert filtered.main(["show", "r7", "--rule", "relist"]) == 0
    out = capsys.readouterr().out
    assert "round r7: 4 filtered out" in out
    assert "   2. Thornbury Bank | Risk Analyst | age (relist): " in out
    assert "Acme Analytics" not in out
    assert filtered.main([]) == 2
