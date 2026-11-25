"""An interview's round has a screen of its own that prepares the person for it (issue 367).

Reading a prep was not preparing: the person had the questions and their answers, but nothing
said how ready they were, who they would meet and what each would probe, how to get there and
what to bring for an interview in person, or how to practise. The prep's own screen is now the
round's: the day, how ready they are as a sentence with the one next step, who they meet with
what each is likely to ask about, the format and the cheat sheet, then the questions; in person,
the day's plan, a fact not known yet said so and never guessed, with Confirm the plan asking
Claude; flashcards that keep each mark and when the card is next due (1, 3, 7 and 14 days); the
stories against the questions they answer (a grid on a wide screen, a list a story on a phone);
the numbers with a drill that hides them; and the cases, each kept as done.

On the sample page (an invented search, every person and employer invented), on a phone and on
a wide screen. The round is the one the engine puts on each upcoming interview (`round`).
"""
from __future__ import annotations

import copy
import json
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))

from test_the_page_journeys import PHONE, WIDE, _go, _sample, browser  # noqa: E402

IV = "int-larkspur-supply"
ADDR = "interviews/prep~" + IV + "/open"
# Tuesday 27 Oct, the day before the phone screen.
CLOCK = "2026-10-27T09:00:00Z"


@pytest.fixture(scope="module")
def run():
    yield from browser()


@pytest.fixture(params=[PHONE, WIDE], ids=["phone", "wide"])
def vp(request):
    return request.param


def _with(model, change):
    m = copy.deepcopy(model)
    for iv in m["interviews"]:
        if iv["id"] == IV:
            change(iv)
    return m


SCREEN = ("(() => { const d = document.querySelector('dialog.detail'); if (!d) return null;"
          " const b = d.querySelector('.detail-body');"
          " const prim = [...d.querySelectorAll('.lp-head .btn.primary')].map((x) => x.textContent);"
          " return {kind: d.dataset.detail, text: d.innerText, prim,"
          " chips: [...d.querySelectorAll('.lp-bar .lp-chips .btn')].map((x) => x.textContent),"
          " scroll: b.scrollWidth - b.clientWidth}; })()")


def _order(text, *parts):
    # Each part after the one before it.
    at = 0
    for p in parts:
        i = text.find(p, at)
        assert i >= 0, (p, "not after", text[max(0, at - 80):at])
        at = i + len(p)


def test_the_round_leads_with_how_ready_then_who_they_meet_then_the_questions(run, tmp_path, vp):
    got = _go(run, tmp_path, [{"hash": ADDR, "read": "dialog.detail", "eval": SCREEN}], vp, clock=CLOCK)
    s = got["after"][0]["eval"]
    assert s["kind"] == "prep:prep~" + IV, s["kind"]
    # The header: how long to go, where and who, and today's step of the plan.
    _order(s["text"], "Tomorrow", "Tomorrow", "Where", "Phone", "Who", "Juno, Recruiter; Kit, Supply planning lead",
           "Today: The two cards not got yet, then the numbers drill.", "You're about halfway ready (55 out of 100).", "Next: Practise the two cards you have not got yet.",
           "Who you meet", "Juno · Recruiter", "Likely to ask about: Why you are moving now", "Kit · Supply planning lead",
           "Format: Twenty minutes on the phone", "Your cheat sheet", "Lead with chilled lines", "Before you go in",
           "1. Tell me about yourself.", "Your stories", "Your numbers", "Cases to work through", "Where you sit on the project",
           "Your plan to the day")
    # The chips of #366, then one a new part, each only where it has something.
    assert s["chips"] == ["On one screen", "Questions", "Stories", "Numbers", "Cases", "Your part", "Plan", "About Larkspur Retail", "Earlier rounds"], s["chips"]
    # Practise, the flashcards, is the one filled step; Practise with Claude stays beside it.
    assert s["prim"] == ["Practise"], s["prim"]
    assert "Practise with Claude" in s["text"]
    # Not in person: no plan for the day.
    assert "On the day" not in s["text"] and "Not known yet" not in s["text"]
    assert s["scroll"] <= 0, "nothing wider than the screen"


