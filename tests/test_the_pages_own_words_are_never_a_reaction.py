"""A tap on the page reaches the chat carrying the app's own words; they are never read as
the person reacting. Only what the person typed is."""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import learned  # noqa: E402


def test_a_page_ring_with_the_pages_notice_is_not_a_reaction():
    ring = "[app] [work:draft~r1] Your draft reads like a first note. Perfect for Morgan."
    assert learned.reaction(ring) == ""
    assert learned.approval(ring) == ""
    wrapped = ("Artifact comment sent to Claude on the page: \"This reads like a template, "
               "too long\"\n[app] [work:draft~r1]")
    assert learned.reaction(wrapped) == ""


def test_the_doorbell_line_is_dropped_but_the_persons_words_stay():
    text = "this is too formal, make it warmer\n[app] [work:talk~1] the notice reads like a form"
    assert learned.reaction(text) == "too formal"
    assert learned.reaction("[app] [work:talk~1] the notice reads like a form") == ""
    assert learned.reaction("that note is too formal") == "too formal"
