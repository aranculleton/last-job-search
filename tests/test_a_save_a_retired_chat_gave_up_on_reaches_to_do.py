"""A save a retired chat gave up on reaches the person as one To do card, until it is saved.

A helper that handed the page on stops trying to save after two tries that never reached
GitHub, and leaves its chat as it is (HC-3); until now nothing told the person, so its last
work could sit there unsaved until the chat was put away (audit HC-3). The retired chat now
writes a small record of it onto the page (meta/unsaved-<chat>), and the next page update, by
any chat, shows one To do card from it, plain, with no button: it goes by itself once that
work is on GitHub, or after a fortnight. Invented ids.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import app  # noqa: E402
import app_listen  # noqa: E402
import app_model  # noqa: E402

CHAT = "session_EXAMPLERETIREDHELPER"
NOW = dt.datetime(2026, 11, 10, 12, 0, tzinfo=dt.timezone.utc)


def test_giving_up_writes_the_record_onto_the_page(tmp_path, monkeypatch, capsys):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    monkeypatch.setenv("LJS_STATE", str(tmp_path))
    monkeypatch.setattr(app_listen, "retired_here", lambda chat: True)
    monkeypatch.setattr(app_listen, "this_chat", lambda chat="": chat or CHAT)
    monkeypatch.setattr(app, "_saved_on_github", lambda root: False)
    for _ in range(app.RETIRED_TRIES + 1):
        app.cmd_retired(argparse.Namespace(chat=CHAT, wait=False))
    out = capsys.readouterr().out.split("did not reach GitHub after two tries", 1)[1]
    batch = next(ln.strip() for ln in out.splitlines() if ln.strip().endswith(".json"))
    (entry,) = json.load(open(batch, encoding="utf-8"))
    assert entry["collection"] == "meta" and entry["doc_id"] == "unsaved-" + CHAT
    body = json.load(open(entry["file_path"], encoding="utf-8"))
    assert body["chat"] == CHAT and body["since"]


def _record(since="2026-11-10T11:00:00Z", head="abc123"):
    return {"chat": CHAT, "title": "Job search page", "since": since, "head": head}


def test_the_next_page_update_shows_one_card_until_it_is_saved(monkeypatch):
    import app_setup
    monkeypatch.setattr(app_setup, "outside_items", lambda targets, kind: [])
    model, targets = app_model.build(NOW.date(), NOW, unsaved=[_record()])
    todo = [x for x in model["needs_you"] if x["id"].startswith("q-unsaved")]
    assert len(todo) == 1, todo
    card = todo[0]
    assert card["options"] == [] and "Job search page" in card["body"]
    assert "could not be saved" in card["body"]
    assert targets[card["id"]]["kind"] == "outside"
    model, _ = app_model.build(NOW.date(), NOW, unsaved=[])
    assert not [x for x in model["needs_you"] if x["id"].startswith("q-unsaved")]


def test_a_record_saved_since_or_a_fortnight_old_goes(monkeypatch):
    db = {"meta": {"unsaved-" + CHAT: {"data": _record(), "version": 1},
                   "unsaved-session_EXAMPLEOLD": {"data": dict(_record(), chat="session_EXAMPLEOLD",
                                                               since="2026-10-20T08:00:00Z"),
                                                  "version": 2}}}
    monkeypatch.setattr(app, "_on_github_sha", lambda sha: False)
    show, gone = app.unsaved_saves(db, NOW)
    assert [r["chat"] for r in show] == [CHAT] and gone == [("unsaved-session_EXAMPLEOLD", 2)]
    monkeypatch.setattr(app, "_on_github_sha", lambda sha: True)
    show, gone = app.unsaved_saves(db, NOW)
    assert show == [] and sorted(g[0] for g in gone) == sorted(db["meta"])
