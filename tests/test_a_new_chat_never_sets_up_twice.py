"""A chat that arrives in a copy that is already set up asks the person for nothing.

A chat on the person's computer, opened after the cloud chat had built the profile and
the brief and was drafting, asked for their resume again (2026-10-25): the profile was on
the cloud chat's branch, not yet on master, and nothing looked there. tools/setup_state.py
looks on master and on every branch not yet merged, and only a copy with no profile
anywhere is set up. The repos here are made in the test; the person is invented.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import setup_state as S  # noqa: E402

DONE = {f: "{}" for f in S.DONE_FILES}


def _git(cwd, *args, env=None):
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True,
                   env=dict(os.environ, GIT_AUTHOR_NAME="Morgan Ellis",
                            GIT_AUTHOR_EMAIL="morgan@example.com", GIT_COMMITTER_NAME="Morgan Ellis",
                            GIT_COMMITTER_EMAIL="morgan@example.com", **(env or {})))


@pytest.fixture
def repos(tmp_path):
    """(origin, a fresh clone of it, a function adding a branch with files)."""
    if not shutil.which("git"):
        pytest.skip("git is not here")
    origin = tmp_path / "origin.git"
    seed = tmp_path / "seed"
    _git(tmp_path, "init", "-q", "--bare", str(origin))
    _git(tmp_path, "init", "-q", "-b", "master", str(seed))
    (seed / "README.md").write_text("the app\n")
    _git(seed, "add", "README.md")
    _git(seed, "commit", "-q", "-m", "app")
    _git(seed, "remote", "add", "origin", str(origin))
    _git(seed, "push", "-q", "origin", "master")

    def branch(name, files, days_ago=0):
        _git(seed, "checkout", "-q", "-B", name, "master")
        for rel, text in files.items():
            p = seed / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)
            _git(seed, "add", rel)
        when = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - days_ago * 86400))
        _git(seed, "commit", "-q", "-m", name, env={"GIT_COMMITTER_DATE": when,
                                                    "GIT_AUTHOR_DATE": when})
        _git(seed, "push", "-q", "origin", name)
        _git(seed, "checkout", "-q", "master")

    clone = tmp_path / "clone"
    _git(tmp_path, "clone", "-q", str(origin), str(clone))
    return origin, clone, branch


def test_an_empty_copy_is_set_up(repos):
    _origin, clone, _branch = repos
    assert S.state(str(clone)) == ("none", "")


def test_a_profile_on_another_chats_branch_is_ready_and_nothing_is_asked(repos):
    _origin, clone, branch = repos
    branch("claude/setup-in-the-cloud", {**DONE, "profile/search.py": "QUERIES = []\n"})
    assert S.state(str(clone)) == ("ready-elsewhere", "origin/claude/setup-in-the-cloud")
    assert S.EXIT["ready-elsewhere"] == 0 and "ready on this computer" in S.SAY["ready-elsewhere"]
    assert "resume" not in S.SAY["ready-elsewhere"].lower()


def test_a_setup_under_way_elsewhere_is_left_to_finish(repos):
    _origin, clone, branch = repos
    branch("claude/setup-now", {"profile/person.json": "{}", S.MARKER: ""}, days_ago=2)
    assert S.state(str(clone))[0] == "running"
    assert "other chat" in S.SAY["running"] and S.EXIT["running"] == 3


def test_a_part_profile_pushed_minutes_ago_is_running_and_one_left_for_days_is_carried_on():
    assert S.judge({"profile/person.json"}, age_hours=0.5) == "running"
    assert S.judge({"profile/person.json"}, age_hours=50) == "unfinished"
    assert S.judge(set(S.DONE_FILES), age_hours=50) == "ready"
    assert S.judge(set(S.DONE_FILES) | {S.MARKER}, age_hours=50) == "running"
    assert S.judge({"README.md"}, age_hours=0) == "none"


def test_a_profile_here_or_on_master_is_ready(repos, tmp_path):
    _origin, clone, branch = repos
    for rel in S.DONE_FILES:
        p = clone / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("{}")
    assert S.state(str(clone), fetch=False) == ("ready", "")
