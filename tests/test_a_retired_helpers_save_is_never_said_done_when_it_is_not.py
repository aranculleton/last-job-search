"""A helper that handed the page on never says its save has ended while it is still running,
and stops starting saves after two that never reached GitHub.

`app.py retired --wait` waited up to 40 minutes for the helper's own save and then said "its
save has ended" whatever had happened, so a stuck save looked finished, and the woken chat
started another save and another wait with no end (audit HC-3). Now the wait says "still
saving" and exits non-zero when the save is still running, and a third start after two saves
that never reached GitHub is refused with a plain stop. Invented chat id, a local checkout.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import pytest  # noqa: E402

import app  # noqa: E402
import app_listen  # noqa: E402
import land  # noqa: E402

CHAT = "session_EXAMPLERETIREDHELPER"


@pytest.fixture
def checkout(tmp_path, monkeypatch):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    monkeypatch.setenv("LJS_STATE", str(tmp_path))
    monkeypatch.setattr(app_listen, "retired_here", lambda chat: True)
    monkeypatch.setattr(app_listen, "this_chat", lambda chat="": chat or CHAT)
    return tmp_path


def _retired(capsys, wait=False):
    rc = app.cmd_retired(argparse.Namespace(chat=CHAT, wait=wait))
    return rc, capsys.readouterr().out


def test_a_wait_that_times_out_says_still_saving_and_fails(checkout, monkeypatch, capsys):
    monkeypatch.setattr(land, "landing", lambda root=None: True)
    monkeypatch.setattr(app, "RETIRED_WAIT_S", 0)
    rc, said = _retired(capsys, wait=True)
    assert rc != 0
    assert "still saving" in said and "has ended" not in said


def test_a_wait_whose_save_ended_says_so(checkout, monkeypatch, capsys):
    monkeypatch.setattr(land, "landing", lambda root=None: False)
    rc, said = _retired(capsys, wait=True)
    assert rc == 0 and "has ended" in said


def test_after_two_saves_that_never_reached_github_it_stops(checkout, monkeypatch, capsys):
    monkeypatch.setattr(app, "_saved_on_github", lambda root: False)
    for _ in range(2):
        rc, said = _retired(capsys)
        assert rc == 0 and "land.py --detach" in said
    rc, said = _retired(capsys)
    assert "land.py --detach" not in said and "archive_session" not in said
    assert "two" in said and "This chat has handed your page on." in said
    # Saved at last: it puts itself away, and the count starts again for any later save.
    monkeypatch.setattr(app, "_saved_on_github", lambda root: True)
    rc, said = _retired(capsys)
    assert "archive_session" in said
    monkeypatch.setattr(app, "_saved_on_github", lambda root: False)
    rc, said = _retired(capsys)
    assert "land.py --detach" in said
