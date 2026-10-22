"""The message log read for what happened, from the networking audit of 2026-10-21.

Who spoke last was decided two ways, and the follow-up log refused a due nudge and set up a
second one; unsend took off an older message the export had appended at the end of the
file; the export added a message with no words again on every run; an answer to someone who
wrote first was logged as a connection request; the per-employer limit counted someone who
had replied as waiting; invitations already accepted were offered for withdrawal; a request
recorded from a Pending page was added again by the export; and a line of seven "=" in a
message made the whole log unreadable. Each case below is one of those, with invented
people and employers.
"""
from __future__ import annotations

import datetime
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import csv_store  # noqa: E402
import export  # noqa: E402
import reading  # noqa: E402
import reply  # noqa: E402
import state  # noqa: E402

ME = "https://www.linkedin.com/in/morgan-ellis-example"


def _c(cid, name, company="Kestrel Mutual", **kw):
    return {"contact_id": cid, "name": name, "company": company, "status": "not_contacted",
            "location": "Manchester, England, United Kingdom", **kw}


def _t(cid, date, direction, scenario="", text="", channel="message", summary=""):
    return {"contact_id": cid, "date": date, "direction": direction, "channel": channel,
            "scenario": scenario, "summary": summary or scenario or "logged", "full_text": text,
            "subject": ""}


@pytest.fixture
def files(tmp_path, monkeypatch):
    """The contact book and the log in files, and the readings and drafts beside them."""
    monkeypatch.setattr(reading.person, "state", lambda *p: str(tmp_path.joinpath(*p)))
    monkeypatch.setenv("LJS_LEDGER", str(tmp_path / "ledger"))
    contacts, threads = str(tmp_path / "contacts.csv"), str(tmp_path / "threads.csv")
    monkeypatch.setattr(state, "CONTACTS_CSV", contacts)
    monkeypatch.setattr(state, "THREADS_CSV", threads)
    real = (state.load_contacts, state.save_contacts, state.load_threads, state.save_threads)
    monkeypatch.setattr(state, "load_contacts", lambda path=contacts: real[0](path))
    monkeypatch.setattr(state, "save_contacts", lambda rows, path=contacts: real[1](rows, path))
    monkeypatch.setattr(state, "load_threads", lambda path=threads: real[2](path))
    monkeypatch.setattr(state, "save_threads", lambda rows, path=threads: real[3](rows, path))
    return {"contacts": contacts, "threads": threads, "dir": tmp_path}


# ------------------------------------------------------------ who spoke last, one answer

def _answered_then_silent(cid):
    contacts = [_c(cid, "Ana Rook", status="awaiting_reply", channel="connection",
                   first_contacted="2026-09-01")]
    threads = [_t(cid, "2026-09-01", "out", "connection_note", "Hi Ana, a first note.",
                  channel="connection"),
               _t(cid, "2026-09-03", "in", "", "Happy to chat. What would you like to know?"),
               _t(cid, "2026-09-04", "out", "reply", "Thanks Ana! Would Tuesday at 2 suit?")]
    return contacts, threads


def test_a_nudge_after_our_answer_to_their_reply_is_the_one_nudge():
    cid = "kes_rook"
    contacts, threads = _answered_then_silent(cid)
    assert [i["kind"] for i in state.owed(contacts, threads, "2026-09-21")] == ["nudge"]
    assert reply._they_spoke_last(state.threads_for(threads, cid)) is False
    got = state.followed_up(contacts, threads, cid, "2026-09-21", kind="nudge",
                            text="Hi Ana, is a call next week still good for you?")
    assert got["row"]["scenario"] == "nudge"
    assert contacts[0]["next_action"].startswith("Nudged: nothing more unless they reply")
    # /reply and the log read who spoke last the same way, on every shape of thread.
    for rows in (threads[:1], threads[:2], threads[:3], threads):
        assert state.they_spoke_last(rows) == reply._they_spoke_last(rows)


def test_the_same_chase_logged_as_a_message_never_sets_up_a_second_nudge():
    cid = "kes_rook"
    contacts, threads = _answered_then_silent(cid)
    got = state.followed_up(contacts, threads, cid, "2026-09-21", kind="message",
                            text="Hi Ana, is a call next week still good for you?")
    assert got["row"]["scenario"] == "nudge"
    later = state.owed(contacts, threads, "2026-10-05")
    assert not [i for i in later if i["kind"] == "nudge" or "One nudge" in str(i.get("next_action"))]


