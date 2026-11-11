"""The versions a read listed are kept in one index, never by rewriting every file it saved.

The second audit of 2026-11-10 (D15): after each read of the page, the app's hook rewrote every
file the read saved to add its version, about 4 MB and 600 files on each start. The versions
now go in one index beside them (`.versions.json`), which `page_db.load` reads; a file is
rewritten only where its own stamp says another number. Every record here is invented.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import page_db  # noqa: E402


def _save(dump, coll, name, fields):
    os.makedirs(os.path.join(dump, coll), exist_ok=True)
    path = os.path.join(dump, coll, name + ".json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(fields, fh)
    return path


def test_matching_stamps_are_indexed_not_rewritten_and_a_wrong_one_is_mended(tmp_path):
    dump = str(tmp_path / "d")
    big = "x" * 50_000
    paths = [_save(dump, "screen", f"jobs{n}", {"data": big, "_v": 7}) for n in range(6)]
    wrong = _save(dump, "work", "draft@1", {"status": "queued", "_v": 3})
    before = {p: os.stat(p).st_mtime_ns for p in paths}
    lines = "\n".join([f'- "jobs{n}"  50000 bytes  version 7  "{paths[n]}"' for n in range(6)] +
                      [f'- "draft~1"  40 bytes  version 5  "{wrong}"'])
    assert page_db.keep_listed(lines, dump) == 7
    # Not one of the big files was written again.
    assert {p: os.stat(p).st_mtime_ns for p in paths} == before
    assert page_db.listed_versions(dump)["screen/jobs0"] == 7
    db = page_db.load(dump)
    assert db["view"]["jobs0"]["version"] == 7
    assert page_db.version_known(dump, "screen/jobs0")
    # The one whose stamp was behind the store is mended in its file, so the copy this
    # checkout keeps of the page carries it too.
    assert db["work"]["draft~1"]["version"] == 5
    with open(wrong, encoding="utf-8") as fh:
        assert json.load(fh)[page_db.STORE_VERSION] == 5


def test_a_record_this_folder_moved_on_is_known_by_its_new_stamp_not_the_old_listing(tmp_path):
    dump = str(tmp_path / "d")
    p = _save(dump, "work", "draft@1", {"status": "queued", "_v": 4})
    page_db.keep_listed(f'- "draft~1"  40 bytes  version 4  "{p}"', dump)
    page_db._keep_dump(dump, "work", "draft~1", {"status": "claimed"}, 5)
    assert page_db.load(dump)["work"]["draft~1"]["version"] == 5
