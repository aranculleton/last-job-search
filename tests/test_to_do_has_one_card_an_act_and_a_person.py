"""To do has one card an act and one card a person, asks the small questions one at a time,
never offers a fix, and offers what the item's own screen offers (the UX review, 2026-11-05).

The review, read as a tired person on a phone with dozens of things owed:
- Someone was on three cards at once: their follow-up, what they asked for and a job's "do not
  apply cold". One card for them, the referral its grey box; a referral with no row about
  them, and a closed posting, are notes on their own cards, never To do cards.
- Four small yes-or-no questions were four cards. One card, "4 quick answers", among the
  first five, one question at a time with "1 of 4", each answered with its own control, the
  next there at once.
- A checklist row had one button: a follow-up done some other way could only be put off. Each
  row has its next step and Done; its bin keeps They replied and the rest.
- "Make it again" and "Shorten it" were buttons on To do. Claude fixes them by itself; the
  draft's own card says so.
- To do's interview card offered less than Coming up's for the same interview.
- A header line under the summary for a link, and a line for Claude's work, made three lines
  where one would do.

Every person and employer is invented (tests/fixtures/app_model_sample.json).
"""
from __future__ import annotations

import copy
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import test_the_page_journeys as journeys  # noqa: E402
from test_the_page_journeys import PHONE, WIDE, _go, _sample  # noqa: E402

T = "2026-10-25T09:00:00Z"
FIRST_FIVE = ("[...document.querySelectorAll('#main section.band [data-card]')].filter((c) => !c.closest('details') && !c.parentElement.closest('[data-card]'))"
              ".map((c) => c.dataset.item)")
QUICK = '[data-item="quick"]'
QREAD = ("(() => { const c = document.querySelector('" + QUICK + "'); if (!c) return null; return {at: c.querySelector('[data-k^=\"qa-at:\"]').textContent, "
         "q: c.querySelector('.ask-q').textContent, title: c.querySelector('.card-title').textContent, "
         "buttons: [...c.querySelectorAll('.ask-choices .btn')].map((b) => b.textContent.trim())}; })()")


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


@pytest.fixture(params=[PHONE, WIDE], ids=["phone", "wide"])
def vp(request):
    return request.param


def test_the_small_questions_are_one_card_among_the_first_five_one_at_a_time(run, tmp_path, vp):
    got = _go(run, tmp_path, [
        {"hash": "todo", "eval": "[" + FIRST_FIVE + ", " + QREAD + "]"},
        {"click": "Yes, I have", "within": QUICK, "eval": QREAD},
    ], vp, clock=T)
    first, q1 = got["after"][0]["eval"]
    assert "quick" in first and len(first) <= 5, first
    assert q1["title"] == "4 quick answers" and q1["at"] == "1 of 4", q1
    assert q1["q"] == "Have you used Looker?" and q1["buttons"] == ["Yes, I have", "No"], q1
    # No card of its own for any of them, nor the checklist "Did these notes go?".
    text = got["after"][0]["text"]
    for gone in ("Did these notes go?", "Two answers about Quayside Foods"):
        assert text.count(gone) <= (1 if gone in q1["q"] else 0), (gone, text)
    a = [x for x in got["actions"] if x["item"] == "q-larkspur-data-looker"]
    assert a and a[-1]["action"] == "consent.yes", got["actions"]
    q2 = got["after"][1]["eval"]
    assert q2 and q2["at"] == "2 of 4" and q2["q"] != q1["q"], "the next question, at once"


def test_a_person_is_one_card_with_the_referral_in_its_grey_box(run, tmp_path, vp):
    tamsin = '[data-item="due-tamsin-resume"]'
    got = _go(run, tmp_path, [
        {"hash": "todo", "read": tamsin, "eval": "[...document.querySelectorAll('#main [data-card]')].filter((c) => /Tamsin/.test(c.textContent) && !c.parentElement.closest('[data-card]')).length"},
        {"click": "Done: Send your CV to Tamsin", "exact": True, "count": tamsin},
    ], vp, clock=T)
    card = got["after"][0]["text"]
    assert got["after"][0]["eval"] == 1, "one card for Tamsin"
    assert "Send your CV to Tamsin" in card and "Tamsin has put your name forward at Copperleaf Pay" in card, card
    assert "do not apply cold" not in got["after"][0]["text"].replace(card, ""), "never a card of its own"
    assert "This posting has closed" not in got["after"][1]["text"], "a closed posting is set aside, never a To do"
    assert [x for x in got["actions"] if x["item"] == "due-tamsin-resume" and x["action"] == "due.done"]


