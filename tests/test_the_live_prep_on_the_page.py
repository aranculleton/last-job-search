"""The live prep on the page: an interview's card opens it full screen, in the order the
interview runs.

The prep is the engine's own (`tools/interview_live.py`), built for the example person's
invented application and filled the way Claude fills it, then put on the sample page's
interview. Each test taps it as a person would, on a phone and on a wide screen: the parts in
order, the one switch that flips every answer and the switch that flips one, a "Likely to
prompt" link that goes to its answer and marks it, a term that opens and its Back, Practice
that hides the answers and shows one on a tap, nothing wider than the screen, the dark look,
and no script errors. Every person and employer is invented.
"""
from __future__ import annotations

import copy
import json
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import app_page  # noqa: E402
import interview_live as L  # noqa: E402
from test_an_interview_has_a_live_prep import _fill  # noqa: E402
from test_interview_pack import _ctx, app  # noqa: E402,F401
from test_the_page_journeys import PHONE, WIDE, _sample, browser  # noqa: E402


# The example person's invented application, on disk for every test here.
pytestmark = pytest.mark.usefixtures("app")

IV = "int-larkspur-supply"


@pytest.fixture(scope="module")
def run():
    yield from browser()


@pytest.fixture(params=[PHONE, WIDE], ids=["phone", "wide"])
def vp(request):
    return request.param


def _live(ctx):
    """The engine's prep, filled as Claude fills it, with a known question, a term inside a
    term, a follow-up two deep and a draft the person asked for."""
    doc = _fill(L.build(ctx))
    doc["known"] = [{"text": "How do you get depot managers to trust a forecast?", "from": "the recruiter"}]
    doc = L.merge(L.build(ctx), doc)
    k = doc["known"][0]
    q = next(x for x in doc["questions"] if x["id"] == k["question"])
    part = next(p for p in doc["parts"] if p["id"] == q["part"])
    part["say"].append({"t": "Trust is usually the first thing people ask about, so I'll take it head on: "
                             "I show the error by site every week.", "prompts": [q["id"]], "known": k["id"]})
    q["simple"] = ("I show the error by site every week, so the planners can see where it holds. Then "
                   "they trust it where it has earned it.")
    q["detailed"] = ("I show the error by site every week, so the planners can see where it holds and where "
                     "it does not. Then they trust it where it has earned it, and tell me where it misses.")
    first = doc["questions"][0]
    first["also"] = ["Give me the short version of your background."]
    first["follow"] = [{"who": "manager", "q": "What did the planners make of it?", "also": [],
                        "simple": "They were wary at first. Seeing the error by site won them over.",
                        "detailed": "", "follow": [{"who": "peer", "q": "And the ones who were not won over?",
                                                    "also": [], "simple": "They kept their own numbers for a while. "
                                                                          "Then the error spoke for itself.",
                                                    "detailed": "", "follow": []}]}]
    doc["questions"][1]["draft"] = True
    doc["terms"]["demand-forecast"]["here"] += " It is built from each site's [[cross-dock]] volumes."
    doc["terms"]["cross-dock"] = {
        "name": "Cross-dock", "here": "A Fernhill Freight site where pallets come off one lorry and onto another.",
        "example": "Forty pallets arrive at six, and by eight they are on three outbound lorries.",
        "plain": "A depot that moves goods straight through instead of storing them.", "technical": ""}
    doc = L.finish(doc)
    assert L.problems(doc, ctx) == [], L.problems(doc, ctx)
    doc["checked"] = {"on": ctx["today"], "problems": 0, "drafts": len(L.drafts(doc))}
    return L.for_page(doc)


def _model(ctx):
    m = _sample()
    for iv in m["interviews"]:
        if iv["id"] == IV:
            iv["live"] = _live(ctx)
    return m


