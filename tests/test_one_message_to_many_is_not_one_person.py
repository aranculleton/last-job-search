"""The same message logged under two rows says one person only where the two could be one.

`reconcile` raised "one person in two rows?" whenever one day's same words sat under two ids,
and a note sent to four people called Tobiah at four employers the same day was raised as one
person: 53 such prompts in one book, drowning the real ones (the audit of 2026-11-10, NW-19).
It is raised now only where the names could be one person's (the same surname, or one row with
none) and the employers could be one (the same, or one blank). Every person is invented.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import state  # noqa: E402

NOTE = ("Hi Tobiah, hope you're well. I build forecasting models for stock and transport and "
        "I'd love to hear what you're working on.")


def _row(cid, name, company):
    return {"contact_id": cid, "name": name, "company": company, "status": "awaiting_reply"}


def _sent(cid, day="2026-08-24", text=NOTE):
    return {"contact_id": cid, "date": day, "direction": "out", "channel": "connection",
            "scenario": "connection_note", "summary": "First note sent", "full_text": text}


def _shared(book, log):
    return [p for p in state.reconcile(book, log) if p["reason"] == "shared_message"]


def test_one_template_to_four_people_at_four_employers_is_not_one_person():
    book = [_row("kestrel_fenwick", "Tobiah Fenwick", "Kestrel Mutual"),
            _row("fernhill_quarrie", "Tobiah Quarrie", "Fernhill Freight"),
            _row("larkspur_ostler", "Tobiah Ostler", "Larkspur Retail"),
            _row("quayside_lisle", "Tobiah Lisle", "Quayside Foods")]
    assert _shared(book, [_sent(c["contact_id"]) for c in book]) == []


def test_one_person_kept_twice_is_still_raised():
    book = [_row("fernhill_tolley", "Sam Tolley", "Fernhill Freight"), _row("tolley", "Sam Tolley", "")]
    found = _shared(book, [_sent("fernhill_tolley", text=NOTE.replace("Tobiah", "Sam")),
                           _sent("tolley", text=NOTE.replace("Tobiah", "Sam"))])
    assert len(found) == 1 and "fernhill_tolley and tolley" in found[0]["detail"], found
    # A first name only on one row, at the same employer: could be one person.
    book = [_row("kestrel_ada", "Ada", "Kestrel Mutual"), _row("kestrel_lind", "Ada Lind", "Kestrel Mutual")]
    assert len(_shared(book, [_sent("kestrel_ada"), _sent("kestrel_lind")])) == 1
