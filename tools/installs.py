#!/usr/bin/env python3
"""Install what this computer is missing, into the person's own folders, with no password.

    python3 tools/env_check.py --fix                  everything missing here (`all`)
    python3 tools/env_check.py --fix latex gh         only those
                                                      (python, packages, runtime, gh, git, latex)
    python3 tools/env_check.py --fix --plan           what it would do, doing nothing

Claude runs it, in the background: LaTeX takes a minute or two, the rest seconds. It
prints one plain line per thing as each is done, and ends with what, if anything, needs
the person. Nothing here asks for a password, needs Homebrew or winget, or changes
anything outside the person's own folders and this repo:

- on a Mac, a current Python (python_floor.CURRENT), because Apple's `python3` is 3.9,
  which has had no security fixes since October 2025: uv, by its own installer
  (https://docs.astral.sh/uv/getting-started/installation/), into ~/.local/bin, then
  `uv python install`, which puts it in ~/.local/share/uv/python
  (https://docs.astral.sh/uv/reference/storage/). Apple's `python3` is left exactly as it
  was: no `--default` (which would put a `python3` of uv's ahead of it), no Python
  command added anywhere a shell looks, and no shell startup file changed by uv
  (UV_NO_MODIFY_PATH): the app runs that Python through the repo's `.venv`, and an app
  command started by Apple's `python3` runs itself again under it
  (local_path.run_in_venv). A Linux whose Python is older than 3.9 gets the same, with no
  sudo; any other Linux, and Windows, keep the Python they have;
- the Python packages (requirements.txt) go in the repo's own `.venv`, made with that
  Python where there is one, which every tool reads (local_path.use_venv, run_in_venv),
  so a system Python that refuses installs (Debian and Ubuntu's, PEP 668) or has no pip
  is no obstacle;
- LaTeX is TinyTeX (yihui.org/tinytex), a TeX Live in one folder of the person's own,
  with the packages the templates use, then a test compile of both example documents.
  A LaTeX already here is kept: MiKTeX is set to install what it lacks without asking
  (otherwise a compile waits for a click nobody sees), and one that lacks packages and
  cannot be given them without a password gets TinyTeX beside it, found first;
- Bun, which runs the job-board searches where there is no Node, from its own release;
- GitHub's command line, from its release archive;
- on Windows, Git (PortableGit, the portable build of Git for Windows, which needs no administrator) and a
  `python3` command where only `python` works.

Each install puts its folder on PATH for new shells (a marked block in the shell's
startup file; the user PATH on Windows) and tools/local_path.py finds it in this chat.
Two things are the person's, and it says so plainly: Apple's own window for the command
line tools on a Mac with no Git, and signing in to GitHub.
"""
from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
import zipfile

TOOLS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)
import local_path  # noqa: E402
import python_floor  # noqa: E402

# Python's own HTTPS (the download fallback below) finds the system's certificates.
local_path.trust_store()

HOME = os.path.expanduser("~")
WINDOWS = sys.platform.startswith("win")
MAC = sys.platform == "darwin"

# The packages the resume (moderncv, lualatex) and the letter (cover.cls, xelatex) load
# beyond TinyTeX's own set: SETUP.md, "Minimal TeX install", and the drafting audit of
# 2026-10-25, which compiled both documents on a fresh TinyTeX with exactly these.
TEX_PACKAGES = ("moderncv", "fontawesome5", "fontawesome6", "academicons", "import",
                "luatexbase", "pgf", "titlesec", "textpos", "xltxtra", "xunicode", "cite",
                "realscripts", "needspace")
# The file each one is found by, to tell a complete LaTeX from one that lacks some.
TEX_FILES = {"moderncv": "moderncv.cls", "fontawesome5": "fontawesome5.sty",
             "fontawesome6": "fontawesome6.sty", "academicons": "academicons.sty",
             "import": "import.sty", "luatexbase": "luatexbase.sty", "pgf": "pgf.sty",
             "titlesec": "titlesec.sty", "textpos": "textpos.sty", "xltxtra": "xltxtra.sty",
             "xunicode": "xunicode.sty", "cite": "cite.sty", "realscripts": "realscripts.sty",
             "needspace": "needspace.sty", "fontspec": "fontspec.sty"}
# What a quick look (--plan) checks for. fontawesome6 is left out: moderncv 2.6 loads it
# and 2.3 does not, so its absence says nothing until a compile does (fix_latex).
CORE_TEX = [p for p in TEX_FILES if p != "fontawesome6"]
TINYTEX_UNIX = "https://tinytex.yihui.org/install-bin-unix.sh"
TINYTEX_WINDOWS = "https://tinytex.yihui.org/install-bin-windows.ps1"
GET_PIP = "https://bootstrap.pypa.io/get-pip.py"
UV_INSTALLER = "https://astral.sh/uv/install.sh"
# Used only when the newest release cannot be looked up (a GitHub that refuses the
# lookup but serves the download): versions that were published and checked 2026-10-25.
GH_FALLBACK = "2.103.2"
PORTABLE_GIT_FALLBACK = "2.56.0"
MODULES = (("pytest", "pytest"), ("yaml", "pyyaml"), ("pypdf", "pypdf"),
           ("openpyxl", "openpyxl"))
# Windows has no time zone data of its own, and Python's zoneinfo reads it from the tzdata
# package there (https://docs.python.org/3/library/zoneinfo.html#data-sources). It was in
# requirements.txt and never in this list, so a .venv made before it arrived was "already
# here" for ever, and the person's own time could not be read.
if sys.platform == "win32":
    MODULES += (("tzdata", "tzdata"),)
