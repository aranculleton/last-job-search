"""A Mac gets a current Python with no password, and every command runs under it.

Apple's own `python3` is 3.9, which has had no security fixes since October 2025. So on a
Mac `env_check.py --fix` installs uv by its own installer into ~/.local/bin and a current
Python with `uv python install`, makes the repo's .venv with it, and leaves Apple's
`python3` exactly as it was. An app command Claude starts with that `python3` (or any
other) then runs itself again under the venv's Python, because a venv's packages are
built for one version of Python and cannot be imported by another. A Linux whose Python
is older than 3.9 takes the same route instead of a sudo line. Python's own HTTPS finds
the system's certificates where its OpenSSL has none of its own (python.org's for a Mac
before "Install Certificates").
"""
from __future__ import annotations

import collections
import os
import re
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import env_check  # noqa: E402
import installs as I  # noqa: E402
import local_path as L  # noqa: E402
import python_floor  # noqa: E402


def _repo(tmp_path, made="3.13", home_exists=True):
    """A repo with a .venv made by `made`, whose base Python's folder is there or not."""
    root = tmp_path / "repo"
    (root / "tools").mkdir(parents=True)
    (root / "tools" / "a_tool.py").write_text("print('hi')\n", encoding="utf-8")
    home = tmp_path / "base" / "bin"
    if home_exists:
        home.mkdir(parents=True)
    venv = root / ".venv"
    exe = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    exe.parent.mkdir(parents=True)
    exe.write_text("")
    # UTF-8, as venv itself writes it (Lib/venv/__init__.py): a folder named "Zoë" written
    # in Windows' own code page instead is a file no Python ever makes.
    (venv / "pyvenv.cfg").write_text(f"home = {home}\nversion = {made}.4\n", encoding="utf-8")
    return root, str(exe)


def test_a_venv_config_with_a_byte_that_is_not_utf8_is_read_as_python_reads_it(tmp_path):
    # Python reads pyvenv.cfg as UTF-8 and keeps a byte that is not (surrogateescape:
    # Python/pathconfig.c in 3.9, Modules/getpath.c from 3.11), so a config written in a
    # code page by some other tool is read, never a stop for every command.
    root, exe = _repo(tmp_path)
    cfg = os.path.join(str(root), ".venv", "pyvenv.cfg")
    with open(cfg, "wb") as fh:
        fh.write(b"home = " + os.fsencode(str(tmp_path / "base" / "bin")) +
                 b"\nprompt = Zo\xeb's search\nversion = 3.13.4\n")
    assert L.venv_version(str(root)) == (3, 13)
    assert L.venv_runs(str(root))
    assert L.venv_site(str(root), (3, 13)) is None          # no site-packages folder in it
    script = str(root / "tools" / "a_tool.py")
    assert L.rerun_args([script], None, {}, "/usr", (3, 9), str(root)) == [exe, script]


def test_an_app_script_started_by_another_version_runs_again_under_the_venvs(tmp_path):
    root, exe = _repo(tmp_path)
    script = str(root / "tools" / "a_tool.py")
    args = L.rerun_args([script, "--due"], None, {}, "/usr", (3, 9), str(root))
    assert args == [exe, script, "--due"]
    # The interpreter's own options are kept where this Python records them (3.10+).
    assert L.rerun_args([script], None, {}, "/usr", (3, 12), str(root),
                        orig_argv=["python3", "-X", "utf8", script]) == [exe, "-X", "utf8",
                                                                         script]


def test_only_the_apps_own_scripts_ever_run_again(tmp_path):
    root, _ = _repo(tmp_path)
    script = str(root / "tools" / "a_tool.py")
    never = {
        "-c": (["-c"], None, {}),
        "-m": ([script], object(), {}),                         # python -m <module>
        "pytest": ([os.path.join(str(tmp_path), "pytest", "__main__.py")], None, {}),
        "a REPL": ([""], None, {}),
        "a second try": ([script], None, {L.REEXEC: "/usr/bin/python3"}),
        "outside tools/": ([str(root / "a_tool.py")], None, {}),
    }
    for why, (argv, spec, env) in never.items():
        assert L.rerun_args(argv, spec, env, "/usr", (3, 9), str(root)) is None, why
    # The same version (its packages work as they are), the venv itself, a venv made too
    # old, or one whose Python was removed: run here.
    assert L.rerun_args([script], None, {}, "/usr", (3, 13), str(root)) is None
    assert L.rerun_args([script], None, {}, str(root / ".venv"), (3, 9), str(root)) is None
    old, _ = _repo(tmp_path / "old", made="3.8")
    assert L.rerun_args([str(old / "tools" / "a_tool.py")], None, {}, "/usr", (3, 12),
                        str(old)) is None
    gone, _ = _repo(tmp_path / "gone", home_exists=False)
    assert L.rerun_args([str(gone / "tools" / "a_tool.py")], None, {}, "/usr", (3, 9),
                        str(gone)) is None


