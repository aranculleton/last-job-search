"""A start that takes an update reads the page's screens once, not twice.

A helper chat in the maintainer's copy, 2026-11-10 (H-6): one start read the page in full
twice, about 4 MB, once after the update landed and again after the improvements step. Both
steps typed a whole read of the page's screens and addresses (`screen`, `addr`), past the copy
this checkout keeps of the page (tools/page_reads.py). Both now read through `app.py reads
--for-view`: whole only for the first read of the day, and after that only what changed, the
screens laid from the copy kept since this chat drew them. The store is the test folder that
keeps the real one's rules (tests/test_the_page_helper_stays_thin.py). Every person, employer
and page here is invented.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import app_listen  # noqa: E402
import test_a_ring_is_answered_in_one_command as R  # noqa: E402,F401  (its fixtures)
import test_the_page_helper_stays_thin as thin  # noqa: E402
from test_the_page_helper_stays_thin import read, used_page, view  # noqa: E402

ring = thin.ring          # the test store's own fixture

LATER = "2026-10-25T18:05:00Z"
BIG = ("screen", "addr")


def read_kept(r, name, *args, now=R.NOW):
    """`app.py reads`, its queries, and the step it names after them: the read's versions
    kept (app.py versions with the lines it printed), as a chat does."""
    import test_the_page_pipeline_survives_two_finishes_and_an_answer as P
    out = os.path.join(r.root, name)
    said = r.run("reads", out, "--now", now, *args, LJS_PAGE_MIRROR=r.mirror)
    listing = []
    for line in said.splitlines()[1:]:
        if line.startswith("{"):
            listing += P.query(r, out, json.loads(line))
    code, got = P.app_in(r, "versions", out, text="\n".join(listing))
    assert code == 0 or not listing, got
    return out, said


def _bytes(folder: str, colls=BIG) -> int:
    n = 0
    for c in colls:
        d = os.path.join(folder, c)
        for f in os.listdir(d) if os.path.isdir(d) else ():
            n += os.path.getsize(os.path.join(d, f))
    return n


def test_both_steps_read_through_the_copy_kept_of_the_page(monkeypatch):
    import app_setup
    monkeypatch.setattr(app_setup, "page_record", lambda: {"url": "https://claude.ai/artifact/p-1"})
    monkeypatch.setattr(app_setup, "set_up", lambda: True)
    monkeypatch.setattr(app_setup, "_page_current", lambda: True)
    steps = app_listen.after_update(landed=True, chat="session_x")
    read_step = next(s for s in steps if s.startswith("1. "))
    assert "app.py reads" in read_step and "--for-view" in read_step, read_step
    assert "screen" not in read_step and "limit 1000" not in read_step, read_step
    assert "app.py reads" in app_listen.READ_STEP and "--for-view" in app_listen.READ_STEP


def test_the_second_read_of_a_start_reads_no_screen(ring):
    used_page(ring)
    # The update's read: the first of the day, whole.
    first, said = read_kept(ring, "r1", "--for-view")
    assert "a whole read" in said and "go on with the step that asked" in said, said
    assert "app.py wake" not in said, said
    got, ok = view(ring, first)
    assert ok, got
    # The page's screens as drawn now: the size a second whole read would take again.
    page = _bytes(ring.db)
    assert page > 0
    # The start's own read, after the improvements step: what changed, and no screen at all.
    second, said = read_kept(ring, "r2", "--for-view", now=LATER)
    assert "what changed since" in said, said
    queries = [json.loads(ln) for ln in said.splitlines() if ln.startswith("{")]
    assert not [q for q in queries if q["collection"] in BIG], queries
    assert _bytes(second) == 0
    # Laid from the copy kept, the folder holds the screens all the same, and view draws.
    got, ok = view(ring, second, LATER)
    # Nothing to say first: the screens' own numbers came with them from the copy kept.
    assert ok and not got.get("for_claude"), got
    assert _bytes(second) >= page * 0.5


def test_the_read_named_for_a_wake_still_says_wake(ring):
    _, said = read(ring, "r1")
    assert "then python3 tools/app.py wake with the same folder" in said, said



def test_the_start_has_no_dead_page_check_left():
    """The second audit, D4: `app.data_current` and `start --dump` were never used (no step
    passed a read to the start), so a page already current was read and drawn again all the
    same. The start's page step reads through the copy kept instead; the dead check is gone."""
    import inspect
    import app
    import app_setup
    assert not hasattr(app, "data_current")
    assert "data_current" not in inspect.signature(app_setup.start).parameters
