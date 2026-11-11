"""The brief's chat is replaced by a fresh one of its own once its history has grown.

The brief runs in one chat for good, and its history grew by about 100,000 tokens a day: the
cache does not last overnight, so each morning's run paid for the whole history again, about
$6.8 a run against $1 to $2 in a fresh chat, and the README said $0.82 and "reuses that context
from cache" (audit BT-2, second audit B3). Now the brief, once its message is out, looks at its
own size and, over BRIEF_CHAT_MAX, gives itself a fresh chat of its own (the same calls as a
move), and the README says what a run costs. Invented ids.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import routines  # noqa: E402

CRON = "CRON_TZ=Europe/London 1 8 * * *"


def _write(tmp_path):
    reg = {"setup": "chat_per_briefing", "timezone": "Europe/London", "routines": [
        {"key": "morning_brief", "name": routines.BRIEF_NAME, "trigger_id": "trig_EXAMPLEB",
         "cron": CRON, "prompt_file": routines.BRIEF_FILE, "copy": True,
         "chat": {"session_id": "session_EXAMPLEBRIEFCHAT", "own": True}}]}
    path = tmp_path / "routines.json"
    path.write_text(json.dumps(reg), encoding="utf-8")
    return str(path)


def test_over_the_limit_the_brief_gets_a_fresh_chat(tmp_path, monkeypatch, capsys):
    path = _write(tmp_path)
    monkeypatch.setattr(routines, "load", lambda p=None: json.load(open(path, encoding="utf-8")))
    assert routines.main(["fresh", "--used", str(routines.BRIEF_CHAT_MAX + 1)]) == 0
    out = capsys.readouterr().out
    assert "create_session" in out and "create_trigger" in out and "--own-chat" in out
    assert '"enabled": false' in out
    assert routines.main(["fresh", "--used", str(routines.BRIEF_CHAT_MAX - 1)]) == 0
    assert "create_session" not in capsys.readouterr().out


def test_the_brief_looks_at_its_size_after_the_message():
    import brief
    line = brief.FRESH_LINE
    assert "get_session" in line and "routines.py fresh --used" in line


def test_the_readme_says_what_a_run_costs():
    readme = " ".join(open(os.path.join(ROOT, "automation", "README.md"),
                           encoding="utf-8").read().split())
    cost = readme.split("## Cost", 1)[1]
    assert "reuses that context from cache" not in cost
    assert "$6.8" in cost and "fresh chat" in cost


def test_never_near_the_limit_of_how_deep_chats_go_and_always_before_the_landing(
        tmp_path, monkeypatch, capsys):
    """Each fresh brief chat is started by the last, one level deeper, and past the platform's
    limit the brief could neither start a fresh chat nor the page's fresh helper; and the step
    came after the landing, so the registry it changed might never be saved (review of
    fix/helpers, item 9)."""
    path = _write(tmp_path)
    monkeypatch.setattr(routines, "load", lambda p=None: json.load(open(path, encoding="utf-8")))
    over = str(routines.BRIEF_CHAT_MAX + 1)
    assert routines.main(["fresh", "--used", over, "--lineage", "6/8"]) == 0
    assert "create_session" not in capsys.readouterr().out
    assert routines.main(["fresh", "--used", over, "--lineage", "2/8"]) == 0
    assert "create_session" in capsys.readouterr().out
    import brief
    assert "before the landing" in brief.FRESH_LINE and "--lineage" in brief.FRESH_LINE
