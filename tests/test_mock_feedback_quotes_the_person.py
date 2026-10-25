"""Mock-interview feedback quotes the person's own words, checked before it is shown.

Feedback on a practice answer was free text in the chat: "you were vague" could not be
checked by anyone, and a quote the model remembered wrongly put words in the person's
mouth. `interview_pack.py feedback` now refuses a point whose quote is not a run of what
they said, a band other than Strong, Solid or Gap, and a note that gives a score or a
verdict on the hire. The pack says at its top that Claude never helps during a live
interview and never records one.

The answer and the feedback are invented.
"""
from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import interview_pack as P  # noqa: E402
ANSWER = ("So at my last place we had eleven spreadsheets that never agreed. I sat down with "
          "the depot managers, I rebuilt the feed as one dataset, and honestly it was kind of "
          "a slog, but the daily reconciliation just stopped.")
GOOD = [("I rebuilt the feed as one dataset", "keep it: it says what you did, in one breath"),
        ("honestly it was kind of a slog", "cut it; go straight to the result")]


def test_a_quote_is_their_words_whatever_the_case_spacing_or_quote_marks():
    assert P.quote_in("I REBUILT  the feed", ANSWER)
    assert P.quote_in("“the daily reconciliation just stopped.”", ANSWER)
    assert P.quote_in("it’s", "Well, it's fine.")


def test_words_they_did_not_say_are_not_their_words():
    assert not P.quote_in("I rebuilt the whole pipeline", ANSWER)     # a paraphrase
    assert not P.quote_in("rebuilt the fee", ANSWER)                   # half a word
    assert not P.quote_in("", ANSWER)


def test_sound_feedback_passes_and_is_shown_under_their_words():
    assert P.feedback_problems(ANSWER, "solid", GOOD) == []
    assert P.feedback_lines("How do you handle conflicting numbers?", "solid", GOOD) == [
        "**Solid.** How do you handle conflicting numbers?",
        '- You said "I rebuilt the feed as one dataset": keep it: it says what you did, in one breath',
        '- You said "honestly it was kind of a slog": cut it; go straight to the result']


def test_a_quote_they_never_said_is_refused():
    [why] = P.feedback_problems(ANSWER, "Gap", [("I led the depot managers", "say how")])
    assert why == '"I led the depot managers" is not what they said: quote their answer word for word'


def test_two_pieces_stitched_together_are_not_one_quote():
    [why] = P.feedback_problems(ANSWER, "Gap", [("I sat down ... it stopped", "say how")])
    assert "joins two pieces" in why


def test_a_quote_too_short_to_point_at_anything_is_refused():
    [why] = P.feedback_problems(ANSWER, "Gap", [("I rebuilt", "say how")])
    assert "too short" in why


def test_a_score_or_a_hiring_verdict_is_never_the_feedback():
    assert P.feedback_problems(ANSWER, "8/10", GOOD) == [
        "the band is '8/10': it is one of Strong, Solid, Gap, never a score"]
    for note in ("that answer is a 7 out of 10", "scored 82 for structure",
                 "you'd get the job with that", "they would pass you on this",
                 "a strong hire answer"):
        found = P.feedback_problems(ANSWER, "Strong", [(GOOD[0][0], note)])
        assert len(found) == 1 and "never a score or whether they would be hired" in found[0], note
    # Coaching that only names numbers in passing is not a score.
    assert P.feedback_problems(ANSWER, "Strong", [(GOOD[0][0], "lead with the 22% to 14%")]) == []


def test_no_point_at_all_is_not_feedback():
    assert P.feedback_problems(ANSWER, "Solid", []) == [
        "no point of feedback: each one quotes their words, then says what to keep or change"]


def _run(*args):
    return subprocess.run([sys.executable, os.path.join(ROOT, "tools", "interview_pack.py"),
                           "feedback", *args], capture_output=True, text=True, encoding="utf-8", errors="replace")


def test_the_command_shows_checked_feedback_and_nothing_it_refused(tmp_path):
    said = tmp_path / "answer.txt"
    said.write_text(ANSWER, encoding="utf-8")
    ok = _run("--question", "Conflicting numbers?", "--answer-file", str(said), "--band", "Solid",
              "--point", *GOOD[0])
    assert ok.returncode == 0
    assert ok.stdout.splitlines() == ["**Solid.** Conflicting numbers?",
                                      '- You said "I rebuilt the feed as one dataset": %s' % GOOD[0][1]]
    bad = _run("--question", "Conflicting numbers?", "--answer", ANSWER, "--band", "Strong",
               "--point", "I owned the whole migration", "great")
    assert bad.returncode == 1 and bad.stdout == ""
    assert '"I owned the whole migration" is not what they said' in bad.stderr

