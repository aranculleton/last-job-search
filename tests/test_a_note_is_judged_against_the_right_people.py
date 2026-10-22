"""A first note is judged against the people it could really be for.

Two checks that guard a batch of notes refused the right note or passed the wrong one. The
example check (a note must not carry the name or employer of somebody an approved example
was written for) refused a warm introduction that led with its referrer, as it must, when
the referrer was that somebody; refused the referrer's employer and the reader's own past
employer; and read "Castellan Partners" as Ana Castellan. Nothing let the person say
it was wrong. And the greeting check passed "Hi Raj" on a note saved for Rajesh Venn
with Raj Allard in the same contact book: Raj's note, shuffled by one. Every person,
employer and message here is invented.
"""
from __future__ import annotations

import datetime
import json
import os
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tools" / "network")]

import compose  # noqa: E402
import reading  # noqa: E402
import tone  # noqa: E402

TODAY = datetime.date(2026, 10, 21)
APPROVED = ("Hi Ana, I saw your talk on promotion lift at the Kestrel Mutual analytics day. "
            "I build demand forecasts in Manchester and would love 15 minutes.")


def _book(rows):
    import csv_store
    import person
    csv_store.write_rows(person.state("network_contacts.csv"), rows,
                         ("contact_id", "name", "company", "status", "referred_by"))


@pytest.fixture
def approved(tmp_path, monkeypatch):
    """The example person's profile with one approved note, to Ana Castellan at Kestrel
    Mutual, and a contact book around her."""
    import learned
    import person
    d = tmp_path / "profile"
    shutil.copytree(os.path.join(ROOT, "profile.example"), d)
    monkeypatch.setenv(person.ENV, str(d))
    monkeypatch.setenv("LJS_STATE", str(tmp_path / "state"))
    monkeypatch.setenv("LJS_LEDGER", str(tmp_path / "ledger"))
    (tmp_path / "state").mkdir()
    person._modules.clear()
    person._data.clear()
    # The book every reader reads: state's loaders take a path fixed when it was imported.
    import state
    contacts = str(tmp_path / "state" / "network_contacts.csv")
    threads = str(tmp_path / "state" / "network_threads.csv")
    real_lc, real_sc = state.load_contacts, state.save_contacts
    real_lt, real_st = state.load_threads, state.save_threads
    monkeypatch.setattr(state, "CONTACTS_CSV", contacts)
    monkeypatch.setattr(state, "THREADS_CSV", threads)
    monkeypatch.setattr(state, "load_contacts", lambda path=contacts: real_lc(path))
    monkeypatch.setattr(state, "save_contacts", lambda rows, path=contacts: real_sc(rows, path))
    monkeypatch.setattr(state, "load_threads", lambda path=threads: real_lt(path))
    monkeypatch.setattr(state, "save_threads", lambda rows, path=threads: real_st(rows, path))
    _book([{"contact_id": "kes_castellan", "name": "Ana Castellan", "company": "Kestrel Mutual",
            "status": "replied_positive"},
           {"contact_id": "kes_venn", "name": "Bo Venn", "company": "Kestrel Mutual",
            "status": "replied_positive"},
           {"contact_id": "fern_allard", "name": "Wren Allard", "company": "Fernhill Freight",
            "status": "not_contacted", "referred_by": "kes_castellan"},
           {"contact_id": "fern_orrin", "name": "Juno Orrin", "company": "Fernhill Freight",
            "status": "not_contacted"},
           {"contact_id": "oak_reed", "name": "Riley Reed", "company": "Oakmere Foods",
            "status": "not_contacted"}])
    learned.approve("this one is good", APPROVED, channel="connection", reader="peer",
                    contact_id="kes_castellan", today="2026-10-01")
    yield
    person._modules.clear()
    person._data.clear()


def _read(cid, name, *employers):
    """What was read about them: their page, with these employers on it, newest first."""
    reading.save(cid, {"name": name, "company": employers[0],
                       "headline": f"Planner at {employers[0]}", "items": [],
                       "sources": [{"kind": "paste", "date": "2026-10-21"}],
                       "experience": [{"title": "Planner", "employer": e} for e in employers]})


def _facts(note, contact, name, referrer=""):
    return [v.text for v in compose.example_facts(note, contact=contact, name=name,
                                                  referrer=referrer)]


