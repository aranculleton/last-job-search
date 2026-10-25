"""`run_round.py --no-seen-read` really does judge every past exclusion again.

It is the switch for after the scoring rules change. The prefilter honoured it,
and the throttle applied every past ruling at the end of the round anyway, so a
round run with it re-scored nothing: each previously excluded posting was
fetched, screened and scored, and then skipped as "already ruled out".
"""
from __future__ import annotations

import pytest
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import prefilter  # noqa: E402

URL = "https://careers.example.com/jobs/311"
ROW = {"url": URL, "title": "Inventory Analyst", "company": "Larkspur Retail",
       "location": "Bolton, England, United Kingdom", "fit": 81, "priority": 77,
       "date": "2026-10-13"}


def _seen(tmp_path):
    seen = tmp_path / "seen.json"
    seen.write_text(json.dumps({"seen": {URL: {
        "url": URL, "title": "Inventory Analyst", "company": "Larkspur Retail",
        "status": "excluded", "excluded_date": "2026-09-01",
        "exclusion_reason": "eligibility gate: British nationality or a security clearance "
                            "stated as a condition: \"SC clearance required\""}}}))
    return seen


def _throttle(tmp_path, *extra):
    src, out = tmp_path / "ranked.json", tmp_path / "short.json"
    src.write_text(json.dumps([ROW]))
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "throttle.py"), str(src),
                        "--out", str(out), "--seen", str(_seen(tmp_path)), "--today",
                        "2026-10-14", "--no-write", "--tracker", str(tmp_path / "none.csv"),
                        *extra], capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode == 0, r.stderr
    return [j["url"] for j in json.loads(out.read_text())]


def test_a_ruled_out_posting_resurfaces_when_everything_is_judged_again(tmp_path):
    assert _throttle(tmp_path) == []
    assert _throttle(tmp_path, "--keep-ruled-out") == [URL]


def test_the_prefilter_keeps_it_too_and_still_ages_it(tmp_path):
    seen = str(_seen(tmp_path))
    assert prefilter.already_ruled_out(seen)(ROW)
    assert prefilter.already_ruled_out(seen, keep_ruled_out=True)(ROW) == ""


def test_the_round_passes_it_to_both_and_still_reads_first_sightings(tmp_path, monkeypatch):
    import run_round
    stages = []
    monkeypatch.setattr(run_round, "run", lambda cmd, log, deadline=None, ok=(0,): stages.append(cmd))
    scraped = tmp_path / "scraped.json"
    scraped.write_text("[]")
    monkeypatch.setattr(sys, "argv", ["run_round.py", "--out", str(tmp_path / "r1"),
                                      "--from-scraped", str(scraped), "--no-seen-read",
                                      "--summary-dir", str(tmp_path / "summ")])
    run_round.main()
    by = {os.path.basename(c[1]): c for c in stages}
    assert "--keep-ruled-out" in by["prefilter.py"] and "--seen" in by["prefilter.py"]
    assert "--keep-ruled-out" in by["throttle.py"]


@pytest.fixture(autouse=True)
def _no_rescreen(monkeypatch):
    """These pin how a ruling holds. Whether a better screen re-judges it is
    tests/test_build_versions.py's, so the app's own re-run versions are held off."""
    monkeypatch.setenv("LJS_RESCREEN", "off")


def test_the_prefilter_reads_the_seen_file_once(tmp_path, monkeypatch):
    # The ruled-out gate and the first-sighting reader each loaded seen_jobs.json, which
    # runs to megabytes in a long-lived repo.
    import json
    import prefilter
    src, seen = tmp_path / "in.json", tmp_path / "seen.json"
    src.write_text(json.dumps([{"title": "Data Analyst", "company": "Oakmere Foods",
                                "location": "Manchester", "url": "https://x.example/1",
                                "date": "2026-10-18"}]))
    seen.write_text(json.dumps({"seen": {}}))
    loads = []
    real = prefilter._seen_entries
    monkeypatch.setattr(prefilter, "_seen_entries", lambda p: loads.append(p) or real(p))
    monkeypatch.setattr(sys, "argv", ["prefilter.py", str(src), "--out", str(tmp_path / "k.json"),
                                      "--today", "2026-10-20", "--seen", str(seen)])
    prefilter.main()
    assert loads == [str(seen)]
