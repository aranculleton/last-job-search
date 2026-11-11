"""In a cloud chat the job sites are probed once on the day's first start, not twice.

Audit E-17 (2026-11-10): the start probed every job site (app_setup.check_job_sites) and the
day's update check, in a process of its own, probed them all again (sync_app.network_check,
env_check --say). The check reads the record the start keeps when it was made today, and
makes it when it was not. Invented data only.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import app_setup  # noqa: E402
import env_check  # noqa: E402


def test_one_probe_a_day_whichever_asks_first(tmp_path, monkeypatch, capsys):
    probes = []
    monkeypatch.setenv("CLAUDE_CODE_REMOTE", "true")
    monkeypatch.setattr(app_setup, "_git_dir", lambda: str(tmp_path))
    monkeypatch.setattr(env_check, "blocked_names", lambda: probes.append(1) or ["Example Board"])
    assert app_setup.check_job_sites()["blocked"] == ["Example Board"]
    assert env_check.main(["--say", "--today"]) == 0
    assert len(probes) == 1, "the update check read the start's record"
    assert "Example Board" in capsys.readouterr().out
    # The update check first, the start after: one probe again.
    (tmp_path / app_setup.JOB_SITES).unlink()
    assert env_check.main(["--say", "--today"]) == 0
    assert app_setup.job_sites()["blocked"] == ["Example Board"] and len(probes) == 2


def test_asked_by_hand_the_sites_are_probed_now(tmp_path, monkeypatch, capsys):
    """The review of E-17 (2026-11-11): the morning's record answered every --say, the
    job-scraper skill's "board unreachable" step and SETUP.md's included, so a block that
    appeared or was fixed mid-day was misreported. Only the update check's own look reads it."""
    import sync_app
    probes = []
    monkeypatch.setenv("CLAUDE_CODE_REMOTE", "true")
    monkeypatch.setattr(app_setup, "_git_dir", lambda: str(tmp_path))
    monkeypatch.setattr(env_check, "blocked_names", lambda: probes.append(1) or [])
    app_setup.check_job_sites()
    assert env_check.main(["--say"]) == 0 and len(probes) == 2, "probed again, live"
    src = open(sync_app.__file__, encoding="utf-8").read()
    assert '"--say", "--today"' in src


def test_the_steps_to_reach_job_sites_carry_the_page_to_check_today(monkeypatch, capsys):
    """The review of E-13 (2026-11-11): the steps were pasted with no check, against the rule
    that another company's steps are checked against their official page that day."""
    import claude_surfaces
    monkeypatch.setenv("CLAUDE_CODE_REMOTE", "true")
    monkeypatch.setattr(env_check, "blocked_names", lambda: ["Example Board"])
    assert env_check.main(["--say"]) == 0
    err = capsys.readouterr().err
    page = claude_surfaces.official(claude_surfaces.entry("cloud-internet"))
    assert page and page in err and "check it today" in err, err


def test_the_starts_one_line_about_auto_carries_the_page_to_check_today(monkeypatch):
    import claude_surfaces
    monkeypatch.setattr(app_setup, "_cloud", lambda: True)
    monkeypatch.setattr(app_setup, "told", lambda key: False)
    import report
    monkeypatch.setattr(report, "stuck", lambda st=None: [])
    said = app_setup._said_once({"page": {}}, no_page=False)
    page = claude_surfaces.official(claude_surfaces.entry("cloud-auto"))
    assert page in said and "check it today" in said and "I could not check this today" in said
