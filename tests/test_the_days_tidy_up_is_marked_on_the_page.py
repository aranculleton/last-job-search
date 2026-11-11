"""The day's tidy-up is marked on the page, so a chat in a fresh container does not run it again.

Whether the day's tidy-up had run was kept only in the git folder of the container that ran
it, so every chat starting in a fresh container ran the whole tidy-up again, its listings typed
back by hand, though another chat had done it that day (second audit D5 and E4). `tidy.py done`
now also writes the day onto the page (meta/tidy), and `due` reads it there. Invented page.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import tidy  # noqa: E402

DAY = "2026-11-10"


def test_a_fresh_container_reads_the_days_mark_from_the_page(tmp_path, monkeypatch):
    monkeypatch.setattr(tidy, "_git_dir", lambda: str(tmp_path))
    db = {"meta": {}, "work": {}}
    assert tidy.due(DAY, db=db) is True
    db["meta"]["tidy"] = {"data": {"checked": DAY, "at": DAY + "T08:30:00Z",
                                   "sweep": tidy.SWEEP}, "version": 2}
    assert tidy.due(DAY, db=db) is False
    assert tidy.due("2026-11-11", db=db) is True


def test_done_writes_the_days_mark_onto_the_page(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(tidy, "_git_dir", lambda: str(tmp_path / "git"))
    (tmp_path / "git").mkdir()
    dump = tmp_path / "dump"
    (dump / "meta").mkdir(parents=True)
    profile = tmp_path / "profile"
    profile.mkdir()
    monkeypatch.setattr(tidy, "_record_path", lambda: str(profile / "tidy.json"))
    assert tidy.main(["done", "--today", DAY, "--dump", str(dump)]) == 0
    out = capsys.readouterr().out
    batch = next(ln.strip() for ln in out.splitlines() if ln.strip().endswith(".json"))
    entries = json.load(open(batch, encoding="utf-8"))
    mark = next(e for e in entries if e["collection"] == "meta" and e["doc_id"] == "tidy")
    body = json.load(open(mark["file_path"], encoding="utf-8")) if mark.get("file_path") \
        else mark.get("data")
    assert body["checked"] == DAY and body["sweep"] == tidy.SWEEP
