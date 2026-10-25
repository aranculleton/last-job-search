"""The app's own scripts run under Git Bash on Windows, never under WSL's launcher.

On GitHub's Windows runner, a bare "bash" started from Python reached
C:\\Windows\\System32\\bash.exe ("Windows Subsystem for Linux has no installed
distributions"), since Windows looks in its own system folder before PATH. A person's
computer is the same. local_path.bash() finds Git Bash the way Claude Code does. Each
case is a folder laid out the way Windows lays it out, so it runs on every computer.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import local_path  # noqa: E402


def _file(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("")
    return path


def _computer(tmp_path, name="Zoë Quillfeather"):
    """A Windows user folder, with a space and an accent in it, and the system folder whose
    bash.exe is WSL's launcher."""
    home = tmp_path / "Users" / name
    system = tmp_path / "Windows"
    wsl = _file(str(system / "System32" / "bash.exe"))
    env = {"SystemRoot": str(system), "LOCALAPPDATA": str(home / "AppData" / "Local"),
           "ProgramFiles": str(tmp_path / "Program Files"), "PATH": ""}
    return home, env, wsl


def test_wsls_launcher_is_never_chosen_even_first_on_path(tmp_path):
    home, env, wsl = _computer(tmp_path)

    def which(name, path=None):
        return wsl if name == "bash" else None
    assert local_path.bash("win32", env, which, str(home)) == ""
    git_bash = _file(os.path.join(env["ProgramFiles"], "Git", "bin", "bash.exe"))
    assert local_path.bash("win32", env, which, str(home)) == git_bash


def test_the_setting_claude_code_reads_comes_first(tmp_path):
    home, env, _ = _computer(tmp_path)
    _file(os.path.join(env["ProgramFiles"], "Git", "bin", "bash.exe"))
    portable = _file(os.path.join(env["LOCALAPPDATA"], "Programs", "PortableGit", "bin",
                                  "bash.exe"))
    settings = home / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({"env": {"CLAUDE_CODE_GIT_BASH_PATH": portable}}),
                        encoding="utf-8")
    none = lambda name, path=None: None  # noqa: E731
    assert local_path.bash("win32", env, none, str(home)) == portable
    other = _file(str(tmp_path / "D" / "Git" / "bin" / "bash.exe"))
    assert local_path.bash("win32", dict(env, CLAUDE_CODE_GIT_BASH_PATH=other), none,
                           str(home)) == other


def test_the_bash_beside_the_git_on_path_is_found(tmp_path):
    home, env, wsl = _computer(tmp_path)
    for sub in (("cmd", "git.exe"), ("mingw64", "bin", "git.exe")):
        top = tmp_path / ("Git " + sub[0])
        git = _file(str(top.joinpath(*sub)))
        bash = _file(str(top / "bin" / "bash.exe"))
        found = local_path.bash("win32", env, lambda n, path=None, g=git: g if n == "git"
                                else wsl, str(home))
        assert found == bash


def test_elsewhere_it_is_the_bash_on_path():
    assert local_path.bash("linux", {"PATH": "/x"}, lambda n, path=None: "/x/bash") == "/x/bash"
    assert local_path.bash("darwin", {"PATH": ""}, lambda n, path=None: None) == ""
