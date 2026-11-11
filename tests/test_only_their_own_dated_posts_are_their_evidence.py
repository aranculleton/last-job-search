"""Only what they posted themselves, dated, is evidence about them.

The 2026-11-10 audit (NW-10): any "posted this", "reposted this" or "shared this" header was
taken as the contact's own without checking the name on it, so a colleague's hiring post was
kept as theirs. A repost's text is its author's words, a liked post was glued onto the item
before it, and an undated item counted as recent. A note could then say something about them
that somebody else wrote. Invented people and employers only.
"""
from __future__ import annotations

import datetime
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import reading  # noqa: E402

TODAY = datetime.date(2026, 11, 10)
NAME = "Wenna Thackeray"


@pytest.fixture(autouse=True)
def day(monkeypatch):
    monkeypatch.setattr(reading.person, "today", lambda: TODAY)


def test_a_post_headed_by_someone_else_is_not_theirs():
    lines = ["Dara Whitlock posted this • 1w",
             "We are hiring a pricing analyst for the Leeds freight desk."]
    assert reading._posts(lines, TODAY, NAME) == []


def test_a_liked_post_is_dropped_and_never_glued_onto_their_own():
    lines = ["Wenna Thackeray posted this • 2w",
             "Our chilled-freight forecast now runs every hour.",
             "Wenna Thackeray liked this",
             "Dara Whitlock: ten years of cold-chain pricing, a thread."]
    got = reading._posts(lines, TODAY, NAME)
    assert [(i["kind"], i["text"]) for i in got] == [
        ("post", "Our chilled-freight forecast now runs every hour.")]


def test_their_own_post_and_repost_are_read_as_before():
    lines = ["Wenna Thackeray posted this • 2w", "Our chilled-freight forecast runs hourly.",
             "Wenna Thackeray reposted this • 3w", "Dara Whitlock",
             "We are hiring a pricing analyst."]
    assert [i["kind"] for i in reading._posts(lines, TODAY, NAME)] == ["post", "repost"]


def _reading(kind, text, date="2026-11-01"):
    return {"name": NAME, "company": "Harbourline Insurance", "headline": "Pricing Lead",
            "current": "Harbourline Insurance", "sources": [{"kind": "browser"}],
            "items": [{"kind": kind, "date": date, "text": text, "url": ""}]}


GROUND = "your hourly reefer telemetry pipeline on the Pennine corridor"
WORDS = "Our hourly reefer telemetry pipeline now covers the Pennine corridor."


def test_a_repost_or_an_undated_post_never_grounds_a_note():
    assert reading.grounded(GROUND, _reading("post", WORDS))[0]
    assert not reading.grounded(GROUND, _reading("repost", WORDS))[0]
    assert not reading.grounded(GROUND, _reading("post", WORDS, date=""))[0]


def test_a_repost_or_an_undated_post_never_decides_the_verdict():
    left = "Welcome to the team, formerly at Harbourline Insurance."
    keep, why = reading.verdict(_reading("post", left), "Harbourline Insurance")
    assert not keep, "their own recent post still counts"
    for got in (_reading("repost", left), _reading("post", left, date="")):
        keep, why = reading.verdict(got, "Harbourline Insurance")
        assert keep, why


# The independent review of the NW-10 fix (2026-11-11): a reaction word anywhere in a line
# ("We found this surprising", "Everyone who supports this") was read as a reaction header,
# so three of four of one person's own posts were dropped; an all-caps header was read as
# somebody else's; and a repost still offered itself as a hook.
def test_a_reaction_is_a_header_only_as_a_whole_line_naming_them():
    lines = ["Wenna Thackeray posted this • 2w", "Our hourly forecast beat the old one.",
             "We found this surprising", "Wenna Thackeray posted this • 3w",
             "Everyone who supports this", "should try the reefer telemetry pipeline."]
    got = reading._posts(lines, TODAY, NAME)
    assert [i["kind"] for i in got] == ["post", "post"]
    assert "surprising" in got[0]["text"] and "supports this" in got[1]["text"]


def test_an_all_caps_header_is_still_theirs():
    lines = ["WENNA THACKERAY REPOSTED THIS • 1w", "Dara Whitlock",
             "We are hiring a pricing analyst.", "WENNA THACKERAY LIKES THIS",
             "Dara Whitlock: a thread on cold-chain pricing."]
    assert [i["kind"] for i in reading._posts(lines, TODAY, NAME)] == ["repost"]


def test_a_repost_is_never_a_hook():
    got = reading.hooks(_reading("repost", WORDS))
    assert not [h for h in got if h[1] == "repost"]
    assert [h for h in reading.hooks(_reading("post", WORDS)) if h[1] == "post"]
