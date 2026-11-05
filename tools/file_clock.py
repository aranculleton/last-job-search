"""Now, on the clock that stamps files: what a file's age is measured against.

A file's time (st_mtime) is set by the file system, never by Python, so its age is the file
system's now less that time, never time.time() less it. The two are different clocks where
Python's is moved (the suite run with the clock 400 days on, tools/everywhere.sh: every file
written that moment read as 400 days old, and a landing called today's notes "over a week
old"; a search's shortlist saved a minute ago read as saved before the search began, 2026-11-05)
or where a network drive's server keeps its own time. A record's own time (a claim's
claimed_at, a commit's date) is Python's clock and is measured against time.time(): each age
on its own clock, and only ages are compared.

    import file_clock
    file_clock.age(path)          # seconds since the file was last written
    file_clock.now(folder)        # now, as a file written in that folder would be stamped
"""
from __future__ import annotations

import os
import tempfile
import time


def now(where: str = "") -> float:
    """Now on the clock that stamps files in `where` (a folder; the system's temporary folder
    when empty): a file written this moment there, its time read back, and removed. Where no
    file can be written, time.time()."""
    try:
        fd, path = tempfile.mkstemp(prefix=".ljs-clock-", dir=where or None)
    except OSError:
        return time.time()
    try:
        os.close(fd)
        return os.stat(path).st_mtime
    except OSError:
        return time.time()
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def age(path: str, at: float | None = None) -> float:
    """Seconds since `path` was last written, on the files' own clock (`at`, a now() already
    read, saves reading it again for many files). Raises OSError as os.stat does."""
    written = os.path.getmtime(path)
    return (now(os.path.dirname(os.path.abspath(path))) if at is None else at) - written
