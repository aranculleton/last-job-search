"""Every person with a message ready to send says so in one word, whatever the message is.

The screen review of 2026-11-11 (row 23): on Contacts, Wren's card said "Ready to send" and
Ash's, Kit's, Rafe's and Noor's said "Not written to", though each had a note ready under it to
Copy and send. Two scales in one corner: one said what was next, the other where things
stood. The corner says what is next for the person (the UX review of 2026-11-10, U-6): a
draft ready to send is "Ready to send", whatever its kind; with none, where things stand.
Every person and employer is the sample's, invented.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest  # noqa: E402

import test_the_page_journeys as journeys  # noqa: E402
from test_the_page_journeys import PHONE, WIDE, _go, _sample  # noqa: E402

T = "2026-10-25T09:00:00Z"
CARDS = ("[...document.querySelectorAll('#main li.person')].map((c) => ({name: (c.querySelector('h3') || {}).textContent,"
         " pill: (c.querySelector('.top-end .state-word') || {}).textContent || '',"
         " ready: !!c.querySelector('[data-k^=\"sent:\"]')}))")
DETAIL = "(document.querySelector('dialog.detail[open] .d-person .state-word') || {}).textContent || ''"


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


@pytest.mark.parametrize("vp", [PHONE, WIDE], ids=["phone", "wide"])
def test_a_ready_draft_reads_ready_to_send_and_the_rest_where_they_stand(run, tmp_path, vp):
    got = _go(run, tmp_path, [{"hash": "contacts", "eval": CARDS}], vp, clock=T)
    cards = {c["name"].split(" at ")[0]: c for c in got["after"][0]["eval"]}
    # A first note, a follow-up, a reply and a thank-you: each one ready to send, said one way.
    for who in ("Ash", "Kit", "Rafe", "Noor", "Wren", "Juno", "Marisol"):
        assert cards[who]["ready"] and cards[who]["pill"] == "Ready to send", cards[who]
    # With nothing ready, the corner keeps where things stand.
    assert cards["Bea"]["pill"] == "Call booked" and cards["Tamsin"]["pill"] == "Referral", cards
    assert all(c["pill"] == "Ready to send" for c in cards.values() if c["ready"]), cards


def test_a_draft_not_ready_keeps_where_they_stand(run, tmp_path):
    # Held by Claude (its words wait on something), a draft is not ready: no "Ready to send".
    m = _sample()
    for x in m["messages"]:
        if x["id"] == "msg-ash-1":
            x["hold"] = "Waiting until their profile is read"
            x["hold_why"] = "profile"
    got = _go(run, tmp_path, [{"hash": "contacts", "eval": CARDS}], PHONE, model=m, clock=T)
    ash = [c for c in got["after"][0]["eval"] if c["name"].startswith("Ash ")][0]
    assert not ash["ready"] and ash["pill"] == "Not written to", ash


def test_their_own_page_says_the_same_as_their_card(run, tmp_path):
    got = _go(run, tmp_path, [{"hash": "contacts", "open": "pname:row:copperleaf_pay_ash", "eval": DETAIL}], WIDE, clock=T)
    assert got["after"][0]["eval"] == "Ready to send", got["after"][0]["eval"]
