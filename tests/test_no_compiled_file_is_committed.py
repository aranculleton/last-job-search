"""No compiled Python file is written beside the profile or committed with it.

From a real repo on 2026-10-21: 128 .pyc files under profile/__pycache__ and
profile/tests/__pycache__ were committed with the profile, by a forced add, and rode along
in every commit after. The tools no longer write them there, and the guards name any
committed one with the command that takes it out.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import person  # noqa: E402
import security_guards  # noqa: E402


def test_loading_a_profile_module_leaves_no_compiled_copy(tmp_path, monkeypatch):
    prof = tmp_path / "profile"
    prof.mkdir()
    (prof / "search.py").write_text("PORTALS = ()\n", encoding="utf-8")
    monkeypatch.setenv(person.ENV, str(prof))
    person.reset()
    try:
        assert person.module("search").PORTALS == ()
        assert not (prof / "__pycache__").exists()
        assert sys.dont_write_bytecode is False or os.environ.get("PYTHONDONTWRITEBYTECODE")
    finally:
        person.reset()


def test_a_committed_compiled_file_fails_the_guards_with_the_way_out(tmp_path, monkeypatch):
    repo = tmp_path / "r"
    (repo / "profile" / "__pycache__").mkdir(parents=True)
    (repo / "profile" / "__pycache__" / "search.cpython-313.pyc").write_bytes(b"\0")
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "-f", "-A"], check=True)
    monkeypatch.setattr(security_guards, "ROOT", Path(repo))
    monkeypatch.setattr(security_guards, "errors", [])
    security_guards.check_tracked_caches()
    [msg] = security_guards.errors
    assert "1 compiled Python file(s) are committed" in msg
    assert "git rm -r -q --cached profile/__pycache__" in msg
    subprocess.run(["git", "-C", str(repo), "rm", "-r", "-q", "--cached", "profile/__pycache__"],
                   check=True)
    monkeypatch.setattr(security_guards, "errors", [])
    security_guards.check_tracked_caches()
    assert security_guards.errors == []
