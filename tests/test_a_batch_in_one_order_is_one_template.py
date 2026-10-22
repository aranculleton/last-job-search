"""A batch whose notes all run in one order is one template, and no close is pushed to one
sentence.

A person's report, 2026-10-22: twenty notes were saved that were all the greeting, the same
line about the sender, one line about the reader and "I'd love to hear ...", and nothing
said so, because each line was the person's own or different from the others. Meanwhile
any closing question with "quick chat", "minutes" or "connect" in it was refused as "not
your ask" unless it was the person's ASK word for word, which sent every close to the one
sentence. Every person and employer here is invented.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tools" / "network")]

import compose  # noqa: E402
import reading  # noqa: E402

PEOPLE = ["Ana Rook", "Bo Venn", "Juno Orrin", "Riley Reed", "Wren Allard", "Quinn Pell",
          "Sasha Lee", "Tamsin Oyelaran", "Idris Corrie", "Rhian Pellow", "Corwin Haldane", "Zoe Ruiz"]
TOPICS = ["stock cover", "promotion lift", "cold-chain forecasts", "supplier lead times",
          "safety stock", "range reviews", "waste in fresh", "store clustering",
          "markdown timing", "demand sensing", "weekly replans", "new-line forecasts"]
# A line about the reader, a line about the sender and a close for each of twelve notes, no
# two alike: only their order is the same.
THEM = ["Your post on stock cover stuck with me.",
        "Your move from buying into planning at Firm B is a route I keep hearing about.",
        "The talk you gave on cold-chain forecasts was the clearest I have seen on it.",
        "Supplier lead times are the thing your team seems to have cracked.",
        "Safety stock at a grocer that size must be a puzzle every week, and you run it.",
        "I saw the range review work you shared in the spring.",
        "Cutting waste in fresh is hard, and your numbers on it were striking.",
        "Store clustering came up in your write-up, which I read twice.",
        "Markdown timing at Firm I sounds like your corner of the business.",
        "Demand sensing is where your team went early, from what you have written.",
        "Weekly replans at your place apparently run on a tool your team built.",
        "New-line forecasts were the subject of your last article, which I enjoyed."]
ME = ["I work on demand forecasts for a Manchester grocer.",
      "My own background is four years of retail planning.",
      "I have been building cold-chain models since 2022.",
      "Most of my work is supplier data and lead-time models.",
      "Safety stock is half of what I do day to day.",
      "Range reviews were my first project as an analyst.",
      "In my current job I track waste across forty stores.",
      "Clustering stores was the model I am proudest of.",
      "Markdowns are a problem I spent last year on.",
      "Sensing demand from till data is my current project.",
      "Replanning is something I automated in my last team.",
      "New lines are the forecasts I find hardest."]
CLOSE = ["Would you be open to a quick chat?",
         "Could I ask how the team splits its week?",
         "I'd love to hear what changed when you moved.",
         "Any chance of 15 minutes this month?",
         "How did you get the buyers to trust the numbers?",
         "What would you learn first in my place?",
         "Is it still mostly spreadsheets there?",
         "Where is the team heading next year?",
         "How did you pick up the retail side?",
         "What surprised you most about the role?",
         "How does the data reach you each morning?",
         "What made you stay so long?"]


def _one_template(n, me_first=()):
    """n notes, each the greeting, a line about the reader, one about the sender and a
    close, all different; the ones in `me_first` say who the sender is first."""
    out = {}
    for i in range(n):
        cid, first = f"c{i}", PEOPLE[i].split()[0]
        parts = (ME[i], THEM[i]) if cid in me_first else (THEM[i], ME[i])
        out[cid] = f"Hi {first}, {parts[0]} {parts[1]} {CLOSE[i]}"
    return out


def _kinds(found):
    return {k for k, _s, _i in found}


def test_a_batch_in_one_order_is_found_and_a_handful_is_not():
    found = [f for f in reading.alike(_one_template(12)) if f[0] != "same shape"]
    # Nothing else in it repeats: the order is all that does.
    assert [(k, s, len(i)) for k, s, i in found] == [("same sentence order",
                                                    "them / me / ask", 12)]
    # Below ORDER_MIN a handful of notes in one order is how short notes are written.
    assert "same sentence order" not in _kinds(reading.alike(_one_template(5)))
    # Below ORDER_SHARE_FROM notes, every one; from it, nine in ten.
    assert "same sentence order" not in _kinds(reading.alike(_one_template(9, {"c0"})))
    assert "same sentence order" in _kinds(reading.alike(_one_template(12, {"c0"})))
    assert "same sentence order" not in _kinds(reading.alike(_one_template(12, {"c0", "c1"})))


def test_a_close_is_never_held_to_the_persons_ask_word_for_word():
    closes = ["Would you be open to a quick chat about how you moved into planning?",
              "Could I grab 15 minutes to hear how the team works?",
              "Would you be up for connecting and comparing notes on forecasting?",
              "Do you have a few minutes for a couple of questions about the move?"]
    notes = {f"c{i}": f"Hi {PEOPLE[i].split()[0]}, your post on {TOPICS[i]} stuck with me. "
                      f"{c}" for i, c in enumerate(closes)}
    assert "not your ask" not in _kinds(reading.alike(notes))


def _compose(i, **kw):
    first = PEOPLE[i % len(PEOPLE)]
    return compose.first_note(first, how_found="I found you on Larkspur's people page",
                              common_ground=f"your post on {TOPICS[i % len(TOPICS)]} stuck "
                                            "with me", variant_key=f"c{i}", card_only=True,
                              **kw)


def test_the_composer_varies_its_order_by_contact_and_a_redraft_does_not():
    notes = {f"c{i}": _compose(i) for i in range(12)}
    orders = {compose.sentence_order(t) for t in notes.values()}
    assert len(orders) >= 2
    assert "same sentence order" not in _kinds(reading.alike(notes))
    # Never opening most of a batch on the person's own line, which is a template of its own.
    assert "same first sentence, your own words included" not in _kinds(reading.alike(notes))
    assert _compose(3) == _compose(3)


def test_an_order_can_be_chosen_and_one_that_does_not_fit_is_refused():
    me_first = _compose(0, order="me_first")
    assert compose.sentence_order(me_first)[0] == "me"
    assert compose.ABOUT_ME in me_first.split(". ", 2)[1]
    with pytest.raises(ValueError, match="order is one of"):
        _compose(0, order="sideways")
    with pytest.raises(ValueError, match="needs a question"):
        _compose(0, order="question_then_me")
    with pytest.raises(ValueError, match="two reasons"):
        compose.first_note("Ana Rook", common_ground="your post on stock cover stuck with me",
                           order="me_second", card_only=True)


def test_a_warm_introduction_always_leads_with_who_made_it():
    for i in range(12):
        note = compose.first_note(PEOPLE[i], how_found="Bo Venn suggested I get in touch",
                                  common_ground=f"your post on {TOPICS[i]} stuck with me",
                                  variant_key=f"w{i}", card_only=True)
        assert note.split(". ", 1)[1].startswith("Bo Venn suggested"), note
    with pytest.raises(ValueError, match="warm introduction"):
        compose.first_note("Ana Rook", how_found="Bo Venn suggested I get in touch",
                           order="me_first", card_only=True)


@pytest.fixture
def book(tmp_path, monkeypatch):
    """The example person's profile and a contact book of the twelve readers."""
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
        {"contact_id": f"c{i}", "name": n, "company": f"Firm {chr(65 + i)}",
         "status": "not_contacted"} for i, n in enumerate(PEOPLE)],
        ("contact_id", "name", "company", "status"))
    yield
    person._modules.clear()
    person._data.clear()


def test_a_batch_in_one_order_is_not_saved(book, capsys):
    batch = {cid: (t, True) for cid, t in _one_template(12).items()}
    assert reading.save_drafts(batch) == reading.EXIT["alike"]
    out = capsys.readouterr().out
    assert "same sentence order" in out and "order=" in out
    assert not os.path.exists(reading.draft_path("c0"))
    # The same notes, two of them in another order: saved.
    mixed = _one_template(12, {"c0", "c1"})
    assert reading.save_drafts({cid: (t, True) for cid, t in mixed.items()}) == \
        reading.EXIT["ok"], capsys.readouterr().out
    assert os.path.exists(reading.draft_path("c0"))
