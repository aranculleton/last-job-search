"""What a chat on the person's own computer runs every day, on a computer laid out like
Windows with python.org's Python.

Simulated on whatever runs the suite, as far as a non-Windows computer can be made to look
like one: a `python3` first on PATH that is the Microsoft Store stand-in (prints a message,
exits 49), `python` the real one, the terminal in cp1252 (PYTHONIOENCODING), the C locale
with no coercion to UTF-8 (so a default encoding is ASCII, harsher than cp1252), UTF-8 mode
off, and a folder whose name has a space. Names with letters cp1252 lacks ("Ł") go through
every piece. A real Windows run is the CI leg for the computer chat; this is what can be
shown here, and it is not that.
"""
import json
import os
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
sys.path.insert(0, TOOLS)

pytestmark = pytest.mark.skipif(not (shutil.which("git") and shutil.which("sh")),
                                reason="needs git and a POSIX sh")

STORE_STUB = ("#!/bin/sh\necho 'Python was not found; run without arguments to install from "
              "the Microsoft Store.' >&2\nexit 49\n")
GIT_ID = dict(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
              GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com")


@pytest.fixture
def win(tmp_path):
    """(the environment, the stand-in folder's `python`)."""
    b = tmp_path / "Program Files" / "bin"
    b.mkdir(parents=True)
    (b / "python3").write_text(STORE_STUB)
    (b / "python3").chmod(0o755)
    py = str(b / "python")
    if sys.platform == "win32":
        # On Windows itself the layout is real already, and a link to a virtual
        # environment's python.exe starts nothing ("No pyvenv.cfg file": its launcher reads
        # that file beside itself, https://docs.python.org/3/library/venv.html#how-venvs-work).
        # `python` on PATH is the real one for sh, which the hooks run in, and the tests run
        # it by its own path.
        real = sys.executable.replace("\\", "/")
        (b / "python").write_text(f'#!/bin/sh\nexec "{real}" "$@"\n', encoding="utf-8")
        py = sys.executable
    else:
        os.symlink(sys.executable, b / "python")
    env = {k: v for k, v in os.environ.items()
           if k not in ("PYTHONUTF8", "PYTHONIOENCODING", "LANG", "LC_ALL", "LC_CTYPE",
                        "LJS_PROFILE", "LJS_STATE", "VIRTUAL_ENV",
                        # A cloud computer may set these itself: here only the settings do.
                        "GIT_TERMINAL_PROMPT", "GCM_INTERACTIVE", "GIT_ASKPASS", "SSH_ASKPASS")}
    env.update(GIT_ID, PATH=str(b) + os.pathsep + os.environ["PATH"], PYTHONIOENCODING="cp1252",
               LC_ALL="C", LANG="C", PYTHONCOERCECLOCALE="0", PYTHONUTF8="0",
               PYTHONDONTWRITEBYTECODE="1", HOME=str(tmp_path / "home"))
    # What the chat's own settings give every command it runs (.claude/settings.json env),
    # bar UTF-8 mode, left off so each tool shows it needs nothing from the chat to cope.
    settings = json.loads(open(os.path.join(ROOT, ".claude", "settings.json"),
                               encoding="utf-8").read())["env"]
    env.update({k: v for k, v in settings.items() if k != "PYTHONUTF8"})
    (tmp_path / "home").mkdir()
    return env, py


def run(argv, cwd, env, stdin=None, timeout=180):
    r = subprocess.run(argv, cwd=cwd, env=env, input=stdin, capture_output=True, timeout=timeout)
    out, err = r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace")
    assert "Traceback" not in err and "UnicodeEncodeError" not in err, err
    return r.returncode, out, err


def git(cwd, *args, env=None):
    return subprocess.run(["git", *args], cwd=cwd, env=dict(os.environ, **GIT_ID, **(env or {})),
                          capture_output=True, text=True, encoding="utf-8", errors="replace",
                          check=True).stdout


def _copy_app(dest):
    shutil.copytree(ROOT, dest, ignore=shutil.ignore_patterns(
        ".git", "__pycache__", ".pytest_cache", "documents", "cv", "cover_letters", "texmf",
        "node_modules", "worktrees", "profile"))


# ------------------------------------------------------------------ the hooks

@pytest.mark.parametrize("event", ["UserPromptSubmit", "Stop"])
def test_both_hooks_run_and_record_a_reaction_naming_lukasz(tmp_path, win, event):
    env, _py = win
    project = tmp_path / "My Job Search"
    _copy_app(project)
    shutil.copytree(os.path.join(ROOT, "profile.example"), project / "profile")
    git(project, "init", "-q", "-b", "master")
    settings = json.loads((project / ".claude" / "settings.json").read_text(encoding="utf-8"))
    cmd = settings["hooks"][event][0]["hooks"][0]["command"]
    transcript = tmp_path / "t.jsonl"
    transcript.write_text("", encoding="utf-8")
    event_in = {"hook_event_name": event, "transcript_path": str(transcript),
                "prompt": "I don't like this, the note to Łukasz is far too formal"}
    rc, out, err = run(["sh", "-c", cmd], project, dict(env, CLAUDE_PROJECT_DIR=str(project)),
                       stdin=json.dumps(event_in).encode("utf-8"))
    assert rc == 0, err
    if out.strip():
        json.loads(out)                                   # what Claude Code reads back


# ------------------------------------------------------------------ the sync

def _person_repo(tmp_path):
    """(the app, the person's repo in "My Job Search", its bare origin)."""
    app = tmp_path / "app"
    _copy_app(app)
    git(app, "init", "-q", "-b", "master")
    git(app, "add", "-A")
    git(app, "commit", "-q", "-m", "app v1")
    me = tmp_path / "My Job Search"
    shutil.copytree(app, me, ignore=shutil.ignore_patterns(".git"))
    git(me, "init", "-q", "-b", "master")
    git(me, "add", "-A")
    git(me, "commit", "-q", "-m", "Initial commit")
    shutil.copytree(os.path.join(ROOT, "profile.example"), me / "profile")
    git(me, "add", "-A")
    git(me, "commit", "-q", "-m", "set me up")
    origin = tmp_path / "origin.git"
    git(tmp_path, "clone", "-q", "--bare", str(me), str(origin))
    git(me, "remote", "add", "origin", str(origin))
    git(me, "fetch", "-q", "origin")
    git(me, "branch", "-q", "--set-upstream-to=origin/master")
    with open(app / "CHANGELOG.md", "a", encoding="utf-8") as fh:
        fh.write("\n- **A reply from Łukasz is read whole**: and a test for it.\n")
    git(app, "commit", "-qam", "app v2")
    return app, me, origin


def test_the_days_sync_pull_and_own_folder_on_windows(tmp_path, win):
    env, py = win
    app, me, _origin = _person_repo(tmp_path)
    env = dict(env, LJS_APP_URL=str(app))
    rc, out, err = run([py, "tools/sync_app.py", "--pull"], me, env)
    assert rc == 0, out + err
    rc, out, err = run([py, "tools/sync_app.py", "--if-stale", "--on", "a model",
                        "--tools", "none"], me, env, timeout=600)
    assert rc == 0, out + err
    assert "A reply from Łukasz is read whole" in out
    assert "already checked today" in run([py, "tools/sync_app.py", "--if-stale", "--on", "x",
                                           "--tools", "none"], me, env)[1]
    rc, out, err = run([py, "tools/sync_app.py", "--worktree", "Laptop chat"], me, env)
    assert rc == 0, out + err
    assert (me / ".claude" / "worktrees" / "laptop-chat" / "tools" / "sync_app.py").exists()
    # The driver it set runs a Python that is not the Store stand-in.
    driver = git(me, "config", "--get", "merge.ljs-state.driver")
    assert "python3 tools/merge_state.py" not in driver and "Program Files" in driver


# ------------------------------------------------------------------ the merge driver

def test_the_row_merge_runs_and_says_what_it_kept_on_windows(tmp_path, win):
    env, py = win
    repo = tmp_path / "My Job Search"
    (repo / "tools").mkdir(parents=True)
    for f in ("merge_state.py", "python_floor.py", "py.sh"):
        shutil.copy(os.path.join(TOOLS, f), repo / "tools" / f)
    shutil.copy(os.path.join(ROOT, ".gitattributes"), repo / ".gitattributes")
    head = "contact_id,name,company,status,notes\n"
    (repo / "network_contacts.csv").write_text(head + "łukasz_w,Łukasz,Zakład,sent,\n",
                                               encoding="utf-8")
    git(repo, "init", "-q", "-b", "master")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "start")
    # The sync sets the driver with the Python that runs it: here, the stand-in's folder.
    rc, _o, err = run([py, "-c", "import sys; sys.path.insert(0, 'tools'); import merge_state; "
                       "merge_state.install('.')"], repo, env)
    assert rc == 0, err
    git(repo, "switch", "-q", "-c", "other")
    (repo / "network_contacts.csv").write_text(head + "łukasz_w,Łukasz,Zakład,replied,\n",
                                               encoding="utf-8")
    git(repo, "commit", "-qam", "they replied", env={"GIT_AUTHOR_DATE": "2026-10-01T10:00:00"})
    git(repo, "switch", "-q", "master")
    (repo / "network_contacts.csv").write_text(head + "łukasz_w,Łukasz,Zakład,call_booked,\n",
                                               encoding="utf-8")
    git(repo, "commit", "-qam", "a call", env={"GIT_AUTHOR_DATE": "2026-10-02T10:00:00"})
    rc, out, err = run(["git", "merge", "--no-edit", "other"], repo, env)
    assert rc == 0, out + err
    merged = (repo / "network_contacts.csv").read_text(encoding="utf-8")
    assert "<<<<<<<" not in merged and "call_booked" in merged


