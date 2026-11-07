"""A round already had reads as had, waiting to hear back, and never as one still to come.

The maintainer, 2026-11-07, on a Saturday: "whys this still showing as coming up on monday the
2nd of november? i had it didnt I? ... I mean, I am waiting on them". Coming up said "1
interview coming up. Your prep is ready for each one." over two cards, a round with no day
yet titled with the employer's whole paragraph, and a recruiter screen "Mon 2 Nov" with
"Waiting to hear". Now the engine says which rounds were had (`had`) and counts once what is
ahead, what has no day and what waits to hear (`coming_up`); the card says "You had it 2
Nov", a gone day without its weekday (DESIGN.md, Words: dates), below what is ahead; and a
round's title is its short name, the paragraph kept as its details. Every person and employer
here is invented (tests/app_state.py, the sample page model).
"""
from __future__ import annotations

import copy
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import upcoming  # noqa: E402
from test_a_tick_on_the_page_is_applied_once import Search  # noqa: E402

PARAGRAPH = ("Initial round : two 60-minute virtual interviews with the hiring manager and a "
             "senior analyst. Interview 1: a technical case on supply data. Interview 2: "
             "behavioural questions and your questions for them")
THORNBURY = "int-thornbury_bank_risk_analyst"
LARKSPUR = "app-larkspur_retail_senior_supply_chain_analyst"
FOLDER = ("documents", "applications", "thornbury_bank_risk_analyst_thornbury")


# ------------------------------------------------------------------ the engine


def test_a_long_stage_name_is_titled_by_its_first_words_and_keeps_the_rest():
    assert upcoming.short_label(PARAGRAPH) == "Initial round"
    assert upcoming.label_details(PARAGRAPH).startswith("Two 60-minute virtual interviews")
    assert "Interview 2: behavioural" in upcoming.label_details(PARAGRAPH)
    # A short name stays as it was, with nothing more to say.
    for name in ("Phone screen", "Online test: case study", "Second interview"):
        assert upcoming.short_label(name) == name and upcoming.label_details(name) == ""


@pytest.fixture
def search(tmp_path):
    return Search(str(tmp_path))


def test_the_engine_says_which_round_was_had_and_counts_coming_up_once(search):
    # Thornbury's panel was on 22 Oct, before today (25 Oct): had, and waiting to hear.
    md = os.path.join(search.state, *FOLDER, "outcome.md")
    with open(md, "w", encoding="utf-8") as fh:
        fh.write("# Outcome\n\n## Interview stages reached\n\n"
                 "- [x] Phone screen (2026-10-15, with the recruiter)\n"
                 "- [ ] Panel interview (scheduled 2026-10-22, with the head of risk)\n")
    # Larkspur invited the person to an initial round, its whole paragraph as the name.
    app = next(a for a in search.model()["applications"] if a["id"] == LARKSPUR)
    aid = search.act("outcome.interview", LARKSPUR, rev=app["rev"], value={"stage": PARAGRAPH, "on": ""})
    assert search.apply()["ok"] == [aid], search.receipt(aid)
    m = search.model()
    ivs = {i["id"]: i for i in m["interviews"]}
    had = ivs[THORNBURY]
    assert had["had"] is True and had["past"] is False and had["when"] == "2026-10-22"
    (initial,) = [i for i in m["interviews"] if i["company"] == "Larkspur Retail"]
    assert initial["had"] is False and initial["when"] is None
    assert initial["stage_title"] == "Initial round"
    assert initial["stage_details"].startswith("Two 60-minute virtual interviews")
    # What an action names the round by is kept whole, so a new day finds the same round.
    assert initial["next_stage"].startswith("Initial round : two 60-minute")
    cu = m["coming_up"]
    assert cu["ahead"] == [initial["id"]] and cu["undated"] == [initial["id"]]
    assert cu["waiting"] == [THORNBURY]
    assert THORNBURY not in cu["ahead"] and THORNBURY not in cu["unprepped"]


# ------------------------------------------------------------------ the page


def _model():
    from test_the_page_journeys import _sample
    m = _sample()
    ivs = {i["id"]: i for i in m["interviews"]}
    lark, harb = copy.deepcopy(ivs["int-larkspur-supply"]), copy.deepcopy(ivs["int-harbourline-risk"])
    lark.update(next_stage=PARAGRAPH, stage_title="Initial round", stage_details=upcoming.label_details(PARAGRAPH),
                when=None, all_day=True, time=None, had=False, alerts=[], suggest=None)
    harb.update(next_stage="Recruiter screen", when="2026-11-02", all_day=True, time=None, had=True, alerts=[], suggest=None)
    m["interviews"] = [lark, harb]
    m["upcoming"] = []
    m["coming_up"] = {"ahead": [lark["id"]], "undated": [lark["id"]], "unprepped": [], "waiting": [harb["id"]]}
    return m


CLOCK = "2026-11-07T10:00:00Z"


@pytest.mark.parametrize("old", [False, True], ids=["engine-counts", "model-before-the-counts"])
def test_coming_up_reads_a_round_had_as_had_below_what_is_ahead(tmp_path, old):
    from test_the_page_journeys import _go, browser, PHONE, WIDE
    gen = browser()
    run = next(gen)
    try:
        for vp in (PHONE, WIDE):
            m = _model()
            if old:
                # A page model written before the engine counted: read from the interviews.
                m.pop("coming_up")
                for i in m["interviews"]:
                    i.pop("had")
            got = _go(run, tmp_path, [
                {"hash": "interviews", "read": "#main"},
                {"hash": "interviews", "eval": "[...document.querySelectorAll('#main article.card.interview')].map((c) => [c.querySelector('h3').textContent, (c.querySelector('.when') || {}).textContent || ''])"},
                {"hash": "todo", "read": "#main"},
                {"hash": "brief", "read": '[data-k="bp:upcoming"]'},
                {"hash": "interviews", "click": "Read your prep for your initial round with Larkspur Retail"},
            ], vp, model=m, clock=CLOCK)
            text = got["after"][0]["text"]
            assert "1 interview coming up, no day yet." in text, text[:400]
            assert "1 interview waiting to hear back." in text, text[:400]
            cards = got["after"][1]["eval"]
            # What is ahead first, then the round had; its day said as gone, with no weekday.
            assert [c[0] for c in cards] == ["Initial round with Larkspur Retail", "Recruiter screen with Harbourline Bank"], cards
            assert cards[1][1].split(" · ")[0] == "You had it 2 Nov", cards
            assert cards[0][1].split(" · ")[0] == "No day yet", cards
            assert "Mon 2 Nov" not in text and "Interview 1:" not in text, text
            # To do never offers the round had as one coming up.
            assert "Recruiter screen with Harbourline Bank" not in got["after"][2]["text"]
            brief = got["after"][3]["text"]
            assert "Waiting to hear back from Harbourline Bank." in brief, brief
            assert "Mon 2 Nov" not in brief
            # The paragraph is not lost: the round's own page says it.
            assert "Interview 1: a technical case on supply data" in got["after"][4]["dialog"], got["after"][4]["dialog"][:600]
    finally:
        try:
            next(gen)
        except StopIteration:
            pass
