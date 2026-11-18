"""A ring after the day's tidy-up asks only about the chat taken over from, as a check-in does.

`listen` knows, once the day's tidy-up has run, to ask only about the page chat this one took
the page over from (one get_session and `tidy.py retire`). A ring from the page runs `wake`,
which threw that away and printed the whole day's tidy-up instead: every ring after the day's
sweep listed every chat and task again. `wake` now carries what the check-in decided, through
a wake that stops for a claim too, and prints the same step as `listen`. Invented chats and
page.
"""
from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import pytest  # noqa: E402

import app  # noqa: E402
from test_one_chat_answers_the_page import Copy  # noqa: E402
from test_the_days_tidy_up_runs_on_a_day_with_a_hand_over import (  # noqa: E402
    CLOUD, NEW, OLD, _listen, _mark, _tidy_lines)


@pytest.fixture
def copy(tmp_path):
    c = Copy(tmp_path)
    subprocess.run(["git", "init", "-q", c.state], check=True, timeout=60)
    c.page()
    yield c
    sys.path.remove(c.root)


def _wake(copy, name, at):
    return copy.run("wake", copy.dump(name), "--chat", NEW, "--kind", "cloud", "--on", "test",
                    "--now", at, **CLOUD)


def test_a_ring_after_the_days_tidy_up_asks_only_about_the_chat_taken_over_from(copy):
    _listen(copy, OLD, "2026-11-17T12:00:00Z", "--helper")
    _mark(copy, "2026-11-17", "2026-11-17T12:10:00Z")
    _listen(copy, NEW, "2026-11-18T08:00:00Z", "--listen", "--helper")
    # Before the day's tidy-up, a ring asks for the whole of it, as a check-in does.
    said = _wake(copy, "w1", "2026-11-18T10:00:00Z")
    assert any(ln.startswith(app.TIDY_SAID) for ln in _tidy_lines(said)), said
    # Done today, with the old helper kept for now: a ring asks about it alone.
    _mark(copy, "2026-11-18", "2026-11-18T15:35:00Z")
    said = _wake(copy, "w2", "2026-11-18T16:30:00Z")
    assert _tidy_lines(said) == [app.TIDY_NOW.format(old=OLD)], said
    assert "list_sessions" not in said
