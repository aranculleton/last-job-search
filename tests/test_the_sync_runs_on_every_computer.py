"""tools/sync_app.py on a person's own computer: Windows, a Mac, Linux.

Found on 2026-10-25, each one a sync that broke for a reason the person could not see:
- git's output read in Windows' own encoding, so a CHANGELOG name with an accent stopped
  the sync after its commit, with no "What changed", no upgrades and no record of the day;
- no git on the computer was a Python traceback;
- a fetch waiting on a sign-in window nobody could see held the chat;
- a chat's own folder made beside the repo, where Claude Code will not let a chat work,
  printed unquoted, so a path with a space could not be used;
- the first sync of a repo with no profile yet printed twenty headlines about the app.
"""
import os
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import rehearse_sync  # noqa: E402
import sync_app  # noqa: E402

ENV = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
           GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com",
           PYTHONDONTWRITEBYTECODE="1")

pytestmark = pytest.mark.skipif(not shutil.which("git"), reason="needs git")


def g(cwd, *args, check=True):
    return subprocess.run(["git", *args], cwd=cwd, env=ENV, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=check)


def _repo(path):
    path.mkdir(parents=True)
    g(path, "init", "-q", "-b", "master")
    (path / "a.txt").write_text("one\n", encoding="utf-8")
    g(path, "add", "-A")
    g(path, "commit", "-q", "-m", "one")
    return path


def test_git_output_that_is_not_utf8_is_read_not_raised(tmp_path):
    repo = _repo(tmp_path / "r")
    (repo / "CHANGELOG.md").write_bytes(b"- **A fix** by \xcd\xf1igo, \x8d\xff saved in cp1252\n")
    g(repo, "add", "-A")
    g(repo, "commit", "-q", "-m", "changelog")
    r = sync_app.run_git(str(repo), "show", "HEAD", "--", "CHANGELOG.md")
    assert r.returncode == 0 and "A fix" in r.stdout and "�" in r.stdout


def _fake_git(tmp_path, monkeypatch, body):
    """git as a Python script, started in its own process with exactly what run_git gives
    it (arguments, environment, timeout). A file called git holding a shell script stood in
    for it before, and Windows starts no such file: it ran the real git.exe, or none."""
    script = tmp_path / "fake_git.py"
    script.write_text(body, encoding="utf-8")
    real = subprocess.run

    def run(cmd, *args, **kw):
        assert cmd[0] == "git", cmd
        return real([sys.executable, str(script), *cmd[1:]], *args, **kw)
    monkeypatch.setattr(sync_app.subprocess, "run", run)


def test_git_never_stops_to_ask_anyone(tmp_path, monkeypatch):
    _fake_git(tmp_path, monkeypatch, "import os\nprint('prompt=%s gcm=%s' % ("
              "os.environ.get('GIT_TERMINAL_PROMPT'), os.environ.get('GCM_INTERACTIVE')))\n")
    monkeypatch.delenv("GIT_TERMINAL_PROMPT", raising=False)
    monkeypatch.setenv("GCM_INTERACTIVE", "always")
    r = sync_app.run_git(str(tmp_path), "fetch")
    assert r.stdout.strip() == "prompt=0 gcm=never"


def test_a_git_that_hangs_is_stopped_and_is_an_ordinary_failure(tmp_path, monkeypatch):
    _fake_git(tmp_path, monkeypatch, "import time\ntime.sleep(30)\n")
    r = sync_app.run_git(str(tmp_path), "fetch", timeout=0.5)
    assert r.returncode == 124 and "was stopped" in r.stderr


def test_no_git_on_the_computer_is_one_plain_line(tmp_path):
    env = {"PATH": str(tmp_path), "HOME": str(tmp_path), "PYTHONDONTWRITEBYTECODE": "1"}
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "sync_app.py"), "--pull"],
                       env=env, capture_output=True, text=True, timeout=60)
    assert r.returncode == 1
    assert "Traceback" not in r.stderr
    assert r.stdout.strip() == sync_app.NO_GIT
    assert sync_app.stale() in (True, False)            # the helpers other tools call never stop


def _clone(tmp_path, name="My Job Search"):
    origin = _repo(tmp_path / "origin")
    me = tmp_path / name
    g(tmp_path, "clone", "-q", str(origin), str(me))
    return origin, me


