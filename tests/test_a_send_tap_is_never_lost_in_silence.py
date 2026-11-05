"""An "I sent it" the store never answers is said, on its card, and never lost in silence.

The maintainer, 2026-11-05: an "I sent it" tap could be lost with no sign on the page. The
write had no time limit: a store that took it and never answered left the message gone from
its card ("I sent it" takes it off at once) with nothing said. Now the write has the Chat's
own limit (20 seconds), says "Saving…" on its card after a few seconds, and once the limit
passes the tap is undone on the card and the card says "Not saved. Tap I sent it again." (its toast first), in
Contacts and on To do's "Messages to send". Every person is the invented sample's.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_the_page_journeys import _sample, browser  # noqa: E402
from test_the_page_works_in_a_browser import _write  # noqa: E402

WIDE = {"width": 1280, "height": 900}
CLOCK = "2026-10-25T09:00:00Z"
JUNO = '#main [data-item="larkspur_retail_castellan"]'


@pytest.fixture(scope="module")
def run():
    yield from browser()


def test_a_send_the_store_never_answers_is_said_on_its_card(run, tmp_path):
    page = _write(tmp_path, "page", _sample())
    got = run("engine", html=page, viewport=WIDE, clock=CLOCK, fake={"canSend": "available", "hangWrites": True}, steps=[
        {"hash": "contacts", "read": JUNO},
        {"click": "I sent it: the message to Juno", "read": JUNO},
        {"tick": 4000, "open": "fold:contacts", "read": JUNO},
        {"tick": 20000, "read": JUNO},
        {"tick": 17000, "read": JUNO},
        {"hash": "todo", "read": '#main [data-item="grp:send"]'},
    ])
    assert not got["errors"], got["errors"]
    draft = "Your reply"
    assert draft in got["after"][0]["text"], got["after"][0]["text"]
    # Taken off at once, as a send is, then said to be saving while the store says nothing.
    assert draft not in got["after"][1]["text"], got["after"][1]["text"]
    assert "Saving" in got["after"][2]["text"], got["after"][2]["text"]
    # Past the limit: the message is back on the card at once, its toast saying it was not
    # saved; once the toast has gone, the card says it, and what to tap (said once at a time).
    assert draft in got["after"][3]["text"], got["after"][3]["text"]
    back = got["after"][4]["text"]
    assert draft in back and "Not saved. Tap I sent it again." in back, back
    # To do's Messages to send says it on Juno's row as well.
    todo = got["after"][5]["text"]
    assert "Juno" in todo and "Not saved. Tap I sent it again." in todo, todo