VENV = os.path.join(ROOT, ".venv")
OURS = ".made-by-last-job-search"
RC_START = "# >>> last-job-search: tools it installed for you >>>"
RC_END = "# <<< last-job-search <<<"
WHAT = ("git", "python", "packages", "runtime", "gh", "latex")


# ------------------------------------------------------------------ small pieces

class Failed(RuntimeError):
    """One install that did not work, with the plain line that says what to do."""


def _say(line: str) -> None:
    print(line, flush=True)


def _run(cmd, timeout=600, env=None, cwd=None):
    """(exit code, output) of a command; 127 when it is not there."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout, env=env, cwd=cwd,
                           stdin=subprocess.DEVNULL)
    except FileNotFoundError:
        return 127, f"{cmd[0]} is not installed"
    except subprocess.TimeoutExpired:
        return 124, f"{os.path.basename(str(cmd[0]))} took longer than {timeout // 60} minutes"
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def _which(name: str) -> str | None:
    local_path.extend()
    return shutil.which(name)


def _works(cmd) -> bool:
    return _run(cmd, timeout=60)[0] == 0


def download(url: str, dest: str) -> None:
    """Fetch `url` to `dest`, with curl where it is (it uses the computer's own
    certificates; python.org's Python on a Mac has none until its install-certificates
    step), else Python's own. Raises Failed with a plain line."""
    curl = shutil.which("curl")
    if curl:
        code, out = _run([curl, "-fsSL", "--retry", "3", "--retry-delay", "2", "-o", dest, url],
                         timeout=900)
        if code == 0 and os.path.getsize(dest) > 0:
            return
        err = out.strip().splitlines()[-1] if out.strip() else f"curl exit {code}"
    else:
        err = ""
    try:
        with urllib.request.urlopen(url, timeout=120) as r, open(dest, "wb") as fh:
            shutil.copyfileobj(r, fh)
        return
    except Exception as exc:  # noqa: BLE001  any reason is the same answer
        err = err or str(exc)
    raise Failed(f"could not download {url} ({err[:120]}). Check this computer is online, "
                 f"then run this again")


def latest(repo: str, fallback: str, strip: str = r"^v") -> str:
    """The newest release's version, from where github.com/<repo>/releases/latest
    redirects (no API, no rate limit); `fallback` when that cannot be read."""
    curl = shutil.which("curl")
    url = f"https://github.com/{repo}/releases/latest"
    loc = ""
    if curl:
        code, out = _run([curl, "-sS", "-o", os.devnull, "-m", "20", "-w", "%{redirect_url}",
                          url], timeout=60)
        loc = out.strip() if code == 0 else ""
    if not loc:
        try:
            class _NoRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, *a, **k):
                    return None
            opener = urllib.request.build_opener(_NoRedirect)
            try:
                opener.open(url, timeout=20)
            except urllib.error.HTTPError as e:   # the 302 arrives as an error here
                loc = e.headers.get("Location", "")
        except Exception:  # noqa: BLE001
            loc = ""
    m = re.search(r"/tag/([^/?#]+)$", loc)
    return re.sub(strip, "", m.group(1)) if m else fallback


def arch() -> str:
    """amd64, arm64 or 386, as the release archives name them."""
    m = (platform.machine() or "").lower()
    if MAC and m == "x86_64":
        code, out = _run(["sysctl", "-n", "sysctl.proc_translated"], timeout=10)
        if code == 0 and out.strip() == "1":       # Python under Rosetta on an Apple chip
            return "arm64"
    if m in ("arm64", "aarch64", "armv8l"):
        return "arm64"
    if m in ("x86_64", "amd64", "x64"):
        return "amd64"
    if m in ("i386", "i686", "x86"):
        return "386"
    return m or "amd64"


def user_bin() -> str:
    """Where a single command goes on a Mac or Linux: ~/.local/bin, the usual place."""
    return os.path.join(HOME, ".local", "bin")


def _programs() -> str:
    return os.path.join(os.environ.get("LOCALAPPDATA") or os.path.join(HOME, "AppData", "Local"),
                        "Programs")


# ------------------------------------------------------------------ PATH, for new shells

def rc_files(shell: str | None = None) -> list[str]:
    """The startup file of the person's shell, where a new shell reads PATH from."""
    shell = os.path.basename(shell or os.environ.get("SHELL") or "")
    if shell == "zsh" or (MAC and not shell):
        return [os.path.join(HOME, ".zshrc")]
    if shell == "bash":
        return [os.path.join(HOME, ".bashrc")] + (
            [os.path.join(HOME, ".bash_profile")] if MAC else [])
    return [os.path.join(HOME, ".profile")]


