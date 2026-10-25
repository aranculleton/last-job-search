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

    python3 tools/local_path.py          # what this adds here
"""
from __future__ import annotations

import glob
import os
import sys

HOME = os.path.expanduser("~")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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


def venv_site(root: str | None = None, version=None) -> str | None:
    """The site-packages of the repo's `.venv`, when it was made by this Python's
    version (a venv's packages are built for one version), else None."""
    venv = os.path.join(root or ROOT, ".venv")
    version = tuple(version or sys.version_info[:2])
    try:
        with open(os.path.join(venv, "pyvenv.cfg"), encoding="utf-8") as fh:
            cfg = dict(line.split("=", 1) for line in fh if "=" in line)
    except OSError:
        return None
    cfg = {k.strip(): v.strip() for k, v in cfg.items()}
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