def test_windows_runs_it_as_a_child_and_exits_with_its_code(monkeypatch):
    monkeypatch.setattr(L, "rerun_args", lambda **k: ["C:/repo/.venv/Scripts/python.exe",
                                                     "tools/a.py"])
    seen = {}

    def call(args, env):
        seen.update(args=args, guard=env.get(L.REEXEC))
        return 7
    with pytest.raises(SystemExit) as stop:
        L.run_in_venv(windows=True, call=call)
    assert stop.value.code == 7 and seen["args"][1] == "tools/a.py" and seen["guard"]
    ran = {}
    L.run_in_venv(windows=False, execve=lambda exe, args, env: ran.update(exe=exe, env=env))
    assert ran["exe"].endswith("python.exe") and ran["env"][L.REEXEC]


def _other_python():
    """A Python of another minor version on this computer, or None."""
    here = "%d.%d" % sys.version_info[:2]
    for minor in range(9, 16):
        for name in (f"python3.{minor}", f"/usr/bin/python3.{minor}"):
            path = shutil.which(name)
            if not path or f"3.{minor}" == here:
                continue
            r = subprocess.run([path, "-I", "-S", "-c", "import sys; print(sys.version_info[:2])"],
                               capture_output=True, text=True, encoding="utf-8", errors="replace")
            if r.returncode == 0 and f", {minor})" in r.stdout:
                return path
    return None


def test_for_real_a_tool_started_by_this_python_runs_under_a_venv_of_another(tmp_path):
    other = _other_python()
    if not other:
        pytest.skip("no Python of a second version here")
    root = tmp_path / "repo"
    (root / "tools").mkdir(parents=True)
    for name in ("local_path.py", "python_floor.py"):
        shutil.copy(os.path.join(ROOT, "tools", name), root / "tools" / name)
    (root / "tools" / "which.py").write_text(
        "import sys, os\nsys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))\n"
        "import python_floor\npython_floor.require()\n"
        "print('%d.%d' % sys.version_info[:2], sys.argv[1:])\n")
    subprocess.run([other, "-m", "venv", "--without-pip", str(root / ".venv")], check=True)
    want = subprocess.run([other, "-c", "import sys; print('%d.%d' % sys.version_info[:2])"],
                          capture_output=True, text=True, encoding="utf-8", errors="replace").stdout.strip()
    env = {k: v for k, v in os.environ.items() if k != L.REEXEC}
    r = subprocess.run([sys.executable, str(root / "tools" / "which.py"), "a b", "ü"],
                       capture_output=True, text=True, env=env, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    assert r.stdout.split()[0] == want and "'a b', 'ü'" in r.stdout
    # -c is the Python that was asked for, never the venv's.
    r = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, sys.argv[1]); "
                        "import python_floor; python_floor.require(); "
                        "print('%d.%d' % sys.version_info[:2])", str(root / "tools")],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    assert r.stdout.strip() == "%d.%d" % sys.version_info[:2]


Paths = collections.namedtuple("Paths", "cafile capath")


def test_python_finds_the_systems_certificates_where_its_own_openssl_has_none(tmp_path):
    bundle = tmp_path / "cert.pem"
    bundle.write_text("-----BEGIN CERTIFICATE-----\n")
    empty = tmp_path / "certs"
    empty.mkdir()
    env = {}
    # python.org's Python for a Mac before "Install Certificates": no file, an empty folder.
    assert L.trust_store(env, Paths(None, str(empty)), [str(bundle)], windows=False) == str(bundle)
    assert env["SSL_CERT_FILE"] == str(bundle)
    # Nothing changes where this Python has certificates, or a choice was already made.
    for paths in (Paths("/its/own.pem", None),):
        assert L.trust_store({}, paths, [str(bundle)], windows=False) == ""
    hashed = tmp_path / "hashed"
    hashed.mkdir()
    (hashed / "002c0b4f.0").write_text("")
    assert L.trust_store({}, Paths(None, str(hashed)), [str(bundle)], windows=False) == ""
    mine = {"SSL_CERT_FILE": "/mine.pem"}
    assert L.trust_store(mine, Paths(None, None), [str(bundle)], windows=False) == ""
    assert mine == {"SSL_CERT_FILE": "/mine.pem"}
    assert L.trust_store({}, Paths(None, None), [str(bundle)], windows=True) == ""
    # The Mac's own bundle is the first place looked.
    assert L.CERT_FILES[0] == "/etc/ssl/cert.pem"