def persist(dirs: list[str], home: str | None = None) -> list[str]:
    """Put `dirs` on PATH for every new shell. Returns the files or settings changed.

    A Mac or Linux: one marked block in the shell's startup file, rewritten in place, so
    running this again never adds a second copy. Windows: the user's own PATH, which
    needs no administrator."""
    dirs = [d for d in dict.fromkeys(dirs) if d]
    if not dirs:
        return []
    if WINDOWS:
        return _persist_windows(dirs)
    home = home or HOME
    # A shell's startup file takes "/" whatever the computer: a backslash there is an
    # escape, and $HOME\.bun\bin would read as $HOME.bunbin.
    shown = []
    for d in dirs:
        shown.append(("$HOME" + d[len(home):] if d.startswith(home + os.sep) else d)
                     .replace("\\", "/"))
    changed = []
    for rc in rc_files():
        rc = rc.replace(HOME, home, 1)
        try:
            with open(rc, encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            text = ""
        have = re.search(re.escape(RC_START) + r"\n(.*?)" + re.escape(RC_END), text, re.S)
        before = re.findall(r"^# path: (.+)$", have.group(1), re.M) if have else []
        want = list(dict.fromkeys(before + shown))
        if have and want == before:
            continue
        block = (RC_START + "\n"
                 + "".join(f'# path: {d}\ncase ":$PATH:" in *":{d}:"*) ;; '
                           f'*) PATH="{d}:$PATH" ;; esac\n' for d in want)
                 + "export PATH\n" + RC_END)
        text = (text[:have.start()] + block + text[have.end():]) if have else \
            (text + ("" if not text or text.endswith("\n") else "\n") + block + "\n")
        os.makedirs(os.path.dirname(rc), exist_ok=True)
        with open(rc, "w", encoding="utf-8") as fh:
            fh.write(text)
        changed.append(rc)
    return changed


def _persist_windows(dirs: list[str], front: bool = False) -> list[str]:
    import winreg  # noqa: PLC0415  Windows only
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0,
                        winreg.KEY_READ | winreg.KEY_WRITE) as key:
        try:
            value, kind = winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            value, kind = "", winreg.REG_EXPAND_SZ
        parts = [p for p in value.split(";") if p]
        low = [p.lower().rstrip("\\") for p in parts]
        new = [d for d in dirs if d.lower().rstrip("\\") not in low]
        if not new:
            return []
        parts = (new + parts) if front else (parts + new)
        winreg.SetValueEx(key, "Path", 0, kind or winreg.REG_EXPAND_SZ, ";".join(parts))
    try:  # tell running programs the environment changed; new ones read it anyway
        import ctypes
        result = ctypes.c_ulong()
        ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x1A, 0, "Environment", 2, 5000,
                                                 ctypes.byref(result))
    except Exception:  # noqa: BLE001
        pass
    return ["your Windows PATH"]


def claude_setting(name: str, value: str, settings: str | None = None) -> bool:
    """Set env[name] in the person's own Claude Code settings (~/.claude/settings.json),
    leaving everything else in it as it was. False, and nothing written, when the file
    is there but is not JSON this can read."""
    path = settings or os.path.join(HOME, ".claude", "settings.json")
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        data = {}
    except (OSError, ValueError):
        return False
    if not isinstance(data, dict) or not isinstance(data.get("env", {}), dict):
        return False
    if data.get("env", {}).get(name) == value:
        return True
    data.setdefault("env", {})[name] = value
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")
    return True


# ------------------------------------------------------------------ what is here

def venv_python(venv: str = VENV) -> str:
    return os.path.join(venv, "Scripts", "python.exe") if WINDOWS else \
        os.path.join(venv, "bin", "python")


def missing_modules(python: str | None = None) -> list[str]:
    """The Python packages `python` (this one by default) cannot import, the repo's .venv
    included where it was made by the same version."""
    probe = ("import sys; sys.path.insert(0, sys.argv[1]); import local_path; "
             "local_path.use_venv(); import importlib.util as u; "
             "print(' '.join(m for m in sys.argv[2:] if u.find_spec(m) is None))")
    code, out = _run([python or sys.executable, "-c", probe, TOOLS, *[m for m, _ in MODULES]],
                     timeout=60)
    gone = out.split() if code == 0 else [m for m, _ in MODULES]
    return [pkg for mod, pkg in MODULES if mod in gone]


def pypdf_panics(python: str | None = None) -> bool:
    """pypdf installed but crashing on import: a broken `cryptography` (a pyo3 panic)."""
    probe = ("import sys; sys.path.insert(0, sys.argv[1]); import local_path; "
             "local_path.use_venv(); import pypdf; pypdf.PdfReader")
    code, out = _run([python or sys.executable, "-c", probe, TOOLS], timeout=60)
    return code != 0 and "No module named" not in out


def version_of(python: str) -> tuple | None:
    """(major, minor) of a Python, by running it with nothing of the repo's."""
    if python == sys.executable:
        return tuple(sys.version_info[:2])
    code, out = _run([python, "-I", "-S", "-c",
                      "import sys; print('%d.%d' % sys.version_info[:2])"], timeout=60)
    m = re.match(r"(\d+)\.(\d+)$", out.strip()) if code == 0 else None
    return (int(m.group(1)), int(m.group(2))) if m else None


def _uv() -> str | None:
    """uv where its installer puts it ($XDG_BIN_HOME, else ~/.local/bin), else on PATH."""
    for d in (os.environ.get("XDG_BIN_HOME"), user_bin()):
        exe = os.path.join(d, "uv.exe" if WINDOWS else "uv") if d else ""
        if exe and os.path.isfile(exe):
            return exe
    return _which("uv")


def _uv_env() -> dict:
    env = dict(os.environ)
    env.pop("VIRTUAL_ENV", None)
    # No python3.13 command added to ~/.local/bin: nothing a shell runs changes.
    env["UV_PYTHON_INSTALL_BIN"] = "0"
    return env


