"""The helper that handed the page on puts itself away; the new one only records it.

`tidy.py retire` archived an old helper whose save branch GitHub never held, so its unsaved
work went with its container; a kept one wrote no stamp, so the tidy-up was due at every
check-in; and a chat get_session could not find was recorded as archived, so Undo would try to
bring back a deleted chat (review of fix/helpers, item 2). Decided: the old helper owns its own
archive (only it can see its unsaved work). The new helper records it once archived, records a
chat that is gone as gone, and archives it itself only after a day of quiet. Invented ids.
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import pytest  # noqa: E402

import tidy  # noqa: E402

REPO = "example-owner/example-copy"
LIVE = "session_EXAMPLENEWHELPER"
OLD = "session_EXAMPLEOLDHELPER"
NOW = dt.datetime(2026, 11, 10, 12, 0, tzinfo=dt.timezone.utc)
LISTENER = {"chat": LIVE, "helper": True, "took_from": OLD, "took_from_helper": True,
            "since": "2026-11-10T11:30:00Z"}


def _detail(status="idle", branch="", updated="2026-11-10T11:58:00Z"):
    return {"id": OLD, "title": "Job search page", "status": status, "updated_at": updated,
            "session_context": {"sources": [{"git_repository": {
                "url": f"https://github.com/{REPO}"}}], "outcomes": [{"git_repository": {
                    "git_info": {"branches": [branch] if branch else []}}}]}}


@pytest.mark.parametrize("detail", [_detail(), _detail(branch="claude/land-2026-11-10-1158")])
def test_an_old_helper_quiet_less_than_a_day_is_left_to_put_itself_away(detail):
    what, why = tidy.retire(OLD, detail, REPO, branches=set(), now=NOW)
    assert what == "keep" and "puts itself away" in why


def test_after_a_day_of_quiet_the_new_helper_archives_it():
    what, _ = tidy.retire(OLD, _detail(updated="2026-11-09T09:00:00Z"), REPO, branches=set(),
                          now=NOW)
    assert what == "archive"


@pytest.fixture
def run(tmp_path, monkeypatch, capsys):
    profile = tmp_path / "profile"
    profile.mkdir()
    monkeypatch.setattr(tidy, "_record_path", lambda: str(profile / "tidy.json"))
    monkeypatch.setattr(tidy, "_git_dir", lambda: str(tmp_path))
    monkeypatch.setattr(tidy, "_listener", lambda dump: LISTENER)
    monkeypatch.setattr(tidy, "_repo", lambda: REPO)
    monkeypatch.setattr(tidy, "unmerged", lambda: set())
    import app_listen
    monkeypatch.setattr(app_listen, "new_day", lambda rec, now: False)

    def go(detail, at="2026-11-10T11:31:00Z"):
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"details": detail})))
        tidy.run_retire(argparse.Namespace(dump="", stdin=True, details=[], now=at))
        return capsys.readouterr().out
    return go


def test_a_kept_old_helper_is_asked_about_again_only_after_half_an_hour(run):
    tidy._mark_checked("2026-11-10", "2026-11-10T09:00:00Z")
    db = {"meta": {}, "work": {}}
    t0 = dt.datetime(2026, 11, 10, 11, 31, tzinfo=dt.timezone.utc)
    assert tidy.due("2026-11-10", db=db, listener=LISTENER, now=t0)
    run(_detail(status="running"))
    assert not tidy.due("2026-11-10", db=db, listener=LISTENER, now=t0 + dt.timedelta(minutes=2))
    assert not tidy.retire_due(t0 + dt.timedelta(minutes=2))
    assert tidy.due("2026-11-10", db=db, listener=LISTENER, now=t0 + dt.timedelta(minutes=31))


def test_a_chat_get_session_cannot_find_is_recorded_as_gone_and_never_brought_back(run, capsys):
    run({"id": OLD, "gone": True})
    rows = tidy.archived()
    assert rows and rows[0]["id"] == OLD and rows[0].get("gone") is True
    assert tidy.retiring(LISTENER, NOW) == ""
    assert tidy.main(["undo"]) == 0
    assert "unarchive_session" not in capsys.readouterr().out
