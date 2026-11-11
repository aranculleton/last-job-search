"""A chat of the app's archived by any chat, or by hand, is recorded as put away.

Only archives the tidy-up made reached profile/tidy.json. An old helper archived by itself or
by hand was never recorded, so the tidy-up stayed due every half hour for the rest of the day,
the fresh helper's renewal waited on it, and Undo could not bring it back (second audit A2,
A5, root R1). The tidy-up now records every chat of the app's it finds archived already, with
its title. Invented ids and titles.
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
LIVE = "session_EXAMPLENEWHELPER"
OLD = "session_EXAMPLEOLDHELPER"
NOW = "2026-11-10T12:00:00Z"
LISTENER = {"chat": LIVE, "helper": True, "took_from": OLD, "took_from_helper": True,
            "since": "2026-11-10T11:30:00Z"}


def test_an_old_helper_archived_elsewhere_is_recorded_and_the_tidy_up_rests(
        monkeypatch, tmp_path, capsys):
    profile = tmp_path / "profile"
    profile.mkdir()
    monkeypatch.setattr(tidy, "_record_path", lambda: str(profile / "tidy.json"))
    monkeypatch.setattr(tidy, "_git_dir", lambda: str(tmp_path))
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
    now = dt.datetime(2026, 11, 10, 12, 0, tzinfo=dt.timezone.utc)
    assert tidy.retiring(LISTENER, now) == OLD
    sessions = tmp_path / "s.json"
    sessions.write_text(json.dumps({"data": [
        {"id": OLD, "title": "Job search page", "session_status": "archived"},
        {"id": LIVE, "title": "Job search page", "session_status": "running"}]}),
        encoding="utf-8")
    a = argparse.Namespace(today="", now=NOW, stdin=False, triggers=[], sessions=[str(sessions)],
                           details=[], dump="", chat=LIVE, verbose=False)
    assert tidy.run_plan(a) == 0
    out = capsys.readouterr().out
    assert f"archive {OLD}" not in out
    rows = json.loads((profile / "tidy.json").read_text(encoding="utf-8"))["archived"]
    assert [(r["id"], r["title"]) for r in rows] == [(OLD, "Job search page")]
    # Recorded, it is no longer the helper still to put away, and Undo knows it.
    assert tidy.retiring(LISTENER, now) == ""
    assert OLD in {x["id"] for x in tidy.archived()}
