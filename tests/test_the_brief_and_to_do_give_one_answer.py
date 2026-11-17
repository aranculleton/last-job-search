"""The Brief and To do answer "what do I do next?" the same way, in the same order, with one count.

The redesign's reviews (2026-11-16): the Brief's Today said one thing first ("Follow up with
Fernhill Freight"), its Next three another ("Reply to Juno"), and To do a third (the thank-you
two days late), and their counts disagreed: To do's badge 4, Today one, Next three, and "4
things today" over seven messages. So the Brief takes To do's own list (todoQueue): Today is To
do's first card with that card's own button, Next the three after it, in the card's own words,
and the one count is To do's, said over Today as "1 of 4" with Next's numbers going on from it.
Every person and employer is invented (the sample's own).
"""
from __future__ import annotations

import copy
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import test_the_page_journeys as journeys  # noqa: E402
from test_the_page_journeys import PHONE, WIDE, _go, _sample  # noqa: E402

T = "2026-10-25T09:00:00.000Z"


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


# To do's cards in the order it draws them, the folds of today's and of what is not due yet
# included, and never the tour, the help band, what is hidden, put off or done today. For each:
# its title, whether it is one of today's (under "Needs your answer" or "Due or late", or in the
# fold of today's rest), and its filled button.
TODO = r"""(() => {
  const skip = '.help-band, .todo-hidden-list, .todo-putoff-list, .todo-done-list, .tour-card';
  const cards = [...document.querySelectorAll('#main .card.todo[data-card]')]
    .filter((c) => !c.closest(skip) && !(c.parentElement && c.parentElement.closest('.card.todo')));
  const summary = (document.querySelector('#main .sec-head .sum, #main .summary') || {}).textContent || '';
  const b = document.querySelector('#tabs .badge, #side .badge');
  return {cards: cards.map((c) => ({title: (c.querySelector('.card-title') || {}).textContent.trim(),
      primary: ((c.querySelector(':scope > .card-actions > .btn.primary') || {}).textContent || '').trim()})),
    summary, badge: b ? Number(b.firstChild.textContent) : 0};
})()"""
BRIEF = r"""(() => {
  const t = document.querySelector('#main .bp-today');
  const what = t && t.querySelector('.bp-iv-what');
  const btn = t && t.querySelector('.bp-iv .btn.primary');
  return {today: what ? what.textContent.trim() : null, count: ((t && t.querySelector('.bp-count')) || {}).textContent || null,
    button: btn ? btn.textContent.trim() : null,
    next: [...document.querySelectorAll('#main .bp-next .bp-steps > li')].map((li) => ({text: li.textContent.trim(), n: li.getAttribute('data-n')})),
    upcoming: [...document.querySelectorAll('#main .bp-upcoming .bp-up > li')].map((li) => li.textContent)};
})()"""


def _read(run, tmp_path, vp, model=None, clock=T):
    got = _go(run, tmp_path, [{"hash": "todo", "eval": TODO}, {"hash": "brief", "eval": BRIEF}], vp, model=model, clock=clock)
    return got["after"][0]["eval"], got["after"][1]["eval"]


def _today_count(todo):
    m = re.search(r"(\d+) things? today", todo["summary"])
    return int(m.group(1)) if m else 0


def _agree(todo, brief):
    cards = todo["cards"]
    assert cards, todo
    # Today is To do's first card, with its button.
    assert brief["today"] == cards[0]["title"], (brief["today"], [c["title"] for c in cards[:4]])
    if cards[0]["primary"]:
        assert brief["button"] == cards[0]["primary"], (brief["button"], cards[0])
    # Next is the three after it, in To do's order, each led by its card's own words.
    want = [c["title"] for c in cards[1:4]]
    got = [s["text"] for s in brief["next"]]
    assert len(got) == len(want), (got, want)
    assert all(g.startswith(w) for g, w in zip(got, want)), (got, want)
    # One count: the badge, To do's summary, and "1 of N" over Today, Next's numbers going on.
    n = todo["badge"]
    assert _today_count(todo) == n, (todo["summary"], n)
    nums = [int(s["n"]) for s in brief["next"] if s["n"]]
    if brief["count"]:
        assert brief["count"] == "1 of %d" % n, (brief["count"], n)
        assert nums == list(range(2, 2 + len(nums))), brief["next"]
    else:
        assert nums == list(range(1, 1 + len(nums))), brief["next"]
    assert (nums[-1] if nums else (1 if brief["count"] else 0)) <= n, (nums, n)


