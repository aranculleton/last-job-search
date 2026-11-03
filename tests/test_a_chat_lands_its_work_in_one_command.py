"""A chat lands its work on master with one background command, tools/land.py.

Landing took about fourteen steps (save, commit, the check, fetch, merge, push, open the pull
request, merge it, unsubscribe, a stash and a checkout of master), each re-reading the whole
chat, and chats ran the three-minute check in the foreground (2026-11-03). These run it on a
throwaway copy with a bare origin, never a real one, with the check faked by a parameter so
the real suite is not run: what it commits, that it merges master before the check, that a
red check, a conflict or nothing to land pushes nothing, that the app's files are never
committed, that a network failure is retried and a refusal is not, and that after the merge
the branch starts from master with no checkout dance.
"""
from __future__ import annotations

import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import land  # noqa: E402

GREEN = [sys.executable, "-c", "print('  documents   SKIP  (no LaTeX here)'); print('Green.')"]
RED = [sys.executable, "-c",
       "print('  tests                     FAIL'); print('      AssertionError: boom'); "
       "print('1 passed, 1 failed, 0 skipped'); print('Not green. Do not push to master.'); "
       "raise SystemExit(1)"]
NEVER = [sys.executable, "-c", "raise SystemExit('the check ran')"]


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
    """(origin, chat, other): a bare origin holding master, a chat on a branch of its own, and
    a second chat's clone that can move master underneath it."""
    for k, v in (("GIT_AUTHOR_NAME", "t"), ("GIT_AUTHOR_EMAIL", "t@example.com"),
                 ("GIT_COMMITTER_NAME", "t"), ("GIT_COMMITTER_EMAIL", "t@example.com")):
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("LJS_LAND_CHECK", raising=False)
    origin, seed = tmp_path / "origin.git", tmp_path / "seed"
    git(tmp_path, "init", "-q", "--bare", "-b", "master", str(origin))
    git(tmp_path, "init", "-q", "-b", "master", str(seed))
    with open(os.path.join(ROOT, ".gitignore"), encoding="utf-8") as fh:
        write(seed, ".gitignore", fh.read())
    write(seed, "tools/example.py", "print('the app')\n")
    write(seed, "profile/person.json", "{}\n")
    write(seed, "profile/notes.md", "first\n")
    git(seed, "add", "-A")
    git(seed, "commit", "-q", "-m", "the person's start")
    git(seed, "remote", "add", "origin", str(origin))
    git(seed, "push", "-q", "origin", "master")
    chat, other = tmp_path / "chat", tmp_path / "other"
    git(tmp_path, "clone", "-q", str(origin), str(chat))
    git(chat, "switch", "-q", "-c", "claude/chat-1")
    git(tmp_path, "clone", "-q", str(origin), str(other))
    return origin, chat, other


def _run(chat, *argv, check=GREEN, capsys=None):
    code = land.main(list(argv), root=str(chat), check=check, sleep=lambda s: None)
    return code, (capsys.readouterr().out if capsys else "")


def _branches(origin):
    return git(origin, "branch", "--format=%(refname:short)").stdout.split()


def test_the_work_is_saved_merged_with_master_checked_and_pushed(copy, capsys):
    origin, chat, other = copy
    # Another chat landed on master meanwhile; the check must see its work too.
    write(other, "documents/network/c1/draft.md", "theirs\n")
    git(other, "add", "-f", "documents/network/c1/draft.md")
    git(other, "commit", "-q", "-m", "another chat's work")
    git(other, "push", "-q", "origin", "master")
    write(chat, "job_search_tracker.csv", "company\nLarkspur\n")      # ignored: forced in
    write(chat, "cv/Morgan_Ellis_Resume_LK.log", "noise\n")           # build noise: never
    sees_both = [sys.executable, "-c",
                 "import os, sys; sys.exit(0 if os.path.exists('documents/network/c1/draft.md') "
                 "and os.path.exists('job_search_tracker.csv') else 1)"]
    code, out = _run(chat, "--message", "Tracker: Larkspur drafted", check=sees_both,
                     capsys=capsys)
    assert code == 0, out
    assert "land: ready claude/chat-1" in out
    assert 'head "claude/chat-1", base "master"' in out and 'title "Tracker: Larkspur drafted"' in out
    assert "merge_pull_request" in out and "python3 tools/land.py --after-merge" in out
    assert "claude/chat-1" in _branches(origin) and "master" in _branches(origin)
    pushed = git(origin, "ls-tree", "-r", "--name-only", "claude/chat-1").stdout.split()
    assert "job_search_tracker.csv" in pushed and "documents/network/c1/draft.md" in pushed
    assert "cv/Morgan_Ellis_Resume_LK.log" not in pushed
    assert "Tracker: Larkspur drafted" in git(chat, "log", "--format=%s").stdout
    # Master itself is never pushed to: only the pull request reaches it.
    assert git(origin, "rev-parse", "master").stdout == git(other, "rev-parse", "HEAD").stdout


