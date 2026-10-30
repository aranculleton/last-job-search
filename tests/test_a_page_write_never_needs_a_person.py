"""A write to the page never stops for a person because of how its files are named.

Every batch a chat sends names a file for each record's body. They were named after the
record ("part~jobs~1.json"), and Claude Code reads a name with "~" and a digit as a short
Windows name that can stand for a different file: each such write was a safety check only a
person could allow, one at a time, and no setting or earlier yes covered it. A new chat on
4.4.0 asked about 50 times (2026-10-30, its prompts read back from the chat: every one a
view batch, "safetyCheck", not approvable by the classifier, no "always allow").
"""
from __future__ import annotations

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import page_db  # noqa: E402

# Claude Code's own test for a short Windows name in a path segment.
SHORT_NAME = re.compile(r"~\d")


def _batch(tmp_path):
    w = page_db.Writes(str(tmp_path / "out"))
    w.add("set", "screen", "part~jobs~1", {"rows": [1]}, if_version=3)
    w.add("set", "screen", "list~applications~2", {"rows": []})
    w.add("set", "talk/thread~1/messages", "m~9", {"text": "hi"})
    w.add("update", "work", "republish~v7", {"status": "done"}, if_version=1)
    w.add("set", "addr", "part~1", {"x": 1})
    w.add("set", "meta", "a:b~2", {"y": 2})
    w.add("delete", "screen", "part~jobs~3", if_version=1)
    return w, w.save("view")


def test_no_file_a_batch_names_looks_like_a_short_windows_name(tmp_path):
    w, paths = _batch(tmp_path)
    named = [e for e in w.entries if e.get("file_path")]
    assert len(named) == 6
    for e in named:
        rel = os.path.relpath(e["file_path"], str(tmp_path))
        for seg in rel.split(os.sep):
            assert not SHORT_NAME.search(seg) and "~" not in seg and ":" not in seg, rel
    for p in paths:
        assert not SHORT_NAME.search(os.path.basename(p))


def test_each_entry_still_names_its_record_and_its_file_holds_the_body(tmp_path):
    w, paths = _batch(tmp_path)
    (only,) = paths
    with open(only, encoding="utf-8") as fh:
        sent = json.load(fh)
    got = {(e["collection"], e["doc_id"]): e for e in sent}
    assert ("screen", "part~jobs~1") in got and ("talk/thread~1/messages", "m~9") in got
    with open(got[("screen", "part~jobs~1")]["file_path"], encoding="utf-8") as fh:
        body = json.load(fh)
    assert body["rows"] == [1] and body[page_db.VERSION_FIELD] == 4
    assert got[("screen", "part~jobs~1")]["if_version"] == 3
    assert "file_path" not in got[("screen", "part~jobs~3")]


def test_two_records_never_share_a_file(tmp_path):
    w, _ = _batch(tmp_path)
    files = [e["file_path"] for e in w.entries if e.get("file_path")]
    assert len(set(files)) == len(files)
    assert page_db.body_path("o", "screen", "a~1") != page_db.body_path("o", "screen", "a@1".replace("@", "_"))
