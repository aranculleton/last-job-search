"""Nobody is owed a follow-up message who cannot receive one.

From a person's repo, 2026-11-04: the follow-up clock listed people whose connection request
nobody accepted and people who had only been sent an InMail and never answered. An unaccepted
request has nowhere to write (at most it is a request to withdraw); an InMail is how LinkedIn
lets you write to a stranger, and a second one is a second InMail, never a free follow-up.
`state.owed` is the one place this is decided; /reply's `nudge_due` reads the same answer.
Every name here is invented.
"""
import datetime
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tools" / "network")]

import reply  # noqa: E402
import state  # noqa: E402

TODAY = datetime.date(2026, 10, 23)


def _c(cid, name):
    row = {k: "" for k in state.schema.CONTACT_COLUMNS}
    row.update({"contact_id": cid, "name": name, "company": "Kestrel Mutual"})
    return row


def _m(cid, day, direction, text, **kw):
    return dict({"contact_id": cid, "date": day, "direction": direction, "channel": "message",
                 "scenario": "", "summary": text[:40], "full_text": text, "subject": ""}, **kw)


def _nudges(threads, cid):
    contacts = [_c(cid, "Tamsin Oyelaran")]
    return [i for i in state.owed(contacts, threads, TODAY) if i["kind"] == "nudge"]


def test_a_connected_person_who_has_not_answered_is_still_owed_a_follow_up():
    threads = [_m("k1", "2026-10-01", "out", "Hi Tamsin, how is the team set up?")]
    assert len(_nudges(threads, "k1")) == 1


def test_someone_only_ever_sent_an_inmail_is_not_owed_a_follow_up():
    threads = [_m("k1", "2026-10-01", "out", "Hi Tamsin, how is the team set up?",
                  channel="inmail", subject="Pricing at Kestrel")]
    assert _nudges(threads, "k1") == []
    why = reply.nudge_due(threads, TODAY)
    assert not why["due"] and "InMail" in why["reason"]


def test_a_request_nobody_accepted_then_an_inmail_is_still_not_a_follow_up():
    threads = [dict(_m("k1", "2026-09-20", "out", "Hi Tamsin"), channel="connection",
                    scenario="connection_request"),
               _m("k1", "2026-10-01", "out", "Hi Tamsin, a question", channel="inmail")]
    assert _nudges(threads, "k1") == []


def test_a_request_nobody_accepted_is_never_a_nudge():
    threads = [dict(_m("k1", "2026-10-01", "out", "Hi Tamsin"), channel="connection",
                    scenario="connection_request")]
    assert _nudges(threads, "k1") == []
    assert not reply.nudge_due(threads, TODAY)["due"]


def test_an_inmail_that_was_accepted_or_answered_is_back_to_normal():
    sent = _m("k1", "2026-10-01", "out", "Hi Tamsin, a question", channel="inmail")
    accepted = _m("k1", "2026-10-02", "in", "", channel="connection",
                  scenario="connection_accepted")
    assert len(_nudges([sent, accepted], "k1")) == 1
    assert not state.inmail_only([sent, accepted])
