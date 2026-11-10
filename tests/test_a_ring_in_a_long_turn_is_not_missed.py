"""A ring that comes while the chat answering the page is in a long turn is not missed.

A job sat at "Starting in a moment" for over a minute until the person asked in a chat
(2026-11-10): the chat that answers the page was alive (its heartbeat fresh) and busy. Whether
a comment sent to Claude mid-turn is delivered after the turn or lost is not documented, so a
turn that ran past app_listen.RING_LOOK_S since its read ends with one more look at the
page's work, and `app_listen.py waiting` says whether anything waits.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import app_listen  # noqa: E402


def _dump(tmp_path, work: dict, age_s: float):
    d = tmp_path / "D"
    (d / "work").mkdir(parents=True)
    for doc_id, data in work.items():
        p = d / "work" / f"{doc_id}.json"
        p.write_text(json.dumps({"data": data, "version": 1}), encoding="utf-8")
        then = time.time() - age_s
        os.utime(p, (then, then))
    return str(d)


def test_a_long_turn_ends_with_one_more_look_and_a_short_one_does_not(tmp_path):
    long_turn = _dump(tmp_path, {"draft-1": {"status": "done"}}, age_s=300)
    line = app_listen.rings_meanwhile(long_turn, "https://claude.ai/artifact/x")
    assert "read the page's work and holds again" in line and "app_listen.py waiting" in line
    assert "https://claude.ai/artifact/x" in line
    assert app_listen.rings_meanwhile(long_turn, "u", now=os.path.getmtime(
        os.path.join(long_turn, "work", "draft-1.json")) + 10) == ""
    assert app_listen.rings_meanwhile(str(tmp_path / "never-read"), "u") == ""


def test_waiting_says_whether_work_was_asked_for_meanwhile(tmp_path):
    queued = _dump(tmp_path, {"network-2": {"status": "queued",
                                            "asked_at": "2026-11-10T20:01:00Z"}}, age_s=0)
    cmd = [sys.executable, os.path.join(ROOT, "tools", "app_listen.py"), "waiting", queued]
    out = subprocess.run(cmd, capture_output=True, encoding="utf-8", check=True).stdout
    assert out.startswith("waiting: work waits since 2026-11-10T20:01:00Z"), out
    os.makedirs(tmp_path / "E" / "work")
    (tmp_path / "E" / "work" / "network-2.json").write_text(
        json.dumps({"data": {"status": "running"}, "version": 2}), encoding="utf-8")
    cmd[-1] = str(tmp_path / "E")
    out = subprocess.run(cmd, capture_output=True, encoding="utf-8", check=True).stdout
    assert out.strip() == "waiting: nothing"
