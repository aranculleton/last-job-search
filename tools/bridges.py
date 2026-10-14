#!/usr/bin/env python3
"""What the candidate actually has that sits next to what a posting asked for.

A posting is a wish list. It names ten tools and the team uses six, and the one
missing item is almost never what decides the hire. The screen was treating them
as bars: a posting docked ten points for the word "LLM" whether it said "build
and deploy LLM applications", "familiarity with LLMs is a plus", or "our
platform uses LLMs". Roles the candidate should obviously have gone for were
scoring below the floor on a word.

This module is the answer to that, and it is the honest one. For anything a
posting asks for, it says which of three things is true:

  HELD      the candidate has it, and the screen should stop treating it as a risk
  BRIDGE    they have something close enough to do the job and to say so out loud
  GAP       they do not have it and nothing here pretends otherwise

A BRIDGE is not a euphemism. "I use Metabase daily and used Superset at my last
employer; they are the same job with different menus" is true, it is what a
hiring manager wants to hear, and it survives the follow-up question. That last
part is why this module exists instead of simply widening the skills inventory:
a claim that does not survive the follow-up question costs more than the
application was worth. A developer who lists Rust gets a Rust question in the
screen.

So the rule the whole file follows: **frame generously, never claim falsely.**
Apply for the role, lead with the adjacent thing, name the gap plainly if asked,
and let the rest of the resume carry the argument.

    from bridges import assess
    assess("Strong Tableau background required")
    # -> [Assessment(asked='Tableau', verdict='bridge', ...)], for a profile whose
    #    BRIDGES say Tableau is bridged from the tool they use now
"""

from __future__ import annotations

import os
import re
import sys
from collections import namedtuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import person  # noqa: E402

# verdicts, strongest first
HELD = "held"
BRIDGE = "bridge"
GAP = "gap"

Assessment = namedtuple("Assessment", "asked verdict have line note")

# ---------------------------------------------------------------------------
# The map is the profile's (skills.py BRIDGES): one entry per capability a
# posting might ask for, with `asked`, the `pattern` a posting spells it with,
# the `verdict`, and for a BRIDGE its `strength`.
#
# `have` is what the candidate genuinely holds that does the same work. `line`
# is how to say it: one sentence, true, and usable in a cover letter, an
# interview answer or a recruiter reply without adjustment. `strength` decides
# how much the screen should still worry: "near" costs almost nothing, "far" is
# a real gap that a good application can still survive.
# ---------------------------------------------------------------------------
MAP = person.module("skills").BRIDGES

_COMPILED = [(re.compile(e["pattern"], re.I), e) for e in MAP]


def assess(text):
    """Every mapped capability the text mentions, with the honest verdict."""
    out, seen = [], set()
    for rx, e in _COMPILED:
        if e["asked"] in seen or not rx.search(text or ""):
            continue
        seen.add(e["asked"])
        out.append(Assessment(e["asked"], e["verdict"], tuple(e.get("have") or ()),
                              e.get("line", ""), e.get("note", "")))
    order = {HELD: 0, BRIDGE: 1, GAP: 2}
    return sorted(out, key=lambda a: order[a.verdict])


def strength_of(asked):
    for e in MAP:
        if e["asked"] == asked:
            return e.get("strength", "near")
    return "near"


def bridge_for(text):
    """The single best line to lead with, or "" if there is nothing honest."""
    for a in assess(text):
        if a.line:
            return a.line
    return ""


def gaps(text):
    """Only the ones nothing covers. These are what to concede, if anything."""
    return [a for a in assess(text) if a.verdict == GAP]


if __name__ == "__main__":
    import sys
    body = " ".join(sys.argv[1:]) or "Power BI or Tableau, SAP a plus, CIPS preferred."
    for a in assess(body):
        print("%-24s %-7s %s" % (a.asked, a.verdict, ", ".join(a.have)[:60]))
        if a.line:
            print("    say: %s" % a.line)
        if a.note:
            print("    note: %s" % a.note)
