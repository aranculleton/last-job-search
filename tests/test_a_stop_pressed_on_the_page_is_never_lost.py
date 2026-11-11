"""A Stop pressed on the page is never lost, nor a draft asked for there.

A tap's receipt and what the tap does to the page (a Stop on a piece of work, a draft
queued) go back in one batch. Where that batch never reached the page (the chat stopped part
way, or it was refused), the next wake found the tap applied already in this copy's ledger
and sent its receipt alone: the page said "Stopping at its next step" and the work ran on,
or said "Queued" for a draft nobody would ever make. What the tap wrote goes again with its
receipt now, pinned to what the page holds, and a receipt never goes in a batch apart from
what its tap wrote.

The store is the folder that keeps the real one's rules; its reads save each record's fields
as the last writer left them, the version only in the lines it prints, which the app's hook
keeps. Every person, employer, page and chat id is invented.
"""
from __future__ import annotations

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import pytest  # noqa: E402

import page_db  # noqa: E402
import test_a_ring_is_answered_in_one_command as R  # noqa: E402
import test_a_tap_reads_only_what_changed_and_every_save_lands as M  # noqa: E402
import test_the_page_helper_stays_thin as T  # noqa: E402

RUNNING = "draft~app-kestrel_mutual_claims_forecasting_analyst"
LATER = "2026-10-25T18:30:00Z"


@pytest.fixture
def ring(tmp_path, monkeypatch):
    yield from T.ring.__wrapped__(tmp_path, monkeypatch)


def unsent_wake(r, d, now):
    """A wake whose batches are never sent: the chat stopped part way."""
    said = r.run("wake", d, "--chat", R.CHAT, "--kind", "cloud", "--on", "Opus 5.5", "--now", now,
                 LJS_PAGE_MIRROR=r.mirror)
    assert R.sends(said), said
    return said


def wake(r, d, now):
    """The next wake, as the app skill runs it: a read it asks for made into the same folder,
    every batch sent, run again while it says to."""
    said = ""
    for _ in range(5):
        said = r.run("wake", d, "--chat", R.CHAT, "--kind", "cloud", "--on", "Opus 5.5",
                     "--now", now, LJS_PAGE_MIRROR=r.mirror)
        if "did not all reach it" in said:
            for q in re.findall(r"\{\"collection\".*?\]\]\}\}", said):
                M.query(r, d, json.loads(q))
            continue
        assert M.send(r, [p for p, _ in R.sends(said)]) == "landed", said
        if "run this again with the same folder" not in said:
            break
    return said


def test_a_stop_pressed_on_the_page_is_never_lost(ring):
    M.drawn_once(ring)
    # Work another chat is running (its last step written just after the page was drawn), and
    # the person's Stop on it.
    ring.put("work", RUNNING, {"kind": "draft", "status": "running", "title": "A draft",
                               "to": "cloud", "asked_at": M.DAY_BEFORE,
                               "claimed_by": "session_EXAMPLEJOB",
                               "lease_until": "2026-10-25T20:00:00Z",
                               "changed_at": "2026-10-25T18:00:30Z", "_v": 3}, version=3)
    ring.put("actions", "stop01", {"action": "work.stop", "item": RUNNING, "at": M.TAP_AT,
                                   "tab": "t1"})
    d, _, _ = M.read(ring, "r2", M.TAP_AT)
    unsent_wake(ring, d, M.TAP_AT)
    assert not ring.stored("work", RUNNING)["data"].get("stop_asked")
    # The next wake: the Stop goes to the page with its receipt, never the receipt alone.
    d, _, _ = M.read(ring, "r3", LATER)
    wake(ring, d, LATER)
    assert ring.stored("work", RUNNING)["data"].get("stop_asked") is True
    assert ring.stored("receipts", "stop01")["data"]["result"] == "ok"
    assert M.view(ring, d, LATER)[1] == "landed"


def test_a_draft_asked_for_on_the_page_is_never_lost(ring):
    M.drawn_once(ring)
    aid = ring.act("job.draft", "r9-3", value={"answers": {"already_applied": "no"}})
    d, _, _ = M.read(ring, "r2", M.TAP_AT)
    unsent_wake(ring, d, M.TAP_AT)
    queued = sorted(f for f in os.listdir(os.path.join(ring.db, "work")) if f.startswith("draft~"))
    d, _, _ = M.read(ring, "r3", LATER)
    wake(ring, d, LATER)
    assert ring.stored("receipts", aid)["data"]["result"] == "ok"
    now = sorted(f for f in os.listdir(os.path.join(ring.db, "work")) if f.startswith("draft~"))
    made = [f[:-5] for f in now if f not in queued]
    assert made and ring.stored("work", made[0])["data"]["status"] in ("queued", "claimed",
                                                                       "running"), now


def test_a_receipt_never_goes_in_a_batch_apart_from_what_its_tap_wrote(tmp_path):
    w = page_db.Writes(str(tmp_path))
    for n in range(page_db.BATCH_MAX - 1):
        w.add("set", "receipts", f"r{n:02d}", {"result": "ok"})
    w.unit = "stop01"
    w.add("update", "work", "draft~x", {"stop_asked": True}, if_version=3)
    w.add("set", "receipts", "stop01", {"result": "ok"})
    w.unit = None
    batches = [json.load(open(p, encoding="utf-8")) for p in w.save("batch")]
    holding = [i for i, b in enumerate(batches)
               for e in b if e["doc_id"] in ("draft~x", "stop01")]
    assert len(set(holding)) == 1, holding
    assert all(set(e) <= {"op", "collection", "doc_id", "file_path", "if_version"}
               for b in batches for e in b), "nothing of the app's own is sent to the page"
