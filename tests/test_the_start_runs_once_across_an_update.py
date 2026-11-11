"""A chat goes round the start once, even across the update that taught the start to carry on.

The maintainer's copy taking 4.15.0 (2026-11-11): the start printed its steps, the first was
the day's update check, the update it took changed how a chat starts, and the check said "run
it again now", so the chat ran the whole start a second time. A start from 4.15.0 on runs the
check itself and carries on from the new code by itself (test_the_start_reads_waiting_work_
quickly). An older start cannot be changed, and every copy still on one meets this once, on
the update that leaves it: so the update does it. The check, from the files it just brought
in, runs the new start itself and prints its steps in place of the old ones, never a "run it
again". Invented data only: the example person.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import app_setup  # noqa: E402
import repo_files  # noqa: E402

GIT_ENV = dict(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com", GIT_COMMITTER_NAME="t",
               GIT_COMMITTER_EMAIL="t@example.com", GIT_TERMINAL_PROMPT="0")


def _git(cwd, *args):
    r = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=dict(os.environ, **GIT_ENV))
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout.strip()


def _app_tree(into):
    """The app as this tree holds it (what is not committed yet included), with no test
    suite: what a template copy is made of."""
    for name in repo_files.tracked(new=True):
        if name.startswith("tests/"):
            continue
        src = os.path.join(ROOT, name)
        if not os.path.isfile(src):
            continue
        dst = os.path.join(into, name)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)


def _older_start(root):
    """Make this copy's start one from before 4.15.0: one that prints the day's update check
    as a step and never carries itself on to the code the check brings in."""
    path = os.path.join(root, "tools", "app.py")
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    assert app_setup.START_RUNS_AGAIN in text
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text.replace(app_setup.START_RUNS_AGAIN, "LJS_START_OLDER"))


@pytest.fixture
def copy(tmp_path):
    """(their copy, made from the app before 4.15.0 and set up as the example person; the app
    on GitHub, one version on; the environment a chat runs in)."""
    app, me, home = tmp_path / "app", tmp_path / "copy", tmp_path / "home"
    home.mkdir()
    _app_tree(app)
    _git(tmp_path, "init", "-q", "-b", "master", str(app))
    _git(app, "add", "-A")
    _git(app, "commit", "-q", "-m", "the app, one version on")
    _app_tree(me)
    _older_start(me)
    _git(tmp_path, "init", "-q", "-b", "master", str(me))
    _git(me, "add", "-A")
    _git(me, "commit", "-q", "-m", "Initial commit")
    shutil.copytree(os.path.join(ROOT, "profile.example"), me / "profile",
                    ignore=shutil.ignore_patterns("state"))
    for name in os.listdir(os.path.join(ROOT, "profile.example", "state")):
        if name == "README.md":         # what the folder is for, not one of the files
            continue
        src = os.path.join(ROOT, "profile.example", "state", name)
        if os.path.isdir(src):
            shutil.copytree(src, str(me / name), dirs_exist_ok=True)
        else:
            shutil.copy(src, str(me / name))
    _git(me, "add", "-A", "-f", "profile", "job_search_tracker.csv", "network_contacts.csv",
         "network_threads.csv", "job_scraper")
    _git(me, "commit", "-q", "-m", "set me up")
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("LJS_", "CLAUDE_CODE_")) and k not in ("GIT_DIR", "GIT_WORK_TREE")}
    env.update(GIT_ENV, HOME=str(home), USERPROFILE=str(home), LJS_APP_URL=str(app),
               LJS_COPY="private", PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
    return me, app, env


def _run(me, env, *args):
    r = subprocess.run([sys.executable, *args], cwd=str(me), env=env, capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=900)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def _started_on(me) -> str:
    """The commit this checkout's start last spoke for (app_setup.START_HEAD)."""
    git_dir = _git(me, "rev-parse", "--absolute-git-dir")
    with open(os.path.join(git_dir, app_setup.START_HEAD), encoding="utf-8") as fh:
        return fh.read().strip()


