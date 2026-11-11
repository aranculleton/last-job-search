"""Two referral asks that differ only in the name, the employer, the role and the link are one
message, and the second is refused.

The swap check counted the role's title and the posting's link as words written for the reader,
so two asks from one template, the same but for those, passed (the review of 2026-11-11 on R1-9,
reopening NW-2). Names, employers and role titles (capitalised runs) and links are taken out
before the words are compared; a line written for the reader still makes a draft its own, and
`compose.referral_ask(line=...)` takes that line. Every person and employer is invented.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import compose  # noqa: E402
import followup_drafts  # noqa: E402

T = ("Hi %s, thanks again for offering to refer me when something came up. %s has posted a %s "
     "role, which looks like a strong fit for my forecasting and pricing work. Would you be happy "
     "to put my name forward? Here is the link: %s")


def _thread(cid):
    return [{"contact_id": cid, "date": "2026-10-01", "direction": "out", "channel": "message",
             "scenario": "first_message", "summary": "", "full_text": "Hi, I'd love to hear what "
             "you're working on."},
            {"contact_id": cid, "date": "2026-10-03", "direction": "in", "channel": "message",
             "scenario": "reply", "summary": "", "full_text": "Happy to refer you when something "
             "comes up."}]


def test_a_template_with_the_role_and_link_swapped_is_refused():
    ana = T % ("Ana", "Kestrel Mutual", "Senior Pricing Analyst", "https://jobs.example/kestrel/123")
    wren = T % ("Wren", "Fernhill Freight", "Data Scientist, Forecasting",
                "https://jobs.example/fernhill/987")
    said = followup_drafts.same_but_for_name(
        ana, "kestrel_mutual_rook", name="Ana Rook", company="Kestrel Mutual",
        others={"fernhill_freight_halloway": (wren, "Wren Halloway", "Fernhill Freight")})
    assert said.startswith("the same words as your draft to Wren"), said


def test_two_composed_asks_are_one_message_unless_a_line_is_written_for_each():
    ctx = "thanks again for offering to refer me when something came up"
    ana = compose.referral_ask("Ana Rook", ctx, "Senior Pricing Analyst role at Kestrel Mutual",
                               "https://jobs.example/kestrel/123", thread=_thread("kestrel_rook"))
    wren = compose.referral_ask("Wren Halloway", ctx, "Data Scientist role at Fernhill Freight",
                                "https://jobs.example/fernhill/987",
                                thread=_thread("fernhill_halloway"))
    others = {"fernhill_halloway": (wren, "Wren Halloway", "Fernhill Freight")}
    assert followup_drafts.same_but_for_name(ana, "kestrel_rook", name="Ana Rook",
                                             company="Kestrel Mutual", others=others)
    own = compose.referral_ask(
        "Ana Rook", ctx, "Senior Pricing Analyst role at Kestrel Mutual",
        "https://jobs.example/kestrel/123", thread=_thread("kestrel_rook"),
        line="It sits in the claims pricing team you told me about, the one moving to weekly "
             "forecasts")
    assert "the one moving to weekly forecasts" in own
    assert followup_drafts.same_but_for_name(own, "kestrel_rook", name="Ana Rook",
                                             company="Kestrel Mutual", others=others) == ""
