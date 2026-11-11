"""A chat that is archived already is done: nothing archives it again.

The maintainer's copy, 2026-11-10 (H-8): an old helper told to put itself away was archived
first by the new helper's tidy-up, and its own archive_session then hung for 1m 45s. Every path
that has a chat archive itself or another chat now looks at the chat's state first and takes
"archived" as done: the tidy-up's plan and close, a retired helper's last step and a finished
job chat's. Every id and title here is invented.
"""
from __future__ import annotations

import datetime as dt
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import app  # noqa: E402
import tidy  # noqa: E402

REPO = "example-owner/example-copy"
TODAY = dt.date(2026, 11, 10)
NOW = dt.datetime(2026, 11, 10, 12, 0, tzinfo=dt.timezone.utc)
LIVE = "session_EXAMPLEPAGEHELPER"
OLD = "session_EXAMPLEOLDHELPER"
JOB = "session_EXAMPLEJOBCHAT"


def _detail(sid, title, status="idle"):
    return {"id": sid, "title": title, "status": status, "session_context": {
        "sources": [{"git_repository": {"url": f"https://github.com/{REPO}"}}]}}


def _chat(sid, title, status):
    return {"id": sid, "title": title, "session_status": status,
            "created_at": "2026-11-01T08:00:00Z", "updated_at": "2026-11-08T08:00:00Z"}


def test_the_plan_never_names_an_archived_chat(monkeypatch):
    monkeypatch.setattr(tidy, "archived", lambda: [])
    listener = {"chat": LIVE, "helper": True}
    for listed, info in (
            ([_chat(OLD, "Job search page", "archived")], {}),
            ([_chat(OLD, "Job search page", "idle")],
             {OLD: _detail(OLD, "Job search page", status="archived")})):
        got = tidy.plan(listed, [], info, {}, listener, LIVE, REPO, TODAY, set(), set(), set(),
                        now=NOW)
        assert OLD not in [a["id"] for a in got["archive"]], got
        assert OLD not in got["ask"]
    # The same chat not archived yet is put away, as ever.
    got = tidy.plan([_chat(OLD, "Job search page", "idle")], [],
                    {OLD: _detail(OLD, "Job search page")}, {}, listener, LIVE, REPO, TODAY,
                    set(), set(), set(), now=NOW)
    assert OLD in [a["id"] for a in got["archive"]]


def test_close_takes_an_archived_job_chat_as_done():
    db = {"work": {"prep~1": {"data": {"kind": "prep", "status": "done"}, "version": 3}}}
    det = {JOB: _detail(JOB, "Job search: Interview prep", status="archived")}
    what, _said = tidy.close(JOB, "prep~1", db, det, {"chat": LIVE}, LIVE, REPO, set())
    assert what == "archived"


def test_a_chat_told_to_put_itself_away_looks_first():
    steps = app._next_job("https://claude.ai/code/artifact/example-page")
    assert steps.index("get_session") < steps.index("archive_session")
    assert "archived already" in steps
    import inspect
    src = inspect.getsource(app.cmd_retired)
    assert src.index("get_session") < src.index("archive_session")