# ------------------------------------------------------------ the latest message, by date

def _with_an_older_import(cid):
    contacts = [_c(cid, "Bo Venn", status="awaiting_reply", channel="message",
                   first_contacted="2026-09-20")]
    threads = [_t(cid, "2026-10-01", "out", "first_message", "Hi Bo, we both worked at "
                  "Oakmere Foods."),
               _t(cid, "2026-10-10", "out", "nudge", "Hi Bo, how is the pricing team set up?"),
               # Appended afterwards by the export import, though it is older than both.
               _t(cid, "2026-09-20", "out", "", "Congrats on the new role!",
                  summary="Message sent, from LinkedIn's export")]
    return contacts, threads


def test_unsend_takes_off_the_latest_message_not_the_last_line(files):
    cid = "kes_venn"
    contacts, threads = _with_an_older_import(cid)
    got = state.unsend(contacts, threads, cid, "2026-10-11")
    assert got["row"]["date"] == "2026-10-10"
    assert sorted(t["date"] for t in threads) == ["2026-09-20", "2026-10-01"]
    with open(got["draft"], encoding="utf-8") as fh:
        assert "pricing team" in fh.read()


def test_resent_corrects_the_latest_message_and_a_reply_before_it_is_not_after_it(files):
    cid = "kes_venn"
    contacts, threads = _with_an_older_import(cid)
    state.resent(contacts, threads, cid, "2026-10-11", date="2026-10-09")
    assert [t["date"] for t in threads] == ["2026-10-01", "2026-10-09", "2026-09-20"]
    # Their reply of 5 Oct, appended at the end, came before the nudge: the nudge can still
    # be taken back, since nothing came back after it.
    contacts, threads = _with_an_older_import(cid)
    threads[2] = _t(cid, "2026-10-05", "in", "", "Thanks, will read it properly soon.")
    got = state.unsend(contacts, threads, cid, "2026-10-11")
    assert got["row"]["date"] == "2026-10-10"


# ------------------------------------------------------------ the export, run twice

def _messages(folder, rows):
    head = ("CONVERSATION ID,CONVERSATION TITLE,FROM,SENDER PROFILE URL,TO,RECIPIENT PROFILE "
            "URLS,DATE,SUBJECT,CONTENT,FOLDER,ATTACHMENTS\n")
    (folder / "messages.csv").write_text(head + "".join(r + "\n" for r in rows), encoding="utf-8")


def test_a_message_with_no_words_is_added_once_however_often_the_export_is_read(tmp_path):
    them = "https://www.linkedin.com/in/example-wren-allard"
    ex = tmp_path / "export"
    ex.mkdir()
    _messages(ex, [
        f"c1,,Morgan Ellis,{ME},Wren Allard,{them},2026-10-01 10:00:00 UTC,,Hi Wren thanks "
        "for the chat,INBOX,",
        f"c1,,Morgan Ellis,{ME},Wren Allard,{them},2026-10-02 10:00:00 UTC,,,INBOX,"
        "https://www.linkedin.com/dms/attach/Resume.pdf",
        f"c1,,Wren Allard,{them},Morgan Ellis,{ME},2026-10-03 10:00:00 UTC,,,INBOX,"
        "https://www.linkedin.com/dms/attach/role.pdf"])
    contacts = [_c("fern_allard", "Wren Allard", "Fernhill Freight", linkedin_url=them,
                   status="awaiting_reply", channel="message")]
    threads: list = []
    counts = []
    for _run in range(3):
        plan = export.plan_history(contacts, threads, str(ex))
        counts.append(len(plan["add"]))
        export.apply_history(threads, plan, contacts)
    assert counts == [3, 0, 0]
    assert not [p for p in state.reconcile(contacts, threads) if p["reason"] == "duplicate_message"]
    # Two files sent alone on one day are two messages, and stay two.
    _messages(ex, [f"c2,,Morgan Ellis,{ME},Wren Allard,{them},2026-10-05 {h}:00:00 UTC,,,INBOX,"
                   "https://www.linkedin.com/dms/attach/Portfolio.pdf" for h in (10, 11)])
    counts = []
    for _run in range(2):
        plan = export.plan_history(contacts, threads, str(ex))
        counts.append(len(plan["add"]))
        export.apply_history(threads, plan, contacts)
    assert counts == [2, 0]


