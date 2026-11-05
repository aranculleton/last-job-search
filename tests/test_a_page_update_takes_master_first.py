"""A page update is drawn from a copy that has what every other chat landed.

Each chat works in its own copy, and a page update drawn from a copy behind master dropped
another chat's results: a finished search could undo a finished draft on the page, and the
next update the search (the release review, 2026-11-03). `app_setup.take_master()` merges
master in first, and when it cannot, the page is left as it is. Invented data only.
"""
from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import app_setup  # noqa: E402


def _git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True, encoding="utf-8",
                          env=dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
                                   GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com"))


def _copies(tmp_path):
    bare = tmp_path / "origin.git"
    _git(tmp_path, "init", "-q", "--bare", "-b", "master", str(bare))
    a = tmp_path / "a"
    _git(tmp_path, "clone", "-q", str(bare), str(a))
    (a / "profile").mkdir()
    (a / "profile" / "person.json").write_text("{}\n")
    (a / "job_search_tracker.csv").write_text("company\nKestrel Mutual\n")
    _git(a, "add", "-A")
    _git(a, "commit", "-qm", "start")
    _git(a, "push", "-q", "origin", "HEAD:master")
    b = tmp_path / "b"
    _git(tmp_path, "clone", "-q", str(bare), str(b))
    return a, b


def _here(monkeypatch, copy):
    monkeypatch.setattr(app_setup, "ROOT", str(copy))
    monkeypatch.setattr(app_setup, "origin", lambda: ("someone", "their-search"))


def test_a_copy_behind_master_takes_it_before_the_page_is_drawn(tmp_path, monkeypatch):
    a, b = _copies(tmp_path)
    # Another chat lands a search's results.
    (b / "round.json").write_text('{"jobs": 10}\n')
    _git(b, "add", "-A")
    _git(b, "commit", "-qm", "a search")
    _git(b, "push", "-q", "origin", "HEAD:master")
    # This chat has its own unsaved change in another file, and draws the page.
    (a / "job_search_tracker.csv").write_text("company\nKestrel Mutual\nFernhill Freight\n")
    _here(monkeypatch, a)
    assert app_setup.take_master() == ""
    assert (a / "round.json").exists(), "the other chat's results are in this copy now"
    assert "Fernhill Freight" in (a / "job_search_tracker.csv").read_text(), "its own change kept"
    # Up to date: nothing to do, nothing changed.
    head = _git(a, "rev-parse", "HEAD").stdout
    assert app_setup.take_master() == "" and _git(a, "rev-parse", "HEAD").stdout == head


def test_a_copy_that_cannot_take_master_leaves_the_page_as_it_is(tmp_path, monkeypatch):
    a, b = _copies(tmp_path)
    (b / "job_search_tracker.csv").write_text("company\nKestrel Mutual\nLarkspur Retail\n")
    _git(b, "commit", "-qam", "another chat's row")
    _git(b, "push", "-q", "origin", "HEAD:master")
    (a / "job_search_tracker.csv").write_text("company\nKestrel Mutual\nQuayside Foods\n")
    _here(monkeypatch, a)
    said = app_setup.take_master()
    assert said.startswith("app: this copy is behind master") and "left as it is" in said
    assert "Quayside Foods" in (a / "job_search_tracker.csv").read_text(), "nothing of its own lost"
    assert not (a / ".git" / "MERGE_HEAD").exists()


