"""A note set aside is not a dead end, and a request sent from LinkedIn itself is recorded.

One contact book held 31 contacts closed with "outreach queue dropped by the
candidate; never sent", beside real dead ends; discovery then told the person their
best employers were "already covered" with nobody written to, and bringing them back
took a hand-written script over the CSV. The same session's queue said "Send now:
connection note", two days overdue, for two people whose profiles showed Pending: they
had been sent from the LinkedIn app, which the log never hears. Invented people only.
"""
from __future__ import annotations

import datetime
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import reading  # noqa: E402
import schema  # noqa: E402
import state  # noqa: E402

TODAY = datetime.date(2026, 10, 19)


def _c(cid, company="Kestrel Mutual", status="not_contacted", **kw):
    row = {k: "" for k in schema.CONTACT_COLUMNS}
    row.update(contact_id=cid, name=cid.replace("_", " ").title(), company=company,
               status=status, **kw)
    return row


@pytest.fixture
def drafts(tmp_path, monkeypatch):
    monkeypatch.setattr(reading.person, "state", lambda *p: str(tmp_path.joinpath(*p)))
    return tmp_path


def test_dropped_is_its_own_status_and_reopen_brings_it_back(drafts):
    contacts = [_c("rosalind_achterberg", status="closed",
                   outcome="outreach queue dropped by the candidate; never sent"),
                _c("corwin_haldane", status="closed", outcome="left the company 2026-09")]
    threads = []
    assert "dropped" in schema.THREAD_STATUSES and "dropped" in schema.TERMINAL
    found = state.closed_but_dropped(contacts, threads)
    assert [c["contact_id"] for c in found] == ["rosalind_achterberg"]   # never the dead end
    found[0]["status"] = "dropped"
    book = state.book_at(contacts, threads, "Kestrel Mutual")
    assert book == {"in_book": 2, "never_messaged": 2, "ids": ["rosalind_achterberg", "corwin_haldane"]}
    with pytest.raises(ValueError, match="--reason"):
        state.reopen(contacts, threads, "rosalind_achterberg", TODAY, "")
    c = state.reopen(contacts, threads, "rosalind_achterberg", TODAY, "the person wants them back")
    assert c["status"] == "not_contacted" and "reopened 2026-10-19 from dropped" in c["notes"]


def test_someone_written_to_is_never_reopened_or_dropped(drafts):
    contacts = [_c("tamsin_oyelaran", status="closed")]
    threads = [{"contact_id": "tamsin_oyelaran", "date": "2026-09-01", "direction": "out",
                "channel": "connection", "scenario": "connection_note", "summary": "",
                "full_text": "Hi Tamsin"}]
    with pytest.raises(ValueError, match="written to"):
        state.reopen(contacts, threads, "tamsin_oyelaran", TODAY, "why not")
    with pytest.raises(ValueError, match="written to"):
        state.drop(contacts, threads, "tamsin_oyelaran", TODAY, "set aside")


def test_where_picks_rows_by_field(drafts):
    contacts = [_c("a_one", outcome="never sent"), _c("b_two", company="Fernhill Freight"),
                _c("c_three", status="dropped")]
    assert [c["contact_id"] for c in state.where(contacts, ["outcome~never sent"])] == ["a_one"]
    assert [c["contact_id"] for c in state.where(contacts, ["company=fernhill freight"])] == ["b_two"]
    assert [c["contact_id"] for c in state.where(contacts, ["status=dropped"])] == ["c_three"]
    with pytest.raises(ValueError):
        state.where(contacts, ["nonsense"])


def test_a_request_seen_as_pending_is_recorded_as_sent_and_its_draft_goes(drafts):
    cid = "rosalind_achterberg"
    contacts, threads = [_c(cid)], []
    reading.write_draft(cid, "Hi Rosalind, hope you're well.", "Rosalind Achterberg")
    assert os.path.isfile(reading.draft_path(cid))
    row = state.sent(contacts, threads, cid, TODAY, date="2026-10-17", outside=True)
    assert row["scenario"] == state.OUTSIDE_SCENARIO and row["full_text"] == ""
    assert contacts[0]["status"] == "awaiting_reply" and contacts[0]["first_contacted"] == "2026-10-17"
    assert not os.path.exists(reading.draft_path(cid))
    # Its words were not seen, so an acceptance never owes a second first message.
    threads.append({"contact_id": cid, "date": "2026-10-18", "direction": "in",
                    "channel": "connection", "scenario": "connection_accepted", "summary": "",
                    "full_text": ""})
    assert state.accepted_never_messaged(threads) is None
    with pytest.raises(ValueError, match="already has a message"):
        state.sent(contacts, threads, cid, TODAY)


def test_a_send_past_its_day_with_nothing_logged_is_unconfirmed(drafts):
    contacts = [_c("rosalind_achterberg", next_action="Send now: connection note",
                   next_action_due="2026-10-17")]
    got = state.owed(contacts, [], TODAY)
    assert got and got[0]["kind"] == "action_due" and got[0]["unconfirmed"]
    contacts[0]["next_action_due"] = "2026-10-19"           # due today: not yet a question
    assert not state.owed(contacts, [], TODAY)[0]["unconfirmed"]


def test_skip_closes_with_the_reason_and_removes_the_draft(drafts, monkeypatch, capsys):
    cid = "corwin_haldane"
    contacts = [_c(cid)]
    monkeypatch.setattr(state, "load_contacts", lambda *a, **k: contacts)
    monkeypatch.setattr(state, "save_contacts", lambda rows, *a, **k: None)
    reading.write_draft(cid, "Hi Corwin.", "Corwin Haldane")
    assert reading.main(["skip", cid, "--reason", "ad sales, not a data role"]) == 0
    assert contacts[0]["status"] == "closed" and "ad sales" in contacts[0]["outcome"]
    assert not os.path.exists(reading.draft_path(cid))
    # A request already pending is never closed: it went.
    assert reading.main(["skip", cid, "--reason", "a request is already pending"]) == 1
    assert "state.py sent" in capsys.readouterr().out


def test_a_skipped_candidate_not_in_the_book_is_written_closed(drafts, monkeypatch):
    contacts = []
    monkeypatch.setattr(state, "load_contacts", lambda *a, **k: contacts)
    monkeypatch.setattr(state, "save_contacts", lambda rows, *a, **k: None)
    reading.save("kestrel_pellow", {"name": "Rhian Pellow", "company": "Kestrel Mutual",
                                    "headline": "account executive, sales", "location": ""})
    assert reading.main(["skip", "kestrel_pellow", "--reason", "sales, not a data role"]) == 0
    assert contacts and contacts[0]["status"] == "closed"
    assert state.already_contacted(contacts, name="Rhian Pellow", company="Kestrel Mutual")


def test_why_ranks_only_people_a_note_may_go_to(judged):
    import why
    judged("Kestrel Mutual")   # nobody is shown at an employer nobody has judged
    assert why.not_writable(_c("a_one", status="closed"), ()).startswith("closed")
    assert why.not_writable(_c("a_two", status="awaiting_reply"), ()).startswith("awaiting_reply")
    assert why.not_writable(_c("a_three", next_action="HOLD until 2026-12-01: interview running"),
                            (), TODAY).startswith("on hold")
    assert why.not_writable(_c("a_four"), (), TODAY) == ""