def test_a_warm_intro_that_names_its_referrer_is_saved(approved, capsys):
    note = ("Hi Wren, Ana Castellan suggested I get in touch. I build demand forecasts in "
            "Manchester and would value your view on how the planning team works.")
    # The referrer from their row (referred_by), on every path: the check, the save, the queue.
    _read("fern_allard", "Wren Allard", "Fernhill Freight")
    assert _facts(note, "fern_allard", "Wren Allard") == []
    assert reading.save_drafts({"fern_allard": (note, False)}) == reading.EXIT["ok"]
    assert os.path.exists(reading.draft_path("fern_allard"))
    book = [{"contact_id": "fern_allard", "name": "Wren Allard", "company": "Fernhill Freight",
             "status": "not_contacted", "referred_by": "kes_castellan"}]
    assert reading.queue(book, TODAY) == []
    # The same note to somebody nobody referred is still refused: her name is the example's.
    assert _facts(note.replace("Wren", "Juno"), "fern_orrin", "Juno Orrin")


def test_the_referrers_employer_and_the_readers_own_past_one_are_theirs(approved, capsys):
    via_bo = ("Hi Juno, Bo Venn at Kestrel Mutual suggested I get in touch. I build demand "
              "forecasts in Manchester and would value your view on the planning team.")
    assert _facts(via_bo, "fern_orrin", "Juno Orrin", referrer="Bo Venn") == []
    assert _facts(via_bo, "fern_orrin", "Juno Orrin", referrer="kes_venn") == []
    moved = ("Hi Juno, I saw you spent five years at Kestrel Mutual before joining Fernhill "
             "Freight. I build demand forecasts in Manchester and would value your view.")
    # Nothing read about Juno says so: refused, with the way to say it is theirs.
    assert _facts(moved, "fern_orrin", "Juno Orrin")
    assert reading.save_drafts({"fern_orrin": (moved, True)}) == reading.EXIT["error"]
    out = capsys.readouterr().out
    assert "not saved" in out and "--own-facts" in out
    # Their page names it: theirs to name.
    _read("fern_orrin", "Juno Orrin", "Fernhill Freight", "Kestrel Mutual")
    assert _facts(moved, "fern_orrin", "Juno Orrin") == []
    # A surname inside an employer's name is not the example reader's name; alone, it is.
    assert _facts("Hi Juno, your post on Castellan Partners outage forecasting stuck "
                  "with me. Would you have 15 minutes?", "fern_orrin", "Juno Orrin") == []
    assert _facts("Hi Juno, your chat with Castellan at the meetup stuck with me. Would you "
                  "have 15 minutes?", "fern_orrin", "Juno Orrin")


def test_a_wrong_refusal_is_lifted_for_one_reader_with_the_reason_kept(approved, capsys):
    moved = ("Hi Juno, I saw you spent five years at Kestrel Mutual before joining Fernhill "
             "Freight. I build demand forecasts in Manchester and would value your view.")
    why = "she told me herself she worked there before"
    _read("fern_orrin", "Juno Orrin", "Fernhill Freight")       # her page does not say so
    assert reading.save_drafts({"fern_orrin": (moved, True)}) == reading.EXIT["error"]
    assert reading.save_drafts({"fern_orrin": (moved, True)},
                               own_facts_why={"fern_orrin": why}) == reading.EXIT["ok"]
    assert "kept on your word" in capsys.readouterr().out
    kept = json.loads(Path(reading.own_facts_path("fern_orrin")).read_text(encoding="utf-8"))
    assert [(k["what"], k["reason"]) for k in kept["kept"]] == [("Kestrel Mutual", why)]
    # The queue and the check read it too, for this reader and for what was found.
    assert _facts(moved, "fern_orrin", "Juno Orrin") == []
    assert reading.queue([{"contact_id": "fern_orrin", "name": "Juno Orrin",
                           "company": "Fernhill Freight", "status": "not_contacted"}],
                         TODAY) == []
    # Another reader is checked as ever, and so is anything else in this one's note.
    assert _facts(moved.replace("Juno", "Riley"), "oak_reed", "Riley Reed")
    assert _facts("Hi Juno, Ana Castellan's talk stuck with me.", "fern_orrin", "Juno Orrin")
    # On the command line, the same: --own-facts with the reason, for another reader.
    note = Path(reading.draft_path("fern_orrin")).parent.parent / "note.txt"
    note.write_text(moved.replace("Juno", "Riley").replace("Fernhill Freight", "Oakmere Foods"),
                    encoding="utf-8")
    assert reading.main(["draft", "oak_reed", str(note), "--card-only"]) == \
        reading.EXIT["error"]
    assert reading.main(["draft", "oak_reed", str(note), "--card-only",
                         "--own-facts", "he said so on our call"]) == reading.EXIT["ok"]
    assert reading.own_facts("oak_reed") == {"kestrel mutual"}


