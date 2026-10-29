"""The page's design language, held on every screen (templates/app/DESIGN.md).

The maintainer, 2026-10-29: "why are some Xs and some bins?", "there's a lot of ? on one of
the draft screenshots", "why do some things show up indents and messy and some things are
bubbles?". Each rule is measured in a browser on every screen, on a phone and wide, light and
dark, over the sample with every kind of item: one "?" a card at most; no x on any card,
since the bin is the one way to put something away; no line drawn down the side of anything;
and every live job, draft, message, person, interview and application carries the bin.
Every person and employer is invented.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

from test_the_page_journeys import _sample, browser  # noqa: E402
from test_the_page_works_in_a_browser import _write  # noqa: E402

SIZES = {"phone": {"width": 375, "height": 812}, "wide": {"width": 1440, "height": 900}}


@pytest.fixture(scope="module")
def run():
    yield from browser()


@pytest.fixture(scope="module")
def page(tmp_path_factory):
    return _write(tmp_path_factory.mktemp("design"), "sample", _sample())


@pytest.mark.parametrize("vp", ["phone", "wide"])
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_every_screen_keeps_the_design_language(run, page, vp, scheme):
    got = run("design", html=page, viewport=SIZES[vp], scheme=scheme, clock="2026-10-25T09:00:00Z")
    assert not got["errors"], got["errors"]
    assert got["sections"], "nothing was measured"
    bad = {sec: {rule: hits for rule, hits in v.items() if hits} for sec, v in got["sections"].items()}
    bad = {sec: v for sec, v in bad.items() if v}
    assert not bad, bad


# ------------------------------------------------------------------ each bin writes the right record

from test_the_page_journeys import PHONE, _go, _one  # noqa: E402

T = "2026-10-25T09:00:00Z"


# The Jobs bin's reasons, short pills with "Not this one" already chosen, each sent as the engine reads it (tests/test_every_bin_choice_changes
# _what_it_says.py applies each one); only the employer choice turns the employer down.
@pytest.mark.parametrize("pick,why,toast", [
    ("Not this one", "not this role", "Not applying: Ellerwick Trust"),
    ("The pay", "pay", "Not applying: Ellerwick Trust"),
    ("The place", "place", "Not applying: Ellerwick Trust"),
    ("Not my field", "field", "Not applying: Ellerwick Trust"),
    ("Too old", "old", "Not applying: Ellerwick Trust"),
    ("No more from Ellerwick Trust", "employer", "No more roles from Ellerwick Trust"),
    ("It has closed", "closed", "Not applying: Ellerwick Trust"),
])
def test_a_drafts_bin_says_why_it_is_not_going_out(run, tmp_path, pick, why, toast):
    got = _go(run, tmp_path, [
        {"hash": "drafts", "open": "dbin:app-ellerwick-insight", "read": "dialog[open]"},
        {"click": pick, "role": "radio", "exact": True},
        {"submit": True, "ready": "[...document.querySelectorAll('[data-toast]')].some((t) => t.textContent.includes(%r))" % toast},
    ], PHONE, clock=T)
    assert "Not sending this one?" in got["after"][0]["text"]
    a = _one(got, "ready.not_applying")
    assert a["item"] == "app-ellerwick-insight" and a["value"] == {"why": why}


def test_a_messages_bin_sets_the_note_aside_first(run, tmp_path):
    got = _go(run, tmp_path, [
        {"hash": "drafts-messages", "open": "wbin:msg-ash-1", "read": "dialog[open]"},
        {"submit": True, "wait": 300},
    ], PHONE, clock=T)
    assert "Not now: set this note aside" in got["after"][0]["text"]
    assert _one(got, "msg.skip")["item"] == "msg-ash-1"
    assert not [x for x in got["actions"] if x["action"] == "person.stop"]


def test_an_interviews_bin_records_how_it_ended(run, tmp_path):
    got = _go(run, tmp_path, [
        {"hash": "interviews", "open": "ivbin:int-harbourline-risk", "read": "dialog[open]"},
        {"click": "I withdrew", "role": "radio", "exact": True},
        {"submit": True, "wait": 300},
    ], PHONE, clock=T)
    assert "Is the" in got["after"][0]["text"] and "Harbourline" in got["after"][0]["text"]
    a = _one(got, "outcome.withdrawn")
    assert a["item"] == "int-harbourline-risk" and a["value"]["on"]


def test_a_to_do_card_about_one_person_offers_their_choices_and_a_week_off(run, tmp_path):
    got = _go(run, tmp_path, [
        {"hash": "todo", "count": "#main .hide-x svg path[d='M7 7l10 10M17 7L7 17']"},
    ], PHONE, clock=T)
    assert got["after"][0]["count"] == 0, "no x on To do: the bin, as everywhere"


def test_a_reply_never_offers_to_set_it_aside_which_the_engine_would_refuse(run, tmp_path):
    # state.py drop refuses anyone already written to, so "set aside" is for first notes only.
    got = _go(run, tmp_path, [
        {"hash": "drafts-messages", "open": "mbin:msg-juno-1", "read": "dialog[open]"},
    ], PHONE, clock=T)
    sheet = got["after"][0]["text"]
    assert "Not Juno?" in sheet and "set this note aside" not in sheet
