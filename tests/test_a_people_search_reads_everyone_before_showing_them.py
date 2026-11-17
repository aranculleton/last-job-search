"""With the person's computer set up to read profiles, a people search shows nobody and drafts no
note before that person's profile is read, recruiters included, and drafting from search results
is the person's own choice, never the default.

Issue 287 (2026-11-16): a people search drafted first notes and showed people while LinkedIn was
signed out on the person's computer, without asking. Recruiters were drafted from search results
alone ("the app's normal route for recruiters", `card_enough`) and the rest under WAITS ON A
READ. The person had never agreed to either: the default is signed in and read first. Invented
people and employers only.
"""
from __future__ import annotations

import datetime
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import place  # noqa: E402
import reading  # noqa: E402
import state  # noqa: E402

RECRUITER = {"name": "Idris Corrie", "company": "Kestrel Mutual", "read_on": "",
             "headline": "Technical Recruiter at Kestrel Mutual",
             "location": "Manchester, England, United Kingdom", "reach": "request",
             "sources": [{"kind": "list", "url": "", "date": "2026-10-21"}], "items": []}
NOTE = ("Hi Rosalind, hope you're well. I'm an analyst in Manchester and I build demand "
        "forecasts. I'd love to hear what you're working on.")


@pytest.fixture
def book(tmp_path, monkeypatch, judged):
    """A contact book, the reading files beside it, and a profile whose computer is set up to
    read LinkedIn (profile/place.json, as `computer.py ready` leaves it)."""
    monkeypatch.setattr(reading.person, "state", lambda *p: str(tmp_path.joinpath(*p)))
    monkeypatch.setenv("LJS_LEDGER", str(tmp_path / "ledger"))
    contacts, threads = str(tmp_path / "contacts.csv"), str(tmp_path / "threads.csv")
    monkeypatch.setattr(state, "CONTACTS_CSV", contacts)
    monkeypatch.setattr(state, "THREADS_CSV", threads)
    real_load_c, real_save_c = state.load_contacts, state.save_contacts
    real_load_t = state.load_threads
    monkeypatch.setattr(state, "load_contacts", lambda path=contacts: real_load_c(path))
    monkeypatch.setattr(state, "save_contacts", lambda rows, path=contacts: real_save_c(rows, path))
    monkeypatch.setattr(state, "load_threads", lambda path=threads: real_load_t(path))
    monkeypatch.setattr(reading, "reads_now", lambda: "browser")
    where = tmp_path / "place.json"
    monkeypatch.setattr(place, "_profile_file", lambda: str(where))
    judged("Kestrel Mutual")

    class Book:
        path = tmp_path

        @staticmethod
        def computer(ready=True):
            where.write_text(json.dumps({"works_on": "computer",
                                         **({"computer_ready": "2026-11-10"} if ready else {})}),
                             encoding="utf-8")

        @staticmethod
        def put(*rows):
            state.save_contacts(state.load_contacts() + [dict(r) for r in rows])

        @staticmethod
        def contacts():
            return state.load_contacts()
    return Book


def _row(cid, name, title="Head of Pricing"):
    return {"contact_id": cid, "name": name, "company": "Kestrel Mutual", "title": title,
            "status": "not_contacted", "location": "Manchester, England, United Kingdom"}


def _note(book, text=NOTE):
    f = book.path / "note.txt"
    f.write_text(text, encoding="utf-8")
    return str(f)


def test_a_recruiter_is_read_before_their_note_like_anyone_else(book, capsys):
    book.computer()
    book.put(_row("kestrel_corrie", "Idris Corrie", RECRUITER["headline"]))
    reading.save("kestrel_corrie", dict(RECRUITER))
    assert not reading.card_enough(reading.load("kestrel_corrie"))
    # On the day's read list, never left off it to be drafted from the card.
    got = reading.shortlist(["kestrel_corrie"], contacts=book.contacts())
    assert got["card_enough"] == [] and got["ids"] == ["kestrel_corrie"], got
    note = _note(book, "Hi Idris, hope you're well. I'm an analyst in Manchester looking for "
                       "my next role. If anything you're working on fits, it'd be great to hear.")
    assert reading.main(["draft", "kestrel_corrie", note]) == reading.EXIT["error"]
    assert "has not been read" in capsys.readouterr().out
    assert not os.path.isfile(reading.draft_path("kestrel_corrie"))