def _go(run, tmp_path, model, steps, vp, scheme=None):
    path = os.path.join(str(tmp_path), "page.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(app_page.standalone(app_page.render(model)))
    got = run("engine", html=path, viewport=vp, steps=steps, seed={}, fake={"canSend": "available"},
              **({"scheme": scheme} if scheme else {}))
    assert not got["errors"], got["errors"]
    return got


OPEN = {"hash": "interviews", "click": "Read your prep", "read": "dialog.detail"}
VISIBLE = "(el) => !!el && el.checkVisibility() && el.getClientRects().length > 0"


def _ev(body):
    return "(() => { const vis = %s; %s })()" % (VISIBLE, body)


def test_the_parts_are_in_the_order_the_interview_runs(run, tmp_path, vp):
    ctx = _ctx()
    model = _model(ctx)
    lv = next(iv for iv in model["interviews"] if iv["id"] == IV)["live"]
    got = _go(run, tmp_path, model, [dict(OPEN, eval=_ev(
        "const d = document.querySelector('dialog.detail');"
        "return {full: d.classList.contains('full'), parts: [...d.querySelectorAll('.lp-part-h')].map((x) => x.textContent),"
        " cards: d.querySelectorAll('.lp-q').length, chips: d.querySelectorAll('.lp-chips .btn').length,"
        " wide: Math.round(d.__drawnRect().width), vw: innerWidth};"))], vp)
    seen = got["after"][0]["eval"]
    assert seen["full"] and seen["wide"] == seen["vw"], "the prep is full screen on every screen"
    titles = [p["title"] for p in lv["parts"]]
    assert [t.split(" · ", 1)[1] for t in seen["parts"]] == titles
    # A chip to every part, then to what they ask, the stories, the words and the notes.
    assert seen["cards"] == len(lv["questions"]) and seen["chips"] == len(titles) + 4
    text = got["after"][0]["text"]
    assert "A technical interview" in text and "What they are known to ask" in text
    assert "Just for you" in text and "Your stories" in text and "Words to know, A to Z" in text
    assert "One month" in text, "the notice period from the profile is in the private notes"
    assert text.count("Draft") >= 2, "the draft is marked where it is, and said once at the top"


def test_the_switch_flips_every_answer_and_one_flips_back(run, tmp_path, vp):
    count = ("const d = document.querySelector('dialog.detail');"
             "return {detailed: [...d.querySelectorAll('.lp-detailed')].filter(vis).length,"
             " all: d.querySelectorAll('.lp-detailed').length, simple: [...d.querySelectorAll('.lp-simple')].filter(vis).length,"
             " first: vis(d.querySelector('#lpq-q1 .lp-detailed'))};")
    got = _go(run, tmp_path, _model(_ctx()), [
        dict(OPEN, eval=_ev(count)),
        {"click": "Detailed", "role": "radio", "within": "dialog.detail .lp-all", "read": "dialog.detail", "eval": _ev(count)},
        {"click": "Simple", "role": "radio", "within": "#lpq-q1 .lp-ans-top", "read": "dialog.detail", "eval": _ev(count)},
    ], vp)
    before, flipped, one = (a["eval"] for a in got["after"])
    assert before["detailed"] == 0 and before["all"] > 1
    assert flipped["detailed"] == flipped["all"], "one switch shows every detailed answer"
    assert one["detailed"] == flipped["all"] - 1 and not one["first"], "an answer's own switch flips that one back"


def test_a_likely_to_prompt_link_goes_to_its_answer_and_marks_it(run, tmp_path, vp):
    got = _go(run, tmp_path, _model(_ctx()), [
        OPEN,
        {"click": "Full answer and follow-ups:", "within": "dialog.detail", "read": "dialog.detail", "wait": 1200,
         "eval": "(() => { const a = document.activeElement; const r = a.__drawnRect();"
                 " return {id: a.id, flash: a.classList.contains('lp-flash'), top: Math.round(r.top), vh: innerHeight}; })()"},
    ], vp)
    at = got["after"][1]["eval"]
    assert at["id"].startswith("lpq-") and at["flash"], at
    assert 0 <= at["top"] < at["vh"], "the answer is scrolled into view"


def test_a_term_opens_and_back_returns(run, tmp_path, vp):
    panel = _ev("const p = document.querySelector('.lp-panel');"
                "return {open: vis(p), title: p.querySelector('.lp-panel-title').textContent,"
                " back: vis(p.querySelector('.lp-back')), text: p.textContent,"
                " box: (() => { const r = p.__drawnRect(); return [Math.round(r.left), Math.round(r.right), Math.round(r.bottom)]; })(), vw: innerWidth, vh: innerHeight};")
    got = _go(run, tmp_path, _model(_ctx()), [
        OPEN,
        {"click": "forecasts: what it means", "within": "dialog.detail .lp-part", "eval": panel},
        {"click": "Cross-dock: what it means", "within": ".lp-panel", "eval": panel},
        {"click": "Back", "exact": True, "within": ".lp-panel", "eval": panel},
        {"click": "Close", "exact": True, "within": ".lp-panel", "eval": panel},
    ], vp)
    first, deeper, back, closed = (a["eval"] for a in got["after"][1:])
    assert first["open"] and first["title"] == "Demand forecast" and not first["back"]
    assert "At Fernhill Freight" in first["text"] and "A worked example" in first["text"]
    assert deeper["title"] == "Cross-dock" and deeper["back"], "a term inside a term opens with Back"
    assert back["title"] == "Demand forecast" and not back["back"]
    assert not closed["open"]
    left, right, bottom = first["box"]
    if vp is PHONE:
        assert left <= 1 and bottom >= first["vh"] - 1, "a sheet from the bottom on a phone"
    else:
        assert left > first["vw"] / 2 and right <= first["vw"], "a panel at the side on a wide screen"


def test_practice_hides_the_answers_and_a_tap_shows_one(run, tmp_path, vp):
    state = _ev("const d = document.querySelector('dialog.detail');"
                "return {shown: [...d.querySelectorAll('.lp-reveal')].filter(vis).length, all: d.querySelectorAll('.lp-reveal').length,"
                " first: vis(d.querySelector('#lpq-q1 .lp-reveal')), timer: d.querySelector('#lpq-q1 .lp-timer').textContent};")
    got = _go(run, tmp_path, _model(_ctx()), [
        dict(OPEN, eval=state),
        {"click": "Hide the answers", "exact": True, "within": "dialog.detail .lp-bar", "eval": state},
        {"click": "Start answering", "within": "#lpq-q1", "eval": state},
        {"click": "Show the answer", "within": "#lpq-q1", "eval": state},
    ], vp)
    before, hidden, started, shown = (a["eval"] for a in got["after"])
    assert before["shown"] == before["all"] > 0
    assert hidden["shown"] == 0, "practice hides every answer"
    assert started["timer"].startswith("0:") and not started["first"]
    assert shown["first"] and shown["shown"] == 1 and shown["timer"].startswith("You took")


def test_nothing_is_wider_than_a_phone_and_the_dark_look_draws(run, tmp_path):
    wide = ("(() => { const d = document.querySelector('dialog.detail'); const b = d.querySelector('.detail-body');"
            " const over = [...d.querySelectorAll('.lp *:not(.lp-chips *)')].filter((e) => e.__drawnRect().right > innerWidth + 1 && e.getClientRects().length).map((e) => e.className).slice(0, 5);"
            " const bg = getComputedStyle(d).backgroundColor.match(/\\d+/g).slice(0, 3).map(Number);"
            " return {sideways: b.scrollWidth > b.clientWidth + 1, over, light: (bg[0] + bg[1] + bg[2]) / 3}; })()")
    steps = [dict(OPEN), {"open": "det:lp:q1.0", "eval": wide}]
    light = _go(run, tmp_path, _model(_ctx()), steps, PHONE)["after"][1]["eval"]
    assert not light["sideways"] and light["over"] == [], light
    dark = _go(run, tmp_path, _model(_ctx()), steps, PHONE, scheme="dark")["after"][1]["eval"]
    assert not dark["sideways"] and dark["over"] == [], dark
    assert dark["light"] < 100 < light["light"], "the dark look is dark and the light look light"


# ------------------------------------------------------------------ the review of 2026-11-10

def _bg(sel):
    return "getComputedStyle(document.querySelector(%r)).backgroundColor" % sel


def test_the_chosen_side_of_each_switch_shows(run, tmp_path, vp):
    # Simple and Detailed looked the same, at the top and on every answer: the page styled
    # aria-pressed and the switch set aria-checked.
    look = ("(() => { const on = (s) => getComputedStyle(document.querySelector(s)).backgroundColor;"
            " return {top: [on('.lp-all [data-v=simple]'), on('.lp-all [data-v=detailed]')],"
            " one: [on('#lpq-q1 .lp-ans-top [data-v=simple]'), on('#lpq-q1 .lp-ans-top [data-v=detailed]')]}; })()")
    got = _go(run, tmp_path, _model(_ctx()), [dict(OPEN, eval=look),
        {"click": "Detailed", "role": "radio", "within": "dialog.detail .lp-all", "wait": 500, "eval": look}], vp)
    before, after = (a["eval"] for a in got["after"])
    for pair in (before["top"], before["one"], after["top"], after["one"]):
        assert pair[0] != pair[1], pair
    assert before["top"] == after["top"][::-1], "the chosen side moves with the choice"


def test_hiding_the_answers_says_so_and_looks_pressed(run, tmp_path, vp):
    look = ("(() => { const b = [...document.querySelectorAll('.lp-bar button')].find((x) => x.textContent === 'Hide the answers');"
            " const line = document.querySelector('.lp-hidden-line');"
            " return {bg: getComputedStyle(b).backgroundColor, pressed: b.getAttribute('aria-pressed'),"
            " line: line.checkVisibility() ? line.textContent : '',"
            " practise: [...document.querySelectorAll('dialog.detail button')].filter((x) => x.textContent.trim() === 'Practise').length}; })()")
    got = _go(run, tmp_path, _model(_ctx()), [dict(OPEN, eval=look),
        {"click": "Hide the answers", "exact": True, "within": "dialog.detail .lp-bar", "wait": 500, "eval": look}], vp)
    off, on = (a["eval"] for a in got["after"])
    assert off["practise"] == 0, "never a second Practise under Practise with Claude"
    assert off["pressed"] == "false" and on["pressed"] == "true"
    lum = lambda c: sum(int(x) for x in re.findall(r"\d+", c)[:3]) / 3  # noqa: E731
    assert abs(lum(on["bg"]) - lum(off["bg"])) > 60, (off["bg"], on["bg"])
    assert off["line"] == "" and on["line"] == "Answers hidden: tap Start, say it aloud."


def test_search_and_the_chips_stay_in_reach_however_far_down(run, tmp_path, vp):
    look = ("(() => { const b = document.querySelector('dialog.detail .detail-body'); b.scrollTop = b.scrollHeight;"
            " return new Promise((ok) => requestAnimationFrame(() => requestAnimationFrame(() => {"
            " const bar = document.querySelector('.lp-bar').__drawnRect();"
            " const f = document.querySelector('.lp-bar input');"
            " ok({top: Math.round(bar.top), bottom: Math.round(bar.bottom), vh: innerHeight, placeholder: f.placeholder,"
            " fits: f.scrollWidth <= f.clientWidth + 1,"
            " chips: [...document.querySelectorAll('.lp-chips .btn')].map((x) => x.textContent)}); }))); })()")
    got = _go(run, tmp_path, _model(_ctx()), [dict(OPEN, eval=look)], vp)
    at = got["after"][0]["eval"]
    assert 0 <= at["top"] < 140 and at["bottom"] < at["vh"] / 3, at
    assert at["placeholder"] == "Search"
    for name in ("Stories", "Words", "Just for you", "They ask"):
        assert name in at["chips"], at["chips"]
    assert at["chips"][0] == "1 Intro"


def test_the_top_is_three_blocks_with_pay_and_notice_at_once(run, tmp_path, vp):
    look = ("(() => { const lp = document.querySelector('.lp'); const kids = [...lp.children];"
            " const first = kids.findIndex((x) => x.classList.contains('lp-part'));"
            " const head = document.querySelector('.lp-head').textContent;"
            " return {before: kids.slice(0, first).map((x) => x.className), head,"
            " top: Math.round(lp.querySelector('.lp-part').__drawnRect().top), vh: innerHeight}; })()")
    got = _go(run, tmp_path, _model(_ctx()), [dict(OPEN, eval=look)], vp)
    at = got["after"][0]["eval"]
    # The card's own actions, the head and the bar: nothing else before part 1.
    assert at["before"] == ["lp-head", "lp-bar"], at["before"]
    assert "If pay comes up:" in at["head"] and "Your notice: One month." in at["head"]
    assert "60 minutes; you talk for" in at["head"]
    assert "words a minute" not in at["head"] and "Likely to prompt" not in at["head"], at["head"]
    assert at["top"] < at["vh"], "part 1 starts on the first screen"


def test_a_term_on_a_wide_screen_opens_beside_the_column_and_nothing_moves(run, tmp_path):
    box = ("(() => { const c = document.querySelector('.lp').__drawnRect(); const p = document.querySelector('.lp-panel');"
           " const r = p.hidden ? null : p.__drawnRect();"
           " return {left: Math.round(c.left), right: Math.round(c.right), panel: r ? Math.round(r.left) : null}; })()")
    got = _go(run, tmp_path, _model(_ctx()), [dict(OPEN, eval=box),
        {"click": "forecasts: what it means", "within": "dialog.detail .lp-part", "eval": box}], WIDE)
    before, after = (a["eval"] for a in got["after"])
    assert (before["left"], before["right"]) == (after["left"], after["right"]), (before, after)
    assert after["panel"] >= after["right"], "the panel sits over the margin, never over the column"


def test_a_term_on_a_phone_is_a_sheet_over_a_dimmed_page(run, tmp_path):
    look = ("(() => { const s = document.querySelector('.lp-scrim'); const p = document.querySelector('.lp-panel');"
            " return {scrim: !s.hidden && s.checkVisibility(), opacity: Number(getComputedStyle(s).opacity),"
            " open: !p.hidden, edge: getComputedStyle(p).borderTopColor !== getComputedStyle(p).backgroundColor}; })()")
    for scheme in (None, "dark"):
        got = _go(run, tmp_path, _model(_ctx()), [OPEN,
            {"click": "forecasts: what it means", "within": "dialog.detail .lp-part", "eval": look},
            {"eval": "(() => { document.querySelector('.lp-scrim').click(); return 1; })()"},
            {"eval": look}], PHONE, scheme=scheme)
        shown, _tap, gone = (a["eval"] for a in got["after"][1:])
        assert shown["scrim"] and shown["opacity"] >= 0.5 and shown["open"] and shown["edge"], shown
        assert not gone["open"] and not gone["scrim"], "a tap on the dimmed page closes the sheet"


def test_the_answer_is_drawn_a_step_larger_than_the_text_around_it(run, tmp_path, vp):
    look = ("(() => { const px = (s) => parseFloat(getComputedStyle(document.querySelector(s)).fontSize);"
            " return {answer: px('#lpq-q1 .lp-simple'), beat: px('.lp-beat-t'), body: px('.lp-key')}; })()")
    at = _go(run, tmp_path, _model(_ctx()), [dict(OPEN, eval=look)], vp)["after"][0]["eval"]
    assert at["answer"] > at["body"] and at["answer"] > at["beat"], at


def test_the_brief_reads_likely_to_come_up_from_the_live_prep(run, tmp_path, vp):
    model = _model(_ctx())
    lv = next(iv for iv in model["interviews"] if iv["id"] == IV)["live"]
    assert lv["likely"] and set(lv["likely"]) == {q["id"] for q in lv["questions"]}
    order = {q["id"]: q["q"] for q in lv["questions"]}
    path = os.path.join(str(tmp_path), "page.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(app_page.standalone(app_page.render(model)))
    # The interview's own day, so the Brief's Today holds it.
    got = run("engine", html=path, viewport=vp, seed={}, fake={"canSend": "available"},
              clock="2026-10-28T08:00:00Z", steps=[{"hash": "brief", "eval":
                  "[...document.querySelectorAll('.bp-today .bp-qs li')].map((x) => x.textContent)"}])
    assert not got["errors"], got["errors"]
    said = got["after"][0]["eval"]
    assert said and order[lv["likely"][0]] in said[0], (said, order[lv["likely"][0]])
    assert "Likely to come up" in got["after"][0]["text"]


def test_an_interview_with_no_live_prep_reads_as_before(run, tmp_path, vp):
    m = _sample()
    got = _go(run, tmp_path, copy.deepcopy(m), [dict(OPEN, eval="document.querySelectorAll('dialog.detail .lp').length")], vp)
    assert got["after"][0]["eval"] == 0 and "Before you go in" in got["after"][0]["text"]
    assert json.dumps(m)  # the sample itself carries no live prep