def test_the_update_an_older_start_asked_for_carries_the_start_on_itself(copy):
    me, _app, env = copy
    # The older start spoke (as every chat's first command) for the commit the copy is on, and
    # printed the day's update check as its first step; the chat runs that step.
    code, said = _run(me, env, "-c", "import sys; sys.path.insert(0, 'tools'); "
                      "import app_setup; app_setup.note_start()")
    assert code == 0, said
    old = _git(me, "rev-parse", "HEAD")
    assert _started_on(me) == old
    code, out = _run(me, env, "tools/sync_app.py", "--on", "m", "--tools", "none")
    assert code == 0, out
    assert _git(me, "rev-parse", "HEAD") != old, "the update was taken"
    # Never round the start again: the new start's own steps, here, once.
    assert "run it again" not in out and "run python3 tools/app.py start" not in out, out
    assert app_setup.START_CHANGED not in out and app_setup.PAGE_NOT_YET not in out, out
    assert out.count(app_setup.START_HERE_SAY) == 1, out
    steps = out[out.index(app_setup.START_HERE_SAY):]
    assert "app start: set up" in steps and "\n1. " in steps, out
    # It took no update check of its own (the update is in), and never a third start.
    assert "tools/sync_app.py --on" not in steps and steps.count("app start:") == 1, out
    # Said after what the check itself printed, which comes first.
    assert out.index("new commit") < out.index(app_setup.START_HERE_SAY), out
    # The new start spoke for the new code: the next check says nothing more about it.
    assert _started_on(me) == _git(me, "rev-parse", "HEAD")


def test_a_start_that_carries_itself_on_hears_only_the_line_it_leaves_out(monkeypatch):
    """Inside a start from 4.15.0 on (or a wake, or the brief's run), the check starts
    nothing: that command runs again on the new code by itself. A start from 4.15.0 marks
    nothing, so the code the update replaced tells it. A chat that ran no start in this
    checkout has no steps to replace."""
    monkeypatch.setattr(app_setup, "_start_change", lambda: (app_setup.START_CHANGED, "abc123"))
    monkeypatch.setattr(app_setup, "_replaced", lambda: "def456")
    monkeypatch.setattr(app_setup, "_runs_again", lambda commit: False)
    monkeypatch.delenv(app_setup.IN_COMMAND, raising=False)
    assert app_setup.start_after_sync() == app_setup.START_HERE
    monkeypatch.setenv(app_setup.IN_COMMAND, "1")
    assert app_setup.start_after_sync() == app_setup.START_CHANGED
    monkeypatch.delenv(app_setup.IN_COMMAND)
    monkeypatch.setattr(app_setup, "_runs_again", lambda commit: commit == "def456")
    assert app_setup.start_after_sync() == app_setup.START_CHANGED
    monkeypatch.setattr(app_setup, "_runs_again", lambda commit: commit == "abc123")
    assert app_setup.start_after_sync() == app_setup.START_CHANGED
    monkeypatch.setattr(app_setup, "_runs_again", lambda commit: False)
    monkeypatch.setattr(app_setup, "_start_change", lambda: (app_setup.START_CHANGED, ""))
    assert app_setup.start_after_sync() == app_setup.START_CHANGED
    monkeypatch.setattr(app_setup, "_start_change", lambda: ("", "abc123"))
    assert app_setup.start_after_sync() == ""


def test_the_mark_is_the_one_the_start_sets_and_every_check_it_runs_carries_it():
    import app
    import inspect
    import brief
    assert app.START_UPDATED == app_setup.START_RUNS_AGAIN
    assert "app_setup.IN_COMMAND" in inspect.getsource(app.days_check)
    assert app_setup.IN_COMMAND in inspect.getsource(brief.start)


def test_a_start_that_cannot_run_here_leaves_the_line_that_sends_the_chat_round(monkeypatch):
    """Never nothing: where the new start fails or runs out of time inside the check, the chat
    is told to start again, as before."""
    def slow(*a, **k):
        raise subprocess.TimeoutExpired("app.py start", 300)
    monkeypatch.setattr(app_setup.subprocess, "run", slow)
    assert app_setup.start_here() == [app_setup.START_CHANGED]
    monkeypatch.setattr(app_setup.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(
        a, 2, stdout="Traceback (most recent call last):\n", stderr=""))
    assert app_setup.start_here() == [app_setup.START_CHANGED]