def test_the_pull_request_names_what_the_check_skipped(copy, capsys):
    _origin, chat, _other = copy
    write(chat, "profile/notes.md", "second\n")
    code, out = _run(chat, capsys=capsys)
    assert code == 0 and "skipped: documents" in out
    assert land.DEFAULT_MESSAGE in git(chat, "log", "-1", "--format=%s").stdout


def test_a_red_check_pushes_its_branch_with_no_pull_request_and_the_next_chat_finds_it(copy,
                                                                                      capsys):
    """A cloud container is gone when its chat ends: work only committed there was lost, and
    a person's own tests failing after an update made every landing red (the release review,
    2026-11-03). Red still pushes the chat's branch, never a pull request, and --waiting
    names it for the next chat or run."""
    origin, chat, other = copy
    write(chat, "profile/notes.md", "second\n")
    code, out = _run(chat, "--message", "Notes", check=RED, capsys=capsys)
    assert code == 1
    assert out.startswith("land: not green; the work waits on claude/chat-1, pushed with no "
                          "pull request") and "AssertionError: boom" in out
    assert "tests                     FAIL" in out and "1 passed, 1 failed" in out
    assert "create_pull_request" not in out and "land: ready" not in out
    assert "claude/chat-1" in _branches(origin)
    assert git(origin, "log", "-1", "--format=%s", "claude/chat-1").stdout.strip() == "Notes"
    assert git(chat, "status", "--porcelain", "--untracked-files=no").stdout == ""
    # The next chat, in a fresh container, finds it and is told how to bring it in.
    git(other, "fetch", "-q", "origin")
    assert land.waiting(str(other)) == ["origin/claude/chat-1"]
    code, out = _run(other, "--waiting", capsys=capsys)
    assert code == 0 and "waiting on: origin/claude/chat-1" in out
    assert "git merge --no-edit <it>" in out
    # The chat's own branch is never listed to itself, and a branch of the app's is never one.
    assert land.waiting(str(chat)) == []
    git(other, "switch", "-q", "-c", "claude/app-change")
    write(other, "tools/example.py", "print('changed')\n")
    git(other, "commit", "-q", "-am", "an app change")
    git(other, "push", "-q", "origin", "claude/app-change")
    git(other, "fetch", "-q", "origin")
    assert land.waiting(str(other)) == ["origin/claude/chat-1"]


def test_a_conflict_pushes_the_work_from_before_the_merge_and_leaves_no_merge(copy, capsys):
    origin, chat, other = copy
    write(other, "profile/notes.md", "theirs\n")
    git(other, "commit", "-q", "-am", "theirs")
    git(other, "push", "-q", "origin", "master")
    write(chat, "profile/notes.md", "mine\n")
    code, out = _run(chat, "--message", "Mine", check=NEVER, capsys=capsys)
    assert code == 2
    assert out.startswith("land: a conflict in profile/notes.md; the work waits on claude/chat-1")
    assert "create_pull_request" not in out
    assert git(chat, "rev-parse", "-q", "--verify", "MERGE_HEAD", check=False).returncode != 0
    # Pushed as it was before the merge: the chat's own commit, master's not in it.
    assert git(origin, "rev-parse", "claude/chat-1").stdout == git(chat, "rev-parse", "HEAD").stdout
    assert git(origin, "log", "-1", "--format=%s", "claude/chat-1").stdout.strip() == "Mine"
    assert git(origin, "merge-base", "--is-ancestor", "master", "claude/chat-1",
               check=False).returncode != 0


def test_nothing_ahead_of_master_lands_nothing_and_runs_no_check(copy, capsys):
    origin, chat, _other = copy
    code, out = _run(chat, check=NEVER, capsys=capsys)
    assert (code, out.strip()) == (0, "land: nothing to land")
    assert "claude/chat-1" not in _branches(origin)


def test_a_file_of_the_apps_is_never_committed(copy, capsys):
    _origin, chat, _other = copy
    write(chat, "tools/example.py", "print('edited here')\n")
    git(chat, "add", "tools/example.py")
    write(chat, "profile/notes.md", "second\n")
    code, out = _run(chat, capsys=capsys)
    assert code == 0 and "left out 1 file(s) of the app's" in out
    changed = git(chat, "diff", "--name-only", "origin/master", "HEAD").stdout.split()
    assert changed == ["profile/notes.md"]
    # Left as it was, in the working tree, for whoever made it.
    with open(os.path.join(str(chat), "tools", "example.py"), encoding="utf-8") as fh:
        assert fh.read() == "print('edited here')\n"


