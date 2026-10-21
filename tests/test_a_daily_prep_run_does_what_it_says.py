"""The daily call-prep run says what it would write, and reads what the answers rest on.

From the sync audit, 2026-10-21, on a copy of a real repo after an update:
- `prep.py --stale-only --dry-run` said 34 documents would be written; the real run wrote
  none ("34 already current"), because a document that would change only its date is left
  as it is. Left with its old stamp, each one was found stale and rendered again on every
  daily run.
- What an employer was told about where the person lives (tools/told.py), and the
  person's stock answers, are what a prep's answers are checked against, but neither was in
  what makes a prep stale: recording either left a live prep saying the old thing.

The people are invented, against the example profile.
"""
from __future__ import annotations

import csv
import os
import re
import shutil
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import person  # noqa: E402
import prep  # noqa: E402
import schema  # noqa: E402
import told  # noqa: E402

TODAY = "2026-10-15"
LIVE = {"contact_id": "kestrel_haldane", "name": "Corwin Haldane", "company": "Kestrel Mutual",
        "title": "Head of Data", "status": "in_conversation"}


def _book(tmp_path):
    contacts, threads = tmp_path / "c.csv", tmp_path / "t.csv"
    for path, rows, cols in ((contacts, [LIVE], schema.CONTACT_COLUMNS),
                             (threads, [], schema.THREAD_COLUMNS)):
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            w.writerows({c: r.get(c, "") for c in cols} for r in rows)
    return ["--contacts", str(contacts), "--threads", str(threads),
            "--tracker", str(tmp_path / "none.csv"), "--root", str(tmp_path), "--today", TODAY]


def _doc(tmp_path):
    return tmp_path / "documents" / "network" / "kestrel_haldane" / "prep.md"


@pytest.fixture
def own_profile(tmp_path, monkeypatch):
    prof = tmp_path / "profile"
    shutil.copytree(os.path.join(ROOT, "profile.example"), prof,
                    ignore=shutil.ignore_patterns("__pycache__", "state"))
    monkeypatch.setenv(person.ENV, str(prof))
    person.reset()
    yield prof
    person.reset()


def test_a_dry_run_counts_only_what_the_real_run_writes(tmp_path, capsys):
    args = _book(tmp_path)
    assert prep.main(["--all", *args]) == 0
    doc = _doc(tmp_path)
    # An older prep's stamp on a body that is current: the real run changes no word of it.
    older = re.sub(r"<!-- prep v\d+", "<!-- prep v1", doc.read_text(encoding="utf-8"))
    doc.write_text(older, encoding="utf-8")
    assert prep.stale(str(doc))
    capsys.readouterr()
    assert prep.main(["--stale-only", "--dry-run", *args]) == 0
    out = capsys.readouterr().out
    assert "0 prep documents would be written" in out and "1 already current" in out
    assert "would rewrite" not in out and doc.read_text(encoding="utf-8") == older
    assert prep.main(["--stale-only", *args]) == 0
    assert "0 prep documents written" in capsys.readouterr().out
    # Its stamp is brought up to date, so tomorrow's run finds nothing to render.
    assert not prep.stale(str(doc), LIVE, (), {}, {}, TODAY)
    assert prep.main(["--stale-only", "--dry-run", *args]) == 0
    assert "0 prep documents would be written (prep v%d); nothing written" \
        % prep.generator_version() in capsys.readouterr().out


def test_a_place_told_or_a_stock_answer_changed_makes_a_live_prep_stale(tmp_path, own_profile):
    _book(tmp_path)
    path = prep.write_prep(LIVE, today=TODAY, root=str(tmp_path))
    assert not prep.stale(path, LIVE, (), {}, {}, TODAY)
    told.record("Kestrel Mutual", "Leeds")
    assert prep.stale(path, LIVE, (), {}, {}, TODAY)
    path = prep.write_prep(LIVE, today=TODAY, root=str(tmp_path))
    assert not prep.stale(path, LIVE, (), {}, {}, TODAY)
    with open(own_profile / "07-interview-prep.md", "a", encoding="utf-8") as fh:
        fh.write('\n### "Where do you see yourself in five years?"\n> Leading a planning '
                 "team that owns its forecast end to end.\n")
    assert prep.stale(path, LIVE, (), {}, {}, TODAY)
