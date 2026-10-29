"""A chat keeps its model's whole window before Claude Code squeezes its history.

The app once capped every chat at 200,000 tokens (CLAUDE_CODE_AUTO_COMPACT_WINDOW) to keep a
weeks-long chat cheap. On a 1M-window model that made a working chat forget what it was doing
every few steps (the maintainer, 2026-10-29: "whyre u compressing so much ... BACK TO
DEFAULT"). The app sets nothing, so Claude Code's default, the model's own window, holds, and
the security guard refuses the setting coming back.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import security_guards  # noqa: E402

SETTINGS = json.load(open(os.path.join(ROOT, ".claude", "settings.json"), encoding="utf-8"))


def test_no_chat_in_a_copy_has_its_history_window_capped():
    assert "CLAUDE_CODE_AUTO_COMPACT_WINDOW" not in SETTINGS.get("env", {})


def test_the_guard_refuses_the_cap_coming_back():
    assert "CLAUDE_CODE_AUTO_COMPACT_WINDOW" not in security_guards.ALLOWED_ENV


def test_the_guide_says_nothing_is_set():
    text = open(os.path.join(ROOT, "automation", "README.md"), encoding="utf-8").read()
    part = text.split("### A long-lived chat keeps its whole window", 1)[1].split("\n### ", 1)[0]
    assert "Nothing to set up" in part and "200000" not in part
