"""Each test starts with none of the checkout's own records another test left.

The suite gives each worker one state folder for its whole run. A checkout keeps its own
records there when the folder is not a git checkout (app_listen.checkout_file: what it last
saw of the page's listener, when it last asked for a fresh helper, the chats marked nested or
handed on), so one test's record was the next test's in the same worker. Under load the
tests were dealt out differently, and a renewal another test had marked made "a helper is a
fresh chat once a day" find none, and a test that popped LJS_PROFILE left the next with no
profile at all: test_one_chat_answers_the_page.py failed beside others and passed alone. The
suite's autouse fixture clears them before every test (conftest.clean_start). One test, so it
never depends on how a run deals tests to workers (review of fix/helpers, item 16).
"""
from __future__ import annotations

import datetime as dt
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import app_listen  # noqa: E402
import conftest  # noqa: E402


def test_what_one_test_leaves_the_next_does_not_find(monkeypatch):
    # What one test leaves behind: a renewal marked, a chat marked nested, the profile popped.
    got = app_listen.seen()
    got["renewed_at"] = "2026-11-10T08:00:00Z"
    got["nested"] = {"session_EXAMPLEDEEP": "2026-11-10T08:00:00Z"}
    app_listen._save_seen(got)
    os.environ.pop("LJS_PROFILE", None)
    # What the next test starts with.
    conftest.clean_start()
    assert app_listen.seen() == {}
    assert not app_listen.nested("session_EXAMPLEDEEP")
    assert os.environ.get("LJS_PROFILE") == os.path.join(ROOT, "profile.example")
    # So a renewal a day on is asked for, as in test_one_chat_answers_the_page.py.
    monkeypatch.setattr(app_listen, "chat_kind", lambda: "cloud")
    monkeypatch.setattr(app_listen, "_zone", lambda: "UTC")
    monkeypatch.setattr(app_listen, "history_tokens", lambda: 0)
    import app_setup
    monkeypatch.setattr(app_setup, "origin", lambda: ("example-owner", "my-job-search"))
    rec = {"chat": "session_EXAMPLEOLD", "kind": "cloud", "helper": True,
           "since": "2026-10-30T08:00:00Z", "answered_at": "2026-10-30T11:00:00Z"}
    db = {"meta": {"listener": {"data": rec, "version": 3}}, "work": {}}
    now = dt.datetime(2026, 10, 31, 7, 0, tzinfo=dt.timezone.utc)
    assert app_listen.renewal(rec, db, "session_EXAMPLEOLD", now)