def test_a_round_with_nothing_built_keeps_the_prep_as_it_was(run, tmp_path):
    got = _go(run, tmp_path, [{"hash": ADDR, "read": "dialog.detail", "eval": SCREEN}], PHONE,
              model=_with(_sample(), lambda iv: iv.update(round={"who": [], "stories": None, "readiness": None, "plan": None, "project": {}})), clock=CLOCK)
    s = got["after"][0]["eval"]
    assert s["chips"] == ["On one screen", "Questions", "Stories", "About Larkspur Retail", "Earlier rounds"], s["chips"]
    assert "halfway ready" not in s["text"] and "Who you meet" not in s["text"] and s["prim"] == ["Practise with Claude"]


DAY = {"address": "4 Mill Lane, Leeds", "entrance": None, "floor": "Third floor", "travel": "Train to Leeds, then a ten-minute walk",
       "arrive_by": "12:40", "bring": [], "wear": None, "timeline": [{"at": "12:40", "what": "Sign in at the front desk"},
                                                                    {"at": "13:00", "what": "Interview with Kit"}],
       "time_zone": "UK time", "final_five": ["Read your cheat sheet once."], "whiteboard": ["Say what you will draw before you draw it."],
       "confirmed": False}


def _in_person(logistics):
    def change(iv):
        iv["round"]["in_person"] = True
        iv["round"]["logistics"] = logistics
    return change


DAY_PART = ("(() => { const p = document.querySelector('[id$=\"-s-day\"]'); if (!p) return null;"
            " return {text: p.innerText, unknown: p.querySelectorAll('.rd-unknown').length,"
            " chips: [...document.querySelectorAll('dialog .lp-bar .lp-chips .btn')].map((x) => x.textContent)}; })()")


def test_in_person_the_day_is_planned_and_what_is_not_known_is_said_so(run, tmp_path, vp):
    got = _go(run, tmp_path, [
        {"hash": ADDR, "read": "dialog.detail", "eval": DAY_PART},
        {"click": "Confirm the plan for the interview with Larkspur Retail", "exact": True, "within": "dialog.detail", "read": "dialog.detail"},
    ], vp, model=_with(_sample(), _in_person(DAY)), clock=CLOCK)
    day = got["after"][0]["eval"]
    assert day["chips"][:3] == ["On one screen", "On the day", "Questions"], day["chips"]
    text = day["text"]
    for said in ("4 Mill Lane, Leeds", "Third floor", "12:40 (UK time)", "Sign in at the front desk", "Read your cheat sheet once.",
                 "Say what you will draw before you draw it.", "Not confirmed yet"):
        assert said in text, said
    # The way in, what to bring and what to wear are not known: said so, nothing filled in.
    assert day["unknown"] == 3 and text.count("Not known yet") == 3, text
    _order(text, "Way in", "Not known yet", "Floor", "Bring", "Not known yet", "Wear", "Not known yet")
    # Confirm the plan asks Claude, under the interview's own thread, and writes nothing else.
    asked = [w for w in got["after"][1]["work"] if w.get("kind") == "talk"]
    assert len(asked) == 1, got["after"][1]["work"]
    about = asked[0]["args"]["about"]
    assert about["kind"] == "interview" and about["id"] == IV, about
    assert "confirm the plan" in asked[0]["args"]["text"].lower()
    assert not [a for a in got["actions"]], "nothing is written to the record itself"


def test_in_person_with_no_plan_yet_says_every_fact_is_not_known(run, tmp_path):
    got = _go(run, tmp_path, [{"hash": ADDR, "read": "dialog.detail", "eval": DAY_PART}], PHONE,
              model=_with(_sample(), _in_person(None)), clock=CLOCK)
    day = got["after"][0]["eval"]
    # Address, way in, floor, travel, arrive by, bring, wear and the day's times: eight.
    assert day["unknown"] == 8, day
    assert "Confirm the plan" in got["after"][0]["text"]
    assert "whiteboard" not in day["text"].lower(), "a part with nothing in it is not drawn"


CARD = ("(() => { const d = document.querySelector('dialog.detail'); const f = d && d.querySelector('.rd-flash');"
        " return d ? {kind: d.dataset.detail, card: f ? f.dataset.card || 'end' : null, text: d.innerText,"
        " clock: (d.querySelector('.rd-clock-n') || {}).textContent || ''} : null; })()")
