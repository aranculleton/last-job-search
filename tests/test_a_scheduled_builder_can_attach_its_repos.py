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


def test_archive_session_is_allowed_so_finished_chats_are_put_away_unattended():
    settings = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    assert "mcp__claude-code-remote__archive_session" in settings["permissions"]["allow"]
