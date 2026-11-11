"""The brief counts one day, the person's own, and never writes over a day's saved record.

A test run at 01:10 UTC on a Tuesday (still Monday evening where the person lives) took the
computer's day in some steps and the person's in others, said "Monday brief", and its landing
rewrote Monday's record and pack, which had been saved the morning before (audit BT-6). Now
the day comes from person.today() once, at the start, and goes to every step as --today; and a
run whose day's record is already on the saved copy is a second one, which writes nothing over
it. Invented people, a local git origin, no network.
"""
from __future__ import annotations

import datetime as dt
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network"),
                os.path.join(ROOT, "tests")]

import brief  # noqa: E402
import person  # noqa: E402

from test_brief import _profile, _run, _state  # noqa: E402

DAY = "2026-11-09"


def git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True,
                          encoding="utf-8", check=True)


def test_the_brief_takes_the_persons_day_not_the_computers(monkeypatch):
    monkeypatch.setattr(person, "today", lambda now=None: dt.date(2026, 11, 9))
    assert brief._today() == dt.date(2026, 11, 9)
    assert brief._today("2026-11-12") == dt.date(2026, 11, 12)


def test_the_start_chooses_the_day_once_and_passes_it_on(tmp_path, monkeypatch):
    calls = []

    class Done:
        returncode, stdout, stderr = 0, "", ""

    def fake(argv, **kw):
        calls.append(list(argv))
        return Done()

    monkeypatch.setenv("LJS_BRIEF_SYNC", str(tmp_path / "sync.txt"))
    monkeypatch.setattr(brief.subprocess, "run", fake)
    monkeypatch.setattr(brief, "page_url", lambda: "")
    monkeypatch.setattr(person, "today", lambda now=None: dt.date(2026, 11, 9))
    import land
    monkeypatch.setattr(land, "stranded", lambda root=None, fetch=False: {}, raising=False)
    assert brief.start(["--on", "a model", "--write"], "a model") == 0
    assert calls[-1][2:] == ["--on", "a model", "--write", "--today", DAY]
    assert brief.read_sync(dt.date(2026, 11, 9), str(tmp_path / "sync.txt")) != {}


def _saved_copy(tmp_path):
    """The state as a git checkout whose origin's master already holds DAY's record."""
    for k, v in (("GIT_AUTHOR_NAME", "t"), ("GIT_AUTHOR_EMAIL", "t@example.com"),
                 ("GIT_COMMITTER_NAME", "t"), ("GIT_COMMITTER_EMAIL", "t@example.com")):
        os.environ[k] = v
    state = _state(tmp_path)
    _profile(state)
    briefs = os.path.join(state, "documents", "briefs")
    os.makedirs(briefs)
    with open(os.path.join(briefs, DAY + ".md"), "w", encoding="utf-8") as fh:
        fh.write("# Brief, %s (Monday)\n\nthe real one, saved that morning\n" % DAY)
    origin = tmp_path / "origin.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "master", str(origin))
    git(state, "init", "-q", "-b", "master")
    git(state, "add", "-A")
    git(state, "commit", "-q", "-m", "saved")
    git(state, "remote", "add", "origin", str(origin))
    git(state, "push", "-q", "origin", "master")
    git(state, "fetch", "-q", "origin")
    return state


def test_a_second_run_for_a_day_already_saved_writes_nothing_over_it(tmp_path):
    state = _saved_copy(tmp_path)
    record = os.path.join(state, "documents", "briefs", DAY + ".md")
    before = open(record, encoding="utf-8").read()
    tracker = open(os.path.join(state, "job_search_tracker.csv"), encoding="utf-8").read()
    r = _run(state, "--today", DAY, "--write")
    assert r.returncode == 0, r.stderr
    assert open(record, encoding="utf-8").read() == before
    assert not os.path.exists(os.path.join(state, "documents", "network",
                                            "followup_pack_%s.md" % DAY))
    assert open(os.path.join(state, "job_search_tracker.csv"), encoding="utf-8").read() == tracker
    assert "already came and its record is saved" in r.stdout.split("FOR CLAUDE", 1)[1]
    # The news step of that run writes nothing over it either.
    r = _run(state, "news", "--today", DAY, stdin="- Larkspur Retail opens a new office "
             "(Example News, 2026-11-09, https://example.com/a)\n")
    assert r.returncode == 0, r.stderr
    assert "nothing written over it" in r.stdout
    assert open(record, encoding="utf-8").read() == before


def test_the_next_day_is_written_as_ever(tmp_path):
    state = _saved_copy(tmp_path)
    r = _run(state, "--today", "2026-11-10", "--write")
    assert r.returncode == 0, r.stderr
    assert os.path.exists(os.path.join(state, "documents", "briefs", "2026-11-10.md"))
    assert "already came" not in r.stdout
