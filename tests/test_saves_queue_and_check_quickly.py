"""Saving is quick again, and saves wait their turn.

The maintainer's copy, 2026-11-06: "The person's 'quick' check now runs the app's full suite
and takes over 10 minutes. Several background saves overlap, each running its own copy of the
check." Two causes, each pinned here on an invented copy:

- `./tools/ci_local.sh --quick` skipped the app's own suite in a person's copy only when it
  could prove every change since master was theirs or exactly the app's release. On the master
  channel the app moves several times a day, so an app file a landing brought in matched
  neither, and every save ran the whole of tests/ (and again on Python 3.9).
- The landing lock was looked at, then written: two landings started together both took it.
  A detached save ran its GitHub steps outside it, and a save asked for during its last round
  was dropped. Now the lock is taken in one step (O_CREAT | O_EXCL), held for the whole run,
  and a save asked for while one runs is queued for it or for the next.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import textwrap
import threading
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import land  # noqa: E402
import local_path  # noqa: E402
import repo_files  # noqa: E402

BASH = local_path.bash() or "bash"


def _git(cwd, *args, check=True):
    r = subprocess.run(["git", "-C", str(cwd), "-c", "user.name=t", "-c",
                        "user.email=t@example.com", *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if check:
        assert r.returncode == 0, r.stderr
    return r


# --------------------------------------------------------------------------- the quick check

def _app_files(dest, with_person: bool):
    for rel in repo_files.tracked(root=ROOT, app_only=True):
        if not rel or rel.startswith(("profile.example/", "docs/images/")):
            continue
        src = os.path.join(ROOT, rel)
        if os.path.isfile(src):
            os.makedirs(dest / os.path.dirname(rel), exist_ok=True)
            shutil.copy2(src, dest / rel)
    if with_person:
        shutil.copytree(os.path.join(ROOT, "profile.example"), dest / "profile",
                        ignore=shutil.ignore_patterns("state", "__pycache__"))
        os.makedirs(dest / "profile" / "tests", exist_ok=True)
        (dest / "profile" / "tests" / "test_mine.py").write_text(
            "def test_mine():\n    assert True\n", encoding="utf-8")


def _python_that_records(tmp_path):
    """A Python that writes down what it is asked to run, and answers any pytest run at once:
    the check's choices are what is tested, never the suites themselves."""
    log = tmp_path / "asked.log"
    env_dir = tmp_path / "venv"
    (env_dir / "bin").mkdir(parents=True)
    py = env_dir / "bin" / "python"
    py.write_text(textwrap.dedent("""\
        #!/bin/sh
        echo "$*" >> "%s"
        case "$*" in
          "-m venv "*) mkdir -p "$3/bin"; cp "$0" "$3/bin/python"; exit 0 ;;
          "-m pytest"*) exit 0 ;;
          "-m pip"*) exit 0 ;;
        esac
        exec "%s" "$@"
        """ % (log, sys.executable)), encoding="utf-8")
    py.chmod(0o755)
    # The floor leg's Python, found by name, records the same way.
    (tmp_path / "bin").mkdir()
    shutil.copy2(py, tmp_path / "bin" / "python3.9")
    return env_dir, log


def _quick(checkout, tmp_path, origin_url):
    env_dir, log = _python_that_records(tmp_path)
    env = dict(os.environ, VIRTUAL_ENV=str(env_dir), PYTHONDONTWRITEBYTECODE="1",
               TMPDIR=str(tmp_path), PATH=str(tmp_path / "bin") + os.pathsep +
               os.environ.get("PATH", ""), LJS_APP_URL="https://github.com/example-owner/x")
    for k in ("LJS_PROFILE", "LJS_STATE", "CLAUDE_CODE_REMOTE", "GITHUB_ACTIONS"):
        env.pop(k, None)
    _git(checkout, "remote", "add", "origin", origin_url)
    r = subprocess.run([BASH, "tools/ci_local.sh", "--quick"], cwd=checkout, env=env,
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=600)
    asked = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    return r.stdout + r.stderr, [a for a in asked if a.startswith("-m pytest")]


@pytest.fixture
def needs_shell():
    if os.name == "nt" or not shutil.which("git") or not local_path.bash():
        pytest.skip("needs git and a POSIX shell (the recording Python is a shell script)")


