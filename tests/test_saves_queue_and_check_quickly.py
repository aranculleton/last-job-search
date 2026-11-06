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


def _quick(checkout, tmp_path, origin_url, **more):
    env_dir, log = _python_that_records(tmp_path)
    env = dict(os.environ, **more, VIRTUAL_ENV=str(env_dir), PYTHONDONTWRITEBYTECODE="1",
               TMPDIR=str(tmp_path), PATH=str(tmp_path / "bin") + os.pathsep +
               os.environ.get("PATH", ""), LJS_APP_URL="https://github.com/example-owner/x")
    for k in ("LJS_PROFILE", "LJS_STATE", "CLAUDE_CODE_REMOTE", "GITHUB_ACTIONS"):
        env.pop(k, None)
    if land.ASIDE_ENV not in more:
        env.pop(land.ASIDE_ENV, None)
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
    # One of their own tests an update broke, set aside by the landing while it is brought
    # in line (tools/land.py): the check leaves it out, by its id, spaces and all.
    aside = tmp_path / "aside.txt"
    aside.write_text("profile/tests/test_mine.py::test_mine[a b]\r\n", encoding="utf-8")
    out, ran = _quick(c, tmp_path, "https://github.com/example-owner/my-search",
                      **{land.ASIDE_ENV: str(aside)})
    assert not any(a.startswith("-m pytest tests") for a in ran), (ran, out)
    own = [a for a in ran if "profile/tests" in a]
    assert own and all("--deselect profile/tests/test_mine.py::test_mine[a b]" in a
                       for a in own), (ran, out)
    assert "1 of your own tests an update changed are set aside" in out, out
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
    # The copy's own identity: the landing commits with it, and a CI runner has no global one.
    _git(c, "config", "user.name", "Test")
    _git(c, "config", "user.email", "test@example.com")
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
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                              encoding="utf-8", errors="replace")
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


# --------------------------------------------------------------------------- an update's tests

def _update_in_this_landing(chat, own_test: str):
    """The person's own test, on master; then an app update this chat took, not on master."""
    (chat / "profile" / "tests").mkdir(exist_ok=True)
    (chat / "profile" / "tests" / "test_mine.py").write_text(own_test, encoding="utf-8")
    (chat / "tools").mkdir(exist_ok=True)
    (chat / "tools" / "thing.py").write_text("SHAPE = 'old'\n", encoding="utf-8")
    _git(chat, "add", "-A")
    _git(chat, "commit", "-qm", "their test")
    _git(chat, "push", "-q", "origin", "HEAD:master")
    _git(chat, "fetch", "-q", "origin")
    (chat / "tools" / "thing.py").write_text("SHAPE = 'new'\n", encoding="utf-8")
    _git(chat, "add", "-A")
    _git(chat, "commit", "-qm", "Sync from the app: the newest version")
    (chat / "profile" / "notes.md").write_text("today's work\n", encoding="utf-8")


PINNED = ("import os\n"
          "def test_shape():\n"
          "    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))\n"
          "    text = open(os.path.join(here, 'tools', 'thing.py')).read()\n"
          "    assert \"'old'\" in text\n")


def _marker_check(tmp_path):
    ran = tmp_path / "check-ran"
    return ran, [sys.executable, "-c", "open(%r, 'w').close()" % str(ran)]


def test_an_update_that_broke_own_tests_never_holds_the_save(chat, tmp_path, capsys,
                                                             monkeypatch):
    """An update this landing carries changed what one of the person's own tests pinned, and
    nothing had run them against it (another chat took it, a short job's chat missed the step):
    the save lands with that test set aside, and bringing it in line is queued at once for the
    background step that needs nobody (the own-tests improvement). Never held, never nagging."""
    import profile_upgrades
    import sync_app
    monkeypatch.setattr(profile_upgrades, "ROOT", str(chat))
    _update_in_this_landing(chat, PINNED)
    got = tmp_path / "aside-seen"
    check = [sys.executable, "-c",
             "import os, shutil; p = os.environ.get(%r, ''); "
             "shutil.copy(p, %r) if p else open(%r, 'w').close()"
             % (land.ASIDE_ENV, str(got), str(got))]
    code = land.main(["--message", "Notes"], root=str(chat), check=check)
    out = capsys.readouterr().out
    assert code == 0 and "land: ready" in out, out
    assert land.OWN_TESTS_DO not in out and "1 of the person's own tests" in out, out
    assert got.read_text(encoding="utf-8").split() == [
        "profile/tests/test_mine.py::test_shape"]
    # Queued at once, for the next chat's hook to start in the background.
    assert "own-tests" in profile_upgrades.listed_ids()
    assert ("own-tests", profile_upgrades._day()) in profile_upgrades.unstarted(chat="a chat")
    # The record still says it fails: the improvement's own check sees the work owed.
    assert sync_app.own_tests_owed(str(chat)) == ["profile.tests.test_mine::test_shape"]
    # Brought in line: nothing is set aside any more.
    (chat / "profile" / "tests" / "test_mine.py").write_text(
        PINNED.replace("'old'", "'new'"), encoding="utf-8")
    got.unlink()
    (chat / "profile" / "notes.md").write_text("more work\n", encoding="utf-8")
    code = land.main(["--message", "Notes"], root=str(chat), check=check)
    out = capsys.readouterr().out
    assert code == 0 and got.read_text(encoding="utf-8") == "", out


