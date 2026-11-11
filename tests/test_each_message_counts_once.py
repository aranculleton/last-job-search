"""Each message to a person counts once toward every limit, in the order it happened.

The 2026-11-10 audit found the counts read from raw rows. A connection note was logged as a
request and again as a message (the note LinkedIn's download also lists in messages), so a
person written to once read as two unanswered messages: their one follow-up was withheld and
the row said "No more follow-ups" (NW-3). A follow-up logged by hand and the download's copy
of it, edited before it went, read as two (NW-4). An imported request appended at the foot of
the log sorted after the reply to it on the same day, and counted as a fresh unanswered
message (NW-14). Every person, employer and message here is invented.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "network"))

import state  # noqa: E402

CID = "quayside_foods_ivo"
NOTE = ("Hi Ivo, hope you're well. I'm an analyst who builds forecasting models, which I "
        "imagine is similar to the planning work at Quayside. I'd love to hear what you're "
        "working on.")


def _row(day, direction, scenario="", text="", channel="message", summary=""):
    return {"contact_id": CID, "date": day, "direction": direction, "channel": channel,
            "scenario": scenario, "summary": summary, "full_text": text, "subject": ""}


# ------------------------------------------------------------------ NW-14

def test_a_request_appended_after_the_reply_that_day_sorts_before_it():
    """Her reply to the note, and the day's request, imported at the foot of the log. The
    request came first: she has answered, and nothing of ours is unanswered."""
    rows = [_row("2026-08-24", "in", "reply", "Thanks for reaching out, happy to chat."),
            _row("2026-08-24", "out", "connection_request", NOTE, channel="connection")]
    ordered = state.threads_for(rows, CID)
    assert state.is_request(ordered[0]), [r["scenario"] for r in ordered]
    assert state._chases(ordered) == 0
    assert state.derive_status(ordered) == "replied_needs_response"


def test_rows_already_in_order_keep_the_order_they_have():
    rows = [_row("2026-08-24", "out", "connection_note", NOTE, channel="connection"),
            _row("2026-08-25", "in", "connection_accepted", channel="connection"),
            _row("2026-08-25", "out", "first_message", "Hi Ivo, thanks for connecting."),
            _row("2026-08-25", "in", "reply", "Nice to meet you.")]
    assert state.threads_for(rows, CID) == rows
    # A same-day answer of theirs to our message stays after it: only a request moves.
    rows = [_row("2026-09-01", "out", "nudge", "Hi Ivo, a quick follow-up to my note."),
            _row("2026-09-01", "in", "reply", "Sorry for the delay, yes let's talk.")]
    assert state.threads_for(rows, CID) == rows
    assert state.derive_status(state.threads_for(rows, CID)) == "replied_needs_response"


# ------------------------------------------------------------------ NW-3

LOGGED = ("Hi Ivo, hope things are going well. Just following up on my note from earlier this "
          "month about the planning team at Quayside. Would be great to hear how the team works.")
AS_SENT = ("Hi Ivo, just following up on my note from earlier this month. Would be great to "
           "hear how the planning team at Quayside works.")
EXPORTED = "Message sent, from LinkedIn's export"
REQUESTED = "Connection request with a note, from LinkedIn's export"


def test_a_note_logged_as_a_request_and_again_as_a_message_is_one_message(monkeypatch):
    """The request and the download's copy of its note, two days apart: one message sent, so
    their one follow-up is still theirs."""
    # The line names a day's year only when it is not the person's own year (state._day_said):
    # this story is in 2026, so their day is held there whatever the computer's clock says
    # (the everywhere check, "400-days").
    monkeypatch.setenv("LJS_TODAY", "2026-08-26")
    rows = [_row("2026-08-24", "out", "connection_request", NOTE, channel="connection",
                 summary=REQUESTED),
            _row("2026-08-25", "in", "connection_accepted", channel="connection"),
            _row("2026-08-26", "out", "", NOTE, summary=EXPORTED)]
    contact = {"contact_id": CID, "name": "Ivo Marsh", "status": "awaiting_reply",
               "next_action": "", "next_action_due": ""}
    assert state._chases(rows) == 1
    assert not state.at_limit(contact, rows)
    action, due = state.follow_up_plan(contact, rows)
    assert action == "Sent 24 Aug, no reply yet: follow up after 6 working days (one left), then stop" and due, \
        (action, due)
    # The same note logged by hand as a first message and by the import as a request.
    rows = [_row("2026-10-22", "out", "first_message", NOTE),
            _row("2026-10-22", "out", "connection_request", NOTE, channel="connection",
                 summary=REQUESTED)]
    assert state._chases(state.threads_for(rows, CID)) == 1


def test_the_note_logged_twice_before_her_reply_counts_once_in_the_order_it_went():
    """Her reply, then the note logged as a message, on one day; our later message; and the
    day's request at the foot of the log. In the order it went: the note (once), her reply,
    our message: one unanswered."""
    rows = [_row("2026-08-24", "in", "reply", "Thanks for reaching out, happy to chat."),
            _row("2026-08-24", "out", "first_message", NOTE),
            _row("2026-08-27", "out", "nudge", "Hi Ivo, would Thursday suit for a call?"),
            _row("2026-08-24", "out", "connection_request", NOTE, channel="connection")]
    assert state._chases(state.threads_for(rows, CID)) == 1


def test_the_same_words_after_their_answer_or_weeks_later_are_a_message_of_their_own():
    nudge = "Hi Ivo, a quick follow-up to my note from August about the planning team."
    rows = [_row("2026-08-24", "out", "connection_note", NOTE, channel="connection"),
            _row("2026-08-25", "out", "message", LOGGED, summary="Nudge sent (message)"),
            _row("2026-08-26", "in", "reply", "Thanks, busy week, will come back to you."),
            _row("2026-08-26", "out", "", AS_SENT, summary=EXPORTED)]
    # With her word between, words that are only alike are not taken for one: counted.
    assert state._chases(rows) == 1
    rows = [_row("2026-08-24", "out", "connection_note", NOTE, channel="connection"),
            _row("2026-09-21", "out", "nudge", nudge)]
    assert state._chases(rows) == 2
    # Two messages the download lists, both its own, are two even with the same words.
    rows = [_row("2026-09-01", "out", "", nudge, summary=EXPORTED),
            _row("2026-09-02", "out", "", nudge, summary=EXPORTED)]
    assert state._chases(rows) == 2


# ------------------------------------------------------------------ NW-4

def test_a_follow_up_logged_from_its_draft_and_the_downloads_copy_as_sent_are_one():
    rows = [_row("2026-10-08", "out", "connection_note", NOTE, channel="connection"),
            _row("2026-10-23", "out", "", AS_SENT, summary=EXPORTED),
            _row("2026-10-24", "out", "nudge", LOGGED, summary="Nudge sent (message)")]
    assert state._chases(rows) == 2
    contact = {"contact_id": CID, "status": "awaiting_reply", "next_action": ""}
    assert state.waiting_action(state._chases(rows)) == state.FOLLOW_UP_STOP.format(n=2, s="s")
    assert state.at_limit(contact, rows)
    # A different message the next day is a message of its own.
    other = ("Hi Ivo, I saw Quayside opened a new depot in Leeds this week. Congratulations "
             "to the team.")
    rows[-1] = _row("2026-10-24", "out", "nudge", other, summary="Nudge sent (message)")
    assert state._chases(rows) == 3


# ------------------------------------------------------------------ the download adds no copy

def _download(tmp_path, messages=(), invitations=()):
    """A LinkedIn download holding Juno's messages and invitations (the invented book of
    tests/fixtures/linkedin_export: Juno Castellan at Larkspur Retail, written to by Morgan)."""
    import csv
    src = tmp_path / "download"
    src.mkdir()
    with open(src / "messages.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["CONVERSATION ID", "FROM", "SENDER PROFILE URL", "TO", "RECIPIENT PROFILE URLS",
                    "DATE", "CONTENT", "ATTACHMENTS"])
        for when, text in messages:
            w.writerow(["c9", "Morgan Ellis", "https://www.linkedin.com/in/morgan-ellis-example",
                        "Juno Castellan", "https://www.linkedin.com/in/example-juno-castellan",
                        when, text, ""])
    with open(src / "Invitations.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["From", "To", "Sent At", "Message", "Direction", "inviterProfileUrl",
                    "inviteeProfileUrl"])
        for when, text in invitations:
            w.writerow(["Morgan Ellis", "Juno Castellan", when, text, "OUTGOING",
                        "https://www.linkedin.com/in/morgan-ellis-example",
                        "https://www.linkedin.com/in/example-juno-castellan"])
    return src


def _juno_book(tmp_path, rows):
    import shutil
    from pathlib import Path
    fix = Path(ROOT) / "tests" / "fixtures" / "linkedin_export"
    c = tmp_path / "network_contacts.csv"
    shutil.copy(fix / "book_contacts.csv", c)
    contacts = state.load_contacts(str(c))
    return contacts, [dict(r, contact_id="larkspur_retail_castellan") for r in rows]


JUNO_NOTE = NOTE.replace("Ivo", "Juno").replace("Quayside", "Larkspur")


def test_the_download_adds_no_copy_of_a_note_already_logged_as_a_request_or_a_message(
        tmp_path, monkeypatch):
    import datetime
    import export
    monkeypatch.setattr(export, "HERE", datetime.timezone.utc)
    # Logged as a request; the download lists its note among the messages two days later.
    contacts, threads = _juno_book(tmp_path, [
        _row("2026-08-24", "out", "connection_note", JUNO_NOTE, channel="connection")])
    src = _download(tmp_path, messages=[("2026-08-26 09:00:00 UTC", JUNO_NOTE)],
                    invitations=[("8/24/26, 9:00 AM", JUNO_NOTE)])
    plan = export.plan_history(contacts, threads, str(src))
    assert plan["add"] == [], plan["add"]
    # Logged by hand as a first message; the download says it went as a request.
    contacts, threads = _juno_book(tmp_path, [_row("2026-08-24", "out", "first_message", JUNO_NOTE)])
    import shutil
    shutil.rmtree(src)
    src = _download(tmp_path, invitations=[("8/24/26, 9:00 AM", JUNO_NOTE)])
    plan = export.plan_history(contacts, threads, str(src))
    assert plan["add"] == [], plan["add"]


def test_the_downloads_copy_of_a_follow_up_edited_before_it_went_gives_its_words_not_a_row(
        tmp_path, monkeypatch):
    import datetime
    import export
    monkeypatch.setattr(export, "HERE", datetime.timezone.utc)
    logged = LOGGED.replace("Ivo", "Juno").replace("Quayside", "Larkspur")
    as_sent = AS_SENT.replace("Ivo", "Juno").replace("Quayside", "Larkspur")
    contacts, threads = _juno_book(tmp_path, [
        _row("2026-10-08", "out", "connection_note", JUNO_NOTE, channel="connection"),
        _row("2026-10-24", "out", "nudge", logged, summary="Nudge sent (message)")])
    src = _download(tmp_path, messages=[("2026-10-23 21:00:00 UTC", as_sent)],
                    invitations=[("10/8/26, 9:00 AM", JUNO_NOTE)])
    plan = export.plan_history(contacts, threads, str(src))
    assert plan["add"] == [], plan["add"]
    export.apply_history(threads, plan)
    nudge = threads[-1]
    assert nudge["scenario"] == "nudge" and nudge["full_text"] == as_sent, nudge
    assert nudge["date"] == "2026-10-23", nudge
    assert state._chases(state.threads_for(threads, "larkspur_retail_castellan")) == 2


def test_a_tidy_takes_out_the_copy_of_a_note_the_download_listed_as_a_message(tmp_path):
    import export
    contacts, threads = _juno_book(tmp_path, [
        _row("2026-08-24", "out", "connection_request", JUNO_NOTE, channel="connection",
             summary=REQUESTED),
        _row("2026-08-25", "in", "connection_accepted", channel="connection"),
        _row("2026-08-26", "out", "", JUNO_NOTE, summary=EXPORTED)])
    gone = export.logged_twice(threads)
    assert [r["date"] for r in gone] == ["2026-08-26"], gone
    # The app's own first message and the download's request: the request is the copy.
    contacts, threads = _juno_book(tmp_path, [
        _row("2026-10-22", "out", "first_message", JUNO_NOTE),
        _row("2026-10-22", "out", "connection_request", JUNO_NOTE, channel="connection",
             summary=REQUESTED)])
    assert [r["scenario"] for r in export.logged_twice(threads)] == ["connection_request"]


def test_a_row_the_double_count_stopped_is_given_its_follow_up_again(monkeypatch):
    # The line names a day's year only when it is not the person's own year (state._day_said):
    # this story is in 2026, so their day is held there whatever the computer's clock says
    # (the everywhere check, "400-days").
    monkeypatch.setenv("LJS_TODAY", "2026-11-10")
    rows = [_row("2026-11-02", "out", "connection_request", NOTE, channel="connection",
                 summary=REQUESTED),
            _row("2026-11-03", "in", "connection_accepted", channel="connection"),
            _row("2026-11-04", "out", "", NOTE, summary=EXPORTED)]
    stopped = {"contact_id": CID, "name": "Ivo Marsh", "status": "awaiting_reply",
               "next_action": state.NUDGED_STOP, "next_action_due": ""}
    own = dict(stopped, contact_id="own", next_action="No reply to 2 messages: leave it")
    said = state.recount([stopped, own], rows + [dict(r, contact_id="own") for r in rows],
                         "2026-11-10")
    assert len(said) == 1 and CID in said[0], said
    assert stopped["next_action"] == "Sent 2 Nov, no reply yet: follow up after 6 working days (one left), then stop" \
        and stopped["next_action_due"], stopped
    assert not state.at_limit(stopped, rows)
    assert own["next_action"] == "No reply to 2 messages: leave it"       # the person's own
    # Run again, nothing.
    assert state.recount([stopped], rows, "2026-11-10") == []