def test_a_merge_being_settled_by_hand_is_never_thrown_away(tmp_path, monkeypatch):
    """With a merge stopped part way and being settled by hand, git merge failed on it and
    the abort that always followed threw the settling away (the release review, 2026-11-03)."""
    a, b = _copies(tmp_path)
    (b / "job_search_tracker.csv").write_text("company\nKestrel Mutual\nLarkspur Retail\n")
    _git(b, "commit", "-qam", "another chat's row")
    _git(b, "push", "-q", "origin", "HEAD:master")
    (a / "job_search_tracker.csv").write_text("company\nKestrel Mutual\nQuayside Foods\n")
    _git(a, "commit", "-qam", "this chat's row")
    _git(a, "fetch", "-q", "origin", "master")
    # Stops on the conflict. With a name to commit as: without one, git refuses before it
    # begins, and no merge is in progress at all (CI's Python 3.9 leg, 2026-11-03).
    subprocess.run(["git", "-C", str(a), "merge", "--no-edit", "origin/master"],
                   capture_output=True, text=True, encoding="utf-8",
                   env=dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
                            GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com"))
    assert (a / ".git" / "MERGE_HEAD").exists(), "the test's own merge stopped part way"
    settled = "company\nKestrel Mutual\nLarkspur Retail\nQuayside Foods\n"
    (a / "job_search_tracker.csv").write_text(settled)      # settled by hand, not yet added
    _here(monkeypatch, a)
    said = app_setup.take_master()
    assert said.startswith("app: a merge is being settled") and "left as it is" in said
    assert (a / ".git" / "MERGE_HEAD").exists(), "the merge is still there to finish"
    assert (a / "job_search_tracker.csv").read_text() == settled


def test_a_page_update_takes_no_master_while_a_landing_runs(tmp_path, monkeypatch):
    """The landing merges master itself; a page update merging at the same moment fought it
    over git's index (the release review, 2026-11-03)."""
    import land
    a, b = _copies(tmp_path)
    (b / "round.json").write_text('{"jobs": 10}\n')
    _git(b, "add", "-A")
    _git(b, "commit", "-qm", "a search")
    _git(b, "push", "-q", "origin", "HEAD:master")
    _here(monkeypatch, a)
    lock = os.path.join(land.git_dir(str(a)), land.LOCK_FILE)
    with open(lock, "w", encoding="utf-8") as fh:
        fh.write(land.lock_text())
    head = _git(a, "rev-parse", "HEAD").stdout
    assert app_setup.take_master() == ""
    assert _git(a, "rev-parse", "HEAD").stdout == head and not (a / "round.json").exists()
    os.remove(lock)
    assert app_setup.take_master() == "" and (a / "round.json").exists()


def test_the_next_chat_is_told_of_work_waiting_since_an_earlier_day(tmp_path, monkeypatch):
    """A landing that was not green pushes its branch to wait, and every landing after brings
    it in (tools/land.py). Work still waiting a day later is kept out by something (a check
    not green, a save refused), and nothing ever said so (the stranger audit, 2026-11-03,
    X-30): the start names it, with what to do, and the line the person hears once."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from test_a_beginner_is_told_in_plain_words import _plain
    a, b = _copies(tmp_path)
    _git(b, "switch", "-q", "-c", "claude/earlier-chat")
    (b / "job_search_tracker.csv").write_text("company\nKestrel Mutual\nLarkspur Retail\n")
    # Two days ago on the clock a commit's age is read on (a fixed day turned a week old on
    # the calendar, and 400 days old with the clock moved on).
    import time
    subprocess.run(["git", "-C", str(b), "commit", "-qam", "unlanded"], check=True,
                   env=dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
                            GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com",
                            GIT_COMMITTER_DATE="@%d +0000" % (time.time() - 2 * 86400)))
    _git(b, "push", "-q", "origin", "claude/earlier-chat")
    _here(monkeypatch, a)
    monkeypatch.setenv("LJS_PROFILE", str(a / "profile"))
    assert list(app_setup._stranded()) == ["origin/claude/earlier-chat"]
    monkeypatch.setattr(app_setup, "state", lambda runner=None: {
        "repo": {"kind": "private"}, "setup": {"state": "here", "say": ""},
        "page": {"url": "https://claude.ai/code/artifact/example"}, "page_current": True,
        "stale": False, "answers": {}, "set_up": True})
    monkeypatch.setattr(app_setup, "_finished", lambda: True)
    _code, lines = app_setup.start(on="test", tools="none")
    said = "\n".join(lines)
    assert "origin/claude/earlier-chat" in said and "python3 tools/land.py" in said
    assert app_setup.UNSAVED_SAY in said
    _plain(app_setup.UNSAVED_SAY)
    # Said once a day, and never twice in one start: the same work stuck for days is not
    # also said with the makers' link (the re-audit of 4 November).
    import report
    monkeypatch.setattr(report, "stuck", lambda today=None, st=None: [
        {"state": "waiting", "since": "2026-10-30", "days": 5, "say": report.STATES["waiting"][0],
         "link": report.link(states=["waiting"])}])
    _code, lines = app_setup.start(on="test", tools="none")
    said = "\n".join(lines)
    assert "origin/claude/earlier-chat" in said and "python3 tools/land.py" in said
    assert app_setup.UNSAVED_SAY not in said and "told report-waiting" not in said
    _code, lines = app_setup.start(on="test", tools="none", work="draft~a")
    assert "earlier-chat" not in "\n".join(lines), "a job's own chat lands; it says nothing"


def test_the_app_itself_and_a_copy_with_no_profile_are_left_alone(tmp_path, monkeypatch):
    a, _ = _copies(tmp_path)
    monkeypatch.setattr(app_setup, "ROOT", str(a))
    monkeypatch.setattr(app_setup, "origin", lambda: tuple(app_setup.APP_REPO.split("/")))
    assert app_setup.take_master() == ""
    monkeypatch.setattr(app_setup, "ROOT", str(tmp_path / "nowhere"))
    assert app_setup.take_master() == ""
