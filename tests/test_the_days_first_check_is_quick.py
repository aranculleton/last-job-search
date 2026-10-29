"""The day's first check is quick, and says what it always said.

CLAUDE.md has a chat run `sync_app.py --if-stale` before each piece of work. Every run
after the first one that day reads a date and stops. The first one did everything, and
on a copy of a real person's repo it took 10 seconds on a day with no update and 42 on
the day one arrived (2026-10-22). Most of that was waste:

- the list of what the repo still needs was worked out twice, the second time straight
  after the first with nothing changed between them;
- each of its sixteen probes started a fresh interpreter and imported the same tools
  again.

These tests pin the quick way, and that each part answers exactly as the slow way did.
"""
from __future__ import annotations

import os
import sys
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import profile_upgrades as U  # noqa: E402


# ------------------------------------------------------------------ probes

def test_a_look_asks_every_probe_of_one_interpreter():
    with U._one_interpreter():
        U._probe("import sys; sys.ljs_seen = 7")
        assert U._probe("import sys; print(getattr(sys, 'ljs_seen', 0))") == "7"
    # Outside a look, each probe has an interpreter to itself, as before.
    assert U._probe("import sys; print(getattr(sys, 'ljs_seen', 0))") == "0"


PROBES = [
    "print('a plain answer')",
    "print('printed, then broken'); raise ValueError('no')",
    "import sys; print('done early'); sys.exit(0)",
    "import sys; print('done badly'); sys.exit(3)",
    "import sys; sys.exit('a message is a failure')",
    # Below print, and from a child process: both reach a pipe, so both count.
    "import os; os.write(1, b'raw '); print('then printed')",
    "import subprocess, sys; subprocess.run([sys.executable, '-c', \"print('from a child')\"])",
    "print('  spaces either side  ')",
    "print('caf\\u00e9 \\u2013 accents and a dash')",
]


@pytest.mark.parametrize("code", PROBES)
def test_a_probe_in_a_look_answers_as_it_would_alone(code):
    alone = U._probe(code)
    with U._one_interpreter():
        U._probe("print('an earlier probe')")
        assert U._probe(code) == alone


def test_a_probe_that_kills_its_interpreter_runs_alone_and_the_next_is_still_answered():
    code = "print('said', flush=True); import os; os._exit(0)"
    alone = U._probe(code)
    assert alone == "said"
    with U._one_interpreter():
        assert U._probe(code) == alone
        assert U._probe("print(2)") == "2"


@pytest.mark.timing
def test_a_probe_out_of_time_says_nothing_and_is_never_run_twice(tmp_path, monkeypatch):
    monkeypatch.setattr(U, "PROBE_SECONDS", 1)
    ran = tmp_path / "ran"
    code = f"import time; open({str(ran)!r}, 'a').write('x'); time.sleep(10)"
    with U._one_interpreter():
        U._probe("print('warm')")
        began = time.monotonic()
        assert U._probe(code) == ""
        assert time.monotonic() - began < 8
        monkeypatch.setattr(U, "PROBE_SECONDS", 120)       # a fresh interpreter, unhurried
        assert U._probe("print('still here')") == "still here"
    assert ran.read_text() == "x"


# ------------------------------------------------------------------ the second look

def _row(uid):
    return (U.by_id(uid), "missing")


def test_the_list_is_not_worked_out_again_when_nothing_it_reads_changed(monkeypatch):
    calls = []
    monkeypatch.setattr(U, "pending", lambda: calls.append(1) or [])
    monkeypatch.setattr(U, "_looked_at", lambda: ("head", [], None))
    first = [_row("required")]
    assert U._look_again(first, ("head", [], None), set(), False) == first
    assert calls == []


def test_the_list_is_worked_out_again_after_an_instant_upgrade_even_with_nothing_committed(
        monkeypatch):
    # One writes only files git ignores (a process folder's job_posting.md): the commit, the
    # checkout's changed files and the record all look the same, and it is done all the same.
    monkeypatch.setattr(U, "pending", lambda: [])
    monkeypatch.setattr(U, "_looked_at", lambda: ("head", [], None))
    instant = U.by_id("process-postings")
    assert instant.cost == "instant" and U._instant_due([(instant, "missing")])
    assert U._look_again([(instant, "missing")], ("head", [], None), set(), True) == []


@pytest.mark.parametrize("now", [("a later commit", [], None),
                                 ("head", ["profile/learned.json"], None),
                                 ("head", [], '{"failures": []}')])
def test_the_list_is_worked_out_again_when_something_it_reads_changed(monkeypatch, now):
    again = [_row("boards")]
    monkeypatch.setattr(U, "pending", lambda: again)
    monkeypatch.setattr(U, "_looked_at", lambda: now)
    assert U._look_again([_row("required")], ("head", [], None), set(), False) == again


@pytest.mark.parametrize("changed", [False, True])
def test_what_another_chat_landed_is_never_listed_again(monkeypatch, changed):
    rows = [_row("required"), _row("boards")]
    monkeypatch.setattr(U, "pending", lambda: rows)
    monkeypatch.setattr(U, "_looked_at", lambda: ("later" if changed else "head", [], None))
    got = U._look_again(rows, ("head", [], None), {"boards"}, False)
    assert [u.id for u, _ in got] == ["required"]
