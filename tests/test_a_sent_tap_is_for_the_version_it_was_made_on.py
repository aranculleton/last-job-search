"""An "I sent it" tap counts for the message it was made on, never the next one to that person.

Every message to one person carries one id (msg-<contact>), so "I sent it" on a check-in was
read against the reply drafted after it: the reply was hidden and the card said "Message sent"
(reported from a person's copy, 2026-11-05). A tap made on an older version (its rev_seen is
not the message's rev now) leaves the new draft to send. Every name here is the sample's,
invented.
"""
from __future__ import annotations

import copy
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_the_page_journeys import _sample, browser  # noqa: E402
from test_the_page_works_in_a_browser import _write  # noqa: E402

WIDE = {"width": 1400, "height": 900}
CLOCK = "2026-10-25T18:30:00Z"


@pytest.fixture(scope="module")
def run():
    yield from browser()


def _tap(rev):
    aid = "act~msg-juno-1~msg.sent~old"
    return {"actions/" + aid: {"item": "msg-juno-1", "action": "msg.sent", "value": {"on": "2026-10-24"},
                               "at": "2026-10-24T09:00:00Z", "rev_seen": rev, "tab": "t0"},
            "receipts/" + aid: {"applied_at": "2026-10-24T09:01:00Z", "result": "ok", "note": "Marked as sent."}}


def _juno(run, tmp_path, rev_now, seed):
    m = copy.deepcopy(_sample())
    for x in m["messages"]:
        if x["id"] == "msg-juno-1":
            x["rev"] = rev_now
    html = _write(tmp_path, "juno" + rev_now, m)
    got = run("engine", html=html, viewport=WIDE, clock=CLOCK, seed=seed, steps=[
        {"hash": "contacts", "read": "#main"}])
    assert not got["errors"], got["errors"]
    return got["after"][0]["text"]


def test_a_tap_on_an_older_version_leaves_the_new_draft_to_send(run, tmp_path):
    text = _juno(run, tmp_path, "m2", _tap("m1"))
    assert "Hi Juno, thank you for coming back" in text, text[:600]


def test_a_tap_on_this_version_still_counts(run, tmp_path):
    text = _juno(run, tmp_path, "m1", _tap("m1"))
    assert "Hi Juno, thank you for coming back" not in text, text[:600]


def _old_tap(words):
    # A tap that kept no version (rev_seen null), as an older page sent it.
    got = _tap(None)
    got["actions/act~msg-juno-1~msg.sent~old"]["value"]["text"] = words
    return got


JUNO_NOW = ("Hi Juno, thank you for coming back to me so quickly. Thursday at 12 suits me well. I would "
            "love to hear how the planning team splits its week between stores and suppliers.")


def test_a_tap_with_no_version_on_an_earlier_message_leaves_the_new_one_to_send(run, tmp_path):
    text = _juno(run, tmp_path, "m1", _old_tap("Hi Juno, just checking in on my note from last week."))
    assert "Hi Juno, thank you for coming back" in text, text[:600]


def test_a_tap_with_no_version_on_these_words_still_counts(run, tmp_path):
    text = _juno(run, tmp_path, "m1", _old_tap(JUNO_NOW))
    assert "Hi Juno, thank you for coming back" not in text, text[:600]
