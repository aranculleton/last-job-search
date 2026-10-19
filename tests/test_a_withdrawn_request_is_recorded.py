"""A connection request the person withdrew is recorded, and the person is never written to again.

`/threads` listed a request nobody had accepted in three weeks as one to withdraw, and
nothing recorded the withdrawal: the request sat on that list for ever, and a row
logged by hand to say it was withdrawn read as one more message sent, so the thread
went on waiting for a reply and a nudge came due on it. The people here are invented.
"""
from __future__ import annotations

import csv
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "network"))

import reply  # noqa: E402
import schema  # noqa: E402
import state  # noqa: E402
import what_works  # noqa: E402

TODAY = "2026-10-15"
NOTE = "Hi Sasha, we were both at Leeds. Would you have 15 minutes for a few questions sometime?"


def _contact(**kw):
    return {"contact_id": "acme_reed", "name": "Sasha Reed", "company": "Acme",
            "channel": "connection", "status": "awaiting_reply", "first_contacted": "2026-09-01",
            "next_action": "nudge once they accept; withdraw after 21 days",
            "next_action_due": "2026-09-09", "outcome": "", **kw}


def _row(date, direction, scenario="", text="", channel="connection"):
    return {"contact_id": "acme_reed", "date": date, "direction": direction,
            "channel": channel, "scenario": scenario, "summary": "", "full_text": text}


def _kinds(contact, rows):
    return [i["kind"] for i in state.owed([contact], rows, TODAY)]


def test_a_withdrawal_in_the_log_closes_the_thread_and_owes_nothing():
    rows = [_row("2026-09-01", "out", "connection_note", NOTE),
            _row("2026-09-30", "out", "request_withdrawn")]
    # Read as one more message sent, it left the thread waiting and a nudge due on it.
    assert state.derive_status(rows) == "closed"
    assert state.effective_status(_contact(next_action=""), rows) == "closed"
    assert state.request_pending(rows) is None
    assert _kinds(_contact(next_action="", next_action_due=""), rows) == []
    got = reply.nudge_due(rows, TODAY)
    assert not got["due"] and "withdrawn" in got["reason"]
    # The contact row still saying awaiting_reply disagrees with the log, and says so.
    found = state.reconcile([_contact()], rows)
    assert [(p["reason"], p["derived"]) for p in found] == [("contradicts_log", "closed")]
    # Anything they say afterwards is a reply owed, whatever the withdrawal said.
    assert state.derive_status(rows + [_row("2026-10-02", "in", "", "Sorry, only just saw this!",
                                            channel="message")]) == "replied_needs_response"


def test_withdraw_records_it_and_closes_the_contact_with_the_date_and_why():
    contact = _contact()
    contacts, threads = [contact], [_row("2026-09-01", "out", "connection_note", NOTE)]
    assert _kinds(contact, threads) == ["request_pending"]
    row = state.withdraw(contacts, threads, "acme_reed", TODAY)
    assert threads[-1] is row
    assert (row["direction"], row["channel"], row["scenario"], row["date"]) == \
        ("out", "connection", "request_withdrawn", TODAY)
    assert row["summary"] == "Withdrew the connection request: not accepted in 44 days"
    assert contact["status"] == "closed" and not contact["next_action"] \
        and not contact["next_action_due"]
    assert contact["outcome"] == "request withdrawn 2026-10-15: not accepted in 44 days"
    assert state.closed_on(contact).isoformat() == TODAY
    assert _kinds(contact, threads) == []
    assert state.reconcile(contacts, threads) == []
    # Never surfaced again: still in the book, at the same employer and URL.
    assert state.already_contacted(contacts, name="Sasha Reed", company="Acme Inc.") is contact
    # Not a request spent, and not a message that went unanswered.
    assert state.connection_requests(contacts, threads) == {("acme_reed", state.as_date("2026-09-01"))}
    attempts = what_works.message_cases(contacts, threads, today=TODAY)
    assert [c["date"] for c in attempts] == ["2026-09-01"]


def test_there_is_nothing_to_withdraw_once_they_accepted_or_answered():
    for rows in ([_row("2026-09-01", "out", "connection_note", NOTE),
                  _row("2026-09-03", "in", "accepted_no_reply")],
                 [_row("2026-09-01", "out", "connection_note", NOTE),
                  _row("2026-09-03", "in", "", "Happy to talk", channel="message")],
                 [_row("2026-09-01", "out", "connection_note", NOTE),
                  _row("2026-09-30", "out", "request_withdrawn")]):
        with pytest.raises(ValueError, match="nothing to withdraw"):
            state.withdraw([_contact()], list(rows), "acme_reed", TODAY)
    with pytest.raises(ValueError, match="no contact"):
        state.withdraw([_contact()], [], "acme_nobody", TODAY)
    # The log behind the row: the request went, its message row did not.
    contact = _contact()
    threads = []
    state.withdraw([contact], threads, "acme_reed", TODAY, reason="the person tidied their invitations")
    assert threads[0]["summary"].endswith("the person tidied their invitations")


def _write(path, rows, columns):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=columns)
        w.writeheader()
        w.writerows({c: r.get(c, "") for c in columns} for r in rows)


def test_the_command_records_every_request_due_and_saves_both_files(tmp_path, capsys):
    contacts, threads = tmp_path / "c.csv", tmp_path / "t.csv"
    other = _contact(contact_id="acme_lee", name="Robin Lee", first_contacted="2026-10-10")
    _write(contacts, [_contact(), other], schema.CONTACT_COLUMNS)
    _write(threads, [_row("2026-09-01", "out", "connection_note", NOTE),
                     dict(_row("2026-10-10", "out", "connection_note", NOTE), contact_id="acme_lee")],
           schema.THREAD_COLUMNS)
    args = ["--contacts", str(contacts), "--threads", str(threads), "--today", TODAY]
    assert state.main(["withdraw", "--all-due", *args]) == 0
    out = capsys.readouterr().out
    assert "acme_reed" in out and "acme_lee" not in out and "1 recorded" in out
    saved = {c["contact_id"]: c for c in state.load_contacts(str(contacts))}
    assert saved["acme_reed"]["status"] == "closed"
    assert saved["acme_lee"]["status"] == "awaiting_reply"       # 5 days old: not due
    assert [r["scenario"] for r in state.load_threads(str(threads))][-1] == "request_withdrawn"
    # The list of what is owed names the command.
    _write(contacts, [_contact()], schema.CONTACT_COLUMNS)
    _write(threads, [_row("2026-09-01", "out", "connection_note", NOTE)], schema.THREAD_COLUMNS)
    state.main(args)
    assert "state.py withdraw acme_reed" in capsys.readouterr().out
