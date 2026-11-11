"""An update that changes the brief's own instructions is followed by the run that took it.

A run reads its prompt before its first command, and that command takes the day's update: on
10 November the update changed the instructions and the run kept following the copy it had read
(audit BT-11). Now the start compares the brief's prompt files before and after the update and,
where they changed, says first to read them again. No network: the steps are stubbed.
"""
from __future__ import annotations

import datetime as dt
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import brief  # noqa: E402
import person  # noqa: E402


class Done:
    returncode, stdout, stderr = 0, "", ""


def _start(tmp_path, monkeypatch, seen, capsys):
    monkeypatch.setenv("LJS_BRIEF_SYNC", str(tmp_path / "sync.txt"))
    monkeypatch.setattr(brief.subprocess, "run", lambda argv, **kw: Done())
    monkeypatch.setattr(brief, "page_url", lambda: "")
    monkeypatch.setattr(person, "today", lambda now=None: dt.date(2026, 11, 10))
    import land
    monkeypatch.setattr(land, "stranded", lambda root=None, fetch=False: {}, raising=False)
    marks = iter(seen)
    monkeypatch.setattr(brief, "_prompts_seen", lambda: next(marks))
    assert brief.start(["--on", "a model", "--write"], "a model") == 0
    return capsys.readouterr().out


def test_a_changed_prompt_is_read_again_first(tmp_path, monkeypatch, capsys):
    out = _start(tmp_path, monkeypatch, [{"automation/prompts/morning_brief.md": "a"},
                                         {"automation/prompts/morning_brief.md": "b"}], capsys)
    assert "read automation/prompts/morning_brief.md again now" in out


def test_an_unchanged_prompt_says_nothing(tmp_path, monkeypatch, capsys):
    same = {"automation/prompts/morning_brief.md": "a"}
    out = _start(tmp_path, monkeypatch, [same, same], capsys)
    assert "again now" not in out
