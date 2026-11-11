"""LinkedIn's download is matched to the contact book by the employer's name, never a stale key.

The book's `company_key` column is a convenience, written once; `company_key.row_key` recomputes
it from the name, and the rest of the app reads that. The download's matching read the stored
column, so a row whose key was written before an alias was added ("harbourline financial group"
for Harbourline) compared unequal and its person was taken for a stranger; and one import took an event's
name as an employer (the audit of 2026-11-10, NW-20; PD-17). Every person is invented.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import export  # noqa: E402
import state  # noqa: E402


def test_a_stale_stored_key_never_keeps_a_person_from_their_messages():
    # A record known by first name, its surname in its id, at an employer whose stored key
    # is a longer form the name no longer gives.
    book = [{"contact_id": "kestrel_mutual_ada_lind", "name": "Ada", "company": "Kestrel Mutual",
             "company_key": "kestrel mutual insurance group plc", "status": "awaiting_reply"}]
    got, how = export.match_more(book, [], "Ada Lind", "", employer="Kestrel Mutual")
    assert got is book[0] and how == "first name", (got, how)
    a = dict(book[0])
    b = {"contact_id": "ada", "name": "Ada Lind", "company": "Kestrel Mutual", "company_key": ""}
    assert export._could_be_one(a, b)


def test_an_event_is_never_taken_for_an_employer():
    rec = {"contact_id": "quayside_ostrander", "name": "Ravi Ostrander", "company": "", "title": ""}
    export.fill_who([(rec, "6th Annual Forecasting World | Supply Summit", "Speaker", "")])
    assert rec["company"] == "", rec
    export.fill_who([(rec, "Quayside Foods", "Planner", "")])
    assert rec["company"] == "Quayside Foods"


def test_reconcile_names_a_stored_key_the_name_no_longer_gives():
    book = [{"contact_id": "kestrel_mutual_ada", "name": "Ada Lind", "company": "Kestrel Mutual",
             "company_key": "kestrel mutual insurance group plc", "status": "not_contacted"}]
    found = [p for p in state.reconcile(book, []) if p["reason"] == "stale_company_key"]
    assert [p["contact_id"] for p in found] == ["kestrel_mutual_ada"], found


def test_an_employer_whose_name_holds_an_event_word_is_kept():
    """The review of 2026-11-11: any event word refused the employer, so "Summit Partners" and
    "The Conference Board" were left blank. Only an event's own shape is refused: "Nth annual",
    a " | " between names, or an event word with a year or a number."""
    for firm in ("The Conference Board of Lakeland", "Summit Partners", "Summit Financial Group",
                 "Expo Communications"):
        rec = {"contact_id": "x", "name": "Ravi Ostrander", "company": "", "title": ""}
        export.fill_who([(rec, firm, "Analyst", "")])
        assert rec["company"] == firm, firm
    for event in ("6th Annual Forecasting World | Supply Summit", "Forecasting Summit 2026",
                  "Data Expo 2025"):
        rec = {"contact_id": "x", "name": "Ravi Ostrander", "company": "", "title": ""}
        export.fill_who([(rec, event, "Speaker", "")])
        assert rec["company"] == "", event