def test_the_own_tests_improvement_is_owed_again_for_a_second_update_the_same_day(chat,
                                                                                  monkeypatch):
    import profile_upgrades
    monkeypatch.setattr(profile_upgrades, "ROOT", str(chat))
    _update_in_this_landing(chat, PINNED)
    assert profile_upgrades.queue_own_tests(str(chat))
    profile_upgrades.mark_started()
    assert profile_upgrades.unstarted(chat="a chat") == []
    (chat / "tools" / "thing.py").write_text("SHAPE = 'newer'\n", encoding="utf-8")
    _git(chat, "add", "-A")
    _git(chat, "commit", "-qm", "Sync from the app: a second version today")
    assert profile_upgrades.queue_own_tests(str(chat))
    assert [i for i, _ in profile_upgrades.unstarted(chat="a chat")] == ["own-tests"]


def test_own_tests_that_pass_after_an_update_hold_nothing(chat, tmp_path, capsys):
    _update_in_this_landing(chat, "def test_fine():\n    assert True\n")
    ran, check = _marker_check(tmp_path)
    code = land.main(["--message", "Notes"], root=str(chat), check=check)
    assert code == 0 and ran.exists(), capsys.readouterr().out


# --------------------------------------------------------------------------- the round folder

def test_the_search_tweak_record_is_never_among_the_round_summaries(tmp_path, monkeypatch):
    """documents/rounds/*.json is the round summaries, each a list of rows, and every reader
    (the app's, and a person's own tests) reads each as one. The record of tweaks to the
    search was written there (documents/rounds/tweaks.json) and broke a person's own test; an
    old one is moved, by the upgrade or the next tweak, its entries kept."""
    import person
    import profile_upgrades
    import tweak
    monkeypatch.setenv(person.STATE_ENV, str(tmp_path))
    rounds = tmp_path / "documents" / "rounds"
    rounds.mkdir(parents=True)
    (rounds / "2026-11-05.json").write_text('[{"url": "https://example.com/1"}]\n')
    (rounds / "tweaks.json").write_text('{"k1": {"at": "2026-11-05"}}\n')
    assert profile_upgrades._old_jobs_tweaks()
    where = tweak.resolve({"args": {"target": {"id": "jobs", "output": "jobs"}}})
    assert os.path.realpath(where["folder"]) == os.path.realpath(rounds / "tweaks")
    assert tweak.log(where) == {"k1": {"at": "2026-11-05"}}
    assert not profile_upgrades._old_jobs_tweaks()
    # Every file directly in the round folder is still a round's list of rows.
    for name in os.listdir(rounds):
        if name.endswith(".json"):
            with open(rounds / name, encoding="utf-8") as fh:
                assert isinstance(json.load(fh), list), name
    # The upgrade's own command, on a copy that has not tweaked since.
    (rounds / "tweaks.json").write_text('{"k2": {"at": "2026-11-06"}}\n')
    assert tweak.main(["move-record"]) == 0
    assert set(tweak.log(where)) == {"k1", "k2"} and not (rounds / "tweaks.json").exists()


# --------------------------------------------------------------------------- the review's finds

def test_queueing_own_tests_again_never_restarts_what_an_agent_has_started(chat, monkeypatch):
    """A background agent started on the update's improvements, and another chat's landing
    queued own-tests again while it worked: the start was dropped and every chat's "not now"
    deleted, so the hook held the next chat for a second agent on the same tests."""
    import profile_upgrades as pu
    monkeypatch.setattr(pu, "ROOT", str(chat))
    _update_in_this_landing(chat, PINNED)
    assert pu.queue_own_tests(str(chat))
    pu.mark_started()
    pu.not_now("on a call", chat="chat b")
    before = pu._listed()
    assert pu.queue_own_tests(str(chat))
    assert pu._listed() == before
    assert pu.unstarted(chat="a chat") == [] and pu.unstarted(chat="chat b") == []


