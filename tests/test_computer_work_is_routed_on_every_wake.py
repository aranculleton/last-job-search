"""Work waiting for the person's computer is routed on every wake of the chat that answers the
page, not only by the next morning's brief.

The maintainer's copy, 2026-11-11 (local review 1): a LinkedIn read sent to the Mac waited 16
hours. `wake` printed nothing about work sent `to: computer` (no cloud chat may take it, so
`next` never shows it), wake.md never mentioned it, and the step that routes it was in a file
read only when a wake handed over computer work, which never happened. So Start it now, Try
again, a sign-in answered on the page and a sign-in wait that ended each rang a wake that did
nothing, while the page promised it would start. Now `wake` prints a `computer:` line whenever
work waits there, with exactly what to do. Every person, employer and chat is invented.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import pytest  # noqa: E402

from test_a_ring_is_answered_in_one_command import CHAT, Ring  # noqa: E402
from test_a_tick_on_the_page_is_applied_once import _w  # noqa: E402


@pytest.fixture
def ring(tmp_path):
    r = Ring(tmp_path)
    yield r
    sys.path.remove(r.root)


def _line(said: str) -> str:
    return next((ln for ln in said.splitlines() if ln.startswith("computer:")), "")


def test_a_wake_names_the_work_waiting_for_the_computer_and_how_to_route_it(ring):
    ring.put("work", "network~read~1", _w("network", "Harbourline Bank", to="computer",
                                          title="People at Harbourline Bank"), version=3)
    d = ring.read("wake1")
    said = ring.wake(d)
    line = _line(said)
    assert line, said
    assert "network~read~1" in line
    assert f'python3 tools/computer.py route "{d}" --chat {CHAT}' in line
    assert "its batches first" in line and "`handback`" in line
    # Never the work itself in the cloud: it is not offered as next.
    assert "network~read~1" not in said.split("\nnext: ", 1)[-1] if "\nnext: " in said else True


def test_a_chat_on_the_computer_left_to_put_away_is_named_too(ring):
    done = dict(_w("network", "Harbourline Bank", to="computer", status="done",
                   finished_at="2026-10-25T10:00:00Z"),
                computer_session={"id": "session_mac1", "at": "2026-10-25T09:00:00Z"})
    ring.put("work", "network~read~1", done, version=4)
    assert "put away" in _line(ring.wake(ring.read("wake1")))


def test_nothing_is_said_when_nothing_waits_for_the_computer(ring):
    ring.put("work", "network~read~1", _w("network", "Harbourline Bank", to="computer",
                                          status="done", finished_at="2026-10-25T10:00:00Z"),
             version=4)
    assert _line(ring.wake(ring.read("wake1"))) == ""


def test_the_instructions_route_it_on_each_wake():
    def text(*path):
        with open(os.path.join(ROOT, *path), encoding="utf-8") as fh:
            return " ".join(fh.read().split())
    wake = text(".claude", "skills", "app", "wake.md")
    assert "`computer:`" in wake and "handback" in wake
    jobs = text(".claude", "skills", "app", "jobs.md")
    assert "After each `wake`, `python3 tools/computer.py waiting" not in jobs
    assert "`computer:`" in jobs
    doc = text("COMPUTER.md")
    assert "The page's helper runs `python3 tools/computer.py waiting` on each wake" not in doc
    assert "`computer:`" in doc
