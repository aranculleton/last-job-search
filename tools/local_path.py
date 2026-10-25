"""Where a person's own computer keeps the tools the app calls, put on PATH.

A chat on a Mac runs its commands in a shell that is not a login shell, so the
places a login shell adds are missing from its PATH: MacTeX's /Library/TeX/texbin
(lualatex, xelatex) and the official Bun installer's ~/.bun/bin. The tools were
installed and working, and setup_env.sh still said "still missing: lualatex xelatex",
and the place check told the person to install LaTeX they already had. A Mac should
need no profile edits for this, so every tool adds them itself: person.py, which
nearly every tool imports, calls `extend()` once.

The same goes for what `tools/env_check.py --fix` installs into the person's own
folders, with no password: TinyTeX (~/Library/TinyTeX on a Mac, ~/.TinyTeX on Linux,
%APPDATA%\\TinyTeX on Windows, or %ProgramData%\\TinyTeX where APPDATA's path has a space
or a letter outside ASCII), GitHub's command line (~/.local/bin, or
%LOCALAPPDATA%\\Programs\\gh\\bin), Git for Windows (%LOCALAPPDATA%\\Programs\\PortableGit)
and the Python install manager's commands (%LOCALAPPDATA%\\Python\\bin). An install
changes the PATH of shells started afterwards, never the one a chat is already
running, so the chat that installed them finds them here, at once.

Only directories that exist are added. Those that hold nothing but the tools they are
for go first (TeX's, Bun's, gh's and Git's own); general ones go last (the package
managers', ~/.local/bin), so they never shadow a Python the person chose, such as a
virtual environment's.

`use_venv()` lets `python3 tools/<tool>.py` import what `env_check.py --fix` installed in
the repo's own `.venv`: a computer whose system Python refuses installs (Debian and
Ubuntu's "externally managed" Python, PEP 668) still needs pypdf and PyYAML, and every
command in the app is written `python3 tools/...`, not with the venv's own Python.

`run_in_venv()` is for when that cannot work: the `.venv` was made by another version of
Python, so its packages (built for one version) cannot be imported by this one. On a Mac
the `python3` Claude types is Apple's 3.9, and `env_check.py --fix` makes the `.venv` with
a current Python instead (tools/installs.py). The app's own script is then started again
by the venv's Python, with the same arguments, and its exit code is this one's.

`trust_store()` is for Python's own HTTPS (urllib): a Python with its own OpenSSL looks
for certificates where that OpenSSL was built to look, and python.org's for a Mac has
none there until its "Install Certificates" step
(https://docs.python.org/3/using/mac.html). The Mac's own bundle, /etc/ssl/cert.pem, is
where the Python uv installs looks already (python-build-standalone's OpenSSL uses
/etc/ssl/cert.pem and /etc/ssl/certs: https://pyoxidizer.readthedocs.io/en/latest/
pyoxidizer_packaging_ssl_certificates.html, by its author), so SSL_CERT_FILE, which
OpenSSL reads (https://docs.python.org/3/library/ssl.html#ssl.get_default_verify_paths),
points there only when this Python has no certificates of its own.

    python3 tools/local_path.py          # what this adds here
"""
from __future__ import annotations

import glob
import os
import sys

HOME = os.path.expanduser("~")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def rel(path: str, start: str | None = None) -> str:
    """os.path.relpath, with "/" between its folders on every computer, or the full path
    where there is none: on Windows two drives (C: and D:) have no path between them and
    relpath raises. A round written to the temporary folder on C: from a copy on D: crashed
    on its last line that way. The "/" is how the app names a file in its own folder,
    in what it prints, in the state it keeps and to git, on Windows too, which reads it
    the same; "company_research\\acme.json" was printed there (2026-10-25)."""
    try:
        got = os.path.relpath(path, start) if start is not None else os.path.relpath(path)
    except ValueError:
        return os.path.abspath(path)
    return got.replace(os.sep, "/")


def _found(patterns) -> list:
    out = []
    for p in patterns:
        for d in sorted(glob.glob(os.path.expanduser(p)), reverse=True):
            if os.path.isdir(d) and d not in out:
                out.append(d)
    return out


def _win_env(name: str, default: str) -> str:
    return os.environ.get(name) or os.path.expanduser(default)