def managed_python(uv: str | None = None, want=None) -> str | None:
    """The Python uv installed for `want` (python_floor.CURRENT), never a venv's or the
    system's (`--system`, `--python-preference only-managed`)."""
    uv = uv or _uv()
    if not uv:
        return None
    want = want or python_floor.CURRENT
    code, out = _run([uv, "python", "find", "--system", "--python-preference", "only-managed",
                      f"{want[0]}.{want[1]}"], timeout=60, env=_uv_env(), cwd=HOME)
    # The path is on stdout; uv's warnings, which _run adds after it, are not paths.
    found = [ln.strip() for ln in out.splitlines() if ln.strip() and os.path.isfile(ln.strip())]
    return found[0] if code == 0 and found else None


def needs_python(mac: bool = MAC, here=None, venv=None, venv_runs=None) -> bool:
    """Whether this computer needs the current Python installed: a Mac whose `.venv` and
    running Python are both older than python_floor.CURRENT, or any other computer but
    Windows whose Python is older than the floor. Each input can be given for a test."""
    if WINDOWS:
        return False
    want = python_floor.CURRENT if mac else python_floor.FLOOR
    here = tuple(here or sys.version_info[:2])
    venv = local_path.venv_version() if venv is None else venv
    runs = local_path.venv_runs() if venv_runs is None else venv_runs
    if runs and venv and tuple(venv) >= want:
        return False
    return here < want


def _made_by(root: str = ROOT) -> str | None:
    """The Python the repo's `.venv` was made from, while it is still there."""
    cfg = local_path._venv_cfg(root)
    if cfg.get("executable") and os.path.isfile(cfg["executable"]):
        return cfg["executable"]
    home = cfg.get("home", "")
    for name in ("python.exe",) if WINDOWS else ("python3", "python"):
        if home and os.path.isfile(os.path.join(home, name)):
            return os.path.join(home, name)
    return None


def venv_base() -> str:
    """The Python the repo's `.venv` is made with: the current one uv installed, where the
    install route put one (a Mac, or a Python older than the floor); else the Python a
    working `.venv` was made from, kept whichever Python runs this (a `.venv` the
    install route made is never made again by an older `python3`); else this one."""
    if not WINDOWS and (MAC or not python_floor.ok()):
        py = managed_python()
        if py:
            return py
    made = local_path.venv_version(root_of(VENV))
    if local_path.venv_runs(root_of(VENV)) and made and made >= python_floor.FLOOR:
        py = _made_by(root_of(VENV))
        if py:
            return py
    return sys.executable


def latex_kind() -> str:
    """"miktex", "tinytex", "texlive" or "" (none, or not both engines)."""
    if not (_which("lualatex") and _which("xelatex")):
        return ""
    code, out = _run([_which("lualatex"), "--version"], timeout=60)
    if "MiKTeX" in out:
        return "miktex"
    tl = _which("tlmgr") or ""
    return "tinytex" if "tinytex" in tl.lower() else "texlive"


def tex_missing() -> list[str]:
    """The template packages this LaTeX cannot find (the repo's texmf/ included)."""
    kpse = _which("kpsewhich")
    if not kpse:
        return list(TEX_FILES)
    env = dict(os.environ, TEXMFHOME=os.path.join(ROOT, "texmf"))
    code, out = _run([kpse, *TEX_FILES.values()], timeout=120, env=env)
    found = {os.path.basename(line.strip()) for line in out.splitlines() if line.strip()}
    return [pkg for pkg in CORE_TEX if TEX_FILES[pkg] not in found]


def runtime_here() -> str:
    return "node" if _which("node") else ("bun" if _which("bun") else "")


# ------------------------------------------------------------------ the installs

def fix_packages(base: str | None = None) -> str:
    """The packages, in the repo's `.venv`, made with `base` (venv_base). A `.venv` made by
    another version of Python, which `base` cannot use, is made again when this made it,
    and left alone, with the reason, when something else did."""
    venv = VENV
    root = root_of(venv)
    base = base or venv_base()
    same = os.path.isdir(venv) and local_path.venv_runs(root) and \
        local_path.venv_version(root) == version_of(base)
    probe = venv_python(venv) if same else base
    need = missing_modules(probe)
    broken = "pypdf" not in need and pypdf_panics(probe)
    if not need and not broken:
        return "already here"
    if os.path.isdir(venv) and not same:
        if not os.path.exists(os.path.join(venv, OURS)):
            raise Failed(f"there is a folder {venv} made by another Python, which this one "
                         f"cannot use; I left it alone. Remove it, then run this again")
        shutil.rmtree(venv)
    if not os.path.isdir(venv):
        code, out = _run([base, "-m", "venv", venv], timeout=300)
        if code != 0:
            # Debian and Ubuntu leave out the part of venv that installs pip
            # (python3-venv, which needs a password): make it bare and fetch pip.
            shutil.rmtree(venv, ignore_errors=True)
            code, out = _run([base, "-m", "venv", "--without-pip", venv], timeout=300)
            if code != 0:
                raise Failed(f"could not make a place for the Python packages "
                             f"({out.strip().splitlines()[-1] if out.strip() else code})")
            getpip = os.path.join(tempfile.mkdtemp(prefix="ljs_"), "get-pip.py")
            download(GET_PIP, getpip)
            code, out = _run([venv_python(venv), getpip, "--quiet"], timeout=600)
            if code != 0:
                raise Failed("could not install pip for the packages: "
                             + (out.strip().splitlines() or ["no output"])[-1][:160])
        open(os.path.join(venv, OURS), "w", encoding="utf-8").close()
    extra = ["--upgrade", "cffi", "cryptography"] if broken else []
    code, out = _run([venv_python(venv), "-m", "pip", "install", "--disable-pip-version-check",
                      "-q", "-r", os.path.join(ROOT, "requirements.txt"), *extra], timeout=900)
    if code != 0:
        raise Failed("could not install the Python packages: "
                     + (out.strip().splitlines() or ["no output"])[-1][:200])
    still = missing_modules(venv_python(venv))
    if still:
        raise Failed("installed, but " + ", ".join(still) + " still cannot be imported")
    return "installed (" + ", ".join(need or ["cffi", "cryptography"]) + ")"


