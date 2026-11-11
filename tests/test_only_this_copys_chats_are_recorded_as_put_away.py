"""Only this copy's chats are recorded as put away when they are found archived.

The tidy-up recorded every archived chat with an app title, another copy's and ones archived
months ago among them, and Undo would bring them all back (review of fix/helpers, item 3; the
reviewer's probe). It records the helper taken over from, the page's own job chats and helpers,
and a chat of this copy used within the week. Invented ids.
"""
from __future__ import annotations

import datetime as dt
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import routines  # noqa: E402
import tidy  # noqa: E402

REPO = "example-owner/example-copy"
LIVE = "session_EXAMPLENEWHELPER"
NOW = dt.datetime(2026, 11, 10, 12, 0, tzinfo=dt.timezone.utc)


def _info(sid, repo):
    return {"id": sid, "session_context": {"sources": [{"git_repository": {
        "url": f"https://github.com/{repo}"}}]}}


def test_only_this_copys_recent_chats_are_recorded(monkeypatch):
    monkeypatch.setattr(routines, "trusted_chat", lambda: "")
    monkeypatch.setattr(tidy, "archived", lambda: [])
    chats = [{"id": LIVE, "title": "Job search page", "session_status": "running"},
             {"id": "session_EXAMPLEOTHERCOPY", "title": "Job search · Read 10 profiles · Mac",
              "session_status": "archived", "updated_at": "2026-11-09T08:00:00Z"},
             {"id": "session_EXAMPLEMONTHSAGO", "title": "Job search: drafts",
              "session_status": "archived", "updated_at": "2026-06-01T08:00:00Z"},
             {"id": "session_EXAMPLEOURS", "title": "Job search: drafts",
              "session_status": "archived", "updated_at": "2026-11-09T08:00:00Z"}]
    info = {"session_EXAMPLEOTHERCOPY": _info("session_EXAMPLEOTHERCOPY", "example-owner/another"),
            "session_EXAMPLEMONTHSAGO": _info("session_EXAMPLEMONTHSAGO", REPO),
            "session_EXAMPLEOURS": _info("session_EXAMPLEOURS", REPO)}
    got = tidy.plan(chats, [], info, {"routines": []}, {"chat": LIVE, "helper": True}, LIVE,
                    REPO, NOW.date(), set(), set(), set(), now=NOW, on_github=set())
    assert [g["id"] for g in got["gone"]] == ["session_EXAMPLEOURS"], got["gone"]
