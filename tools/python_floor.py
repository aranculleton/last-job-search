#!/usr/bin/env python3
"""The oldest Python the app runs on, and the one sentence when this one is older.

3.9 is the floor because it is what a Mac's own `python3` is (3.9.6, from Apple's
command line tools), so every command still starts there. 3.9 has had no security fixes
since October 2025, so on a Mac `env_check.py --fix` installs a current Python (CURRENT)
into the person's own folders with no password and makes the repo's `.venv` with it, and
an app command started by Apple's `python3` runs itself again under that Python
(local_path.run_in_venv). CI runs the suite on 3.9 and 3.13, so nothing newer than 3.9
creeps in unnoticed.

Every tool imports `person`, which calls `require()` before anything else, and the
merge driver (`merge_state.py`) calls it too: an older Python stops with one plain
sentence instead of a traceback halfway through a state file.

    python3 tools/python_floor.py           ok, or the sentence
    python3 tools/python_floor.py --which   the Python an app command runs under here

This file is read by Pythons far older than the floor, which is its point: no
`from __future__ import annotations` (3.7 and newer: on RHEL 8's and Ubuntu 18.04's
Python 3.6 the sentence was a SyntaxError, 2026-10-25), and its annotations are text.
"""

import codecs
import platform
import sys

FLOOR = (3, 9)
# What `env_check.py --fix python` installs where one is needed (a Mac, or a Linux whose
# Python is older than FLOOR): the newest version CI runs the whole suite on.
CURRENT = (3, 13)
# uv's own installer, as its documentation gives it (https://docs.astral.sh/uv/getting-
# started/installation/), told not to edit the shell's startup files: the app runs uv and
# the Python it installs by their paths.
UV_INSTALL = "curl -LsSf https://astral.sh/uv/install.sh | env UV_NO_MODIFY_PATH=1 sh"


def how_to_install(system: "str | None" = None) -> str:
    """The one way to get a newer Python where this session runs."""
    system = system or sys.platform
    if system == "darwin":
        return ("on a Mac, run `xcode-select --install` once (Apple's window asks to install "
                "its developer tools, which bring Python 3.9)")
    if system.startswith("win"):
        return ("run `powershell -ExecutionPolicy Bypass -File tools/computer_setup.ps1`, which "
                "installs python.org's own install manager with no administrator (or use the "
                "installer at https://www.python.org/downloads/ and tick \"Add python.exe to "
                "PATH\")")
    return (f"install Python {CURRENT[0]}.{CURRENT[1]} into your own folders, with no password: "
            f"`{linux_route()}`")


def linux_route() -> str:
    """One command, for a Linux whose Python is too old to run the app: uv by its own
    installer, a current Python, then the install route run by that Python, which makes
    the repo's .venv with it. It needs no Python to start."""
    want = f"{CURRENT[0]}.{CURRENT[1]}"
    return (f"{UV_INSTALL} && ~/.local/bin/uv python install {want} && "
            f"\"$(~/.local/bin/uv python find {want})\" tools/env_check.py --fix")


def message(version: "str | None" = None, system: "str | None" = None) -> str:
    version = version or platform.python_version()
    return (f"Python {FLOOR[0]}.{FLOOR[1]} or newer is needed; this is {version}. "
            f"To install it, {how_to_install(system)}.")


def ok(info=None) -> bool:
    return tuple((info or sys.version_info)[:2]) >= FLOOR


def _safe(e):
    """Never stop on text: a name os read in an undecodable locale goes out as its own bytes
    (what "surrogateescape" does), any other character that cannot be written is "?", and
    a byte that cannot be read is U+FFFD."""
    if isinstance(e, UnicodeEncodeError):
        out = bytearray()
        for ch in e.object[e.start:e.end]:
            c = ord(ch)
            out += bytes([c - 0xDC00]) if 0xDC80 <= c <= 0xDCFF else b"?"
        return bytes(out), e.end
    return "\ufffd", e.end


_SAFE = "ljs-safe"
codecs.register_error(_SAFE, _safe)


def utf8_stdio(streams=None) -> "list[str]":
    """Read and write the terminal in UTF-8, whatever this computer's own encoding is.

    Python on Windows writes to a pipe in the computer's code page (cp1252 in English,
    https://docs.python.org/3/library/sys.html#sys.stdout) unless UTF-8 mode is on, so a
    contact called Łukasz, a reply ending in 👍 or a name in another alphabet stopped a tool
    with UnicodeEncodeError halfway through what it was saying, and a pasted profile read
    from stdin came in garbled. `.claude/settings.json` turns UTF-8 mode on for every chat
    (PYTHONUTF8, https://docs.python.org/3/using/cmdline.html#envvar-PYTHONUTF8); this is for
    a tool run any other way. A character the terminal cannot show prints as "?" rather than
    stopping it. A file name the computer's C locale could not decode (a Linux or Mac
    terminal with no UTF-8 locale set) prints as the bytes it is, so "Łukasz.md" stays
    "Łukasz.md". Returns the names of the streams it changed."""
    changed = []
    for name in streams or ("stdin", "stdout", "stderr"):
        s = getattr(sys, name, None)
        enc = str(getattr(s, "encoding", "") or "").lower().replace("_", "-")
        if enc in ("utf-8", "utf8") or not hasattr(s, "reconfigure"):
            continue
        try:
            s.reconfigure(encoding="utf-8", errors=_SAFE)
            changed.append(name)
        except (ValueError, OSError, AttributeError):  # a stream already read from, or closed
            pass
    return changed


def _local_path():
    try:
        import local_path
    except ImportError:
        import os
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import local_path
    return local_path


def require(code: int = 3) -> None:
    """Run the app's own script under the repo's .venv when that venv was made by another
    version of Python (a Mac's, made with a current one), then stop with the one sentence
    on an older Python; nothing else has run yet. Then the terminal is read and written in
    UTF-8 (utf8_stdio), and on a Mac, or with a Python uv installed, Python's own HTTPS
    finds the system's certificates (local_path.trust_store)."""
    lp = _local_path()
    lp.run_in_venv()
    if not ok():
        print(message(), file=sys.stderr)
        raise SystemExit(code)
    utf8_stdio()
    if sys.platform == "darwin" or "uv" in sys.base_prefix.replace("\\", "/").split("/"):
        lp.trust_store()


if __name__ == "__main__":
    if sys.argv[1:2] == ["--which"]:
        require()
        print(f"Python {platform.python_version()} at {sys.executable}")
    else:
        print("ok" if ok() else message())
