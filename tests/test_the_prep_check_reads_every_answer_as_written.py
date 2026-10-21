"""The answer checks read every answer as the person wrote it, and pass nothing unfinished.

From a real repo on 2026-10-21: after the update an answer written as a quote was read as a
note, so a prep that had passed failed six answers "not in the first person" with no word
of what had changed; an answer holding "[FILL IN: ...]" was reported fit to say aloud; and
only the Your answers section was read, so a question answered under another heading was
neither checked nor listed as a draft. Every answer here is invented.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]
os.environ.setdefault("LJS_PROFILE", os.path.join(ROOT, "profile.example"))

import interview_pack as P  # noqa: E402
import prep  # noqa: E402

SAID = "I built the forecast that freed the safety stock, and I'd start there."


def test_an_answer_written_as_a_quote_is_still_the_answer():
    assert prep.spoken_lines(["> " + SAID]) == [SAID]
    assert prep.unsayable(prep.spoken_lines(["> " + SAID])) == []
    # A quote beside an answer said outside it stays a note, as 3.9.0 made it.
    assert prep.spoken_lines([SAID, "> remember the 22% figure"]) == [SAID]
    # The pack's own line is never the answer.
    assert prep.spoken_lines(["> Checking: rigour. They want to hear: the test."]) == []


def test_a_placeholder_is_never_fit_to_say():
    found = prep.unsayable(["I led a team of [FILL IN: how many] analysts on the forecast."])
    assert found and found[0].startswith("a placeholder still to fill: [FILL IN")
    assert prep.unsayable(["I cut the error to <the number> percent."])
    assert prep.unsayable([SAID]) == []


def test_a_question_answered_under_another_heading_is_checked_and_its_draft_listed(tmp_path):
    doc = tmp_path / "interview_prep.md"
    doc.write_text("\n".join([
        "# Interview prep", "", "## Your answers", "", "### Tell me about yourself.", SAID, "",
        "## Notes", "", "### Why this team?",
        "Planning analytics owned end to end across the network, with the forecast feeding "
        "every weekly stock decision the team makes.", "",
        "### Tell me about a time you led something.", prep.DRAFT_MARK, SAID, "",
        "### What you found out", "- The canal walk is worth it.", "",
    ]), encoding="utf-8")
    found = P.check(str(doc))
    assert ("Why this team?", "not in the first person: say it as \"I ...\"") in found
    assert (P.DRAFT, "Tell me about a time you led something.") in found
    assert not any(q == "What you found out" for q, _ in found)
    assert not any(q == "Tell me about yourself." for q, _ in found)
