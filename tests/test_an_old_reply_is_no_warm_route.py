"""A reply makes an employer a warm route while it is recent, or while the record says what it
is for: an old reply nobody did anything with is not a way in.

`warm_routes` counted every contact who had ever replied, so an employer-brand marketer's reply
from months before, with "no action recorded", put "DO NOT APPLY COLD" and a fit bonus on her
employer: 96 employers in one book, 93 of their rows with no action recorded (the audit of
2026-11-10, NW-18). A referral in flight or a call booked is a route whatever its age, and so
is a reply whose record carries a next step. Every person and employer is invented.
"""
from __future__ import annotations

import datetime
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import open_actions  # noqa: E402
import throttle  # noqa: E402

TODAY = datetime.date(2026, 11, 10)


def _c(cid, company, status, action=""):
    return {"contact_id": cid, "name": cid.title(), "company": company, "status": status,
            "next_action": action}


def _said(cid, day):
    return {"contact_id": cid, "date": day, "direction": "in", "channel": "message",
            "scenario": "reply", "summary": "a reply", "full_text": "Thanks, good to hear from you."}


BOOK = [_c("old", "Zephyr Dental", "in_conversation"),
        _c("recent", "Quayside Foods", "in_conversation"),
        _c("noted", "Kestrel Mutual", "in_conversation", "Apply via Noted's referral"),
        _c("referring", "Fernhill Freight", "referral_in_progress")]
LOG = [_said("old", "2026-09-01"), _said("recent", "2026-11-03"), _said("noted", "2026-08-01"),
       _said("referring", "2026-07-01")]


def test_an_old_reply_with_nothing_recorded_is_no_route():
    live = {c["contact_id"]: c["status"] for c in BOOK}
    got = throttle.warm_routes(rows=BOOK, live=live, threads=LOG, today=TODAY)
    assert sorted(got) == ["fernhill freight", "kestrel mutual", "quayside foods"], sorted(got)
    # The due list's own view reads the same.
    _live, warm, _holds = open_actions.network_views(BOOK, LOG, today=TODAY)
    assert "zephyr dental" not in warm and "quayside foods" in warm


def test_the_brief_reads_the_same_rule():
    """The brief kept a reader of its own (every contact who had replied, and no record that
    says one is not a way in): one rule now, throttle's, for the brief's in-play employers and
    its lead line."""
    import brief
    book = BOOK + [_c("parked", "Brindle Hart Logistics", "in_conversation",
                      "Parked: not a route, do not use him to chase")]
    log = LOG + [_said("parked", "2026-11-08")]
    got = sorted(w["company"] for w in brief._warm_routes(book, log, TODAY))
    assert got == ["Fernhill Freight", "Kestrel Mutual", "Quayside Foods"], got
    live = {c["contact_id"]: c["status"] for c in book}
    assert sorted(w["company"] for w in brief._warm_routes(book, log, TODAY)) == sorted(
        p["company"] for p in throttle.route_rows(book, live, log, TODAY))
