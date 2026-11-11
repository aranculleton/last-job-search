"""The start reads the work other chats left waiting quickly, however often they took master.

A helper chat in the maintainer's copy (H-2, 2026-11-10): `app.py start --listen --helper` ran
for over two minutes before it printed anything, and its first step is "say this to the person
at once". Nearly all of it was the look at other chats' branches (land.waiting): a git call for
every merge each branch had made of master (every page update makes one), and the whole look
twice in one start (the work stranded off master, and the stuck states). Now a branch costs a
few git calls whatever it merged, and the look is made once while nothing it reads moved.
Invented people and data only.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import land  # noqa: E402
import pytest  # noqa: E402

import test_a_chat_lands_its_work_in_one_command as L  # noqa: E402
from test_a_chat_lands_its_work_in_one_command import git, write  # noqa: E402


@pytest.fixture
def copy(tmp_path, monkeypatch):
    return L.copy.__wrapped__(tmp_path, monkeypatch)


def _counted(monkeypatch):
    calls = []
    real = land._git

    def counting(root, *args, **k):
        calls.append(args[0] if args else "")
        return real(root, *args, **k)
    monkeypatch.setattr(land, "_git", counting)
    return calls


def test_a_branch_that_took_master_many_times_costs_a_few_git_calls(copy, monkeypatch):
    origin, chat, other = copy
    # A chat whose page updates took master eight times while it worked.
    for n in range(8):
        write(other, f"profile/round{n}.md", f"round {n}\n")
        git(other, "add", "-A")
        git(other, "commit", "-q", "-m", f"another chat's round {n}")
        git(other, "push", "-q", "origin", "HEAD:master")
        git(chat, "fetch", "-q", "origin")
        write(chat, f"profile/notes{n}.md", f"note {n}\n")
        git(chat, "add", "-A")
        git(chat, "commit", "-q", "-m", f"a note {n}")
        git(chat, "merge", "-q", "--no-edit", "origin/master")
    git(chat, "push", "-q", "origin", "claude/chat-1")
    git(other, "fetch", "-q", "origin")
    calls = _counted(monkeypatch)
    assert land.waiting(str(other)) == ["origin/claude/chat-1"]
    assert len(calls) <= 8, calls
    # Asked again with nothing moved (the start asks twice): no branch is read again.
    calls.clear()
    assert land.waiting(str(other)) == ["origin/claude/chat-1"]
    assert land.stranded(str(other)) == {}
    # (the one log left is the age of the work waiting, which stranded asks for)
    assert len(calls) <= 8 and calls.count("log") <= 1, calls
    # Something moved: read again, and the answer follows it.
    write(other, "profile/later.md", "later\n")
    git(other, "add", "-A")
    git(other, "commit", "-q", "-m", "later")
    git(other, "push", "-q", "origin", "HEAD:master")
    git(other, "fetch", "-q", "origin")
    assert land.waiting(str(other)) == ["origin/claude/chat-1"]


# D1, H-2 (2026-11-10): the start printed the day's update check as a step, and the update it
# took changed the start's own files on 12 of 15 updates, so the chat was told to run the whole
# start again. The start runs the check itself now, and where it took an update it runs again
# on the new code, once, with what the check printed.

def test_the_start_runs_the_days_check_itself_and_once_more_on_the_new_code(tmp_path,
                                                                             monkeypatch, capsys):
    import subprocess as sp
    import types
    import app
    import app_listen
    import app_setup
    said = "sync_app: brought in the app's update.\n" + app_setup.START_CHANGED + "\n"
    monkeypatch.setattr(app, "days_check", lambda on, chat, tools="", new_chat=False: {
        "ran": True, "rc": 0, "said": said, "landed": True, "before": "abc"})
    monkeypatch.setattr(app_setup, "_local_file", lambda name: str(tmp_path / name))
    again = []
    real = sp.run

    def run(cmd, *args, env=None, **k):
        if cmd[0] != sys.executable:
            return real(cmd, *args, env=env, **k)
        again.append(env[app.START_UPDATED])
        return types.SimpleNamespace(returncode=0)
    monkeypatch.setattr(sp, "run", run)
    monkeypatch.delenv(app.START_UPDATED, raising=False)
    asked = []
    monkeypatch.setattr(app_setup, "start", lambda **k: asked.append(k) or (
        0, ["app start: set up", "Claude, do this:", "1. Carry on with what the person asked."]))
    monkeypatch.setattr(app_listen, "shape", lambda code, lines, **k: lines)
    monkeypatch.setattr(app, "own_tests_first", lambda: "")
    a = types.SimpleNamespace(argv=["start", "--on", "m"], paste=False, work="", on="m",
                              tools="none", page="", chat="", listen=False, helper=False, dump="")
    assert app.cmd_start(a) == 0
    assert len(again) == 1 and asked == [], "the steps come from the new code, never the old"
    # The run made again on the new code: the check's lines, its own steps, nothing to redo.
    monkeypatch.setenv(app.START_UPDATED, again[0])
    capsys.readouterr()
    assert app.cmd_start(a) == 0
    out = capsys.readouterr().out
    assert len(again) == 1 and asked[0]["checked"] is True
    assert "update check ran in this command" in out and "brought in the app's update" in out
    assert app_setup.START_CHANGED not in out and "run it again" not in out
    assert out.index("brought in the app's update") < out.index("1. Carry on")


def test_the_update_check_inside_the_start_never_sends_the_chat_to_start_again(monkeypatch, capsys):
    """E-15 (2026-11-10): before a page exists the update check says "run python3 tools/app.py
    start", and run inside the start that sent the chat round once more."""
    import types
    import app
    import app_listen
    import app_setup
    said = "sync_app: up to date with the app.\n" + app_setup.PAGE_NOT_YET + "\n"
    monkeypatch.setattr(app, "days_check", lambda on, chat, tools="", new_chat=False: {
        "ran": True, "rc": 0, "said": said, "landed": False, "before": "abc"})
    monkeypatch.delenv(app.START_UPDATED, raising=False)
    monkeypatch.setattr(app_setup, "start", lambda **k: (
        0, ["app start: set up, page to publish", "Claude, do this:", "1. Build the page."]))
    monkeypatch.setattr(app_listen, "shape", lambda code, lines, **k: lines)
    monkeypatch.setattr(app, "own_tests_first", lambda: "")
    a = types.SimpleNamespace(argv=["start"], paste=False, work="", on="m", tools="none",
                              page="", chat="", listen=False, helper=False, dump="")
    assert app.cmd_start(a) == 0
    out = capsys.readouterr().out
    assert "up to date with the app" in out and "app.py start and do what it prints" not in out


