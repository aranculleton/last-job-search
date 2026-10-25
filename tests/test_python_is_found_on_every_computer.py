"""tools/py.sh: the app's hooks and scripts find a Python on a Mac, on Linux and on Windows.

`python3` is not a command on every computer that has Python. The python.org installer for
Windows gives `python` and `py`, and the `python3` Windows finds instead is a Microsoft
Store stand-in that prints a message and exits 49. The learned-reaction hook, the merge
driver and the local checks all said python3, so on Windows none of them ran.

Each test builds a folder of stand-in commands and runs py.sh with only that folder on
PATH, so what it picks is what a computer laid out that way would give.
"""
import json
import os
import shutil
import subprocess
import sys

import pytest
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY_SH = os.path.join(ROOT, "tools", "py.sh")

pytestmark = pytest.mark.skipif(not shutil.which("sh"), reason="needs a POSIX sh")

STORE_STUB = ("#!/bin/sh\n"
              "echo 'Python was not found; run without arguments to install from the "
              "Microsoft Store, or disable this shortcut from Settings' >&2\n"
              "exit 49\n")


WIN = sys.platform == "win32"
SH = shutil.which("sh")


def _bin(tmp_path, name="bin"):
    """A PATH folder holding the few commands py.sh itself needs, and nothing else. On
    Windows they stay in Git's own folder, which _path puts after it: Git Bash's commands
    do not start from a link elsewhere, and that folder holds no Python."""
    b = tmp_path / name
    b.mkdir()
    if not WIN:
        for tool in ("sh", "dirname", "tr"):
            os.symlink(shutil.which(tool), b / tool)
    return b


def _path(b, *more):
    return os.pathsep.join([str(b)] + ([os.path.dirname(SH)] if WIN else []) + list(more))


def _env(b, *more, **extra):
    e = {"PATH": _path(b, *more), "HOME": os.environ.get("HOME", "/tmp"), **extra}
    if WIN:                       # what any Windows program needs to start at all
        e["SYSTEMROOT"] = os.environ.get("SYSTEMROOT", r"C:\Windows")
    return e


def _posix(path):
    """A Windows path as sh reads it: a backslash in a script is an escape."""
    return str(path).replace("\\", "/")


def _real_python(at):
    """The Python running the suite, at `at`: a link, or on Windows a script that starts
    it, since a link to a virtual environment's python.exe starts nothing there ("No
    pyvenv.cfg file": https://docs.python.org/3/library/venv.html#how-venvs-work)."""
    if WIN:
        _script(at, f'#!/bin/sh\nexec "{_posix(sys.executable)}" "$@"\n')
    else:
        os.symlink(sys.executable, at)


def _named(path):
    """A path py.sh printed, as this computer names it: Git Bash prints /c/Users/...,
    which cygpath gives back the Windows way."""
    path = str(path).strip()
    if WIN and path.startswith("/"):
        path = subprocess.run([shutil.which("cygpath"), "-w", path], capture_output=True,
                              text=True).stdout.strip()
    return os.path.normcase(os.path.normpath(path))


def _script(path, text):
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)
    return path


def _alone(tmp_path):
    """py.sh in a folder of its own: the checkout's own .venv, made wherever env_check
    --fix has run (a CI runner, a person's computer), comes first by design, so a test of
    the stand-ins must not see it."""
    tools = tmp_path / "alone" / "tools"
    tools.mkdir(parents=True)
    shutil.copy(PY_SH, tools / "py.sh")
    return str(tools / "py.sh")


def _run(args, path, cwd=ROOT, stdin=None, env=None):
    e = _env(path, **(env or {}))
    sh = _alone(Path(str(path)).parent)
    return subprocess.run([SH, sh, *args], cwd=cwd, env=e, input=stdin,
                          capture_output=True, text=True, timeout=60)


