"""Every reader of the tracker agrees on what a status means.

The status vocabulary was hand-copied into four files: `throttle.FINAL`,
`what_works.WIN` and `LOSS`, `followups.LIVE_PROCESS` and `open_actions.HEAT`. The copies
had drifted once already (open_actions keyed on `interviewing` while the tracker wrote
`interview`, so an employer mid-interview sorted below a booked call), and they still
disagreed: a row spelled `interviewing` was a live process to the follow-ups and the
employer view, and silence to the throttle (which stopped holding its employer after 45
days) and nothing at all to what_works. One vocabulary now, in throttle.py, and these
read it.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "network"))

import datetime  # noqa: E402

import followups  # noqa: E402
import open_actions  # noqa: E402
import state  # noqa: E402
import throttle  # noqa: E402
import what_works as W  # noqa: E402

TODAY = datetime.date(2026, 10, 21)
SPELLINGS = ("drafted", "applied", "interview", "interviewing", "offer", "hired", "rejected",
             "no_response", "no response", "offer_declined", "offer declined", "withdrawn")


def _row(status):
    return {"date": "2026-06-01", "company": "Larkspur Retail", "role": "Planning Analyst",
            "status": status, "notes": ""}


def _live_to_followups(status):
    return bool(followups.live_processes([_row(status)], {}))


def _live_to_throttle(status):
    # A live process is never silence, however old: an older row that is not live is.
    return not throttle.is_silent(_row(status), TODAY)


def _won(status):
    got = W.application_cases([_row(status)], TODAY)
    return bool(got) and got[0]["won"]


def test_live_means_the_same_to_the_follow_ups_the_throttle_and_the_employer_view():
    for status in SPELLINGS:
        live = status in throttle.LIVE_PROCESS
        assert _live_to_followups(status) == live, status
        if status not in throttle.FINAL | throttle.UNSENT:
            assert _live_to_throttle(status) == live, status
        assert (open_actions.HEAT.get(status) == 100) == live, status


def test_an_older_spelling_is_the_status_it_spells():
    for old, new in throttle.LEGACY_SPELLINGS.items():
        for name in ("FINAL", "LIVE_PROCESS", "REACHED_INTERVIEW", "LOST"):
            group = getattr(throttle, name)
            assert (old in group) == (new in group), (old, name)
    assert _live_to_throttle("interviewing") and _won("interviewing")


def test_what_works_counts_by_the_same_vocabulary():
    for status in SPELLINGS:
        if status in throttle.REACHED_INTERVIEW:
            assert _won(status), status
        elif status in throttle.LOST:
            assert W.application_cases([_row(status)], TODAY)[0]["won"] is False, status
    assert W.WIN == throttle.REACHED_INTERVIEW and W.LOSS == throttle.LOST


def test_final_is_one_set_everywhere():
    assert open_actions.FINAL == throttle.FINAL == set(state.TRACKER_FINAL)
    assert followups.LIVE_PROCESS == throttle.LIVE_PROCESS
    assert set(throttle.STATUSES) <= (throttle.FINAL | throttle.LIVE_PROCESS
                                      | throttle.UNSENT | {"applied"})