def test_a_mac_needs_the_current_python_until_its_venv_runs_one(monkeypatch):
    monkeypatch.setattr(I, "WINDOWS", False)
    cur = python_floor.CURRENT
    assert I.needs_python(mac=True, here=(3, 9), venv=None, venv_runs=False)
    assert I.needs_python(mac=True, here=(3, 9), venv=(3, 9), venv_runs=True)
    assert not I.needs_python(mac=True, here=(3, 9), venv=cur, venv_runs=True)
    assert I.needs_python(mac=True, here=(3, 9), venv=cur, venv_runs=False)      # Python removed
    assert not I.needs_python(mac=True, here=cur, venv=None, venv_runs=False)     # brew's, say
    # Linux keeps its Python unless it is under the floor.
    assert not I.needs_python(mac=False, here=(3, 12), venv=None, venv_runs=False)
    assert I.needs_python(mac=False, here=(3, 8), venv=None, venv_runs=False)
    monkeypatch.setattr(I, "WINDOWS", True)
    assert not I.needs_python(mac=True, here=(3, 8), venv=None, venv_runs=False)


def test_uv_comes_from_its_own_installer_and_changes_no_startup_file(home, monkeypatch):
    calls, fetched = [], []
    have = {"uv": None}
    monkeypatch.setattr(I, "_uv", lambda: have["uv"])
    monkeypatch.setattr(I, "download", lambda url, dest: fetched.append(url) or
                        open(dest, "w").write("#!/bin/sh\n"))

    def run(cmd, timeout=600, env=None, cwd=None):
        calls.append((list(cmd), env or {}))
        if cmd[0] == "sh":
            have["uv"] = os.path.join(I.user_bin(), "uv")
        return 0, "uv 0.13.5"
    monkeypatch.setattr(I, "_run", run)
    exe = I.install_uv()
    assert fetched == ["https://astral.sh/uv/install.sh"]
    assert calls[0][0][0] == "sh" and calls[0][1].get("UV_NO_MODIFY_PATH") == "1"
    assert exe == os.path.join(I.user_bin(), "uv")
    assert not [c for c, _ in calls if "sudo" in c or "brew" in " ".join(c)]


def test_the_python_install_adds_no_python_command_and_touches_apples(monkeypatch):
    calls = []
    monkeypatch.setattr(I, "install_uv", lambda: "/h/.local/bin/uv")
    monkeypatch.setenv("VIRTUAL_ENV", "/somewhere/.venv")

    def run(cmd, timeout=600, env=None, cwd=None):
        calls.append((list(cmd), env or {}))
        if cmd[1:3] == ["python", "find"]:
            return 0, f"{sys.executable}\nwarning: something uv says on stderr\n"
        return 0, "Installed Python 3.13.17"
    monkeypatch.setattr(I, "_run", run)
    assert I.install_python() == sys.executable          # the path, never uv's warning line
    install, find = calls[0], calls[1]
    assert install[0] == ["/h/.local/bin/uv", "python", "install", "3.13"]
    assert "--default" not in install[0]                 # no python3 of uv's ahead of Apple's
    assert install[1]["UV_PYTHON_INSTALL_BIN"] == "0" and "VIRTUAL_ENV" not in install[1]
    assert find[0][:3] == ["/h/.local/bin/uv", "python", "find"]
    assert "--system" in find[0] and "only-managed" in find[0]
    text = open(os.path.join(ROOT, "tools", "installs.py"), encoding="utf-8").read()
    assert '"--default"' not in text and not re.search(r"\bbrew (install|upgrade)", text)


