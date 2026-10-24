"""Accepting a connection request is not a referral offer, and a chat offered is a yes.

"Happy to connect" is the commonest reply LinkedIn carries, and the referral cue read
"connect" as an introduction whatever followed it. Every such reply in one real log was
a referral offer at 0.92, two of thirteen really were ("happy to connect you with a
recruiter"), and the guidance said to accept an introduction and send the resume unasked
(2026-10-24). A chat offered ("happy to connect over a coffee chat") read as a referral
too, or as substance to engage with point by point, when the move is to settle a time.
Every person, employer and message here is invented.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tools" / "network")]

import reply  # noqa: E402


def test_a_plain_acceptance_is_never_a_referral():
    for text in ("Hi Juno, happy to connect!", "Happy to connect!", "I'm happy to connect, Juno",
                 "Hey Juno, for sure! Happy to connect, welcome to the city!",
                 "Hi Juno, happy to connect. My suggestion is to check our careers page often.",
                 "Thanks for reaching out, I'd be glad to connect with you here."):
        got = reply.classify(text)
        assert got["scenario"] != "referral_offered", (text, got)
    assert reply.classify("Hi Juno, happy to connect!")["scenario"] == "low_effort"


def test_connecting_you_with_someone_is_still_a_referral():
    for text in ("Recommend a look at our open roles, happy to connect you with a recruiter "
                 "if something appeals.",
                 "I can connect you with Wren on the data team.",
                 "Happy to refer you for the analyst role.",
                 "I'd be happy to introduce you to Bo, who runs planning.",
                 "Happy to pass your profile on to the hiring manager."):
        got = reply.classify(text)["scenario"]
        assert got in ("referral_offered", "send_resume"), (text, got)


def test_a_chat_offered_is_a_yes_and_the_move_is_a_time():
    text = ("Hi Juno, great to connect with you, and welcome! I'm not directly involved in "
            "forecasting models; my work is more on data products. Not sure how much overlap "
            "there is between our areas of work, but I'd be happy to connect over a coffee chat!")
    got = reply.classify(text)
    assert got["scenario"] == "chat_offered", got
    g = reply.guidance(got)
    assert "two specific times" in g["move"] and g["next_action"]
    assert any("referral" in d for d in g["do_not"])


def test_a_chat_offered_beside_a_no_is_not_a_no():
    for text in ("Not hiring right now, but I'd be happy to connect over a coffee chat!",
                 "We're not hiring at the moment, but let's chat next week."):
        assert reply.classify(text)["scenario"] == "chat_offered", text
        assert reply.declines_in([{"direction": "in", "full_text": text}]) == [], text


def test_a_no_with_a_polite_close_still_counts_as_one():
    # "Happy to connect for the future" keeps in touch; it offers no time, and the no
    # beside it is one of the two that end a thread, as any other no is.
    text = ("Thanks for reaching out. We're not hiring right now, but happy to connect for "
            "the future!")
    assert reply.classify(text)["scenario"] == "rejection"
    assert len(reply.declines_in([{"direction": "in", "full_text": text}])) == 1


def test_a_chat_declined_is_not_a_chat_offered():
    # The same words with a no in front of them read as they did before chat_offered.
    for text in ("Sorry, I'm not available to chat at the moment.",
                 "I won't be free to talk until next month, but feel free to apply.",
                 "We're not hiring and I'm not keen to talk about roles."):
        assert reply.classify(text)["scenario"] != "chat_offered", text
    assert reply.classify("I'm not sure about roles, but happy to chat.")["scenario"] == "chat_offered"


def test_a_chat_declined_is_still_a_no_that_counts():
    # The guard applies to the yes that excuses a no, too: these were rejections before
    # chat_offered, and two of them end a thread.
    for text in ("No thanks, I'm not free to talk.",
                 "Sorry, not available to chat. We're not hiring.",
                 "Unfortunately we're not hiring at the moment, and I'm not available to chat."):
        assert reply.classify(text)["scenario"] == "rejection", text
        assert len(reply.declines_in([{"direction": "in", "full_text": text}])) == 1, text


def test_a_talk_with_somebody_else_is_not_a_chat_offered():
    for text in ("Feel free to talk to HR about it.",
                 "Not hiring at the moment, but feel free to speak with our talent team.",
                 "We're always open to talk with talented people, so please apply online."):
        assert reply.classify(text)["scenario"] != "chat_offered", text
    assert reply.declines_in([{"direction": "in", "full_text":
                               "Not hiring at the moment, but feel free to speak with our "
                               "talent team."}])
    # A hedge is not a no.
    assert reply.classify("Not sure I'm free to talk this week, but next week works"
                          )["scenario"] == "chat_offered"
