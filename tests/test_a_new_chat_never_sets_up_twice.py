"""A chat that arrives in a copy that is already set up asks the person for nothing.

A chat on the person's computer, opened after the cloud chat had built the profile and
the brief and was drafting, asked for their resume again (2026-10-25): the profile was on
the cloud chat's branch, not yet on master, and nothing looked there. place.setup_state()
looks on master and on every branch not yet merged, and only a copy with no profile
anywhere is set up. It is the one detector, and `python3 tools/app.py start`, the one
command every chat runs first (COMPUTER.md, RUNBOOK.md step 3 and /setup's own first step
included), says its answer, so no two commands tell one person two different things. The
repos here are made in the test; the person is invented.
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

import app  # noqa: E402
import app_setup  # noqa: E402
import place  # noqa: E402

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


def _state(root, fetch=True):
    """place.setup_state()'s (state, ref) for the copy at `root`, as start reads it."""
    old = place.ROOT
    place.ROOT = str(root)
    try:
        got = place.setup_state(fetch=fetch)
    finally:
        place.ROOT = old
    return got["state"], ("" if got.get("ref") in (None, "HEAD") else got["ref"])


def _start_head(root, monkeypatch):
    """The first line `app.py start` prints for the copy at `root`."""
    monkeypatch.setattr(place, "ROOT", str(root))
    monkeypatch.setattr(app_setup, "repo_kind", lambda runner=None: {"kind": "private",
                                                                     "owner": "", "name": ""})
    monkeypatch.setattr(app_setup, "_sync_stale", lambda: False)
    monkeypatch.setattr(app_setup, "set_up", lambda: False)
    real = place.setup_state
    monkeypatch.setattr(place, "setup_state", lambda **kw: real(**dict(kw, profile=None)))
    return app_setup.start(on="test", tools="none")[1][0]


def test_an_empty_copy_is_set_up(repos):
    _origin, clone, _branch = repos
    assert _state(clone) == ("none", "")


def test_a_profile_on_another_chats_branch_is_ready_and_nothing_is_asked(repos, monkeypatch):
    _origin, clone, branch = repos
    branch("claude/setup-in-the-cloud", {**DONE, "profile/search.py": "QUERIES = []\n"})
    assert _state(clone) == ("branch", "origin/claude/setup-in-the-cloud")
    head = _start_head(clone, monkeypatch)
    assert head == "app start: set up elsewhere (branch)" and "resume" not in head.lower()


def test_a_setup_under_way_elsewhere_is_left_to_finish(repos, monkeypatch):
    _origin, clone, branch = repos
    today = time.strftime("%Y-%m-%d")
    branch("claude/setup-now", {"profile/person.json": "{}",
                                **_mark(started=today, chat="cloud-chat")})
    assert _state(clone)[0] == "going"
    assert _start_head(clone, monkeypatch) == "app start: setup going in another chat"


def test_a_setup_that_stopped_days_ago_is_carried_on(repos):
    _origin, clone, branch = repos
    branch("claude/setup-then", {"profile/person.json": "{}",
                                 **_mark(started="2026-10-20", chat="cloud-chat")},
           days_ago=2)
    old = place.ROOT
    place.ROOT = str(clone)
    try:
        got = place.setup_state()
    finally:
        place.ROOT = old
    assert got["state"] == "stopped" and got["say"] == place.STOPPED


def test_every_chat_hears_one_answer_about_one_setup(repos, monkeypatch):
    """A copy whose master holds the first profile and /setup's mark, started today by a
    cloud chat: a computer chat's own check said "unfinished, I'll carry it on" while
    /setup's said "still going in your other chat", and the marker it relied on was written
    by nothing (found 2026-10-25). One detector now, and the chat setting up hears nothing."""
    _origin, clone, branch = repos
    branch("master", {**DONE, **_mark(started=time.strftime("%Y-%m-%d"),
                                      chat="cloud-chat")})
    _git(clone, "pull", "-q", "origin", "master")
    monkeypatch.setattr(place, "ROOT", str(clone))
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "laptop-chat")
    monkeypatch.delenv("CLAUDE_CODE_REMOTE_SESSION_ID", raising=False)
    got = place.setup_state(fetch=False)
    assert got["state"] == "going" and got["say"] == place.STILL_GOING
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "cloud-chat")
    assert place.setup_state(fetch=False)["state"] == "self"


def test_a_profile_here_or_on_master_is_ready(repos, tmp_path):
    _origin, clone, branch = repos
    for rel in DONE:
        p = clone / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("{}")
    assert _state(clone, fetch=False) == ("here", "")


def test_the_line_for_a_new_computer_names_the_copy_and_the_page(monkeypatch, capsys):
    """`app.py start --paste` is the line a person pastes into the first chat on their
    computer (COMPUTER.md), naming their copy; it was a command of its own."""
    line = app.paste_line("morgan-ellis", "my-job-search")
    assert line == ("Open my job search on this computer. My copy is github.com/morgan-ellis/"
                    "my-job-search. Follow github.com/aranculleton/last-job-search/blob/master/"
                    "COMPUTER.md")
    assert line == place.computer_paste("morgan-ellis", "my-job-search")    # the registry's
    monkeypatch.setattr(app_setup, "origin", lambda: ("morgan-ellis", "my-job-search"))
    assert app.main(["start", "--paste"]) == 0 and capsys.readouterr().out.strip() == line
    with open(os.path.join(ROOT, "COMPUTER.md"), encoding="utf-8") as fh:
        page = fh.read()
    assert "Open my job search on this computer" in page and "app.py start --paste" in page
    assert "setup_state" not in page
    assert not os.path.exists(os.path.join(ROOT, "tools", "setup_state.py"))