def test_the_quick_check_in_a_copy_never_runs_the_apps_suite(tmp_path, needs_shell):
    """An app file at HEAD that is neither master's nor the app's newest (a landing brought in
    another chat's update, and the app has moved on since) made --quick run all of tests/,
    twice. In a person's copy it never does; their own tests still run."""
    c = tmp_path / "copy"
    _app_files(c, with_person=True)
    _git(tmp_path, "init", "-q", str(c))
    _git(c, "add", "-A")
    _git(c, "commit", "-qm", "a person's copy")
    _git(c, "update-ref", "refs/remotes/origin/master", "HEAD")
    # The app file as an older or newer app had it: matches nothing this copy knows.
    with open(c / "tools" / "brief.py", "a", encoding="utf-8") as fh:
        fh.write("\n# as the app's master had it an hour ago\n")
    (c / "profile" / "notes.md").write_text("today's work\n", encoding="utf-8")
    _git(c, "add", "-A")
    _git(c, "commit", "-qm", "a landing brought in an update")
    out, ran = _quick(c, tmp_path, "https://github.com/example-owner/my-search")
    assert not any(a.startswith("-m pytest tests") for a in ran), (ran, out)
    assert any("profile/tests" in a for a in ran), (ran, out)
    line = next(ln for ln in out.splitlines() if "pytest (the app's suite" in ln)
    assert "SKIP" in line and "--quick in your copy" in line, out


def test_the_apps_own_checkout_still_runs_its_suite_on_quick(tmp_path, needs_shell):
    a = tmp_path / "app"
    _app_files(a, with_person=False)
    _git(tmp_path, "init", "-q", str(a))
    _git(a, "add", "-A")
    _git(a, "commit", "-qm", "the app")
    _out, ran = _quick(a, tmp_path, "https://github.com/aranculleton/last-job-search")
    assert any(a_.startswith("-m pytest tests") for a_ in ran), ran


# --------------------------------------------------------------------------- the queue

@pytest.fixture
def chat(tmp_path):
    """A person's copy with an origin it can push to, on a chat's branch."""
    if not shutil.which("git"):
        pytest.skip("needs git")
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "-q", "--bare", "-b", "master", str(origin))
    c = tmp_path / "chat"
    _git(tmp_path, "init", "-q", "-b", "master", str(c))
    (c / "profile").mkdir()
    (c / "profile" / "person.json").write_text('{"name": "Example"}\n', encoding="utf-8")
    (c / "profile" / "notes.md").write_text("first\n", encoding="utf-8")
    _git(c, "add", "-A")
    _git(c, "commit", "-qm", "start")
    _git(c, "remote", "add", "origin", str(origin))
    _git(c, "push", "-q", "origin", "master")
    _git(c, "fetch", "-q", "origin")
    _git(c, "checkout", "-q", "-b", "claude/chat-1")
    return c


def _slow_check(tmp_path, seconds=1.5):
    """A check that writes when it starts and ends, so overlapping runs show."""
    rec = tmp_path / "checks.log"
    script = tmp_path / "check.py"
    script.write_text(textwrap.dedent("""\
        import sys, time
        with open(%r, "a") as fh: fh.write("start %%f\\n" %% time.time())
        time.sleep(%s)
        with open(%r, "a") as fh: fh.write("end %%f\\n" %% time.time())
        print("Green.")
        """ % (str(rec), seconds, str(rec))), encoding="utf-8")
    return [sys.executable, str(script)], rec


def _runs(rec):
    if not rec.exists():
        return []
    spans, start = [], None
    for ln in rec.read_text().splitlines():
        kind, at = ln.split()
        if kind == "start":
            start = float(at)
        else:
            spans.append((start, float(at)))
    return spans


