"""What a computer is missing is installed by Claude, into the person's own folders, with
no password, no Homebrew and no winget (tools/installs.py, `env_check.py --fix`).

The install advice sent a Mac to Homebrew and MacTeX (both ask for the password), Windows
to winget, and Linux to sudo apt, whose output went nowhere (2026-10-25). The real route
was run on a Linux account with no root, in a scratch home: TinyTeX in 21 seconds, gh and
Bun from their releases, and both example documents compiled. These tests pin the
commands it runs and what it leaves behind, with every download and install stood in for.
"""
from __future__ import annotations

import io
import json
import os
import re
import sys
import tarfile
import zipfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import installs as I  # noqa: E402
import local_path  # noqa: E402


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(I, "HOME", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("SHELL", "/bin/zsh")
    monkeypatch.setattr(I, "WINDOWS", False)
    monkeypatch.setattr(I, "MAC", False)
    return tmp_path


def test_nothing_it_runs_asks_for_a_password_or_a_package_manager():
    with open(os.path.join(ROOT, "tools", "installs.py"), encoding="utf-8") as fh:
        src = fh.read()
    # The commands it runs are lists; none starts with, or holds, these.
    for cmd in re.findall(r"_run\(\s*(\[[^\]]*\])", src):
        assert not re.search(r'"(sudo|brew|winget|choco|apt-get|dnf|pacman)"', cmd), cmd
    # sudo appears only in what it tells a Linux person to run for system packages.
    assert all("linux_install" in line or line.strip().startswith(("for tool", '("'))
               for line in src.splitlines() if "sudo " in line)


def test_new_shells_find_what_it_installed_and_running_it_again_adds_nothing(home):
    rc = home / ".zshrc"
    rc.write_text("export EDITOR=vi\n")
    assert I.persist([str(home / ".local" / "bin")], home=str(home)) == [str(rc)]
    assert I.persist([str(home / ".local" / "bin")], home=str(home)) == []
    I.persist([str(home / ".bun" / "bin")], home=str(home))
    text = rc.read_text()
    assert text.startswith("export EDITOR=vi\n") and text.count(I.RC_START) == 1
    assert "# path: $HOME/.local/bin" in text and "# path: $HOME/.bun/bin" in text


def test_claude_codes_own_settings_gain_one_value_and_keep_the_rest(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"model": "x", "env": {"A": "1"}}))
    assert I.claude_setting("CLAUDE_CODE_GIT_BASH_PATH", r"C:\Git\bin\bash.exe", str(path))
    data = json.loads(path.read_text())
    assert data == {"model": "x", "env": {"A": "1",
                                          "CLAUDE_CODE_GIT_BASH_PATH": r"C:\Git\bin\bash.exe"}}
    path.write_text("{ not json")
    assert not I.claude_setting("X", "1", str(path))
    assert path.read_text() == "{ not json"                     # left exactly as it was


def test_the_newest_release_is_read_from_where_its_page_redirects(monkeypatch):
    monkeypatch.setattr(I.shutil, "which", lambda n: "/usr/bin/curl" if n == "curl" else None)
    monkeypatch.setattr(I, "_run", lambda cmd, **k: (
        0, "https://github.com/cli/cli/releases/tag/v2.200.1"))
    assert I.latest("cli/cli", "1.0.0") == "2.200.1"
    monkeypatch.setattr(I, "_run", lambda cmd, **k: (
        0, "https://github.com/git-for-windows/git/releases/tag/v2.57.1.windows.2"))
    assert I.latest("git-for-windows/git", "2.0.0", strip=r"^v|\.windows\.\d+$") == "2.57.1"
    monkeypatch.setattr(I, "_run", lambda cmd, **k: (0, ""))
    monkeypatch.setattr(I.urllib.request, "build_opener", lambda *a: (_ for _ in ()).throw(OSError))
    assert I.latest("cli/cli", "2.103.2") == "2.103.2"


def _zip(member, data=b"#!/bin/sh\necho 1.0\n"):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(member, data)
    return buf.getvalue()


def _tgz(member, data=b"#!/bin/sh\necho 2.0\n"):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        info = tarfile.TarInfo(member)
        info.size = len(data)
        t.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def test_bun_comes_from_its_release_unpacked_by_python_with_no_unzip(home, monkeypatch):
    got = {}

    def download(url, dest):
        got["url"] = url
        open(dest, "wb").write(_zip("bun-linux-x64-baseline/bun"))
    monkeypatch.setattr(I, "download", download)
    monkeypatch.setattr(I, "runtime_here", lambda: "")
    monkeypatch.setattr(I, "arch", lambda: "amd64")
    monkeypatch.setattr(I, "_works", lambda cmd: True)
    assert I.fix_runtime() == "installed (Bun, for the job searches)"
    # The baseline build runs on every x64 processor, old ones included.
    assert got["url"].endswith("/releases/latest/download/bun-linux-x64-baseline.zip")
    bun = home / ".bun" / "bin" / "bun"
    assert bun.exists() and os.access(bun, os.X_OK)
    assert "# path: $HOME/.bun/bin" in (home / ".zshrc").read_text()


