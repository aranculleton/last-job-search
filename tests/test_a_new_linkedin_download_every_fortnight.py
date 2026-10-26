"""A new LinkedIn download every fortnight, and what changed since the last one.

From a person's repo on 2026-10-23: the download is the only place the app learns who
accepted a request, who replied on LinkedIn and which requests still wait, and nothing
said when it had gone stale. The brief now asks for a new one once the last is
EXPORT_EVERY_DAYS old (14 unless the person sets otherwise), and taking it says first
what changed since the one before. Every name and address here is invented.
"""
import datetime
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tools" / "network")]

import export as E  # noqa: E402
import state  # noqa: E402

TODAY = datetime.date.today()


class _Today(datetime.date):
    @classmethod
    def today(cls):
        return TODAY


class _Clock:
    """export.py's datetime with today held at TODAY. TODAY is read once, when the file is
    loaded, and a run that crossed midnight took the download on the new day and checked it
    against the old one (Windows, 2026-10-26)."""
    date = _Today

    def __getattr__(self, name):
        return getattr(datetime, name)


CONN_HEAD = ('Notes:\n"When exporting your connection data, you may notice that some of the '
             'email addresses are missing."\n\nFirst Name,Last Name,URL,Email Address,Company,'
             'Position,Connected On\n')
ME = "Morgan Ellis,https://www.linkedin.com/in/morgan-ellis-example"


def _conn(first, last, handle, company, connected):
    return f"{first},{last},https://www.linkedin.com/in/{handle},,{company},Data Analyst,{connected}\n"


def _day(d):
    return d.strftime("%d %b %Y")


def _state(tmp_path, monkeypatch):
    st = tmp_path / "state"
    (st / "documents" / "linkedin").mkdir(parents=True)
    monkeypatch.setenv("LJS_STATE", str(st))
    monkeypatch.setattr(E, "datetime", _Clock())
    contacts = [
        {"contact_id": "kestrel_achterberg", "name": "Rosalind Achterberg", "company": "Kestrel Mutual",
         "linkedin_url": "https://www.linkedin.com/in/example-rosalind", "status": "awaiting_reply",
         "channel": "connection", "first_contacted": "2026-09-20"},
        {"contact_id": "fernhill_oyelaran", "name": "Tamsin Oyelaran", "company": "Fernhill Freight",
         "linkedin_url": "https://www.linkedin.com/in/example-tamsin", "status": "awaiting_reply",
         "channel": "message", "first_contacted": "2026-10-01"},
    ]
    threads = [
        {"contact_id": "kestrel_achterberg", "date": "2026-09-20", "direction": "out",
         "channel": "connection", "scenario": "connection_request", "summary": "request, no note",
         "full_text": "", "subject": ""},
        {"contact_id": "fernhill_oyelaran", "date": "2026-10-01", "direction": "out",
         "channel": "message", "scenario": "", "summary": "first message",
         "full_text": "Hi Tamsin, hope you're well. How is the planning team set up?", "subject": ""},
    ]
    c, t = str(st / "network_contacts.csv"), str(st / "network_threads.csv")
    state.save_contacts([{k: r.get(k, "") for k in state.schema.CONTACT_COLUMNS} for r in contacts], c)
    state.save_threads(threads, t)
    old = st / "documents" / "linkedin" / "Connections.csv"
    old.write_text(CONN_HEAD + _conn("Idris", "Corrie", "example-idris", "Kestrel Mutual",
                                     "01 Jan 2026"), encoding="utf-8")
    return st, c, t


def _download(tmp_path):
    d = tmp_path / "Basic_LinkedInDataExport"
    d.mkdir()
    (d / "Connections.csv").write_text(
        CONN_HEAD
        + _conn("Idris", "Corrie", "example-idris", "Kestrel Mutual", "01 Jan 2026")
        + _conn("Rosalind", "Achterberg", "example-rosalind", "Kestrel Mutual", "05 Oct 2026")
        + _conn("Hal", "Okonedo", "example-hal", "Fernhill Freight", "10 Oct 2026"),
        encoding="utf-8")
    (d / "messages.csv").write_text(
        "CONVERSATION ID,CONVERSATION TITLE,FROM,SENDER PROFILE URL,TO,RECIPIENT PROFILE URLS,"
        "DATE,SUBJECT,CONTENT,FOLDER,ATTACHMENTS\n"
        f"conv-t,,{ME},Tamsin Oyelaran,https://www.linkedin.com/in/example-tamsin,"
        "2026-10-01 10:00:00 UTC,,\"Hi Tamsin, hope you're well. How is the planning team set up?\",INBOX,\n"
        f"conv-t,,Tamsin Oyelaran,https://www.linkedin.com/in/example-tamsin,{ME},"
        "2026-10-06 09:00:00 UTC,,\"Happy to talk, Thursday works.\",INBOX,\n",
        encoding="utf-8")
    (d / "Invitations.csv").write_text(
        "From,To,Sent At,Message,Direction,inviterProfileUrl,inviteeProfileUrl\n"
        "Morgan Ellis,Rosalind Achterberg,\"9/20/26, 10:15 AM\",,OUTGOING,"
        "https://www.linkedin.com/in/morgan-ellis-example,https://www.linkedin.com/in/example-rosalind\n"
        "Morgan Ellis,Wren Pellow,\"9/1/26, 9:00 AM\",,OUTGOING,"
        "https://www.linkedin.com/in/morgan-ellis-example,https://www.linkedin.com/in/example-wren\n",
        encoding="utf-8")
    return d


