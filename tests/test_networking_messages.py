"""Every outbound networking message is one the person can send, and every reply is read right.

Found by reading the composers and the reply classifier against the example person:

- the limits were a Premium account's for everyone, so a free account was handed
  300-character notes and InMail it could not send;
- an InMail had no subject, and none of the first note's rules;
- "Not interested, thanks." read as a short friendly reply, and "not hiring, but happy
  to chat" as a no, so a booked call could be closed after two of them;
- an empty /reply on a thread we had already answered re-read their old message and
  drafted a CV already sent;
- the plain ways of asking for a job ("any openings on your team?") passed the first note.
"""
from __future__ import annotations

import importlib
import os
import shutil
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "network"))

import compose  # noqa: E402
import outreach  # noqa: E402
import person  # noqa: E402
import reply  # noqa: E402
import schema  # noqa: E402
import state  # noqa: E402


# ------------------------------------------------------------------ the plan

@pytest.fixture
def plan(tmp_path, monkeypatch):
    """Reload schema against a copy of the example whose plan the test sets."""
    d = tmp_path / "profile"
    shutil.copytree(os.path.join(ROOT, "profile.example"), d)
    net = d / "networking.py"

    def use(line):
        text = net.read_text(encoding="utf-8").replace('LINKEDIN_PLAN = "premium"\n', line)
        net.write_text(text, encoding="utf-8")
        monkeypatch.setenv(person.ENV, str(d))
        person._modules.clear()
        person._data.clear()
        return importlib.reload(schema)
    yield use
    monkeypatch.undo()
    person._modules.clear()
    person._data.clear()
    importlib.reload(schema)


def test_with_no_plan_recorded_the_free_limits_apply(plan):
    s = plan("")
    assert s.PLAN == "free"
    assert s.LIMITS["connection_note_chars"] == 200
    assert s.LIMITS["inmail_credits_per_month"] == 0
    assert s.LIMITS["nudge_chars"] < s.LIMITS["connection_note_chars"]


def test_premium_and_an_override(plan):
    s = plan('LINKEDIN_PLAN = "Premium"\nLINKEDIN_LIMITS = {"inmail_credits_per_month": 15}\n')
    assert (s.PLAN, s.LIMITS["connection_note_chars"], s.LIMITS["inmail_credits_per_month"]) \
        == ("premium", 300, 15)


def test_the_budget_says_the_plan_and_counts_what_is_queued():
    contacts = [{"contact_id": "a_x", "status": "not_contacted", "channel": "connection"},
                {"contact_id": "a_y", "status": "not_contacted", "channel": "inmail"}]
    b = state.platform_budget(contacts, [], "2026-10-15")
    assert b["plan"] == schema.PLAN
    assert b["queued_unsent"] == {"connection": 1, "inmail": 1}


def test_the_budget_counts_requests_sent_and_caps_none():
    # 2026-10-15 is a Thursday: 125 requests went today and 5 on Monday. The app holds
    # nothing back: LinkedIn says when its own weekly limit is reached (2026-10-22).
    sent = [{"contact_id": f"c{i}", "status": "awaiting_reply", "channel": "connection",
             "first_contacted": "2026-10-15" if i < 125 else "2026-10-12"} for i in range(130)]
    b = state.platform_budget(sent, [], "2026-10-15")
    assert b["connections_today"] == 125 and b["connections_sent"] == 130
    assert not any(k.startswith("connections_left") or k == "connections_limit" for k in b)
    assert b["note"] == ""


# ------------------------------------------------------------------ InMail

INMAIL = dict(
    name="SASHA REED", subject="Your forecasting talk at Northern Data Week",
    common_ground="Your talk at Northern Data Week on forecasting stock levels stuck with me",
    question="How did your team settle on building the forecasts in-house",
    evidence=("At Brindle & Hart I built weekly demand forecasts across 2,400 SKUs, cutting "
              "forecast error from 22% to 14%"))


def test_an_inmail_has_a_subject_and_the_first_notes_shape():
    m = compose.inmail(**INMAIL)
    subject, body = m.split("\n\n", 1)
    assert subject == "Subject: Your forecasting talk at Northern Data Week"
    assert body.startswith("Hi Sasha,")                       # not "Hi SASHA,"
    assert "?" in body and "22% to 14%" in body
    assert compose.validate(m, "inmail", name="Sasha Reed") == []


@pytest.mark.parametrize("subject", ["Quick question", "Job enquiry", "Opportunity",
                                     "Are you hiring analysts?"])
