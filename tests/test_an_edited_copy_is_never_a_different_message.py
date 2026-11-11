"""Two different messages are never taken for one message and its edited copy.

The review of fix/nwthreads (2026-11-11) found two ways the "edited copy" reading made a
different message disappear. A connection note, then a different first message after they
accepted that only the LinkedIn download holds: a person's recipe repeats its who-line, so most
of the words are alike, and the two counted as one: the row at its limit was given a third
message (recount). And the import gave a logged reply the words and day of a later, different
reply the download holds, though a message of theirs sat between the two and the logged one had
its own exact copy in the download. A request is never an edited copy (a note goes word for
word), an exact copy claims its row, and nothing of theirs may sit between. Every person and
message is invented.
"""
from __future__ import annotations

import csv
import datetime
import os
import shutil
import sys
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import state  # noqa: E402

EXP = "Message sent, from LinkedIn's export"


def _row(cid, day, way, scenario="", text="", channel="message", summary=""):
    return {"contact_id": cid, "date": day, "direction": way, "channel": channel,
            "scenario": scenario, "summary": summary, "full_text": text, "subject": ""}


NOTE = ("Hi Tove, hope you're well. I'm an analyst, ex-Northwind and Quayside Foods, and just moved "
        "to Manchester from Leeds. I build forecasting models for stock and transport, which I "
        "imagine is similar to some of the planning work at Oakmere. I'd love to hear what you're "
        "working on.")
DM = ("Hi Tove, thanks for connecting. I'm an analyst, ex-Northwind and Quayside Foods, and just "
      "moved to Manchester from Leeds. I build forecasting models for stock and transport, and "
      "I'd love to hear what you're working on at Oakmere when you have a moment.")


def test_a_note_and_a_different_first_message_after_acceptance_are_two():
    cid = "oakmere_tove"
    rows = [_row(cid, "2026-11-02", "out", "connection_request", NOTE, "connection",
                 "Connection request with a note"),
            _row(cid, "2026-11-03", "in", "connection_accepted", channel="connection"),
            _row(cid, "2026-11-03", "out", "", DM, summary=EXP)]
    assert state._chases(rows) == 2
    stopped = {"contact_id": cid, "name": "Tove Ostler", "status": "awaiting_reply",
               "next_action": state.FOLLOW_UP_STOP.format(n=2, s="s"), "next_action_due": ""}
    assert state.recount([stopped], rows, "2026-11-11") == []
    assert stopped["next_action"] == state.FOLLOW_UP_STOP.format(n=2, s="s")


def test_the_import_never_gives_a_logged_reply_the_words_of_a_later_one(tmp_path, monkeypatch):
    import export
    monkeypatch.setattr(export, "HERE", datetime.timezone.utc)
    cid = "larkspur_retail_castellan"
    fix = Path(ROOT) / "tests" / "fixtures" / "linkedin_export"
    book = tmp_path / "network_contacts.csv"
    shutil.copy(fix / "book_contacts.csv", book)
    contacts = state.load_contacts(str(book))
    ours = ("Hi Juno, thanks so much for getting back to me. Thursday at 10 works well for me, "
            "looking forward to speaking then.")
    later = ("Hi Juno, no problem at all. Friday at 10 works well for me, looking forward to "
             "speaking then.")
    first, then = "Happy to chat, does Thursday at 10 work?", "Sorry, could we do Friday at 10 instead?"
    threads = [_row(cid, "2026-10-20", "in", "reply", first, summary="Reply logged"),
               _row(cid, "2026-10-20", "out", "reply", ours, summary="Reply sent"),
               _row(cid, "2026-10-20", "in", "reply", then, summary="Reply logged")]
    src = tmp_path / "download"
    src.mkdir()
    me = ("Morgan Ellis", "https://www.linkedin.com/in/morgan-ellis-example")
    juno = ("Juno Castellan", "https://www.linkedin.com/in/example-juno-castellan")
    with open(src / "messages.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["CONVERSATION ID", "FROM", "SENDER PROFILE URL", "TO", "RECIPIENT PROFILE URLS",
                    "DATE", "CONTENT", "ATTACHMENTS"])
        for when, who, text in (("2026-10-20 09:00:00 UTC", juno, first),
                                ("2026-10-20 10:00:00 UTC", me, ours),
                                ("2026-10-20 15:00:00 UTC", juno, then),
                                ("2026-10-21 09:00:00 UTC", me, later)):
            other = juno if who is me else me
            w.writerow(["c9", who[0], who[1], other[0], other[1], when, text, ""])
    with open(src / "Invitations.csv", "w", encoding="utf-8", newline="") as fh:
        csv.writer(fh).writerow(["From", "To", "Sent At", "Message", "Direction",
                                 "inviterProfileUrl", "inviteeProfileUrl"])
    plan = export.plan_history(contacts, threads, str(src))
    assert plan["resay"] == [], plan["resay"]
    assert [r["full_text"] for r in plan["add"]] == [later], plan["add"]
    export.apply_history(threads, plan)
    assert threads[1]["full_text"] == ours and threads[1]["date"] == "2026-10-20", threads[1]