def test_a_checklist_row_has_its_next_step_and_done_and_its_bin_they_replied(run, tmp_path, vp):
    m = copy.deepcopy(_sample())
    m["messages"] = [x for x in m["messages"] if x["id"] != "msg-wren-2"]
    m["to_send"] = {"n": len(m["messages"]), "ids": [x["id"] for x in m["messages"]]}
    m["due"].append({"id": "due-ivo-nudge", "kind": "nudge", "title": "Follow up with Ivo at Quayside Foods", "due": "2026-10-24", "overdue_days": 1,
                     "action": "work:follow_up", "contact": "quayside_foods_ivo", "done": {"action": "due.done", "label": "Done"}, "rev": "d9"})
    card = '[data-item="grp:follow:now"]'
    row = card + ' .g-row[data-item="due-ivo-nudge"]'
    acts = "[...document.querySelectorAll('" + row.replace('"', '\\"') + " .g-acts .btn')].map((b) => b.textContent.trim() || b.getAttribute('aria-label'))"
    choices = "[...document.querySelectorAll('dialog[open] .choice-btn')].map((b) => b.textContent)"
    got = _go(run, tmp_path, [
        {"hash": "todo", "eval": acts},
        {"click": "Not Ivo at Quayside Foods? Or later", "exact": True, "eval": choices},
        {"click": "They replied", "exact": True, "within": "dialog", "ready": "!!document.querySelector('dialog[open] textarea')", "read": "dialog"},
    ], vp, model=m, clock=T)
    assert got["after"][0]["eval"][:2] == ["Draft", "Done"], got["after"][0]["eval"]
    assert got["after"][1]["eval"][0] == "They replied", got["after"][1]["eval"]
    assert "Paste what Ivo said" in got["after"][2]["dialog"], got["after"][2]["dialog"]


def test_to_do_never_offers_a_fix_and_the_draft_says_what_claude_will_fix(run, tmp_path):
    # Claude makes the draft again by itself (tools/app.py self_fixes queues it); a closed
    # posting is set aside by itself; a referral is a note on the job.
    got = _go(run, tmp_path, [{"hash": "todo"}, {"hash": "drafts", "read": '[data-item="app-quayside-demand"]'}], WIDE, clock=T)
    todo = got["after"][0]["text"]
    for b in ("Make it again", "Shorten it", "Set it aside", "the CV runs to a second page"):
        assert b not in todo, (b, todo)
    # The check's own finding leads the line since the UX review of 2026-11-10 (U-19), so it
    # starts with a capital: "The CV runs to ...: Claude makes it again next."
    assert "The CV runs to a second page by two lines" in got["after"][1]["text"] and "Make it again" not in got["after"][1]["text"], got["after"][1]["text"]


def test_a_fix_claude_could_not_make_is_said_on_to_do_with_no_button(run, tmp_path):
    # Claude's own remake has run and ended; the check still fails.
    seed = {"work/draft~app-quayside-demand": {"kind": "draft", "title": "Make it again: Quayside Foods", "status": "done",
                                               "asked_at": "2026-10-25T08:00:00Z", "finished_at": "2026-10-25T08:20:00Z", "args": {}}}
    card = '[data-item="al:al-checks-app-quayside-demand"]'
    got = _go(run, tmp_path, [{"hash": "todo", "read": card}], WIDE, clock=T, seed=seed)
    text = got["after"][0]["text"]
    assert "the CV runs to a second page by two lines" in text and "Make it again" not in text and "Open in Jobs" in text.replace("Drafts", "Jobs"), text


def test_to_dos_interview_card_offers_what_coming_up_offers(run, tmp_path):
    names = lambda sel: ("[...document.querySelectorAll('" + sel + " .card-actions > .btn, " + sel + " .card-actions > span > .btn, " + sel + " .more-acts .btn')]"  # noqa: E731
                         ".map((b) => b.textContent.trim()).filter(Boolean)")
    got = _go(run, tmp_path, [
        {"hash": "todo", "eval": names('[data-item="soon:int-larkspur-supply"]')},
        {"hash": "interviews", "click": "Interviews", "exact": True, "eval": names('article[data-item="int-larkspur-supply"]')},
    ], WIDE, clock=T)
    todo, coming = got["after"][0]["eval"], got["after"][1]["eval"]
    assert todo and todo == coming, (todo, coming)
    assert todo[:4] == ["Read your prep", "Add to calendar", "Practise with Claude", "Update my prep"], todo


def test_to_dos_header_is_one_line_with_its_way_to_the_jobs_a_pill(run, tmp_path, vp):
    head = ("(() => { const h = document.querySelector('#main .sec-head'); return {small: h.querySelectorAll('.sum-small').length, "
            "pill: [...h.querySelectorAll('.head-tools .btn')].map((b) => [b.textContent.trim(), b.className])}; })()")
    seed = {"work/prep~int-harbourline-risk": {"kind": "prep", "title": "Interview prep: Harbourline Bank", "status": "running", "to": "cloud", "args": {},
                                               "asked_at": "2026-10-25T08:58:00Z", "claimed_by": "cloud-1", "claimed_at": "2026-10-25T08:58:10Z", "stage": 1,
                                               "stage_at": "2026-10-25T08:58:10Z", "stages": [{"name": "Reading", "est_s": 60}, {"name": "Writing", "est_s": 600}],
                                               "steps": [], "stop_asked": False, "attempt": 1}}
    got = _go(run, tmp_path, [{"hash": "todo", "eval": head}, {"hash": "interviews", "eval": head}], vp, clock=T, seed=seed)
    todo, coming = got["after"][0]["eval"], got["after"][1]["eval"]
    assert todo["small"] == 0 and todo["pill"] and todo["pill"][0][0] == "1 new job to look at" and "secondary" in todo["pill"][0][1], todo
    assert coming["small"] == 0, "no line of its own for Claude's work, nor one under the summary"