def test_taking_a_download_says_what_changed_since_the_last_one(tmp_path, monkeypatch):
    st, c, t = _state(tmp_path, monkeypatch)
    lines = E.take([str(_download(tmp_path))], c, t)
    assert lines[0] == (
        "Since your last download (2026-01-01): 2 new connections, 1 accepted your request "
        "(Rosalind Achterberg), 1 replied (Tamsin Oyelaran), and 1 request sent over "
        f"{E.PENDING_DAYS} days ago still wait (export.py pending lists them).")
    assert lines[1].startswith("Saved Connections.csv, messages.csv and Invitations.csv")
    kept = json.loads((st / "documents" / "network" / "linkedin_export.json").read_text())
    assert kept["taken_on"] == TODAY.isoformat()
    assert kept["newest"]["connections"] == "2026-10-10" and kept["rows"]["connections"] == 3
    # Taken again at once: nothing new since, and the record's day is the one counted from.
    again = E.take([str(st / "documents" / "linkedin")], c, t)
    assert again[0].startswith(f"Since your last download ({TODAY.isoformat()}): 0 new "
                               "connections, 0 accepted your request, 0 replied")


def test_the_brief_asks_for_a_new_one_once_the_last_is_a_fortnight_old(tmp_path, monkeypatch):
    st, c, t = _state(tmp_path, monkeypatch)
    E.take([str(_download(tmp_path))], c, t)
    assert E.due(TODAY + datetime.timedelta(days=13)) == ""
    line = E.due(TODAY + datetime.timedelta(days=14))
    assert line.startswith(f"Your LinkedIn download is 14 days old (taken {TODAY.isoformat()})")
    assert "claude_surfaces.py steps linkedin-export-files" in line and "export.py take" in line
    monkeypatch.setattr(E, "EXPORT_EVERY_DAYS", 0)
    assert E.due(TODAY + datetime.timedelta(days=90)) == ""


def test_with_no_record_the_age_comes_from_the_files_or_the_log(tmp_path, monkeypatch):
    st, c, t = _state(tmp_path, monkeypatch)
    assert E.last_taken() == (datetime.date(2026, 1, 1), "the newest day in it")
    os.remove(st / "documents" / "linkedin" / "Connections.csv")
    rows = state.load_threads(t)
    rows.append({"contact_id": "fernhill_oyelaran", "date": "2026-10-06", "direction": "in",
                 "channel": "message", "summary": f"Happy to talk, {E.EXPORT_NOTE}",
                 "full_text": "Happy to talk.", "scenario": "", "subject": ""})
    assert E.last_taken(rows) == (datetime.date(2026, 10, 6),
                                  "the newest message the log has from it")
    # Never taken at all: the brief says nothing (the connections-export upgrade asks).
    assert E.due(TODAY, threads=state.load_threads(t)) == ""


def test_the_command_prints_the_line_only_when_due(tmp_path, monkeypatch, capsys):
    _state(tmp_path, monkeypatch)
    assert E.main(["due", "--today", "2026-01-10"]) == 0
    assert capsys.readouterr().out == ""
    assert E.main(["due", "--today", "2026-02-01"]) == 0
    assert capsys.readouterr().out.startswith("Your LinkedIn download is 31 days old")


def test_old_history_in_a_download_is_not_news(tmp_path, monkeypatch):
    # A conversation from before the last download, with someone added to the book since,
    # and an invitation they sent long ago, come in with the history: neither is "since".
    st, c, t = _state(tmp_path, monkeypatch)
    d = _download(tmp_path)
    (d / "messages.csv").write_text(
        "CONVERSATION ID,CONVERSATION TITLE,FROM,SENDER PROFILE URL,TO,RECIPIENT PROFILE URLS,"
        "DATE,SUBJECT,CONTENT,FOLDER,ATTACHMENTS\n"
        f"conv-t,,Tamsin Oyelaran,https://www.linkedin.com/in/example-tamsin,{ME},"
        "2025-03-01 09:00:00 UTC,,\"Good to hear from you, let us talk in the spring.\",INBOX,\n",
        encoding="utf-8")
    with open(d / "Invitations.csv", "a", encoding="utf-8") as fh:
        fh.write("Rosalind Achterberg,Morgan Ellis,\"3/2/24, 9:00 AM\",Hello,INCOMING,"
                 "https://www.linkedin.com/in/example-rosalind,"
                 "https://www.linkedin.com/in/morgan-ellis-example\n")
    lines = E.take([str(d)], c, t)
    assert ", 0 replied," in lines[0], lines[0]


def test_an_older_download_given_again_never_replaces_a_newer_one(tmp_path, monkeypatch):
    st, c, t = _state(tmp_path, monkeypatch)
    E.take([str(_download(tmp_path))], c, t)
    kept = st / "documents" / "linkedin" / "Connections.csv"
    newer = kept.read_text(encoding="utf-8")
    older = tmp_path / "older"
    older.mkdir()
    (older / "Connections.csv").write_text(
        CONN_HEAD + _conn("Idris", "Corrie", "example-idris", "Kestrel Mutual", "01 Jan 2026"),
        encoding="utf-8")
    said = E.save([str(older)], "connections")
    assert said.startswith("Nothing saved: the files kept here are newer: Connections.csv "
                           "(the one kept here runs to 2026-10-10, this one to 2026-01-01)")
    assert kept.read_text(encoding="utf-8") == newer
