"""The line at the limit of unanswered messages carries no date and no "close it", whatever
the conversation's status or age.

Since 2026-11-04 the stop line has no date: nothing is owed them. The audit of 2026-11-10 (NW-22)
found 19 rows still saying "If still silent by the date, close it" with a date, closed ones and
threads months old among them, because the rewrite skipped every closed status and every thread
owed more than 45 days. Every row like that is now undated by itself (the stop-lines-undated
profile upgrade), and the check of the contacts names one (PD-18). Every person is invented.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import state  # noqa: E402

STOP = ("No more follow-ups: 2 messages with no reply, your rule's limit (14 days, at most 2 "
        "with no reply)")


def _old(cid, status, due):
    return {"contact_id": cid, "name": cid.title(), "status": status,
            "next_action": STOP + ". " + state.CLOSE_IT.format(cid=cid),
            "next_action_due": due}


def test_every_old_stop_line_loses_its_close_it_and_its_date():
    book = [_old("brindle_corwin", "closed", "2026-11-04"), _old("ashby_mira", "awaiting_reply", "2026-09-09"),
            _old("oakmere_tove", "gone_cold", "2026-10-26"),
            {"contact_id": "own", "name": "Own", "status": "awaiting_reply",
             "next_action": "Ask about the depot in March", "next_action_due": "2027-03-01"}]
    found = [p["contact_id"] for p in state.reconcile(book, []) if p["reason"] == "stop_line_dated"]
    assert found == ["brindle_corwin", "ashby_mira", "oakmere_tove"], found
    said = state.undate_stop_lines(book)
    assert len(said) == 3, said
    for c in book[:3]:
        assert c["next_action"] == STOP and c["next_action_due"] == "", c
    assert book[3]["next_action_due"] == "2027-03-01"                      # the person's own
    assert state.undate_stop_lines(book) == []
    assert not [p for p in state.reconcile(book, []) if p["reason"] == "stop_line_dated"]


def test_a_line_of_the_persons_own_that_starts_the_same_way_keeps_its_date():
    """The review of 2026-11-11: the check read the stop line as a prefix, so a line the person
    wrote on, with a plan and a day of their own, lost its day; only the app's own line, whole,
    is undated."""
    own = {"contact_id": "oakmere_tove", "name": "Tove Ostler", "status": "awaiting_reply",
           "next_action": ("No reply to 2 messages: leave it unless they write back. She is on "
                           "leave until December; I'll try her once more on the 1st"),
           "next_action_due": "2026-12-01"}
    assert not state.stop_line_dated(own)
    assert state.undate_stop_lines([own]) == []
    assert own["next_action_due"] == "2026-12-01"
    assert not [p for p in state.reconcile([own], []) if p["reason"] == "stop_line_dated"]
