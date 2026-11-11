"""A message log that cannot be read is said, never read as "nobody is waiting".

The per-employer limit counts the people at an employer waiting on a reply. When the message log
could not be read (a merge left markers in it, a file the computer would not open), it was read
as empty: nobody waiting, so every note at every employer went through (the audit of 2026-11-10,
NW-17). Now the limit refuses on a log it cannot read, and the short list and the save of first
notes say so in plain words. Every person and employer is invented.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import pytest  # noqa: E402

import csv_store  # noqa: E402
import reading  # noqa: E402
import state  # noqa: E402

NEW = {"contact_id": "fernhill_freight_ostler", "name": "Tove Ostler", "company": "Fernhill Freight",
       "status": "not_contacted", "location": "Manchester, England, United Kingdom"}


@pytest.fixture
def unreadable(monkeypatch):
    def refuse(path=None):
        raise csv_store.Conflicted("network_threads.csv has unresolved merge markers in it")
    monkeypatch.setattr(state, "load_threads", refuse)


def test_the_limit_refuses_on_a_log_it_cannot_read(unreadable):
    with pytest.raises(reading.LogUnreadable, match="message log could not be read"):
        reading.at_employer("Fernhill Freight", [NEW])


def test_the_short_list_adds_nobody_there_and_says_why(unreadable, monkeypatch):
    monkeypatch.setattr(reading, "_save_shortlist", lambda have, today: None)
    monkeypatch.setattr(reading, "_shortlist_file", lambda today: [])
    got = reading.shortlist([NEW["contact_id"]], contacts=[NEW])
    assert NEW["contact_id"] not in got["ids"], got
    assert "message log could not be read" in got["unreadable"][NEW["contact_id"]], got


def test_saving_notes_saves_nothing_and_says_why(unreadable, capsys):
    code = reading.save_drafts({NEW["contact_id"]: ("Hi Tove, I'd love to hear about the team.",
                                                    False)})
    out = capsys.readouterr().out
    assert code == reading.EXIT["error"], out
    assert "nothing saved: your message log could not be read" in out, out
    assert not os.path.isfile(reading.draft_path(NEW["contact_id"]))


def test_the_page_holds_the_note_and_says_why(unreadable):
    """The review of 2026-11-11: the page's own check read any failure as "not held"; a log it
    cannot read holds the note, with the words that say why."""
    import datetime
    import types
    import app_model
    ctx = types.SimpleNamespace(_got={}, contacts=[NEW], today=datetime.date(2026, 11, 11),
                                threads=None)
    said = app_model.employer_held(ctx, "Fernhill Freight", NEW["contact_id"])
    assert said.startswith("On hold: your message log could not be read"), said
