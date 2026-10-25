"""A referral in flight holds while the referrer writes, until somebody says it is done.

The hold read the log's status, and the log reads the last word: when the referrer wrote
again ("I've passed your resume to the hiring manager"), a reply was owed, the status read
`replied_needs_response`, and the hold lifted. The throttle stopped blocking a cold
application at that employer, the held application nudge fell due, and the quiet-close
could close the application. A reply owed and a referral in flight are both true. Every
name here is invented.
"""
import csv
import datetime
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tools" / "network")]

import followups  # noqa: E402
import state  # noqa: E402
import throttle  # noqa: E402

CID = "acme_halloway"


def _contact(status="referral_in_progress"):
    return {"contact_id": CID, "name": "Wren Halloway", "title": "Analytics Lead",
            "company": "Acme", "company_key": "acme", "status": status,
            "first_contacted": "2026-10-01", "next_action": "Wait for her news"}


def _msg(date, direction, text):
    return {"contact_id": CID, "date": date, "direction": direction, "channel": "message",
            "scenario": "", "summary": "", "full_text": text}


THREAD = [_msg("2026-10-01", "out", "Hi Wren, hope you're well."),
          _msg("2026-10-03", "in", "Happy to refer you, send me your resume."),
          _msg("2026-10-04", "out", "Thanks Wren, attached.")]
UPDATE = _msg("2026-10-10", "in", "Quick update: I've passed your resume to the hiring manager.")
APPLIED = {"date": "2026-10-02", "company": "Acme", "role": "Analyst", "status": "applied",
           "notes": ""}


def _holds(contacts, threads):
    live = {c["contact_id"]: state.effective_status(c, threads) for c in contacts}
    return throttle.referral_holds(rows=contacts, live=live)


def test_the_referrers_update_keeps_the_hold_and_owes_a_reply():
    contacts, threads = [_contact()], THREAD + [UPDATE]
    assert state.effective_status(contacts[0], threads) == "replied_needs_response"
    assert "acme" in _holds(contacts, threads)
    assert [o["kind"] for o in state.owed(contacts, threads, "2026-10-12")] == ["reply"]


def test_the_application_nudge_stays_held_and_is_never_closed_quiet():
    contacts, threads = [_contact()], THREAD + [UPDATE]
    holds = _holds(contacts, threads)
    got = followups.review([dict(APPLIED)], datetime.date(2026, 10, 20), holds=holds)
    assert [it["state"] for it in got] == ["held"]
    assert "referral in progress" in " ".join(got[0]["held"])


def test_read_from_the_files_the_hold_stands_too(tmp_path):
    book, log = tmp_path / "network_contacts.csv", tmp_path / "network_threads.csv"
    with open(book, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(_contact()))
        w.writeheader()
        w.writerow(_contact())
    with open(log, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(UPDATE))
        w.writeheader()
        w.writerows(THREAD + [UPDATE])
    assert "acme" in throttle.referral_holds(str(book))


def test_the_person_saying_it_is_done_lifts_it():
    for status in ("in_conversation", "converted_to_application", "closed"):
        assert _holds([_contact(status)], THREAD + [UPDATE]) == {}, status