def test_a_subject_that_says_nothing_or_asks_for_the_job_is_refused(subject):
    with pytest.raises(ValueError):
        compose.inmail(**dict(INMAIL, subject=subject))


def test_no_subject_given_is_the_identity_line_that_drew_a_reply():
    # "<title>, ex-<employers>": who they are, not a topic.
    m = compose.inmail(**dict(INMAIL, subject=""))
    assert m.subject == compose.identity_subject()
    assert m.subject == "Senior Operations Analyst, ex-Oakmere and Saltmarsh Analytics"
    assert m["body"] == m.body and str(m).startswith(f"Subject: {m.subject}\n\n")
    assert compose.validate(m, "inmail", name="Sasha Reed") == []
    with pytest.raises(ValueError):
        compose.inmail_subject("")


def test_an_inmail_that_asks_for_the_job_is_refused_and_validate_sees_it():
    with pytest.raises(compose.AsksForTheJob):
        compose.inmail(**dict(INMAIL, question="Do you have any openings on your team"))
    body = compose.inmail(**INMAIL).split("\n\n", 1)[1]
    rules = {v.rule for v in compose.validate(body + " Are you hiring?", "inmail")}
    assert {"no_subject", "asks_for_the_job"} <= rules


# ------------------------------------------------------------------ the first note

@pytest.mark.parametrize("text", [
    "Do you have any openings on your team?",
    "Are there any vacancies in your group?",
    "Are you looking to add analysts?",
    "Could you refer me for the Senior Analyst job?",
    "Are you recruiting for a forecasting analyst?",
    "I'd like to be considered for the Senior Analyst position",
    "I am applying to your team's Senior Analyst opening",
])
def test_the_plain_ways_of_asking_for_the_job_are_caught(text):
    assert compose.first_note_findings(text)


@pytest.mark.parametrize("reader", ["peer", "decision_maker"])
@pytest.mark.parametrize("text", [
    "I'd love a referral for the Staff Data Scientist role.",
    "Would you be open to giving me an internal referral?",
    "Could you put my name forward for the planning role?",
])
def test_a_referral_asked_for_in_a_first_note_is_refused(text, reader):
    note = "Hi Ana, I saw your talk on demand planning at the Leeds meetup. " + text
    assert "asks_for_the_job" in {v.rule for v in compose.validate(note, "connection",
                                                                   reader=reader)}


def test_a_referral_mentioned_without_asking_for_one_is_not_an_ask():
    for text in ("You came in through a referral, I read, and stayed six years.",
                 "Your referral programme for graduates sounds generous."):
        assert not compose.first_note_findings(text, reader="peer"), text


def test_a_recruiter_may_still_be_asked():
    assert not compose.first_note_findings(
        "I'd love a referral for the Staff Data Scientist role.", reader="recruiter")


def test_common_ground_about_openings_is_not_a_job_ask():
    assert not compose.first_note_findings("Your talk on the store openings in Leeds stuck with me")


def test_a_question_ends_in_a_question_mark_and_a_statement_does_not():
    assert compose._sentence("Would you have 15 minutes sometime") == \
        "Would you have 15 minutes sometime?"
    assert compose._sentence("Would love to hear more") == "Would love to hear more."
    assert compose._sentence("Do let me know") == "Do let me know."
    assert compose._sentence("What you wrote about forecasting stuck with me").endswith("me.")
    assert compose._sentence("How did the team start").endswith("?")


def test_beside_their_hiring_the_looking_clause_goes():
    hiring = compose._about_me_for("Saw your post about hiring a forecasting analyst",
                                   compose.ABOUT_ME)
    assert "looking" not in hiring and hiring
    assert compose._about_me_for("Your talk stuck with me", compose.ABOUT_ME) == compose.ABOUT_ME


def test_a_nudge_and_a_connection_sized_intro_can_be_validated():
    long = "Hi Sasha, " + "following up on my note. " * 20
    assert any(v.rule == "too_long" for v in compose.validate(long, "nudge"))
    assert any(v.rule == "too_long" for v in compose.validate(long, "intro_connection"))


def test_a_warm_intro_keeps_to_its_word_ceiling():
    with pytest.raises(compose.TooLong):
        compose.warm_intro("Jane Smith", "Wren Halloway",
                           "Jane Smith suggested I write. " + "More detail here. " * 120)


# ------------------------------------------------------------------ replies

@pytest.mark.parametrize("text", ["Not interested, thanks.", "Please stop messaging me.",
                                  "Sorry, I can't make time for a call", "I'm going to pass",
                                  "I don't think I'm the right person"])
