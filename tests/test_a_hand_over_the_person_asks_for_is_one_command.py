"""A hand-over the person asks for is one command.

"Hand over to a fresh helper and archive yourself" took many turns on a chat of some 630,000
tokens that had cost $87: no command did it, and `listen --hand` was in no instruction (second
audit A7). `app.py hand-over` prints the whole of it: the fresh helper's create_session, the
hand of the page to it with its id, and this chat's own save and archive.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import app  # noqa: E402
import app_listen  # noqa: E402

ME = "session_EXAMPLEHELPER"


def _meta(tmp_path, chat):
    d = tmp_path / ("dump-" + chat)
    (d / "meta").mkdir(parents=True)
    (d / "meta" / "listen.json").write_text(json.dumps(
        {"chat": chat, "helper": True, "kind": "cloud", "_v": 3}), encoding="utf-8")
    return str(d)


def test_it_reads_first_and_refuses_in_a_chat_that_does_not_answer_the_page(
        tmp_path, monkeypatch, capsys):
    """Review of fix/helpers, item 12: the create_session came before any check that this chat
    answers the page, so a retired or other chat left a stray helper that took the page."""
    import app_setup
    monkeypatch.setattr(app_setup, "origin", lambda: ("example-owner", "my-job-search"))
    monkeypatch.setattr(app_setup, "page_record", lambda: {"url": "https://claude.ai/code/artifact/example-page"})
    monkeypatch.setattr(app_listen, "this_chat", lambda chat="": chat or ME)
    assert app.cmd_hand_over(argparse.Namespace(chat=ME, dump="")) == 0
    out = capsys.readouterr().out
    assert "create_session" not in out and "collections meta" in out
    assert app.cmd_hand_over(argparse.Namespace(chat=ME, dump=_meta(tmp_path,
                                                                    "session_EXAMPLEOTHER"))) == 1
    out = capsys.readouterr().out
    assert "create_session" not in out and "does not answer the page" in out


def test_one_command_prints_the_whole_hand_over(tmp_path, monkeypatch, capsys):
    import app_setup
    monkeypatch.setattr(app_setup, "origin", lambda: ("example-owner", "my-job-search"))
    monkeypatch.setattr(app_setup, "page_record", lambda: {"url": "https://claude.ai/code/artifact/example-page"})
    monkeypatch.setattr(app_listen, "this_chat", lambda chat="": chat or ME)
    assert app.cmd_hand_over(argparse.Namespace(chat=ME, dump=_meta(tmp_path, ME))) == 0
    out = capsys.readouterr().out
    at = out.index("create_session ") + len("create_session ")
    call = json.JSONDecoder().raw_decode(out, at)[0]
    assert call["title"] == app_listen.HELPER_CHAT_TITLE
    assert call["source_url"] == "https://github.com/example-owner/my-job-search"
    assert f"--chat {ME} --hand <its id>" in out and "on: false" in out
    assert f"python3 tools/app.py retired --chat {ME}" in out
    assert out.index("create_session") < out.index("--hand") < out.index("retired --chat")


def test_the_app_skill_names_it():
    # The skill in parts (E-3): a hand-over is a wake's, in wake.md beside the daily renewal.
    import app_skill
    skill = " ".join(app_skill.read("wake.md").split())
    assert "python3 tools/app.py hand-over" in skill