# ------------------------------------------------------------------ saving work

def test_saving_stages_a_file_whose_name_has_a_letter_cp1252_lacks(tmp_path, win):
    env, py = win
    repo = tmp_path / "My Job Search"
    (repo / "tools").mkdir(parents=True)
    for f in ("save_state.py", "personal_paths.py", "python_floor.py"):
        shutil.copy(os.path.join(TOOLS, f), repo / "tools" / f)
    shutil.copy(os.path.join(ROOT, ".gitignore"), repo / ".gitignore")
    git(repo, "init", "-q", "-b", "master")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "app")
    notes = repo / "documents" / "network" / "Łukasz call notes.md"
    notes.parent.mkdir(parents=True)
    notes.write_text("Talked about the team.\n", encoding="utf-8")
    (repo / "job_search_tracker.csv").write_text("date,company,role,status\n", encoding="utf-8")
    rc, out, err = run([py, "tools/save_state.py", "--list"], repo, env)
    assert rc == 0 and "Łukasz call notes.md" in out, out + err
    rc, out, err = run([py, "tools/save_state.py"], repo, env)
    assert rc == 0, out + err
    staged = git(repo, "diff", "--cached", "--name-only", "-z").split("\0")
    assert "documents/network/Łukasz call notes.md" in staged
    assert "job_search_tracker.csv" in staged


