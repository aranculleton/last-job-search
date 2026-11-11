"""The live prep on the page: an interview's card opens it full screen, in the order the
interview runs.

The prep is the engine's own (`tools/interview_live.py`), built for the example person's
invented application and filled the way Claude fills it, then put on the sample page's
interview. It is laid out as the maintainer's call-prep page (2026-11-10). Each test taps it as
a person would, on a phone and on a wide screen: the parts in order, the one switch that flips
every answer and the switch that flips one, a "Likely to prompt" link and a chip that go where
they say and mark it, a term that opens and its Back, search through what to say, every answer
and follow-up, Open all and Close all, one way to practise, nothing wider than the screen, the
dark look, other kinds of sitting, and no script errors. Every person and employer is invented.
"""
from __future__ import annotations

import copy
import json
import os
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


REAL = os.path.join(ROOT, "tests", "fixtures", "interview_live_filled.json")
STAGE = "Second round"
FORMAT = "personal experience interview, live Python coding exercise, 60 minutes"


def _real_ctx():
    """The records of the invented second round the kept prep was written for."""
    ctx = _ctx(stage=STAGE, format_=FORMAT)
    ctx["bank"] = []  # the copy the prep was made on held no question asked there before
    return ctx


def _live(ctx=None):
    """A real prep, made once through the whole pipeline (2026-11-10): `interview_pack.py live`
    built it for an invented second round at the invented employer, a personal experience
    interview and a live Python coding exercise in one 60 minute sitting; the words were
    written as /interview Step 3b says, and `live --fill --write` kept it once every check
    passed. Here the engine builds the same round from the same records and takes those words
    back, so what the tests draw is what a person would see, and it must still pass."""
    ctx = _real_ctx()
    with open(REAL, encoding="utf-8") as fh:
        doc = L.merge(L.build(ctx), json.load(fh))
    assert L.problems(doc, ctx) == [], L.problems(doc, ctx)
    doc["checked"] = {"on": ctx["today"], "problems": 0, "drafts": len(L.drafts(doc))}
    return L.for_page(doc)


def _model(ctx=None):
    """The sample page, its interview the one the prep is for: the same employer, role, round
    and person in the head as in the prep under it."""
    m = _sample()
    for iv in m["interviews"]:
        if iv["id"] == IV:
            iv["live"] = _live()
            iv.update(company=iv["live"]["company"], role=iv["live"]["role"], next_stage=STAGE,
                      format="Video", **{"with": "Shirin Example, Head of Planning"})
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
Q1 = '[data-lpq="q1"]'
# Where a tap went, once its smooth scroll has brought it to the top of the screen.
IN_VIEW = ("(() => { const a = document.activeElement; if (!a || !a.classList.contains('lp-flash')) return false;"
           " const t = Math.round(a.__drawnRect().top); const still = window.__lpTop === t; window.__lpTop = t;"
           " return still && t >= -2 && t < innerHeight; })()")


def _ev(body):
    return "(() => { const vis = %s; %s })()" % (VISIBLE, body)


def _shaped_model(ctx, fmt):
    """The sample page with the interview's prep built for another kind of sitting, filled the
    way Claude fills it, every part given its words."""
    ctx = dict(ctx, format=fmt)
    doc = _fill(L.build(ctx))
    doc = L.finish(doc)
    doc["checked"] = {"on": ctx["today"], "problems": 0, "drafts": 0}
    m = _sample()
    for iv in m["interviews"]:
        if iv["id"] == IV:
            iv["live"] = L.for_page(doc)
    return m, doc


def test_the_parts_are_in_the_order_the_interview_runs(run, tmp_path, vp):
    ctx = _ctx()
    model = _model(ctx)
    lv = next(iv for iv in model["interviews"] if iv["id"] == IV)["live"]
    got = _go(run, tmp_path, model, [dict(OPEN, eval=_ev(
        "const d = document.querySelector('dialog.detail');"
        "return {full: d.classList.contains('full'), parts: [...d.querySelectorAll('.lp-part[data-lpp] .lp-part-h')].map((x) => x.textContent),"
        " cards: d.querySelectorAll('.lp-q[data-lpq]').length, chips: [...d.querySelectorAll('.lp-chips .btn')].map((x) => x.textContent),"
        " ids: [...d.querySelectorAll('.lp [id]')].map((x) => x.id).filter((x) => !x.startsWith('lp-int-larkspur-supply-')),"
        " wide: Math.round(d.__drawnRect().width), vw: innerWidth};"))], vp)
    seen = got["after"][0]["eval"]
    assert seen["full"] and seen["wide"] == seen["vw"], "the prep is full screen on every screen"
    titles = [p["title"] for p in lv["parts"]]
    assert seen["parts"] == titles
    # A chip to every part, then to the stories, the words and the notes.
    assert seen["cards"] == len(lv["questions"])
    assert seen["chips"] == ["%d %s" % (i + 1, p["short"]) for i, p in enumerate(lv["parts"])] + ["Stories", "Words", "Your notes"]
    # Every id carries the interview's, so two interviews' preps never share one.
    assert seen["ids"] == [], seen["ids"]
    text = got["after"][0]["text"]
    # Labels are drawn in small capitals, so they are read without their case.
    low = text.lower()
    assert "A personal experience interview and a technical interview in one sitting for the Demand Planning Analyst role" in text and "known to ask" in low
    assert "your notes, not for saying" in low and "Your stories" in text and "Every word, A to Z" in text
    # The timing is one line on its fold, the rest of it inside (the UX review, 2026-11-10, U-5).
    assert "Timing: 60 minutes in 5 parts" in text
    assert "One month" in text, "the notice period from the profile is in the notes"
    assert text.count("Draft") >= 2, "the draft is marked where it is, and said once at the top"