def test_a_no_to_the_conversation_is_read_as_a_no(text):
    assert reply.classify(text, [], "2026-10-15")["scenario"] == "rejection"


def test_not_hiring_but_happy_to_chat_is_not_a_no():
    assert reply.classify("We're not hiring right now but happy to chat", [],
                          "2026-10-15")["scenario"] != "rejection"
    rows = [{"contact_id": "x", "date": "2026-09-01", "direction": "in",
             "full_text": "We're not hiring right now but happy to chat"},
            {"contact_id": "x", "date": "2026-09-03", "direction": "in",
             "full_text": "No open roles at the moment either, Thursday 3pm works"}]
    assert reply.should_continue({"contact_id": "x", "status": "in_conversation"}, rows)[0]


def test_two_real_nos_stop_the_thread_but_never_a_booked_call():
    rows = [{"contact_id": "x", "date": "2026-09-01", "direction": "in",
             "full_text": "Not interested, thanks."},
            {"contact_id": "x", "date": "2026-09-10", "direction": "in",
             "full_text": "Please stop messaging me."}]
    assert not reply.should_continue({"contact_id": "x", "status": "in_conversation"}, rows)[0]
    assert reply.should_continue({"contact_id": "x", "status": "call_booked"}, rows)[0]


def test_talk_to_a_named_colleague_is_a_referral():
    assert reply.classify("Thanks Sam, I'm not the right person but talk to Wren Halloway",
                          [], "2026-10-15")["scenario"] == "referral_offered"


def test_an_empty_reply_after_we_answered_is_a_quiet_thread_not_their_old_message():
    rows = [{"contact_id": "x", "date": "2026-09-01", "direction": "out", "channel": "connection",
             "full_text": "Hi Sasha"},
            {"contact_id": "x", "date": "2026-09-03", "direction": "in",
             "full_text": "Sure, send me your CV at sasha@example.com"},
            {"contact_id": "x", "date": "2026-09-04", "direction": "out", "full_text": "Sent."}]
    assert reply.classify("", rows, "2026-10-15")["scenario"] == "gone_quiet"
    assert reply.classify("", rows[:2], "2026-10-15")["scenario"] == "send_resume"


# ------------------------------------------------------------------ the outreach note

LETTER = {"company": "Wrenfield Freight Ltd", "role": "Senior Supply Chain Analyst",
          "abbr": "Wrenfield", "posting": "A posting.", "lead": "", "cl_bullets": [],
          "p4": "", "summary": "", "tools": "",
          "p1": ("Chilled and ambient volumes behave differently, and a forecast that treats "
                 "them as one stream fills the wrong trailers. At Brindle & Hart I forecast "
                 "both, by depot, every week."),
          "p2": "Wrenfield moves goods across the North West for retailers."}


def test_the_note_meets_the_networking_tone_rules():
    assert outreach.check_note(outreach.outreach_note(LETTER)) == []
    bad = ("Hi [name], I've just applied. At Brindle & Hart I forecast stock. As a British "
           "citizen I need no sponsorship.")
    assert any("unsupported" in p or "claim" in p for p in outreach.check_note(bad))


def test_a_note_longer_than_a_request_gets_a_version_that_fits(tmp_path, monkeypatch):
    monkeypatch.setattr(outreach.person, "state", lambda *parts: str(tmp_path.joinpath(*parts)))
    monkeypatch.setitem(schema.LIMITS, "connection_note_chars", 200)
    d = outreach.write(dict(LETTER), {}, "2026-10-15")
    text = open(os.path.join(d, "outreach.md"), encoding="utf-8").read()
    assert "Characters:" in text and "connection request instead" in text
    short = outreach.short_note(LETTER, 200)
    assert short and len(short) <= 200


def test_someone_who_has_not_replied_is_never_asked_for_the_referral(tmp_path, monkeypatch):
    monkeypatch.setattr(outreach.person, "state", lambda *parts: str(tmp_path.joinpath(*parts)))
    monkeypatch.setattr(outreach, "_known_contacts", lambda company: [
        {"name": "Wren Halloway", "title": "Head of Planning", "status": "awaiting_reply"}])
    d = outreach.write(dict(LETTER), {}, "2026-10-15")
    text = open(os.path.join(d, "outreach.md"), encoding="utf-8").read()
    assert "Do not message them again" in text and "STOP" not in text


def test_the_note_checker_runs_from_the_command_line():
    import subprocess
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "outreach.py"), "--check-note",
                        outreach.outreach_note(LETTER)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
