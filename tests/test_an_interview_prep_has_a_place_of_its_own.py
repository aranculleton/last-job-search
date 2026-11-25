"""An interview's prep has a place of its own, full screen, and no card holds it (issue 365).

A person opening an employer with a live interview process found the whole prep (the format,
who they were meeting, the likely questions, the answers, the follow-ups) at the foot of a
card, under everything else: minutes before a call they had to scroll past the card to reach
the questions. Now the employer's card and the interview's card each say where the prep is and
open it with Read your prep; the prep is its own full-screen sheet with an address of its own,
opening on the one-screen summary, with every likely question one tap from it, a bar that goes
to each part, and nothing folded. A follow-up may carry its own follow-ups at any depth, and
each is drawn under the one it follows.

On the sample page (an invented search, every person and employer invented), on a phone and on
a wide screen.
"""
from __future__ import annotations

import copy
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))

from test_the_page_journeys import PHONE, WIDE, _go, _sample, browser  # noqa: E402

IV = "int-larkspur-supply"
# The day before the interview (Wed 28 Oct, 13:00): the employer's card leads with it.
CLOCK = "2026-10-27T09:00:00Z"
QUESTION = "Tell me about a forecast that was wrong."


@pytest.fixture(scope="module")
def run():
    yield from browser()


@pytest.fixture(params=[PHONE, WIDE], ids=["phone", "wide"])
def vp(request):
    return request.param


# What a card holds of the prep: its questions and answers, drawn anywhere in it.
CARD = ("(() => { const d = document.querySelector('dialog.detail'); if (!d) return null;"
        " return {kind: d.dataset.detail, full: d.classList.contains('full'),"
        " questions: d.querySelectorAll('.pq-a, .pq-cue, .pq, .pv-q, .lp-q, details.prep-fold').length,"
        " read: [...d.querySelectorAll('button')].filter((b) => b.textContent.trim() === 'Read your prep').length}; })()")
# The prep's own place: what comes first under its bar, its chips, its questions.
PREP = ("(() => { const d = document.querySelector('dialog.detail'); if (!d) return null;"
        " const lp = d.querySelector('.lp.pv'); const bar = lp && lp.querySelector('.lp-bar');"
        " let first = bar && bar.nextElementSibling;"
        " return {kind: d.dataset.detail, full: d.classList.contains('full'), wide: Math.round(d.getBoundingClientRect().width), vw: innerWidth,"
        " first: first ? first.className : '', firstText: first ? first.textContent : '',"
        " chips: bar ? [...bar.querySelectorAll('.lp-chips .btn')].map((b) => b.textContent) : [],"
        " questions: d.querySelectorAll('.pv-q').length, index: d.querySelectorAll('.pv-index .lp-glance-q').length,"
        " folds: d.querySelectorAll('details').length, scroll: d.querySelector('.detail-body').scrollWidth - d.querySelector('.detail-body').clientWidth,"
        " follow: [...d.querySelectorAll('.pv-fu-q')].map((x) => [x.textContent, +x.closest('.pv-follow').dataset.depth])}; })()")
FOCUS = "(() => { const a = document.activeElement; return a ? (a.closest('.pv-q') || a).id + '|' + (a.closest('.pv-q') || a).textContent.slice(0, 60) : ''; })()"


def test_the_employer_card_links_to_the_prep_and_the_prep_opens_on_its_summary(run, tmp_path, vp):
    got = _go(run, tmp_path, [
        # The employer's card: its next thing is the interview, and Read your prep its button.
        {"hash": "jobs/emp~larkspur-retail/open", "read": "dialog.detail", "eval": CARD},
        {"click": "Read your prep", "exact": True, "within": "dialog.detail", "read": "dialog.detail", "eval": PREP},
        # A likely question, from the summary, goes to its answer.
        {"click": QUESTION, "exact": True, "within": "dialog.detail .pv-index", "eval": FOCUS},
        # The bar goes to a part.
        {"click": "Stories", "exact": True, "within": "dialog.detail .lp-bar", "eval": FOCUS},
    ], vp, clock=CLOCK)
    card, prep, asked, stories = (a["eval"] for a in got["after"])
    # The card links to the prep and holds none of it.
    assert card["kind"] == "employer:emp~larkspur-retail" and card["read"] == 1, card
    assert card["questions"] == 0 and QUESTION not in got["after"][0]["text"], card
    # The prep is a place of its own: full screen, its own address, the summary first.
    assert prep["kind"] == "prep:prep~" + IV and prep["full"] and prep["wide"] == prep["vw"], prep
    assert got["after"][1]["hash"].endswith("/prep~" + IV + "/open"), got["after"][1]["hash"]
    assert "pv-summary" in prep["first"] and "Before you go in" in prep["firstText"], prep
    assert prep["chips"][:2] == ["On one screen", "Questions"] and "Stories" in prep["chips"], prep["chips"]
    assert prep["questions"] == prep["index"] == 5 and prep["folds"] == 0, prep
    assert prep["scroll"] <= 0, "nothing wider than the screen"
    # Practising stays one tap away on the prep itself.
    assert "Practise with Claude" in got["after"][1]["text"]
    assert asked.split("|")[0].endswith("-q-2") and QUESTION in asked, asked
    assert "-s-stories" in stories.split("|")[0], stories