SEED = {
    # Got on the 20th, due on the 21st: due, after the missed one.
    "practice/c-proud": {"card": "c-proud", "interview": IV, "marks": [{"at": "2026-10-20T10:00:00Z", "mark": "got"}], "due": "2026-10-21", "_v": 1},
    # Missed this morning: missed cards come back first.
    "practice/c-explain": {"card": "c-explain", "interview": IV, "marks": [{"at": "2026-10-27T08:00:00Z", "mark": "missed"}], "due": "2026-10-28", "_v": 1},
    # Got twice, due in a few days: last.
    "practice/c-about": {"card": "c-about", "interview": IV, "marks": [{"at": "2026-10-20T10:00:00Z", "mark": "got"}, {"at": "2026-10-23T10:00:00Z", "mark": "got"}], "due": "2026-10-30", "_v": 1},
}


def _mark(word):
    return [{"click": "Show the answer", "exact": True, "within": "dialog.detail", "eval": CARD},
            {"click": word, "exact": True, "within": "dialog.detail", "eval": CARD}]


def test_flashcards_keep_each_mark_and_when_the_card_is_due_again(run, tmp_path, vp):
    steps = [{"hash": ADDR, "read": "dialog.detail"},
             {"click": "Practise", "exact": True, "within": "dialog.detail", "eval": CARD},
             # The clock waits to be started; then it counts down, and never stops anything.
             {"tick": 5000, "eval": CARD},
             {"click": "Start the 90 second clock", "exact": True, "within": "dialog.detail"},
             {"tick": 5000, "eval": CARD}]
    for word in ("Shaky", "Got it", "Missed", "Got it"):
        steps += _mark(word)
    steps[-1]["store"] = "practice/"
    got = _go(run, tmp_path, steps, vp, seed=copy.deepcopy(SEED), clock=CLOCK)
    after = [a.get("eval") for a in got["after"]]
    first, waiting, ticked = after[1], after[2], after[4]
    assert first["kind"] == "practise:practise~" + IV, first["kind"]
    assert got["after"][1]["hash"].endswith("/practise~" + IV + "/open"), got["after"][1]["hash"]
    assert first["clock"] == waiting["clock"] == "1:30" and re.fullmatch(r"1:2[4-6]", ticked["clock"]), (first["clock"], ticked["clock"])
    # The one missed first, then the one due, then the new one, then the one not due.
    shown = after[5::2]
    assert [first["card"]] + [x["card"] for x in after[6::2]] == ["c-explain", "c-proud", "c-wrong", "c-about", "end"], [x and x["card"] for x in after]
    # Before Show the answer only the question; after it the trigger, the points and the follow-ups.
    assert "Trigger word" not in first["text"] and "Got it" not in first["text"], "the question first, the answer behind a tap"
    wrong = shown[2]
    assert wrong["card"] == "c-wrong" and "Trigger word: Holiday miss" in wrong["text"], wrong["text"]
    assert "What would you do differently?" in wrong["text"] and "Who would you tell first?" in wrong["text"]
    assert "That's all 4 cards." in after[-1]["text"] and "2 got · 1 shaky · 1 missed" in after[-1]["text"]
    docs = {d["path"].split("/", 1)[1]: d for d in got["after"][-1]["store"]}
    # Got after one got: the second step, 3 days. Shaky after a miss: stays on 1 day. Missed:
    # back to 1 day. Got after two gots: the third step, 7 days.
    want = {"c-proud": ("got", 2, "2026-10-30"), "c-explain": ("shaky", 2, "2026-10-28"),
            "c-wrong": ("missed", 1, "2026-10-28"), "c-about": ("got", 3, "2026-11-03")}
    for card, (mark, n, due) in want.items():
        d = docs[card]
        assert d["card"] == card and d["interview"] == IV, d
        assert [m["mark"] for m in d["marks"]][-1] == mark and len(d["marks"]) == n, d
        assert d["due"] == due, (card, d["due"])
        assert d["marks"][-1]["at"].startswith("2026-10-27"), d


