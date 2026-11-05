"""A contact kept "Talking" with no word of theirs in the log reads as what the log shows.

The maintainer, 2026-11-05: a contact imported from earlier notes as in_conversation
("varying engagement") had one logged message, our own request, which the LinkedIn export
showed was never accepted. The stored status won, as for any status the log cannot work out,
and the page queued "Write to <name>" off a reply never sent. With rows in the log and nothing
from them, the log wins: awaiting_reply, or connected_no_reply where Connections.csv has them.
The check says so as an error, never a note.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "network"))

import export  # noqa: E402
import state  # noqa: E402

REQUEST = {"contact_id": "calder_reed", "date": "2026-08-27", "direction": "out", "channel": "linkedin",
           "scenario": "connection_request", "summary": "Connection request with a note"}
REED = {"contact_id": "calder_reed", "name": "Sasha Reed", "company": "Calder Bank", "status": "in_conversation",
        "linkedin_url": "https://www.linkedin.com/in/example-sasha-reed/"}

# LinkedIn's own Connections.csv: a Notes block, a blank line, then the header.
NOTES = ('Notes:\r\n"When exporting your connection data, you may notice that some of the email addresses are '
         'missing. You will only see email addresses for connected members who have allowed their connections '
         'to see or download their email address using this setting https://www.linkedin.com/psettings/privacy/'
         'email. You can learn more here https://www.linkedin.com/help/linkedin/answer/261"\r\n\r\n'
         'First Name,Last Name,URL,Email Address,Company,Position,Connected On\r\n')


def _connections(tmp_path, *rows):
    p = tmp_path / "Connections.csv"
    p.write_text(NOTES + "".join(r + "\r\n" for r in rows), encoding="utf-8")
    return str(p)


def test_talking_with_only_our_unaccepted_request_reads_as_awaiting_reply(tmp_path, monkeypatch):
    path = _connections(tmp_path, "Robin,Vale,https://www.linkedin.com/in/example-robin-vale,,Other Co,Analyst,03 Oct 2026")
    monkeypatch.setattr(state.person, "local_state", lambda *a: path)
    assert state.effective_status(REED, [REQUEST]) == "awaiting_reply"
    found = [p for p in state.reconcile([REED], [REQUEST]) if p["contact_id"] == "calder_reed"]
    assert [p["reason"] for p in found] == ["no_word_from_them"], found
    assert "no_word_from_them" not in state.NOTE_ONLY


def test_connected_on_linkedin_reads_as_connected_no_reply(tmp_path, monkeypatch):
    path = _connections(tmp_path, "Sasha,Reed,https://www.linkedin.com/in/example-sasha-reed,,Calder Bank,Analyst,03 Oct 2026")
    monkeypatch.setattr(state.person, "local_state", lambda *a: path)
    assert state.effective_status(REED, [REQUEST]) == "connected_no_reply"
    # By name too, where the row has no profile address.
    assert state.effective_status({**REED, "linkedin_url": ""}, [REQUEST]) == "connected_no_reply"
    for status in ("in_conversation", "call_booked"):
        assert state.effective_status({**REED, "status": status}, [REQUEST]) == "connected_no_reply"


def test_a_word_or_a_call_from_them_keeps_the_conversation(tmp_path, monkeypatch):
    monkeypatch.setattr(state.person, "local_state", lambda *a: str(tmp_path / "none.csv"))
    theirs = {**REQUEST, "date": "2026-09-02", "direction": "in", "scenario": "reply", "channel": "linkedin_dm",
              "summary": "Happy to chat next week"}
    ours = {**REQUEST, "date": "2026-09-03", "scenario": "reply", "channel": "linkedin_dm", "summary": "Thanks"}
    assert state.effective_status(REED, [REQUEST, theirs, ours]) == "in_conversation"
    call = {**REQUEST, "date": "2026-09-10", "direction": "in", "channel": "call", "scenario": "call_held",
            "summary": "Call held"}
    assert state.effective_status({**REED, "status": "call_booked"}, [REQUEST, call]) == "call_booked"
    assert not [p for p in state.reconcile([REED], [REQUEST, theirs, ours]) if p["reason"] == "no_word_from_them"]
    # A relationship that predates the log, with no rows at all, stays as it was: a note.
    assert state.effective_status(REED, []) == "in_conversation"
    assert [p["reason"] for p in state.reconcile([REED], [])] == ["history_not_logged"]


def test_the_export_reader_skips_linkedins_notes_block(tmp_path):
    path = _connections(tmp_path, "Sasha,Reed,https://www.linkedin.com/in/example-sasha-reed,,Calder Bank,Analyst,03 Oct 2026")
    got = export.read("connections", path)
    assert got["usable"] and len(got["rows"]) == 1, got
    assert [c["name"] for c in state.first_degree(path)] == ["Sasha Reed"]


def test_the_persons_own_word_or_a_booked_call_keeps_the_status(tmp_path, monkeypatch):
    # "In touch another way" on the page, or a call booked: the person said so, and that is
    # the evidence the log cannot hold.
    monkeypatch.setattr(state.person, "local_state", lambda *a: str(tmp_path / "none.csv"))
    row = {**REED, "status": "awaiting_reply"}
    state.set_contact([row], [REQUEST], "calder_reed", status="in_conversation", today="2026-11-05")
    assert state.effective_status(row, [REQUEST]) == "in_conversation", row
    assert not [p for p in state.reconcile([row], [REQUEST]) if p["reason"] == "no_word_from_them"]
    booked = {**REED, "status": "call_booked", "next_action": "Call on 2026-11-12 at 12:30: prepare for it",
              "next_action_due": "2026-11-12"}
    assert state.effective_status(booked, [REQUEST]) == "call_booked"
    over = {**REED, "next_action": "Call on 2026-11-01 is over: thank them and ask how it went"}
    assert state.effective_status(over, [REQUEST]) == "in_conversation"
