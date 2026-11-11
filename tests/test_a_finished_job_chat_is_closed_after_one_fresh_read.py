"""A finished job's chat is closed after one fresh read of the page, never asked to read again.

`tidy.py close` judged a finished job's chat from a folder that lacked its work item and kept
it for a day; today's fix reads the page again first. But a fresh read that still lacks the
item (taken off the page) answered "read" again, for good, and the README still said a job's
chat messages the chat that answers the page, which archives it (audit HC-1). Now the read line
asks for the same command with --fresh, and from a fresh read a work item the page no longer
holds is a job that has ended. Every id and title here is invented.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import tidy  # noqa: E402

REPO = "example-owner/example-copy"
LIVE = "session_EXAMPLEPAGEHELPER"
JOB = "session_EXAMPLEJOBCHAT"
TITLE = "Job search: Interview prep: Larkspur Retail, Data Analyst"


def _detail():
    return {JOB: {"id": JOB, "title": TITLE, "session_context": {
        "sources": [{"git_repository": {"url": f"https://github.com/{REPO}"}}]}}}


def test_a_fresh_read_without_the_item_is_judged_not_read_again():
    db = {"work": {"other~1": {"data": {"kind": "network", "status": "done"}, "version": 1}}}
    assert tidy.close(JOB, "prep~1", db, _detail(), {"chat": LIVE}, LIVE, REPO, set())[0] == "read"
    what, said = tidy.close(JOB, "prep~1", db, _detail(), {"chat": LIVE}, LIVE, REPO, set(),
                            fresh=True)
    assert what == "archive" and said == TITLE


def test_the_read_line_asks_for_the_fresh_run(tmp_path, monkeypatch, capsys):
    import argparse
    monkeypatch.setattr(tidy, "_listener", lambda dump: {"chat": LIVE})
    monkeypatch.setattr(tidy, "_repo", lambda: REPO)
    monkeypatch.setattr(tidy, "unmerged", lambda: set())
    monkeypatch.setattr(tidy, "on_github", lambda: set())
    monkeypatch.setattr(tidy, "details", lambda pages: _detail())
    monkeypatch.setattr(tidy, "saves", lambda: {})
    import app_listen
    monkeypatch.setattr(app_listen, "this_chat", lambda chat="": LIVE)
    a = argparse.Namespace(id=JOB, work="prep~1", dump=str(tmp_path), details=[], chat=LIVE,
                           now="2026-11-10T12:00:00Z", fresh=False)
    assert tidy.run_close(a) == 0
    assert "--fresh" in capsys.readouterr().out


def test_the_docs_say_a_job_chat_puts_itself_away():
    readme = " ".join(open(os.path.join(ROOT, "automation", "README.md"),
                           encoding="utf-8").read().split())
    assert "that chat archives it at once" not in readme
    assert "puts itself away once its work is saved" in readme
    skill = " ".join(open(os.path.join(ROOT, ".claude", "skills", "app", "SKILL.md"),
                          encoding="utf-8").read().split())
    assert "the daily tidy archives it once its work is on master" not in skill


def test_a_wrong_id_never_archives_a_chat_still_at_work():
    """With --fresh a missing item read as "job ended", so a wrong --work id archived a chat
    still running and holding another item it had claimed (review of fix/helpers, item 4)."""
    running = {JOB: dict(_detail()[JOB], status="running")}
    db = {"work": {"prep~2": {"data": {"kind": "prep", "status": "running", "claimed_by": JOB},
                              "version": 3}}}
    assert tidy.close(JOB, "prep~1", db, running, {"chat": LIVE}, LIVE, REPO, set(),
                      fresh=True)[0] == "keep"
    idle = _detail()
    what, why = tidy.close(JOB, "prep~1", db, idle, {"chat": LIVE}, LIVE, REPO, set(), fresh=True)
    assert what == "keep" and "prep~2" in why


def test_a_job_chat_running_a_second_job_under_the_starters_id_is_kept():
    """The engine review of 2026-11-11: a job's chat runs its jobs under the id of the chat that
    started it, with `run_by` its own. close read only `claimed_by`, so a chat that reported its
    first job while blocked on an approval part way through its second was put away at work."""
    db = {"work": {
        "prep~1": {"data": {"kind": "prep", "status": "done", "claimed_by": LIVE, "run_by": JOB,
                            "finished_at": "2026-11-11T08:00:00Z"}, "version": 4},
        "prep~2": {"data": {"kind": "prep", "status": "running", "claimed_by": LIVE,
                            "run_by": JOB, "blocked_at": "2026-11-11T08:20:00Z"}, "version": 6}}}
    idle = _detail()
    what, why = tidy.close(JOB, "prep~1", db, idle, {"chat": LIVE}, LIVE, REPO, set())
    assert what == "keep" and "prep~2" in why, (what, why)
    # Waiting on an approval with nothing else held: still at work, never put away.
    blocked = {JOB: dict(_detail()[JOB], status_bucket="blocked")}
    done = {"work": {"prep~1": db["work"]["prep~1"]}}
    assert tidy.close(JOB, "prep~1", done, blocked, {"chat": LIVE}, LIVE, REPO, set())[0] == "keep"
    assert tidy.close(JOB, "prep~1", done, idle, {"chat": LIVE}, LIVE, REPO, set())[0] == "archive"
