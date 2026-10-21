"""LinkedIn's export, read into the message log, knows a resume by the names the app gives it.

The app names a resume `<Prefix>_CV_<ABBR>.pdf`. The export import read "_" as part of a
word, so "Morgan_Ellis_CV_KestrelMutual.pdf" was "an attachment", and a resume the person
had sent on LinkedIn stayed owed. And a resume the app had logged with words ("Sent my CV
as an attachment.") came back from the export as a second, wordless message on the same
day. Every person, address and message here is invented; the candidate is the example
person, whose word for the document is "CV".
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tools" / "network")]

import export  # noqa: E402
import state  # noqa: E402

ME = "https://www.linkedin.com/in/morgan-ellis-example"
THEM = "https://www.linkedin.com/in/example-quillon-varga"
HEAD = ("CONVERSATION ID,CONVERSATION TITLE,FROM,SENDER PROFILE URL,TO,RECIPIENT PROFILE URLS,"
        "DATE,SUBJECT,CONTENT,FOLDER,ATTACHMENTS\n")


def _book(root):
    contacts = [{"contact_id": "kes_varga", "name": "Quillon Varga", "company": "Kestrel Mutual",
                 "linkedin_url": THEM, "channel": "message", "status": "in_conversation"}]
    threads = [{"contact_id": "kes_varga", "date": "2026-09-28", "direction": "out",
                "channel": "connection", "scenario": "connection_note",
                "summary": "Connection note sent", "full_text": "Hi Quillon, I plan stock."},
               {"contact_id": "kes_varga", "date": "2026-09-30", "direction": "in",
                "channel": "message", "scenario": "", "summary": "",
                "full_text": "Send me your CV and I'll pass it on."}]
    c, t = str(root / "network_contacts.csv"), str(root / "network_threads.csv")
    state.save_contacts(contacts, c)
    state.save_threads(threads, t)
    return c, t


def _export(root, content, attachment):
    d = root / "export"
    d.mkdir(exist_ok=True)
    (d / "messages.csv").write_text(
        HEAD + f"c1,,Morgan Ellis,{ME},Quillon Varga,{THEM},2026-10-01 10:00:00 UTC,,"
               f"{content},INBOX,https://www.linkedin.com/dms/attach/{attachment}\n",
        encoding="utf-8")
    return str(d)


def _import(c, t, src):
    contacts, threads = state.load_contacts(c), state.load_threads(t)
    added = export.apply_history(threads, export.plan_history(contacts, threads, src), contacts)
    state.save_threads(threads, t)
    state.save_contacts(contacts, c)
    return added


def test_the_apps_own_resume_name_is_a_resume_and_settles_what_is_owed(tmp_path, monkeypatch):
    monkeypatch.setenv("LJS_STATE", str(tmp_path))
    c, t = _book(tmp_path)
    assert [o["contact_id"] for o in state.resumes_owed(state.load_contacts(c),
                                                        state.load_threads(t))] == ["kes_varga"]
    assert _import(c, t, _export(tmp_path, "Thanks Quillon.",
                                 "Morgan_Ellis_CV_KestrelMutual.pdf")) == 1
    last = state.load_threads(t)[-1]
    assert "a resume attached (Morgan_Ellis_CV_KestrelMutual.pdf)" in last["summary"]
    assert state.attached(last) == ["Morgan_Ellis_CV_KestrelMutual.pdf"]
    assert state.resumes_owed(state.load_contacts(c), state.load_threads(t)) == []
    # A letter is still only an attachment, and a short name with the word in it a resume.
    letter = {"ATTACHMENTS": "https://x.example/Morgan_Ellis_Cover_Letter_KestrelMutual.pdf",
              "CONTENT": ""}
    assert export._attachment(letter).startswith("an attachment attached")
    assert export._attachment({"ATTACHMENTS": "https://x.example/CV_2026.pdf", "CONTENT": ""}) \
        == "a resume attached (CV_2026.pdf)"


def test_a_resume_logged_with_words_is_not_added_again_without_them(tmp_path, monkeypatch):
    monkeypatch.setenv("LJS_STATE", str(tmp_path))
    c, t = _book(tmp_path)
    cv = tmp_path / "documents" / "cv" / "Morgan_Ellis_CV_current.pdf"
    cv.parent.mkdir(parents=True)
    cv.write_bytes(b"%PDF")
    contacts, threads = state.load_contacts(c), state.load_threads(t)
    # The person sent the CV alone on LinkedIn; the app needs words, so they said what they did.
    state.followed_up(contacts, threads, "kes_varga", "2026-10-01",
                      text="Sent my CV as an attachment.", date="2026-10-01",
                      attached="documents/cv/Morgan_Ellis_CV_current.pdf")
    state.save_threads(threads, t)
    state.save_contacts(contacts, c)
    before = len(state.load_threads(t))
    src = _export(tmp_path, "", "Morgan_Ellis_CV_current.pdf")
    for _ in (1, 2):
        assert _import(c, t, src) == 0
        assert len(state.load_threads(t)) == before
    # A different file sent alone on that day is its own message.
    other = tmp_path / "other"
    other.mkdir()
    (other / "messages.csv").write_text(
        HEAD + f"c1,,Morgan Ellis,{ME},Quillon Varga,{THEM},2026-10-01 11:00:00 UTC,,,INBOX,"
               "https://www.linkedin.com/dms/attach/Portfolio_2026.pdf\n", encoding="utf-8")
    assert _import(c, t, str(other)) == 1
    assert os.path.basename(state.attached(state.load_threads(t)[-1])[0]) == "Portfolio_2026.pdf"


def test_a_logged_resume_is_shown_in_the_persons_own_word_and_case(tmp_path, monkeypatch):
    # The example person's word is "CV": the line said "cv sent (message), as asked; a
    # resume attached", lower-casing their word and mixing in another one.
    monkeypatch.setenv("LJS_STATE", str(tmp_path))
    c, t = _book(tmp_path)
    cv = tmp_path / "documents" / "cv" / "Morgan_Ellis_CV_current.pdf"
    cv.parent.mkdir(parents=True)
    cv.write_bytes(b"%PDF")
    contacts, threads = state.load_contacts(c), state.load_threads(t)
    got = state.followed_up(contacts, threads, "kes_varga", "2026-10-01",
                            text="Sent my CV as an attachment.", date="2026-10-01",
                            attached="documents/cv/Morgan_Ellis_CV_current.pdf")
    assert state.shown_summary(got["row"]) == \
        "CV sent (message), as asked; a CV attached (documents/cv/Morgan_Ellis_CV_current.pdf)"
    # The stored marker is the one every reader shares, unchanged.
    assert "a resume attached (documents/cv/Morgan_Ellis_CV_current.pdf)" in got["row"]["summary"]
    # Other lines read as before mid-sentence, and keep a proper name's case.
    assert state.shown_summary({"summary": "Nudge sent (message)"}) == "nudge sent (message)"
    assert state.shown_summary(
        {"summary": "Message sent, from LinkedIn's export; an attachment attached "
                    "(Portfolio_2026.pdf)"}) == \
        "message sent, from LinkedIn's export; an attachment attached (Portfolio_2026.pdf)"