def test_which_names_a_python_that_runs_three_nine_or_newer():
    r = subprocess.run([SH, PY_SH, "--which"], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    exe = r.stdout.strip()
    # Run as its callers run it, from sh (ci_local.sh), which reads the path it printed.
    v = subprocess.run([SH, "-c", '"$0" -c "import sys; print(sys.version_info >= (3, 9))"',
                        exe], capture_output=True, text=True)
    assert v.stdout.strip() == "True", v.stderr


def test_a_store_stand_in_called_python3_is_passed_over_for_python(tmp_path):
    b = _bin(tmp_path)
    _script(b / "python3", STORE_STUB)
    _real_python(b / "python")
    r = _run(["--which"], b)
    assert r.returncode == 0, r.stderr
    assert _named(r.stdout) == _named(b / "python")


def test_only_windows_py_launcher_is_resolved_to_the_python_it_starts(tmp_path):
    b = _bin(tmp_path)
    _script(b / "python3", STORE_STUB)
    # `py -3 <args>`: the launcher drops its version flag and runs the real Python.
    _script(b / "py", f'#!/bin/sh\n[ "$1" = "-3" ] && shift\nexec "{_posix(sys.executable)}" "$@"\n')
    r = _run(["--which"], b)
    assert r.returncode == 0, r.stderr
    assert os.path.realpath(r.stdout.strip()) == os.path.realpath(sys.executable)


def test_no_python_at_all_is_one_plain_line_and_exit_1(tmp_path):
    b = _bin(tmp_path)
    _script(b / "python3", STORE_STUB)
    r = _run(["--which"], b)
    assert r.returncode == 1 and r.stdout == ""
    assert r.stderr.strip().splitlines() == [
        "No Python 3.9 or newer was found on this computer (tried python3, python and py -3)."]


def test_a_python_older_than_the_floor_is_passed_over(tmp_path):
    b = _bin(tmp_path)
    _script(b / "python3", "#!/bin/sh\nexit 1\n")       # what -c's version test says on 3.8
    _real_python(b / "python")
    assert _named(_run(["--which"], b).stdout) == _named(b / "python")


def test_the_repos_own_virtual_environment_comes_first_and_a_broken_one_is_skipped(tmp_path):
    repo = tmp_path / "repo"
    (repo / "tools").mkdir(parents=True)
    shutil.copy(PY_SH, repo / "tools" / "py.sh")
    b = _bin(tmp_path)
    _real_python(b / "python3")
    venv = repo / ".venv" / "bin"
    venv.mkdir(parents=True)
    # A virtual environment whose Python was removed since: the file is there, it fails.
    _script(venv / "python", "#!/bin/sh\nexit 127\n")
    r = subprocess.run([SH, str(repo / "tools" / "py.sh"), "--which"], env=_env(b),
                       capture_output=True, text=True, timeout=60)
    assert _named(r.stdout) == _named(b / "python3")
    (venv / "python").unlink()
    _real_python(venv / "python")
    r = subprocess.run([SH, str(repo / "tools" / "py.sh"), "--which"], env=_env(b),
                       capture_output=True, text=True, timeout=60)
    assert _named(r.stdout) == _named(venv / "python")


def test_running_through_it_passes_the_arguments_and_stdin(tmp_path):
    b = _bin(tmp_path)
    _real_python(b / "python")
    r = _run(["-c", "import sys; print(sys.argv[1:], sys.stdin.read())", "a b", "c"], b,
             stdin="from stdin")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "['a b', 'c'] from stdin"


def _shipped_hook(event):
    data = json.loads(open(os.path.join(ROOT, ".claude", "settings.json"),
                           encoding="utf-8").read())
    return data["hooks"][event][0]["hooks"][0]["command"]


@pytest.mark.parametrize("event", ["UserPromptSubmit", "Stop"])
def test_the_shipped_hook_runs_where_python3_is_a_store_stand_in(tmp_path, event):
    # The hook runs the way Claude Code runs a shell-form hook: the command string given
    # to a shell, CLAUDE_PROJECT_DIR set, from a folder whose name has a space.
    project = tmp_path / "My Job Search"
    shutil.copytree(ROOT, project, ignore=shutil.ignore_patterns(
        ".git", "__pycache__", ".pytest_cache", "documents", "cv", "cover_letters", "texmf",
        "node_modules", ".claude", ".venv", "venv"))
    b = _bin(tmp_path)
    _script(b / "python3", STORE_STUB)
    log = tmp_path / "ran.txt"
    _script(b / "python", f'#!/bin/sh\necho "$@" >> "{_posix(log)}"\n'
                          f'exec "{_posix(sys.executable)}" "$@"\n')
    git = os.path.dirname(shutil.which("git"))
    if WIN:
        more = (git,)            # git.exe finds the rest of Git from its own folder
    else:
        os.symlink(shutil.which("git"), b / "git")
        more = ()
    r = subprocess.run([SH, "-c", _shipped_hook(event)], cwd=project,
                       env=_env(b, *more, CLAUDE_PROJECT_DIR=str(project), HOME=str(tmp_path)),
                       input=json.dumps({"hook_event_name": event, "prompt": "fine"}),
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    assert "learned.py hook" in log.read_text(encoding="utf-8")
    # No profile in this copy: the check does nothing, and says nothing.
    assert r.stdout.strip() == "" and "Error" not in r.stderr


def test_the_local_checks_pick_their_python_through_the_launcher():
    import re
    lines = [ln for ln in open(os.path.join(ROOT, "tools", "ci_local.sh"), encoding="utf-8")
             if ln.strip() and not ln.lstrip().startswith("#")]
    assert any('PY="$(sh tools/py.sh --which)"' in ln for ln in lines)
    assert not [ln for ln in lines if re.match(r'\s*PY="?python3', ln)]
    # A virtual environment's Python on Windows is Scripts/python.exe, for the floor leg too.
    assert any("Scripts/python.exe" in ln for ln in lines)
