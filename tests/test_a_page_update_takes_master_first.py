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
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True,
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


def test_the_app_itself_and_a_copy_with_no_profile_are_left_alone(tmp_path, monkeypatch):
    a, _ = _copies(tmp_path)
    monkeypatch.setattr(app_setup, "ROOT", str(a))
    monkeypatch.setattr(app_setup, "origin", lambda: tuple(app_setup.APP_REPO.split("/")))
    assert app_setup.take_master() == ""
    monkeypatch.setattr(app_setup, "ROOT", str(tmp_path / "nowhere"))
    assert app_setup.take_master() == ""