def test_the_interview_card_says_where_the_prep_is_and_holds_none_of_it(run, tmp_path):
    got = _go(run, tmp_path, [
        {"hash": "interviews", "open": "up-go:up-app-larkspur-supply-phone-screen-2026-10-28", "read": "dialog.detail", "eval": CARD},
        {"click": "Read your prep", "within": "dialog.detail", "eval": PREP},
    ], PHONE, clock=CLOCK)
    card, prep = (a["eval"] for a in got["after"])
    assert card["kind"] == "interview:" + IV and not card["full"] and card["read"] == 1, card
    assert card["questions"] == 0 and "Before you go in" not in got["after"][0]["text"], card
    assert prep["kind"] == "prep:prep~" + IV and prep["questions"] == 5, prep


def test_its_own_address_opens_it(run, tmp_path):
    got = _go(run, tmp_path, [{"hash": "interviews/prep~" + IV + "/open", "read": "dialog.detail", "eval": PREP}],
              WIDE, clock=CLOCK)
    prep = got["after"][0]["eval"]
    assert prep["kind"] == "prep:prep~" + IV and "Before you go in" in prep["firstText"], prep


def _with(model, change):
    m = copy.deepcopy(model)
    for iv in m["interviews"]:
        if iv["id"] == IV:
            change(iv)
    return m


def test_a_follow_up_with_its_own_follow_ups_is_drawn_at_every_depth(run, tmp_path, vp):
    def deep(iv):
        iv["prep_read"]["questions"][0]["follow"] = [
            {"q": "Which part was hardest?", "who": "manager", "simple": ["The supplier data.", "It came late."],
             "follow": [{"q": "What did you do about it?", "answer": "Moved the cut-off a day.",
                         "follow": [{"q": "Who agreed to that?", "follow": [{"question": "And did it hold?"}]}]}]},
            "Would you do it again?"]
    got = _go(run, tmp_path, [{"hash": "interviews/prep~" + IV + "/open", "read": "dialog.detail", "eval": PREP}],
              vp, model=_with(_sample(), deep), clock=CLOCK)
    prep = got["after"][0]["eval"]
    assert [q for q, _ in prep["follow"]][:5] == ["Which part was hardest? Hiring manager", "What did you do about it?",
                                                  "Who agreed to that?", "And did it hold?", "Would you do it again?"], prep["follow"]
    assert [d for _, d in prep["follow"]] == [1, 2, 3, 4, 1], prep["follow"]
    text = got["after"][0]["text"]
    assert "The supplier data. It came late." in text and "Moved the cut-off a day." in text


def test_a_prep_the_engine_could_not_read_is_parted_by_its_own_headings(run, tmp_path):
    def unread(iv):
        # A prep the engine could not read has no round built from it either (issue 367).
        iv.pop("round", None)
        iv["prep_read"] = None
        iv["one_screen"] = None
        iv["prep_text"] = ("# Prep: Larkspur Retail\n\n## Format\n\nTwenty minutes on video with the recruiter.\n\n"
                           "## Likely questions\n\n### Why this role?\n\nThe store-level forecasting.\n\n"
                           "### Walk me through a case.\n\nThe bank holiday miss.\n\n"
                           "## On one screen\n\n- Lead with the chilled lines result.\n")
    got = _go(run, tmp_path, [
        {"hash": "interviews/prep~" + IV + "/open", "read": "dialog.detail", "eval": PREP},
        {"click": "Walk me through a case.", "exact": True, "within": "dialog.detail .pv-index",
         "eval": "document.activeElement.id + '|' + document.activeElement.textContent"},
    ], PHONE, model=_with(_sample(), unread), clock=CLOCK)
    prep, jumped = got["after"][0]["eval"], got["after"][1]["eval"]
    # The one-screen summary leads, then each part by its own heading; nothing is folded.
    assert prep["chips"] == ["On one screen", "Format", "Likely questions"], prep["chips"]
    assert "Lead with the chilled lines result." in prep["firstText"] and prep["index"] == 2, prep
    assert prep["folds"] == 0
    assert jumped.endswith("|Walk me through a case."), jumped
