"""A section and its parts are written in one batch, and the page's `meta/now` goes last.

The audit of 2026-11-10 (PE-9): `Writes.save` cut a page update into batches by size alone, so
the parts of People went partly in a batch the store refused and partly, with its head and
`meta/now`, in one that landed, and the page mixed two versions of People. Now a section that
fits in one batch is never cut, a new batch starting before it instead, and `meta/now` is
written last of all.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import page_db  # noqa: E402

KB = 1024


def _batches(paths):
    out = []
    for p in paths:
        with open(p, encoding="utf-8") as fh:
            out.append([(e["collection"], e["doc_id"]) for e in json.load(fh)])
    return out


def test_a_section_bigger_than_half_a_batch_is_kept_whole_and_meta_now_is_last(tmp_path):
    w = page_db.Writes(str(tmp_path))
    w.add("set", "meta", "current", {"rev": 7})
    for name in ("jobs", "drafts", "brief"):
        w.add("set", "view", name, {"data": "a" * (150 * KB)})
    for n in range(1, 5):
        w.add("set", "view", page_db.part_id("people", n), {"of": "people", "part": n,
                                                            "text": "b" * (120 * KB)})
    w.add("set", "view", "people", {"in_parts": 4})
    got = _batches(w.save("view"))
    people = [i for i, b in enumerate(got) for c, d in b if d == "people" or d.startswith("part~people~")]
    assert len(set(people)) == 1, got
    assert got[-1][-1] == ("meta", "now"), got
    # Each batch is still within the tool's limits.
    for b in got:
        assert len(b) <= page_db.BATCH_MAX


def test_a_section_bigger_than_a_batch_is_cut_parts_first_and_its_head_last(tmp_path):
    w = page_db.Writes(str(tmp_path))
    for n in range(1, 9):
        w.add("set", "view", page_db.part_id("people", n), {"of": "people", "part": n,
                                                            "text": "c" * (200 * KB)})
    w.add("set", "view", "people", {"in_parts": 8})
    got = _batches(w.save("view"))
    flat = [d for b in got for _c, d in b]
    assert len(got) > 1 and flat[-1] == "people", got
    assert flat[:-1] == [page_db.part_id("people", n) for n in range(1, 9)]


def test_a_refused_batch_stops_the_ones_after_it_as_view_and_the_skill_say():
    """The review of 2026-11-11 (PE-9): nothing told a chat to stop sending once an earlier
    batch was refused, and the page then mixed two versions of a section."""
    import app
    assert "send none after it" in app.SEND_IN_ORDER
    with open(os.path.join(ROOT, ".claude", "skills", "app", "SKILL.md"), encoding="utf-8") as fh:
        skill = " ".join(fh.read().split())
    assert "once one is refused, send none after it" in skill
    src = open(os.path.join(ROOT, "tools", "app.py"), encoding="utf-8").read()
    assert '{"send": SEND_IN_ORDER} if len(batches) > 1' in src
