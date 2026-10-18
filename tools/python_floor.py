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


def require(code: int = 3) -> None:
    """Stop with the one sentence on an older Python; nothing else has run yet."""
    if not ok():
        print(message(), file=sys.stderr)
        raise SystemExit(code)


if __name__ == "__main__":
    print("ok" if ok() else message())