def test_the_switch_flips_every_answer_and_one_flips_back(run, tmp_path, vp):
    count = ("const d = document.querySelector('dialog.detail');"
             "return {detailed: [...d.querySelectorAll('.lp-detailed')].filter(vis).length,"
             " all: d.querySelectorAll('.lp-detailed').length, simple: [...d.querySelectorAll('.lp-simple')].filter(vis).length,"
             " first: vis(d.querySelector('%s > .lp-ans > .lp-detailed'))};" % Q1)
    got = _go(run, tmp_path, _model(_ctx()), [
        dict(OPEN, eval=_ev(count)),
        {"click": "Detailed", "role": "radio", "within": "dialog.detail .lp-all", "read": "dialog.detail", "eval": _ev(count)},
        {"click": "Simple", "role": "radio", "within": Q1 + " > .lp-ans > .lp-ans-top", "read": "dialog.detail", "eval": _ev(count)},
        {"click": "Simple", "role": "radio", "within": "dialog.detail .lp-all", "read": "dialog.detail", "eval": _ev(count)},
    ], vp)
    before, flipped, one, back = (a["eval"] for a in got["after"])
    assert before["detailed"] == 0 and before["all"] > 1
    assert flipped["detailed"] == flipped["all"], "one switch shows every detailed answer"
    assert one["detailed"] == flipped["all"] - 1 and not one["first"], "an answer's own switch flips that one back"
    assert back["detailed"] == 0, "the switch for all of them flips every one, the one flipped alone too"


def test_a_likely_to_prompt_link_goes_to_its_answer_and_marks_it(run, tmp_path, vp):
    got = _go(run, tmp_path, _model(_ctx()), [
        OPEN,
        {"click": "Full answer and follow-ups:", "within": "dialog.detail", "read": "dialog.detail",
         "ready": IN_VIEW,
         "eval": "(() => { const a = document.activeElement; const r = a.__drawnRect();"
                 " return {lpq: a.dataset.lpq || '', known: a.classList.contains('lp-q-known'), top: Math.round(r.top), vh: innerHeight}; })()"},
    ], vp)
    at = got["after"][1]["eval"]
    assert at["lpq"] and at["known"], at
    assert -2 <= at["top"] < at["vh"], "the answer is scrolled into view"


def test_a_chip_goes_to_its_part_and_the_words_open(run, tmp_path, vp):
    look = ("(() => { const a = document.activeElement; const r = a.__drawnRect();"
            " return {cls: a.className, tag: a.tagName, open: !!a.open, top: Math.round(r.top), vh: innerHeight}; })()")
    got = _go(run, tmp_path, _model(_ctx()), [
        OPEN,
        {"click": "4 Probes", "exact": True, "within": "dialog.detail .lp-chips", "ready": IN_VIEW, "eval": look},
        {"click": "Stories", "exact": True, "within": "dialog.detail .lp-chips", "ready": IN_VIEW, "eval": look},
        {"click": "Words", "exact": True, "within": "dialog.detail .lp-chips", "ready": IN_VIEW, "eval": look},
    ], vp)
    probes, stories, words = (a["eval"] for a in got["after"][1:])
    assert "lp-part" in probes["cls"] and 0 <= probes["top"] < probes["vh"], probes
    assert "lp-stories" in stories["cls"], stories
    assert words["tag"] == "DETAILS" and words["open"], "the A to Z opens where the chip lands"


