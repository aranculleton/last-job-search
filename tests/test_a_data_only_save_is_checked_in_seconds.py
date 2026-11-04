"""A save of the person's own files is checked in seconds, and its failures are read for what they are.

Engine audit 32 and 33 (2026-11-03): `./tools/ci_local.sh --quick` with nothing changed took
5 minutes 8 seconds in the maintainer's own copy, 124 seconds of it building the app's tree
from HEAD for a leak scan of app files that had not changed; and a failure of the person's
own tests caused by the computer printed "2 now fail after this update... rewrite, retire
and bring in line", though no update was in the change. Both are run here on a copy shaped
like the maintainer's (invented example person, no change since master).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import repo_files  # noqa: E402

sys.path.insert(0, os.path.join(ROOT, "tools"))
import local_path  # noqa: E402

# Git Bash on Windows, never the Linux layer's launcher a bare "bash" reaches there.
BASH = local_path.bash() or "bash"


def _git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), "-c", "user.name=t",
                           "-c", "user.email=t@example.com", *args],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")


@pytest.fixture
def copy(tmp_path):
    """The app's tracked files with the example person as the person, committed, with
    origin/master at that commit: nothing changed since master."""
    if not shutil.which("git") or not local_path.bash():
        pytest.skip("needs git and bash")
    files = repo_files.tracked(root=ROOT, app_only=False)
    c = tmp_path / "copy"
    for rel in files:
        if not rel or rel.startswith(("profile.example/", "docs/images/")):
            continue
        src = os.path.join(ROOT, rel)
        if os.path.isfile(src):
            os.makedirs(c / os.path.dirname(rel), exist_ok=True)
            shutil.copy2(src, c / rel)
    shutil.copytree(os.path.join(ROOT, "profile.example"), c / "profile",
                    ignore=shutil.ignore_patterns("state", "__pycache__"))
    os.makedirs(c / "profile" / "tests", exist_ok=True)
    (c / "profile" / "tests" / "test_this_computer.py").write_text(
        "def test_a_fault_of_this_computer():\n    assert False, 'the checkout path'\n",
        encoding="utf-8")
    _git(tmp_path, "init", "-q", str(c))
    _git(c, "add", "-A")
    _git(c, "commit", "-qm", "a person's copy")
    _git(c, "remote", "add", "origin", "https://github.com/example-owner/my-search")
    _git(c, "update-ref", "refs/remotes/origin/master", "HEAD")
    return c


@pytest.mark.timing
def test_nothing_changed_skips_the_app_tree_and_never_blames_an_update(copy):
    # The check runs the first python3 on the path (tools/py.sh): this one, which has pytest,
    # so the person's own failing test is run, never skipped as "pytest is not installed"
    # on a machine whose first python3 lacks it (the person job on GitHub, 2026-11-03).
    here = copy.parent / "bin"
    here.mkdir(exist_ok=True)
    path = os.environ.get("PATH", "")
    if os.name != "nt":
        # A launcher, never a link: a link to a virtual environment's python starts the base
        # Python, which finds no pyvenv.cfg beside the link and so none of its packages.
        launch = here / "python3"
        launch.write_text('#!/bin/sh\nexec "%s" "$@"\n' % sys.executable, encoding="utf-8")
        launch.chmod(0o755)
        path = str(here) + os.pathsep + path
    env = dict(os.environ, LJS_APP_URL="https://github.com/example-owner/last-job-search",
               PYTHONDONTWRITEBYTECODE="1", PATH=path)
    env.pop("LJS_PROFILE", None)
    env.pop("LJS_STATE", None)
    env.pop("VIRTUAL_ENV", None)
    if sys.prefix != sys.base_prefix:
        # Run from a virtual environment (the person job, on every system): tools/py.sh takes
        # VIRTUAL_ENV's Python first, the one with pytest, wherever the launcher cannot go.
        env["VIRTUAL_ENV"] = sys.prefix
    start = time.monotonic()
    r = subprocess.run([BASH, "tools/ci_local.sh", "--quick"], cwd=copy, env=env,
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=600)
    took = time.monotonic() - start
    out = r.stdout + r.stderr
    line = next(ln for ln in out.splitlines() if "leak scan (app tree built from HEAD)" in ln)
    assert "SKIP" in line and "none of the app's files changed" in line, out
    # The failing own test is reported, and never as something an update did.
    assert r.returncode == 1 and "pytest (profile/tests, on this person)" in out
    assert "no update of the app is in this change" in out, out
    assert "after this update" not in out and "rewrite, retire" not in out, out
    assert took < 300, took


def test_a_profile_missing_a_setting_never_lands_and_is_named_never_traced(copy):
    """X-39 (the stranger audit, 2026-11-03): a hand edit or a merge left profile/search.py
    with no SALARY_FLOOR. The check only loaded each file, so the change landed, and then
    every page update and brief crashed with a raw traceback, naming nothing. The check now
    builds the page from the person's files, and a build that stops says which file."""
    (copy / "profile" / "search.py").write_text("# emptied by a merge\n", encoding="utf-8")
    (copy / "profile" / "tests" / "test_this_computer.py").unlink()
    _git(copy, "add", "-A")
    _git(copy, "commit", "-qm", "a setting lost")
    env = dict(os.environ, LJS_APP_URL="https://github.com/example-owner/last-job-search",
               PYTHONDONTWRITEBYTECODE="1")
    env.pop("LJS_PROFILE", None)
    env.pop("LJS_STATE", None)
    r = subprocess.run([sys.executable, "tools/app.py", "model"], cwd=copy, env=env,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = r.stdout + r.stderr
    assert r.returncode == 1 and "Traceback" not in out, out
    assert "profile/search.py has no" in out, out
    r = subprocess.run([BASH, "tools/ci_local.sh", "--quick"], cwd=copy, env=env,
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=600)
    out = r.stdout + r.stderr
    line = next((ln for ln in out.splitlines() if "your page can be built from your files" in ln), None)
    assert line is not None, out
    assert "FAIL" in line and r.returncode == 1, out
    assert "profile/search.py has no" in out
