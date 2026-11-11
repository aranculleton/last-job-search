"""After a hand-over, the helper taken over from is put away from one get_session, not a listing.

Right after every hand-over the tidy-up asked the chat to type back every chat and every
scheduled task of the account, some 60 and 20, into one command: slow, costly, and cut short by
hand, which changed what the plan decided (H-4; second audit A6, root R3). The old helper is
now judged from one get_session of it, the one chat the page's record names: `tidy.py retire`.
The daily sweep keeps the full listing. Invented ids.
"""
from __future__ import annotations

import argparse
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
LISTENER = {"chat": LIVE, "helper": True, "took_from": OLD, "took_from_helper": True,
            "since": "2026-11-10T11:30:00Z"}


def _detail(status="idle", repo=REPO, branch="", updated="2026-11-10T11:00:00Z"):
    return {"id": OLD, "title": "Job search page", "status": status, "updated_at": updated,
            "session_context": {"sources": [{"git_repository": {
                "url": f"https://github.com/{repo}"}}], "outcomes": [{"git_repository": {
                    "git_info": {"branches": [branch] if branch else []}}}]}}


@pytest.fixture
def setup(monkeypatch, tmp_path):
    profile = tmp_path / "profile"
    profile.mkdir()
    monkeypatch.setattr(tidy, "_record_path", lambda: str(profile / "tidy.json"))
    monkeypatch.setattr(tidy, "_git_dir", lambda: str(tmp_path))
    monkeypatch.setattr(tidy, "_listener", lambda dump: LISTENER)
    monkeypatch.setattr(tidy, "_repo", lambda: REPO)
    monkeypatch.setattr(tidy, "unmerged", lambda: {"claude/land-unsaved"})
    return tmp_path


def _retire(monkeypatch, capsys, detail):
    if detail is not None:
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"details": detail})))
    a = argparse.Namespace(dump="", stdin=detail is not None, details=[],
                           now="2026-11-10T12:00:00Z")
    assert tidy.run_retire(a) == 0
    return capsys.readouterr().out


def test_it_asks_for_the_one_chat_then_puts_it_away(setup, monkeypatch, capsys):
    out = _retire(monkeypatch, capsys, None)
    assert f"get_session (session_id {OLD})" in out and "list_sessions" not in out
    out = _retire(monkeypatch, capsys, _detail())
    # It puts itself away (review of fix/helpers, item 2); a day quiet, this chat does.
    assert "archive_session" not in out and "puts itself away" in out
    out = _retire(monkeypatch, capsys, _detail(updated="2026-11-09T08:00:00Z"))
    assert f'archive_session {{"session_id": "{OLD}"}}' in out
    assert f"tidy.py closed {OLD}" in out


@pytest.mark.parametrize("detail, why", [
    (_detail(status="running"), "kept for now"),
    (_detail(branch="claude/land-unsaved"), "kept for now"),
    (_detail(repo="example-owner/another-copy"), "kept"),
])
def test_one_still_at_work_or_unsaved_is_kept_and_nothing_archived_by_hand(
        setup, monkeypatch, capsys, detail, why):
    out = _retire(monkeypatch, capsys, detail)
    assert "archive_session" not in out and why in out
    assert "archive nothing by hand" in out


def test_one_archived_already_is_recorded_and_the_hand_over_is_done(setup, monkeypatch, capsys):
    out = _retire(monkeypatch, capsys, _detail(status="archived"))
    assert "archive_session" not in out
    assert OLD in {x["id"] for x in tidy.archived()}


def test_the_hand_over_step_asks_for_one_read():
    import app
    said = app.TIDY_NOW.format(old=OLD)
    assert f"get_session (session_id {OLD})" in said and "tidy.py retire" in said
    assert "list_sessions" not in said and "list_triggers" not in said
