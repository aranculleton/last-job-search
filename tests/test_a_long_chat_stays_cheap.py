"""Every chat in a person's copy squeezes its history at 200,000 tokens.

The chat that answers the page lives for weeks, and every tap and every brief re-reads its
history. On a model with a 1M-token window that history grew to a million tokens before
Claude Code compacted it, and the maintainer's plan ran out (2026-10-29). The app's own
.claude/settings.json caps it for every chat in every copy, cloud and computer alike
(code.claude.com/docs/en/model-config: CLAUDE_CODE_AUTO_COMPACT_WINDOW, clamped to 100,000
to 1,000,000; a committed project settings file applies in single-repository cloud sessions).
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import security_guards  # noqa: E402

SETTINGS = json.load(open(os.path.join(ROOT, ".claude", "settings.json"), encoding="utf-8"))


def test_every_chat_in_a_copy_compacts_at_200000_tokens():
    window = SETTINGS["env"]["CLAUDE_CODE_AUTO_COMPACT_WINDOW"]
    assert window == "200000"
    assert 100_000 <= int(window) <= 1_000_000          # the range Claude Code accepts


def test_the_guard_reviewed_that_exact_value():
    assert security_guards.ALLOWED_ENV["CLAUDE_CODE_AUTO_COMPACT_WINDOW"] == "200000"


def test_the_guide_says_it_is_built_in():
    text = open(os.path.join(ROOT, "automation", "README.md"), encoding="utf-8").read()
    part = text.split("### Keep a long-lived chat small", 1)[1].split("\n### ", 1)[0]
    assert "CLAUDE_CODE_AUTO_COMPACT_WINDOW" in part and "Nothing to set up" in part