def dirs(platform: str | None = None) -> tuple[list, list]:
    """(directories to put first, directories to put last) that exist here."""
    platform = platform or sys.platform
    first = ["~/.bun/bin"]
    last = []
    if platform == "darwin":
        first += ["/Library/TeX/texbin", "~/Library/TinyTeX/bin/*"]
        last += ["~/.local/bin", "/opt/homebrew/bin", "/usr/local/bin"]
    elif platform.startswith("win"):
        local = _win_env("LOCALAPPDATA", "~/AppData/Local")
        appdata = _win_env("APPDATA", "~/AppData/Roaming")
        programdata = os.environ.get("ProgramData") or os.environ.get("PROGRAMDATA") \
            or r"C:\ProgramData"
        first += [os.path.join(appdata, "TinyTeX", "bin", "windows"),
                  os.path.join(programdata, "TinyTeX", "bin", "windows"),
                  os.path.join(local, "Programs", "MiKTeX", "miktex", "bin", "x64"),
                  r"C:\Program Files\MiKTeX\miktex\bin\x64",
                  os.path.join(local, "Programs", "gh", "bin"),
                  os.path.join(local, "Programs", "PortableGit", "cmd"),
                  os.path.join(local, "Programs", "PortableGit", "usr", "bin")]
        last += [os.path.join(local, "Python", "bin"),
                 os.path.join(local, "Programs", "last-job-search", "bin")]
    else:
        first += ["~/.TinyTeX/bin/*"]
        last += ["~/.local/bin"]
    first += ["/usr/local/texlive/20*/bin/*"]
    return _found(first), _found(last)


def _settings_bash(home: str) -> str:
    """CLAUDE_CODE_GIT_BASH_PATH from the person's own Claude Code settings, where
    computer_setup.ps1 and installs.fix_git write it; a terminal's Python never has it in
    its environment, only Claude Code's own commands do."""
    import json
    try:
        with open(os.path.join(home, ".claude", "settings.json"), encoding="utf-8") as fh:
            env = json.load(fh).get("env") or {}
        return str(env.get("CLAUDE_CODE_GIT_BASH_PATH") or "")
    except (OSError, ValueError, AttributeError):
        return ""


def bash(platform: str | None = None, env: dict | None = None, which=None,
         home: str | None = None) -> str:
    """The full path of the bash the app's own scripts run under, or "" where there is none.

    On Windows that is Git Bash, found the way Claude Code finds it
    (https://code.claude.com/docs/en/setup, "Install on native Windows"):
    CLAUDE_CODE_GIT_BASH_PATH, then Git for Windows' own folders (C:\\Program Files\\Git
    and the per-user and portable ones), then the bash beside the git on PATH. Never
    C:\\Windows\\System32\\bash.exe, the launcher of the Windows Subsystem for Linux: a bare
    "bash" reaches it first, since Windows looks in its own system folder before PATH
    (https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-createprocessw,
    lpCommandLine; https://docs.python.org/3/library/subprocess.html#popen-constructor says
    to pass a full path for that reason), and it runs no script on a computer with no
    Linux installed ("Windows Subsystem for Linux has no installed distributions")."""
    import shutil
    platform = platform or sys.platform
    env = os.environ if env is None else env
    which = which or shutil.which
    path = env.get("PATH")
    if not platform.startswith("win"):
        return which("bash", path=path) or ""
    home = home or os.path.expanduser("~")

    def get(name: str) -> str:
        return env.get(name) or env.get(name.upper()) or ""
    wanted = [get("CLAUDE_CODE_GIT_BASH_PATH"), _settings_bash(home)]
    local = get("LOCALAPPDATA") or os.path.join(home, "AppData", "Local")
    # C:\Program Files only where Windows names no folder for programs: where it names one,
    # that is where Git for Windows installed.
    for base in (get("ProgramFiles") or r"C:\Program Files", get("ProgramW6432"),
                 get("ProgramFiles(x86)"), os.path.join(local, "Programs")):
        if base:
            wanted.append(os.path.join(base, "Git", "bin", "bash.exe"))
    wanted.append(os.path.join(local, "Programs", "PortableGit", "bin", "bash.exe"))
    git = which("git", path=path)
    if git:
        top = os.path.dirname(os.path.dirname(os.path.abspath(git)))
        if os.path.basename(top).lower() == "mingw64":
            top = os.path.dirname(top)
        wanted.append(os.path.join(top, "bin", "bash.exe"))
    system = os.path.normcase(os.path.join(get("SystemRoot") or get("windir") or r"C:\Windows",
                                           ""))
    found = which("bash", path=path)
    if found and "windowsapps" not in found.lower():
        wanted.append(found)
    for cand in wanted:
        if cand and os.path.isfile(cand) and not os.path.normcase(
                os.path.abspath(cand)).startswith(system):
            return cand
    return ""


