"""LinkedIn's download dates messages in UTC; the app dates them on the person's own clock.

East of UTC the two disagree for part of every day. A person in Sydney logged a first note on
15 October (09:05 there); the download had it at 22:05 UTC on the 14th and the answer at
23:10 UTC on the 14th, which was added on the 14th, before the note it answered. The thread
read as waiting on them, the reply owed disappeared and a nudge was offered to someone who
had said "happy to chat". Every name and message here is invented.
"""
import datetime
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tools" / "network")]

import export as E  # noqa: E402
import state  # noqa: E402

CID = "fernhill_freight_halloway"
URL = "https://www.linkedin.com/in/example-wren-halloway"
MINE = "https://www.linkedin.com/in/example-morgan-ellis"
HEAD = ("CONVERSATION ID,CONVERSATION TITLE,FROM,SENDER PROFILE URL,TO,RECIPIENT PROFILE URLS,"
        "DATE,SUBJECT,CONTENT,FOLDER,ATTACHMENTS\n")


def _line(frm, frm_url, to, to_url, when, text):
    return f'c1,,{frm},{frm_url},{to},{to_url},{when},,"{text}",INBOX,\n'


SYDNEY, TORONTO = datetime.timedelta(hours=11), datetime.timedelta(hours=-4)   # in October


@pytest.fixture
def zone(monkeypatch):
    """The person's clock, as a fixed offset: no zone data needed, on any computer."""
    def use(offset):
        monkeypatch.setattr(E, "HERE", datetime.timezone(offset))
    return use


def _contacts():
    return [{"contact_id": CID, "name": "Wren Halloway", "company": "Fernhill Freight",
             "linkedin_url": URL, "status": "awaiting_reply", "first_contacted": "2026-10-15",
             "channel": "message"}]


NOTE = "Hi Wren, hope you're well. How is the planning team set up for peak?"
ANSWER = "Hi Morgan, happy to chat. Does Thursday work?"


def test_a_reply_never_sorts_before_the_message_it_answers(tmp_path, zone):
    zone(SYDNEY)
    (tmp_path / "messages.csv").write_text(
        HEAD + _line("Morgan Ellis", MINE, "Wren Halloway", URL, "2026-10-14 22:05:00 UTC", NOTE)
        + _line("Wren Halloway", URL, "Morgan Ellis", MINE, "2026-10-14 23:10:00 UTC", ANSWER),
        encoding="utf-8")
    contacts = _contacts()
    threads = [{"contact_id": CID, "date": "2026-10-15", "direction": "out",
                "channel": "message", "scenario": "first_note", "summary": "First note sent",
                "full_text": NOTE}]
    plan = E.plan_history(contacts, threads, src=str(tmp_path),
                          mine=("example-morgan-ellis", "morgan_ellis"))
    assert [(r["date"], r["direction"]) for r in plan["add"]] == [("2026-10-15", "in")]
    E.apply_history(threads, plan, contacts)
    rows = state.threads_for(threads, CID)
    assert [(r["date"], r["direction"]) for r in rows] == [("2026-10-15", "out"),
                                                            ("2026-10-15", "in")]
    assert state.effective_status(contacts[0], rows) == "replied_needs_response"
    assert [i["kind"] for i in state.owed(contacts, threads, "2026-10-26")] == ["reply"]


def test_two_messages_on_one_day_are_in_the_order_they_were_sent(tmp_path, zone):
    zone(SYDNEY)
    # Newest first, the way a download can list them, and both on the 16th in Sydney.
    (tmp_path / "messages.csv").write_text(
        HEAD + _line("Wren Halloway", URL, "Morgan Ellis", MINE, "2026-10-15 23:10:00 UTC", ANSWER)
        + _line("Morgan Ellis", MINE, "Wren Halloway", URL, "2026-10-15 22:05:00 UTC", NOTE),
        encoding="utf-8")
    contacts, threads = _contacts(), []
    plan = E.plan_history(contacts, threads, src=str(tmp_path),
                          mine=("example-morgan-ellis", "morgan_ellis"))
    assert [(r["date"], r["direction"]) for r in plan["add"]] == [("2026-10-16", "out"),
                                                                  ("2026-10-16", "in")]


def test_a_stated_zone_is_read_on_this_clock_and_any_other_date_as_written(zone):
    zone(SYDNEY)
    assert E.day("2026-10-14 23:10:00 UTC") == datetime.date(2026, 10, 15)
    assert E.clock("2026-10-14 23:10:00 UTC") == "10:10"
    assert E.day("2026-10-14T23:10:00+11:00") == datetime.date(2026, 10, 14)
    zone(TORONTO)
    assert E.day("2026-10-15 02:30:00 UTC") == datetime.date(2026, 10, 14)
    assert E.clock("2026-10-15 02:30:00 UTC") == "22:30"
    # Invitations and connections state no zone: the day as written.
    assert E.day("10/15/26, 2:22 AM") == datetime.date(2026, 10, 15)
    assert E.day("15 Oct 2026") == datetime.date(2026, 10, 15)
    assert E.day("2026-10-15") == datetime.date(2026, 10, 15)


def test_with_no_zone_named_it_is_this_computers_own():
    assert E.HERE is None
    at = datetime.datetime(2026, 10, 14, 23, 10, tzinfo=datetime.timezone.utc).astimezone()
    assert E.day("2026-10-14 23:10:00 UTC") == at.date()
