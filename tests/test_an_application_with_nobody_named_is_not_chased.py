"""An application with nobody to write to is never offered as a follow-up to send.

One person's 64 applications had no named recruiter; 40 of them sat in To do as nudges the
drafter then refused ("no recipient on file"). A chase nobody can receive is not a job, so
the row stays unlisted until a name, an outreach note or a reply at the employer exists.
"""
from __future__ import annotations

import datetime
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import followups  # noqa: E402
import open_actions  # noqa: E402

D = datetime.date
ROW = {"company": "Quayside Foods", "role": "Lifecycle Marketing Manager",
       "date": "2026-11-03", "applied_on": "2026-11-03", "status": "applied",
       "contact_person": "", "notes": "", "deadline": ""}
TODAY = D(2026, 11, 14)


def _review(row, warm=None):
    return followups.review([dict(row)], TODAY, warm=warm or {}, holds={}, docs="/nonexistent")[0]


def test_nobody_named_means_nothing_to_send_and_nothing_in_to_do():
    assert _review(ROW)["state"] == "unnamed"
    assert followups.due([dict(ROW)], TODAY, docs="/nonexistent") == []
    items = open_actions.due_items([], [], [dict(ROW)], TODAY)
    assert [i for i in items if i["half"] == "application"] == []


def test_the_same_row_is_due_the_day_somebody_is_named():
    it = _review(dict(ROW, contact_person="Wren Castellan"))
    assert it["state"] == "due" and it["to"]["name"] == "Wren"


def test_a_reply_at_the_employer_is_somebody_to_write_to():
    key = followups.company_key(ROW["company"])
    it = _review(ROW, warm={key: [{"name": "Juno Pell", "status": "in_conversation"}]})
    assert it["state"] == "due"


def test_an_unnamed_row_still_goes_quiet_by_age():
    old = dict(ROW, date="2026-08-01", applied_on="2026-08-01")
    assert _review(old)["state"] == "quiet"
