"""A short list says who it left out and why, never drops anyone silently.

The 2026-11-10 audit (NW-12): `reading.py shortlist` skipped anyone already past a first
note or read on an earlier day (`_gone`) and threw the reason away, so a chat that asked for
ten names got eight with no word about the other two. Invented people only.
"""
from __future__ import annotations

import datetime
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import reading  # noqa: E402

TODAY = datetime.date(2026, 11, 10)


@pytest.fixture
def here(tmp_path, monkeypatch):
    monkeypatch.setattr(reading.person, "state", lambda *p: str(tmp_path.joinpath(*p)))
    monkeypatch.setattr(reading.person, "today", lambda: TODAY)
    import state
    monkeypatch.setattr(state, "load_contacts", lambda *a, **k: list(BOOK))
    return tmp_path


BOOK = [{"contact_id": "orla_vantongeren", "name": "Orla Vantongeren", "location": "Leeds",
         "company": "Kestrel Mutual", "status": "not_contacted"},
        {"contact_id": "bram_okonkwo", "name": "Bram Okonkwo", "location": "Leeds",
         "company": "Fernhill Freight", "status": "awaiting_reply"}]


def test_someone_past_a_first_note_is_named_with_the_reason(here):
    got = reading.shortlist(["orla_vantongeren", "bram_okonkwo"], TODAY, contacts=BOOK)
    assert got["ids"] == ["orla_vantongeren"]
    assert got["gone"] == {"bram_okonkwo": "now awaiting_reply in the contact book"}


def test_the_command_prints_each_one_left_out(here, capsys):
    reading.main(["shortlist", "orla_vantongeren", "bram_okonkwo"])
    out = capsys.readouterr().out
    assert "not added: bram_okonkwo, now awaiting_reply in the contact book" in out
