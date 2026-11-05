"""A skill question on a job card leaves it once answered, and only the answer given is ticked.

The maintainer, 2026-11-05: on a job card, "Can you claim Domo and back it up in an
interview?" was answered No; the toast said "Answered: No" and the card kept the question,
with Yes and No both ticked. The question stayed until Claude had applied the answer (To do's
own copy left at once), and an answer was ticked by its action alone, which Yes and No share.
Now an answer on a card takes the question off it at once, its Undo in the toast, as To do
does, and a tick is the answer's own action and value. Every employer is the invented
sample's (tests/fixtures/app_model_sample.json).
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_the_page_journeys import _sample, browser  # noqa: E402
from test_the_page_works_in_a_browser import _write  # noqa: E402

WIDE = {"width": 1280, "height": 900}
CLOCK = "2026-10-25T09:00:00Z"
SKILL_Q = {
    "id": "q-skill-domo", "kind": "consent", "title": "Can you claim Domo and back it up in an interview?",
    "body": ("Harbourline Bank asks for it, and your profile doesn't list it. Resumes leave it off until you "
             "say. Yes adds it to your profile, for every resume. Just for this role puts it on this role's "
             "resume only, never your profile. No keeps it off them all."),
    "options": [{"label": "Yes, add it to my profile", "action": "needs.answer", "value": "yes"},
                {"label": "Just for this role", "action": "needs.answer", "value": "role"},
                {"label": "No", "action": "needs.answer", "value": "no"}],
    "about": {"company": "Harbourline Bank"}, "rev": "sq1"}
UPDATE_Q = {
    "id": "q-upgrade-calendar-feed", "kind": "upgrade_ask", "title": "Set up your calendar feed?",
    "body": "An update can add your interviews to your calendar by itself.",
    "options": [{"label": "Yes", "action": "needs.answer", "value": "yes"},
                {"label": "Not now", "action": "needs.answer", "value": "no"}],
    "about": {}, "rev": "uq1"}


@pytest.fixture(scope="module")
def run():
    yield from browser()


def _model():
    m = _sample()
    m["needs_you"] = list(m["needs_you"]) + [SKILL_Q, UPDATE_Q]
    return m


CARD = '#main [data-item="r12-1"]'


def test_a_no_on_a_job_card_takes_the_question_off_it_at_once(run, tmp_path):
    page = _write(tmp_path, "page", _model())
    got = run("engine", html=page, viewport=WIDE, clock=CLOCK, fake={"canSend": "available"}, steps=[
        {"hash": "jobs", "read": CARD},
        {"click": "No: Pricing Analyst", "within": CARD, "exact": True, "read": CARD},
    ])
    assert not got["errors"], got["errors"]
    before, after = got["after"][0]["text"], got["after"][1]["text"]
    assert "Can you claim Domo" in before and "Just for this role" in before, before
    # Answered: gone from the card at once, before Claude has caught up.
    assert "Can you claim Domo" not in after, after
    (a,) = [x for x in got["actions"] if x["item"] == "q-skill-domo"]
    assert a["action"] == "needs.answer" and a["value"] == "no", a


def test_only_the_answer_given_is_ticked(run, tmp_path):
    """Settings keeps an update's question, answered, until Claude has done it: Not now is
    ticked there, and Yes is not."""
    page = _write(tmp_path, "page", _model())
    pressed = ("[...document.querySelectorAll('#main [data-item=\"q-upgrade-calendar-feed\"] .opts button')]"
               ".map((b) => [b.textContent.trim(), b.getAttribute('aria-pressed')])")
    got = run("engine", html=page, viewport=WIDE, clock=CLOCK, fake={"canSend": "available"}, steps=[
        {"hash": "settings", "click": "Not now", "within": '#main [data-item="q-upgrade-calendar-feed"]', "exact": True,
         "eval": pressed},
    ])
    assert not got["errors"], got["errors"]
    assert got["after"][0]["eval"] == [["Yes", "false"], ["Not now", "true"]], got["after"][0]["eval"]