def root_of(venv: str) -> str:
    return os.path.dirname(os.path.abspath(venv))


def fix_runtime() -> str:
    have = runtime_here()
    if have:
        return f"already here ({'Node' if have == 'node' else 'Bun'})"
    a = arch()
    if WINDOWS:
        target = "windows-aarch64" if a == "arm64" else "windows-x64-baseline"
    elif MAC:
        target = "darwin-aarch64" if a == "arm64" else "darwin-x64-baseline"
    else:
        musl = os.path.exists("/etc/alpine-release")
        target = ("linux-aarch64" if a == "arm64" else "linux-x64-baseline")
        if musl:
            target = target.replace("linux-x64-baseline", "linux-x64-musl-baseline") \
                .replace("linux-aarch64", "linux-aarch64-musl")
    url = f"https://github.com/oven-sh/bun/releases/latest/download/bun-{target}.zip"
    work = tempfile.mkdtemp(prefix="ljs_bun_")
    zpath = os.path.join(work, "bun.zip")
    download(url, zpath)
    exe = "bun.exe" if WINDOWS else "bun"
    bindir = os.path.join(HOME, ".bun", "bin")
    os.makedirs(bindir, exist_ok=True)
    with zipfile.ZipFile(zpath) as z:
        member = next((n for n in z.namelist() if n.endswith("/" + exe) or n == exe), None)
        if not member:
            raise Failed(f"the Bun download had no {exe} in it")
        with z.open(member) as src, open(os.path.join(bindir, exe), "wb") as dst:
            shutil.copyfileobj(src, dst)
    os.chmod(os.path.join(bindir, exe), 0o755)
    if not _works([os.path.join(bindir, exe), "--version"]):
        raise Failed("Bun was downloaded but does not run on this computer")
    persist([bindir])
    return "installed (Bun, for the job searches)"


def gh_signed_in() -> bool:
    gh = _which("gh")
    return bool(gh) and _run([gh, "auth", "status"], timeout=30)[0] == 0


def fix_gh() -> str:
    gh = _which("gh")
    if not (gh and _works([gh, "--version"])):
        v = latest("cli/cli", GH_FALLBACK)
        a = arch()
        if WINDOWS:
            name, kind = f"gh_{v}_windows_{a}.zip", "zip"
        elif MAC:
            name, kind = f"gh_{v}_macOS_{'arm64' if a == 'arm64' else 'amd64'}.zip", "zip"
        else:
            name, kind = f"gh_{v}_linux_{a}.tar.gz", "tar"
        work = tempfile.mkdtemp(prefix="ljs_gh_")
        archive = os.path.join(work, name)
        download(f"https://github.com/cli/cli/releases/download/v{v}/{name}", archive)
        exe = "gh.exe" if WINDOWS else "gh"
        dest = os.path.join(_programs(), "gh", "bin") if WINDOWS else user_bin()
        os.makedirs(dest, exist_ok=True)
        if kind == "zip":
            with zipfile.ZipFile(archive) as z:
                member = next((n for n in z.namelist() if n.endswith("bin/" + exe)), None)
                if not member:
                    raise Failed(f"the GitHub download had no {exe} in it")
                with z.open(member) as src, open(os.path.join(dest, exe), "wb") as dst:
                    shutil.copyfileobj(src, dst)
        else:
            with tarfile.open(archive) as t:
                member = next((m for m in t.getmembers() if m.name.endswith("bin/" + exe)), None)
                if not member:
                    raise Failed(f"the GitHub download had no {exe} in it")
                with t.extractfile(member) as src, open(os.path.join(dest, exe), "wb") as dst:
                    shutil.copyfileobj(src, dst)
        os.chmod(os.path.join(dest, exe), 0o755)
        gh = os.path.join(dest, exe)
        if not _works([gh, "--version"]):
            raise Failed("GitHub's command line was downloaded but does not run here")
        persist([dest])
        said = f"installed (version {v})"
    else:
        said = "already here"
    if not gh_signed_in():
        said += ("; signing in is yours, once: I start `gh auth login --web --git-protocol "
                 "https` and you copy the code it shows into the GitHub page that opens")
    return said


