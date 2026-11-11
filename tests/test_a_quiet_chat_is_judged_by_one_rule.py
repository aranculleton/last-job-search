"""Work a chat runs itself is called quiet by one rule, with a lease or without.

The audit of 2026-11-10 (PE-12): with a lease, work was quiet a whole lease after its lease
ended; without one, the moment its claim stopped being live, and from its stage's start even
where its claim came later. Both now end the same way: live until a lease after its last word
(or its lease), quiet a lease after that. Every chat here is invented.
"""
from __future__ import annotations

import datetime as dt
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import app_model  # noqa: E402
import page_db  # noqa: E402

T = dt.datetime(2026, 11, 10, 12, 0, tzinfo=dt.timezone.utc)
L = dt.timedelta(seconds=page_db.LEASE_S)


def _at(t):
    return app_model.stamp(t)


def _item(**kw):
    return dict({"kind": "talk", "status": "running", "claimed_by": "session_c1", "in_chat": True}, **kw)


def _quiet_from(item):
    """The first minute at which it is live no more, and the first it is quiet."""
    live = quiet = None
    for m in range(0, 200):
        now = T + dt.timedelta(minutes=m)
        if live is None and not page_db._live_claim(item, now):
            live = m
        if quiet is None and page_db._chat_quiet(item, now):
            quiet = m
    return live, quiet


def test_with_a_lease_and_without_it_is_quiet_a_lease_after_it_stops_being_live():
    with_lease = _item(claimed_at=_at(T), stage_at=_at(T), lease_until=_at(T + L))
    without = _item(claimed_at=_at(T), stage_at=_at(T))
    lease = page_db.LEASE_S // 60
    assert _quiet_from(with_lease) == (lease, 2 * lease)
    assert _quiet_from(without) == (lease, 2 * lease)


def test_without_a_lease_its_last_word_counts_not_its_first():
    late_claim = _item(stage_at=_at(T - dt.timedelta(minutes=50)), claimed_at=_at(T))
    lease = page_db.LEASE_S // 60
    assert _quiet_from(late_claim) == (lease, 2 * lease)