def test_a_branch_gone_from_github_leaves_the_copys_list(copy):
    """D14 (2026-11-10): 169 merged chat branches stayed, and every page update fetched them
    all. A branch deleted on GitHub leaves this copy's list on the next fetch."""
    origin, chat, other = copy
    write(chat, "profile/notes.md", "work\n")
    git(chat, "add", "-A")
    git(chat, "commit", "-q", "-m", "work")
    git(chat, "push", "-q", "origin", "claude/chat-1")
    assert land.fetch_waiting(str(other))
    assert git(other, "rev-parse", "-q", "--verify", "refs/remotes/origin/claude/chat-1",
               check=False).returncode == 0
    git(origin, "branch", "-D", "claude/chat-1")
    assert land.fetch_waiting(str(other))
    assert git(other, "rev-parse", "-q", "--verify", "refs/remotes/origin/claude/chat-1",
               check=False).returncode != 0


def test_a_new_helper_says_the_link_before_the_update_check_runs(monkeypatch, capsys):
    """The review of D3 (2026-11-11): with the update check inside the start, the helper's
    "say this to the person at once" line came only after the check ended."""
    import types
    import app
    import app_listen
    import app_setup
    url = "https://claude.ai/artifact/example-page"
    monkeypatch.setattr(app_setup, "page_record", lambda: {"url": url})
    monkeypatch.setattr(app_listen, "role", lambda chat, listen=False, url="": "listener")
    before = []

    def check(on, chat, tools="", new_chat=False):
        before.append(capsys.readouterr().out)
        return {"ran": False}
    monkeypatch.setattr(app, "days_check", check)
    monkeypatch.delenv(app.START_UPDATED, raising=False)
    monkeypatch.setattr(app_setup, "start", lambda **k: (
        0, ["app start: set up", "Claude, do this:", "Carry on."]))
    monkeypatch.setattr(app, "own_tests_first", lambda: "")
    a = types.SimpleNamespace(argv=["start"], paste=False, work="", on="m", tools="none",
                              page="", chat="session_HELPER", listen=False, helper=True, dump="")
    assert app.cmd_start(a) == 0
    first = app_listen.helper_first(url)
    assert before and first in before[0], before
    assert first not in capsys.readouterr().out, "said once"