def test_no_note_is_saved_before_a_read_card_only_or_waiting_alike(book, capsys):
    book.computer()
    book.put(_row("kestrel_achterberg", "Rosalind Achterberg"))
    for how in (["--wait-for-read"], ["--card-only"]):
        assert reading.main(["draft", "kestrel_achterberg", _note(book), *how]) == \
            reading.EXIT["error"], how
        out = capsys.readouterr().out
        assert "has not been read" in out and "reading.py signin" in out, out
        assert "from-search --said" in out
        assert not os.path.isfile(reading.draft_path("kestrel_achterberg"))
    # A public finding is not their profile: still not read.
    assert reading.main(["add", "kestrel_achterberg", "--kind", "talk", "--url",
                         "https://example.org/talk", "--date", "2026-09-01", "--text",
                         "Forecasting demand at Kestrel Mutual"]) == reading.EXIT["ok"]
    assert reading.has_read(reading.load("kestrel_achterberg"))
    capsys.readouterr()
    assert reading.main(["draft", "kestrel_achterberg", _note(book)]) == reading.EXIT["error"]
    assert "has not been read" in capsys.readouterr().out


def test_notes_from_search_results_are_the_persons_choice_for_that_day(book, capsys):
    book.computer()
    book.put(_row("kestrel_achterberg", "Rosalind Achterberg"))
    # Never chosen for them: no words, no choice.
    with pytest.raises(SystemExit):
        reading.main(["from-search", "--said", "  "])
    assert reading.main(["from-search", "--said", "just draft them from the search this time"]) \
        == reading.EXIT["ok"]
    capsys.readouterr()
    assert reading.main(["draft", "kestrel_achterberg", _note(book), "--wait-for-read"]) == 0
    assert reading.waits_on_read("kestrel_achterberg")
    # The next day, read first again.
    tomorrow = reading.person.today() + datetime.timedelta(days=1)
    assert reading.from_search_chosen(tomorrow) == ""
    assert reading.reads_first(tomorrow)


def test_without_a_computer_set_up_for_reads_the_run_is_as_before(book, capsys):
    book.computer(ready=False)
    book.put(_row("kestrel_achterberg", "Rosalind Achterberg"))
    assert not reading.reads_first()
    assert reading.main(["draft", "kestrel_achterberg", _note(book), "--wait-for-read"]) == 0
    assert reading.waits_on_read("kestrel_achterberg")


def test_a_chat_without_the_browser_queues_the_reads_and_saves_no_note(book, capsys):
    # A people search in a chat with no browser of its own (a cloud chat) was told to save each
    # note from search results under WAITS ON A READ: with the computer reading profiles that
    # is refused, so it queues them and the computer reads each and writes its note.
    book.computer()
    got = reading.route(tools=(), consent="browser", env={})
    assert got["route"] == "page", got
    assert "--wait-for-read" not in got["do"] and "save no note" in got["do"], got
    assert "queue-page" in got["do"] and "a recruiter's included" in got["do"]
    book.put(_row("kestrel_achterberg", "Rosalind Achterberg"))
    assert reading.main(["draft", "kestrel_achterberg", _note(book), "--wait-for-read"]) == \
        reading.EXIT["error"]
    assert "queue-page" in capsys.readouterr().out
    # Without a computer set up for reads, the page reads them and notes wait on it, as before.
    book.computer(ready=False)
    assert "--wait-for-read" in reading.route(tools=(), consent="browser", env={})["do"]


def test_the_run_on_the_computer_is_told_to_wait_for_the_sign_in_and_draft_nothing():
    got = reading.route(tools=("browser",), consent="browser", env={})
    assert got["route"] == "here", got
    assert "drafting nothing from search results" in got["do"]
    assert "a recruiter's included" in got["do"]
