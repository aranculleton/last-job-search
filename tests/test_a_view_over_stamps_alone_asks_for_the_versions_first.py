"""A page update pinned to numbers no read confirmed says so first, with the step for next time.

The audit of 2026-11-10 (PE-2): a chat started outside the copy's folder runs no hook, so its
read kept no versions, its records were pinned by their writers' `_v` stamps (a screen pinned to
4 where the store had 56), and the whole batch was refused. `app.py view` now names, first,
the records it pins by stamp alone, how a refusal is put right, and the step that keeps the
store's own numbers after every read; it never refuses, so an old hook and the test store still
work. A command cannot read the store's versions itself: only the chat's read lists them. Every person and
page here is invented.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import test_the_page_pipeline_survives_two_finishes_and_an_answer as P  # noqa: E402
import test_a_ring_is_answered_in_one_command as R  # noqa: E402

ring = P.ring          # the pipeline's test store, which prints a read's lines as ArtifactData does


def _view(r, d):
    return json.loads(r.run("view", os.path.join(d, "v"), "--dump", d, "--chat", R.CHAT,
                            "--now", P.NOW, LJS_PAGE_MIRROR=r.mirror, ok=(0, 2)))


def test_stamps_alone_are_said_first_with_the_step_and_kept_versions_are_not(ring):
    first = P.read(ring, "r0")
    P.T.wake(ring, first)
    got = _view(ring, first)
    assert all(P.land(ring, got["batches"])), got
    # A read whose versions were never kept: the update still goes, and says first what to do.
    d = os.path.join(ring.root, "r1")
    said = ring.run("reads", d, "--full", "--now", P.NOW, LJS_PAGE_MIRROR=ring.mirror)
    listing = []
    for line in said.splitlines()[1:]:
        if line.startswith("{"):
            listing += P.query(ring, d, json.loads(line))
    got = _view(ring, d)
    assert got["batches"], got
    head = (got.get("for_claude") or [""])[0]
    assert "known here only by the number their last writer stamped" in head, got
    assert "app.py versions" in head, head
    # A read whose versions were kept (the step `reads` names): nothing said.
    kept = P.read(ring, "r2", "--full")
    got = _view(ring, kept)
    assert not any("last writer stamped" in x for x in got.get("for_claude") or []), got


def test_a_second_read_laid_from_the_copy_kept_is_not_taken_for_stamps(ring):
    """The review of 2026-11-11: with every read's versions kept, a second read the same day laid
    the screens from the copy this checkout keeps, which carried their stamps alone, and the
    update said they were known only by stamp. The copy keeps the known numbers too."""
    first = P.read(ring, "r0")
    P.T.wake(ring, first)
    got = _view(ring, first)
    assert all(P.land(ring, got["batches"])), got
    ring.act("job.keep", "r9-3")                  # a tap the same day: Jobs changes
    second = P.read(ring, "r1", now="2026-10-25T18:05:00Z")
    P.T.wake(ring, second, now="2026-10-25T18:05:00Z")
    got = json.loads(ring.run("view", os.path.join(second, "v"), "--dump", second, "--chat", R.CHAT,
                              "--now", "2026-10-25T18:05:00Z", LJS_PAGE_MIRROR=ring.mirror, ok=(0, 2)))
    assert got["batches"], got
    assert not any("last writer stamped" in x for x in got.get("for_claude") or []), got
