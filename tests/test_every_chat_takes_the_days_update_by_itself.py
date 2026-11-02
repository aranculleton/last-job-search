"""Every chat takes the day's update with nothing asked of anyone.

A chat open for days never ran the start command again and missed CLAUDE.md's line asking
for the check each day; a page opened with no chat running was never brought up to date (the
maintainer, 2026-11-02: "will their claude know what to do... with ZERO PROMPTING even if its
the same chat thats been used this entire time?"). The app's one prompt hook now puts the
check beside the day's first message in any chat, and is silent once it has run; it reads
files only, since a prompt hook is cut off after 30 seconds, mid-merge. The chat that answers
the page checks on every wake (a page's ring may not run the hook), and the daily upkeep
(tools/routines.py) wakes that chat where no brief runs every day.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import learned  # noqa: E402
import sync_app  # noqa: E402

PROMPT = {"hook_event_name": "UserPromptSubmit", "prompt": "find me jobs"}


def _said(out):
    return ((out or {}).get("hookSpecificOutput") or {}).get("additionalContext") or ""


def test_the_days_first_message_carries_the_check_and_later_ones_do_not(monkeypatch, tmp_path):
    monkeypatch.setattr(learned, "_path", lambda: str(tmp_path / "learned.json"))
    monkeypatch.setattr(sync_app, "stale", lambda: True)
    out = learned._with_update(learned.hook(PROMPT), learned._update_due(PROMPT))
    assert out["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
    assert "Before anything else in this turn, run python3 tools/sync_app.py --if-stale" in _said(out)
    monkeypatch.setattr(sync_app, "stale", lambda: False)
    assert learned._with_update(learned.hook(PROMPT), learned._update_due(PROMPT)) == {}


def test_a_reaction_and_the_check_on_one_message_are_both_said(monkeypatch, tmp_path):
    monkeypatch.setattr(learned, "_path", lambda: str(tmp_path / "learned.json"))
    monkeypatch.setattr(sync_app, "stale", lambda: True)
    reacted = {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                      "additionalContext": "The person reacted (\"too formal\")."}}
    said = _said(learned._with_update(json.loads(json.dumps(reacted)), learned._update_due(PROMPT)))
    assert said.startswith("The app's daily update check") and "The person reacted" in said


def test_only_the_prompt_carries_it_and_a_broken_check_never_breaks_the_chat(monkeypatch, tmp_path):
    monkeypatch.setattr(learned, "_path", lambda: str(tmp_path / "learned.json"))
    monkeypatch.setattr(sync_app, "stale", lambda: True)
    assert learned._update_due({"hook_event_name": "Stop"}) == ""
    def boom():
        raise RuntimeError("no git")
    monkeypatch.setattr(sync_app, "stale", boom)
    assert learned._update_due(PROMPT) == ""


def test_in_the_app_itself_and_before_setup_nothing_is_said(monkeypatch):
    assert sync_app.stale() is False         # this checkout is the app
    monkeypatch.setattr(sync_app, "stale", lambda: True)
    monkeypatch.setattr(learned, "_path", lambda: None)   # no profile yet: its start syncs
    assert learned._update_due(PROMPT) == ""


def test_the_chat_that_answers_the_page_checks_on_every_wake():
    with open(os.path.join(ROOT, ".claude", "skills", "app", "SKILL.md"), encoding="utf-8") as fh:
        skill = fh.read()
    step1 = skill[skill.index("## 1. Read, in one go"):skill.index("## 2.")]
    assert "python3 tools/sync_app.py --if-stale" in step1 and "on every wake" in step1
