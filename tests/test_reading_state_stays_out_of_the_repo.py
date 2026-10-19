"""What changes on every profile read stays out of the person's repo.

The stop, the day's list, the list-page reads and the sign-in were kept in
documents/network. A persistence step that force-added the folder committed them, and
from then on every read left the repo dirty: the sync refused to run, and with it the
day's update check and a read queued behind it. Invented people only.
"""
from __future__ import annotations

import datetime
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import pace  # noqa: E402
import reading  # noqa: E402


@pytest.fixture
def here(tmp_path, monkeypatch):
    state_dir = tmp_path / "repo"
    monkeypatch.setattr(reading.person, "state", lambda *p: str(state_dir.joinpath(*p)))
    monkeypatch.setenv("LJS_LEDGER", str(tmp_path / "ledger"))
    import state
    monkeypatch.setattr(state, "load_contacts", lambda *a, **k: [])
    return state_dir


def test_a_read_writes_nothing_into_the_repo(here):
    now = datetime.datetime(2026, 10, 20, 10, 0)
    reading.mark_signed_in(now)
    reading._write_stop("LinkedIn showed a check", now.date())
    reading._save_shortlist(["ana_rook"], now.date())
    reading.page_read("people", "https://example.com/p", now, people=9)
    net = here / "documents" / "network"
    assert not any(net.glob(".*")) if net.exists() else True
    assert reading.signed_in_today(now.date())
    assert reading.stopped(now.date()) == "LinkedIn showed a check"
    assert reading._shortlist_file(now.date()) == ["ana_rook"]
    assert [p["people"] for p in reading._pages()] == [9]


def test_an_older_copys_files_are_moved_into_the_ledger_and_removed(here):
    net = here / "documents" / "network"
    net.mkdir(parents=True)
    (net / ".shortlist.json").write_text(json.dumps({"date": "2026-10-20", "ids": ["bo_venn"]}))
    (net / ".page_reads.json").write_text(json.dumps({"reads": [
        {"kind": "invitations", "url": "u", "at": "2026-10-20T09:00:00", "people": 10}]}))
    (net / ".signed_in.json").write_text(json.dumps({"date": "2026-10-20"}))
    moved = reading.move_runtime()
    assert sorted(moved) == sorted(["documents/network/.shortlist.json",
                                    "documents/network/.page_reads.json",
                                    "documents/network/.signed_in.json"])
    assert not any(net.glob(".*"))
    assert reading._shortlist_file(datetime.date(2026, 10, 20)) == ["bo_venn"]
    assert reading.signed_in_today(datetime.date(2026, 10, 20))
    assert pace.load()["pages"][0]["people"] == 10
    assert reading.move_runtime() == []


def test_a_read_waiting_past_midnight_says_today_needs_its_own_list(here, monkeypatch, capsys):
    today = datetime.date.today()
    reading._save_shortlist(["ana_rook", "bo_venn"], today - datetime.timedelta(days=1))
    monkeypatch.setattr(reading, "next_up", lambda contacts=None: None)
    import argparse
    rc = reading._cli_next(argparse.Namespace(wait=False, timeout=1, mode="card"))
    out = capsys.readouterr().out
    assert rc == reading.EXIT["new_day"]
    assert "new day" in out and "reading.py shortlist ana_rook bo_venn" in out
