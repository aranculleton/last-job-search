"""`ats_boards.py --probe` reads the employer boards side by side, as a round does.

It read them one after another: 92 boards on one person's list took minutes, though
nothing made one wait on another and a round reads the same boards sixteen at a time.
openroles still holds each host to its own few requests at once. The verdicts and their
order are what they were.
"""
from __future__ import annotations

import os
import sys
import threading
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import ats_boards  # noqa: E402


class _Slow:
    """A reader that takes a moment and notes how many are read at once."""
    def __init__(self):
        self.now = self.most = 0
        self.lock = threading.Lock()

    def fetch(self, token):
        with self.lock:
            self.now += 1
            self.most = max(self.most, self.now)
        time.sleep(0.2)
        with self.lock:
            self.now -= 1
        if token == "gone":
            raise ats_boards.BoardError("greenhouse gone: 404 Not Found")
        return []


@pytest.mark.timing
def test_the_boards_are_read_at_once_and_said_in_order(monkeypatch):
    slow = _Slow()
    monkeypatch.setattr(ats_boards, "READERS", dict(ats_boards.READERS, greenhouse=slow))
    monkeypatch.setattr(ats_boards, "REFUSED", {})
    monkeypatch.setattr(ats_boards, "REFUSED_PROVIDERS", {})
    boards = {f"Employer {n:02d}": ("greenhouse", "gone" if n == 3 else f"t{n}") for n in range(8)}
    boards["Employer 99"] = ("nosuchsystem", "x")
    began = time.monotonic()
    got = ats_boards.probe(boards)
    assert time.monotonic() - began < 8 * 0.2
    assert slow.most > 1
    assert list(got) == sorted(boards)
    assert got["Employer 03"] == "NO JOBS (404 Not Found)"
    assert got["Employer 00"] == "NO JOBS (token may be wrong)"
    assert got["Employer 99"] == "NO READER ('nosuchsystem')"
