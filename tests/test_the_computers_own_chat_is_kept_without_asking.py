"""The chat that stays open on the person's computer as its own chat is the default, kept
without a question to the person.

Issue 288 (2026-11-16): getting one LinkedIn read to run took four trips into chats on the
computer, one of them to answer that chat's question whether to keep it open as the computer's
standing chat. Its step said it "becomes your computer's own chat" and to rename it "where you
can, asked in plain words", and nothing said the person is never asked: the chat asked them. The
rename is asked of the Claude app's own session tools (claude_surfaces `computer-chat-archive`),
never of the person. Invented computers only.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import computer  # noqa: E402
from test_a_computer_chat_is_seen_to_its_end import T, _as  # noqa: E402
from test_a_tick_on_the_page_is_applied_once import _db  # noqa: E402


def test_becoming_the_computers_own_chat_is_never_asked_of_the_person(tmp_path, monkeypatch):
    _as(monkeypatch, "computer", tmp_path)
    said = computer.listener_become(_db(), "session_macA", str(tmp_path / "bell.html"), T)
    assert said.startswith("stay:"), said
    assert computer.LISTENER_UNASKED in said
    assert "never ask the person" in said.lower()
    # The rename is the app's to do, asked of its own session tools, never of the person.
    assert "asked in plain words" not in said
    assert "never the person" in said[said.index("Rename this chat"):]


def test_the_computers_own_chat_says_nothing_of_it_when_it_already_is_it(tmp_path, monkeypatch):
    _as(monkeypatch, "computer", tmp_path)
    db = _db()
    db["meta"] = {computer.LISTENER_DOC[1]: {"data": {
        "chat": "session_macA", "bell": "https://claude.ai/code/artifact/bell-example",
        "computer": "Studio Laptop", "ready_at": "2026-10-25T17:00:00Z",
        "answered_at": "2026-10-25T17:55:00Z"}, "version": 2}}
    said = computer.listener_become(db, "session_macA", str(tmp_path / "bell.html"), T)
    assert said.startswith("stay:") and computer.LISTENER_UNASKED in said, said