@pytest.mark.parametrize("vp", [PHONE, WIDE], ids=["phone", "wide"])
def test_the_brief_is_to_dos_first_four_in_its_order_with_its_count(run, tmp_path, vp):
    todo, brief = _read(run, tmp_path, vp)
    _agree(todo, brief)
    # The sample's day: the thank-you two days late leads both, "Draft the thank-you" its button,
    # and the four of today are four everywhere.
    assert brief["today"].startswith("Thank-you note") and brief["button"] == "Draft the thank-you", brief
    assert todo["badge"] == 4 and brief["count"] == "1 of 4", (todo, brief)
    # The messages to send are one step, said by who they are for, as To do's one card is.
    assert brief["next"][0]["text"].startswith("Messages to send (7)") and "Juno" in brief["next"][0]["text"], brief["next"]


def test_an_interview_two_days_off_with_no_prep_leads_both(run, tmp_path):
    # The second interview on Wednesday, with no prep yet: To do's first card, and so Today's,
    # with Prepare me; the online test due today is Coming up's, beside it.
    todo, brief = _read(run, tmp_path, WIDE, clock="2026-11-02T08:30:00Z")
    _agree(todo, brief)
    assert "Second interview" in brief["today"] and brief["button"] == "Prepare me", brief
    assert any("Online test" in u for u in brief["upcoming"]), brief["upcoming"]


def test_a_quiet_to_do_fills_next_with_what_is_not_due_yet_by_its_day(run, tmp_path):
    m = copy.deepcopy(_sample())
    for k in ("needs_you", "ready", "messages", "refusal_asks"):
        m[k] = []
    m["to_send"] = {"n": 0, "ids": []}
    m["due"] = [d for d in m["due"] if d["id"] == "due-harbourline-thanks"]
    todo, brief = _read(run, tmp_path, WIDE, model=m)
    _agree(todo, brief)
    # One thing today, so no "1 of 1"; what follows is To do's "Not due yet", a dot and its day.
    assert todo["badge"] == 1 and brief["count"] is None, (todo, brief)
    assert brief["next"] and all(s["n"] is None for s in brief["next"]), brief["next"]


def test_a_call_today_stays_in_coming_up_and_today_is_still_to_dos_first(run, tmp_path):
    m = copy.deepcopy(_sample())
    call = copy.deepcopy(next(u for u in m["upcoming"] if u["kind"] == "call"))
    call.update(id="up-call-today", day="2026-10-25", time="15:00", start="2026-10-25T15:00:00Z", end="2026-10-25T15:30:00Z")
    m["upcoming"].insert(0, call)
    todo, brief = _read(run, tmp_path, WIDE, model=m)
    _agree(todo, brief)
    assert any(call["title"] in u for u in brief["upcoming"]), brief["upcoming"]


def test_a_step_opens_its_own_card_in_to_do(run, tmp_path):
    # Each step opens To do at the card it names, where its button is.
    got = _go(run, tmp_path, [{"hash": "brief", "eval": "(document.querySelectorAll('#main .bp-next .bp-steps a')[1].click(), 1)",
                               "until": "location.hash.startsWith('#todo') && !!document.activeElement && !!document.activeElement.closest('[data-card]')"},
                              {"eval": "[location.hash, (document.activeElement && document.activeElement.closest('[data-card]') || {}).textContent || '']"}], WIDE, clock=T)
    where, focused = got["after"][1]["eval"]
    assert where.startswith("#todo/") and "Tamsin" in focused, (where, focused)
