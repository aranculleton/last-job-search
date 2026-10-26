"""Progress counts a reply only when someone answered the person (the maintainer, 2026-10-26).

A LinkedIn history imported whole holds years of other conversations; counting every
message that came in said 359 replies. A reply is a message back after one of theirs, from
someone in the contact book, and the first view is the last 30 days.
"""
from __future__ import annotations

import datetime as dt
import os
import sys
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import app_model  # noqa: E402

TODAY = dt.date(2026, 10, 26)


def _ctx(threads, contacts, tracker=()):
    return SimpleNamespace(tracker=list(tracker), threads=threads, contacts=contacts, today=TODAY, _got={})


def _row(cid, date, direction, text="Happy to have a chat next week, what suits you?"):
    return {"contact_id": cid, "date": date, "direction": direction, "channel": "linkedin_message",
            "summary": text, "full_text": text}


def test_a_message_in_with_nothing_sent_first_is_not_a_reply():
    book = [{"contact_id": "ana"}, {"contact_id": "bo"}, {"contact_id": "cy"}]
    threads = [
        _row("ana", "2026-10-01", "out"), _row("ana", "2026-10-03", "in"),      # a reply, this month
        _row("bo", "2025-03-01", "in"),                                        # they wrote first, long ago
        _row("cy", "2026-01-05", "out"), _row("cy", "2026-01-09", "in"),       # a reply, months ago
        _row("dee", "2026-10-02", "out"), _row("dee", "2026-10-04", "in"),     # not in the contact book
    ]
    done = app_model._done(_ctx(threads, book), {})
    assert done["counts"]["replies"] == 2
    assert done["recent"]["counts"]["replies"] == 1 and done["recent"]["days"] == 30


def test_the_last_30_days_count_what_was_sent_in_them():
    tracker = [{"company": "Acme", "role": "Analyst", "status": "applied", "applied_on": "2026-10-10"},
               {"company": "Birch", "role": "Analyst", "status": "interview", "applied_on": "2026-06-01"}]
    done = app_model._done(_ctx([], [], tracker), {})
    assert done["counts"]["applied"] == 2 and done["recent"]["counts"]["applied"] == 1
    assert done["recent"]["funnel"][0] == {"stage": "applied", "n": 1}
