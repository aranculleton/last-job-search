"""A late reply to a thread gone cold is a reply owed.

`gone_cold` is what the app tells the person to set when a nudge drew nothing. It was
terminal whatever the log said, so when they did answer, weeks later, through the LinkedIn
download or a row logged by hand, nothing was owed: the due list said "0 replies owed" while
they waited. Only `state.py received` reopened it. Every name here is invented.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tools" / "network")]

import export as E  # noqa: E402
import open_actions  # noqa: E402
import state  # noqa: E402

CID = "acme_halloway"


def _contact(**kw):
    return dict({"contact_id": CID, "name": "Wren Halloway", "company": "Acme",
                 "status": "gone_cold", "first_contacted": "2026-09-01", "next_action": "",
                 "next_action_due": "", "notes": "", "outcome": ""}, **kw)


def _msg(date, direction, text):
    return {"contact_id": CID, "date": date, "direction": direction, "channel": "message",
            "scenario": "", "summary": "", "full_text": text}


COLD = [_msg("2026-09-01", "out", "Hi Wren, hope you're well."),
        _msg("2026-09-10", "out", "Hi Wren, just following up on my note.")]
LATE = _msg("2026-10-15", "in", "Sorry for the slow reply! Happy to chat next week, what "
            "times suit?")


def test_a_reply_logged_by_hand_is_owed():
    contacts, threads = [_contact()], COLD + [LATE]
    assert state.effective_status(contacts[0], threads) == "replied_needs_response"
    assert [i["kind"] for i in state.owed(contacts, threads, "2026-10-16")] == ["reply"]
    due = open_actions.render_due(open_actions.due_items(contacts, threads, [], "2026-10-16"),
                                  "2026-10-16")
    assert "Wren Halloway" in due


def test_a_reply_the_download_brought_reopens_the_thread():
    contacts, threads = [_contact()], COLD + [LATE]
    assert E.settle(contacts, threads, {CID}) == [(CID, "gone_cold", "replied_needs_response")]
    assert contacts[0]["status"] == "replied_needs_response"


def test_silence_and_a_close_after_their_last_word_stay_closed():
    assert state.effective_status(_contact(), COLD) == "gone_cold"
    assert state.owed([_contact()], COLD, "2026-10-16") == []
    # Closed after reading it, on purpose or with the day written.
    for kept in (_contact(notes="2026-10-16: closed on purpose, not a fit"),
                 _contact(outcome="closed 2026-10-16 by the candidate")):
        assert state.effective_status(kept, COLD + [LATE]) == "gone_cold"
        assert E.settle([kept], COLD + [LATE], {CID}) == []
    # The person's own closes are theirs to judge: reported, never undone.
    closed = _contact(status="closed")
    assert state.effective_status(closed, COLD + [LATE]) == "closed"
    assert [p["reason"] for p in state.reconcile([closed], COLD + [LATE])] == ["reopened"]
