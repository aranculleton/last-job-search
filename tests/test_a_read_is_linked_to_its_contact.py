"""A profile read is linked to the contact it is about.

The 2026-11-10 audit (NW-28): reads were saved with no contact row (an interviewer read for a
prep), or under a folder that matched no row (a read kept as `<employer>_<surname>` for the
contact `<surname>`, whose employer was blank). Now a read fills a blank employer on its
contact from what it read, and `reading.py unlinked` names every reading no contact row
holds, with the row it may belong to. Invented people and employers only.
"""
from __future__ import annotations

import datetime
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import reading  # noqa: E402
import state  # noqa: E402

TODAY = datetime.date(2026, 11, 10)
PAGE = "\n".join([
    "Ines Halvorsen", "Head of Risk Analytics at Ashgrove Ledger", "Toronto, Ontario, Canada",
    "Contact info", "Connect", "Experience", "Head of Risk Analytics",
    "Ashgrove Ledger · Full-time", "Jan 2022 - Present", "Toronto, Ontario, Canada"])


@pytest.fixture
def book(tmp_path, monkeypatch):
    monkeypatch.setattr(reading.person, "state", lambda *p: str(tmp_path.joinpath(*p)))
    monkeypatch.setattr(reading.person, "today", lambda: TODAY)
    monkeypatch.setenv("LJS_LEDGER", str(tmp_path / "ledger"))
    path = str(tmp_path / "contacts.csv")
    monkeypatch.setattr(state, "CONTACTS_CSV", path)
    real_load, real_save = state.load_contacts, state.save_contacts
    monkeypatch.setattr(state, "load_contacts", lambda p=path: real_load(p))
    monkeypatch.setattr(state, "save_contacts", lambda rows, p=path: real_save(rows, p))
    state.save_contacts([{"contact_id": "halvorsen", "name": "Ines Halvorsen", "company": "",
                          "status": "not_contacted", "location": ""}])
    return tmp_path


def test_a_read_fills_its_contacts_blank_employer(book):
    page = book / "p.txt"
    page.write_text(PAGE, encoding="utf-8")
    assert reading.main(["read", "halvorsen", str(page), "--source", "paste"]) == 0
    row = next(c for c in state.load_contacts() if c["contact_id"] == "halvorsen")
    assert row["company"] == "Ashgrove Ledger"
    assert row.get("company_key")


def test_a_reading_no_contact_holds_is_named_with_the_row_it_may_be(book, capsys):
    reading.save("ashgrove_halvorsen", {"name": "Ines Halvorsen", "company": "Ashgrove Ledger",
                                        "read_on": "2026-11-09", "sources": [], "items": []})
    reading.save("quillfeather_okafor", {"name": "Dayo Okafor", "company": "Quillfeather Bank",
                                         "read_on": "2026-11-09", "sources": [], "items": []})
    got = reading.unlinked(state.load_contacts())
    assert [(u["id"], u["maybe"]) for u in got] == [
        ("ashgrove_halvorsen", "halvorsen"), ("quillfeather_okafor", "")]
    assert reading.main(["unlinked"]) == 1
    out = capsys.readouterr().out
    assert "ashgrove_halvorsen" in out and "halvorsen" in out and "quillfeather_okafor" in out
