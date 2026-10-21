"""One person in two rows is raised, never merged.

`already_contacted` matches a name exactly, so against a book holding "Robert Smith" at
an employer, "Bob Smith", "R. Smith", "Robert J. Smith", "Smith, Robert" and a one-letter
typo of the surname were all strangers, and `reconcile` said nothing about a second row
"Bob Smith" there. Rows from a web search carry no LinkedIn address, which is the one
thing that would have told. The rule it endangers is the one that nobody already
contacted is surfaced again. A wrong merge would hand one person's messages to another,
so this only ever warns.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "network"))

import sources  # noqa: E402
import state  # noqa: E402

BOOK = [{"contact_id": "larkspur_retail_halloway", "name": "Robert Halloway",
         "company": "Larkspur Retail", "status": "awaiting_reply"}]


def test_a_nickname_an_initial_a_middle_name_a_reversal_and_a_typo_are_each_a_possible_match():
    for name in ("Bob Halloway", "R. Halloway", "Robert J. Halloway", "Halloway, Robert",
                 "Robert Hallowey"):
        got = state.possible_match(BOOK, name, "Larkspur Retail")
        assert got and got["row"]["contact_id"] == "larkspur_retail_halloway", name
        assert got["reason"], name


def test_different_people_are_left_alone():
    for name in ("Riley Halloway", "Robin Halloway", "Robert Halloway Sr.", "Robert Hart"):
        if name.endswith("Sr."):
            book = [dict(BOOK[0], name="Robert Halloway Jr.")]
        else:
            book = BOOK
        assert state.possible_match(book, name, "Larkspur Retail") is None, name
    # Another employer is another person, and the exact name is already_contacted's job.
    assert state.possible_match(BOOK, "Bob Halloway", "Fernhill Freight") is None
    assert state.possible_match(BOOK, "Robert Halloway", "Larkspur Retail") is None


def test_two_different_linkedin_profiles_are_two_people():
    book = [dict(BOOK[0], linkedin_url="https://www.linkedin.com/in/example-robert")]
    assert state.possible_match(book, "Bob Halloway", "Larkspur Retail",
                                "https://www.linkedin.com/in/example-bob") is None


def test_reconcile_raises_the_pair_on_the_newer_row_and_merges_nothing():
    book = BOOK + [{"contact_id": "larkspur_retail_halloway_b", "name": "Bob Halloway",
                    "company": "Larkspur Retail", "status": "not_contacted"}]
    before = [dict(r) for r in book]
    found = [p for p in state.reconcile(book, []) if p["reason"] == "possible_duplicate"]
    assert [p["contact_id"] for p in found] == ["larkspur_retail_halloway_b"]
    assert "Robert Halloway (larkspur_retail_halloway)" in found[0]["detail"]
    assert "Never merged" in found[0]["detail"]
    assert book == before


def test_a_pair_marked_as_two_people_is_not_raised_again():
    book = BOOK + [{"contact_id": "larkspur_retail_halloway_b", "name": "Bob Halloway",
                    "company": "Larkspur Retail",
                    "notes": "not the same person as larkspur_retail_halloway"}]
    assert state.possible_duplicates(book) == []


def test_three_rows_that_may_be_one_person_are_one_finding_to_check_by_hand():
    book = BOOK + [{"contact_id": "a2", "name": "Bob Halloway", "company": "Larkspur Retail"},
                   {"contact_id": "a3", "name": "R. Halloway", "company": "Larkspur Retail"}]
    found = state.possible_duplicates(book)
    assert len(found) == 1 and found[0]["sure"] == "check"
    assert set(found[0]["contact_ids"]) == {"larkspur_retail_halloway", "a2", "a3"}


def test_discovery_asks_before_adding_a_second_row():
    conns = [{"name": "Bob Halloway", "company": "Larkspur Retail", "title": "Planning Lead",
              "linkedin_url": "", "connected_on": ""}]
    got = sources.from_connections("Larkspur Retail", connections=conns, contacts=BOOK)
    assert len(got) == 1 and "larkspur_retail_halloway" in got[0]["maybe_in_book"]
