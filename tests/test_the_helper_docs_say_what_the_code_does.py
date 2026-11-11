"""What the app says about helpers, job chats and test check-ins matches what the code does.

Second audit A10, E1, E2 and E3: the tidy-up's instructions said it moves the brief into the
chat that answers the page, which it never does now; a job's chat was said to report back to the
chat that started it, which it no longer does; the computer's notes said the cloud chat that
started a chat there archives it, which is the starter chat's job; and the README's way to
test a task made a one-off task in the chat and never took it away, so test check-ins piled up.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return " ".join(fh.read().split())


def test_no_stale_line_is_left():
    skill = _read(".claude", "skills", "app", "SKILL.md")
    assert "prints the brief's move into this chat" not in skill
    app = _read("tools", "app.py")
    assert "the brief moved here first" not in app
    assert "reports back to `chat`, which then archives it" not in app
    assert "so the job's chat can report back to it" not in app
    computer = _read("tools", "computer.py")
    assert "the cloud chat that started it archives it once its work is finished" not in computer


def test_the_readme_test_takes_its_one_off_task_away():
    readme = _read("automation", "README.md")
    test = readme.split("### Test it, without fire_trigger", 1)[1].split("###", 1)[0]
    assert "delete_trigger" in test
    assert "never in the chat that answers your page" in test