def test_a_chats_own_folder_is_inside_the_project_and_said_quoted(tmp_path, monkeypatch,
                                                                    capsys):
    _origin, me = _clone(tmp_path)
    shutil.copy(os.path.join(ROOT, ".gitignore"), me / ".gitignore")
    g(me, "add", ".gitignore")
    g(me, "commit", "-q", "-m", "the app's ignore rules")
    monkeypatch.setattr(sync_app, "ROOT", str(me))
    assert sync_app.worktree("Laptop chat") == 0
    out = capsys.readouterr().out
    folder = me / ".claude" / "worktrees" / "laptop-chat"
    assert folder.is_dir() and (folder / "a.txt").exists()
    assert f"'{folder}'" in out
    assert f"git worktree remove '{folder}'" in out
    # rehearse_sync reads the folder back out of that line, space and all
    assert rehearse_sync.folder_said(out) == str(folder)
    # and the main folder does not see it as a change
    assert g(me, "status", "--porcelain", "--untracked-files=all").stdout.strip() == ""


def test_a_folder_is_still_made_when_master_cannot_be_fetched(tmp_path, monkeypatch, capsys):
    origin, me = _clone(tmp_path, "me")
    g(me, "remote", "set-url", "origin", str(tmp_path / "nowhere"))
    monkeypatch.setattr(sync_app, "ROOT", str(me))
    assert sync_app.worktree("two") == 0
    out = capsys.readouterr().out
    assert "could not be fetched (" in out and "copy this computer fetched last" in out
    assert (me / ".claude" / "worktrees" / "two" / "a.txt").exists()


def test_with_no_copy_of_master_at_all_no_folder_is_made_and_it_says_why(tmp_path,
                                                                          monkeypatch, capsys):
    me = _repo(tmp_path / "solo")
    g(me, "remote", "add", "origin", str(tmp_path / "nowhere"))
    monkeypatch.setattr(sync_app, "ROOT", str(me))
    assert sync_app.worktree("two") == 1
    out = capsys.readouterr().out
    assert "no copy of it yet" in out and "fatal" in out.lower()


def test_the_rehearsal_starts_from_ref_not_the_branch_the_repo_was_on(tmp_path):
    repo = _repo(tmp_path / "theirs")
    g(repo, "switch", "-q", "-c", "scratch")
    (repo / "b.txt").write_text("scratch\n", encoding="utf-8")
    g(repo, "add", "-A")
    g(repo, "commit", "-q", "-m", "scratch work")
    bare = tmp_path / "origin.git"
    g(tmp_path, "clone", "-q", "--bare", "--no-local", str(repo), str(bare))
    sha, _said = rehearse_sync.start_commit(str(repo), "master", str(bare))
    assert sha
    chat = tmp_path / "chat"
    g(tmp_path, "clone", "-q", str(bare), str(chat))
    assert g(chat, "rev-parse", "HEAD").stdout.strip() == sha
    assert not (chat / "b.txt").exists()


def test_the_first_sync_before_setup_says_nothing_about_what_changed(tmp_path):
    app = tmp_path / "app"
    app.mkdir()
    g(app, "init", "-q", "-b", "master")
    (app / "tools").mkdir()
    for tool in ("sync_app.py", "personal_paths.py"):
        shutil.copy(os.path.join(ROOT, "tools", tool), app / "tools" / tool)
    (app / ".gitignore").write_text("__pycache__/\n")
    (app / "CHANGELOG.md").write_text("# Changelog\n")
    g(app, "add", "-A")
    g(app, "commit", "-q", "-m", "app v1")
    me = tmp_path / "me"
    shutil.copytree(app, me, ignore=shutil.ignore_patterns(".git"))
    g(me, "init", "-q", "-b", "master")
    g(me, "remote", "add", "origin", "https://github.com/someone/my-job-search")
    g(me, "add", "-A")
    g(me, "commit", "-q", "-m", "Initial commit")
    (app / "CHANGELOG.md").write_text("# Changelog\n- **Twenty things you never used**\n")
    g(app, "add", "-A")
    g(app, "commit", "-q", "-m", "app v2")

    def run():
        return subprocess.run([sys.executable, str(me / "tools" / "sync_app.py")], cwd=me,
                              env=dict(ENV, LJS_APP_URL=str(app)), capture_output=True,
                              text=True, timeout=120)
    r = run()
    assert r.returncode == 0, r.stdout + r.stderr
    assert "What changed" not in r.stdout and "Twenty things" not in r.stdout
    # Once there is a profile, the lines come back.
    (me / "profile").mkdir()
    (me / "profile" / "person.json").write_text("{}\n")
    g(me, "add", "-A")
    g(me, "commit", "-q", "-m", "set me up")
    (app / "CHANGELOG.md").write_text("# Changelog\n- **Twenty things you never used**\n"
                                      "- **One thing for you**\n")
    g(app, "add", "-A")
    g(app, "commit", "-q", "-m", "app v3")
    r = run()
    assert r.returncode == 0, r.stdout + r.stderr
    assert "What changed" in r.stdout and "One thing for you" in r.stdout
