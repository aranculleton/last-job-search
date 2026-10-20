"""Every recorded send keeps its words, and a send recorded wrong can be put right.

The message that drew a reply from a senior reader within three hours reached the log
days later, pasted in by the person, and earlier ones that drew replies were logged as
"approach" with no text, so nothing could learn from them. A send that did not go, or
went with other words, could only be fixed by editing two CSVs by hand. Invented people.
"""
from __future__ import annotations

import datetime
import os
import shutil
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import learned  # noqa: E402
import person  # noqa: E402
import reading  # noqa: E402
import schema  # noqa: E402
import state  # noqa: E402

TODAY = datetime.date(2026, 10, 20)
NOTE = "Hi Ana, I'm a data analyst in Leeds. Would love to hear if you have anything coming up."


def _c(cid, **kw):
    row = {k: "" for k in schema.CONTACT_COLUMNS}
    row.update(contact_id=cid, name=cid.replace("_", " ").title(), company="Kestrel Mutual",
               status="not_contacted", **kw)
    return row


@pytest.fixture
def here(tmp_path, monkeypatch):
    d = tmp_path / "profile"
    shutil.copytree(os.path.join(ROOT, "profile.example"), d)
    monkeypatch.setenv(person.ENV, str(d))
    person._modules.clear()
    person._data.clear()
    monkeypatch.setattr(reading.person, "state", lambda *p: str(tmp_path.joinpath("st", *p)))
    yield tmp_path
    person._modules.clear()
    person._data.clear()


def test_a_send_with_no_words_is_refused_unless_it_was_a_bare_request(here):
    contacts, threads = [_c("ana_rook")], []
    with pytest.raises(ValueError, match="words that went are needed"):
        state.sent(contacts, threads, "ana_rook", TODAY)
    row = state.sent(contacts, threads, "ana_rook", TODAY, note=False)
    assert row["scenario"] == "connection_request"


def test_an_inmail_keeps_its_subject_and_spends_a_credit(here):
    contacts, threads = [_c("ana_rook")], []
    with pytest.raises(ValueError, match="subject is needed"):
        state.sent(contacts, threads, "ana_rook", TODAY, channel="inmail", text=NOTE)
    row = state.sent(contacts, threads, "ana_rook", TODAY, channel="inmail", text=NOTE,
                     subject="Data analyst, ex-Oakmere Foods")
    assert row["subject"] == "Data analyst, ex-Oakmere Foods" and "subject" in schema.THREAD_COLUMNS
    b = state.platform_budget(contacts, threads, TODAY)
    assert b["inmails_sent"] == 1


def test_a_request_seen_on_the_invitations_page_keeps_the_note_it_shows(here):
    page = "\n".join(["Sent", "People (2)", "Ana Rook", "Head of Pricing at Kestrel Mutual",
                      "Sent 3 days ago", "Withdraw", "Hi Ana, I'm a data analyst in Leeds and",
                      "...show more", "Bo Venn", "Analyst at Fernhill Freight", "Sent 1 week ago",
                      "Withdraw"])
    cards = reading.invitations(page, today=TODAY)
    assert [c["name"] for c in cards] == ["Ana Rook", "Bo Venn"]
    assert cards[0]["note"] == "Hi Ana, I'm a data analyst in Leeds and" and cards[0]["note_cut"]
    assert "note" not in cards[1]
    contacts, threads = [_c("ana_rook")], []
    row = state.sent(contacts, threads, "ana_rook", TODAY, outside=True, text=cards[0]["note"],
                     preview=True)
    assert row["full_text"].startswith("Hi Ana") and "cut where the page folds" in row["summary"]


def test_a_send_on_another_day_or_with_other_words_is_put_right(here):
    contacts, threads = [_c("ana_rook")], []
    state.sent(contacts, threads, "ana_rook", TODAY, text="Hi Ana, I am a data analyst.")
    got = state.resent(contacts, threads, "ana_rook", TODAY, text=NOTE, date="2026-10-22")
    assert got["before"] == "Hi Ana, I am a data analyst."
    assert threads[0]["full_text"] == NOTE and threads[0]["date"] == "2026-10-22"
    assert contacts[0]["first_contacted"] == "2026-10-22"
    assert contacts[0]["next_action_due"] == state.add_business_days(
        datetime.date(2026, 10, 22), schema.FOLLOWUP_BUSINESS_DAYS).isoformat()


