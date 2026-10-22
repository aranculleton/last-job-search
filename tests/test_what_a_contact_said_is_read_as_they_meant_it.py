"""What a contact wrote back, and what the person wrote, read as they meant it.

Three readings went wrong in a re-audit of the networking fixes. "I'll pass on the
opportunity" was a referral offer, so a decline counted as a warm route and not towards the
two that end a thread. "My CV went through the portal" closed a resume owed to the contact,
which never reached them. "Fernhill Freight is no longer part of the Brindle group" was the
automatic "no longer with us" reply, so a person's answer got nothing drafted. Every
person, employer and message here is invented.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tools" / "network")]

import reply  # noqa: E402
import schema  # noqa: E402
import state  # noqa: E402


# ------------------------------------------------------------------ "pass on"

def test_passing_on_the_opportunity_is_a_no_and_passing_on_a_cv_is_not():
    for no in ("Thanks, but I'll pass on the opportunity.", "I'll pass on the offer, thanks.",
               "I will pass on the call, thanks for understanding.", "I'll pass on it, thanks.",
               "I'll pass on your kind offer.", "I'll pass on the call for now, thanks.",
               "Appreciate it, but I'll pass on the chance to chat."):
        got = reply.classify(no)
        assert got["scenario"] == "rejection", (no, got)
        assert len(reply.declines_in([{"direction": "in", "full_text": no}])) == 1, no
    # Handing something on is still a referral (or the resume ask it carries).
    for on in ("I'll pass on your profile to the hiring manager.", "I'll pass on the details.",
               "I'll pass on to the hiring manager.", "I'll pass it on to the team.",
               "I'll pass the message on to our talent team.", "I'll pass that to Wren in planning.",
               "I'll pass you to Bo, who runs the team."):
        got = reply.classify(on)["scenario"]
        assert got in ("referral_offered", "send_resume"), (on, got)
        assert reply.declines_in([{"direction": "in", "full_text": on}]) == [], on


# ------------------------------------------------------------------ the resume reached them

def _out(text):
    return {"contact_id": "kes_ansgar", "date": "2026-10-16", "direction": "out",
            "channel": "message", "scenario": "reply", "summary": "Reply sent (message)",
            "full_text": text}


def test_a_resume_that_went_to_the_portal_never_reached_the_contact():
    for elsewhere in ("I've updated my CV and sent the application through the portal today.",
                      "My CV went through the portal this morning, so no need to pass it on.",
                      "My CV is attached to my LinkedIn profile if that helps.",
                      "I applied with my CV through the careers site yesterday."):
        assert not state.says_resume_went(_out(elsewhere)), elsewhere
    for went in ("Here is my CV, as promised.", "I'm attaching my CV.",
                 "Please find my CV attached; I also applied through the portal."):
        assert state.says_resume_went(_out(went)), went


def test_a_portal_message_leaves_the_resume_owed():
    contacts = [{"contact_id": "kes_ansgar", "name": "Pell Ansgar", "company": "Kestrel Mutual",
                 "status": "in_conversation"}]
    threads = [{"contact_id": "kes_ansgar", "date": "2026-10-14", "direction": "in",
                "channel": "message", "full_text": "Send me your CV and I'll pass it on."},
               _out("My CV went through the portal this morning, so no need to pass it on.")]
    assert [o["contact_id"] for o in state.resumes_owed(contacts, threads)] == ["kes_ansgar"]


# ------------------------------------------------------------------ "is no longer with"

def test_an_employer_that_is_no_longer_part_of_a_group_is_a_person_explaining(tmp_path,
                                                                              monkeypatch):
    explaining = ("Thanks Morgan. Fernhill Freight is no longer part of the Brindle group, so "
                  "I'm not sure I can help, but try our careers page.")
    assert state.auto_reply(explaining) is None
    assert reply.classify(explaining)["scenario"] != "auto_reply"
    # An employer the contact book holds, whatever it is no longer with.
    monkeypatch.setenv("LJS_STATE", str(tmp_path))
    with open(tmp_path / "network_contacts.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=schema.CONTACT_COLUMNS)
        w.writeheader()
        w.writerow({"contact_id": "oak_reed", "name": "Riley Reed",
                    "company": "Oakmere Foods"})
    assert state.auto_reply("Oakmere Foods is no longer with the old payroll provider. "
                            "Try the careers page.") is None
    # A person, named or by pronoun, is still the template.
    for gone in ("Riley Reed is no longer with Oakmere Foods. Please contact "
                 "hr@oakmere.example.com.",
                 "Riley is no longer with Oakmere Foods.",
                 "She is no longer with the company. This mailbox is not monitored.",
                 "Hi, Bo Venn has left the company. This mailbox is not monitored."):
        assert state.auto_reply(gone)["kind"] == "left", gone


# ------------------------------------------------------------------ a polite no

def test_a_polite_no_without_cant_is_a_no_and_a_route_on_stays_one():
    # "I can't help" was already a no; these are the same answer said more gently, and were
    # read as a considered, generous reply that counted toward nothing.
    for no in ("Thanks for reaching out. I'm not sure I can help, sorry.",
               "I'm not sure I can help with that, good luck with the search.",
               "Hi Morgan, I don't think I can help here, but best of luck.",
               "I'm not the best person to help with this one.",
               "I'm afraid I can't really help, sorry.",
               "Thanks Morgan. Fernhill Freight is no longer part of the Brindle group, so I'm "
               "not sure I can help, but try our careers page."):
        got = reply.classify(no)
        assert got["scenario"] == "rejection", (no, got["scenario"])
        assert len(reply.declines_in([{"direction": "in", "full_text": no}])) == 1, no
    # Counted the way "I can't help" already is.
    assert len(reply.declines_in([{"direction": "in", "full_text": "I can't help, sorry."}])) == 1
    # Pointed on to someone, it is that route, and no decline.
    for on in ("I'm not sure I can help, but try Wren Halloway in planning.",
               "I don't think I can help, but talk to Bo Venn on the data team."):
        assert reply.classify(on)["scenario"] == "referral_offered", on
        assert reply.declines_in([{"direction": "in", "full_text": on}]) == [], on
    # "But happy to chat" is a yes to the conversation, whatever came before it.
    yes = "Not sure I can help but happy to chat if useful."
    assert reply.classify(yes)["scenario"] != "rejection"
    assert reply.declines_in([{"direction": "in", "full_text": yes}]) == []


def test_a_no_that_points_them_on_is_not_one_of_the_two_nos():
    # Read as a referral, but counted as a decline it ended the very thread it opened.
    for on in ("I can't help, but talk to Wren Halloway in planning.",
               "I'm not the right person, but try Bo Venn on the data team."):
        assert reply.classify(on)["scenario"] == "referral_offered", on
        assert reply.declines_in([{"direction": "in", "full_text": on}]) == [], on
    for no in ("I can't help, sorry.", "Thanks, but I'll pass."):
        assert len(reply.declines_in([{"direction": "in", "full_text": no}])) == 1, no