GRID = ("(() => { const vis = (s) => { const e = document.querySelector('dialog ' + s); return !!e && getComputedStyle(e).display !== 'none' && e.getClientRects().length > 0; };"
        " const rows = [...document.querySelectorAll('dialog .rd-grid tbody tr')].map((r) => [r.querySelector('th').textContent, r.querySelectorAll('.rd-tick').length, r.querySelectorAll('.rd-home').length]);"
        " const cols = [...document.querySelectorAll('dialog .rd-grid thead th')].map((x) => x.textContent);"
        " return {grid: vis('.rd-grid-wrap'), list: vis('.rd-grid-list'), rows, cols,"
        " list_items: [...document.querySelectorAll('dialog .rd-gl')].map((g) => g.innerText)}; })()")


def test_stories_are_a_grid_on_a_wide_screen_and_a_list_on_a_phone(run, tmp_path, vp):
    got = _go(run, tmp_path, [{"hash": ADDR, "read": "dialog.detail", "eval": GRID},
                              {"click": "Stories", "exact": True, "within": "dialog.detail .lp-bar", "eval": "document.activeElement.id"}], vp, clock=CLOCK)
    g = got["after"][0]["eval"]
    text = got["after"][0]["text"]
    for said in ("The bank holiday forecast", "Trigger word: Holiday miss", "Answers 3 likely questions.", "The one-page regional plan"):
        assert said in text, said
    # One story answering many is plain to see: a story a row, a likely question a column in
    # the cards' order, each story's home once and its backups.
    assert g["cols"] == ["Story", "Tell me about a forecast that was wrong.", "How do you explain a model to a store manager?",
                         "What are you proudest of?"], g["cols"]
    assert g["rows"] == [["The bank holiday forecast", 3, 1], ["The one-page regional plan", 1, 1]], g["rows"]
    if vp is WIDE:
        assert g["grid"] and not g["list"], g
    else:
        assert g["list"] and not g["grid"], g
        assert g["list_items"][0].startswith("The bank holiday forecast") and "What are you proudest of?" in g["list_items"][0]
    assert got["after"][1]["eval"].endswith("-s-stories"), got["after"][1]["eval"]


NUMS = "(() => { const n = document.querySelector('dialog .rd-numbers'); return n ? n.innerText : null; })()"


def test_the_numbers_drill_hides_each_value_until_it_is_shown(run, tmp_path, vp):
    got = _go(run, tmp_path, [
        {"hash": ADDR, "read": "dialog.detail", "eval": NUMS},
        {"click": "Drill: hide the numbers to recall them", "exact": True, "within": "dialog.detail", "eval": NUMS},
        {"click": "Show the number for forecast error the quarter after the fix", "exact": True, "within": "dialog.detail", "eval": NUMS},
        {"click": "Show every number", "exact": True, "within": "dialog.detail", "eval": NUMS},
    ], vp, clock=CLOCK)
    plain, drill, one, back = (a["eval"] for a in got["after"])
    for v in ("a third", "9%", "2,400"):
        assert v in plain and v in back, v
        assert v not in drill, v
    assert "fewer stock-outs on chilled lines" in drill and drill.count("Show") >= 3
    assert "9%" in one and "a third" not in one and "2,400" not in one


def test_a_case_is_kept_as_done_and_a_mock_names_the_interviewer(run, tmp_path):
    got = _go(run, tmp_path, [
        {"hash": ADDR, "read": "dialog.detail"},
        {"click": "Done: I worked through Why are stock-outs up?", "exact": True, "within": "dialog.detail", "read": "dialog.detail", "store": "practice/"},
        {"click": "Mock interview with Claude as Kit, Supply planning lead", "exact": True, "within": "dialog.detail", "read": "#main", "wait": 300, "calls": "sample"},
    ], WIDE, clock=CLOCK, fake={"canSend": "available", "sample": {"replies": ["Tell me about a forecast that was wrong."]}})
    case = got["after"][0]["text"]
    for said in ("Why are stock-outs up?", "Stock-outs on yoghurt rose by a quarter", "Split by store and day", "Draw it like this".upper(),
                 "About 180 stores in the region", "Forecast  ->  Order"):
        assert said in case, said
    done = got["after"][1]
    docs = {d["path"]: d for d in done["store"]}
    d = docs["practice/case~" + IV + "~case-stockout"]
    assert d["kind"] == "case" and d["interview"] == IV and d["at"].startswith("2026-10-27"), d
    assert "Worked through Tue 27 Oct." in done["text"] and "Done again" in done["text"], done["text"]
    asked = json.dumps(got["after"][2]["calls"][0])
    assert "You are playing Kit, Supply planning lead" in asked and "How you handle a forecast miss" in asked, asked[:400]


