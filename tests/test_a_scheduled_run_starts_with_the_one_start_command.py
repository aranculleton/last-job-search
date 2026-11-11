"""A scheduled run starts with the same command every chat starts with, and it runs the brief.

CLAUDE.md says every chat runs `app.py start` first, with no word for a scheduled run, while
the brief's prompt said to run `brief.py --start`; a run that obeyed CLAUDE.md spent minutes on
a person's start (second audit B11). CLAUDE.md is at its size limit, so the code does it:
`app.py start --scheduled morning_brief` runs the brief's own start, and the brief's prompt
says to run exactly that, so the two never disagree.
"""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import app  # noqa: E402
import brief  # noqa: E402


def test_start_with_the_brief_named_runs_the_briefs_start(monkeypatch):
    got = []
    monkeypatch.setattr(brief, "start", lambda argv, model: got.append((argv, model)) or 0)
    a = argparse.Namespace(scheduled="morning_brief", on="a model", tools="", page="", chat="",
                           listen=False, helper=False, work="", dump="", paste=False)
    assert app.cmd_start(a) == 0
    assert got == [(["--on", "a model", "--write"], "a model")]


def test_an_unknown_scheduled_run_is_said_plainly(monkeypatch, capsys):
    a = argparse.Namespace(scheduled="something_else", on="m", tools="", page="", chat="",
                           listen=False, helper=False, work="", dump="", paste=False)
    assert app.cmd_start(a) == 2
    assert "something_else" in capsys.readouterr().err


def test_the_briefs_prompt_names_the_one_start_command():
    prompt = " ".join(open(os.path.join(ROOT, "automation", "prompts", "morning_brief.md"),
                           encoding="utf-8").read().split())
    assert 'python3 tools/app.py start --scheduled morning_brief --on' in prompt
    assert "brief.py --start" not in prompt


def test_the_hook_says_so_before_the_plain_start_runs():
    """CLAUDE.md's "run start first" is read before the prompt file, so a run could still make
    the plain start (review of fix/helpers, item 11): the app's hook says, beside the run's own
    first words, which start it is."""
    import learned
    said = learned._scheduled_start({"hook_event_name": "UserPromptSubmit",
                                     "prompt": "Scheduled run: morning brief. Read "
                                               "automation/prompts/morning_brief.md and do it."})
    assert "python3 tools/app.py start --scheduled morning_brief" in said
    assert learned._scheduled_start({"hook_event_name": "UserPromptSubmit",
                                     "prompt": "hello"}) == ""
