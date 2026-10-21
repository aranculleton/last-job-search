"""The pack says at its top what it is for: before and after the interview, never during.

Some interview tools listen in on a live call, feed answers while it runs and record the
other side without asking. The app said nothing either way. Every pack now says, in one
plain line, that Claude never helps during a live interview and never records or
transcribes one; /interview's rules say the same.

The application is invented.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network"),
                os.path.dirname(os.path.abspath(__file__))]

import interview_pack as P  # noqa: E402
import test_interview_pack as base  # noqa: E402

app = base.app


def test_the_pack_says_it_is_for_before_and_after_never_during(app):
    head = base._pack().split("\n## ", 1)[0].splitlines()
    assert ("This is for before and after the interview. Claude never helps during a live "
            "interview, and never records or transcribes one.") in head
    assert P.LIVE_LINE in head
