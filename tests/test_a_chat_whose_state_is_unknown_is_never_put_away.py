"""A chat on the computer is put away only when its listing says it has finished.

The computer chat's clean-up read a listing with no state, or a state it did not know, as
finished: only "running", "working" and a few more kept a chat, so one waiting on a permission
prompt, one waiting for an answer, one paused, or one the person typed in between turns was
put away, and so was every chat in a list of titles alone (audit HC-2). Now only a state that
says the chat has finished (idle, done, completed and the like) lets it go; no state, or one
it does not know, keeps it. Invented titles.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import computer  # noqa: E402

JOB = "Job search · Find 10 people at Larkspur · Studio Laptop"


def _names(rows, set_up=True):
    return [r["title"] for r in computer.archivable(json.dumps(rows), set_up)]


def test_only_a_finished_state_lets_a_chat_go():
    for status in ("idle", "completed", "done", "finished", "SESSION_STATUS_IDLE", "stopped"):
        assert _names([{"title": JOB, "status": status}]) == [JOB], status
    for status in ("", "waiting", "needs input", "paused", "requires_action", "blocked",
                   "waiting for permission", "something new"):
        assert _names([{"title": JOB, "status": status}]) == [], status
    assert _names([{"title": JOB}]) == []


def test_a_list_of_titles_alone_puts_nothing_away():
    assert computer.archivable(f"- {JOB}\n- Holiday plans\n", True) == []
    assert computer.archivable([JOB], set_up=False) == []


def test_whole_words_recent_use_and_only_the_exact_setup_title():
    """Review of fix/helpers, item 7: "complete" matched inside "incomplete"; a chat idle
    between the person's turns was archived with no look at when it was last used; and the
    setup chat's pattern matched a chat the person had named."""
    import datetime as dt
    now = dt.datetime(2026, 11, 10, 12, 0, tzinfo=dt.timezone.utc)
    assert _names([{"title": JOB, "status": "incomplete"}]) == []
    rows = [{"title": JOB, "status": "idle", "updated_at": "2026-11-10T11:30:00Z"}]
    assert computer.archivable(json.dumps(rows), True, now=now) == []
    rows[0]["updated_at"] = "2026-11-10T06:00:00Z"
    assert len(computer.archivable(json.dumps(rows), True, now=now)) == 1
    named = [{"title": "Start my job search notes on this laptop", "status": "idle"},
             {"title": "Open job search on this Mac", "status": "idle"},
             {"title": "Open my job search on this computer", "status": "idle"}]
    assert _names(named) == ["Open my job search on this computer"]
