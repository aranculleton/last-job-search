"""The allocator's lift reads the results once, and again when they change.

`allocate._wins()` asks `what_works.bullet_wins()` for the bullets of resumes
that reached an interview on every `bullet_scores` call. what_works caches that
per state root and never looks again, so a result recorded after the first
render in a process was never seen (the tests cleared the cache by hand). It is
now read once per process and again only when the tracker or a kept draft.json
changes on disk.
"""
from __future__ import annotations

import csv
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import allocate  # noqa: E402
import what_works  # noqa: E402

HEAD = ["date", "company", "role", "status", "cv_file", "notes"]


def _tracker(path, status):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=HEAD)
        w.writeheader()
        w.writerow({"date": "2026-09-01", "company": "Larkspur Retail", "role": "Analyst",
                    "status": status, "cv_file": "cv/Morgan_Ellis_CV_Larkspur.tex"})


def test_a_result_recorded_later_in_the_process_is_seen(tmp_path, monkeypatch):
    d = tmp_path / "documents" / "applications" / "larkspur_retail_analyst_larkspur"
    d.mkdir(parents=True)
    (d / "draft.json").write_text(json.dumps([{
        "company": "Larkspur Retail", "role": "Analyst", "abbr": "Larkspur",
        "jobs": [{"employer": "Brindle & Hart Logistics", "bullets": ["BH_FORECAST"]}]}]),
        encoding="utf-8")
    tracker = tmp_path / "job_search_tracker.csv"
    _tracker(tracker, "applied")
    monkeypatch.setenv("LJS_STATE", str(tmp_path))
    assert allocate._wins() == {}
    _tracker(tracker, "interview")
    st = os.stat(tracker)
    os.utime(tracker, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))
    assert allocate._wins() == {"BH_FORECAST": 1}


def test_unchanged_files_are_not_read_again(tmp_path, monkeypatch):
    monkeypatch.setenv("LJS_STATE", str(tmp_path))
    _tracker(tmp_path / "job_search_tracker.csv", "applied")
    calls = []
    real = what_works.bullet_wins
    monkeypatch.setattr(what_works, "bullet_wins", lambda: calls.append(1) or real())
    for _ in range(5):
        allocate.bullet_scores("forecasting")
    assert len(calls) == 1
