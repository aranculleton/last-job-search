"""A referral is asked only of someone who has engaged: the three stages are kept in code.

Outreach is a first note that asks for a conversation, the conversation, then a referral ask
for one linked role, "never compressed into one". Nothing in code kept it: a referral ask to
someone never written to composed, and validate() read it as a live thread and found
nothing. Every name here is invented.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tools" / "network")]

import compose  # noqa: E402
import state  # noqa: E402

LINK = "https://example.com/jobs/1"
CID = "corvid_ames"


def _msg(direction, text="", channel="message", scenario=""):
    return {"contact_id": CID, "date": "2026-10-10", "direction": direction,
            "channel": channel, "scenario": scenario, "summary": "", "full_text": text}


def _ask(thread):
    return compose.referral_ask("Tal Ames", "thanks again for the chat on Tuesday",
                                "Planning Analyst role at Corvid", LINK, thread=thread)


@pytest.mark.parametrize("thread", [
    [],
    [_msg("out", "Hi Tal, hope you're well.")],
    [_msg("out", "Hi Tal"), _msg("in", "Thank you for your email. I am out of the office until "
                                 "20 October with limited access to email.")],
    [_msg("out", "", channel="connection", scenario="connection_request"),
     _msg("in", "", channel="connection", scenario="connection_accepted")],
])
def test_nobody_who_has_not_engaged_is_asked(thread):
    with pytest.raises(ValueError, match="first note"):
        _ask(thread)


def test_it_needs_to_know_who_it_goes_to():
    with pytest.raises(ValueError, match="thread="):
        compose.referral_ask("Tal Ames", "thanks for the chat", "Planning Analyst", LINK)


@pytest.mark.parametrize("thread", [
    [_msg("out", "Hi Tal"), _msg("in", "Happy to help, what's the role?")],
    [_msg("out", "Hi Tal"), _msg("in", "", channel="call", scenario="call_held")],
])
def test_after_a_reply_or_a_call_it_is_asked(thread):
    assert LINK in _ask(thread)


def test_read_from_the_book_and_the_log_by_contact(tmp_path, monkeypatch):
    monkeypatch.setenv("LJS_STATE", str(tmp_path))
    contacts = [{"contact_id": CID, "name": "Tal Ames", "company": "Corvid",
                 "status": "awaiting_reply"}]
    threads = [_msg("out", "Hi Tal, hope you're well.")]
    state.save_contacts(contacts, str(tmp_path / "network_contacts.csv"))
    state.save_threads(threads, str(tmp_path / "network_threads.csv"))
    with pytest.raises(ValueError, match="first note"):
        _ask(CID)
    text = ("Hi Tal, thanks again. The Planning Analyst role at Corvid looks like a strong fit. "
            "Would you be comfortable referring me for it?\n\n" + LINK)
    assert "referral_ask_too_soon" in [r for r, _ in compose.validate(
        text, "referral_ask", name="Tal Ames", contact=CID)]
    # A relationship the book says replied before the log began counts.
    contacts[0]["status"] = "in_conversation"
    state.save_contacts(contacts, str(tmp_path / "network_contacts.csv"))
    assert LINK in _ask(CID)
    assert "referral_ask_too_soon" not in [r for r, _ in compose.validate(
        text, "referral_ask", name="Tal Ames", contact=CID)]