def test_a_term_opens_and_back_returns(run, tmp_path, vp):
    panel = _ev("const p = document.querySelector('.lp-panel');"
                "return {open: vis(p), title: p.querySelector('.lp-panel-title').textContent,"
                " back: vis(p.querySelector('.lp-back')), text: p.textContent,"
                " box: (() => { const r = p.__drawnRect(); return [Math.round(r.left), Math.round(r.right), Math.round(r.bottom)]; })(), vw: innerWidth, vh: innerHeight};")
    got = _go(run, tmp_path, _model(_ctx()), [
        OPEN,
        {"click": "demand forecast: what it means", "within": "dialog.detail .lp-part", "eval": panel},
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


def test_a_term_in_a_follow_up_title_opens_without_shutting_its_fold(run, tmp_path):
    # A term button inside a <summary> fights the fold (SPEC section 5): a term in the panel
    # from the A to Z opens it, and the A to Z stays open behind it.
    got = _go(run, tmp_path, _model(_ctx()), [
        OPEN,
        {"open": "det:lp:%s:az" % IV},
        {"click": "Cross-dock: what it means", "within": "dialog.detail .lp-az", "eval": _ev(
            "return {open: vis(document.querySelector('.lp-panel')), az: document.querySelector('.lp-glossary').open};")},
    ], WIDE)
    at = got["after"][2]["eval"]
    assert at["open"] and at["az"], at


def test_search_finds_what_to_say_answers_and_follow_ups(run, tmp_path, vp):
    look = _ev("const d = document.querySelector('dialog.detail');"
               "return {found: d.querySelector('.lp-found').textContent,"
               " beats: [...d.querySelectorAll('.lp-beat')].filter(vis).length,"
               " cards: [...d.querySelectorAll('.lp-q')].filter(vis).map((x) => x.dataset.lpq || x.dataset.lpa || 'story'),"
               " once: [...d.querySelectorAll('.lp-part-follow > .lp-kids > .lp-f')].filter(vis).map((x) => x.closest('.lp-part').dataset.lpp),"
               " parts: [...d.querySelectorAll('.lp-part')].filter(vis).length, open: [...d.querySelectorAll('.lp-part details[open]')].length};")
    fill = lambda q: {"eval": "(() => { const f = document.querySelector('.lp-search input'); f.value = %r; f.dispatchEvent(new Event('input')); return 1; })()" % q}  # noqa: E731
    got = _go(run, tmp_path, _model(_ctx()), [
        dict(OPEN, eval=look),
        dict(fill("error by distribution centre"), read="dialog.detail"), {"eval": look},
        dict(fill("its users can check it themselves")), {"eval": look},
        dict(fill("new lines with little history")), {"eval": look},
        dict(fill("zebra crossings")), {"eval": look},
        dict(fill("")), {"eval": look},
    ], vp)
    ev = [a.get("eval") for a in got["after"]]
    before, narr, detailed, follow, none, cleared = ev[0], ev[2], ev[4], ev[6], ev[8], ev[10]
    # What to say first and the answer that says it are found; the rest steps aside.
    assert narr["beats"] == 1 and narr["cards"] and narr["found"].endswith("found"), narr
    # A detailed answer, hidden behind Simple, is still found.
    assert detailed["cards"] and detailed["beats"] == 0, detailed
    # A follow-up two deep is found and its folds open. It is one said once for its part, after
    # any story there, since the screen review of 2026-11-11 (row 35): it stood under q1.
    q1_part = next(q["part"] for q in _live()["questions"] if q["id"] == "q1")
    assert follow["cards"] == [] and follow["once"] == [q1_part] and follow["open"] >= 2, follow
    assert none["found"] == "Nothing found: try fewer words" and none["parts"] == 0
    assert cleared["parts"] == before["parts"] and cleared["beats"] == before["beats"] and not cleared["found"]


# Search, Open all and Close all are folded under Tools, beside the answers switch (the UX
# review, 2026-11-10, U-5: the first phone screen was controls before anything to say).
TOOLS = {"open": "lp-tools"}


def test_open_all_and_close_all(run, tmp_path, vp):
    n = "[...document.querySelectorAll('.lp-part details')].filter((d) => d.open).length + '/' + document.querySelectorAll('.lp-part details').length"
    got = _go(run, tmp_path, _model(_ctx()), [
        OPEN, dict(TOOLS, eval=n),
        {"click": "Open all", "exact": True, "within": "dialog.detail .lp-tools", "eval": n},
        {"click": "Close all", "exact": True, "within": "dialog.detail .lp-tools", "eval": n},
    ], vp)
    before, opened, shut = (a["eval"] for a in got["after"][1:])
    total = before.split("/")[1]
    assert before == "0/" + total and opened == total + "/" + total and shut == "0/" + total and int(total) > 1


def test_practice_is_trying_an_answer_first_then_looking(run, tmp_path, vp):
    # The maintainer called a Start on every card and a second button to hide the answers
    # cluttered (2026-11-10); the UX review the same day (U-4) found trying an answer and then
    # checking it beats rereading. So it is one more side of the one switch, Hidden, and only
    # then does each answer show "Show the answer"; the one pill is still Practise with Claude.
    look = _ev("const d = document.querySelector('dialog.detail');"
               "return {pills: [...d.querySelectorAll('.lp-head .card-actions .btn')].map((b) => b.textContent.trim()),"
               " shown: [...d.querySelectorAll('.lp-reveal')].filter(vis).length,"
               " all: [...d.querySelectorAll('.lp-ans')].filter((a) => !a.closest('details:not([open])')).length,"
               " simple: [...d.querySelectorAll('.lp-simple')].filter(vis).length, detailed: [...d.querySelectorAll('.lp-detailed')].filter(vis).length,"
               " first: vis(d.querySelector('%s > .lp-ans > .lp-simple')), sides: [...d.querySelectorAll('.lp-all .seg-opt')].map((b) => b.textContent),"
               " inTop: [...d.querySelectorAll('.lp-reveal')].every((b) => b.parentElement.classList.contains('lp-ans-top')),"
               " beats: [...d.querySelectorAll('.lp-beat')].filter(vis).length, sayShow: [...d.querySelectorAll('.lp-narr-show')].filter(vis).length,"
               " open: vis(d.querySelector('.lp-glance-open'))};" % Q1)
    got = _go(run, tmp_path, _model(_ctx()), [
        dict(OPEN, eval=look),
        {"click": "Hidden", "role": "radio", "within": "dialog.detail .lp-all", "eval": look},
        {"click": "Show the answer", "exact": True, "within": Q1 + " > .lp-ans", "eval": look},
        {"click": "Simple", "role": "radio", "within": "dialog.detail .lp-all", "eval": look},
    ], vp)
    before, hidden, one, back = (a["eval"] for a in got["after"])
    assert before["pills"] == ["Practise with Claude"] and before["shown"] == 0
    assert before["sides"] == ["Simple", "Detailed", "Hidden"], before["sides"]
    assert hidden["simple"] == 0 and hidden["detailed"] == 0 and hidden["shown"] == hidden["all"] > 1, hidden
    # Show the answer sits beside Say, never as a bar across the answer (d48b3379), and what
    # to say first, at a glance and in each part, waits behind its own Show too (the review of
    # the fixes, 2026-11-10: Part 1's lines still gave the opening answer away).
    assert hidden["inTop"] and before["beats"] > 0 and before["open"], (hidden, before)
    assert hidden["beats"] == 0 and hidden["sayShow"] > 0 and not hidden["open"], hidden
    assert one["first"] and one["simple"] == 1 and one["shown"] == hidden["all"] - 1, one
    assert back["shown"] == 0 and back["simple"] == back["all"] and back["beats"] == before["beats"], back


def _soon(days):
    """The sample page, its interview with the live prep `days` days away (the page's day is
    Sunday 25 October)."""
    m = _model(_ctx())
    for iv in m["interviews"]:
        if iv["id"] == IV:
            iv["when"] = "2026-10-%02dT13:00:00Z" % (25 + days)
    return m


def test_in_the_days_before_practice_is_on_the_interviews_card(run, tmp_path, vp):
    # The UX review of 2026-11-10 (U-4): Practise with Claude was under More, and nothing said
    # to practise. Two days before and the day before, the card says to practise three
    # questions today and its first pill opens the prep with the answers hidden, at the first
    # question likely to come up; three days before and on the day itself, reading leads and
    # the calendar is beside it.
    card = ("(() => { const c = [...document.querySelectorAll('#main [data-item]')].find((x) => x.dataset.item === 'soon:%s');"
            " return c ? {pills: [...c.querySelectorAll(':scope > .card-actions > .btn')].map((b) => b.textContent.trim()),"
            " text: c.textContent} : null; })()" % IV)
    opened = _ev("const d = document.querySelector('dialog.detail'); const a = document.activeElement;"
                 " return {simple: [...d.querySelectorAll('.lp-simple')].filter(vis).length, shown: [...d.querySelectorAll('.lp-reveal')].filter(vis).length,"
                 " at: a && a.dataset ? a.dataset.lpq || '' : ''};")
    seen = {}
    for days in (0, 1, 2, 3):
        steps = [{"hash": "todo", "eval": card}]
        if days == 1:
            steps.append({"click": "Practise 3 questions", "within": "#main", "read": "dialog.detail",
                          "ready": "!!document.querySelector('.lp-flash')", "eval": opened})
        got = _go(run, tmp_path, _soon(days), steps, vp)
        seen[days] = [a["eval"] for a in got["after"]]
    assert seen[0][0]["pills"][0] == "Read your prep" and "Practise with Claude" not in seen[0][0]["pills"], seen[0]
    for days in (1, 2):
        at = seen[days][0]
        assert at["pills"] == ["Practise 3 questions", "Read your prep"], (days, at["pills"])
        assert "Today: practise 3 questions, about 10 minutes." in at["text"], at["text"]
    assert seen[3][0]["pills"] == ["Read your prep", "Add to calendar"], seen[3][0]["pills"]
    assert "practise 3 questions" not in seen[3][0]["text"]
    drill = seen[1][1]
    assert drill["simple"] == 0 and drill["shown"] > 0 and drill["at"], drill
    # Hidden is for that practice only: Read your prep afterwards, the interview morning
    # included, opens with every answer showing (the review of the fixes, 2026-11-10).
    again = _go(run, tmp_path, _soon(1), [
        {"hash": "todo"},
        {"click": "Practise 3 questions", "within": "#main", "read": "dialog.detail"},
        {"eval": "(() => { document.querySelector('[data-k=detail-back]').click(); return 1; })()"},
        {"click": "Read your prep", "within": "#main", "read": "dialog.detail", "eval": opened}], vp)
    assert again["after"][3]["eval"]["simple"] > 0 and again["after"][3]["eval"]["shown"] == 0, again["after"][3]["eval"]


def test_nothing_is_wider_than_a_phone_and_the_dark_look_draws(run, tmp_path):
    wide = ("(() => { const d = document.querySelector('dialog.detail'); const b = d.querySelector('.detail-body');"
            # The chips scroll sideways inside their own row on a phone (the screen review,
            # 2026-11-11): one past its edge is inside the row, never wider than the screen.
            " const over = [...d.querySelectorAll('.lp *')].filter((e) => e.getClientRects().length && !e.closest('[hidden]') && !e.parentElement.closest('.lp-chips') && e.__drawnRect().right > innerWidth + 1).map((e) => e.className).slice(0, 5);"
            " const bg = getComputedStyle(d).backgroundColor.match(/\\d+/g).slice(0, 3).map(Number);"
            " return {sideways: b.scrollWidth > b.clientWidth + 1, over, light: (bg[0] + bg[1] + bg[2]) / 3}; })()")
    steps = [dict(OPEN), TOOLS, {"click": "Open all", "exact": True, "within": "dialog.detail .lp-tools", "eval": wide}]
    light = _go(run, tmp_path, _model(_ctx()), steps, PHONE)["after"][2]["eval"]
    assert not light["sideways"] and light["over"] == [], light
    dark = _go(run, tmp_path, _model(_ctx()), steps, PHONE, scheme="dark")["after"][2]["eval"]
    assert not dark["sideways"] and dark["over"] == [], dark
    assert dark["light"] < 100 < light["light"], "the dark look is dark and the light look light"


def test_the_smoke_test_at_phone_width(run, tmp_path):
    # The call-prep page's own smoke test (its smoke-test.cjs), at 390 pixels: no script
    # errors, no sideways scroll, a term and a term inside it with Back, the switch for all
    # and one answer's own.
    phone = {"width": 390, "height": 844}
    probe = _ev("const d = document.querySelector('dialog.detail'); const b = d.querySelector('.detail-body'); const p = d.querySelector('.lp-panel');"
                "return {sideways: b.scrollWidth > b.clientWidth + 1 || document.documentElement.scrollWidth > innerWidth + 1,"
                " panel: vis(p) ? p.querySelector('.lp-panel-title').textContent : '', back: vis(p.querySelector('.lp-back')),"
                " detailed: [...d.querySelectorAll('.lp-detailed')].filter(vis).length, all: d.querySelectorAll('.lp-detailed').length,"
                " terms: d.querySelectorAll('.lp-term').length, cards: d.querySelectorAll('.lp-q').length, follows: d.querySelectorAll('.lp-f').length};")
    got = _go(run, tmp_path, _model(_ctx()), [
        dict(OPEN, eval=probe),
        {"click": "demand forecast: what it means", "within": "dialog.detail .lp-part", "eval": probe},
        {"click": "Cross-dock: what it means", "within": ".lp-panel", "eval": probe},
        {"click": "Close", "exact": True, "within": ".lp-panel"},
        {"click": "Detailed", "role": "radio", "within": "dialog.detail .lp-all", "eval": probe},
        {"click": "Simple", "role": "radio", "within": Q1 + " > .lp-ans > .lp-ans-top", "eval": probe},
    ], phone)
    start, term, deeper, _close, detailed, one = (a.get("eval") for a in got["after"])
    assert not start["sideways"] and start["terms"] > 0 and start["cards"] > 0 and start["follows"] > 0
    assert term["panel"] == "Demand forecast" and not term["back"]
    assert deeper["panel"] == "Cross-dock" and deeper["back"]
    assert detailed["detailed"] == detailed["all"] and one["detailed"] == detailed["all"] - 1


def _bg(sel):
    return "getComputedStyle(document.querySelector(%r)).backgroundColor" % sel


def test_the_chosen_side_of_each_switch_shows(run, tmp_path, vp):
    # Simple and Detailed looked the same, at the top and on every answer: the page styled
    # aria-pressed and the switch set aria-checked.
    one = Q1 + " > .lp-ans > .lp-ans-top"
    look = ("(() => { const on = (s) => getComputedStyle(document.querySelector(s)).backgroundColor;"
            " return {top: [on('.lp-all [data-v=simple]'), on('.lp-all [data-v=detailed]')],"
            " one: [on('%s [data-v=simple]'), on('%s [data-v=detailed]')]}; })()" % (one, one))
    # Read once the chosen sides have finished their fade, never part way through it.
    settled = ("[...document.querySelectorAll('.lp-all [aria-checked=true], %s [aria-checked=true]')]"
               ".every((b) => /^rgb\\(/.test(getComputedStyle(b).backgroundColor))" % one)
    got = _go(run, tmp_path, _model(_ctx()), [dict(OPEN, ready=settled, eval=look),
        {"click": "Detailed", "role": "radio", "within": "dialog.detail .lp-all",
         "ready": "document.querySelector('.lp-all [data-v=detailed]').getAttribute('aria-checked') === 'true' && " + settled, "eval": look}], vp)
    before, after = (a["eval"] for a in got["after"])
    for pair in (before["top"], before["one"], after["top"], after["one"]):
        assert pair[0] != pair[1], pair
    assert before["top"] == after["top"][::-1], "the chosen side moves with the choice"


def test_the_top_is_the_head_the_timing_and_what_they_ask(run, tmp_path, vp):
    look = ("(() => { const lp = document.querySelector('.lp'); const kids = [...lp.children];"
            " const first = kids.findIndex((x) => x.classList.contains('lp-part'));"
            " return {before: kids.slice(0, first).map((x) => x.className),"
            " head: document.querySelector('.lp-head').textContent, notes: document.querySelector('.lp-notes').textContent,"
            " sticky: [...lp.querySelectorAll('*')].filter((x) => ['sticky', 'fixed'].includes(getComputedStyle(x).position) && x.checkVisibility()).length,"
            " pills: [...lp.querySelectorAll('.lp-head .card-actions .btn')].map((x) => x.textContent.trim()),"
            " search: lp.querySelector('.lp-search input').placeholder}; })()")
    got = _go(run, tmp_path, _model(_ctx()), [dict(OPEN, eval=look)], vp)
    at = got["after"][0]["eval"]
    # The head, with what to say at a glance in it, then the timing folded to a line, then part 1
    # (the UX review, 2026-11-10, U-5).
    assert at["before"] == ["lp-head", "lp-f lp-timing"], at["before"]
    assert "Practise with Claude" in at["head"] and "At a glance" in at["head"] and "Open all" in at["head"]
    # One pill on the prep: Update my prep and the calendar stay on the card in Coming up.
    assert at["pills"] == ["Practise with Claude"], at["pills"]
    assert at["search"] == "Search questions and answers"
    # Nothing stays on the screen over the reading: no bar that follows it down.
    assert at["sticky"] == 0
    # The pay and the notice are the person's own notes, last, never on the head.
    assert "If pay comes up:" in at["notes"] and "Your notice: One month." in at["notes"]
    assert "If pay comes up" not in at["head"]


def test_a_term_on_a_wide_screen_opens_beside_the_column_and_nothing_moves(run, tmp_path):
    box = ("(() => { const c = document.querySelector('.lp').__drawnRect(); const p = document.querySelector('.lp-panel');"
           " const r = p.hidden ? null : p.__drawnRect();"
           " return {left: Math.round(c.left), right: Math.round(c.right), panel: r ? Math.round(r.left) : null}; })()")
    got = _go(run, tmp_path, _model(_ctx()), [dict(OPEN, eval=box),
        {"click": "demand forecast: what it means", "within": "dialog.detail .lp-part", "eval": box}], WIDE)
    before, after = (a["eval"] for a in got["after"])
    assert (before["left"], before["right"]) == (after["left"], after["right"]), (before, after)
    assert after["panel"] >= after["right"], "the panel sits over the margin, never over the column"


def test_a_term_on_a_phone_is_a_sheet_over_a_dimmed_page(run, tmp_path):
    look = ("(() => { const s = document.querySelector('.lp-scrim'); const p = document.querySelector('.lp-panel');"
            " return {scrim: !s.hidden && s.checkVisibility(), opacity: Number(getComputedStyle(s).opacity),"
            " open: !p.hidden, edge: getComputedStyle(p).borderTopColor !== getComputedStyle(p).backgroundColor}; })()")
    for scheme in (None, "dark"):
        got = _go(run, tmp_path, _model(_ctx()), [OPEN,
            {"click": "demand forecast: what it means", "within": "dialog.detail .lp-part", "eval": look},
            {"eval": "(() => { document.querySelector('.lp-scrim').click(); return 1; })()"},
            {"eval": look}], PHONE, scheme=scheme)
        shown, _tap, gone = (a["eval"] for a in got["after"][1:])
        assert shown["scrim"] and shown["opacity"] >= 0.5 and shown["open"] and shown["edge"], shown
        assert not gone["open"] and not gone["scrim"], "a tap on the dimmed page closes the sheet"


def test_a_technical_prep_opens_in_its_own_stages(run, tmp_path, vp):
    model, doc = _shaped_model(_ctx(), "live SQL and Python, 45 minutes")
    look = _ev("return {parts: [...document.querySelectorAll('.lp-part[data-lpp] .lp-part-h')].map((x) => x.textContent),"
               " lede: document.querySelector('.lp-lede').textContent, sideways: (() => { const b = document.querySelector('dialog.detail .detail-body'); return b.scrollWidth > b.clientWidth + 1; })()};")
    at = _go(run, tmp_path, model, [dict(OPEN, eval=look)], vp)["after"][0]["eval"]
    assert at["parts"] == ["Warm-up, and your background", "A problem, worked aloud", "The follow-up probes and trade-offs",
                           "Your questions for them"]
    assert at["lede"].startswith("A technical interview") and not at["sideways"]


def test_a_personal_story_and_live_coding_open_as_one_sitting(run, tmp_path, vp):
    model, doc = _shaped_model(dict(_ctx(), stage="Second round"), "personal experience, technical coding (HackerRank, Python)")
    assert doc["shape"] == "combined:personal+technical"
    look = _ev("return {parts: [...document.querySelectorAll('.lp-part[data-lpp] .lp-part-h')].map((x) => x.textContent),"
               " chips: [...document.querySelectorAll('.lp-chips .btn')].map((x) => x.textContent),"
               " timing: document.querySelector('.lp-timing').textContent};")
    at = _go(run, tmp_path, model, [dict(OPEN, eval=look)], vp)["after"][0]["eval"]
    assert at["parts"] == [p["title"] for p in doc["parts"]]
    assert at["chips"][:5] == ["1 Intro", "2 Your story", "3 The problem", "4 Probes", "5 Your questions"]
    assert "in 5 parts" in at["timing"]
    # A part's title read inside a sentence starts small: "The longest stop is a problem, ...".
    assert "stop is A " not in at["timing"] and "longest stop is a problem, worked aloud" in at["timing"], at["timing"]


def test_a_guessed_kind_says_so_and_is_one_tap_from_the_right_one(run, tmp_path, vp):
    # The review of 2026-11-10 (R1-2): a guessed kind opened a box to type in. Each kind is one
    # tap, and the prep is made again as that kind; Something else is for words of your own
    # ("a personal experience interview, then live coding").
    model = _model(_ctx())
    lv = next(iv for iv in model["interviews"] if iv["id"] == IV)["live"]
    lv["assumed"] = "a consulting firm's rounds after the screen are usually a case and a personal experience interview together"
    got = _go(run, tmp_path, model, [OPEN,
        {"click": "Not this kind of interview?", "exact": True, "within": "dialog.detail .lp-glance", "read": "dialog.sheet"},
        {"click": "A technical or coding interview", "exact": True, "within": "dialog.sheet"}], vp)
    assert "a best guess" in got["after"][0]["text"].lower()
    assert "a consulting firm's rounds after the screen are usually" in got["after"][0]["text"].lower()
    sheet = got["after"][1]["text"]
    for kind in ("A recruiter or HR screen", "A hiring manager interview", "A technical or coding interview",
                 "A test you take alone", "A case interview", "A personal experience interview", "Something else"):
        assert kind in sheet, (kind, sheet[:400])
    work = [w for w in got["after"][2]["work"] if w.get("kind") == "prep"]
    assert work and work[-1]["args"]["format"] == "a technical interview with live coding", work
    assert work[-1]["args"]["interview"] == IV and "technical interview" in work[-1]["args"]["note"]
    # Something else is the box to say it in your own words.
    other = _go(run, tmp_path, model, [OPEN,
        {"click": "Not this kind of interview?", "exact": True, "within": "dialog.detail .lp-glance"},
        {"click": "Something else", "exact": True, "within": "dialog.sheet", "read": "dialog.sheet"}], vp)
    assert "Anything you know about this interview?" in other["after"][2]["text"]


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


def test_it_opens_on_what_to_say_at_a_glance_with_the_controls_folded(run, tmp_path, vp):
    # The UX review of 2026-11-10 (U-5): the first phone screen was a 43-word introduction,
    # search, Open all, Close all, the switch, eight chips and a Timing box before Part 1.
    # It opens on the line to open with, what they are known to ask and two questions to ask
    # them; search and the folds wait under Tools; a simple answer is a sentence a line.
    look = _ev("const d = document.querySelector('dialog.detail'); const g = d.querySelector('.lp-glance');"
               " const top = (x) => Math.round(x.__drawnRect().top);"
               " return {glance: g && g.textContent, glanceIn: !!g && g.__drawnRect().bottom <= innerHeight + 1,"
               " beforePart: !!g && top(g) < top(d.querySelector('.lp-part')),"
               " search: vis(d.querySelector('.lp-search input')), openAll: [...d.querySelectorAll('.lp-tools .btn')].some(vis),"
               " lede: d.querySelector('.lp-lede').textContent.split(/\\s+/).length,"
               " lines: d.querySelectorAll('%s > .lp-ans > .lp-simple > p').length,"
               " detailedLines: d.querySelectorAll('%s > .lp-ans > .lp-detailed').length,"
               " timingOpen: d.querySelector('.lp-timing').open,"
               " left: Math.round(d.querySelector('.detail-title').__drawnRect().left)};" % (Q1, Q1))
    got = _go(run, tmp_path, _model(_ctx()), [dict(OPEN, eval=look), dict(TOOLS, eval=look)], vp)
    at, tools = (a["eval"] for a in got["after"])
    assert "Open with" in at["glance"] and "I'm an operations analyst" in at["glance"], at["glance"]
    assert "Known to ask" in at["glance"] and "How do you get depot managers to trust a forecast?" in at["glance"]
    assert "Ask them" in at["glance"] and "cross-dock in Warrington" in at["glance"]
    assert at["beforePart"] and (at["glanceIn"] or vp is not PHONE), "the glance is on the first screen"
    # On a phone the words start 16px from its edge, as everywhere on the page: the full-screen
    # body's empty side columns once added their gap as more padding (2026-11-11).
    assert vp is not PHONE or at["left"] == 16, at["left"]
    assert not at["search"] and not at["openAll"] and not at["timingOpen"], at
    assert tools["search"] and tools["openAll"], "Tools opens search, Open all and Close all"
    assert at["lede"] <= 30, at["lede"]
    assert at["lines"] >= 2 and at["detailedLines"] == 1


def test_on_a_phone_who_asks_sits_over_the_question_and_the_tools_keep_one_row(run, tmp_path, vp):
    # The review of 2026-11-10 (R1-11): at 390 pixels the who-asks pill sat inline, so a title
    # broke after a word or two ("Walk me / through a project end to end."), and Close all fell
    # onto a row of its own under the search box.
    look = ("(() => { const out = []; for (const h4 of document.querySelectorAll('dialog.detail .lp-q[data-lpq] .lp-q-q')) {"
            " const pill = h4.querySelector('.lp-who'); const tn = [...h4.childNodes].filter((n) => n.nodeType === 3 && n.textContent.trim()).pop();"
            " if (!pill || !tn) continue; const at = tn.textContent.search(/\\S/); const r = document.createRange(); r.setStart(tn, at); r.setEnd(tn, at + 1);"
            " out.push({below: r.getBoundingClientRect().top >= pill.getBoundingClientRect().bottom - 1}); }"
            " const b = [...document.querySelectorAll('dialog.detail .lp-tools .btn')].map((x) => Math.round(x.getBoundingClientRect().top));"
            " return {below: out.map((x) => x.below), tools: b}; })()")
    got = _go(run, tmp_path, _model(_ctx()), [OPEN, dict(TOOLS, eval=look)], vp)
    at = got["after"][1]["eval"]
    assert at["below"] and len(set(at["tools"])) == 1, at
    if vp is PHONE:
        assert all(at["below"]), "on a phone who asks sits on its own line, over the question"
    else:
        assert not any(at["below"]), "on a wide screen who asks stays inline, before the question"


def test_a_test_taken_alone_reads_as_a_test_and_a_day_in_hours(run, tmp_path, vp):
    # A test with nobody in the room has nothing to say first and no talk to time; a day of
    # interviews is said in hours (2026-11-10).
    model, doc = _shaped_model(dict(_ctx(), stage="Online assessment"), "HackerRank, 90 minutes")
    look = _ev("const d = document.querySelector('dialog.detail');"
               "return {labels: [...d.querySelectorAll('.lp-narr > .lp-lbl')].map((x) => x.textContent),"
               " eyebrows: [...d.querySelectorAll('.lp-eyebrow')].map((x) => x.textContent).join(' | '),"
               " lede: d.querySelector('.lp-lede').textContent, glance: d.querySelector('.lp-glance').textContent};")
    at = _go(run, tmp_path, model, [dict(OPEN, eval=look)], vp)["after"][0]["eval"]
    assert at["labels"] and "Say first" not in at["labels"] and set(at["labels"]) == {"Keep in mind"}, at["labels"]
    assert "you talk" not in at["eyebrows"].lower(), at["eyebrows"]
    assert "90 minutes" in at["lede"] and "Before you start" in at["glance"] and "Ask them" not in at["glance"]
    day, _doc = _shaped_model(dict(_ctx(), stage="Superday"), "")
    lede = _go(run, tmp_path, day, [dict(OPEN, eval=_ev("return document.querySelector('.lp-lede').textContent;"))], vp)["after"][0]["eval"]
    assert "3 hours in 6 parts" in lede, lede


def test_only_the_stories_a_question_is_answered_with_are_shown(run, tmp_path, vp):
    # The night-before run (2026-11-10): a test taken alone and a superday showed all four
    # stories under "Each told once, from the questions it answers", with no question in them.
    look = _ev("const d = document.querySelector('dialog.detail');"
               "return {stories: [...d.querySelectorAll('.lp-story')].map((s) => s.querySelectorAll('.lp-hook').length),"
               " chip: [...d.querySelectorAll('.lp-chips .btn')].some((b) => b.textContent === 'Stories')};")
    alone, _doc = _shaped_model(dict(_ctx(), stage="Online assessment"), "HackerRank, 90 minutes")
    at = _go(run, tmp_path, alone, [dict(OPEN, eval=look)], vp)["after"][0]["eval"]
    assert at == {"stories": [], "chip": False}, at
    real = _go(run, tmp_path, _model(_ctx()), [dict(OPEN, eval=look)], vp)["after"][0]["eval"]
    assert real["stories"] and all(n > 0 for n in real["stories"]) and real["chip"], real


def test_on_a_practice_day_coming_up_and_to_do_lead_with_the_same_step(run, tmp_path, vp):
    # The review of the fixes (2026-11-10): on practice days To do led with Practise 3
    # questions while Coming up's row led with Read your prep.
    todo = ("(() => { const c = [...document.querySelectorAll('#main [data-item]')].find((x) => x.dataset.item === 'soon:%s');"
            " return c ? c.querySelector('.card-actions > .btn').textContent.trim() : null; })()" % IV)
    row = "(() => { const b = document.querySelector('#main .up-prep .btn'); return b ? b.textContent.trim() : null; })()"
    for days, lead in ((1, "Practise 3 questions"), (3, "Read your prep")):
        got = _go(run, tmp_path, _soon(days), [{"hash": "todo", "eval": todo}, {"hash": "interviews", "eval": row}], vp)
        assert [a["eval"] for a in got["after"]] == [lead, lead], (days, [a["eval"] for a in got["after"]])


def test_a_term_is_a_quiet_dotted_word_that_wraps_with_its_sentence(run, tmp_path, vp):
    # A red dotted line under "demand forecast", "SKUs" and "dbt" read as a spelling mistake,
    # and a term drawn as a button never broke across lines, so a long one left its line short
    # (the screen review, 2026-11-11). The line is the words' own muted tone, and the term is
    # inline, kept a control for a keyboard and a screen reader.
    look = _ev("const t = [...document.querySelectorAll('dialog.detail .lp-part .lp-term')].filter(vis);"
               " const probe = document.createElement('span'); probe.style.color = 'var(--mark)'; document.body.appendChild(probe);"
               " const mark = getComputedStyle(probe).color; probe.remove();"
               " return {n: t.length, mark, colours: [...new Set(t.map((e) => getComputedStyle(e).textDecorationColor))],"
               " display: [...new Set(t.map((e) => getComputedStyle(e).display))], roles: [...new Set(t.map((e) => e.getAttribute('role') || e.tagName))],"
               " tab: t.every((e) => e.tabIndex === 0)};")
    got = _go(run, tmp_path, _model(_ctx()), [dict(OPEN, eval=look),
        {"eval": "(() => { const t = document.querySelector('dialog.detail .lp-part .lp-term'); t.focus(); t.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', bubbles: true})); return !document.querySelector('.lp-panel').hidden; })()"}], vp)
    seen, opened = got["after"][0]["eval"], got["after"][1]["eval"]
    assert seen["n"] > 0 and seen["mark"] not in seen["colours"], seen
    assert seen["display"] == ["inline"] and seen["roles"] == ["button"] and seen["tab"], seen
    assert opened is True, "Enter opens a term, as a button's does"


def test_on_a_phone_the_chips_are_one_row_and_tools_sit_beside_the_answers_switch(run, tmp_path):
    # Eight chips over three rows, then All answers, then Tools on a row of its own: more than
    # a screen before Part 1 on a phone (the screen review, 2026-11-11). The chips are one row
    # that scrolls sideways inside itself, and Tools shares the switch's row.
    look = _ev("const d = document.querySelector('dialog.detail');"
               " const chips = [...d.querySelectorAll('.lp-chips .btn')].filter(vis).map((b) => Math.round(b.__drawnRect().top));"
               " const sw = d.querySelector('.lp-global .segctl, .lp-global [role=radiogroup]'), tools = d.querySelector('.lp-toolfold-sum');"
               " const mid = (e) => { const r = e.__drawnRect(); return (r.top + r.bottom) / 2; };"
               " return {rows: new Set(chips).size, n: chips.length, sideways: document.documentElement.scrollWidth > innerWidth || d.scrollWidth > d.clientWidth,"
               " tools: Math.round(Math.abs(mid(sw) - mid(tools)))};")
    got = _go(run, tmp_path, _model(_ctx()), [dict(OPEN, eval=look)], PHONE)
    seen = got["after"][0]["eval"]
    assert seen["n"] >= 6 and seen["rows"] == 1 and not seen["sideways"], seen
    assert seen["tools"] <= 4, seen
