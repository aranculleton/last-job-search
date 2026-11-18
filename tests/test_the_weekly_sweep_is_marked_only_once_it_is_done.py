"""The week's sweep of one-off tasks that have fired counts only once a tidy-up has done it.

Once a week the day's tidy-up also asks list_triggers for the tasks that have fired
(include_completed), so the app's one-off check-ins are cleaned away. It was marked done the
moment the line was printed, so a chat that never finished the tidy-up skipped that week, and
a ring (`wake`) never asked for it at all. Now printing it notes only that it was asked, and
`tidy.py done` after it marks the week's sweep done; a ring asks for it as a check-in does.
Invented chats and page.
"""
from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import pytest  # noqa: E402

import app  # noqa: E402
import repo_files  # noqa: E402
from test_one_chat_answers_the_page import Copy  # noqa: E402
from test_the_days_tidy_up_runs_on_a_day_with_a_hand_over import (  # noqa: E402
    CLOUD, NEW, _listen, _tidy_lines)

TIDY = os.path.join(ROOT, "tools", "tidy.py")


@pytest.fixture
def copy(tmp_path):
    c = Copy(tmp_path)
    subprocess.run(["git", "init", "-q", c.state], check=True, timeout=60)
    c.page()
    yield c
    sys.path.remove(c.root)


def _weekly(said):
    lines = _tidy_lines(said)
    assert lines and lines[0].startswith(app.TIDY_SAID), said
    return app.TIDY_COMPLETED in lines[0]


def _done(copy, day):
    r = subprocess.run([*repo_files.python_on_github(TIDY), "done", "--today", day],
                       env=copy.env(**CLOUD), capture_output=True, encoding="utf-8",
                       errors="replace", timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr


def test_the_weeks_sweep_is_asked_again_until_a_tidy_up_has_done_it(copy):
    assert _weekly(_listen(copy, NEW, "2026-11-10T12:00:00Z", "--listen"))
    # The chat never finished that tidy-up: the next check-in asks for the week's sweep again.
    assert _weekly(_listen(copy, NEW, "2026-11-10T13:00:00Z"))
    _done(copy, "2026-11-10")
    # Done: the next days' tidy-ups leave it out, until the week is up.
    assert not _weekly(_listen(copy, NEW, "2026-11-12T12:00:00Z"))
    _done(copy, "2026-11-12")
    assert _weekly(_listen(copy, NEW, "2026-11-17T12:00:00Z"))


def test_a_ring_asks_for_the_weeks_sweep_too(copy):
    _listen(copy, NEW, "2026-11-10T12:00:00Z", "--listen")
    said = copy.run("wake", copy.dump("w1"), "--chat", NEW, "--kind", "cloud", "--on", "test",
                    "--now", "2026-11-10T13:00:00Z", **CLOUD)
    assert _weekly(said), said


def test_the_briefs_tidy_up_asks_for_it_the_same_way(copy):
    def due(day):
        r = subprocess.run([*repo_files.python_on_github(TIDY), "due", "--dump", copy.dump(),
                            "--today", day, "--now", day + "T08:05:00Z"],
                           env=copy.env(**CLOUD, LJS_CHAT="session_EXAMPLEBRIEFSOWNCHAT"),
                           capture_output=True, encoding="utf-8", errors="replace", timeout=120)
        assert r.returncode == 0, r.stdout + r.stderr
        assert app.TIDY_GIVE in r.stdout, r.stdout
        return app.TIDY_COMPLETED in r.stdout
    assert due("2026-11-10") and due("2026-11-10")      # asked again until it is done
    _done(copy, "2026-11-10")
    assert not due("2026-11-11")