def test_a_request_recorded_from_a_pending_page_is_the_one_the_export_lists(tmp_path):
    ex = tmp_path / "export"
    ex.mkdir()
    (ex / "Invitations.csv").write_text(
        "From,To,Sent At,Message,Direction,inviterProfileUrl,inviteeProfileUrl\n"
        f"Morgan Ellis,Hal Okonedo,\"9/1/26, 10:00 AM\",,OUTGOING,{ME},"
        "https://www.linkedin.com/in/example-hal-okonedo\n", encoding="utf-8")
    contacts = [_c("kes_okonedo", "Hal Okonedo",
                   linkedin_url="https://www.linkedin.com/in/example-hal-okonedo")]
    threads: list = []
    # Seen Pending on their page on 2 Oct, and recorded then.
    state.sent(contacts, threads, "kes_okonedo", "2026-10-02", outside=True)
    export.apply_history(threads, export.plan_history(contacts, threads, str(ex)), contacts)
    assert [(t["date"], state.is_request(t)) for t in threads] == [("2026-09-01", True)]
    assert state.connection_requests(contacts, threads) == {
        ("kes_okonedo", datetime.date(2026, 9, 1))}
    assert contacts[0]["first_contacted"] == "2026-09-01"
    waiting = [i for i in state.owed(contacts, threads, "2026-10-21")
               if i["kind"] == "request_pending"]
    assert [i["since"] for i in waiting] == ["2026-09-01"]


def test_an_accepted_invitation_is_never_offered_for_withdrawal_when_one_side_lacks_an_address(
        tmp_path):
    ex = tmp_path / "export"
    ex.mkdir()
    (ex / "Invitations.csv").write_text(
        "From,To,Sent At,Message,Direction,inviterProfileUrl,inviteeProfileUrl\n"
        f"Morgan Ellis,Juno Castellan,\"9/1/26, 10:00 AM\",,OUTGOING,{ME},\n"
        f"Morgan Ellis,Pell Ansgar,\"9/1/26, 10:00 AM\",,OUTGOING,{ME},"
        "https://www.linkedin.com/in/example-pell-ansgar\n"
        f"Morgan Ellis,Corwin Haldane,\"9/1/26, 10:00 AM\",,OUTGOING,{ME},"
        "https://www.linkedin.com/in/example-corwin-haldane-two\n", encoding="utf-8")
    (ex / "Connections.csv").write_text(
        "Notes:\nWhen exporting your connection data...\n\n"
        "First Name,Last Name,URL,Email Address,Company,Position,Connected On\n"
        "Juno,Castellan,https://www.linkedin.com/in/example-juno-castellan,,Larkspur,Analyst,"
        "05 Sep 2026\n"
        "Pell,Ansgar,,,Fernhill Freight,Analyst,05 Sep 2026\n"
        # The same name at another address is another person: still waiting.
        "Corwin,Haldane,https://www.linkedin.com/in/example-corwin-haldane,,Larkspur,Analyst,"
        "05 Sep 2026\n", encoding="utf-8")
    got = export.pending([], [], "2026-10-21", str(ex))
    assert [i["name"] for i in got["items"]] == ["Corwin Haldane"]


# ------------------------------------------------------------ they wrote first

def test_an_answer_to_someone_who_wrote_first_is_a_reply_whichever_command_logs_it():
    cid = "kes_corrie"

    def book():
        return ([_c(cid, "Idris Corrie", status="replied_needs_response", channel="message",
                    title="Technical Recruiter")],
                [_t(cid, "2026-10-01", "in", "recruiter_inbound",
                    "Hi Morgan, I have a role you might like. Free for a call?")])
    words = "Hi Idris, thanks for reaching out. Thursday after 2 suits me."
    contacts, threads = book()
    got = state.followed_up(contacts, threads, cid, "2026-10-02", text=words, kind="message")
    assert (got["row"]["scenario"], got["row"]["channel"]) == ("reply", "message")
    contacts, threads = book()
    row = state.sent(contacts, threads, cid, "2026-10-02", text=words)   # channel: connection
    assert (row["scenario"], row["channel"]) == ("reply", "message")
    assert not state.connection_requests(contacts, threads)
    assert not [i for i in state.owed(contacts, threads, "2026-10-30")
                if i["kind"] == "request_pending"]


