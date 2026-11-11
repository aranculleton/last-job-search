"""The person's own tests an update broke are brought in line first, before any other work.

A person's copy (2026-11-05): an update changed what the network state reads, and five of the
person's own tests failed. The steps said Claude brings them in line in the same turn as the
sync, but the update had been taken by another run, the page's helper took two jobs, and
neither could be saved, since every landing runs those tests: the landing said only "not
green". Now the last run's result is kept in the git folder, keyed on the app's code as well
as the tests; every command that starts work says the step first until they pass; a landing
stopped only by them says so, with the step, and keeps the work; and master bringing in an
update checks them here too. Invented people only.
"""
from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import land  # noqa: E402
import sync_app  # noqa: E402
import pytest  # noqa: E402

import test_a_chat_lands_its_work_in_one_command as L  # noqa: E402
from test_a_chat_lands_its_work_in_one_command import _branches, git, write  # noqa: E402


@pytest.fixture
def copy(tmp_path, monkeypatch):
    return L.copy.__wrapped__(tmp_path, monkeypatch)


def _repo(tmp_path, passing=False):
    for k, v in (("GIT_AUTHOR_NAME", "t"), ("GIT_AUTHOR_EMAIL", "t@example.com"),
                 ("GIT_COMMITTER_NAME", "t"), ("GIT_COMMITTER_EMAIL", "t@example.com")):
        os.environ.setdefault(k, v)
    root = str(tmp_path / "copy")
    # Named, never the machine's default: a newer git (the Mac runner's) starts on "main".
    subprocess.run(["git", "init", "-q", "-b", "master", root], check=True)
    write(root, "tools/state_rule.py", "LIMIT = 2\n")
    write(root, "profile/tests/test_mine.py",
          "import os, sys\nsys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'tools'))\n"
          "import state_rule\n\ndef test_limit():\n    assert state_rule.LIMIT == 2\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "start")
    return root


def _update(root, value):
    write(root, "tools/state_rule.py", f"LIMIT = {value}\n")
    git(root, "commit", "-q", "-am", "Sync from the app: 1 new commit(s)")


def test_the_step_comes_first_until_the_tests_pass_and_then_never(tmp_path):
    root = _repo(tmp_path)
    sync_app.own_tests(root)                     # all pass: nothing owed
    assert sync_app.own_tests_step(root) == ""
    _update(root, 3)
    sync_app.own_tests(root)
    step = sync_app.own_tests_step(root)
    # Since 2026-11-06 it holds no work: saves set them aside and the own-tests improvement is
    # queued for the background (tests/test_saves_queue_and_check_quickly.py).
    assert step.startswith("Claude: 1 of the person's own tests fail after an update"), step
    assert "test_limit" in step and "own-tests" in step and sync_app.OWN_CHECKS_SAID in step
    assert "Nothing waits on them" in step and "before any other work" not in step
    # Said again by every command that starts work, until they pass: brought in line here
    # (not committed yet), it is checked again and goes.
    assert sync_app.own_tests_step(root) == step
    write(root, "profile/tests/test_mine.py", open(os.path.join(root, "profile/tests/test_mine.py"))
          .read().replace("== 2", "== 3"))
    assert sync_app.own_tests_step(root) == ""


def test_a_record_made_on_other_app_code_is_checked_again_by_the_upgrade(tmp_path, monkeypatch):
    """The record was keyed on the tests' own tree alone: made before an update ("all pass"),
    it stayed true after it, so the own-tests upgrade never saw the five. Since D2 (2026-11-10)
    the check again runs in the background: the upgrade's look waited 71 seconds on it."""
    root = _repo(tmp_path)
    sync_app.own_tests(root)
    _update(root, 4)                               # arrived with no own-tests run here
    started = []
    monkeypatch.setattr(sync_app, "_spawn", lambda cmd, **k: started.append(cmd))
    assert sync_app.own_tests_owed(root) == []     # an entry point reads, and runs nothing
    assert started == []
    assert sync_app.own_tests_owed(root, clean_too=True) == []
    assert len(started) == 1 and started[0][-1] == "--own-tests-record"
    sync_app.own_tests(root)                       # what the background run does
    assert sync_app.own_tests_owed(root, clean_too=True)[0].endswith("test_mine::test_limit")
    assert sync_app.own_tests_step(root) != ""


LAND_OWN_RED = [sys.executable, "-c", (
    "print('  pytest (profile/tests, on this person)     FAIL'); "
    "print('      FAILED profile/tests/test_network_state.py::test_quiet - AssertionError: 1'); "
    "print('      Claude, not for the person: their own tests, 1 now fail after this update.'); "
    "print('1 passed, 1 failed, 0 skipped'); print('Not green. Do not push to master.'); "
    "raise SystemExit(1)")]


def test_a_landing_stopped_only_by_them_says_so_keeps_the_work_and_names_the_step(copy, capsys):
    origin, chat, other = copy
    write(chat, "profile/notes.md", "finished work\n")
    code = land.main(["--message", "Finished work"], root=str(chat), check=LAND_OWN_RED,
                     sleep=lambda s: None)
    out = capsys.readouterr().out
    assert code == 1
    assert out.startswith(land.OWN_TESTS_HEAD), out
    assert "the work waits on claude/chat-1" in out and land.OWN_TESTS_DO in out, out
    # Never dropped: committed, and pushed where the next landing brings it in.
    assert "claude/chat-1" in _branches(origin)
    # Every command that starts work in this copy says the step now.
    rec = sync_app.own_tests_record(str(chat))
    assert rec["failures"][0][0] == "profile/tests/test_network_state.py::test_quiet", rec
    # A generic red is still a generic red.
    assert land.own_tests_only("  tests      FAIL\n") is None
    assert land.own_tests_only(
        "  pytest (profile/tests, on this person)     FAIL\n      Claude, not for the person: no "
        "update of the app is in this change\n") is None


def test_master_bringing_in_an_update_checks_them_here_too(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    ran = []
    monkeypatch.setattr(sync_app, "ROOT", root)
    # In the background since D2: nothing waits on the person's whole suite.
    monkeypatch.setattr(sync_app, "own_tests_later", lambda r=None: ran.append(r))
    monkeypatch.setattr(sync_app, "_driver", lambda: None)
    origin = str(tmp_path / "origin.git")
    # The bare origin names master as its own HEAD. Left to the machine's default, a newer
    # git (the Mac runner's, 2026-11-06) points it at "main", which nothing pushed: the clone
    # then checks out no files, the write below is untracked, and `commit -a` finds nothing.
    git(tmp_path, "init", "-q", "--bare", "-b", "master", origin)
    git(root, "remote", "add", "origin", origin)
    git(root, "push", "-q", "origin", "HEAD:master")
    other = str(tmp_path / "other")
    git(tmp_path, "clone", "-q", origin, other)
    assert os.path.isfile(os.path.join(other, "tools", "state_rule.py"))
    write(other, "tools/state_rule.py", "LIMIT = 5\n")
    git(other, "commit", "-q", "-am", "Sync from the app: 1 new commit(s)")
    git(other, "push", "-q", "origin", "HEAD:master")
    assert sync_app.pull_master() == 0
    assert ran == [None]


def test_start_and_the_briefs_run_say_it_first(monkeypatch, capsys):
    import types
    import app
    import app_listen
    import app_setup
    monkeypatch.setattr(sync_app, "is_the_app", lambda root=None: False)
    monkeypatch.setattr(sync_app, "own_tests_step", lambda root=None: "Claude, first, before any other work: X")
    # The start runs the day's update check itself (D1): never the real one, on this checkout.
    monkeypatch.setattr(app, "days_check", lambda on, chat, tools="": {"ran": False})
    monkeypatch.setattr(app_setup, "start", lambda **kw: (0, ["app start: ready", "Claude, do this:", "1. the work"]))
    monkeypatch.setattr(app_listen, "shape", lambda code, lines, **kw: lines)
    a = types.SimpleNamespace(paste=False, work="", on="", tools="", page="", dump="", chat="",
                              listen=False, helper=False)
    assert app.cmd_start(a) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[:3] == ["app start: ready", "Claude, first, before any other work: X", "Claude, do this:"]
    # The brief's run reads it in a fresh process, after the update check, before anything else.
    src = open(os.path.join(ROOT, "tools", "brief.py"), encoding="utf-8").read()
    start = src[src.index("def start("):src.index("def setup_waiting(")]
    assert start.index("own_tests_first") < start.index("page_first(url, argv)")


# D2 (2026-11-10): the person's own tests, 71 seconds in one copy, ran inside the update check
# and could run inside the start. The update check starts them in the background now, once a
# commit, and a command that starts work runs again only the ones that failed.

def test_the_update_check_starts_them_in_the_background_once(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    started = []
    monkeypatch.setattr(sync_app, "_spawn", lambda cmd, **k: started.append(cmd))
    assert sync_app.own_tests_later(root) is True
    assert started and started[0][-1] == "--own-tests-record"
    assert sync_app.own_tests_later(root) is False and len(started) == 1
    _update(root, 7)
    assert sync_app.own_tests_later(root) is True and len(started) == 2


def test_only_the_tests_that_failed_are_run_again_when_theirs_change(tmp_path):
    root = _repo(tmp_path)
    ran = os.path.join(str(tmp_path), "slow-ran")
    write(root, "profile/tests/test_slow.py",
          "def test_slow():\n    open(%r, 'a').write('x')\n" % ran)
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "a slow one")
    _update(root, 3)
    sync_app.own_tests(root)
    os.remove(ran)
    assert sync_app.own_tests_step(root)
    write(root, "profile/tests/test_mine.py", open(os.path.join(root, "profile/tests/test_mine.py"))
          .read().replace("== 2", "== 3"))
    assert sync_app.own_tests_step(root) == ""
    assert not os.path.exists(ran), "only the test that failed was run again"
