"""A day's brief counts as come only once its record is on the saved copy.

The brief's task said SUCCEEDED in 16 ms (only the wake was delivered), and the check that a
brief did not come read the day's record from the folder, so a run that wrote it and never
saved it, or wrote it under the wrong day, passed (audit BT-12). The check now reads the
records the saved copy holds (any branch of it on GitHub, so a save still waiting counts),
and the folder only where there is no saved copy to read. A local git origin, invented days.
"""
from __future__ import annotations

import datetime as dt
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import routines  # noqa: E402

REG = {"setup": "chat_per_briefing", "timezone": "Europe/London", "routines": [
    {"key": "morning_brief", "name": routines.BRIEF_NAME, "trigger_id": "trig_EXAMPLEB",
     "cron": "CRON_TZ=Europe/London 1 8 * * *", "prompt_file": routines.BRIEF_FILE,
     "made": "2026-11-01", "chat": {"session_id": "session_EXAMPLEBRIEFCHAT", "own": True}}]}
NOW = dt.datetime(2026, 11, 10, 12, 0, tzinfo=dt.timezone.utc)


def git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


def test_a_record_written_but_never_saved_is_a_brief_that_did_not_come(tmp_path, monkeypatch):
    for k, v in (("GIT_AUTHOR_NAME", "t"), ("GIT_AUTHOR_EMAIL", "t@example.com"),
                 ("GIT_COMMITTER_NAME", "t"), ("GIT_COMMITTER_EMAIL", "t@example.com")):
        monkeypatch.setenv(k, v)
    state = tmp_path / "state"
    briefs = state / "documents" / "briefs"
    briefs.mkdir(parents=True)
    (briefs / "2026-11-09.md").write_text("# Brief, 2026-11-09\n", encoding="utf-8")
    origin = tmp_path / "origin.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "master", str(origin))
    git(state, "init", "-q", "-b", "master")
    git(state, "add", "-A")
    git(state, "commit", "-q", "-m", "saved")
    git(state, "remote", "add", "origin", str(origin))
    git(state, "push", "-q", "origin", "master")
    git(state, "fetch", "-q", "origin")
    # Today's written, never saved.
    (briefs / "2026-11-10.md").write_text("# Brief, 2026-11-10\n", encoding="utf-8")
    monkeypatch.setenv("LJS_STATE", str(state))
    assert routines._brief_days_on_file() == {"2026-11-09"}
    assert routines.overdue(REG, NOW) == "2026-11-10"
    # Saved on a branch of its own, waiting to land: it came.
    git(state, "switch", "-q", "-c", "claude/ops-2026-11-10-morning_brief")
    git(state, "add", "-A")
    git(state, "commit", "-q", "-m", "Brief 2026-11-10")
    git(state, "push", "-q", "origin", "claude/ops-2026-11-10-morning_brief")
    git(state, "fetch", "-q", "origin")
    assert routines.overdue(REG, NOW) == ""


def test_with_no_saved_copy_the_folder_is_read(tmp_path, monkeypatch):
    briefs = tmp_path / "documents" / "briefs"
    briefs.mkdir(parents=True)
    (briefs / "2026-11-10.md").write_text("# Brief\n", encoding="utf-8")
    monkeypatch.setenv("LJS_STATE", str(tmp_path))
    assert routines._brief_days_on_file() == {"2026-11-10"}