def fix_git() -> str:
    if _which("git") and _works([_which("git"), "--version"]):
        return "already here"
    if MAC:
        _run(["xcode-select", "--install"], timeout=30)
        raise Failed("yours, once: a window from Apple asks to install the command line "
                     "developer tools. Click Install (a few minutes, no Homebrew); Git and "
                     "Python come with them. Then say \"done\"")
    if not WINDOWS:
        raise Failed("yours, once (it asks for your password): Git comes from your system on "
                     "Linux: " + linux_install("git"))
    v = latest("git-for-windows/git", PORTABLE_GIT_FALLBACK, strip=r"^v|\.windows\.\d+$")
    name = f"PortableGit-{v}-{'arm64' if arch() == 'arm64' else '64-bit'}.7z.exe"
    work = tempfile.mkdtemp(prefix="ljs_git_")
    exe = os.path.join(work, name)
    download(f"https://github.com/git-for-windows/git/releases/download/v{v}.windows.1/{name}",
             exe)
    dest = os.path.join(_programs(), "PortableGit")
    bash = os.path.join(dest, "bin", "bash.exe")
    for args in ([exe, f"-o{dest}", "-y"], [exe, "-y", "-gm2", f"-InstallPath={dest}"]):
        _run(args, timeout=900)
        for _ in range(60):          # its first-run step finishes after the extractor exits
            if os.path.exists(bash) and os.path.exists(os.path.join(dest, "cmd", "git.exe")):
                break
            time.sleep(1)
        if os.path.exists(bash):
            break
    git = os.path.join(dest, "cmd", "git.exe")
    if not (os.path.exists(bash) and _works([git, "--version"])):
        raise Failed("Git for Windows was downloaded but would not unpack")
    persist([os.path.join(dest, "cmd")])
    # Claude Code finds Git Bash where Git for Windows' installer puts it; a portable one
    # it is told about (code.claude.com/docs/en/setup, "If Claude Code can't find Git Bash").
    told = claude_setting("CLAUDE_CODE_GIT_BASH_PATH", bash)
    return ("installed (Git for Windows, in your own folder). Restart the Claude app once so "
            "new chats use it" + ("" if told else f"; tell Claude Code where its shell is: "
                                  f"CLAUDE_CODE_GIT_BASH_PATH={bash}"))


def install_uv() -> str:
    """uv, by its official installer (curl -LsSf https://astral.sh/uv/install.sh | sh), into
    ~/.local/bin, telling it to leave the shell's startup files alone (UV_NO_MODIFY_PATH,
    https://docs.astral.sh/uv/reference/installer/): the app runs uv by its path, so nothing
    a person types needs it, and the one place this route changes PATH stays the one
    marked block persist() writes."""
    have = _uv()
    if have and _works([have, "--version"]):
        return have
    work = tempfile.mkdtemp(prefix="ljs_uv_")
    script = os.path.join(work, "uv-installer.sh")
    download(UV_INSTALLER, script)
    env = dict(os.environ, UV_NO_MODIFY_PATH="1")
    code, out = _run(["sh", script], timeout=600, env=env)
    exe = _uv()
    if code != 0 or not exe or not _works([exe, "--version"]):
        raise Failed("could not install uv, which installs Python: "
                     + (out.strip().splitlines() or [f"exit {code}"])[-1][:160])
    return exe


def install_python(want=None) -> str:
    """The current Python, by uv, in the person's own folder; returns its path."""
    want = want or python_floor.CURRENT
    uv = install_uv()
    code, out = _run([uv, "python", "install", f"{want[0]}.{want[1]}"], timeout=1200,
                     env=_uv_env(), cwd=HOME)
    py = managed_python(uv, want)
    if code != 0 or not py:
        raise Failed(f"could not install Python {want[0]}.{want[1]}: "
                     + (out.strip().splitlines() or [f"exit {code}"])[-1][:160])
    return py


# The folders a path in a batch file is written under by name, longest first where one
# holds another, so that cmd.exe expands them itself.
_BATCH_VARS = ("LOCALAPPDATA", "APPDATA", "USERPROFILE", "ProgramFiles(x86)", "ProgramFiles")


def _batch_path(path: str, env=None, short=None) -> str:
    """A path as a .cmd file can hold it. cmd.exe reads a batch file in the console's code
    page (the OEM one, 437 or 850, until `chcp` changes it:
    https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/chcp),
    so a python.exe under C:\\Users\\María, written in UTF-8, came out as other letters and
    `python3` failed in cmd and PowerShell. The part under the person's own folders is
    written as the variable cmd expands for itself (%LOCALAPPDATA%), in full; a path still
    holding a letter outside ASCII is given in its short form (GetShortPathNameW), which
    is ASCII. Only Windows calls this; it reads the path the Windows way on any computer."""
    import ntpath
    env = os.environ if env is None else env
    bases = sorted(((var, env.get(var) or "") for var in _BATCH_VARS), key=lambda b: -len(b[1]))
    for var, base in bases:
        base = base.rstrip("\\/")
        if base and ntpath.normcase(path).startswith(ntpath.normcase(base) + "\\"):
            path = f"%{var}%" + path[len(base):]
            break
    if path.isascii():
        return path
    shorter = (short or _short_path)(path)
    return shorter if shorter and shorter.isascii() else path


def _short_path(path: str) -> str:
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(32768)
        n = ctypes.windll.kernel32.GetShortPathNameW(path, buf, len(buf))
        return buf.value if 0 < n < len(buf) else ""
    except (AttributeError, OSError):
        return ""


def _batch_bytes(text: str) -> bytes:
    """A batch file's text in the code page cmd.exe reads it in: ASCII when it is (as
    _batch_path makes it), else the OEM code page, which Python names "oem" on Windows."""
    if text.isascii():
        return text.encode("ascii")
    try:
        return text.encode("oem", errors="replace")
    except LookupError:          # not Windows: no "oem" codec here
        return text.encode("utf-8")


