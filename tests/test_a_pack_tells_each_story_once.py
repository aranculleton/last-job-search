"""The pack chooses its stories across the whole plan, and fresh ones at a later round.

Each likely question was matched to a story on its own, so two of the five answers on one
screen could be the same story, and a final round heard the story the screen had already
heard: a thin bench, to the people deciding the hire. `plan_stories` now gives each story
to the question it fits best; another question takes a second story only when it fits
nearly as well, and prefers one not yet told at this employer. A story the session mapped
or the last build kept is never moved.

Every story, employer and question here is invented.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network"),
                os.path.dirname(os.path.abspath(__file__))]

import interview_pack as P  # noqa: E402
import test_interview_pack as base  # noqa: E402

app = base.app          # the invented application, its own fixture

MODEL = "Tell me about a model you built."
DEPOTS = "Tell me about a forecasting model you built for the depots."


def _story(title, *use_for):
    return {"title": title, "theme": "", "use_for": list(use_for), "star": {},
            "source": "profile/07-interview-prep.md"}


STOCK = _story("Freed safety stock", "Tell me about a model you built",
               "A forecasting model for the depots")
ROUTES = _story("Fewer van miles", "A forecasting model for the depots")
NEAR_ONLY_IN_WORDS = _story("Depot dashboards", "A model for the depots")


def _ctx(stories, bank=(), stage="Final round", **kw):
    ctx = {"company": base.COMPANY, "stage": stage, "folder": "/nonexistent", "map": {},
           "kept_map": {}, "stories": list(stories), "bank": list(bank), "earlier": []}
    ctx.update(kw)
    return ctx


def _q(*questions):
    return [{"question": q, "why": "", "source": ""} for q in questions]


def test_one_question_at_a_time_gave_two_answers_the_same_story():
    # The behaviour this replaces, kept as the reason for the plan: matched alone, both
    # questions land on the first story.
    for q in (MODEL, DEPOTS):
        assert P.best_story(P._match_text(q), [STOCK, ROUTES])[0] is STOCK


def test_a_story_goes_to_the_question_it_fits_best_and_the_other_takes_the_next():
    plan = P.plan_stories(_q(DEPOTS, MODEL), _ctx([STOCK, ROUTES]))
    # The model question fits Freed safety stock exactly, so it keeps it, though it comes
    # second; the depot question fits Fewer van miles as well and takes that.
    assert plan[MODEL][0] is STOCK and plan[MODEL][1] == "matched by its Use for tags"
    assert plan[DEPOTS][0] is ROUTES
    assert plan[DEPOTS][1] == ('matched by its Use for tags; chosen over Freed safety stock, '
                               'which answers "%s" here' % MODEL)


def test_a_weaker_story_never_replaces_a_clearly_better_one():
    # 0.75 against 0.5: not nearly as well, so the same story answers both.
    plan = P.plan_stories(_q(MODEL, DEPOTS), _ctx([STOCK, NEAR_ONLY_IN_WORDS]))
    assert plan[MODEL][0] is STOCK and plan[DEPOTS][0] is STOCK
    assert plan[DEPOTS][1] == "matched by its Use for tags"


def test_a_story_told_here_in_an_earlier_round_gives_way_to_a_fresh_one():
    told = {"date": "2026-03-02", "company": base.COMPANY, "role": base.ROLE,
            "stage": "Phone screen", "question": "Walk me through a project",
            "story": "Freed safety stock", "landed": "yes", "note": ""}
    plan = P.plan_stories(_q(DEPOTS), _ctx([STOCK, ROUTES], bank=[told]))
    assert plan[DEPOTS][0] is ROUTES
    assert plan[DEPOTS][1].endswith("chosen over Freed safety stock, told here at the Phone screen")
    # Told at another employer, or reported rather than told, it is still fresh here.
    for row in (dict(told, company="Larkspur Retail"), dict(told, landed="", source="a contact")):
        assert P.plan_stories(_q(DEPOTS), _ctx([STOCK, ROUTES], bank=[row]))[DEPOTS][0] is STOCK
    # And a row for this very round is this round, not an earlier one.
    same = dict(told, stage="Final round")
    assert P.plan_stories(_q(DEPOTS), _ctx([STOCK, ROUTES], bank=[same]))[DEPOTS][0] is STOCK


def test_a_mapped_or_kept_story_is_never_moved_and_is_claimed_first():
    for fixed in ({"map": {MODEL: "Freed safety stock"}},
                  {"kept_map": {MODEL: "Freed safety stock"}}):
        plan = P.plan_stories(_q(DEPOTS, MODEL), _ctx([STOCK, ROUTES], **fixed))
        assert MODEL not in plan                  # not the plan's to choose
        assert plan[DEPOTS][0] is ROUTES          # and the open question moves instead
    # Mapped even where it was told before: the session's choice stands.
    told = {"company": base.COMPANY, "stage": "Phone screen", "story": "Freed safety stock",
            "question": "Walk me through a project", "landed": "yes"}
    ctx = _ctx([STOCK, ROUTES], bank=[told], map={DEPOTS: "Freed safety stock"})
    assert DEPOTS not in P.plan_stories(_q(DEPOTS), ctx)
    answered = P.answer_for(_q(DEPOTS)[0], dict(ctx, facts={}, answers=[], company=base.COMPANY,
                                                draft=None, form=[], contacts=[]))
    assert answered["short"] == "story: Freed safety stock"


def test_the_one_screen_tells_two_stories_where_it_told_one_twice(app):
    check = "How did you check the result was right?"
    both = _story("One report in place of eleven", "How do you handle conflicting numbers",
                  "How did you check the result was right")
    other = _story("Matched-control pilot", "How did you check the result was right")
    ctx = base._ctx()
    ctx["stories"] = [both, other]
    screen = base._section(P.pack_markdown(ctx, never_say=[]), "On one screen")
    plan = [ln for ln in screen if ln[:3] in ("1. ", "2. ", "3. ", "4. ", "5. ")]
    assert "1. How do you handle conflicting numbers? -> story: One report in place of eleven" in plan
    assert "5. %s -> story: Matched-control pilot" % check in plan
