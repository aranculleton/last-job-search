"""The brief's time is one thing: where the person's own notes say another, they are asked.

A person's notes said the brief came at 07:56, the scheduled task ran at 08:01, and the app's
default was 7:38: three answers, and nothing noticed (audit BT-7, second audit B10). The
registry's time is when it comes; where the person's notes on their automation name a brief
time that differs, `routines.py check` says so (a note, never a failed check: only the person
can say which they want) and the brief asks them once. Invented notes.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import routines  # noqa: E402

NOTES = """# The person

## This search's automation

- **Times are UK** (`Europe/London`): the brief runs every day at 07:56 and the job round is off.

| Routine | When | What |
|---|---|---|
| **Brief** | Every day 07:56 | the brief |
| **Job round** | Mondays 06:52 | a round |

## Something else

The brief once ran at 06:00 in another set-up.
"""


def _reg(cron):
    return {"setup": "chat_per_briefing", "timezone": "Europe/London", "routines": [
        {"key": "morning_brief", "name": routines.BRIEF_NAME, "trigger_id": "trig_EXAMPLEB",
         "cron": cron, "prompt_file": routines.BRIEF_FILE,
         "chat": {"session_id": "session_EXAMPLEBRIEFCHAT", "own": True}}]}


def test_a_different_time_in_their_notes_is_said():
    said = routines.time_disagrees(_reg("CRON_TZ=Europe/London 1 8 * * *"), NOTES)
    assert "07:56" in said and "08:01" in said
    assert routines.time_disagrees(_reg("CRON_TZ=Europe/London 56 7 * * *"), NOTES) == ""
    assert routines.time_disagrees(_reg("CRON_TZ=Europe/London 1 8 * * *"), "# Notes\n") == ""


def test_check_says_it_without_failing(tmp_path, monkeypatch, capsys):
    import json
    path = tmp_path / "routines.json"
    path.write_text(json.dumps(_reg("CRON_TZ=Europe/London 1 8 * * *")), encoding="utf-8")
    monkeypatch.setattr(routines, "_profile_notes", lambda: NOTES)
    assert routines.main(["check", str(path)]) == 0
    out = capsys.readouterr().out
    assert "note:" in out and "07:56" in out


def test_the_brief_asks_them(monkeypatch):
    import brief
    monkeypatch.setattr(routines, "load", lambda *a, **k: _reg("CRON_TZ=Europe/London 1 8 * * *"))
    monkeypatch.setattr(routines, "_profile_notes", lambda: NOTES)
    monkeypatch.setattr(routines, "calls", lambda **k: [])
    monkeypatch.setattr(brief, "_tidy_due", lambda: "")
    monkeypatch.setattr(brief, "_computer_lines", lambda b: [])
    monkeypatch.setattr(brief, "push_step", lambda b: "")
    b = {"sync": {}, "page": "", "write_here": [], "profile_line": "", "queries": [],
         "since": "2026-11-01", "skip_links": [], "what_counts": "x", "pack": "",
         "date": "2026-11-10"}
    lines = brief.claude_lines(b)
    assert any("07:56" in ln and "08:01" in ln for ln in lines), lines


def test_only_clock_times_are_read_and_the_question_is_asked_once(monkeypatch, tmp_path):
    """Review of fix/helpers, item 8: "4.14" (a version) and "$1.50" read as times, and the
    question came in every brief."""
    notes = NOTES.replace("07:56", "8am") + (
        "\n\n## This search's automation\n\nThe brief costs $1.50 a run since release 4.14.\n")
    said = routines.time_disagrees(_reg("CRON_TZ=Europe/London 1 8 * * *"), notes)
    assert "08:00" in said and "04:14" not in said and "01:50" not in said
    import brief
    import app_setup
    kept = {}
    monkeypatch.setattr(app_setup, "said_once", lambda: dict(kept))
    monkeypatch.setattr(app_setup, "save_said", lambda key, day: kept.update({key: day}) or "")
    monkeypatch.setattr(routines, "load", lambda *a, **k: _reg("CRON_TZ=Europe/London 1 8 * * *"))
    monkeypatch.setattr(routines, "_profile_notes", lambda: NOTES)
    monkeypatch.setattr(routines, "calls", lambda **k: [])
    monkeypatch.setattr(brief, "_tidy_due", lambda: "")
    monkeypatch.setattr(brief, "_computer_lines", lambda b: [])
    monkeypatch.setattr(brief, "push_step", lambda b: "")
    b = {"sync": {}, "page": "", "write_here": [], "profile_line": "", "queries": [],
         "since": "2026-11-01", "skip_links": [], "what_counts": "x", "pack": "",
         "date": "2026-11-10"}
    first = brief.claude_lines(b)
    again = brief.claude_lines(dict(b, date="2026-11-11"))
    assert any("07:56" in ln for ln in first)
    assert not any("07:56" in ln for ln in again)