def test_a_push_never_waits_for_a_password_and_takes_gh_sign_in(tmp_path, win):
    env, _py = win
    assert env["GIT_TERMINAL_PROMPT"] == "0" and env["GCM_INTERACTIVE"] == "never"
    repo = tmp_path / "r"
    repo.mkdir()
    git(repo, "init", "-q")
    ask = "protocol=https\nhost=github.com\npath=someone/my-job-search.git\n\n".encode()
    # No credential on file: it fails at once, saying why, instead of waiting on a prompt.
    rc, out, err = run(["git", "-c", "credential.helper=", "credential", "fill"], repo, env,
                       stdin=ask, timeout=30)
    assert rc != 0 and "terminal prompts disabled" in err
    # Signed in with gh (`gh auth setup-git` makes gh git's helper for github.com): the
    # credential comes from gh, and nothing is asked.
    b = tmp_path / "ghbin"
    b.mkdir()
    (b / "gh").write_text('#!/bin/sh\n[ "$1 $2 $3" = "auth git-credential get" ] && '
                          'printf "username=x-access-token\\npassword=gho_example\\n"\n')
    (b / "gh").chmod(0o755)
    env2 = dict(env, PATH=str(b) + os.pathsep + env["PATH"])
    rc, out, err = run(["git", "-c", "credential.helper=",
                        "-c", "credential.https://github.com.helper=!gh auth git-credential",
                        "credential", "fill"], repo, env2, stdin=ask, timeout=30)
    assert rc == 0, err
    assert "password=gho_example" in out


# ------------------------------------------------------------------ the owed list

def test_the_owed_list_names_lukasz_on_windows(tmp_path, win):
    env, py = win
    from network import schema
    state = tmp_path / "state"
    state.mkdir()
    import csv

    def write(name, cols, rows):
        with open(state / name, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow(r)
    write("network_contacts.csv", schema.CONTACT_COLUMNS,
          [{"contact_id": "łukasz_w", "name": "Łukasz", "company": "Zakład"}])
    write("network_threads.csv", schema.THREAD_COLUMNS,
          [{"contact_id": "łukasz_w", "date": "2026-10-20", "direction": "out",
            "channel": "linkedin", "summary": "first note", "full_text": "Cześć"},
           {"contact_id": "łukasz_w", "date": "2026-10-21", "direction": "in",
            "channel": "linkedin", "summary": "happy to talk", "full_text": "Chętnie 👍"}])
    write("job_search_tracker.csv", ["date", "company", "role", "status"], [])
    rc, out, err = run([py, os.path.join(TOOLS, "open_actions.py"), "--due", "--today",
                        "2026-10-25"], ROOT,
                       dict(env, LJS_PROFILE="profile.example", LJS_STATE=str(state)))
    assert rc == 0, out + err
    assert "Łukasz" in out
