"""tools/sync_app.py: a person's repo takes the app's updates and never its own edits back.

Each test builds two throwaway repositories: an "app" with a few commits, and a
person's repo made from it the way "Use this template" makes one (the app's
files, a fresh history, then a profile and a tracker on top). LJS_APP_URL points
the tool at the local app, so nothing touches the network.
"""
import os
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
           GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com",
           PYTHONDONTWRITEBYTECODE="1")


def sh(cwd, *args):
    return subprocess.run(args, cwd=cwd, env=ENV, text=True, capture_output=True, check=True).stdout


def write(repo, rel, text):
    p = os.path.join(repo, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(text)


def commit(repo, msg):
    sh(repo, "git", "add", "-A")
    sh(repo, "git", "commit", "-q", "-m", msg)


def head(repo):
    return sh(repo, "git", "rev-parse", "HEAD").strip()


def read(repo, rel):
    with open(os.path.join(repo, rel), encoding="utf-8") as fh:
        return fh.read()


@pytest.fixture
def repos(tmp_path):
    app = str(tmp_path / "app")
    os.makedirs(app)
    sh(app, "git", "init", "-q", "-b", "master")
    for tool in ("sync_app.py", "personal_paths.py"):
        write(app, f"tools/{tool}", read(ROOT, f"tools/{tool}"))
    write(app, ".gitignore", "__pycache__/\n")
    write(app, "README.md", "v1\n")
    write(app, "tools/x.py", "a = 1\n")
    write(app, "CHANGELOG.md", "# Changelog\n")
    commit(app, "app v1")

    me = str(tmp_path / "me")
    shutil.copytree(app, me, ignore=shutil.ignore_patterns(".git"))
    sh(me, "git", "init", "-q", "-b", "master")
    sh(me, "git", "remote", "add", "origin", "https://github.com/someone/my-job-search")
    commit(me, "Initial commit")
    write(me, "profile/person.json", "{}\n")
    write(me, "job_search_tracker.csv", "date,company\n")
    commit(me, "set me up")
    return app, me


def run(me, app, *args):
    env = dict(ENV, LJS_APP_URL=app)
    r = subprocess.run([sys.executable, os.path.join(me, "tools", "sync_app.py"), *args],
                       cwd=me, env=env, text=True, capture_output=True)
    return r.returncode, r.stdout + r.stderr


def test_the_first_sync_merges_a_template_made_repo(repos):
    app, me = repos
    write(app, "README.md", "v2\n")
    write(app, "CHANGELOG.md", "# Changelog\n- README is v2\n")
    commit(app, "app v2")
    rc, out = run(me, app)
    assert rc == 0, out
    assert read(me, "README.md") == "v2\n"
    assert read(me, "job_search_tracker.csv") == "date,company\n"
    assert len(sh(me, "git", "log", "-1", "--format=%P").split()) == 2
    assert "README is v2" in out


def test_a_later_sync_brings_only_the_new_commits(repos):
    app, me = repos
    assert run(me, app)[0] == 0
    write(app, "tools/x.py", "a = 2\n")
    commit(app, "app v3")
    rc, out = run(me, app)
    assert rc == 0, out
    assert read(me, "tools/x.py") == "a = 2\n"
    assert "1 new commit" in out
    rc, out = run(me, app)
    assert rc == 0 and "up to date" in out


def test_check_reports_and_changes_nothing(repos):
    app, me = repos
    run(me, app)
    write(app, "tools/x.py", "a = 3\n")
    commit(app, "app v3")
    before = head(me)
    rc, out = run(me, app, "--check")
    assert rc == 0 and "1 app commit(s) to bring in" in out
    assert head(me) == before


def test_an_app_file_edited_here_is_put_back_and_named(repos):
    app, me = repos
    run(me, app)
    write(me, "README.md", "my edit\n")
    write(me, "tools/mine.py", "mine = True\n")
    commit(me, "local edits")
    rc, out = run(me, app, "--check")
    assert "drift: 1" in out and "README.md" in out
    rc, out = run(me, app)
    assert rc == 0, out
    assert read(me, "README.md") == "v1\n"
    assert "put back (edited here): README.md" in out
    assert read(me, "tools/mine.py") == "mine = True\n"       # an addition is kept
    assert "README.md" in sh(me, "git", "log", "-1", "--format=%B")


def test_a_conflict_on_an_app_file_takes_the_apps_version(repos):
    app, me = repos
    run(me, app)
    write(me, "tools/x.py", "a = 'mine'\n")
    commit(me, "local edit")
    write(app, "tools/x.py", "a = 'app'\n")
    commit(app, "app edit")
    rc, out = run(me, app)
    assert rc == 0, out
    assert read(me, "tools/x.py") == "a = 'app'\n"


def test_an_app_that_carries_a_personal_path_is_refused(repos):
    app, me = repos
    write(app, "job_search_tracker.csv", "date,company\nleaked,row\n")
    commit(app, "broken app")
    before = head(me)
    rc, out = run(me, app)
    assert rc == 1 and "job_search_tracker.csv" in out
    assert head(me) == before
    assert read(me, "job_search_tracker.csv") == "date,company\n"


def test_uncommitted_changes_stop_it_first(repos):
    app, me = repos
    write(me, "README.md", "half done\n")
    rc, out = run(me, app)
    assert rc == 1 and "Commit or stash" in out
    assert read(me, "README.md") == "half done\n"


def test_in_the_app_itself_it_does_nothing(repos):
    app, me = repos
    sh(me, "git", "remote", "set-url", "origin", app)
    before = head(me)
    rc, out = run(me, app)
    assert rc == 0 and "the app itself" in out and head(me) == before


def test_an_unreachable_app_is_exit_two(repos, tmp_path):
    _, me = repos
    rc, out = run(me, str(tmp_path / "nowhere"))
    assert rc == 2 and "could not be reached" in out


def test_adopt_records_the_history_without_changing_a_file(tmp_path):
    # The repo the app was built from: its app-owned files are the app's exactly.
    me = str(tmp_path / "me")
    os.makedirs(me)
    sh(me, "git", "init", "-q", "-b", "master")
    sh(me, "git", "remote", "add", "origin", "https://github.com/someone/private")
    for tool in ("sync_app.py", "personal_paths.py"):
        write(me, f"tools/{tool}", read(ROOT, f"tools/{tool}"))
    write(me, ".gitignore", "__pycache__/\n")
    write(me, "README.md", "v1\n")
    write(me, "profile/person.json", "{}\n")
    commit(me, "years of history")
    app = str(tmp_path / "app")
    shutil.copytree(me, app, ignore=shutil.ignore_patterns(".git", "profile"))
    sh(app, "git", "init", "-q", "-b", "master")
    commit(app, "app tree")

    tree = sh(me, "git", "rev-parse", "HEAD^{tree}")
    rc, out = run(me, app, "--adopt")
    assert rc == 0, out
    assert sh(me, "git", "rev-parse", "HEAD^{tree}") == tree
    write(app, "README.md", "v2\n")
    commit(app, "app v2")
    rc, out = run(me, app)
    assert rc == 0 and read(me, "README.md") == "v2\n" and "1 new commit" in out


def test_adopt_refuses_when_a_file_differs(repos):
    app, me = repos
    write(app, "README.md", "v2\n")
    commit(app, "app v2")
    before = head(me)
    rc, out = run(me, app, "--adopt")
    assert rc == 1 and "README.md" in out and head(me) == before


def test_a_shallow_clone_finds_its_last_sync_instead_of_starting_over(repos, tmp_path):
    """Cloud sessions clone shallow. A last sync below the clone's depth looks like
    no sync at all, and treating it as one would re-merge the whole app."""
    app, me = repos
    run(me, app)
    for i in range(5):
        write(me, f"documents/note{i}.md", f"{i}\n")
        commit(me, f"work {i}")
    origin = str(tmp_path / "origin.git")
    sh(str(tmp_path), "git", "clone", "-q", "--bare", me, origin)
    shallow = str(tmp_path / "shallow")
    sh(str(tmp_path), "git", "clone", "-q", "--depth", "1", "file://" + origin, shallow)
    assert sh(shallow, "git", "rev-parse", "--is-shallow-repository").strip() == "true"
    write(app, "tools/x.py", "a = 9\n")
    commit(app, "app v4")
    rc, out = run(shallow, app)
    assert rc == 0, out
    assert "1 new commit" in out and read(shallow, "tools/x.py") == "a = 9\n"
