"""A master whose history was rewritten is branched from, never merged.

A fetch printed "(forced update)", and the start-of-session merge from a checkout made
before the rewrite conflicted on hundreds of files: the person had to warn the session in
their own prompt. Real git repositories in a temporary folder; nothing is pushed anywhere.
"""
from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import sync_app  # noqa: E402


def g(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), *args], text=True, capture_output=True, check=True)


def commit(cwd, name, text):
    (cwd / name).write_text(text, encoding="utf-8")
    g(cwd, "add", name)
    g(cwd, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", name)


def _setup(tmp_path):
    origin = tmp_path / "origin"
    origin.mkdir()
    g(origin, "init", "-q", "-b", "master")
    commit(origin, "a.txt", "one")
    commit(origin, "b.txt", "two")
    me = tmp_path / "me"
    g(tmp_path, "clone", "-q", str(origin), str(me))
    g(me, "switch", "-q", "-c", "claude/work")
    # The rewrite: master replaced by a history without the old second commit.
    g(origin, "reset", "-q", "--hard", "HEAD~1")
    commit(origin, "c.txt", "three")
    return origin, me


def test_a_branch_with_nothing_of_its_own_moves_to_the_new_master(tmp_path, monkeypatch, capsys):
    origin, me = _setup(tmp_path)
    monkeypatch.setattr(sync_app, "ROOT", str(me))
    assert sync_app.pull_master() == 0
    said = capsys.readouterr().out
    assert "rewritten" in said and "nothing was lost" in said
    assert g(me, "rev-parse", "HEAD").stdout == g(origin, "rev-parse", "HEAD").stdout
    assert g(me, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == "claude/work"


def test_a_branch_with_commits_of_its_own_stops_and_names_them(tmp_path, monkeypatch, capsys):
    origin, me = _setup(tmp_path)
    commit(me, "mine.txt", "work in progress")
    mine = g(me, "rev-parse", "HEAD").stdout.strip()
    monkeypatch.setattr(sync_app, "ROOT", str(me))
    assert sync_app.pull_master() == 1
    said = capsys.readouterr().out
    assert "Do not merge" in said and mine[:12] in said and "cherry-pick" in said
    assert g(me, "rev-parse", "HEAD").stdout.strip() == mine          # nothing changed
    assert not (me / "c.txt").exists()


def test_an_ordinary_new_master_is_still_merged(tmp_path, monkeypatch):
    origin = tmp_path / "origin"
    origin.mkdir()
    g(origin, "init", "-q", "-b", "master")
    commit(origin, "a.txt", "one")
    me = tmp_path / "me"
    g(tmp_path, "clone", "-q", str(origin), str(me))
    g(me, "config", "user.name", "t")
    g(me, "config", "user.email", "t@example.com")
    commit(origin, "b.txt", "two")
    monkeypatch.setattr(sync_app, "ROOT", str(me))
    assert sync_app.pull_master() == 0
    assert (me / "b.txt").exists()


def test_a_second_chat_gets_a_branch_name_nobody_has(tmp_path, monkeypatch):
    origin = tmp_path / "origin"
    origin.mkdir()
    g(origin, "init", "-q", "-b", "master")
    commit(origin, "a.txt", "one")
    me = tmp_path / "me"
    g(tmp_path, "clone", "-q", str(origin), str(me))
    import datetime
    day = datetime.date(2026, 10, 19)
    monkeypatch.setattr(sync_app, "ROOT", str(me))
    first = sync_app.branch_name("Networking", day)
    assert first == "chat/networking-20261019"
    g(me, "branch", first)
    assert sync_app.branch_name("networking", day) == "chat/networking-20261019-2"


def test_a_rewrite_fetched_by_hand_first_is_still_caught(tmp_path, monkeypatch, capsys):
    # The session ran `git fetch` itself before the sync: origin/master already points at
    # the new history, so only the fetch's own record says it was forced.
    origin, me = _setup(tmp_path)
    commit(me, "mine.txt", "work in progress")
    mine = g(me, "rev-parse", "HEAD").stdout.strip()
    g(me, "fetch", "-q", "origin", "master")
    monkeypatch.setattr(sync_app, "ROOT", str(me))
    assert sync_app.pull_master() == 1
    assert "rewritten" in capsys.readouterr().out
    assert g(me, "rev-parse", "HEAD").stdout.strip() == mine


def test_a_branch_already_on_the_new_master_is_not_stopped(tmp_path, monkeypatch):
    # After the rewrite was dealt with, the reflog still says "forced-update"; a branch
    # built on the new history has nothing to do with the old one and merges as usual.
    origin, me = _setup(tmp_path)
    g(me, "fetch", "-q", "origin", "master")
    g(me, "switch", "-q", "-C", "claude/work", "origin/master")
    g(me, "config", "user.name", "t")
    g(me, "config", "user.email", "t@example.com")
    monkeypatch.setattr(sync_app, "ROOT", str(me))
    assert sync_app.pull_master() == 0
    commit(origin, "d.txt", "four")
    assert sync_app.pull_master() == 0
    assert (me / "d.txt").exists()


def test_the_first_step_of_a_session_is_the_sync_not_a_bare_merge():
    text = open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8").read()
    step = text.split("1. **Pull master**", 1)[1].split("\n2. ", 1)[0]
    assert "sync_app.py --pull" in step and "git merge origin/master" not in step


def test_a_rewrite_fetched_by_hand_then_fast_forwarded_is_still_caught(tmp_path, monkeypatch):
    origin, me = _setup(tmp_path)
    commit(me, "mine.txt", "work in progress")
    g(me, "fetch", "-q", "origin", "master")          # the forced update, by hand
    commit(origin, "d.txt", "four")
    g(me, "fetch", "-q", "origin", "master")          # then an ordinary one on top
    monkeypatch.setattr(sync_app, "ROOT", str(me))
    assert sync_app.pull_master() == 1
    assert not (me / "d.txt").exists()


def test_a_checkout_that_fails_is_never_called_a_success(tmp_path, monkeypatch, capsys):
    origin, me = _setup(tmp_path)
    (me / "c.txt").write_text("mine, not tracked", encoding="utf-8")   # the new master adds it
    monkeypatch.setattr(sync_app, "ROOT", str(me))
    assert sync_app.pull_master() == 1
    said = capsys.readouterr().out
    assert "nothing was lost" not in said and "in the way" in said


def test_uncommitted_work_stops_the_merge_and_says_so(tmp_path, monkeypatch, capsys):
    origin = tmp_path / "origin"
    origin.mkdir()
    g(origin, "init", "-q", "-b", "master")
    commit(origin, "a.txt", "one")
    me = tmp_path / "me"
    g(tmp_path, "clone", "-q", str(origin), str(me))
    commit(origin, "a.txt", "two")
    (me / "a.txt").write_text("my edit", encoding="utf-8")
    g(me, "switch", "-q", "-c", "claude/work")
    commit(me, "b.txt", "mine")
    (me / "a.txt").write_text("my edit", encoding="utf-8")
    monkeypatch.setattr(sync_app, "ROOT", str(me))
    assert sync_app.pull_master() == 1
    assert "uncommitted changes" in capsys.readouterr().out
    assert (me / "a.txt").read_text(encoding="utf-8") == "my edit"


def test_a_second_chat_on_the_persons_computer_is_told_to_take_a_folder_of_its_own(
        tmp_path, monkeypatch):
    _origin, me = _setup(tmp_path)
    monkeypatch.setattr(sync_app, "ROOT", str(me))
    monkeypatch.setattr(sync_app, "CLOUD", False)
    # The first chat works in the copy itself, as CLAUDE.md says; it was told to move too
    # (2026-10-25). A second chat while the first is working there is told.
    assert sync_app.own_folder(now=1000.0, chat="session_first") == ""
    assert sync_app.own_folder(now=2000.0, chat="session_first") == ""
    assert "--worktree" in sync_app.own_folder(now=3000.0, chat="session_second")
    # Hours after the first chat's last sync, the main folder is nobody's.
    later = 3000.0 + sync_app.MAIN_CHAT_HOURS * 3600
    assert sync_app.own_folder(now=later, chat="session_second") == ""
    assert "--worktree" in sync_app.own_folder(now=later + 60, chat="session_first")
    own = tmp_path / "me-two"
    g(me, "worktree", "add", "-q", "-b", "chat/two", str(own))
    monkeypatch.setattr(sync_app, "ROOT", str(own))
    assert sync_app.own_folder() == ""                  # its own folder already
    monkeypatch.setattr(sync_app, "ROOT", str(me))
    monkeypatch.setattr(sync_app, "CLOUD", True)
    assert sync_app.own_folder() == ""                  # a cloud chat has a container of its own


def _with_a_sync_on_the_branch(tmp_path, me):
    """The day's sync ran on this chat's branch before the rewrite: an app commit, merged
    the way sync_app merges it (a merge commit), sits beside the person's own work."""
    app = tmp_path / "app"
    app.mkdir()
    g(app, "init", "-q", "-b", "master")
    commit(app, "tools.txt", "the app's own change")
    g(me, "remote", "add", "app", str(app))
    g(me, "fetch", "-q", "app")
    g(me, "-c", "user.name=t", "-c", "user.email=t@example.com", "merge", "-q", "--no-ff",
      "--allow-unrelated-histories", "-m", f"{sync_app.SYNC_SUBJECT}: 1 new commit(s)",
      "app/master")


def test_the_command_given_after_a_rewrite_carries_only_their_own_commits(
        tmp_path, monkeypatch, capsys):
    """It listed the app's commits and the sync's merge as well, and `git cherry-pick`
    stops on a merge ("is a merge but no -m option was given"), so the person's own commit
    was never carried across (found 2026-10-25)."""
    origin, me = _setup(tmp_path)
    _with_a_sync_on_the_branch(tmp_path, me)
    commit(me, "mine.txt", "work in progress")
    mine = g(me, "rev-parse", "HEAD").stdout.strip()
    monkeypatch.setattr(sync_app, "ROOT", str(me))
    assert sync_app.pull_master() == 1
    said = capsys.readouterr().out
    assert "1 commit(s) of its own" in said
    line = next(ln.strip() for ln in said.splitlines() if "cherry-pick" in ln)
    picked = line.split("cherry-pick", 1)[1].split()
    assert picked == [mine[:12]]
    # The command as given works: each part run on its own, as a chat runs them.
    for part in line.split("&&"):
        g(me, "-c", "user.name=t", "-c", "user.email=t@example.com", *part.split()[1:])
    assert (me / "mine.txt").read_text(encoding="utf-8") == "work in progress"
    assert (me / "c.txt").exists()                     # on the new master


def test_a_branch_whose_only_extra_is_a_sync_moves_to_the_new_master(
        tmp_path, monkeypatch, capsys):
    origin, me = _setup(tmp_path)
    _with_a_sync_on_the_branch(tmp_path, me)
    monkeypatch.setattr(sync_app, "ROOT", str(me))
    assert sync_app.pull_master() == 0
    assert "nothing was lost" in capsys.readouterr().out
    assert g(me, "rev-parse", "HEAD").stdout == g(origin, "rev-parse", "HEAD").stdout