def test_a_greeting_that_starts_a_name_is_theirs_only_when_nobody_else_answers_to_it(
        approved, capsys):
    _book([{"contact_id": "raj_allard", "name": "Raj Allard", "company": "Fernhill Freight",
            "status": "not_contacted"},
           {"contact_id": "rajesh_venn", "name": "Rajesh Venn", "company": "Oakmere Foods",
            "status": "not_contacted"}])
    note = ("Hi Raj, I am a demand planning analyst in Manchester and would value 15 "
            "minutes on how your planning team works.")
    # Raj's note saved under Rajesh: the shuffle the check exists for.
    assert reading.save_drafts({"rajesh_venn": (note, True)}) == reading.EXIT["error"]
    assert "greets Raj, but this message is for Rajesh Venn" in capsys.readouterr().out
    assert not os.path.exists(reading.draft_path("rajesh_venn"))
    assert reading.save_drafts({"raj_allard": (note, True)}) == reading.EXIT["ok"]
    found = compose.validate(note, "connection", name="Rajesh Venn", contact="rajesh_venn",
                             card_only=True)
    assert "greeting_wrong_name" in [v.rule for v in found]
    # With nobody else in the book who answers to it, a short form of hers is hers.
    assert tone.wrong_greeting(note, "Rajesh Venn") == []
    assert tone.wrong_greeting(note, "Rajesh Venn", ["Juno Orrin"]) == []
    # A closer fit is somebody else's too: "Thad" starts Thaddea before Thaddeus.
    assert tone.wrong_greeting("Hi Thad, hope you're well.", "Thaddeus Venn", ["Thaddea Rook"])
    assert tone.wrong_greeting("Hi Thad, hope you're well.", "Thaddea Rook",
                               ["Thaddeus Venn"]) == []


# Two notes from 2026-10-22: a reader whose first name is an approved example's surname was
# refused on their own greeting, and an employer called Visa was read as work authorization.

def test_the_readers_own_name_is_never_borrowed_from_an_example(approved, capsys):
    import learned
    _book([{"contact_id": "kes_castellan", "name": "Ana Castellan", "company": "Kestrel Mutual",
            "status": "replied_positive"},
           {"contact_id": "kes_pell", "name": "Pell Juno", "company": "Kestrel Mutual",
            "status": "replied_positive"},
           {"contact_id": "fern_orrin", "name": "Juno Orrin", "company": "Fernhill Freight",
            "status": "not_contacted"},
           {"contact_id": "oak_reed", "name": "Riley Reed", "company": "Oakmere Foods",
            "status": "not_contacted"}])
    learned.approve("this one is good too", "Hi Pell, your post on stock cover stuck with me. "
                    "I build demand forecasts in Manchester and would love 15 minutes.",
                    channel="connection", reader="peer", contact_id="kes_pell",
                    today="2026-10-02")
    note = ("Hi Juno, I build demand forecasts in Manchester and would value 15 minutes on "
            "how your planning team works.")
    # Juno is this reader's own first name, and the surname of the approved note's reader.
    assert _facts(note, "fern_orrin", "Juno Orrin") == []
    assert reading.save_drafts({"fern_orrin": (note, True)}) == reading.EXIT["ok"]
    assert "not saved" not in capsys.readouterr().out
    # The example's reader is still theirs alone: the full name, and the surname to anyone else.
    assert _facts("Hi Juno, Pell Juno's post stuck with me.", "fern_orrin", "Juno Orrin")
    assert _facts("Hi Riley, your chat with Juno at the meetup stuck with me.",
                  "oak_reed", "Riley Reed")


def test_an_employer_named_visa_is_its_name_not_work_authorization(approved):
    _book([{"contact_id": "visa_orrin", "name": "Juno Orrin", "company": "Visa",
            "status": "not_contacted"}])
    note = ("Hi Juno, the data science team at Visa works on the fraud models I build too. "
            "Would you have 15 minutes?")

    def auth(text, **kw):
        return [v.text for v in compose.validate(text, "connection", name="Juno Orrin",
                                                 reader="peer", card_only=True, **kw)
                if v.rule == "work_auth_in_first_note"]
    assert auth(note, employers=("Visa",)) == []
    assert auth(note, contact="visa_orrin") == []         # their employer, from their row
    assert auth(note)                                     # nothing says Visa is an employer
    # The word is still the word: lower case, or beside the name.
    assert auth(note + " My visa is sorted.", employers=("Visa",))
    assert auth(note.replace("at Visa", "at Kestrel Mutual") + " No visa needed.",
                employers=("Visa",))
    # The composer passes the names it keeps (`their`) the same way.
    made = compose.first_note("Juno Orrin", common_ground="the data science team at Visa "
                              "works on the fraud models I build too", their=("Visa",),
                              reader="peer", card_only=True)
    assert "Visa" in made
