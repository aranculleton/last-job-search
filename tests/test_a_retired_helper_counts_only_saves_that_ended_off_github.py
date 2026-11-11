"""A retired helper counts only saves that ended off GitHub, and its card names it plainly.

`_retired_tries` counted every run of `retired`: three wakes during one slow landing started a
second save and then gave up on a save still running, and the --wait path said "the next turn
runs retired again", which started another save; the To do card named "Job search page", the
title every helper has (review of fix/helpers, item 5; the reviewer's probe). Now a save still
landing starts nothing and re-arms the wait, only a save that ended without reaching GitHub
counts, and giving up renames the chat to a name of its own that the card gives. Invented ids.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import pytest  # noqa: E402

import app  # noqa: E402
import app_listen  # noqa: E402
import land  # noqa: E402
import save_state  # noqa: E402

CHAT = "session_EXAMPLERETIREDHELPER"


@pytest.fixture
def checkout(tmp_path, monkeypatch):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    monkeypatch.setenv("LJS_STATE", str(tmp_path))
    monkeypatch.setattr(app_listen, "retired_here", lambda chat: True)
    monkeypatch.setattr(app_listen, "this_chat", lambda chat="": chat or CHAT)
    monkeypatch.setattr(save_state, "unsaved", lambda root=None: [])
    return tmp_path


def _go(capsys, wait=False):
    rc = app.cmd_retired(argparse.Namespace(chat=CHAT, wait=wait))
    return rc, capsys.readouterr().out


def test_wakes_during_one_slow_landing_start_nothing_and_never_give_up(checkout, monkeypatch,
                                                                        capsys):
    monkeypatch.setattr(app, "_saved_on_github", lambda root: False)
    landing = {"on": False}
    monkeypatch.setattr(land, "landing", lambda root=None: landing["on"])
    _rc, first = _go(capsys)
    assert "land.py --detach" in first
    landing["on"] = True
    for _ in range(3):
        _rc, said = _go(capsys)
        assert "land.py --detach" not in said and "after two tries" not in said
        assert "--wait" in said                                  # the wait re-armed
    # The wait that times out re-arms itself; it never asks for retired, which starts a save.
    monkeypatch.setattr(app, "RETIRED_WAIT_S", 0)
    rc, said = _go(capsys, wait=True)
    assert rc != 0 and "--wait" in said and "runs python3 tools/app.py retired --chat" not in said


def test_only_saves_that_ended_off_github_count(checkout, monkeypatch, capsys):
    monkeypatch.setattr(app, "_saved_on_github", lambda root: False)
    monkeypatch.setattr(land, "landing", lambda root=None: False)
    outs = [_go(capsys)[1] for _ in range(3)]
    assert "land.py --detach" in outs[0] and "land.py --detach" in outs[1]
    assert "after two tries" in outs[2]
    # It renames itself to a name of its own, and the card gives that name.
    assert "set_session_title" in outs[2]
    batch = next(ln.strip() for ln in outs[2].splitlines() if ln.strip().endswith(".json"))
    (entry,) = json.load(open(batch, encoding="utf-8"))
    body = json.load(open(entry["file_path"], encoding="utf-8"))
    assert body["title"] != app_listen.HELPER_CHAT_TITLE and body["title"] in outs[2]
