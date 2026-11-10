"""A save waits on nothing it does not need (tools/land.py).

Two things held saves for minutes in one evening of real use (2026-11-10). Every save ran the
code checks (./tools/ci_local.sh --quick) though most change only the person's own files,
which cannot break the app's code: such a save now lands after a quick read of its files.
And a chat on the person's computer had its save stopped at the last step, twice, by
Claude's own safety check on merging: a computer chat's save now ends at its push, and the
chat that answers the page in the cloud brings it to master with its next save.

Each runs on a throwaway copy with a bare origin. The repo here has no tools/ci_local.sh, so
a landing that ran the code checks fails: a green landing is one that never ran them.
"""
from __future__ import annotations

import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import land  # noqa: E402

GREEN = [sys.executable, "-c", "print('Green.')"]


def git(cwd, *args, check=True):
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=check)


def write(repo, rel, text):
    p = os.path.join(str(repo), rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(text)


@pytest.fixture
def copy(tmp_path, monkeypatch):
    """(origin, chat, helper): a bare origin holding master, a chat on a branch of its own,
    and the cloud helper's clone."""
    for k, v in (("GIT_AUTHOR_NAME", "t"), ("GIT_AUTHOR_EMAIL", "t@example.com"),
                 ("GIT_COMMITTER_NAME", "t"), ("GIT_COMMITTER_EMAIL", "t@example.com")):
        monkeypatch.setenv(k, v)
    for k in ("LJS_LAND_CHECK", "CLAUDECODE", "CLAUDE_CODE_REMOTE"):
        monkeypatch.delenv(k, raising=False)
    origin, seed = tmp_path / "origin.git", tmp_path / "seed"
    git(tmp_path, "init", "-q", "--bare", "-b", "master", str(origin))
    git(tmp_path, "init", "-q", "-b", "master", str(seed))
    with open(os.path.join(ROOT, ".gitignore"), encoding="utf-8") as fh:
        write(seed, ".gitignore", fh.read())
    write(seed, "tools/example.py", "print('the app')\n")
    write(seed, "profile/person.json", "{}\n")
    write(seed, "profile/notes.md", "first\n")
    write(seed, "job_search_tracker.csv", "date,company,role,status\n")
    git(seed, "add", "-A")
    git(seed, "add", "-f", "job_search_tracker.csv")
    git(seed, "commit", "-q", "-m", "the person's start")
    git(seed, "remote", "add", "origin", str(origin))
    git(seed, "push", "-q", "origin", "master")
    chat, helper = tmp_path / "chat", tmp_path / "helper"
    git(tmp_path, "clone", "-q", str(origin), str(chat))
    git(chat, "switch", "-q", "-c", "claude/chat-1")
    git(tmp_path, "clone", "-q", str(origin), str(helper))
    git(helper, "switch", "-q", "-c", "claude/helper")
    return origin, chat, helper


def _land(repo, capsys, check=None, *argv):
    code = land.main(["--message", "Saved", *argv], root=str(repo), check=check,
                     sleep=lambda s: None)
    return code, capsys.readouterr().out


# ------------------------------------------------------------------ 20: data only, at once


def test_a_save_of_only_the_persons_data_lands_without_the_code_checks(copy, capsys):
    _origin, chat, _helper = copy
    write(chat, "job_search_tracker.csv",
          "date,company,role,status\n2026-11-10,Larkspur Health,Nurse,applied\n")
    write(chat, "documents/network/c1/draft.md", "Hi Quillon, hope you're well.\n")
    code, out = _land(chat, capsys)
    assert code == 0, out
    assert "land: ready claude/chat-1" in out, out
    assert "only the person's own files changed (2)" in out


def test_an_app_file_changed_still_runs_the_code_checks(copy, capsys):
    _origin, chat, _helper = copy
    assert land.data_only(str(chat)) is None          # nothing ahead yet
    write(chat, "tools/example.py", "print('changed')\n")
    git(chat, "add", "tools/example.py")
    git(chat, "commit", "-q", "-m", "an app change")
    git(chat, "fetch", "-q", "origin")
    assert land.data_only(str(chat)) is None
    code, out = _land(chat, capsys)
    assert code == 1 and "not green" in out, out       # it ran the check, which is not here


@pytest.mark.parametrize("rel", ["profile/search.py", "profile/tests/test_mine.py",
                                 "profile/person.json"])
def test_the_persons_own_code_and_settings_are_still_checked_in_full(copy, rel):
    _origin, chat, _helper = copy
    write(chat, rel, "{\"name\": \"x\"}\n" if rel.endswith(".json") else "X = 1\n")
    git(chat, "add", "-f", rel)
    git(chat, "commit", "-q", "-m", "theirs")
    git(chat, "fetch", "-q", "origin")
    assert land.data_only(str(chat)) is None


def test_the_data_check_stops_a_broken_file(copy, capsys):
    _origin, chat, _helper = copy
    write(chat, "documents/state/day.json", "{\"open\": \n")
    write(chat, "network_contacts.csv", "name,company\nRiley Ward,Larkspur\n")  # no contact_id
    code, out = _land(chat, capsys)
    assert code == 1 and "not green" in out, out
    assert "documents/state/day.json: not valid JSON" in out
    assert "network_contacts.csv: its contact_id column(s) are missing" in out


def test_the_data_check_finds_conflict_markers_and_a_template_profile(tmp_path):
    write(tmp_path, "documents/notes.md", "a\n<<<<<<< ours\nb\n=======\nc\n>>>>>>> theirs\n")
    write(tmp_path, "profile/CLAUDE.md", "# [YOUR_NAME]\n")
    write(tmp_path, "job_search_tracker.csv", "date,company,role\n2026-11-10,A,B\n")
    bad = land.data_check(str(tmp_path), ["documents/notes.md", "profile/CLAUDE.md",
                                          "job_search_tracker.csv", "documents/gone.json"])
    assert any(b.startswith("documents/notes.md: git's conflict markers") for b in bad), bad
    assert any("profile/CLAUDE.md reverted to template" in b for b in bad), bad
    assert len(bad) == 2, bad


# ------------------------------------------------------------------ 21: a computer's save


def test_a_computer_chats_save_ends_at_its_push_and_the_helper_brings_it_in(copy, capsys,
                                                                             monkeypatch):
    origin, chat, helper = copy
    assert land.on_computer({"CLAUDECODE": "1"})
    assert not land.on_computer({"CLAUDECODE": "1", "CLAUDE_CODE_REMOTE": "true"})
    assert not land.on_computer({})
    # The computer chat: a draft of its own, saved.
    monkeypatch.setenv("CLAUDECODE", "1")
    write(chat, "documents/network/c2/draft.md", "Hi Bexley, hope you're well.\n")
    code, out = _land(chat, capsys)
    assert code == 0, out
    assert "saved to GitHub on claude/chat-1" in out, out
    # Nothing about a pull request or merging, for it to do or to say.
    for word in ("create_pull_request", "merge_pull_request", "gh api", "pull request",
                 "--after-merge"):
        assert word not in out, out
    assert "claude/chat-1" in git(origin, "branch", "--format=%(refname:short)").stdout.split()
    master = git(origin, "rev-parse", "master").stdout
    # The detached save on the computer opens nothing on GitHub either.
    assert land.READY == {} or not land.READY.get("head")
    # The cloud helper's next save, with nothing of its own, brings it in and lands it.
    monkeypatch.setenv("CLAUDE_CODE_REMOTE", "true")
    code, out = _land(helper, capsys, GREEN)
    assert code == 0, out
    assert "brought in work that waited on origin/claude/chat-1" in out, out
    assert "land: ready claude/helper" in out and "merge_pull_request" in out
    files = git(origin, "ls-tree", "-r", "--name-only", "claude/helper").stdout.split()
    assert "documents/network/c2/draft.md" in files
    assert git(origin, "rev-parse", "master").stdout == master   # only through the PR


def test_a_detached_save_on_a_computer_never_goes_to_github_for_a_merge(copy, capsys,
                                                                         monkeypatch):
    _origin, chat, _helper = copy
    monkeypatch.setenv("CLAUDECODE", "1")
    write(chat, "documents/network/c3/draft.md", "Hi Jo.\n")
    asked = []
    code = land.run_detached(str(chat), "Saved", sleep=lambda s: None,
                             finish=lambda root, ready: asked.append(ready) or (True, "1"))
    out = capsys.readouterr().out
    assert code == 0, out
    assert asked == [], "a computer chat opened or merged a pull request"
    assert land.github_waiting(str(chat)) == ""