def extend(env: dict | None = None, platform: str | None = None) -> list:
    """Add the directories that exist and are missing to env["PATH"] (os.environ by
    default). Returns what was added. Never removes or reorders what was there."""
    env = os.environ if env is None else env
    have = [p for p in env.get("PATH", "").split(os.pathsep) if p]
    first, last = dirs(platform)
    add_first = [d for d in first if d not in have]
    add_last = [d for d in last if d not in have and d not in add_first]
    if add_first or add_last:
        env["PATH"] = os.pathsep.join(add_first + have + add_last)
    if env is os.environ:
        use_venv()
    return add_first + add_last


# Set in the environment of a script run again under the venv's Python, to the Python that
# first started it: a venv whose Python cannot help is then never tried a second time.
REEXEC = "LJS_REEXEC"
TOOLS = os.path.dirname(os.path.abspath(__file__))


def venv_python(root: str | None = None) -> str:
    venv = os.path.join(root or ROOT, ".venv")
    return os.path.join(venv, "Scripts", "python.exe") if os.name == "nt" else \
        os.path.join(venv, "bin", "python")


def _venv_cfg(root: str | None = None) -> dict:
    """The .venv's pyvenv.cfg, read the way Python itself reads it: UTF-8, which is how
    venv writes it, and a byte that is not UTF-8 kept as it is (surrogateescape) rather
    than stopping every command (Lib/venv/__init__.py; Python/pathconfig.c in 3.9,
    Modules/getpath.c from 3.11)."""
    try:
        with open(os.path.join(root or ROOT, ".venv", "pyvenv.cfg"), encoding="utf-8",
                  errors="surrogateescape") as fh:
            return {k.strip(): v.strip() for k, v in
                    (line.split("=", 1) for line in fh if "=" in line)}
    except OSError:
        return {}


def venv_version(root: str | None = None) -> tuple | None:
    """(major, minor) of the Python the repo's .venv was made by, or None."""
    made = _venv_cfg(root).get("version") or _venv_cfg(root).get("version_info", "")
    parts = tuple(int(x) for x in made.split(".")[:2] if x.isdigit())
    return parts if len(parts) == 2 else None


def venv_runs(root: str | None = None) -> bool:
    """The .venv's Python is there and so is the Python it was made from (a venv's
    `home`): uninstalling that Python leaves a venv that cannot start."""
    home = _venv_cfg(root).get("home", "")
    return os.path.exists(venv_python(root)) and bool(home) and os.path.isdir(home)


def rerun_args(argv=None, main_spec=None, env=None, prefix=None, version=None,
               root: str | None = None, orig_argv=None) -> list | None:
    """The command that runs this script again under the venv's Python, or None when
    this Python is the one to run it: not the app's own script (`-c`, `-m`, pytest, a
    REPL), already the venv's Python or its version, no venv that starts, or a second
    try. Every input can be given, so each case is testable from any Python."""
    argv = sys.argv if argv is None else argv
    env = os.environ if env is None else env
    if env.get(REEXEC) or main_spec is not None or not argv:
        return None
    script = argv[0]
    if not script or script in ("-c", "-") or not script.endswith(".py"):
        return None
    tools = os.path.normcase(os.path.realpath(os.path.join(root, "tools") if root else TOOLS))
    path = os.path.normcase(os.path.realpath(script))
    if not path.startswith(tools + os.sep):
        return None
    if not venv_runs(root):
        return None
    made = venv_version(root)
    here = tuple(version or sys.version_info[:2])
    venv = os.path.normcase(os.path.realpath(os.path.join(root or ROOT, ".venv")))
    if os.path.normcase(os.path.realpath(prefix or sys.prefix)) == venv:
        return None
    if not made or made == here or made < (3, 9):
        return None
    # The interpreter's own options (-X utf8, -u) where this Python keeps them (3.10+).
    rest = list(orig_argv[1:]) if orig_argv else list(argv)
    return [venv_python(root), *rest]


