"""A portal failing part of its requests is a warning, never a stopped round.

The job-scraper skill: if a portal fails, log it and continue, do not abort the
whole search. scrape_wide exits 2, after writing its files, when more than a
quarter of the requests failed, and run_round treated that as a broken stage:
the round stopped and everything the other requests had found was thrown away.
"""
from __future__ import annotations

import os
import subprocess
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import run_round  # noqa: E402


def _round(tmp_path, monkeypatch, scrape_exit):
    calls = []

    def fake_run(cmd, **kw):
        calls.append(os.path.basename(cmd[1]))
        code = scrape_exit if os.path.basename(cmd[1]) == "scrape_wide.py" else 0
        return subprocess.CompletedProcess(cmd, code, "", "")

    monkeypatch.setattr(run_round, "subprocess", types.SimpleNamespace(
        run=fake_run, TimeoutExpired=subprocess.TimeoutExpired, call=lambda cmd: 0))
    monkeypatch.setattr(sys, "argv", ["run_round.py", "--out", str(tmp_path / "r1"),
                                      "--summary-dir", str(tmp_path / "summ")])
    return run_round.main(), calls


def test_a_partial_scrape_carries_on_with_a_warning(tmp_path, monkeypatch, capsys):
    code, calls = _round(tmp_path, monkeypatch, 2)              # scrape_wide: too many failed
    assert code == run_round.EXIT_YIELD_MISSED                 # a thin round, not a broken one
    assert calls[-1] == "throttle.py"
    said = capsys.readouterr().out
    assert "warning: more than a quarter of the portal requests failed" in said


def test_any_other_failure_still_stops_the_round(tmp_path, monkeypatch):
    import pytest
    with pytest.raises(SystemExit) as stop:
        _round(tmp_path, monkeypatch, 1)
    assert "stage failed: scrape_wide.py" in str(stop.value)
