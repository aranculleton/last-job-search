"""A helper as deep as chats go is marked so at its check-in, not after a refused call.

Each helper starts the next, one level deeper a day, and the platform refuses a chat past its
limit (lineage {"depth": 8, "limit": 8}); the app learned it only from a refused
create_session, a wasted turn on a long chat, though get_session says so (second audit A9).
`listen --lineage <depth>/<limit>`, from that get_session, marks it nested at once, in this
checkout and on the page's record, so its big jobs run as background agents and the brief's
next run starts its fresh helper. Invented ids.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import pytest  # noqa: E402

import app_listen  # noqa: E402

NOW = dt.datetime(2026, 11, 10, 9, 0, tzinfo=dt.timezone.utc)
ME = "session_EXAMPLEDEEPHELPER"


@pytest.mark.parametrize("given", ["8/8", '{"depth": 8, "limit": 8}', "9/8"])
def test_a_chat_at_its_limit_is_nested_at_once(tmp_path, monkeypatch, given):
    monkeypatch.setattr(app_listen, "chat_kind", lambda: "cloud")
    rec = {"chat": ME, "kind": "cloud", "helper": True, "since": "2026-11-10T08:00:00Z",
           "answered_at": "2026-11-10T08:30:00Z"}
    db = {"meta": {"listener": {"data": rec, "version": 3}}, "work": {}}
    got = app_listen.decide(db, ME, str(tmp_path / "out"), NOW, helper=True,
                            lineage=app_listen.read_lineage(given))
    assert app_listen.nested(ME)
    (batch,) = got["batches"]
    (entry,) = json.load(open(batch, encoding="utf-8"))
    body = json.load(open(entry["file_path"], encoding="utf-8"))
    assert body.get("nested_at")
    assert any("as deep as chats go" in ln for ln in got["lines"])


def test_a_chat_below_its_limit_is_not(tmp_path, monkeypatch):
    monkeypatch.setattr(app_listen, "chat_kind", lambda: "cloud")
    rec = {"chat": ME, "kind": "cloud", "helper": True, "since": "2026-11-10T08:00:00Z"}
    db = {"meta": {"listener": {"data": rec, "version": 3}}, "work": {}}
    app_listen.decide(db, ME, str(tmp_path / "out"), NOW, helper=True,
                      lineage=app_listen.read_lineage("3/8"))
    assert not app_listen.nested(ME)
    assert app_listen.read_lineage("") is None and app_listen.read_lineage("deep") is None


def test_the_listen_command_takes_it():
    import subprocess
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "app.py"), "listen", "--help"],
                       capture_output=True, text=True, encoding="utf-8")
    assert "--lineage" in r.stdout
