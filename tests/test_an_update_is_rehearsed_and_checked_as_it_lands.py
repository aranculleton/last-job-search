"""An update is rehearsed from where the person's repo really is, and checked as it lands.

From the sync audit, 2026-10-21:
- `rehearse_sync.py` copied only the repo's branches, so its default start, origin/master,
  was "not a commit" of a repo whose newest commit is on no local branch (a cloud checkout,
  a local master behind origin's), and an app commit given as --ref was called the same.
  A run with --keep that stopped early kept its copies without saying where.
- The light local CI asks `personal_paths.py --only-personal-changed` whether only the
  person's own files changed. An app file moved into a personal folder was read as one
  change, the new path, so the app's checks were skipped though an app file was gone.

Every repository here is a throwaway one made by the test.
"""
from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import personal_paths  # noqa: E402
import rehearse_sync  # noqa: E402


def _git(cwd, *args):
    return subprocess.run(["git", "-C", cwd, "-c", "user.name=t", "-c", "user.email=t@example.com",
                           *args], capture_output=True, text=True)


def _repo_on_no_branch(tmp_path):
    """A person's repo whose newest commit is held only by origin/master."""
    upstream, repo = str(tmp_path / "upstream"), str(tmp_path / "repo")
    subprocess.run(["git", "init", "-q", "-b", "master", upstream], check=True)
    _git(upstream, "commit", "-q", "--allow-empty", "-m", "one")
    subprocess.run(["git", "clone", "-q", upstream, repo], check=True, capture_output=True)
    _git(upstream, "commit", "-q", "--allow-empty", "-m", "two, only on origin")
    _git(repo, "fetch", "-q", "origin")
    return repo


def test_a_start_held_only_by_origin_master_is_copied_by_its_commit(tmp_path):
    repo = _repo_on_no_branch(tmp_path)
    origin = str(tmp_path / "copy.git")
    subprocess.run(["git", "clone", "-q", "--bare", "--no-local", repo, origin], check=True,
                   capture_output=True)
    want = _git(repo, "rev-parse", "origin/master").stdout.strip()
    assert _git(origin, "cat-file", "-e", want + "^{commit}").returncode   # not copied
    sha, said = rehearse_sync.start_commit(repo, "origin/master", origin)
    assert sha == want and "on no branch" in said
    assert _git(origin, "rev-parse", "master").stdout.strip() == want


def test_a_commit_that_is_not_there_is_said_plainly(tmp_path):
    repo = _repo_on_no_branch(tmp_path)
    origin = str(tmp_path / "copy.git")
    subprocess.run(["git", "clone", "-q", "--bare", "--no-local", repo, origin], check=True,
                   capture_output=True)
    sha, said = rehearse_sync.start_commit(repo, "no-such-branch", origin)
    assert sha == "" and said.startswith("no-such-branch is not a commit of")
    # The app's own commit, given where the person's start goes, is named as the app's.
    app = _git(ROOT, "rev-parse", "HEAD").stdout.strip()
    sha, said = rehearse_sync.start_commit(repo, app, origin)
    assert sha == "" and "is a commit of the app" in said and "--app" in said


def test_kept_copies_are_named_even_when_the_run_stops_early(tmp_path, capsys):
    repo = _repo_on_no_branch(tmp_path)
    assert rehearse_sync.rehearse(repo, "origin/master", "no-such-app-commit", ci=False,
                                  keep=True) == 2
    out = capsys.readouterr().out
    assert "not a commit of this app" in out and "The copies are kept in " in out
    kept = out.rsplit("The copies are kept in ", 1)[1].strip()
    assert os.path.isdir(kept)
    import shutil
    shutil.rmtree(kept, ignore_errors=True)


def test_an_app_file_moved_into_a_personal_folder_is_an_app_change(tmp_path):
    repo = str(tmp_path / "repo")
    subprocess.run(["git", "init", "-q", "-b", "master", repo], check=True)
    os.makedirs(os.path.join(repo, "tools"))
    with open(os.path.join(repo, "tools", "fit.py"), "w") as fh:
        fh.write("def score():\n    return 1\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "the app")
    _git(repo, "update-ref", "refs/remotes/origin/master", "HEAD")
    os.makedirs(os.path.join(repo, "documents"))
    _git(repo, "mv", "tools/fit.py", "documents/fit_notes.py")
    _git(repo, "commit", "-qm", "moved")
    got = personal_paths.changed(repo)
    assert "tools/fit.py" in got and "documents/fit_notes.py" in got
    app, _mine = personal_paths.split(got)
    assert "tools/fit.py" in app
