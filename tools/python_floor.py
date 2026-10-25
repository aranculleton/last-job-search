#!/usr/bin/env python3
"""The oldest Python the app runs on, and the one sentence when this one is older.

3.9 is the floor because it is what a Mac's own `python3` is (3.9.6, from Apple's
command line tools): a person on a Mac needs no installer at all. CI runs the suite
on 3.9 and 3.13, so nothing newer than 3.9 creeps in unnoticed.

Every tool imports `person`, which calls `require()` before anything else, and the
merge driver (`merge_state.py`) calls it too: an older Python stops with one plain
sentence instead of a traceback halfway through a state file.
"""
from __future__ import annotations

import codecs
import platform
import sys

FLOOR = (3, 9)


def how_to_install(system: str | None = None) -> str:
    """The one way to get a newer Python where this session runs."""
    system = system or sys.platform
    if system == "darwin":
        return ("on a Mac, run `xcode-select --install` once (it asks for your Mac password "
                "and brings Python 3.9), or use the installer at "
                "https://www.python.org/downloads/")
    if system.startswith("win"):
        return ("use the installer at https://www.python.org/downloads/ and tick "
                "\"Add python.exe to PATH\", or run `winget install Python.Python.3.12`")
    return "install it with your system's package manager, for example `sudo apt-get install python3`"


def message(version: str | None = None, system: str | None = None) -> str:
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


def utf8_stdio(streams=None) -> list[str]:
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


def require(code: int = 3) -> None:
    """Stop with the one sentence on an older Python; nothing else has run yet. Then the
    terminal is read and written in UTF-8 (utf8_stdio)."""
    if not ok():
        print(message(), file=sys.stderr)
        raise SystemExit(code)
    utf8_stdio()


if __name__ == "__main__":
    print("ok" if ok() else message())