def test_on_a_mac_the_fix_installs_it_and_makes_the_venv_with_it(monkeypatch):
    monkeypatch.setattr(I, "WINDOWS", False)
    monkeypatch.setattr(I, "MAC", True)
    monkeypatch.setattr(I, "needs_python", lambda **k: True)
    monkeypatch.setattr(I, "install_python", lambda: "/h/.local/share/uv/python/cp313/bin/python3.13")
    monkeypatch.setattr(I, "version_of", lambda p: (3, 13))
    made = []
    monkeypatch.setattr(I, "fix_packages", lambda base=None: made.append(base) or "installed (pypdf)")
    said = I.fix_python()
    assert made == ["/h/.local/share/uv/python/cp313/bin/python3.13"]
    assert said.startswith("installed (Python 3.13, in your own folder; Apple's python3 is as it was")
    monkeypatch.setattr(I, "needs_python", lambda **k: False)
    assert I.fix_python() == "already here"


def test_a_bare_fix_includes_the_python_where_one_is_needed():
    assert "python" in I.default_todo(windows=False, mac=True, floor_ok=True)
    assert "python" in I.default_todo(windows=True, mac=False, floor_ok=True)
    assert "python" in I.default_todo(windows=False, mac=False, floor_ok=False)
    assert "python" not in I.default_todo(windows=False, mac=False, floor_ok=True)
    assert I.default_todo(windows=False, mac=True, floor_ok=True).index("python") < \
        I.default_todo(windows=False, mac=True, floor_ok=True).index("packages")


def test_a_working_venv_is_never_made_again_by_an_older_python3(tmp_path, monkeypatch):
    root, _ = _repo(tmp_path, made="3.13")
    base = tmp_path / "base" / "bin" / "python3"
    base.write_text("")
    monkeypatch.setattr(I, "VENV", str(root / ".venv"))
    monkeypatch.setattr(I, "WINDOWS", False)
    monkeypatch.setattr(I, "MAC", False)
    assert I.venv_base() == str(base)
    # On a Mac the current Python uv installed comes first.
    monkeypatch.setattr(I, "MAC", True)
    monkeypatch.setattr(I, "managed_python", lambda *a, **k: "/uv/python3.13")
    assert I.venv_base() == "/uv/python3.13"


def test_the_advice_for_an_old_python_on_linux_needs_no_password():
    said = python_floor.how_to_install("linux")
    assert "astral.sh/uv/install.sh" in said and "UV_NO_MODIFY_PATH=1" in said
    assert "sudo" not in said and "password" in said     # "with no password"
    fixes = env_check.local_fixes("linux", have=lambda t: None, module=lambda m: True,
                                  py_ok=False, pypdf="ok", gh_signed_in=True)
    py = [f for f in fixes if f[0].startswith("Python")][0]
    assert py == ("Python 3.9 or newer", python_floor.linux_route(), "")
    git = [f for f in fixes if f[0] == "Git"][0]
    assert git[1].startswith("sudo apt-get install") and git[2] == "yours"   # Git keeps it
    # A Mac whose Python is Apple's is offered the current one, by Claude, no password.
    mac = env_check.local_fixes("darwin", have=lambda t: "/usr/bin/" + t, module=lambda m: True,
                                py_ok=True, pypdf="ok", gh_signed_in=True, newer=True)
    assert mac == [(mac[0][0], "python3 tools/env_check.py --fix python", "")]
    assert mac[0][0].startswith("Python 3.13 (this Mac's own is")
    assert "security fixes" in mac[0][0]


def test_pythons_own_https_names_a_python_that_cannot_check_certificates(monkeypatch):
    import ssl
    import urllib.error
    import urllib.request

    def refuse(url, timeout=10):
        raise urllib.error.URLError(ssl.SSLCertVerificationError(1, "CERTIFICATE_VERIFY_FAILED"))
    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    verdict, detail = env_check.https_check("https://example.com")
    assert verdict == "certificates" and sys.executable in detail

    def answer(url, timeout=10):
        raise urllib.error.HTTPError(url, 403, "Forbidden", {}, None)
    monkeypatch.setattr(urllib.request, "urlopen", answer)
    assert env_check.https_check("https://example.com") == ("ok", "HTTP 403")

    def offline(url, timeout=10):
        raise urllib.error.URLError(OSError("Name or service not known"))
    monkeypatch.setattr(urllib.request, "urlopen", offline)
    assert env_check.https_check("https://example.com")[0] == "unknown"
    assert "linkedin" not in env_check.https_host()


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(I, "HOME", str(tmp_path))
    monkeypatch.setattr(I, "user_bin", lambda: os.path.join(str(tmp_path), ".local", "bin"))
    return tmp_path