@pytest.mark.parametrize("mac, archive, member", [
    (False, "gh_2.103.2_linux_amd64.tar.gz", "gh_2.103.2_linux_amd64/bin/gh"),
    (True, "gh_2.103.2_macOS_arm64.zip", "gh_2.103.2_macOS_arm64/bin/gh"),
])
def test_github_cli_comes_from_its_release_archive(home, monkeypatch, mac, archive, member):
    monkeypatch.setattr(I, "MAC", mac)
    monkeypatch.setattr(I, "arch", lambda: "arm64" if mac else "amd64")
    monkeypatch.setattr(I, "latest", lambda repo, fb, **k: "2.103.2")
    monkeypatch.setattr(I, "_which", lambda n: None)
    monkeypatch.setattr(I, "_works", lambda cmd: True)
    monkeypatch.setattr(I, "gh_signed_in", lambda: False)
    got = {}

    def download(url, dest):
        got["url"] = url
        open(dest, "wb").write(_zip(member) if archive.endswith(".zip") else _tgz(member))
    monkeypatch.setattr(I, "download", download)
    said = I.fix_gh()
    assert got["url"] == f"https://github.com/cli/cli/releases/download/v2.103.2/{archive}"
    assert (home / ".local" / "bin" / "gh").exists()
    assert said.startswith("installed (version 2.103.2); signing in is yours, once")
    assert "gh auth login --web --git-protocol https" in said


def test_python_packages_go_in_the_repos_own_venv_even_where_pip_is_refused(home, tmp_path,
                                                                           monkeypatch):
    venv = tmp_path / "repo" / ".venv"
    monkeypatch.setattr(I, "VENV", str(venv))
    calls = []
    left = {"n": 1}

    def missing():
        left["n"] -= 1
        return ["pypdf", "pyyaml"] if left["n"] >= 0 else []

    def run(cmd, **k):
        calls.append(list(cmd))
        if cmd[1:3] == ["-m", "venv"] and "--without-pip" not in cmd:
            return 1, "The virtual environment was not created successfully because ensurepip is not available"
        if "--without-pip" in cmd:
            os.makedirs(venv, exist_ok=True)
        return 0, ""
    monkeypatch.setattr(I, "missing_modules", missing)
    monkeypatch.setattr(I, "pypdf_panics", lambda: False)
    monkeypatch.setattr(I.local_path, "venv_site", lambda *a: None)
    monkeypatch.setattr(I, "_run", run)
    monkeypatch.setattr(I, "download", lambda url, dest: open(dest, "w").write("# get-pip"))
    assert I.fix_packages() == "installed (pypdf, pyyaml)"
    assert calls[0][1:] == ["-m", "venv", str(venv)]
    assert calls[1][1:] == ["-m", "venv", "--without-pip", str(venv)]
    assert calls[2][0] == I.venv_python(str(venv)) and calls[2][1].endswith("get-pip.py")
    assert calls[3][:4] == [I.venv_python(str(venv)), "-m", "pip", "install"]
    assert not [c for c in calls if "--user" in c or "--break-system-packages" in c]
    assert (venv / I.OURS).exists()


def test_a_latex_already_here_is_kept_when_it_compiles_and_miktex_stops_asking(monkeypatch):
    seen = []
    monkeypatch.setattr(I, "test_compile", lambda: seen.append("compiled"))
    monkeypatch.setattr(I, "install_tinytex", lambda: seen.append("TINYTEX"))
    monkeypatch.setattr(I, "latex_kind", lambda: "texlive")
    assert I.fix_latex() == "already here" and seen == ["compiled"]
    monkeypatch.setattr(I, "latex_kind", lambda: "miktex")
    monkeypatch.setattr(I, "_which", lambda n: "C:/MiKTeX/initexmf.exe" if n == "initexmf" else None)
    ran = []
    monkeypatch.setattr(I, "_run", lambda cmd, **k: ran.append(cmd) or (0, ""))
    assert I.fix_latex().startswith("already here (MiKTeX")
    assert ran == [["C:/MiKTeX/initexmf.exe", "--set-config-value=[MPM]AutoInstall=yes"]]


def test_a_system_latex_that_cannot_compile_the_templates_gets_tinytex_beside_it(monkeypatch):
    seen = []

    def compile_():
        seen.append("compile")
        if seen.count("compile") == 1:
            raise I.Failed("the resume example did not compile")
    monkeypatch.setattr(I, "latex_kind", lambda: "texlive")
    monkeypatch.setattr(I, "test_compile", compile_)
    monkeypatch.setattr(I, "install_tinytex", lambda: seen.append("tinytex"))
    monkeypatch.setattr(I, "tlmgr_install", lambda pkgs: seen.append(tuple(pkgs)))
    assert I.fix_latex().startswith("installed (TinyTeX")
    assert seen == ["compile", "tinytex", I.TEX_PACKAGES, "compile"]