def test_a_send_that_did_not_go_comes_off_the_log_and_back_to_its_draft(here):
    contacts, threads = [_c("ana_rook")], []
    state.sent(contacts, threads, "ana_rook", TODAY, text=NOTE)
    got = state.unsend(contacts, threads, "ana_rook", TODAY)
    assert threads == [] and contacts[0]["status"] == "not_contacted"
    assert contacts[0]["first_contacted"] == "" and NOTE in open(got["draft"]).read()
    state.sent(contacts, threads, "ana_rook", TODAY, text=NOTE)
    threads.append({"contact_id": "ana_rook", "date": "2026-10-21", "direction": "in",
                    "channel": "connection", "scenario": "reply", "summary": "", "full_text": "Hi!"})
    with pytest.raises(ValueError, match="replied after it"):
        state.unsend(contacts, threads, "ana_rook", TODAY)


def test_an_edit_before_sending_is_recorded_as_their_preference(here, capsys):
    contacts = here / "c.csv"
    threads = here / "t.csv"
    state.save_contacts([_c("ana_rook")], str(contacts))
    state.save_threads([], str(threads))
    reading.write_draft("ana_rook", "Hi Ana, I am a data analyst in Leeds. I would love to "
                        "hear how your team works.", "Ana Rook")
    sent_file = here / "sent.txt"
    sent_file.write_text(NOTE, encoding="utf-8")
    rc = state.main(["sent", "ana_rook", "--text-file", str(sent_file), "--contacts",
                     str(contacts), "--threads", str(threads), "--today", TODAY.isoformat()])
    assert rc == 0
    assert "learned from the edit" in capsys.readouterr().out
    e = [r for r in learned.load() if r.get("kind") == "edit"]
    assert e and e[0]["sent"] == NOTE


def test_a_refused_send_records_no_edit_and_the_retry_records_it_once(here):
    contacts, threads = here / "c.csv", here / "t.csv"
    state.save_contacts([_c("ana_rook")], str(contacts))
    state.save_threads([], str(threads))
    reading.write_draft("ana_rook", "Subject: Analyst, ex-Kestrel\n\nHi Ana, I am a data "
                        "analyst in Leeds.", "Ana Rook")
    sent_file = here / "sent.txt"
    sent_file.write_text("Hi Ana, I'm a data analyst in Leeds.", encoding="utf-8")
    args = ["sent", "ana_rook", "--text-file", str(sent_file), "--channel", "inmail",
            "--contacts", str(contacts), "--threads", str(threads), "--today", TODAY.isoformat()]
    state.main(args)                                     # no subject: refused
    assert [r for r in learned.load() if r.get("kind") == "edit"] == []
    assert state.main(args + ["--subject", "Analyst, ex-Kestrel"]) == 0
    edits = [r for r in learned.load() if r.get("kind") == "edit"]
    assert len(edits) == 1 and "Subject" not in edits[0]["draft"]


def test_an_inmail_draft_logs_its_own_subject(here):
    contacts, threads = here / "c.csv", here / "t.csv"
    state.save_contacts([_c("ana_rook")], str(contacts))
    state.save_threads([], str(threads))
    reading.write_draft("ana_rook", "Subject: Analyst, ex-Kestrel\n\nHi Ana,\n\nA second "
                        "paragraph.", "Ana Rook")
    assert state.main(["sent", "ana_rook", "--draft", "--channel", "inmail", "--contacts",
                       str(contacts), "--threads", str(threads), "--today",
                       TODAY.isoformat()]) == 0
    row = state.load_threads(str(threads))[0]
    assert row["subject"] == "Analyst, ex-Kestrel"
    assert row["full_text"] == "Hi Ana,\n\nA second paragraph."


def test_an_unsent_inmail_comes_back_with_its_subject_and_paragraphs(here):
    contacts, threads = [_c("ana_rook")], []
    state.sent(contacts, threads, "ana_rook", TODAY, channel="inmail", subject="Analyst",
               text="Hi Ana,\n\nSecond   paragraph here.")
    got = state.unsend(contacts, threads, "ana_rook", TODAY)
    text = open(got["draft"]).read()
    assert "Subject: Analyst\n\nHi Ana,\n\nSecond paragraph here." in text


def test_unsending_to_someone_who_wrote_first_keeps_their_message_owed(here):
    contacts = [_c("ana_rook")]
    threads = [{"contact_id": "ana_rook", "date": "2026-10-19", "direction": "in",
                "channel": "connection", "scenario": "reply", "summary": "",
                "full_text": "Hi, saw your post."}]
    state.sent(contacts, threads, "ana_rook", TODAY, text=NOTE)
    state.unsend(contacts, threads, "ana_rook", TODAY)
    assert contacts[0]["status"] == "replied_needs_response"


def test_nothing_is_ever_recorded_into_the_example_person(monkeypatch):
    monkeypatch.setenv(person.ENV, os.path.join(ROOT, "profile.example"))
    person._modules.clear()
    person._data.clear()
    with pytest.raises(SystemExit, match="example person"):
        learned.record("voice", "x", "y")
    person._modules.clear()
    person._data.clear()
