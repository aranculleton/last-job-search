"""To do counts cards, says how far today has gone, and what was done (the UX review, 2026-11-05).

The review: a checklist of 25 people counted as 25 made a calm screen read as an emergency;
the badge and the summary count cards, a checklist card says its own "2 of 8 done", the
summary says "3 of 9 done today" and, once nothing is left, that it is all done. "Recent
changes", a log of every tap, gave way to "Done today (N): Show", each finished thing in grey
with its Undo or Change back where there is one, an answer said in the words chosen. Every
person and employer is invented (tests/fixtures/app_model_sample.json).
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
from test_the_page_journeys import WIDE, _go, _sample  # noqa: E402

T = "2026-10-25T09:00:00.000Z"


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


COUNT = r"""(() => {
  const head = document.querySelector('#main h2, #main h1');
  const sum = head && head.parentElement ? head.parentElement.textContent : document.querySelector('#main').textContent;
  const today = [...document.querySelectorAll('#main section.band')].filter((b) => /Due or late|Needs your answer/.test(b.querySelector('h3').textContent));
  const cards = today.reduce((n, b) => n + [...b.querySelectorAll('[data-card]')].filter((c) => !c.parentElement.closest('[data-card]')).length, 0);
  const badge = (document.querySelector('[data-k="side:todo"] .badge') || {}).textContent || '';
  const groups = [...document.querySelectorAll('#main .group-card')].map((g) => (g.querySelector('[data-k^="grp-done:"]') || {}).textContent || null);
  return {sum, cards, badge: parseInt(badge, 10) || 0, groups};
})()"""


def _today(sum_text):
    m = re.search(r"(\d+) things? today", sum_text)
    return int(m.group(1)) if m else None


def test_the_badge_and_the_summary_count_cards_and_a_checklist_says_its_own_done(run, tmp_path):
    got = _go(run, tmp_path, [{"hash": "todo", "eval": COUNT}], WIDE, clock=T)
    r = got["after"][0]["eval"]
    # One count, of cards: a card a thing, the checklist of drafted messages one of them. A
    # wave of first notes in the same band asks nothing today and counts nothing.
    assert _today(r["sum"]) == r["badge"] and r["cards"] - 1 <= r["badge"] <= r["cards"], ("one count, of cards", r)
    assert r["groups"] and all(g and re.fullmatch(r"\d+ of \d+ done", g) for g in r["groups"]), r


def test_a_thing_done_is_counted_as_done_today_and_listed_with_its_way_back(run, tmp_path):
    m = copy.deepcopy(_sample())
    got = _go(run, tmp_path, [
        {"hash": "todo", "eval": COUNT},
        {"click": "Yes, I have", "eval": COUNT},
        {"click": "Show Done today (1)", "exact": True,
         "eval": "(document.querySelector('#main .todo-done-list') || {}).textContent || ''"},
    ], WIDE, model=m, clock=T)
    before, after, listed = got["after"][0]["eval"], got["after"][1]["eval"], got["after"][2]["eval"]
    n0 = _today(before["sum"])
    # One of four quick answers given: its card stays for the other three, so the cards left
    # today stay as they were and the answer is one thing done.
    assert n0 and re.search(r"%d things? today · 1 of %d done" % (n0, n0 + 1), after["sum"]), (before["sum"], after["sum"])
    assert "Recent changes" not in got["after"][2]["text"], "one line of what was done, never a log of every tap"
    assert listed.startswith("Answered") and ": Yes" in listed and "Undo" in listed, listed
    assert "Only a chat can take this back" not in listed


def test_a_dated_row_is_put_off_in_the_engine_tomorrow_or_next_week(run, tmp_path):
    """The review (A7): putting off a row hid it on this device alone for a week; it is the
    engine's due.snooze, Tomorrow and Next week first, on every device."""
    choices = "[...document.querySelectorAll('dialog[open] .choice-btn')].map((b) => b.textContent)"
    got = _go(run, tmp_path, [
        {"hash": "todo", "click": "Later: Thank-you note after your Harbourline Bank first interview", "exact": True, "eval": choices},
        {"click": "Next week", "exact": True, "within": "dialog"},
    ], WIDE, clock=T)
    assert got["after"][0]["eval"][:2] == ["Tomorrow", "Next week"], got["after"][0]["eval"]
    a = [x for x in got["actions"] if x["action"] == "due.snooze"]
    assert a and a[-1]["value"] == {"until": "2026-11-01"}, got["actions"]
    assert "Thank-you note after your Harbourline Bank first interview" not in got["after"][1]["text"], "it leaves To do at once"


def test_with_everything_done_to_do_says_so_and_what_is_next(run, tmp_path):
    m = copy.deepcopy(_sample())
    m["due"] = [d for d in m["due"] if d["id"] == "due-tamsin-resume"]
    m["needs_you"], m["interviews"], m["upcoming"] = [], [], []
    for x in m["jobs"]["rows"] + m["ready"] + m["messages"]:
        x["alerts"] = []
    got = _go(run, tmp_path, [{"hash": "todo", "click": "Done: Send your CV to Tamsin", "exact": True, "eval": COUNT}], WIDE, model=m, clock=T)
    assert "All done for today: 1 thing done." in got["after"][0]["eval"]["sum"], got["after"][0]["eval"]
