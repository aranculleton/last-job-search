"""The build's own checks read the tracker the way every state file is read.

A tracker saved by a spreadsheet in Windows' own encoding crashed the check for unsent
drafts, which read it as UTF-8 alone (2026-10-25).
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import build_versions  # noqa: E402
import person  # noqa: E402


def test_a_tracker_saved_in_windows_encoding_is_read(tmp_path, monkeypatch):
    (tmp_path / "job_search_tracker.csv").write_bytes(
        "company,role,status\nCafé Brûlé,Analyst,drafted\n".encode("cp1252"))
    monkeypatch.setenv(person.STATE_ENV, str(tmp_path))
    assert build_versions._tracker_statuses() == {"drafted"}
    assert build_versions._has_rows(str(tmp_path / "job_search_tracker.csv"))
    assert not build_versions._has_rows(str(tmp_path / "missing.csv"))
