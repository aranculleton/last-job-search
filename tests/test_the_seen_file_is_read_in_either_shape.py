"""The seen file is read whether or not it has its top-level "seen" key.

A person's copy held the bare map of postings, {url: entry}, with no "seen" key:
`lookup_score.py` crashed with KeyError 'seen', so /apply could not reuse a score it had
(2026-10-22), and the throttle and `exclude.py` read the file as empty, so everything it
had ruled out came back. All three read it through `throttle.as_seen` now.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import exclude  # noqa: E402
import lookup_score  # noqa: E402
import throttle  # noqa: E402

URL = "https://careers.example.com/jobs/42"
ENTRY = {"company": "Kestrel Mutual", "title": "Data Analyst", "status": "excluded",
         "exclusion_reason": "language: French required"}


def _write(tmp_path, data):
    path = tmp_path / "seen_jobs.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_both_shapes_read_the_same(tmp_path, monkeypatch):
    for data in ({"seen": {URL: ENTRY}}, {URL: ENTRY}):
        path = _write(tmp_path, data)
        assert throttle.load_seen(str(path))["seen"] == {URL: ENTRY}
        monkeypatch.setattr(lookup_score, "SEEN", str(path))
        assert lookup_score.load_seen() == {URL: ENTRY}
        assert exclude._load(str(path))["seen"] == {URL: ENTRY}


def test_a_missing_or_odd_file_is_empty_not_a_crash(tmp_path, monkeypatch):
    monkeypatch.setattr(lookup_score, "SEEN", str(tmp_path / "none.json"))
    assert lookup_score.load_seen() == {}
    assert throttle.as_seen([]) == {"seen": {}}
    assert throttle.as_seen({"seen": None, "note": "x"}) == {"seen": {}, "note": "x"}
    assert throttle.as_seen({}) == {"seen": {}}


def test_a_ruling_in_the_bare_shape_is_saved_back_in_the_one_shape(tmp_path):
    path = _write(tmp_path, {URL: ENTRY})
    data = exclude._load(str(path))
    exclude._save(data, str(path))
    assert json.loads(path.read_text(encoding="utf-8")) == {"seen": {URL: ENTRY}}
