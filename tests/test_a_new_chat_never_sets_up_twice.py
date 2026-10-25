"""A chat that arrives in a copy that is already set up asks the person for nothing.

A chat on the person's computer, opened after the cloud chat had built the profile and
the brief and was drafting, asked for their resume again (2026-10-25): the profile was on
the cloud chat's branch, not yet on master, and nothing looked there. tools/setup_state.py
looks on master and on every branch not yet merged, and only a copy with no profile
anywhere is set up. It reads place.setup_state(), the rule /setup's own first step reads,
so the two never tell one person two different things. The repos here are made in the
test; the person is invented.
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

import json  # noqa: E402

import place  # noqa: E402
import setup_state as S  # noqa: E402

DONE = {"profile/person.json": "{}", "profile/01-candidate-profile.md": "# Morgan Ellis\n",
        "profile/CLAUDE.md": "# Morgan Ellis\n"}


def _mark(**setup):
    """profile/place.json as /setup writes it (place.py started, place.py finished)."""
    return {"profile/place.json": json.dumps({"setup": setup})}


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
    today = time.strftime("%Y-%m-%d")
    branch("claude/setup-now", {"profile/person.json": "{}",
                                **_mark(started=today, chat="cloud-chat")})
    assert S.state(str(clone))[0] == "running"
    assert S.SAY["running"] == place.STILL_GOING and S.EXIT["running"] == 3


def test_a_setup_that_stopped_days_ago_is_carried_on(repos):
    _origin, clone, branch = repos
    branch("claude/setup-then", {"profile/person.json": "{}",
                                 **_mark(started="2026-10-20", chat="cloud-chat")},
           days_ago=2)
    assert S.state(str(clone))[0] == "unfinished" and S.SAY["unfinished"] == place.STOPPED


def test_it_and_setups_own_first_step_say_the_same_about_one_setup(repos, monkeypatch, capsys):
    """A copy whose master holds the first profile and /setup's mark, started today by a
    cloud chat: COMPUTER.md's check said "unfinished, I'll carry it on" while /setup's said
    "still going in your other chat", and the marker it relied on was written by nothing
    (found 2026-10-25)."""
    _origin, clone, branch = repos
    branch("master", {**DONE, **_mark(started=time.strftime("%Y-%m-%d"),
                                      chat="cloud-chat")})
    _git(clone, "pull", "-q", "origin", "master")
    monkeypatch.setattr(S, "ROOT", str(clone))
    monkeypatch.setattr(place, "ROOT", str(clone))
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "laptop-chat")
    monkeypatch.delenv("CLAUDE_CODE_REMOTE_SESSION_ID", raising=False)
    assert S.main(["--no-fetch"]) == 3
    said = capsys.readouterr().out.splitlines()
    assert said == ["running", place.STILL_GOING]
    assert place.setup_state(fetch=False)["say"] == said[1]
    # The chat that is setting up hears nothing, and carries on with /setup.
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "cloud-chat")
    assert S.main(["--no-fetch"]) == 4
    assert capsys.readouterr().out.splitlines() == ["unfinished"]


def test_a_profile_here_or_on_master_is_ready(repos, tmp_path):
    _origin, clone, branch = repos
    for rel in DONE:
        p = clone / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("{}")
    assert S.state(str(clone), fetch=False) == ("ready", "")


def test_the_line_for_a_new_computer_names_the_copy_and_the_page(repos):
    _origin, clone, _branch = repos
    _git(clone, "remote", "set-url", "origin", "https://github.com/morgan-ellis/my-job-search.git")
    assert S.this_copy(str(clone)) == ("morgan-ellis", "my-job-search")
    line = S.paste(*S.this_copy(str(clone)))
    assert line == ("Open my job search on this computer: github.com/morgan-ellis/my-job-search. "
                    "Steps: https://github.com/aranculleton/last-job-search/blob/master/COMPUTER.md")
    with open(os.path.join(ROOT, "COMPUTER.md"), encoding="utf-8") as fh:
        page = fh.read()
    assert "Open my job search on this computer" in page and S.PAGE.endswith("/COMPUTER.md")
