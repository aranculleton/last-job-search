"""A scheduled chat in Auto attaches the repositories its task names without a person there.

The weekly builder runs in a chat with the app attached and attaches the maintainer's copy itself
(automation/prompts/builder_week.md needs it for the push gate and the rehearsals). Run on
2026-11-12, Auto's own check refused `add_repo` and the builder stopped before doing anything.
An allow rule is what lets it through; GitHub still attaches only what the person has granted.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_add_repo_is_allowed_for_a_chat_nobody_is_watching():
    settings = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    assert "mcp__claude-code-remote__add_repo" in settings["permissions"]["allow"]


def test_a_builder_can_find_its_own_chat_and_tasks_unattended_and_nothing_more():
    # The weekly builder hands over with nobody watching (tools/app_bug.py handover). This file
    # is every person's, so only the two reads are pre-approved here: making a chat or a task,
    # or deleting one, stays with the chat's own check, so a posting read in anyone's chat can
    # never delete their brief unasked. A refusal leaves the old chat and its tasks as they were.
    settings = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    allow = settings["permissions"]["allow"]
    for tool in ("get_session", "list_triggers"):
        assert f"mcp__claude-code-remote__{tool}" in allow, tool
    for tool in ("create_session", "create_trigger", "delete_trigger", "update_trigger"):
        assert f"mcp__claude-code-remote__{tool}" not in allow, tool


def test_archive_session_is_allowed_so_finished_chats_are_put_away_unattended():
    settings = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    assert "mcp__claude-code-remote__archive_session" in settings["permissions"]["allow"]
