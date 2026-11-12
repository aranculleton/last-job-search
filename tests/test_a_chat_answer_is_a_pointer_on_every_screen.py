"""A Chat answer is a pointer, not a dump, as the page draws it on a phone and a wide screen.

The feature request of 2026-11-10 (the audit's section 13, and PE-7), checked where the person
reads it: an answer that changed nothing has no button; a pasted reply's answer is a line under
thirty words ending on "Updated in Contacts", with no draft in the thread; and while Claude
answers, its question says Claude is answering under it, never "Starting in a moment" under a
follow-up, which says it is waiting its turn. The buttons of each kind and where they open are tests/
test_a_chat_answers_button_opens_the_card_in_place.py; the engine's side,
tests/test_a_chat_answer_points_to_where_its_change_is.py. Every person is the sample's,
invented.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest  # noqa: E402

import test_the_page_journeys as journeys  # noqa: E402
from test_the_page_journeys import PHONE, WIDE, _go  # noqa: E402

CLOCK = "2026-10-25T18:30:00Z"
THREAD = {"talk/cloud-1": {"to": "cloud", "conv": "1", "title": "Questions",
                           "created_at": "2026-10-25T09:00:00Z", "_v": 1}}
SAID = ("[...document.querySelectorAll('#main .talk-msg')].map((li) => ({text: (li.querySelector('.talk-text') || {}).textContent || '',"
        " go: [...li.querySelectorAll('.page-go button')].map((b) => b.textContent)}))")


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


@pytest.fixture(params=[PHONE, WIDE], ids=["phone", "wide"])
def vp(request):
    return request.param


def _msg(mid, who, text, at, **kw):
    return {"talk/cloud-1/messages/" + mid: dict({"from": who, "text": text, "at": at, "_v": 1}, **kw)}


def test_an_answer_that_changed_nothing_has_no_button_and_a_pasted_reply_is_one_line(run, tmp_path, vp):
    seed = dict(THREAD)
    seed.update(_msg("q1", "you", "When is the Thornbury panel?", "2026-10-25T18:00:00Z"))
    seed.update(_msg("a1", "cloud", "Wednesday at 2pm.", "2026-10-25T18:01:00Z"))
    seed.update(_msg("q2", "you", "Juno wrote back: thanks, happy to chat next week.", "2026-10-25T18:10:00Z"))
    seed.update(_msg("a2", "cloud", "Juno replied; your answer to her is drafted.", "2026-10-25T18:11:00Z",
                     go=[{"label": "Updated in Contacts", "to": "page:contacts/larkspur_retail_castellan"}]))
    got = _go(run, tmp_path, [{"hash": "chat", "wait": 200, "eval": SAID}], vp, seed=seed, clock=CLOCK)
    said = {m["text"].strip(): m["go"] for m in got["after"][0]["eval"] if m["text"].strip()}
    assert said.get("Wednesday at 2pm.") == [], said
    line = "Juno replied; your answer to her is drafted."
    assert said.get(line) == ["Updated in Contacts"], said
    shown = line + " " + " ".join(said[line])
    assert len(shown.split()) < 30 and shown.endswith("Updated in Contacts"), shown


def test_while_claude_answers_the_thread_says_so_never_starting_in_a_moment(run, tmp_path, vp):
    seed = dict(THREAD)
    seed.update(_msg("q1", "you", "Which jobs did the search find?", "2026-10-25T18:20:00Z",
                     work="talk~cloud-1~q1"))
    seed["work/talk~cloud-1~q1"] = {"kind": "talk", "title": "Which jobs did the search find?", "to": "cloud",
                                    "args": {"thread": "cloud-1"}, "asked_at": "2026-10-25T18:20:00Z",
                                    "status": "claimed", "claimed_by": "session_EXAMPLEhelper1",
                                    "claimed_at": "2026-10-25T18:20:10Z", "lease_until": "2026-10-25T18:50:10Z",
                                    "stage": 0, "steps": [], "_v": 2}
    # Said under the question itself, never as a line of its own (issue #234).
    look = ("({states: [...document.querySelectorAll('#main .talk-msg.from-you .talk-state')].map((e) => e.textContent.trim()),"
            " text: [...document.querySelectorAll('#main .talk-msg')].map((li) => li.textContent).join(' | ')})")
    got = _go(run, tmp_path, [{"hash": "chat", "wait": 200, "eval": look}], vp, seed=seed, clock=CLOCK)
    seen = got["after"][0]["eval"]
    assert seen["states"] == ["Claude is answering"] and "Starting in a moment" not in seen["text"], seen
    # A follow-up sent while it answers waits behind it, said so, with Claude listening.
    seed.update(_msg("q2", "you", "And which were from banks?", "2026-10-25T18:25:00Z",
                     work="talk~cloud-1~q2"))
    seed["work/talk~cloud-1~q2"] = {"kind": "talk", "title": "And which were from banks?", "to": "cloud",
                                    "args": {"thread": "cloud-1"}, "asked_at": "2026-10-25T18:25:00Z",
                                    "status": "queued", "stage": 0, "steps": [], "_v": 1}
    seed["chats/session_EXAMPLEhelper1"] = {"kind": "cloud", "seen_at": "2026-10-25T18:29:30Z", "watching": True}
    seed["meta/listener"] = {"chat": "session_EXAMPLEhelper1", "kind": "cloud", "answered_at": "2026-10-25T18:29:00Z",
                             "since": "2026-10-25T08:00:00Z"}
    got = _go(run, tmp_path, [{"hash": "chat", "wait": 200, "eval": look}], vp, seed=seed, clock=CLOCK)
    seen = got["after"][0]["eval"]
    assert seen["states"] == ["Claude is answering", "Waiting its turn"] and "Starting in a moment" not in seen["text"], seen
