"""A follow-up the person set themselves is ready, never overdue; only someone else's date is.

The UX review of 2026-11-10 (U-6): self-set networking nudges read as failures, "Overdue", "34
days late" and "0 of 7 done", the Brief opening on "Overdue" for a follow-up to a stranger. Past
its day, a nudge, a follow-up or a message to send is now "Ready to send" (or "Ready to do"), a
checklist counts what is left in its title (its pill said it again, "7 to send", until the screen
review of 2026-11-11), and only a date someone else set (an application closing, a test, a
reply-by) is overdue. Every person and employer is invented.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest  # noqa: E402

import test_the_page_journeys as journeys  # noqa: E402
from test_a_question_is_answered_on_its_card import _busier  # noqa: E402
from test_the_page_journeys import PHONE, WIDE, _go  # noqa: E402

T = "2026-10-25T09:00:00Z"
TODO = "document.querySelector('#main').textContent"


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


def _late(model, days=34, kind="follow_up"):
    for d in model["due"]:
        if str(d.get("id", "")).startswith("due-more-"):
            d.update(due="2026-09-21", overdue_days=days, sub="follow_up", kind=kind)
    return model


@pytest.mark.parametrize("vp", [PHONE, WIDE], ids=["phone", "wide"])
def test_follow_ups_past_their_day_are_ready_and_counted_as_left(run, tmp_path, vp):
    got = _go(run, tmp_path, [{"hash": "todo", "eval": TODO}], vp, model=_late(_busier()), clock=T)
    text = got["after"][0]["eval"]
    # What is left is the title's count; its pill no longer says "3 to do" again (the screen
    # review of 2026-11-11, row 28).
    assert "Follow up on 3 applications" in text and "3 to do" not in text and "0 of 3 done" not in text, text
    assert "3 overdue" not in text and "34 days late" not in text, text


def _row(did, sub, title, days):
    """A due row as the engine writes it (tools/app_model.py _due): an interview's, by its sub."""
    return {"id": did, "kind": "interview", "sub": sub, "title": title, "context": "",
            "due": "2026-10-%02d" % (25 - days), "overdue_days": days, "action": "work:follow_up",
            "company": "Harbourline Bank", "item": None, "work": None,
            "done": {"action": "due.done", "label": "Done"}, "rev": did}


def test_engine_shaped_rows_say_ready_and_only_a_test_or_a_choice_is_late(run, tmp_path):
    """The review of 2026-11-11: keyed on kinds the engine never writes, a thank-you and "No word
    since your last update" still said "21 days late"; only an interview's test to sit or day to
    choose is someone else's date."""
    m = _busier()
    m["due"] += [_row("due-interview-hb-note", "status_note", "No word from Harbourline Bank since your last update", 21),
                 _row("due-interview-hb-thanks", "thank_you", "Thank-you note after your Harbourline Bank interview", 2),
                 dict(_row("due-interview-hb-test", "test", "Sit the Harbourline Bank numeracy test", 3), action="go:interviews")]
    got = _go(run, tmp_path, [{"hash": "todo", "eval": TODO}], WIDE, model=m, clock=T)
    text = got["after"][0]["eval"]
    assert "21 days late" not in text and "2 days late" not in text, text
    assert "3 days late" in text or "Overdue" in text, text