def test_two_landings_started_at_once_run_one_check_at_a_time(chat, tmp_path):
    check, rec = _slow_check(tmp_path)
    (chat / "profile" / "notes.md").write_text("second\n", encoding="utf-8")
    env = dict(os.environ, LJS_LAND_CHECK=" ".join(check))
    for k in ("LJS_PROFILE", "LJS_STATE"):
        env.pop(k, None)
    run = ("import sys; sys.path.insert(0, %r); import land; "
           "sys.exit(land.main(['--message', 'Notes'], root=%r))"
           % (os.path.join(ROOT, "tools"), str(chat)))
    # Both see no lock at the same moment: the old look-then-write let both in.
    procs = [subprocess.Popen([sys.executable, "-c", run], cwd=chat, env=env,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
             for _ in range(2)]
    outs = [p.communicate(timeout=120)[0] for p in procs]
    spans = _runs(rec)
    assert len(spans) == 1, (spans, outs)
    queued = [o for o in outs if "another landing is running" in o]
    assert len(queued) == 1 and "saves this work too" in queued[0], outs


def test_the_lock_is_taken_in_one_step(chat):
    root = str(chat)
    got = []
    barrier = threading.Barrier(8)

    def grab():
        barrier.wait()
        got.append(land._take_lock(root))
    threads = [threading.Thread(target=grab) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sum(1 for g in got if g) == 1, got
    land._drop_lock(root, next(g for g in got if g))
    assert not land.landing(root)


def test_a_save_asked_for_while_one_runs_is_taken_by_it(chat, capsys):
    """A save asked for during the running one (here, during its last allowed round) is kept,
    and the running one lands it before it lets go; never dropped."""
    root = str(chat)
    rounds = []

    def landed(r, message, check=None, sleep=None):
        rounds.append(message)
        assert land.landing(r)                       # the run holds the lock all along
        if len(rounds) <= land.DETACHED_ROUNDS:
            # Another chat asks for a save while this round runs, every round.
            assert land.detach(r, "more %d" % len(rounds), popen=_never) == 0
        return 0
    land.run_detached(root, "first", land_fn=landed, finish=lambda r, ready: (True, ""))
    assert len(rounds) == land.DETACHED_ROUNDS + 1, rounds
    assert not land.wanted(root) and not land.landing(root)
    assert "saves this too" in capsys.readouterr().out


def _never(*a, **k):
    raise AssertionError("a second landing was started while one runs")


def test_a_save_asked_for_between_rounds_is_queued_for_the_next(chat, capsys):
    """While the detached run is between its landing and its GitHub steps, a second --detach
    starts nothing: it is queued, and the running one takes it."""
    root = str(chat)
    rounds = []

    def landed(r, message, check=None, sleep=None):
        rounds.append(message)
        land.READY.update({"owner": "o", "repo": "r", "head": "claude/chat-1", "title": "t",
                           "body": "b"})
        return 0

    def finish(r, ready):
        if len(rounds) == 1:
            assert land.detach(r, "asked during GitHub's part", popen=_never) == 0
        return False, "gh is not on this computer"
    land.run_detached(root, "first", land_fn=landed, finish=finish)
    assert len(rounds) == 2 and not land.wanted(root)


def test_a_landing_asked_for_while_a_save_runs_is_queued_not_refused(chat, capsys):
    root = str(chat)
    held = land._take_lock(root)
    try:
        (chat / "profile" / "notes.md").write_text("third\n", encoding="utf-8")
        code = land.main(["--message", "Third"], root=root, check=[sys.executable, "-c", "1/0"])
        out = capsys.readouterr().out
        assert code == 0 and "another landing is running" in out and "saves this work too" in out
        assert land.wanted(root)
        assert json.load(open(os.path.join(land.git_dir(root), land.WANTED_FILE),
                              encoding="utf-8"))["message"] == "Third"
    finally:
        land._drop_lock(root, held)


def test_a_lock_an_older_version_left_is_read_and_a_dead_one_is_taken_over(chat):
    """Copies updated while a save ran hold the old one-line lock ("<pid> <stamp>"): read as
    a landing running while it is live, and taken over once it is stale."""
    root = str(chat)
    p = os.path.join(land.git_dir(root), land.LOCK_FILE)
    with open(p, "w", encoding="utf-8") as fh:
        fh.write("%d %s\n" % (os.getpid(), time.strftime(land.LOCK_STAMP, time.gmtime())))
    assert land.landing(root) and not land._take_lock(root)
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(land.lock_text(time.time() - land.LOCK_STALE_S - 60))
    got = land._take_lock(root)
    assert got and land.landing(root)
    land._drop_lock(root, got)
    assert not os.path.exists(p)
