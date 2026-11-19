"""A round told to keep its summaries elsewhere keeps its record of what it searched with there.

Each round keeps what it searched with (the places, the kinds of employer out, the employers
turned down), so the next can say what changed since (issue 327). It kept it under the
person's own documents/rounds/searched/ whatever `--summary-dir` said, so a test's round in a
folder of its own left a file in the person's copy, which a person's own check that a round
writing elsewhere cannot touch their tree caught in the 4.17.0 rehearsal. Kept beside the
round's summaries, it follows them: the person's own documents/rounds for a real round, the
test's own folder for a test's. Invented postings (tests/round_fixture.py).
"""
from __future__ import annotations

import json
import os
import shutil
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import round_fixture as F  # noqa: E402


@pytest.fixture(autouse=True)
def _rulings_hold(monkeypatch):
    monkeypatch.setenv("LJS_RESCREEN", "off")


@pytest.mark.skipif(not shutil.which("node"), reason="the stand-in detail CLI needs node")
def test_a_round_kept_elsewhere_leaves_nothing_in_the_persons_rounds(tmp_path):
    work = str(tmp_path)
    r = F.free_stages(F.KEPT, os.path.join(work, "r1"), work)
    assert r.returncode in (0, 2), r.stdout[-2000:] + r.stderr[-2000:]
    mine = [os.path.join(root, f) for root, _d, files in os.walk(work) for f in files
            if f == "with.json" and os.sep + "searched" + os.sep in os.path.join(root, f)]
    kept = os.path.join(work, "summary", "searched", "with.json")
    assert mine == [kept], mine
    with open(kept, encoding="utf-8") as fh:
        got = json.load(fh)
    assert list(got) == ["r1"] and got["r1"]["with"]["places"], got
    assert "searching with:" in r.stdout and "since the last search: no record of one yet" in r.stdout, r.stdout[-1500:]