def test_tinytex_is_installed_with_the_empty_first_word_and_no_path_change(home, monkeypatch):
    ran = []
    monkeypatch.setattr(I, "_works", lambda cmd: True)
    monkeypatch.setattr(I.shutil, "which", lambda n: "/usr/bin/" + n)
    monkeypatch.setattr(I, "download", lambda url, dest: open(dest, "w").write("#!/bin/sh"))
    bindir = home / ".TinyTeX" / "bin" / "x86_64-linux"

    def run(cmd, **k):
        ran.append(cmd)
        bindir.mkdir(parents=True, exist_ok=True)
        return 0, ""
    monkeypatch.setattr(I, "_run", run)
    assert I.install_tinytex() == str(bindir)
    # The script reads its first word as a folder for the download: "--no-path" first
    # stopped it with an error (the drafting audit, 2026-10-25).
    assert ran[0][0] == "sh" and ran[0][2:] == ["", "--no-path"]


def test_the_plan_and_the_run_say_one_plain_line_each(monkeypatch, capsys):
    for what in I.WHAT:
        monkeypatch.setitem(I.FIXES, what, (I.FIXES[what][0], lambda: "already here"))
    monkeypatch.setitem(I.FIXES, "gh", ("GitHub's command line", lambda: (
        "already here; signing in is yours, once: I start it")))
    assert I.main([]) == 2 and "usage:" in capsys.readouterr().out    # never from a bare command
    assert I.main(["all"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[-1] == "Done. Yours, once: GitHub sign-in."
    assert all(": " in line for line in out[:-1])
    monkeypatch.setitem(I.FIXES, "latex", ("LaTeX, for the PDFs",
                                           lambda: (_ for _ in ()).throw(I.Failed("no room"))))
    assert I.main(["latex"]) == 1
    assert capsys.readouterr().out.splitlines() == [
        "LaTeX, for the PDFs: no room", "Not done: LaTeX, for the PDFs. The lines above say "
        "what to do."]
    assert I.main(["tea"]) == 2


def test_env_check_fix_is_this_on_a_computer_and_the_setup_script_in_the_cloud(monkeypatch):
    import env_check
    monkeypatch.setattr(env_check, "CLOUD", False)
    monkeypatch.setattr(I, "main", lambda argv: {("latex",): 7, ("all",): 5}.get(tuple(argv), 0))
    assert env_check.main(["--fix", "latex"]) == 7
    assert env_check.main(["--fix"]) == 5
    monkeypatch.setattr(env_check, "CLOUD", True)
    ran = []
    monkeypatch.setattr(env_check.subprocess, "call", lambda cmd: ran.append(cmd) or 0)
    assert env_check.main(["--fix"]) == 0
    assert ran[0][0] == "bash" and ran[0][1].endswith("setup_env.sh")


def test_a_running_chat_finds_every_folder_it_installs_into(tmp_path, monkeypatch):
    local = tmp_path / "Local"
    roaming = tmp_path / "Roaming"
    for d in (roaming / "TinyTeX" / "bin" / "windows", local / "Programs" / "gh" / "bin",
              local / "Programs" / "PortableGit" / "cmd", local / "Python" / "bin"):
        d.mkdir(parents=True)
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    monkeypatch.setenv("APPDATA", str(roaming))
    first, last = local_path.dirs("win32")
    assert str(roaming / "TinyTeX" / "bin" / "windows") in first
    assert str(local / "Programs" / "gh" / "bin") in first
    assert str(local / "Programs" / "PortableGit" / "cmd") in first
    assert str(local / "Python" / "bin") in last


def test_the_venvs_packages_are_read_only_when_this_python_made_it(tmp_path):
    v = tmp_path / ".venv"
    ver = f"{sys.version_info[0]}.{sys.version_info[1]}"
    site = v / "lib" / f"python{ver}" / "site-packages"
    site.mkdir(parents=True)
    (v / "pyvenv.cfg").write_text(f"home = /usr/bin\nversion = {ver}.7\n")
    assert local_path.venv_site(str(tmp_path)) == str(site)
    saved = list(sys.path)
    try:
        assert local_path.use_venv(str(tmp_path)) == str(site) and sys.path[1] == str(site)
    finally:
        sys.path[:] = saved
    (v / "pyvenv.cfg").write_text("home = /usr/bin\nversion = 3.1.0\n")
    assert local_path.venv_site(str(tmp_path)) is None


def test_the_windows_bootstrap_needs_no_administrator_and_runs_on_powershell_5():
    with open(os.path.join(ROOT, "tools", "computer_setup.ps1"), encoding="utf-8") as fh:
        src = fh.read()
    code = "\n".join(line for line in src.splitlines() if not line.lstrip().startswith("#"))
    # Nothing that asks for an administrator, or a package manager the person lacks.
    for word in ("winget", "choco", "scoop", "-Verb RunAs", "Machine')", "HKLM:"):
        assert word not in code, word
    # Windows PowerShell 5.1, the shell a fresh Windows has: no pwsh-only syntax.
    for token in (" && ", " || ", " ?? ", "?."):
        assert token not in code, token
    # Everything into the person's own folders, and Claude Code told where Git Bash is.
    assert "$env:LOCALAPPDATA" in code and "CLAUDE_CODE_GIT_BASH_PATH" in code
    assert "Add-AppxPackage" in code and "'User')" in code