def test_work_on_master_itself_gets_a_branch_and_master_is_never_pushed(copy, capsys):
    origin, chat, _other = copy
    git(chat, "switch", "-q", "master")
    before = git(origin, "rev-parse", "master").stdout
    write(chat, "profile/notes.md", "second\n")
    code, out = _run(chat, capsys=capsys)
    assert code == 0
    made = [b for b in _branches(origin) if b.startswith("claude/land-")]
    assert len(made) == 1 and f"land: ready {made[0]}" in out
    assert git(origin, "rev-parse", "master").stdout == before


def test_after_the_merge_the_branch_starts_from_master_with_no_checkout_dance(copy, capsys):
    origin, chat, other = copy
    write(chat, "profile/notes.md", "second\n")
    assert _run(chat, capsys=capsys)[0] == 0
    # Not merged yet: it says so and changes nothing.
    head = git(chat, "rev-parse", "HEAD").stdout
    code, out = _run(chat, "--after-merge", capsys=capsys)
    assert code == 1 and "not on master yet" in out
    assert git(chat, "rev-parse", "HEAD").stdout == head
    # GitHub merges the pull request (a merge commit), and another chat lands after it.
    git(other, "fetch", "-q", "origin", "claude/chat-1")
    git(other, "merge", "-q", "--no-ff", "--no-edit", "FETCH_HEAD")
    write(other, "profile/later.md", "later\n")
    git(other, "add", "profile/later.md")
    git(other, "commit", "-q", "-m", "a later chat")
    git(other, "push", "-q", "origin", "master")
    code, out = _run(chat, "--after-merge", capsys=capsys)
    assert code == 0 and "landed" in out
    assert git(chat, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == "claude/chat-1"
    assert git(chat, "rev-parse", "HEAD").stdout == git(origin, "rev-parse", "master").stdout
    assert os.path.exists(os.path.join(str(chat), "profile", "later.md"))
    # The next piece of work lands the same way, its push a plain fast-forward of the branch.
    write(chat, "profile/notes.md", "third\n")
    code, out = _run(chat, capsys=capsys)
    assert code == 0 and "land: ready claude/chat-1 (1 commit(s) ahead of master)" in out


def _fake(results):
    calls = []

    def run(root, *args):
        calls.append(args)
        code, err = results[min(len(calls), len(results)) - 1]
        return subprocess.CompletedProcess(["git", *args], code, "", err)
    return run, calls


def test_a_network_failure_is_retried_with_waits_and_a_refusal_is_not():
    hung = (128, "fatal: unable to access 'https://github.com/x/y/': Could not resolve host")
    run, calls = _fake([hung, hung, (0, "")])
    waits = []
    r = land._retried("/nowhere", "push", "-u", "origin", "HEAD", sleep=waits.append, run=run)
    assert r.returncode == 0 and waits == [2, 4] and len(calls) == 3
    run, calls = _fake([hung])
    waits = []
    assert land._retried("/nowhere", "push", sleep=waits.append, run=run).returncode == 128
    assert waits == [2, 4, 8, 16] and len(calls) == 5
    refused = (1, "! [remote rejected] HEAD -> claude/x (permission denied) 403")
    run, calls = _fake([refused])
    waits = []
    assert land._retried("/nowhere", "push", sleep=waits.append, run=run).returncode == 1
    assert waits == [] and len(calls) == 1


def test_it_never_force_pushes_and_runs_each_git_command_alone():
    with open(os.path.join(ROOT, "tools", "land.py"), encoding="utf-8") as fh:
        text = fh.read()
    assert "--force" not in text and "+HEAD" not in text and "shell=True" not in text
    assert '"push", "-q", "-u", "origin", "HEAD"' in text


def test_the_app_itself_is_never_landed_this_way(copy, capsys):
    origin, chat, _other = copy
    git(chat, "remote", "set-url", "origin", "https://github.com/" + land.APP_REPO + ".git")
    os.remove(os.path.join(str(chat), "profile", "person.json"))
    code, out = _run(chat, check=NEVER, capsys=capsys)
    assert code == 2 and "the app itself" in out
    git(chat, "remote", "set-url", "origin", str(origin))


def test_a_refused_merge_is_landed_again_here_then_merged(copy, capsys):
    """Two chats landing at once: each merges master here with the row-by-row driver, but
    GitHub's merge has no driver, so the second pull request is not mergeable (the release
    review, 2026-11-03). The steps say what to do, and landing again does it."""
    origin, chat, other = copy
    write(chat, "profile/notes.md", "second\n")
    code, out = _run(chat, capsys=capsys)
    assert code == 0 and land.MERGE_REFUSED in out
    assert "merge refused" in land.MERGE_REFUSED and "python3 tools/land.py" in land.MERGE_REFUSED
    with open(os.path.join(ROOT, "RUNBOOK.md"), encoding="utf-8") as fh:
        assert "merge refused" in fh.read()
    # The other chat's landing reaches master first; landing again takes it in, same branch.
    write(other, "profile/theirs.md", "theirs\n")
    git(other, "add", "profile/theirs.md")
    git(other, "commit", "-q", "-m", "the other chat")
    git(other, "push", "-q", "origin", "master")
    code, out = _run(chat, capsys=capsys)
    assert code == 0 and "land: ready claude/chat-1" in out
    assert git(origin, "merge-base", "--is-ancestor", "master", "claude/chat-1",
               check=False).returncode == 0


def test_after_the_merge_a_page_update_that_took_master_since_is_no_reason_to_stay(copy, capsys):
    """A page update (app_setup.take_master) merged master into the branch after the push,
    so HEAD was never on master and --after-merge said "not merged" for ever (the release
    review, 2026-11-03). The commit the landing pushed is what is looked for."""
    origin, chat, other = copy
    write(chat, "profile/notes.md", "second\n")
    assert _run(chat, capsys=capsys)[0] == 0
    write(other, "profile/later.md", "later\n")
    git(other, "add", "profile/later.md")
    git(other, "commit", "-q", "-m", "a later chat")
    git(other, "push", "-q", "origin", "master")
    git(chat, "fetch", "-q", "origin", "master")
    git(chat, "merge", "-q", "--no-edit", "origin/master")          # the page update
    git(other, "fetch", "-q", "origin", "claude/chat-1")
    git(other, "merge", "-q", "--no-ff", "--no-edit", "FETCH_HEAD")  # GitHub merges the PR
    git(other, "push", "-q", "origin", "master")
    code, out = _run(chat, "--after-merge", capsys=capsys)
    assert code == 0 and "starts from master now" in out
    assert git(chat, "rev-parse", "HEAD").stdout == git(origin, "rev-parse", "master").stdout


def test_after_the_merge_newer_work_of_its_own_is_kept(copy, capsys):
    origin, chat, other = copy
    write(chat, "profile/notes.md", "second\n")
    assert _run(chat, capsys=capsys)[0] == 0
    write(chat, "profile/newer.md", "newer\n")
    git(chat, "add", "profile/newer.md")
    git(chat, "commit", "-q", "-m", "newer work")
    git(other, "fetch", "-q", "origin", "claude/chat-1")
    git(other, "merge", "-q", "--no-ff", "--no-edit", "FETCH_HEAD")
    git(other, "push", "-q", "origin", "master")
    code, out = _run(chat, "--after-merge", capsys=capsys)
    assert code == 0 and "newer work of its own" in out
    assert git(chat, "merge-base", "--is-ancestor", "origin/master", "HEAD",
               check=False).returncode == 0
    assert os.path.exists(os.path.join(str(chat), "profile", "newer.md"))


def test_a_landing_holds_a_lock_and_a_second_one_waits_for_it(copy, capsys, monkeypatch):
    """A page update takes no master while a landing runs (app_setup.take_master reads the
    same lock), and two landings never run in one checkout at once."""
    _origin, chat, _other = copy
    lock = os.path.join(land.git_dir(str(chat)), land.LOCK_FILE)
    seen = []
    monkeypatch.setattr(land, "_check_command",
                        lambda root, check: seen.append(land.landing(str(chat))) or GREEN)
    write(chat, "profile/notes.md", "second\n")
    assert _run(chat, capsys=capsys)[0] == 0
    assert seen == [True] and not os.path.exists(lock) and not land.landing(str(chat))
    monkeypatch.undo()
    # Another landing's lock, live: nothing is done.
    with open(lock, "w", encoding="utf-8") as fh:
        fh.write("%d now\n" % os.getpid())
    write(chat, "profile/notes.md", "third\n")
    code, out = _run(chat, check=NEVER, capsys=capsys)
    assert code == 2 and "another landing is running" in out
    # One left by a landing killed long ago is stale, and ignored.
    os.utime(lock, (1, 1))
    assert not land.landing(str(chat))


def test_a_git_command_refused_for_another_ones_index_lock_is_tried_again(copy, capsys):
    """git refuses at once while another command holds index.lock (a page update, the
    update check): the landing stopped with exit 2 (2026-11-03). It waits a moment instead."""
    import threading
    _origin, chat, _other = copy
    lock = os.path.join(land.git_dir(str(chat)), "index.lock")
    with open(lock, "w", encoding="utf-8") as fh:
        fh.write("")
    threading.Timer(0.3, os.remove, [lock]).start()
    write(chat, "profile/notes.md", "second\n")
    code, out = _run(chat, capsys=capsys)
    assert code == 0 and "land: ready claude/chat-1" in out, out

