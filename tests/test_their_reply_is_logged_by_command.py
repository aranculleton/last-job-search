"""Their reply goes into the message log by command, with their words.

/reply step 6 says their message is logged at once, and there was no command for it:
every chat wrote the row into network_threads.csv by hand, some without the words, so the
message could never be read again or count as a reply that worked (networking audit,
2026-10-25). `state.py received` writes it the way the LinkedIn download's import does.
Invented people and employers throughout.
"""
from __future__ import annotations

import csv
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import schema  # noqa: E402
import state  # noqa: E402

CID = "kestrel_mutual_rook"


def _book(status="awaiting_reply", action="One nudge if no reply", due="2026-10-30"):
    contacts = [{"contact_id": CID, "name": "Ana Rook", "company": "Kestrel Mutual",
                 "status": status, "channel": "connection", "first_contacted": "2026-10-20",
                 "next_action": action, "next_action_due": due}]
    threads = [{"contact_id": CID, "date": "2026-10-20", "direction": "out",
                "channel": "connection", "scenario": "connection_note",
                "summary": "Connection request with a note", "full_text": "Hi Ana, a note.",
                "subject": ""}]
    return contacts, threads


def test_their_message_is_logged_inbound_with_its_words_and_a_reply_is_owed():
    contacts, threads = _book()
    words = "Happy to chat next week. Would Tuesday afternoon work for a quick call?"
    got = state.received(contacts, threads, CID, "2026-10-24", text=words)
    row = got["row"]
    assert row["direction"] == "in" and row["full_text"] == words
    assert row["date"] == "2026-10-24"
    assert row["channel"] == "message"          # an answer to a request comes as a message
    assert row["summary"].startswith("They replied")
    assert row["scenario"]                       # read the way /reply reads it
    assert contacts[0]["status"] == "replied_needs_response"
    # The app's own "nudge if no reply" line is over: a reply is owed now.
    assert contacts[0]["next_action"] == "" and contacts[0]["next_action_due"] == ""
    assert state.they_spoke_last(state.threads_for(threads, CID))


def test_the_scenario_step_two_read_is_kept_and_a_click_is_refused():
    contacts, threads = _book()
    got = state.received(contacts, threads, CID, "2026-10-24", scenario="calendar link",
                         text="Tuesday at 3 works, here is my calendar.")
    assert got["row"]["scenario"] == "calendar_link"
    for click in ("connection_accepted", "invitation"):
        with pytest.raises(ValueError, match="not a message"):
            state.received(contacts, threads, CID, "2026-10-25", scenario=click,
                           text="Another message.")


def test_an_out_of_office_is_logged_as_one_and_owes_nothing():
    contacts, threads = _book()
    got = state.received(contacts, threads, CID, "2026-10-21",
                         text="I am out of the office until 3 November with limited access "
                              "to email.")
    assert got["row"]["summary"].startswith("Automatic reply")
    assert contacts[0]["status"] == "awaiting_reply"
    assert contacts[0]["next_action"] == "One nudge if no reply"


def test_a_persons_own_line_and_a_status_the_log_cannot_know_are_left():
    contacts, threads = _book(status="call_booked", action="Call Thursday 14:00",
                              due="2026-10-29")
    got = state.received(contacts, threads, CID, "2026-10-24",
                         text="Looking forward to Thursday. I will send an invite.")
    assert contacts[0]["status"] == "call_booked"
    assert contacts[0]["next_action"] == "Call Thursday 14:00"
    assert "call_booked" in got["said"] and "state.py set" in got["said"]


def test_no_words_no_contact_and_the_same_words_twice_are_refused():
    contacts, threads = _book()
    with pytest.raises(ValueError, match="their words are needed"):
        state.received(contacts, threads, CID, "2026-10-24", text="  ")
    with pytest.raises(ValueError, match="no contact"):
        state.received(contacts, threads, "nobody_here", "2026-10-24", text="Hello")
    state.received(contacts, threads, CID, "2026-10-24", text="Thanks, speak soon.")
    with pytest.raises(ValueError, match="already logged"):
        state.received(contacts, threads, CID, "2026-10-24", text="Thanks, speak soon.")


def test_the_command_writes_both_files(tmp_path):
    contacts, threads = _book()
    cpath, tpath = tmp_path / "contacts.csv", tmp_path / "threads.csv"
    state.save_contacts(contacts, str(cpath))
    state.save_threads(threads, str(tpath))
    msg = tmp_path / "theirs.txt"
    msg.write_text("Thanks for reaching out. Happy to talk on Friday.", encoding="utf-8")
    code = state.main(["received", CID, "--text-file", str(msg), "--date", "2026-10-24",
                       "--contacts", str(cpath), "--threads", str(tpath),
                       "--today", "2026-10-24"])
    assert code == 0
    with open(tpath, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert list(rows[0]) == schema.THREAD_COLUMNS
    assert rows[-1]["direction"] == "in"
    assert rows[-1]["full_text"] == "Thanks for reaching out. Happy to talk on Friday."
    assert state.load_contacts(str(cpath))[0]["status"] == "replied_needs_response"


def test_the_reply_command_and_the_skill_name_it():
    for rel in (".claude/commands/reply.md", ".claude/skills/networking/SKILL.md"):
        with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
            assert "state.py received" in fh.read(), rel
