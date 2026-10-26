"""A connection request nobody has accepted is never listed overdue.

Sending a request writes "Once they accept: one nudge if no reply. Withdraw the request if
nobody accepts in 21 days" with a date six working days out, and the due list then put the
person under "Overdue" (and on the phone's first line) with "Once they accept" as the thing
to do, though nothing can be sent until they accept. A request is listed once, to withdraw,
after 21 days. Every name here is invented.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tools" / "network")]

import open_actions  # noqa: E402
import state  # noqa: E402

CID = "acme_halloway"


def _sent():
    contacts = [{"contact_id": CID, "name": "Wren Halloway", "company": "Acme", "status": "",
                 "first_contacted": ""}]
    threads = []
    state.sent(contacts, threads, CID, "2026-10-01", text="Hi Wren, I work in analytics.",
               channel="connection")
    return contacts, threads


def test_the_apps_own_line_on_a_waiting_request_is_not_due():
    contacts, threads = _sent()
    assert contacts[0]["next_action"].startswith("Once they accept")
    for day in ("2026-10-09", "2026-10-12", "2026-10-21"):
        assert state.owed(contacts, threads, day) == [], day
    due = open_actions.render_due(open_actions.due_items(contacts, threads, [], "2026-10-14"),
                                  "2026-10-14")
    assert "Wren Halloway" not in due and "Once they accept" not in due
    assert [i["kind"] for i in state.owed(contacts, threads, "2026-10-23")] == ["request_pending"]


def test_a_date_the_person_set_on_a_waiting_request_is_still_owed():
    contacts, threads = _sent()
    contacts[0]["next_action"] = "Email her the deck if the request sits"
    contacts[0]["next_action_due"] = "2026-10-08"
    assert [i["kind"] for i in state.owed(contacts, threads, "2026-10-12")] == ["action_due"]