def test_a_first_message_after_a_bare_request_is_accepted_drops_the_request_line():
    cid = "kes_rook"
    contacts, threads = [_c(cid, "Ana Rook")], []
    state.sent(contacts, threads, cid, "2026-10-01", note=False)
    threads.append(_t(cid, "2026-10-05", "in", "accepted_no_reply", channel="connection"))
    contacts[0]["status"] = "connected_no_reply"
    state.followed_up(contacts, threads, cid, "2026-10-06", kind="message",
                      text="Hi Ana, thanks for connecting. How did you find the move?")
    assert contacts[0]["next_action"] == "One nudge if no reply"


# ------------------------------------------------------------ the per-employer limit

def test_someone_the_log_shows_answered_is_not_counted_as_waiting(files):
    today = datetime.date.today()
    sent_on = (today - datetime.timedelta(days=10)).isoformat()
    state.save_contacts([
        _c("kes_rook", "Ana Rook", status="awaiting_reply", first_contacted=sent_on),
        _c("kes_venn", "Bo Venn", "Kestrel Mutual Ltd", status="awaiting_reply",
           first_contacted=sent_on)])
    state.save_threads([
        _t("kes_rook", sent_on, "out", "connection_note", "Hi Ana, ...", "connection"),
        _t("kes_venn", sent_on, "out", "connection_note", "Hi Bo, ...", "connection"),
        _t("kes_rook", today.isoformat(), "in", "", "Hi Morgan, happy to chat!")])
    contacts = state.load_contacts()
    assert reading.employer_full_line("Kestrel Mutual", contacts) == ""
    waiting, _there = reading.at_employer("Kestrel Mutual", contacts)
    assert [c["contact_id"] for c in waiting] == ["kes_venn"]


# ------------------------------------------------------------ the file stays readable

def test_a_line_of_equals_signs_inside_a_message_is_words_not_a_conflict(tmp_path):
    path = str(tmp_path / "network_threads.csv")
    rows = [_t("kes_rook", "2026-10-01", "in", "", "Happy to chat next week.\n=======\n"
               "Ana Rook | Pricing\nKestrel Mutual"),
            _t("kes_rook", "2026-10-02", "in", "", "A pasted merge:\n<<<<<<< ours\nmine\n"
               "=======\ntheirs\n>>>>>>> theirs\nend")]
    state.save_threads(rows, path)
    assert [r["full_text"] for r in state.load_threads(path)] == [r["full_text"] for r in rows]


def test_a_real_conflict_is_still_refused_even_inside_a_message_cell(tmp_path):
    path = tmp_path / "network_threads.csv"
    # Git splits a row whose message runs over lines in the middle of its quoted cell.
    path.write_text("contact_id,date,direction,full_text\n"
                    "kes_rook,2026-10-01,in,\"Line one\n"
                    "<<<<<<< ours\n"
                    "Line two, as we had it\"\n"
                    "=======\n"
                    "Line two, as they had it\"\n"
                    ">>>>>>> theirs\n", encoding="utf-8")
    with pytest.raises(csv_store.Conflicted, match="at line 3"):
        state.load_threads(str(path))


# ------------------------------------------------------------ commands

def test_several_follow_ups_are_logged_from_one_file_of_texts(files, capsys):
    state.save_contacts([_c("kes_rook", "Ana Rook", status="awaiting_reply"),
                         _c("kes_venn", "Bo Venn", status="awaiting_reply")])
    state.save_threads([
        _t("kes_rook", "2026-10-01", "out", "first_message", "Hi Ana, a first message."),
        _t("kes_venn", "2026-10-01", "out", "first_message", "Hi Bo, a first one.")])
    texts = files["dir"] / "texts.json"
    texts.write_text(json.dumps({"kes_rook": "Hi Ana, one nudge.",
                                 "kes_venn": "Hi Bo, one nudge."}), encoding="utf-8")
    code = state.main(["nudge", "--texts", str(texts), "--today", "2026-10-14",
                       "--contacts", files["contacts"], "--threads", files["threads"]])
    assert code == 0 and "nudge: 2 recorded" in capsys.readouterr().out
    assert [t["scenario"] for t in state.load_threads()][-2:] == ["nudge", "nudge"]


