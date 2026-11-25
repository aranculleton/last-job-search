"""A pack is rebuilt for the next round only: the round held retired, what was hard carried
forward, and kept short (issue 364).

A pack built round after round kept every answer of every round, led with steps already
done after outcome.md showed them complete, and only grew (one reached about 68 KB).
Questions the person struggled with in a round never fed the next, and nothing prompted the
chat to record them after a debrief.

Every person, employer and answer here is invented: the example person, and the made-up
application `tests/test_interview_pack.py` builds (a phone screen held, a technical interview
booked next).
"""
from __future__ import annotations

import io
import os
import sys
from contextlib import redirect_stdout

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network"),
                os.path.dirname(os.path.abspath(__file__))]

import interview_pack as P  # noqa: E402
from test_interview_pack import BANK, COMPANY, ROLE, _ctx, app  # noqa: E402,F401

pytestmark = pytest.mark.usefixtures("app")

SCREEN_ONLY = "Why are you leaving your current role?"
SCREEN_WORDS = ("I've taken the forecasting about as far as one network allows, and I want a "
                "bigger planning problem.")
BOTH = "Tell me about yourself."
BOTH_WORDS = ("I'm an operations analyst, and the thread through my work is forecasts that "
              "planners actually trust.")


def _write_answer(path, question, words):
    text = open(path, encoding="utf-8").read()
    head, rest = text.split("### %s\n" % question, 1)
    body, tail = rest.split("\n### ", 1) if "\n### " in rest else rest.split("\n## ", 1)
    sep = "\n### " if "\n### " in rest else "\n## "
    keep = [ln for ln in body.splitlines() if ln.startswith(P.INTENT_MARK)]
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(head + "### %s\n" % question + "\n".join(keep + [words, ""]) + sep + tail)


def test_the_next_round_retires_the_one_held_and_keeps_its_answers_apart():
    # Built for the phone screen first, its answers written.
    path = P.write_pack(_ctx(stage="Phone screen"))
    _write_answer(path, SCREEN_ONLY, SCREEN_WORDS)
    _write_answer(path, BOTH, BOTH_WORDS)
    # Then for the technical interview booked next.
    ctx = _ctx()
    assert not P._same_round(ctx["stage"], "Phone screen")
    P.write_pack(ctx)
    text = open(path, encoding="utf-8").read()
    # The screen's own answer is out of the next round's pack...
    assert SCREEN_WORDS not in text and "### %s" % SCREEN_ONLY not in text
    # ...kept apart beside it, never lost...
    kept = open(os.path.join(os.path.dirname(path), P.EARLIER_ANSWERS), encoding="utf-8").read()
    assert SCREEN_ONLY in kept and SCREEN_WORDS in kept and "Phone screen" in kept
    # ...and the pack says so, once.
    assert text.count(P.EARLIER_LINE) == 1
    # An answer the next round asks too stays where it was written.
    assert BOTH_WORDS in text
    # Built again for the same round, nothing more moves and nothing is kept twice.
    P.write_pack(_ctx())
    again = open(os.path.join(os.path.dirname(path), P.EARLIER_ANSWERS), encoding="utf-8").read()
    assert again == kept
    assert BOTH_WORDS in open(path, encoding="utf-8").read()


def test_an_answer_added_for_this_round_stays():
    path = P.write_pack(_ctx())
    text = open(path, encoding="utf-8").read()
    head, tail = text.split("## Your answers\n", 1)
    body, rest = tail.split("\n## ", 1)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(head + "## Your answers\n" + body.rstrip("\n") + "\n\n### Why that cut-off?\n"
                 "I picked it with the planners, so a site was flagged only when it mattered.\n"
                 "\n## " + rest)
    P.write_pack(_ctx())
    assert "### Why that cut-off?" in open(path, encoding="utf-8").read()
    assert not os.path.exists(os.path.join(os.path.dirname(path), P.EARLIER_ANSWERS))


def test_a_question_found_hard_last_round_comes_first():
    hard = dict(BANK[0], question="How do the forecasts reach the depots?", landed="no",
                note="lost the thread on the hand-off")
    ctx = _ctx()
    ctx["bank"] = BANK + [hard]
    qs = P.likely_questions(ctx)
    assert qs[0]["question"] == "How do the forecasts reach the depots?"
    assert "hard" in qs[0]["why"] and "hand-off" in qs[0]["why"]
    # Asked here and landed, a question is not put first as one found hard.
    ctx["bank"] = BANK + [dict(hard, landed="yes")]
    assert not any("hard" in q["why"] for q in P.likely_questions(ctx))

def test_a_pack_over_its_length_is_not_ready():
    path = P.write_pack(_ctx())
    with open(path, "a", encoding="utf-8", newline="\n") as fh:
        fh.write("\n- a note kept from an older build\n" * (P.MAX_PACK_CHARS // 30))
    found = [why for where, why in P.check(path) if where == "the document"]
    assert any("characters long" in why for why in found)


def test_booking_the_next_round_says_to_record_what_was_hard_and_build_for_it_only():
    out = io.StringIO()
    with redirect_stdout(out):
        assert P.main(["book", COMPANY, "--role", ROLE, "--stage", "Final round",
                       "--date", "2026-03-20", "--today", "2026-03-11"]) == 0
    said = out.getvalue()
    assert "--landed no" in said and "--stage \"Final round\" --write" in said
