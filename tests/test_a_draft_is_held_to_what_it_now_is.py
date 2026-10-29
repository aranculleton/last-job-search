"""A draft waiting for someone is checked as what it now is, and against everything they said.

Seen on a person's page (2026-10-26): a LinkedIn message to someone already written to was
shown as a ready draft at "287 of 280 characters", and said the person had "just moved from
London to Toronto" where their profile says never to write that they moved or are
relocating. `reading.py draft` checked the note's length as a first note (300 on the plan)
when the page counted it as a follow-up (280), and checked nothing the person said never to
say; and the never-say check knew three spellings of the move, not the claim. Invented
people, employers and places throughout.
"""
from __future__ import annotations

import os
import shutil
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import app_model  # noqa: E402
import compose  # noqa: E402
import learned  # noqa: E402
import person  # noqa: E402
import reading  # noqa: E402
import schema  # noqa: E402
import state  # noqa: E402
import tone  # noqa: E402
import voice_check  # noqa: E402


@pytest.fixture
def profile(tmp_path, monkeypatch):
    """The example person, in a copy of their own: learned.json is written here."""
    d = tmp_path / "profile"
    shutil.copytree(os.path.join(ROOT, "profile.example"), d)
    monkeypatch.setenv(person.ENV, str(d))
    person._modules.clear()
    person._data.clear()
    yield d
    person._modules.clear()
    person._data.clear()


@pytest.fixture
def book(tmp_path, monkeypatch):
    """A contact book and a message log in files, the reading files and drafts beside them."""
    monkeypatch.setattr(reading.person, "state", lambda *p: str(tmp_path.joinpath("state", *p)))
    monkeypatch.setenv("LJS_LEDGER", str(tmp_path / "ledger"))
    contacts, threads = str(tmp_path / "contacts.csv"), str(tmp_path / "threads.csv")
    real_load_c, real_save_c = state.load_contacts, state.save_contacts
    real_load_t, real_save_t = state.load_threads, state.save_threads
    monkeypatch.setattr(state, "load_contacts", lambda path=contacts: real_load_c(path))
    monkeypatch.setattr(state, "save_contacts", lambda rows, path=contacts: real_save_c(rows, path))
    monkeypatch.setattr(state, "load_threads", lambda path=threads: real_load_t(path))
    monkeypatch.setattr(state, "save_threads", lambda rows, path=threads: real_save_t(rows, path))
    monkeypatch.setattr(learned, "approved", lambda include_retired=False: [])
    # The plan the page and the composer both count by: Premium, a 300-character note and a
    # follow-up held 20 below it.
    monkeypatch.setitem(schema.LIMITS, "connection_note_chars", 300)
    monkeypatch.setitem(schema.LIMITS, "nudge_chars", 280)
    monkeypatch.setitem(compose.KIND_LIMITS, "connection", {"chars": 300})
    monkeypatch.setitem(compose.KIND_LIMITS, "nudge", {"chars": 280})

    class Book:
        path = tmp_path

        @staticmethod
        def put(contact, *messages):
            state.save_contacts(state.load_contacts() + [dict(contact)])
            state.save_threads(state.load_threads() + [dict(m) for m in messages])
            reading.save(contact["contact_id"], {
                "name": contact["name"], "company": contact["company"],
                "headline": contact["title"], "location": contact["location"],
                "sources": [{"kind": "paste", "url": "", "date": "2026-10-20"}],
                "items": [{"kind": "about", "text": "Forecasting for the depot network."}]})
    return Book


# Someone already written to: a connection note went on 9 October and nothing came back.
WREN = {"contact_id": "larkspur_haldane", "name": "Corwin Haldane", "title": "Analytics Lead",
        "company": "Larkspur Freight", "location": "Manchester, England, United Kingdom",
        "channel": "connection", "status": "awaiting_reply", "first_contacted": "2026-10-09"}
NOTE_SENT = {"contact_id": "larkspur_haldane", "date": "2026-10-09", "direction": "outbound",
             "channel": "linkedin", "scenario": "first_note", "summary": "connection note",
             "full_text": "Hi Corwin, I'm a supply-chain analyst in Manchester. How is the "
                          "forecasting team at Larkspur set up?"}

# 287 characters: inside a first note's 300, over a follow-up's 280.
FOLLOW_UP = ("Hi Corwin, Larkspur has since posted a demand planning role, which is close to the "
             "forecasting I do for the depot network at Brindle & Hart. I'd like to hear how "
             "the planning team works with the depots there. Would you have fifteen minutes "
             "for a call one afternoon in the next few weeks?")


def _draft(book, cid, text):
    f = book.path / "note.txt"
    f.write_text(text, encoding="utf-8")
    return reading.main(["draft", cid, str(f)])


