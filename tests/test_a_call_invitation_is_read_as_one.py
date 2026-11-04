"""A call invitation in the words recruiters and contacts write it is read as one.

The most common reply a stranger gets is an invitation to a call: "Would you be free for a
20 minute call on Thursday at 2pm?". The reader knew only "happy to chat" and "let's talk",
so this was read as a long generous message, and the guidance said to engage with its
substance in three sentences and ask one question, with nothing about saying yes and
settling the time. The guidance is worked out again from their last message whenever a
reply is prepared, so a message already logged is read the new way at the next reply.
"""
from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "network"))

import reply  # noqa: E402


@pytest.mark.parametrize("text", [
    "Thanks for reaching out! Would you be free for a 20 minute call on Thursday at 2pm?",
    "Great to hear from you. Are you available for a quick call on Thursday?",
    "Could we set up a call this week?",
    "Do you have time for a chat on Friday?",
    "I'd love to arrange a 30-minute phone screen next week.",
    "Would you be open to a call?",
    "Thanks for applying. Can we schedule a short introductory call for Tuesday?",
    "Happy to chat, when suits you?",
])
def test_a_call_invitation_is_read_as_one(text):
    got = reply.classify(text)
    assert got["scenario"] == "chat_offered", (text, got)


@pytest.mark.parametrize("text", [
    "I'm not available for a call this week, but happy to answer by message.",
    "We set up a call centre in Leeds last year, so the team is growing fast there.",
    "Unfortunately I don't have time for a chat at the moment.",
])
def test_a_refusal_or_a_call_centre_is_not_an_invitation(text):
    assert reply.classify(text)["scenario"] != "chat_offered"
