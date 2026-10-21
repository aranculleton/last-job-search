"""An out-of-office is not a reply.

An email logged inbound that read "I am out of the office until 20 October" derived
`replied_needs_response`: the employer became a warm route ("DO NOT APPLY COLD"), a reply
was owed to an inbox nobody was reading, `reply.classify` answered it as four generous
paragraphs, and the nudge the thread actually needed was refused because "they answered".
Nobody had said anything. These pin that an automatic reply changes none of that, and
that the one nudge waits until they are back.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "network"))

import reply  # noqa: E402
import state  # noqa: E402
import throttle  # noqa: E402
import what_works as W  # noqa: E402

CID = "fernhill_freight_halloway"
CONTACT = {"contact_id": CID, "name": "Wren Halloway", "company": "Fernhill Freight",
           "status": "awaiting_reply", "route": "cold"}
OOO = ("Thank you for your email. I am out of the office until 20 October with limited "
       "access to email. For urgent matters contact reception@example.com.")


def _row(date, direction, text, **kw):
    return dict({"contact_id": CID, "date": date, "direction": direction, "channel": "email",
                 "scenario": "", "summary": "", "full_text": text}, **kw)


SENT = _row("2026-10-01", "out", "Hi Wren, how is the planning team set up for peak?")
AWAY = _row("2026-10-01", "in", OOO)


def test_the_thread_still_waits_on_them_and_no_route_is_warm():
    rows = [SENT, AWAY]
    assert state.derive_status(rows) == "awaiting_reply"
    assert state.effective_status(CONTACT, rows) not in throttle.RESPONDED
    assert not state.said_something(AWAY)


def test_a_real_reply_after_it_is_a_reply():
    rows = [SENT, AWAY, _row("2026-10-21", "in", "Back now. Happy to chat next week.")]
    assert state.derive_status(rows) == "replied_needs_response"


def test_no_reply_is_owed_and_the_nudge_waits_until_they_are_back():
    rows = [SENT, AWAY]
    # Seven business days after the message the nudge would be due; they are away until
    # the 20th, so it waits until two working days after that.
    assert state.owed([CONTACT], rows, "2026-10-12") == []
    due = reply.nudge_due(rows, "2026-10-12")
    assert not due["due"] and "away until 2026-10-20" in due["reason"]
    assert due["due_date"] == "2026-10-22" and due["last_out"] == "2026-10-01"
    owed = state.owed([CONTACT], rows, "2026-10-22")
    assert [(o["kind"], o["due"], o["since"]) for o in owed] == [
        ("nudge", "2026-10-22", "2026-10-01")]


def test_with_no_return_date_the_usual_clock_runs_from_our_message():
    plain = _row("2026-10-01", "in", "This is an automated response. Your message has been "
                 "received and will be read shortly.")
    rows = [SENT, plain]
    owed = state.owed([CONTACT], rows, "2026-10-09")
    assert [(o["kind"], o["since"]) for o in owed] == [("nudge", "2026-10-01")]


def test_it_is_read_as_an_automatic_reply_and_told_what_to_do():
    got = reply.classify(OOO, [SENT, AWAY], "2026-10-05")
    assert got["scenario"] == "auto_reply" and got["confidence"] >= 0.9
    advice = reply.guidance(got)
    assert "away until 2026-10-20" in advice["next_action"]
    assert advice["target_sentences"] == 0
    left = reply.classify("Automatic reply: Wren Halloway is no longer with Fernhill Freight. "
                          "Please contact careers@example.com.")
    assert left["scenario"] == "auto_reply"
    assert "find who holds the role now" in reply.guidance(left)["next_action"]


def test_scenario_logged_as_auto_reply_counts_whatever_the_words():
    logged = _row("2026-10-02", "in", "", scenario="auto_reply", summary="away message")
    assert state.derive_status([SENT, logged]) == "awaiting_reply"


def test_a_person_who_mentions_being_away_has_still_replied():
    for text in ("I'm out of the office until Monday, but happy to chat then. Does Tuesday work?",
                 "Thanks, I've passed your details to the hiring manager. I'm out of the office "
                 "next week, so expect to hear after that.",
                 "Wren is no longer with us, but I'd be glad to help."):
        assert state.auto_reply(text) is None, text
        assert state.derive_status([SENT, _row("2026-10-02", "in", text)]) == \
            "replied_needs_response"


def test_other_languages_are_recognised():
    for text in ("Abwesenheitsnotiz: Ich bin bis 3. November nicht im Büro.",
                 "Réponse automatique : je suis absente jusqu'au 4 novembre.",
                 "Respuesta automática: estoy fuera de la oficina hasta el lunes."):
        assert state.auto_reply(text) is not None, text


def test_what_works_never_counts_it_as_the_message_that_drew_a_reply():
    cases = W.message_cases([CONTACT], [SENT, AWAY], "2026-11-01")
    assert [c["won"] for c in cases] == [False]