def test_a_follow_up_over_its_limit_is_refused_and_says_to_shorten_it(book, capsys):
    assert len(FOLLOW_UP) == 287
    book.put(WREN, NOTE_SENT)
    # What the page counts it as: a follow-up, held to 280.
    assert app_model.draft_limit(WREN, "awaiting_reply") == ("follow_up", "nudge", 280)
    assert _draft(book, "larkspur_haldane", FOLLOW_UP) == reading.EXIT["error"]
    out = capsys.readouterr().out
    assert "not saved" in out and "follow-up" in out and "287 characters, limit 280" in out
    assert "shorten" in out.lower()
    assert not os.path.isfile(reading.draft_path("larkspur_haldane"))
    # Cut to fit, it is saved, and the page shows it inside its limit.
    short = FOLLOW_UP.replace(" for the depot network at Brindle & Hart", "")
    assert len(short) <= 280
    assert _draft(book, "larkspur_haldane", short) == reading.EXIT["ok"]
    assert os.path.isfile(reading.draft_path("larkspur_haldane"))


def test_a_first_note_is_still_held_to_the_plans_note_length(book, capsys):
    new = dict(WREN, contact_id="larkspur_ansgar", name="Pell Ansgar", status="not_contacted",
               first_contacted="")
    book.put(new)
    assert app_model.draft_limit(new, "not_contacted") == ("first_note", "connection", 300)
    note = FOLLOW_UP.replace("Hi Corwin", "Hi Pell")
    assert 280 < len(note) <= 300
    assert _draft(book, "larkspur_ansgar", note) == reading.EXIT["ok"], capsys.readouterr().out


# ------------------------------------------------------------ never say that they moved

MOVED = ("Hi Corwin, I just moved from Leeds to Manchester. Larkspur has since posted a demand "
         "planning role: would you have fifteen minutes for a call one afternoon?")


def _ban_the_move():
    learned.record("messages", "I live here now, I'm not moving",
                   "never say I moved or am relocating; say I'm based in Manchester",
                   never_say=["recently moved", "relocating", "moving to Manchester"],
                   today="2026-10-20", answers=False)


@pytest.mark.parametrize("said", [
    "I just moved from Leeds to Manchester.",
    "Just moved from Leeds to Manchester, so I'm keen to meet people.",
    "I moved from Leeds to Manchester in the spring.",
    "Since moving to Manchester I've been looking around.",
    "I'm relocating at the end of the month.",
    "I've recently relocated.",
])
def test_a_ban_on_saying_you_moved_covers_every_way_of_saying_it(profile, said):
    assert learned.dislikes(said) == []          # nobody said it yet: nothing is banned
    _ban_the_move()
    assert learned.dislikes(said), said
    assert "person_dislikes" in [r for r, _t in tone.check(said)]
    assert any(f["rule"] == "person-dislikes" for f in voice_check.check(said))


@pytest.mark.parametrize("said", [
    "I'm based in Manchester.",
    "I moved our forecasting to dbt last year.",
    "We moved to Snowflake in the spring.",
    "I moved to Brindle & Hart in 2023.",
    "We relocated the depot to Trafford.",
    "I moved into demand planning in 2022.",
    # Another person's own answer to "how long have you been here?": arriving is not moving.
    "I've just arrived in Manchester.",
])
def test_a_move_that_is_not_the_person_moving_is_not_caught(profile, said):
    _ban_the_move()
    assert learned.dislikes(said) == [], said


def test_the_profiles_own_never_write_rule_turns_the_whole_claim_on(profile):
    rules = profile / "CLAUDE.md"
    rules.write_text(rules.read_text(encoding="utf-8") + (
        "\n## Where they live\n- Never write \"moving to Manchester\", \"relocating\" or "
        "\"currently moving\" anywhere; the line is \"I made the move\".\n"), encoding="utf-8")
    learned.adopt_profile_rules(today="2026-10-20")
    assert learned.dislikes("Hi Bo, I just moved from Leeds to Manchester.") == [
        "just moved from Leeds to Manchester"]
    # Their own line stays theirs.
    assert learned.dislikes("I made the move to Manchester last year.") == []


def test_the_persons_own_line_is_never_caught_by_the_wider_family(profile):
    """A first note built from their own ABOUT_ME was refused for the move it states (the
    maintainer's copy, 2026-10-29). Their words are theirs; the phrases they banned still
    are caught word for word."""
    net = profile / "networking.py"
    net.write_text(net.read_text(encoding="utf-8") + (
        '\nABOUT_ME = "I just moved to Manchester from Leeds and work in demand planning."\n'),
        encoding="utf-8")
    person.clear_cache() if hasattr(person, "clear_cache") else person._modules.clear()
    _ban_the_move()
    assert learned.dislikes("Hi Bo, I just moved to Manchester from Leeds and work in demand "
                            "planning.") == []
    assert learned.dislikes("Hi Bo, I recently moved and am relocating.") != []


def test_a_draft_saying_the_person_moved_is_not_saved(profile, book, capsys):
    _ban_the_move()
    book.put(WREN, NOTE_SENT)
    assert _draft(book, "larkspur_haldane", MOVED) == reading.EXIT["error"]
    out = capsys.readouterr().out
    assert "not saved" in out and "just moved from Leeds to Manchester" in out
    assert not os.path.isfile(reading.draft_path("larkspur_haldane"))
    # Every other door a drafted message goes through says the same.
    assert "person_dislikes" in [r for r, _t in compose.validate(MOVED, "nudge")]
    with pytest.raises(compose.Refused, match="just moved"):
        compose.nudge("Corwin", "I just moved from Leeds to Manchester, and Larkspur has since "
                              "posted a demand planning role")