def fix_python() -> str:
    """On a Mac, and on a Linux whose Python is older than the floor, the current Python
    (install_python) and the repo's `.venv` made again with it. On Windows a `python3`
    command, where the python.org installer gives only `python` and `py`, and `python3`
    is a shortcut that opens the Microsoft Store."""
    if not WINDOWS:
        if not needs_python():
            return "already here"
        py = install_python()
        v = version_of(py)
        packages = fix_packages(py)
        return (f"installed (Python {v[0]}.{v[1]}, in your own folder; Apple's python3 is "
                f"as it was; the Python packages: {packages})" if MAC else
                f"installed (Python {v[0]}.{v[1]}, in your own folder; the Python packages: "
                f"{packages})")
    real = os.path.normcase(os.path.realpath(sys.executable))
    found = shutil.which("python3")
    if found:
        code, out = _run([found, "-c", "import sys; print(sys.executable)"], timeout=30)
        if code == 0 and out.strip():
            return "already here"
    shim = os.path.join(_programs(), "last-job-search", "bin")
    os.makedirs(shim, exist_ok=True)
    with open(os.path.join(shim, "python3.cmd"), "wb") as fh:
        fh.write(_batch_bytes(f'@"{_batch_path(sys.executable)}" %*\r\n'))
    posix = "/" + real[0].lower() + real[2:].replace("\\", "/") if real[1:2] == ":" else real
    with open(os.path.join(shim, "python3"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(f'#!/bin/sh\nexec "{posix}" "$@"\n')
    _persist_windows([shim], front=True)
    return "set up (python3 now runs the Python you have)"


def linux_install(*packages: str) -> str:
    """The one command that installs system packages on this Linux, which asks for the
    password: apt, dnf, pacman or zypper, whichever it has."""
    for tool, cmd in (("apt-get", "sudo apt-get install -y"), ("dnf", "sudo dnf install -y"),
                      ("pacman", "sudo pacman -S --noconfirm"),
                      ("zypper", "sudo zypper install -y")):
        if shutil.which(tool):
            return f"{cmd} {' '.join(packages)}"
    return "install " + " and ".join(packages) + " with your system's package manager"


def _tinytex_bin() -> str | None:
    """TinyTeX's folder of commands, where its installer puts it on this computer."""
    if WINDOWS:
        for base in (os.environ.get("APPDATA"), os.environ.get("ProgramData")):
            d = os.path.join(base or "", "TinyTeX", "bin", "windows")
            if base and os.path.isdir(d):
                return d
        return None
    import glob
    root = os.path.join(HOME, "Library", "TinyTeX") if MAC else os.path.join(HOME, ".TinyTeX")
    hits = sorted(d for d in glob.glob(os.path.join(root, "bin", "*")) if os.path.isdir(d))
    return hits[0] if hits else None


def install_tinytex() -> str:
    work = tempfile.mkdtemp(prefix="ljs_tex_")
    if WINDOWS:
        ps1 = os.path.join(work, "install-bin-windows.ps1")
        download(TINYTEX_WINDOWS, ps1)
        code, out = _run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ps1],
                         timeout=1800, cwd=work)
    else:
        if not _works(["perl", "-mFile::Find", "-e", "1"]):
            raise Failed("yours, once (it asks for your password): LaTeX needs Perl, which "
                         "comes from your system: " + linux_install("perl"))
        if not MAC and not shutil.which("xz"):
            raise Failed("yours, once (it asks for your password): LaTeX's download needs xz, "
                         "which comes from your system: "
                         + linux_install("xz-utils" if shutil.which("apt-get") else "xz"))
        sh = os.path.join(work, "install-bin-unix.sh")
        download(TINYTEX_UNIX, sh)
        # The script reads its first word as a folder to keep the download in, so the
        # documented `sh -s --no-path` stops with an error: an empty first word, then the
        # option, installs with no password and changes nothing outside its own folder.
        code, out = _run(["sh", sh, "", "--no-path"], timeout=1800,
                         env=dict(os.environ, TMPDIR=work), cwd=work)
    b = _tinytex_bin()
    if code != 0 or not b:
        raise Failed("TinyTeX did not install: "
                     + (out.strip().splitlines() or ["no output"])[-1][:200])
    os.environ["PATH"] = b + os.pathsep + os.environ.get("PATH", "")
    if not WINDOWS:
        persist([b])
    return b


def tlmgr_install(packages) -> None:
    tl = _which("tlmgr")
    if not tl:
        raise Failed("TinyTeX's package manager is missing")
    # A fresh TinyTeX refuses any install until its manager is updated.
    _run([tl, "update", "--self"], timeout=900)
    code, out = _run([tl, "install", *packages], timeout=1800)
    if code != 0:
        raise Failed("the LaTeX packages did not install: "
                     + (out.strip().splitlines() or ["no output"])[-1][:200])


def test_compile() -> None:
    """Compile both example documents, as CI does, in a scratch copy."""
    work = tempfile.mkdtemp(prefix="ljs_smoke_")
    env = dict(os.environ, TEXMFHOME=os.path.join(ROOT, "texmf"))
    for folder, engine, tex in (("cv", "lualatex", "main_example.tex"),
                                ("cover_letters", "xelatex", "cover_example.tex")):
        dest = os.path.join(work, folder)
        shutil.copytree(os.path.join(ROOT, folder), dest,
                        ignore=shutil.ignore_patterns("*.pdf", "*.aux", "*.log", "*_Resume_*",
                                                      "*_CV_*", "*_Cover_Letter_*"))
        code, out = _run([_which(engine), "-interaction=nonstopmode", "-halt-on-error", tex],
                         timeout=600, env=env, cwd=dest)
        if not os.path.exists(os.path.join(dest, tex[:-4] + ".pdf")):
            err = [ln for ln in out.splitlines() if ln.startswith("!")][:2]
            raise Failed(f"LaTeX is installed but the {folder.replace('_', ' ')} example did "
                         f"not compile: " + (" ".join(err) or f"{engine} exit {code}"))
    shutil.rmtree(work, ignore_errors=True)


