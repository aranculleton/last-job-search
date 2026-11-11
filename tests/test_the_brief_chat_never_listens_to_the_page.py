"""The brief's chat stops listening to the page after it publishes it, and its last reply stays
the brief.

Publishing the page subscribes the chat that publishes it to the page's comments. The brief
republished the page after an update, so the page rang the brief's chat twice that day; each
ring read the whole page store at the cost of a run and ended "Nothing to do here. Another
chat answers your page", the last thing the person saw there after the brief (audit BT-3,
BT-10). Every brief with a page now ends its page step by stopping its watch, and the prompt
says a ring there is never answered. Invented page address.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import brief  # noqa: E402

from test_brief import TODAY, _profile, _run, _state  # noqa: E402

PAGE = "https://claude.ai/code/artifact/example-brief-page"


def _claude(tmp_path):
    state = _state(tmp_path)
    with open(os.path.join(_profile(state), "app.json"), "w", encoding="utf-8") as fh:
        json.dump({"url": PAGE}, fh)
    r = _run(state, "--today", TODAY)
    assert r.returncode == 0, r.stderr
    return [ln for ln in r.stdout.split("FOR CLAUDE, never in the message:\n", 1)[1].splitlines()]


def test_the_page_step_ends_by_stopping_the_watch_a_publish_starts(tmp_path):
    lines = _claude(tmp_path)
    page = next(i for i, ln in enumerate(lines) if ln.startswith("- the page, once the news"))
    stop = next(i for i, ln in enumerate(lines) if "on: false" in ln)
    assert stop > page
    said = lines[stop]
    assert "ArtifactComments" in said and PAGE in said and "watch" in said
    assert "never answers the page" in said


def test_a_republish_line_is_followed_by_the_stop(monkeypatch):
    monkeypatch.setattr(brief, "page_behind", lambda: "an update changed the page itself")
    monkeypatch.setattr(brief, "behind_steps", lambda url: ["1. publish it"])
    b = {"sync": {}, "page": PAGE, "write_here": [], "profile_line": "", "queries": [],
         "since": "2026-11-01", "skip_links": [], "what_counts": "x", "pack": "",
         "date": "2026-11-10"}
    monkeypatch.setattr(brief, "_tidy_due", lambda: "")
    monkeypatch.setattr(brief, "_computer_lines", lambda b: [])
    monkeypatch.setattr(brief, "push_step", lambda b: "")
    lines = brief.claude_lines(b)
    pub = next(i for i, ln in enumerate(lines) if "republish it now" in ln)
    stop = next(i for i, ln in enumerate(lines) if "on: false" in ln)
    assert stop > pub


def test_the_prompt_says_a_ring_here_is_never_answered_and_nothing_follows_the_message():
    prompt = " ".join(open(os.path.join(ROOT, "automation", "prompts", "morning_brief.md"),
                           encoding="utf-8").read().split())
    assert "never answers the page" in prompt
    assert "a ring from the page" in prompt.lower()
    assert "write nothing after" in prompt


def test_a_brief_running_in_the_chat_that_answers_the_page_keeps_its_watch(monkeypatch):
    """A copy whose brief still runs in the live helper would have stopped the listener's own
    watch, and the page gone unanswered (review of fix/helpers, item 6): the line is only for a
    brief in a chat of its own."""
    import app_listen
    b = {"sync": {}, "page": PAGE, "write_here": [], "profile_line": "", "queries": [],
         "since": "2026-11-01", "skip_links": [], "what_counts": "x", "pack": "",
         "date": "2026-11-10"}
    monkeypatch.setattr(brief, "_tidy_due", lambda: "")
    monkeypatch.setattr(brief, "_computer_lines", lambda b: [])
    monkeypatch.setattr(brief, "push_step", lambda b: "")
    monkeypatch.setattr(brief, "page_behind", lambda: "")
    monkeypatch.setattr(app_listen, "this_chat", lambda chat="": "session_EXAMPLEHELPER")
    monkeypatch.setattr(app_listen, "seen",
                        lambda: {"listener": {"chat": "session_EXAMPLEHELPER"}})
    assert not any("on: false" in ln for ln in brief.claude_lines(b))
    monkeypatch.setattr(app_listen, "seen", lambda: {"listener": {"chat": "session_EXAMPLEOTHER"}})
    assert any("on: false" in ln for ln in brief.claude_lines(b))
