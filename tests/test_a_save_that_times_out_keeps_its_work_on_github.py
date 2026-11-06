"""A job chat whose save times out still has its work on GitHub.

The maintainer's copy, 2026-11-06: the "Finding jobs" chat timed out while saving after an
update. Its landing ran the long check before it pushed anything, so when the chat's time ran
out mid-check its work was on no branch at all: the shortlist lived only in that chat's
container, it reported "not landed", and the next landing had nothing to bring in. Now a
landing pushes the chat's own branch before the check, never forced, so a check that is
stopped, a chat that times out or a container that goes mid-check leaves the work waiting on
GitHub, where the next landing anywhere brings it in. These run on throwaway copies with a
bare origin, the check faked.
"""
from __future__ import annotations

import os
import shlex
import signal
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
    """(origin, chat, other): a bare origin holding master, a job chat on a branch of its own,
    and a second chat's fresh clone."""
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
    git(chat, "switch", "-q", "-c", "claude/finding-jobs")
    git(tmp_path, "clone", "-q", str(origin), str(other))
    git(other, "switch", "-q", "-c", "claude/page")
    return origin, chat, other


def _check_that(tmp_path, body: str) -> list[str]:
    script = tmp_path / "check.py"
    script.write_text(body, encoding="utf-8")
    return [sys.executable, str(script)]


def test_the_branch_is_on_github_before_the_check_starts(copy, tmp_path, capsys):
    origin, chat, _other = copy
    write(chat, "documents/rounds/r1.json", '[{"url": "https://example.com/a"}]\n')
    seen = tmp_path / "seen.txt"
    check = _check_that(tmp_path, (
        "import subprocess\n"
        "r = subprocess.run(['git', 'ls-remote', %r, 'refs/heads/claude/finding-jobs'],"
        " capture_output=True, text=True)\n"
        "open(%r, 'w').write(r.stdout)\n"
        "print('Green.')\n") % (str(origin), str(seen)))
    code = land.main(["--message", "Search: r1"], root=str(chat), check=check,
                     sleep=lambda s: None)
    out = capsys.readouterr().out
    assert code == 0, out
    assert "claude/finding-jobs" in seen.read_text(encoding="utf-8"), out
    # Pushed once more after the check, as ever: the steps for the pull request follow.
    assert "land: ready claude/finding-jobs" in out


@pytest.mark.skipif(os.name == "nt", reason="the chat's end is faked with a POSIX signal")
def test_a_chat_that_ends_mid_check_leaves_its_work_for_the_next_landing(copy, tmp_path):
    """The real path: the landing process itself is ended while the check runs (the chat's
    time ran out), so no code after the check ever runs. The next chat's landing brings the
    shortlist in."""
    origin, chat, other = copy
    write(chat, "documents/rounds/r7.json", '[{"url": "https://example.com/found"}]\n')
    check = _check_that(tmp_path, "import os, signal\nos.kill(os.getppid(), signal.SIGKILL)\n")
    run = ("import sys; sys.path.insert(0, %r); import land; "
           "sys.exit(land.main(['--message', 'Search: r7'], root=%r))"
           % (os.path.join(ROOT, "tools"), str(chat)))
    env = dict(os.environ, LJS_LAND_CHECK=shlex.join(check))
    for k in ("LJS_PROFILE", "LJS_STATE"):
        env.pop(k, None)
    p = subprocess.run([sys.executable, "-c", run], cwd=chat, env=env, capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=120)
    assert p.returncode == -signal.SIGKILL, p.stdout + p.stderr
    assert "documents/rounds/r7.json" in git(origin, "ls-tree", "-r", "--name-only",
                                             "claude/finding-jobs").stdout
    write(other, "profile/notes.md", "the page's own work\n")
    code = land.main(["--message", "Page"], root=str(other), check=GREEN, sleep=lambda s: None)
    assert code == 0
    assert os.path.isfile(os.path.join(str(other), "documents", "rounds", "r7.json"))


def test_a_check_stopped_at_its_deadline_says_where_the_work_waits(copy, monkeypatch, capsys):
    """CHECK_STOPPED said "nothing was pushed", which is no longer so."""
    origin, chat, _other = copy
    monkeypatch.setattr(land, "CHECK_DEADLINE_S", 1)
    monkeypatch.setattr(land, "BEAT_S", 1)
    write(chat, "profile/notes.md", "second\n")
    hang = [sys.executable, "-c", "import time; time.sleep(30)"]
    code = land.main(["--message", "Notes"], root=str(chat), check=hang, sleep=lambda s: None)
    out = capsys.readouterr().out
    assert code == 1 and "was stopped" in out, out
    assert "nothing was pushed" not in out, out
    assert "the work waits on claude/finding-jobs" in out
    assert "claude/finding-jobs" in git(origin, "branch").stdout


def test_work_another_landing_took_to_master_during_the_check_is_landed(copy, tmp_path, capsys):
    """Pushed before the check, the branch can be brought in by another chat's landing while
    the check runs. Then nothing is left to open: it says landed and starts from master."""
    origin, chat, _other = copy
    write(chat, "profile/notes.md", "second\n")
    check = _check_that(tmp_path, (
        "import subprocess\n"
        "subprocess.run(['git', 'push', '-q', 'origin', 'HEAD:refs/heads/master'], check=True)\n"
        "print('Green.')\n"))
    code = land.main(["--message", "Notes"], root=str(chat), check=check, sleep=lambda s: None)
    out = capsys.readouterr().out
    assert code == 0, out
    assert "land: ready" not in out and "create_pull_request" not in out, out
    assert "landed" in out
    assert git(chat, "rev-parse", "HEAD").stdout == git(origin, "rev-parse", "master").stdout


def test_a_detached_save_still_lands_the_same_way(copy, tmp_path):
    """--detach: the early push changes nothing of its round: ready, GitHub's part, then the
    branch moved to master."""
    origin, chat, _other = copy
    write(chat, "profile/notes.md", "second\n")
    done = {}

    def finish(root, ready):
        done.update(ready)
        # GitHub's merge, as the REST call would make it.
        git(root, "push", "-q", "origin", "HEAD:refs/heads/master")
        return True, "1"

    code = land.run_detached(str(chat), "Notes", check=GREEN, sleep=lambda s: None,
                             finish=finish)
    assert code == 0
    assert done.get("head") == "claude/finding-jobs"
    assert git(chat, "rev-parse", "HEAD").stdout == git(origin, "rev-parse", "master").stdout