def test_a_placeholder_logged_as_drafted_is_said_with_how_to_correct_it(files, capsys):
    state.save_contacts([_c("kes_rook", "Ana Rook")])
    state.save_threads([])
    reading.write_draft("kes_rook", "Hi Ana, a placeholder note.", "Ana Rook")
    assert reading.waits_on_read("kes_rook")
    code = state.main(["sent", "kes_rook", "--draft", "--today", "2026-10-14",
                       "--contacts", files["contacts"], "--threads", files["threads"]])
    out = capsys.readouterr().out
    assert code == 0 and "placeholder waiting on a read" in out
    assert "state.py resent kes_rook --text-file" in out


def test_a_name_two_contacts_share_changes_neither():
    contacts = [_c("kes_oyelaran", "Tamsin Oyelaran", status="awaiting_reply"),
                _c("fern_oyelaran", "Tamsin Oyelaran", "Fernhill Freight", status="in_conversation")]
    with pytest.raises(ValueError, match="kes_oyelaran.*fern_oyelaran"):
        state.set_contact(contacts, [], "Tamsin Oyelaran", status="closed")
    assert [c["status"] for c in contacts] == ["awaiting_reply", "in_conversation"]
    row, _said = state.set_contact(contacts, [], "fern_oyelaran", status="closed")
    assert row["contact_id"] == "fern_oyelaran"


def test_a_request_with_no_note_spends_no_personalised_note(monkeypatch):
    monkeypatch.setitem(state.schema.LIMITS, "personal_notes_per_month", 5)
    contacts, threads = [], []
    for i in range(5):
        contacts.append(_c(f"c{i}", f"Ana Rook{i}", f"Employer {i}"))
        state.sent(contacts, threads, f"c{i}", "2026-10-05", note=False)
    b = state.platform_budget(contacts, threads, "2026-10-06")
    assert b["personal_notes_left"] == 5 and b["note"] == ""
    state.sent(contacts + [_c("c9", "Bo Venn")], threads, "c9", "2026-10-06",
               text="Hi Bo, a note with words.")
    assert state.platform_budget(contacts, threads, "2026-10-06")["personal_notes_left"] == 4


# ------------------------------------------------------------ an automatic reply, or a person

def test_an_out_of_office_that_makes_an_offer_is_a_person():
    offer = ("Thanks for the note. I'm out of the office this week with limited access to email, "
             "but I'll pass your profile to our recruiter.")
    assert state.auto_reply(offer, sent_on="2026-10-21") is None
    explaining = ("Thanks for reaching out. Our analytics team is no longer part of the "
                  "Manchester office, so I'm not the right person. Best of luck.")
    assert state.auto_reply(explaining, sent_on="2026-10-21") is None
    # The templates are still read as what they are.
    assert state.auto_reply("Wren Allard is no longer with Fernhill Freight. For urgent "
                            "matters contact the planning desk.")["kind"] == "left"
    assert state.auto_reply("This person is no longer employed by Kestrel Mutual.")["kind"] == "left"
    assert state.auto_reply("The person you are trying to reach is no longer with the "
                            "company.")["kind"] == "left"
    assert state.auto_reply("I am out of the office until 3 November with limited access to "
                            "email.", sent_on="2026-10-21")["kind"] == "away"


def test_two_messages_one_day_with_one_summary_are_two_not_a_copy():
    """An export import gives a day's messages one summary: their words tell them apart."""
    contacts = [_c("kes_rook", "Ana Rook", status="awaiting_reply", channel="message")]
    day = "2026-10-01"
    two = [_t("kes_rook", day, "out", "first_message", "Hi Ana, a first message.",
              summary="from the LinkedIn export"),
           _t("kes_rook", day, "out", "first_message", "Hi Ana, and the file I mentioned.",
              summary="from the LinkedIn export")]
    assert not [p for p in state.reconcile(contacts, two) if p["reason"] == "duplicate_message"]
    copied = two[:1] + [dict(two[0])]
    found = [p for p in state.reconcile(contacts, copied) if p["reason"] == "duplicate_message"]
    assert len(found) == 1 and "2 identical rows" in found[0]["detail"]
