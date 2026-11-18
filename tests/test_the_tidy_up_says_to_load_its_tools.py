"""The tidy-up's steps say to load the tools they use, where a chat has not loaded them.

In a chat made with create_session (the page's chat, the brief's), list_sessions,
list_triggers, get_session, archive_session and set_session_title are deferred: named, but not
callable until ToolSearch loads them, and no step said so. Each step that uses them now says,
in one clause, to load them first where they are not loaded, naming every tool it calls.
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import app  # noqa: E402

PREFIX = "mcp__claude-code-remote__"


def _loaded(said: str) -> set[str]:
    got = re.search(r"ToolSearch select:(\S+?) first, where they are not loaded", said)
    assert got, said
    return {n[len(PREFIX):] for n in got.group(1).split(",") if n.startswith(PREFIX)}


def test_the_days_tidy_up_loads_every_tool_it_and_its_plan_call():
    need = {"list_sessions", "list_triggers", "get_session", "archive_session",
            "set_session_title"}
    for said in (app.TIDY_GIVE, app.TIDY_SAID):
        assert need <= _loaded(said), said


def test_the_hand_overs_step_loads_only_what_it_calls():
    said = app.TIDY_NOW.format(old="session_EXAMPLEOLDHELPER")
    assert _loaded(said) == {"get_session", "archive_session"}
    assert "list_sessions" not in said            # never the whole listing (H-4)