def fix_latex() -> str:
    """LaTeX that compiles both templates. A LaTeX already here is tested by compiling
    them, never by a list of packages: TeX Live 2023's moderncv needs no fontawesome6 and
    2026's does, and either compiles the resume."""
    kind = latex_kind()
    if kind == "miktex":
        initexmf = _which("initexmf")
        if initexmf:
            # MiKTeX asks before it installs a package it lacks; with nobody to answer, a
            # compile waits for ever. "Just enough TeX" (miktex.org/kb/just-enough-tex)
            # gives this per-user setting, which needs no administrator.
            _run([initexmf, "--set-config-value=[MPM]AutoInstall=yes"], timeout=120)
        test_compile()
        return "already here (MiKTeX, set to install what it lacks without asking)"
    if kind:
        try:
            test_compile()
            return "already here"
        except Failed:
            if kind == "tinytex":
                tlmgr_install(TEX_PACKAGES)
                test_compile()
                return "already here; added the packages the templates use"
            # A system LaTeX takes a password to change: TinyTeX beside it, found first.
    started = time.monotonic()
    install_tinytex()
    tlmgr_install(TEX_PACKAGES)
    test_compile()
    took = int(time.monotonic() - started)
    return f"installed (TinyTeX, {took // 60} min {took % 60} s; both example documents compiled)"


FIXES = {"git": ("Git", fix_git),
         "python": ("A python3 command" if WINDOWS else "A current Python", fix_python),
         "packages": ("The Python packages", fix_packages),
         "runtime": ("Node or Bun, for the job searches", fix_runtime),
         "gh": ("GitHub's command line", fix_gh), "latex": ("LaTeX, for the PDFs", fix_latex)}


def plan() -> list[tuple[str, str]]:
    """(what, what it would do) for each thing missing here, doing nothing."""
    out = []
    if not (_which("git") and _works([_which("git"), "--version"])):
        out.append(("git", "Apple's command line tools window" if MAC else
                    "PortableGit, in your own folder" if WINDOWS else linux_install("git")))
    if WINDOWS and not shutil.which("python3"):
        out.append(("python", "a python3 command for the Python you have"))
    if needs_python():
        want = python_floor.CURRENT
        out.append(("python", f"Python {want[0]}.{want[1]} in your own folder (uv), with the "
                              "packages moved to it"))
    if missing_modules():
        out.append(("packages", "the Python packages, in this folder's .venv"))
    if not runtime_here():
        out.append(("runtime", "Bun, from its own release"))
    if not (_which("gh") and _works([_which("gh"), "--version"])):
        out.append(("gh", "GitHub's command line, from its release"))
    kind = latex_kind()
    if not kind or (kind != "miktex" and tex_missing()):
        out.append(("latex", "TinyTeX and the template packages, then a test compile"))
    return out


def default_todo(windows: bool = WINDOWS, mac: bool = MAC, floor_ok=None) -> list:
    """What a bare `--fix` does: everything, but a new Python only where one is needed
    (Windows' python3 command, a Mac's current Python, a Python under the floor)."""
    floor_ok = python_floor.ok() if floor_ok is None else floor_ok
    return [w for w in WHAT if w != "python" or windows or mac or not floor_ok]


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[:1] in (["-h"], ["--help"]):
        # Never an install from a bare command: `all` says everything, on purpose.
        print(f"usage: python3 tools/env_check.py --fix [all | {' '.join(WHAT)}] [--plan]\n\n"
              + __doc__.strip().split("\n\n")[1])
        return 0 if argv else 2
    if "--plan" in argv:
        todo = plan()
        for what, how in todo:
            _say(f"{FIXES[what][0]}: {how}")
        if not todo:
            _say("Nothing is missing here.")
        return 0
    asked = [a for a in argv if not a.startswith("-") and a != "all"]
    unknown = [a for a in asked if a not in FIXES]
    if unknown:
        print(f"env_check --fix: no such thing as {', '.join(unknown)}; "
              f"choose from {', '.join(WHAT)}", file=sys.stderr)
        return 2
    failed, yours = [], []
    todo = [w for w in WHAT if w in asked] if asked else default_todo()
    for what in todo:
        label, fn = FIXES[what]
        try:
            said = fn()
        except Failed as exc:
            said = str(exc)
            (yours if said.startswith("yours") else failed).append(label)
        except Exception as exc:  # noqa: BLE001  one install never stops the others
            said = f"could not be set up: {type(exc).__name__}: {str(exc)[:160]}"
            failed.append(label)
        _say(f"{label}: {said}")
        if "signing in is yours" in said:
            yours.append("GitHub sign-in")
    if failed:
        _say("Not done: " + ", ".join(failed) + ". The lines above say what to do.")
        return 1
    _say("Done." + (" Yours, once: " + ", ".join(yours) + "." if yours else
                    " Nothing needs you."))
    return 0


if __name__ == "__main__":
    sys.exit(main())
