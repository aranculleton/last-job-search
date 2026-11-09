"""A draft for someone already in conversation can be held back by command, and a hold never
writes over a draft already set aside.

A chat holding a follow-up "until she answers the email" found no command for it: `drop` is
for people never written to and `set --status` does not move the draft, so it called
`park_draft` from inline Python with a name of its own, because the default name would have
replaced a draft already parked there (2026-11-09). Every person here is invented.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tools" / "network")]

import state  # noqa: E402


@pytest.fixture
def book(tmp_path, monkeypatch):
    import csv_store
    import person
    d = tmp_path / "profile"
    shutil.copytree(os.path.join(ROOT, "profile.example"), d)
    monkeypatch.setenv(person.ENV, str(d))
    monkeypatch.setenv("LJS_STATE", str(tmp_path / "state"))
    (tmp_path / "state").mkdir()
    person._modules.clear()
    person._data.clear()
    contacts = str(tmp_path / "state" / "network_contacts.csv")
    csv_store.write_rows(contacts, [
        {"contact_id": "larkspur_venn", "name": "Bo Venn", "company": "Larkspur Retail",
         "status": "awaiting_reply", "next_action": "Follow up"}],
        ("contact_id", "name", "company", "status", "next_action"))
    import reading
    folder = os.path.dirname(reading.draft_path("larkspur_venn"))
    os.makedirs(folder, exist_ok=True)
    yield contacts, folder
    person._modules.clear()
    person._data.clear()


def _write(folder, name, text):
    with open(os.path.join(folder, name), "w", encoding="utf-8") as fh:
        fh.write(text)


def _read(folder, name):
    with open(os.path.join(folder, name), encoding="utf-8") as fh:
        return fh.read()


def test_hold_keeps_the_draft_and_never_writes_over_one_set_aside(book, capsys):
    contacts, folder = book
    _write(folder, state.PARKED, "an older note nobody will send")
    _write(folder, "draft.md", "the follow-up")
    assert state.main(["hold", "larkspur_venn", "--until", "she answers the email",
                       "--contacts", contacts, "--today", "2026-11-09"]) == 0
    assert "held until she answers the email" in capsys.readouterr().out
    assert not os.path.exists(os.path.join(folder, "draft.md"))
    assert _read(folder, state.PARKED) == "an older note nobody will send"
    assert _read(folder, state.HELD) == "the follow-up"
    row = state.load_contacts(contacts)[0]
    assert row["next_action"] == "Draft held until she answers the email"
    assert row["status"] == "awaiting_reply"
    assert "draft held 2026-11-09 until she answers the email" in row["notes"]

    # A second hold keeps both.
    _write(folder, "draft.md", "a newer follow-up")
    assert state.main(["hold", "larkspur_venn", "--contacts", contacts]) == 0
    assert _read(folder, state.HELD) == "the follow-up"
    assert _read(folder, "draft.held-2.md") == "a newer follow-up"

    # Release brings back the newest, and only where nothing is waiting.
    assert state.main(["hold", "larkspur_venn", "--release", "--contacts", contacts]) == 0
    assert _read(folder, "draft.md") == "a newer follow-up"
    assert state.main(["hold", "larkspur_venn", "--release", "--contacts", contacts]) == 1
    assert _read(folder, state.HELD) == "the follow-up"


def test_hold_with_nothing_waiting_says_so(book, capsys):
    contacts, _folder = book
    assert state.main(["hold", "larkspur_venn", "--contacts", contacts]) == 1
    assert "nothing to hold" in capsys.readouterr().out
    assert state.main(["hold", "nobody_here", "--contacts", contacts]) == 1