def test_own_tests_queued_after_a_start_is_owed_alone(chat, monkeypatch):
    """Started on what the sync listed, without own-tests: own-tests queued later is owed on
    its own, and nothing the start took is owed twice."""
    import profile_upgrades as pu
    monkeypatch.setattr(pu, "ROOT", str(chat))
    _update_in_this_landing(chat, PINNED)
    day = pu._day()
    pu._save_listed({"sync": pu._sync_head()[0], "ids": ["sweep-cursor-moved"], "day": day,
                     "since": {}, "elsewhere": False, "started": {"day": day}})
    assert pu.unstarted(chat="a chat") == []
    assert pu.queue_own_tests(str(chat))
    assert pu.unstarted(chat="a chat") == [("own-tests", day)]


def test_a_save_queued_behind_one_that_stopped_short_is_started_next(chat, monkeypatch, capsys):
    """Chat B was told its work is saved too while chat A's landing ran; A's stopped short
    (not green), and B's request sat with nothing to take it while the hook held nobody."""
    root = str(chat)
    started = []

    def a_lands(r, message, check, sleep):
        assert land.main(["--message", "B's work"], root=r) == 0      # B, queued behind A
        return 1                                                       # A: not green
    monkeypatch.setattr(land, "_land", a_lands)
    monkeypatch.setattr(land, "_next", lambda r: started.append(r))
    assert land.main(["--message", "A's work"], root=root) == 1
    assert started == [root], capsys.readouterr().out


def test_a_queued_save_is_owned_only_while_a_landing_lives(chat):
    root = str(chat)
    p = os.path.join(land.git_dir(root), land.WANTED_FILE)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump({"message": "B", "at": time.time() - 5}, fh)
    assert land.wanted(root)                       # a moment old: one is starting for it
    with open(p, "w", encoding="utf-8") as fh:
        json.dump({"message": "B", "at": time.time() - 300}, fh)
    assert not land.wanted(root)                   # nobody alive to take it: the hook holds
    token = land._take_lock(root)
    try:
        assert land.wanted(root)
    finally:
        land._drop_lock(root, token)


def test_a_check_that_hangs_is_stopped_and_the_work_kept(chat, tmp_path, monkeypatch, capsys):
    """The lock is kept alive while the check runs, so a hung check held every save for ever."""
    monkeypatch.setattr(land, "CHECK_DEADLINE_S", 2)
    monkeypatch.setattr(land, "BEAT_S", 1)
    (chat / "profile" / "notes.md").write_text("second\n", encoding="utf-8")
    hang = [sys.executable, "-c", "import time; time.sleep(40)"]
    start = time.monotonic()
    code = land.main(["--message", "Notes"], root=str(chat), check=hang)
    out = capsys.readouterr().out
    assert time.monotonic() - start < 30, out
    assert code == 1 and "was stopped" in out and "the work waits on" in out, out
    assert not land.landing(str(chat))


def test_a_handed_over_lock_another_landing_holds_now_is_left_alone(chat):
    root = str(chat)
    p = os.path.join(land.git_dir(root), land.LOCK_FILE)
    with open(p, "w", encoding="utf-8") as fh:
        fh.write("4242 %s other-token\n" % time.strftime(land.LOCK_STAMP, time.gmtime()))
    land._hand_over(root, "my-token", 99)
    assert land._lock_words(p)[::2] == ["4242", "other-token"]


def test_a_lock_put_back_never_lands_over_a_third_landings(chat, monkeypatch):
    """Judged stale, moved aside, found live after all; meanwhile a third landing took the
    lock: putting it back must never replace the third one's."""
    root = str(chat)
    p = os.path.join(land.git_dir(root), land.LOCK_FILE)
    with open(p, "w", encoding="utf-8") as fh:
        fh.write("1 %s first\n" % time.strftime(land.LOCK_STAMP, time.gmtime()))
    calls = []
    monkeypatch.setattr(land, "_live", lambda path: calls.append(path) or len(calls) > 1)

    def third_takes_it(src, dst):
        with open(dst, "w", encoding="utf-8") as fh:
            fh.write("2 %s third\n" % time.strftime(land.LOCK_STAMP, time.gmtime()))
        raise FileExistsError(dst)
    monkeypatch.setattr(land.os, "link", third_takes_it)
    assert land._take_lock(root) == ""
    assert land._lock_words(p)[2] == "third"
