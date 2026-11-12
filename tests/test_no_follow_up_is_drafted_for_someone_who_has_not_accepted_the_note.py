"""No follow-up is drafted for someone who has not accepted the connection request a note
went with.

A note sent with a connection request and logged by hand as an ordinary message stayed a
message when the LinkedIn download was taken, though Invitations.csv listed the same words
as a request of the person's and Connections.csv did not list the reader: the log read as a
message they could answer, a follow-up fell due when the person's rule said, and one was
drafted for someone LinkedIn still showed as Pending (2026-11-11). A tidy did the same where
an older import had logged the request beside the hand-logged message: it kept the message
and took the request out. Every name, address and message here is invented
(tests/fixtures/linkedin_export/README.md).
"""
import csv
import datetime
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tools" / "network")]

import export as E  # noqa: E402
import followup_drafts  # noqa: E402
import open_actions  # noqa: E402
import state  # noqa: E402

FIX = ROOT / "tests" / "fixtures" / "linkedin_export"
CID = "kestrel_mutual_varga"
ME = "https://www.linkedin.com/in/morgan-ellis-example"
HER = "https://www.linkedin.com/in/example-tamsin-varga"
NOTE = ("Hi Tamsin, hope you're well. I build demand forecasts for a logistics firm, which I "
        "imagine is similar to the planning work at Kestrel. I'd love to hear what you're "
        "working on.")
SENT_ON = "2026-10-20"


def _book(tmp_path, monkeypatch):
    """The invented contact book and log, with the note to Tamsin logged by hand as an
    ordinary message on SENT_ON (state.py sent --channel message)."""
    st = tmp_path / "state"
    st.mkdir()
    monkeypatch.setenv("LJS_STATE", str(st))
    monkeypatch.setenv("LJS_TODAY", "2026-10-27")
    monkeypatch.setattr(E, "HERE", datetime.timezone.utc)
    c, t = str(st / "network_contacts.csv"), str(st / "network_threads.csv")
    shutil.copy(FIX / "book_contacts.csv", c)
    shutil.copy(FIX / "book_threads.csv", t)
    contacts, threads = state.load_contacts(c), state.load_threads(t)
    state.sent(contacts, threads, CID, SENT_ON, text=NOTE, channel="message")
    state.save_contacts(contacts, c)
    state.save_threads(threads, t)
    return c, t


def _download(tmp_path, connected=()):
    """A LinkedIn download whose Invitations.csv lists the note as Morgan's request to
    Tamsin, and whose Connections.csv lists Juno and anyone in `connected`."""
    dl = tmp_path / "Complete_LinkedInDataExport"
    dl.mkdir()
    shutil.copy(FIX / "Profile.csv", dl / "Profile.csv")
    with open(dl / "Invitations.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["From", "To", "Sent At", "Message", "Direction", "inviterProfileUrl",
                    "inviteeProfileUrl"])
        w.writerow(["Morgan Ellis", "Tamsin Varga", "10/20/26, 9:00 AM", NOTE, "OUTGOING", ME, HER])
    with open(dl / "Connections.csv", "w", encoding="utf-8", newline="") as fh:
        fh.write('Notes:\n"When exporting your connection data, you may notice that some of '
                 'the email addresses are missing."\n\n')
        w = csv.writer(fh)
        w.writerow(["First Name", "Last Name", "URL", "Email Address", "Company", "Position",
                    "Connected On"])
        w.writerow(["Juno", "Castellan", "https://www.linkedin.com/in/example-juno-castellan",
                    "", "Larkspur Retail", "Analytics Manager", "11 Sep 2026"])
        for first, last, url, on in connected:
            w.writerow([first, last, url, "", "Kestrel Mutual", "Analytics Lead", on])
    with open(dl / "messages.csv", "w", encoding="utf-8", newline="") as fh:
        csv.writer(fh).writerow(["CONVERSATION ID", "FROM", "SENDER PROFILE URL", "TO",
                                 "RECIPIENT PROFILE URLS", "DATE", "CONTENT", "ATTACHMENTS"])
    return dl


def _hers(c, t):
    contacts, threads = state.load_contacts(c), state.load_threads(t)
    rows = [r for r in state.threads_for(threads, CID) if state.direction(r)]
    return contacts, threads, rows


def _owed_her(c, t, day):
    """What the follow-up pack holds for Tamsin on `day`: (kind, what code drafted)."""
    contacts, threads, _rows = _hers(c, t)
    items = open_actions.due_items(contacts, threads, [], datetime.date.fromisoformat(day))
    return [(i["kind"], i["draft"]["status"], i["draft"].get("why", ""))
            for i in followup_drafts.drafts(items, contacts, threads, [], day)
            if i.get("contact_id") == CID]


def test_a_note_logged_as_a_message_waits_as_the_request_it_went_as(tmp_path, monkeypatch):
    c, t = _book(tmp_path, monkeypatch)
    E.take([str(_download(tmp_path))], c, t)
    # Past the day a follow-up would have fallen due: nothing is owed her, nothing drafted.
    assert _owed_her(c, t, "2026-11-04") == []
    contacts, _threads, rows = _hers(c, t)
    # One send, typed as the request the download says it was, with its words and day kept.
    assert [(r["date"], r["channel"], r["scenario"], r["full_text"]) for r in rows] == [
        (SENT_ON, "connection", "connection_note", NOTE)], rows
    assert state.request_pending(rows) == datetime.date(2026, 10, 20)
    her = next(x for x in contacts if x["contact_id"] == CID)
    assert her["channel"] == "connection"
    assert her["next_action"].startswith("Once they accept:"), her["next_action"]
    # Three weeks on, the request is one to withdraw, never a follow-up.
    assert [k for k, _s, _w in _owed_her(c, t, "2026-11-12")] == ["request_pending"]
    # Taken again, nothing changes.
    E.take([str(Path(os.environ["LJS_STATE"]) / "documents" / "linkedin")], c, t)
    assert [(r["channel"], r["scenario"]) for r in _hers(c, t)[2]] == [
        ("connection", "connection_note")]


def test_once_she_has_accepted_the_follow_up_is_owed_as_before(tmp_path, monkeypatch):
    c, t = _book(tmp_path, monkeypatch)
    E.take([str(_download(tmp_path, connected=[("Tamsin", "Varga", HER, "22 Oct 2026")]))],
           c, t)
    _contacts, _threads, rows = _hers(c, t)
    assert state.request_pending(rows) is None
    assert [k for k, _s, _w in _owed_her(c, t, "2026-11-04")] == ["nudge"]


def test_a_tidy_keeps_the_note_as_the_request_an_older_import_logged_beside_it(
        tmp_path, monkeypatch):
    c, t = _book(tmp_path, monkeypatch)
    threads = state.load_threads(t)
    # What an import before 2026-11-10 added beside the hand-logged message.
    threads.append({"contact_id": CID, "date": SENT_ON, "direction": "out",
                    "channel": "connection", "scenario": "connection_request",
                    "summary": "Connection request with a note, " + E.EXPORT_NOTE,
                    "full_text": NOTE, "subject": ""})
    state.save_threads(threads, t)
    got = E.tidy(c, t)
    assert got["removed"] == 1, got
    assert _owed_her(c, t, "2026-11-04") == []
    _contacts, _threads, rows = _hers(c, t)
    assert [(r["channel"], r["scenario"]) for r in rows] == [("connection", "connection_note")]
    assert state.request_pending(rows) == datetime.date(2026, 10, 20)
    assert got.get("retyped") == 1, got