FILTERED = ("(() => { const d = document.querySelector('dialog.detail'); const f = d.querySelector('.rd-flash');"
            " return {card: f ? f.dataset.card : null, of: (d.querySelector('.rd-flash-top p') || {}).textContent || '',"
            " pressed: [...d.querySelectorAll('.rd-filter [aria-pressed=true]')].map((b) => b.getAttribute('aria-label'))}; })()")


def test_the_cards_are_filtered_by_part_and_by_who_asks(run, tmp_path):
    got = _go(run, tmp_path, [
        {"hash": "interviews/practise~" + IV + "/open", "read": "dialog.detail", "eval": FILTERED},
        {"click": "Asked by: Kit", "exact": True, "within": "dialog.detail", "eval": FILTERED},
        {"click": "Part: Opening", "exact": True, "within": "dialog.detail", "eval": FILTERED},
    ], PHONE, clock=CLOCK)
    every, kit, opening = (a["eval"] for a in got["after"])
    assert every["of"].startswith("Card 1 of 4") and every["pressed"] == ["Part: all", "Asked by: all"], every
    # Kit's cards and the ones anyone may ask.
    assert kit["of"].startswith("Card 1 of 3") and kit["card"] == "c-about" and "anyone may ask" in kit["of"], kit
    assert opening["of"].startswith("Card 1 of 1") and opening["pressed"] == ["Part: Opening", "Asked by: Kit"], opening


PARTS = ("(() => ({today: [...document.querySelectorAll('dialog .rd-plan .rd-is-today')].map((x) => x.innerText),"
         " was: document.querySelectorAll('dialog .rd-plan .rd-was').length,"
         " you: [...document.querySelectorAll('dialog .rd-proj .rd-you strong')].map((x) => x.textContent),"
         " bars: [...document.querySelectorAll('dialog .rd-bar')].map((b) => [b.querySelector('.rd-bar-k').textContent, b.classList.contains('rd-bar-low')]),"
         " steps: document.querySelectorAll('dialog .rd-case .rd-steps li').length}))()")


def test_the_plan_marks_today_and_the_project_marks_what_they_lead(run, tmp_path, vp):
    got = _go(run, tmp_path, [{"hash": ADDR, "read": "dialog.detail", "eval": PARTS},
                              {"click": "Plan", "exact": True, "within": "dialog.detail .lp-bar", "eval": "document.activeElement.id"}], vp, clock=CLOCK)
    p = got["after"][0]["eval"]
    assert len(p["today"]) == 1 and "The two cards not got yet" in p["today"][0] and "Today" in p["today"][0], p
    assert p["was"] == 2, p
    assert p["you"] == ["Data", "Forecast"], p
    # The case's steps drawn as a row of steps, its numbers as bars, the shortest marked.
    assert p["steps"] == 4 and p["bars"] == [["Depot A", False], ["Depot B", True], ["Depot C", False]], p
    assert got["after"][0]["text"].count("You lead") == 2
    assert got["after"][1]["eval"].endswith("-s-plan"), got["after"][1]["eval"]


def test_a_live_prep_and_its_round_are_one_tap_apart(run, tmp_path):
    from test_the_live_prep_on_the_page import _live_made_before as _live

    def both(iv):
        iv["live"] = _live()
    got = _go(run, tmp_path, [
        {"hash": "interviews", "open": "up-go:up-app-larkspur-supply-phone-screen-2026-10-28", "read": "dialog.detail"},
        {"click": "Open your round", "exact": True, "within": "dialog.detail", "eval": SCREEN},
        {"click": "Read it as you'll say it", "exact": True, "within": "dialog.detail", "eval": "document.querySelector('dialog.detail').dataset.detail"},
    ], WIDE, model=_with(_sample(), both), clock=CLOCK)
    s = got["after"][1]["eval"]
    assert s["kind"] == "prep:prep~" + IV and "halfway ready" in s["text"], s["kind"]
    assert got["after"][2]["eval"] == "interview:" + IV, got["after"][2]["eval"]
