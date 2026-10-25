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


def test_a_return_date_with_no_year_is_read_from_the_day_it_came():
    # Pasted on 28 December, "back on 5 January" is the coming January, whatever today is.
    note = ("Automatic reply: I am out of the office until 5 January with limited access to "
            "email. I will reply when I am back.")
    advice = reply.guidance(reply.classify(note, [SENT], "2026-12-28"))
    assert "away until 2027-01-05" in advice["next_action"]


# A person who answers while mentioning leave has replied (networking audit, 2026-10-25):
# each of these was read as an out-of-office, so the reply was hidden and a nudge offered.
ANSWERED_WHILE_AWAY = (
    "Thanks Morgan, I'm on parental leave until January so not the best person to ask. Try "
    "Bo Venn on the analytics team, she runs hiring there.",
    "Hi Morgan, I'm out of the office until the 20th, but Bo Venn runs hiring for that team.",
    "Hi Morgan, I'm away until Monday. Our team isn't hiring right now, sorry.",
    "I'm on holiday until 2 November. Not interested, thanks.",
    "I am on leave until 30 October. When I return I'll take a look at your profile.",
    "I'm on maternity leave until spring, so I can't help with this one. Good luck!",
    "I'm out of office until Thursday. Speak to Priya Shah in talent, she's the one hiring.",
    "I'm away until 4 November, and we aren't recruiting for analysts this quarter.",
)
# And these are templates, whatever else they say: a redirect for urgent matters, a promise
# to answer email on return, a greeting that names nobody.
STILL_AUTOMATIC = (
    OOO,
    "Hello, I am currently on annual leave until 15 November and will have limited access to "
    "email. If your matter is urgent, please contact Jane Smith on 0123 456. Otherwise I will "
    "respond to your email on my return.",
    "Hi, I'm on parental leave until March 2027. For anything urgent please reach out to "
    "analytics-team@example.com. Thanks!",
    "I'm away from my desk until Monday 3rd. I'll get back to you when I return.",
    "Thanks for your message. I'm out of the office until 1 Nov, with no access to email.",
    "Hello there, I am out of the office until Monday. For urgent queries please contact Bo "
    "Venn, who is covering for me.",
    "Dear All, I am on annual leave until 2 December. I will reply on my return.",
    "Thank you for your message. I'm currently on vacation until Nov 3 with intermittent "
    "access to email.",
)


def test_an_answer_that_mentions_leave_is_a_reply_and_owed_one():
    for text in ANSWERED_WHILE_AWAY:
        assert state.auto_reply(text, sent_on="2026-10-12") is None, text
        theirs = _row("2026-10-12", "in", text)
        rows = [SENT, theirs]
        assert state.said_something(theirs), text
        assert state.derive_status(rows) == "replied_needs_response", text
        assert [o["kind"] for o in state.owed([CONTACT], rows, "2026-10-21")] == ["reply"], text
        assert reply.classify(text, [SENT], "2026-10-12")["scenario"] != "auto_reply", text


def test_a_template_that_mentions_leave_is_still_automatic():
    for text in STILL_AUTOMATIC:
        got = state.auto_reply(text, sent_on="2026-10-12")
        assert got is not None and got["kind"] == "away", text
        assert state.derive_status([SENT, _row("2026-10-12", "in", text)]) == "awaiting_reply"


def test_a_message_logged_as_a_persons_answer_is_never_an_automatic_reply():
    offered = _row("2026-10-12", "in", OOO, scenario="referral_offered")
    assert not state.is_auto_reply(offered) and state.said_something(offered)
    assert state.derive_status([SENT, offered]) == "replied_needs_response"
    assert state.is_auto_reply(_row("2026-10-12", "in", OOO, scenario="auto_reply"))
    assert state.is_auto_reply(_row("2026-10-12", "in", OOO))
