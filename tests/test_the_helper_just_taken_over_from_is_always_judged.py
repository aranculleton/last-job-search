"""The tidy-up always judges the helper this chat just took the page over from.

The maintainer's copy, 2026-11-10 (H-1): right after a hand-over the tidy-up printed "nothing to
tidy" while the old helper was still open, its save already merged. The page's record named
it, but the session list the chat passed was cut down, and the plan judged only the chats in
that list: it asked about the brief's chat and never about the old helper. Now the helper the
record says it took over from is read with get_session when the list lacks it, put away once it
can be, and a run that keeps it for now says so rather than "nothing to tidy". Invented ids.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import tidy  # noqa: E402

REPO = "example-owner/example-copy"
TODAY = dt.date(2026, 11, 10)
NOW = dt.datetime(2026, 11, 10, 12, 0, tzinfo=dt.timezone.utc)
LIVE = "session_EXAMPLENEWHELPER"
OLD = "session_EXAMPLEOLDHELPER"
LISTENER = {"chat": LIVE, "helper": True, "took_from": OLD, "took_from_helper": True,
            "since": "2026-11-10T11:30:00Z"}


def _detail(sid, title="Job search page", status="idle"):
    return {"id": sid, "title": title, "status": status,
            "updated_at": "2026-11-10T11:20:00Z", "session_context": {
                "sources": [{"git_repository": {"url": f"https://github.com/{REPO}"}}]}}


def _plan(chats, info, monkeypatch):
    monkeypatch.setattr(tidy, "archived", lambda: [])
    return tidy.plan(chats, [], info, {}, LISTENER, LIVE, REPO, TODAY, set(), set(), set(),
                     now=NOW)


def test_a_list_that_lacks_the_old_helper_asks_for_it_then_puts_it_away(monkeypatch):
    brief_chat = {"id": "session_EXAMPLEBRIEF", "title": "Job search: morning brief"}
    got = _plan([brief_chat], {}, monkeypatch)
    assert OLD in got["ask"], got
    got = _plan([brief_chat], {OLD: _detail(OLD)}, monkeypatch)
    # Judged: it puts itself away (review of fix/helpers, item 2), and after a day of quiet
    # this chat does.
    assert {k["id"]: k["why"] for k in got["keep"]}[OLD] == \
        "it puts itself away once its work is saved", got
    got = _plan([brief_chat], {OLD: dict(_detail(OLD), updated_at="2026-11-09T08:00:00Z")},
                monkeypatch)
    assert OLD in [a["id"] for a in got["archive"]], got


def test_kept_for_now_it_is_said_never_nothing_to_tidy(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(tidy, "_git_dir", lambda: str(tmp_path))
    monkeypatch.setattr(tidy, "archived", lambda: [])
    monkeypatch.setattr(tidy, "_listener", lambda dump: LISTENER)
    monkeypatch.setattr(tidy, "_repo", lambda: REPO)
    monkeypatch.setattr(tidy, "unmerged", lambda: set())
    monkeypatch.setattr(tidy, "on_github", lambda: set())
    monkeypatch.setattr(tidy, "_campaign_chats", lambda: set())
    import app_listen
    import app_setup
    import routines
    monkeypatch.setattr(app_listen, "this_chat", lambda chat="": LIVE)
    monkeypatch.setattr(app_listen, "nested", lambda chat: False)
    monkeypatch.setattr(app_setup, "doorbells_due", lambda today: False)
    monkeypatch.setattr(routines, "load", lambda *a, **k: {})
    monkeypatch.setattr(routines, "saw", lambda tasks: None)
    details = tmp_path / "d.json"
    details.write_text(json.dumps(_detail(OLD, status="running")), encoding="utf-8")
    a = argparse.Namespace(today="", now="2026-11-10T12:00:00Z", stdin=False, triggers=[],
                           sessions=[], details=[str(details)], dump="", chat=LIVE,
                           verbose=False)
    assert tidy.run_plan(a) == 0
    out = capsys.readouterr().out
    assert "nothing to tidy" not in out
    assert OLD in out and "kept for now" in out
