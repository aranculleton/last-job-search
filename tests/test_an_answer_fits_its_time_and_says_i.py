"""An answer is checked for the time it has, and for "I" where they asked what you did.

`check` passed any answer in the spoken register, however long: a three-hundred-word answer
to a screen question reads well and is cut off when said, at about 150 words a minute, with
60 to 90 seconds to say it. And "we" counted as first person, so an answer that said "we"
throughout passed where the question asked what the person did, which is exactly what "we"
hides. Both are now findings, in the interview pack's check and the call prep's.

The answers are invented.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import interview_pack as P  # noqa: E402
import prep  # noqa: E402
import voice_check as V  # noqa: E402

LONG = " ".join(["I rebuilt the depot feed so the numbers matched every morning."] * 28)  # 308
SHORT = " ".join(["I rebuilt the depot feed so the numbers matched every morning."] * 18)  # 198
WE = ("We had eleven spreadsheets that never agreed. We sat down with the depots and we rebuilt "
      "the feed as one dataset. Our reconciliation stopped within a month, and we kept it that way.")
LED = "Tell me about a time you led something."


def test_an_answer_far_over_its_time_is_flagged_with_how_long_it_runs():
    [why] = V.answer_findings(LONG, seconds=V.SCREEN_SECONDS)
    assert why == ("about 120 seconds said aloud (308 words at about 150 a minute), where an "
                   "answer here has about 90: cut it to about 225 words")
    # A story in a later round has two minutes, and the same answer fits it.
    assert V.answer_findings(LONG, seconds=V.ANSWER_SECONDS) == []
    # A little over is not far over.
    assert V.answer_findings(SHORT, seconds=V.SCREEN_SECONDS) == []
    assert V.answer_findings(LONG) == []                       # no time given, no time check


def test_we_where_they_asked_what_you_did_is_flagged():
    [why] = V.answer_findings(WE, LED)
    assert why.startswith('says "we" 5 time(s) and "I" 0 where they asked what you did')
    for q in ("Walk me through a project in sixty seconds.", "What was your role in it?",
              "Give me an example of a hard stakeholder.", "How did you check it was right?"):
        assert V.asks_what_you_did(q), q
        assert V.answer_findings(WE, q), q


def test_we_is_still_first_person_where_they_did_not_ask_what_you_did():
    assert not V.asks_what_you_did("Why do you want to work here?")
    assert V.answer_findings(WE, "Why do you want to work here?") == []
    # The register rule is unchanged: "we" still reads as said, never as a resume line.
    assert V.spoken_findings(WE) == []
    # And an answer that says what they did, naming the team once, passes.
    mine = ("We had eleven spreadsheets that never agreed, so I sat down with the depots and I "
            "rebuilt the feed as one dataset. The reconciliation I used to do every morning stopped.")
    assert V.answer_findings(mine, LED) == []


def test_the_call_prep_and_the_pack_hold_answers_to_both():
    assert prep.unsayable([WE], LED) and prep.unsayable([LONG], "", V.SCREEN_SECONDS)
    assert prep.unsayable([WE]) == [] and prep.unsayable([LONG]) == []   # unchanged without them


def _doc(tmp_path, stage, answers):
    body = ["# Interview prep: Demand Planner at Fernhill Freight", "",
            "Last updated 2026-03-11. Next: %s, 2026-03-14. One document for this whole process: "
            "change an answer here, and it is sent to you again." % stage, "", "## Your answers", ""]
    for q, a in answers:
        body += ["### %s" % q, a, ""]
    body += ["## To rework", "", "- Nothing yet.", ""]
    path = tmp_path / P.LIVING
    path.write_text("\n".join(body), encoding="utf-8")
    return str(path)


def test_the_living_documents_check_reads_the_stage_for_the_time(tmp_path):
    answers = [("Walk me through a project in sixty seconds.", LONG), (LED, WE)]
    found = P.check(_doc(tmp_path, "Phone screen", answers))
    assert ("Walk me through a project in sixty seconds.",
            "about 120 seconds said aloud (308 words at about 150 a minute), where an answer here "
            "has about 90: cut it to about 225 words") in found
    assert any(q == LED and why.startswith('says "we" 5 time(s)') for q, why in found)
    later = P.check(_doc(tmp_path, "Technical interview", answers))
    assert not any("seconds said aloud" in why for _q, why in later)
    assert any(q == LED for q, _why in later)
