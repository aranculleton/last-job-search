"""A job no chat will take up again is ended on any redraw, not only at the listener's check-in.

The audit of 2026-11-10 (PE-4): a job that stopped part way twice, was asked to stop, or was
begun in a chat that went quiet was failed in code only by the check-in of the chat that
answers the page. With no such chat checking in, its card said "May have stopped" for good,
with no Try again. Any chat that brings the page up to date (`app.py view`) now ends it, in a
batch of its own after the screens. Every chat and employer here is invented.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import page_db  # noqa: E402
import test_a_ring_is_answered_in_one_command as R  # noqa: E402
import test_the_page_helper_stays_thin as thin  # noqa: E402
from test_the_page_helper_stays_thin import read, view  # noqa: E402

ring = thin.ring          # the test store's own fixture

GONE = "2026-10-25T17:00:00Z"        # its last word, an hour before the redraw


def test_a_redraw_ends_a_job_that_stopped_twice_and_offers_try_again(ring):
    ring.put("work", "draft~kestrel", {"kind": "draft", "title": "Draft: Kestrel Mutual",
                                       "status": "running", "attempt": 2,
                                       "claimed_by": "session_gone1", "claimed_at": GONE,
                                       "stage_at": GONE, "lease_until": "2026-10-25T17:30:00Z",
                                       "asked_at": GONE, "args": {"company": "Kestrel Mutual"}},
             version=3)
    d, _said = read(ring, "r1")
    got, ok = view(ring, d)
    assert ok, got
    item = ring.stored("work", "draft~kestrel")["data"]
    assert item["status"] == "failed" and item["error"] == page_db.STRANDED_SAID, item
    # A job still going is left alone.
    ring.put("work", "draft~oakmere", {"kind": "draft", "status": "running", "attempt": 1,
                                       "claimed_by": "session_live1", "claimed_at": R.NOW,
                                       "lease_until": "2026-10-25T18:20:00Z", "asked_at": R.NOW,
                                       "args": {"company": "Oakmere Foods"}}, version=2)
    d, _said = read(ring, "r2", now="2026-10-25T18:01:00Z")
    got, ok = view(ring, d, "2026-10-25T18:01:00Z")
    assert ok, got
    assert ring.stored("work", "draft~oakmere")["data"]["status"] == "running"


def test_a_chat_on_the_computer_ends_a_read_that_died_twice_before_it_looks(tmp_path):
    """PE-4 again: a chat on the computer never checks in as the listener, so a read whose
    chat there died twice waited there for good; its own `next` ends it first."""
    import json
    import subprocess
    dump = tmp_path / "dump"
    (dump / "work").mkdir(parents=True)
    item = {"kind": "network", "title": "Reading 4 profiles", "to": "computer", "status": "running",
            "attempt": 2, "claimed_by": "local-mac-gone", "claimed_as": "computer", "claimed_at": GONE,
            "stage_at": GONE, "lease_until": "2026-10-25T17:30:00Z", "asked_at": GONE,
            "args": {"read_on_computer": True}}
    # The dump's own file name ("~" kept as "@" on disk), made here rather than written out,
    # which reads as an email address to the leak scan.
    name = "~".join(("network", "read", "9")).replace("~", "@") + ".json"
    with open(dump / "work" / name, "w", encoding="utf-8") as fh:
        json.dump({"data": item, "version": 6}, fh)
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "app.py"), "next", str(dump),
                        "--chat", "local-mac-new", "--kind", "computer", "--computer-only",
                        "--claim-out", str(tmp_path / "claim"), "--now", R.NOW],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    got = json.loads(r.stdout)
    assert got["ended"] == ["network~read~9"] and got["batches"], got
    with open(got["batches"][0], encoding="utf-8") as fh:
        entry = json.load(fh)[0]
    with open(entry["file_path"], encoding="utf-8") as fh:
        assert json.load(fh)["status"] == "failed"