def run_in_venv(windows=None, call=None, execve=None) -> None:
    """Start this script again under the venv's Python and exit with its code, when the
    venv was made by another version of Python (rerun_args). On Windows a child process,
    since a replaced process there lets the shell carry on before it ends; elsewhere
    exec, the same process id and terminal. `windows`, `call` and `execve` are for tests."""
    main = sys.modules.get("__main__")
    args = rerun_args(main_spec=getattr(main, "__spec__", None),
                      orig_argv=getattr(sys, "orig_argv", None))
    if not args:
        return
    windows = os.name == "nt" if windows is None else windows
    env = dict(os.environ)
    env[REEXEC] = sys.executable or "python3"
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.flush()
        except (AttributeError, OSError, ValueError):
            pass
    if windows:
        if call is None:
            import subprocess
            call = subprocess.call
        try:
            code = call(args, env=env)
        except OSError:
            return
        raise SystemExit(code)
    try:
        (execve or os.execve)(args[0], args, env)
    except OSError:
        return


# Where a Mac and the common Linux families keep the system's certificate bundle.
CERT_FILES = ("/etc/ssl/cert.pem", "/etc/ssl/certs/ca-certificates.crt",
              "/etc/pki/tls/certs/ca-bundle.crt")


def _hashed(capath: str | None) -> bool:
    """A certificate folder OpenSSL can read: certificates under their hashed names."""
    try:
        return any(len(n) >= 10 and n[8] == "." and n[:8].isalnum() for n in os.listdir(capath))
    except (OSError, TypeError):
        return False


def trust_store(env=None, paths=None, files=CERT_FILES, windows=None) -> str:
    """Point SSL_CERT_FILE at the system's bundle when the OpenSSL this Python carries has no
    certificates where it looks, and nothing else does. Returns the file, or "". Never
    on Windows (Python reads the system store there) and never over a choice already
    made (SSL_CERT_FILE or SSL_CERT_DIR set)."""
    env = os.environ if env is None else env
    windows = os.name == "nt" if windows is None else windows
    if windows or env.get("SSL_CERT_FILE") or env.get("SSL_CERT_DIR"):
        return ""
    if paths is None:
        try:
            import ssl
        except ImportError:
            return ""
        paths = ssl.get_default_verify_paths()
    if getattr(paths, "cafile", None) or _hashed(getattr(paths, "capath", None)):
        return ""
    for f in files:
        if os.path.isfile(f):
            env["SSL_CERT_FILE"] = f
            return f
    return ""


def venv_site(root: str | None = None, version=None) -> str | None:
    """The site-packages of the repo's `.venv`, when it was made by this Python's
    version (a venv's packages are built for one version), else None."""
    venv = os.path.join(root or ROOT, ".venv")
    version = tuple(version or sys.version_info[:2])
    cfg = _venv_cfg(root)
    if not cfg:
        return None
    made = cfg.get("version") or cfg.get("version_info", "")
    if tuple(int(x) for x in made.split(".")[:2] if x.isdigit()) != version:
        return None
    for site in (os.path.join(venv, "Lib", "site-packages"),
                 os.path.join(venv, "lib", f"python{version[0]}.{version[1]}",
                              "site-packages")):
        if os.path.isdir(site):
            return site
    return None


def use_venv(root: str | None = None) -> str | None:
    """Put the repo's `.venv` packages where this Python imports from, right after the
    script's own folder, so what was installed there is what is used. Nothing when this
    Python is already the venv's, or there is no venv made by this Python's version."""
    site = venv_site(root)
    venv = os.path.join(root or ROOT, ".venv")
    if not site or os.path.normcase(os.path.realpath(sys.prefix)) == \
            os.path.normcase(os.path.realpath(venv)):
        return None
    if site not in sys.path:
        sys.path.insert(1 if sys.path else 0, site)
    return site


if __name__ == "__main__":
    added = extend()
    print("local_path: " + (", ".join(added) if added else "nothing to add here"))
    site = venv_site()
    if site:
        print(f"local_path: packages from {site}")
