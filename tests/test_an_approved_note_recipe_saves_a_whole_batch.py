"""The person's own approved note recipe saves for a whole batch of ten (acceptance test T11).

A person's recipe, kept with their approved examples, made the line about them the first
sentence of every note, in three approved variants, and closed on one of two asks. The
batch check refused ten notes written to it: "too alike ... same first sentence, your own
words included", then "shared" for each variant of the line about them, so a run reordered
six notes against the recipe the person had approved (2026-11-09). The opening and closing
lines of the notes they approved, every variant, and any shape at least two of those notes
share are theirs to repeat. Anything else the batch repeats is still a template.

The recipe here is invented: a paediatric nurse moving to Vancouver, and her readers.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tools" / "network")]

import reading  # noqa: E402

WHO = ["I'm a children's nurse, ex-Lakeshore and Harbourview, and just moved to Vancouver "
       "from Halifax.",
       "I'm a children's nurse (Lakeshore, then Harbourview), and just moved to Vancouver "
       "from Halifax.",
       "I'm a children's nurse, previously at Lakeshore and Harbourview, and just moved to "
       "Vancouver from Halifax."]
WORK = [("I ran discharge teaching for families on a surgical ward", "the family education work"),
        ("I led the move to bedside handovers on our unit", "how handovers run"),
        ("I trained new graduates on sepsis screening", "the sepsis work"),
        ("I set up a pain-scoring audit across two wards", "some of the quality work"),
        ("I worked night charge on a twenty-bed unit", "the charge role"),
        ("I built a feeding-plan checklist with dietitians", "the nutrition team"),
        ("I helped open a short-stay unit for day surgery", "the day-surgery side"),
        ("I precepted student nurses for three years", "the education roles"),
        ("I sat on our unit's falls-prevention group", "the patient-safety work"),
        ("I did transport nursing between two hospitals", "the transport team"),
        ("I ran our ward's infection-control audits", "the infection-control team"),
        ("I covered the paediatric high-dependency bay", "the critical-care side"),
        ("I trained parents on home tube feeding", "the community nursing work")]
HEDGE = ["which I imagine is similar to", "which could be similar to"]
ASKS = ["I'd love to hear what you're working on.", "Would be great to hear how the team works."]
NAMES = ["Ana Rook", "Bo Venn", "Juno Orrin", "Riley Reed", "Wren Allard", "Quinn Pell",
         "Sasha Lee", "Tamsin Oyelaran", "Idris Corrie", "Rhian Pellow", "Corwin Haldane",
         "Zoe Ruiz", "Mira Stavros"]
EMP = ["Fraserline Health", "Coastwell Clinic", "Harbourmead Hospital", "Northgate Care",
       "Islay Health", "Cedarholt Hospice", "Pinecrest Children's", "Valleyford Medical",
       "Baywater Rehab", "Summitvale Care", "Larkmoor Health", "Fernhill Clinic", "Oakbank Hospital"]


def note(i: int) -> str:
    work, theirs = WORK[i]
    return (f"Hi {NAMES[i].split()[0]}, hope you're well. {WHO[i % 3]} {work}, "
            f"{HEDGE[i % 2]} {theirs} at {EMP[i]}. {ASKS[i % 2]}")


APPROVED = [note(10), note(11), note(12)]          # three approved examples, one per variant


@pytest.fixture
def book(tmp_path, monkeypatch):
    """The example person's profile, a contact book of ten readers, and, when asked, the
    approved examples in their learned.json."""
    import csv_store
    import person
    import state
    d = tmp_path / "profile"
    shutil.copytree(os.path.join(ROOT, "profile.example"), d)
    monkeypatch.setenv(person.ENV, str(d))
    monkeypatch.setenv("LJS_STATE", str(tmp_path / "state"))
    monkeypatch.setenv("LJS_LEDGER", str(tmp_path / "ledger"))
    (tmp_path / "state").mkdir()
    person._modules.clear()
    person._data.clear()
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
    csv_store.write_rows(contacts, [
        {"contact_id": f"c{i}", "name": NAMES[i], "company": EMP[i], "status": "not_contacted"}
        for i in range(10)], ("contact_id", "name", "company", "status"))

    def approve(texts):
        (d / "learned.json").write_text(json.dumps({"entries": [], "approved": [
            {"date": "2026-10-01", "said": "perfect, more like this", "text": t,
             "channel": "connection", "reader": "peer", "status": "active"} for t in texts]}),
            encoding="utf-8")
    yield approve
    person._modules.clear()
    person._data.clear()


def _batch():
    return {f"c{i}": (note(i), True) for i in range(10)}


def test_without_the_recipe_the_batch_reads_as_one_template(book, capsys):
    assert reading.save_drafts(_batch()) == reading.EXIT["alike"]
    assert "too alike" in capsys.readouterr().out
    assert not os.path.exists(reading.draft_path("c0"))


def test_the_approved_recipe_saves_a_whole_batch_of_ten(book, capsys):
    book(APPROVED)
    assert reading.save_drafts(_batch()) == reading.EXIT["ok"], capsys.readouterr().out
    for i in range(10):
        assert os.path.exists(reading.draft_path(f"c{i}"))


def test_the_recipe_is_read_from_the_approved_notes(book):
    book(APPROVED)
    taught = reading.recipe()
    # Each approved variant of the line about her, and each approved close, is hers.
    for line in WHO + ASKS:
        assert any(reading._same(line, x) for x in taught["lines"]), line
    # A shape needs two approved notes: one approved note is not a recipe.
    assert reading.recipe([APPROVED[0]])["orders"] == set()


def test_what_the_recipe_does_not_cover_is_still_a_template(book):
    book(APPROVED)
    # The same middle sentence in every note is not in any approved note: still refused.
    copied = {f"c{i}": f"Hi {NAMES[i].split()[0]}, hope you're well. {WHO[i % 3]} "
                       f"I ran discharge teaching for families on a surgical ward. {ASKS[i % 2]}"
              for i in range(10)}
    kinds = {k for k, _s, _i in reading.alike(copied)}
    assert "shared" in kinds
