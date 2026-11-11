"""A note written for its reader is never refused as another's with the name swapped.

The check that refuses a draft which is another person's with the name and the employer
swapped (followup_drafts.same_but_for_name) counted nine words in ten the same as a swap. A
person's own recipe for first notes keeps three of its four lines the same for everyone, so two
notes whose one tailored sentence differed ("some of the planning work at Kestrel Mutual"
against "the depot planning at Fernhill Freight") were refused (the review, 2026-11-10, R1-9).
Every person and employer is invented.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import followup_drafts  # noqa: E402

RECIPE = ("Hi %s, hope you're well. I'm an analyst, ex-Northwind and Quayside Foods, and just "
          "moved to Manchester from Leeds. I build forecasting models for stock and transport, "
          "which I imagine is similar to %s. I'd love to hear what you're working on.")
ANA = RECIPE % ("Ana", "some of the planning work at Kestrel Mutual")
WREN = RECIPE % ("Wren", "the depot planning at Fernhill Freight")


def test_two_notes_by_one_recipe_that_differ_in_their_tailored_line_are_both_written_for_their_reader():
    others = {"fernhill_freight_halloway": (WREN, "Wren Halloway", "Fernhill Freight")}
    assert followup_drafts.same_but_for_name(ANA, "kestrel_mutual_rook", name="Ana Rook",
                                             company="Kestrel Mutual", others=others) == ""


def test_the_same_note_with_only_the_name_and_the_employer_swapped_is_still_refused():
    same = RECIPE % ("Wren", "the depot planning at Fernhill Freight")
    copy = same.replace("Wren", "Ana").replace("Fernhill Freight", "Kestrel Mutual")
    others = {"fernhill_freight_halloway": (same, "Wren Halloway", "Fernhill Freight")}
    said = followup_drafts.same_but_for_name(copy, "kestrel_mutual_rook", name="Ana Rook",
                                             company="Kestrel Mutual", others=others)
    assert said.startswith("the same words as your draft to Wren"), said
    # A word or two besides ("a" for "an", a day) is still the same message.
    tweak = copy.replace("hope you're well", "hope you are well")
    assert followup_drafts.same_but_for_name(tweak, "kestrel_mutual_rook", name="Ana Rook",
                                             company="Kestrel Mutual", others=others)
