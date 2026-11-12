"""The live prep on the page: an interview's card opens it full screen, in the order the
interview runs.

The prep is the engine's own (`tools/interview_live.py`), built for the example person's
invented application and filled the way Claude fills it, then put on the sample page's
interview. It is laid out as the maintainer's call-prep page (2026-11-10). Each test taps it as
a person would, on a phone and on a wide screen: the parts in order, every answer as a script and
as points at once with nothing to open, the follow-ups as choices three deep with the way back,
a "Likely to prompt" link and a chip that go where they say and mark it, a term that opens and
its Back, find in the bar that stays at the top, one way to practise, nothing wider than the
screen, the dark look, other kinds of sitting, and no script errors. Every person and employer
is invented.
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


def _go(run, tmp_path, model, steps, vp, scheme=None, touch=False):
    path = os.path.join(str(tmp_path), "page.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(app_page.standalone(app_page.render(model)))
    got = run("engine", html=path, viewport=vp, steps=steps, seed={}, fake={"canSend": "available"},
              **({"scheme": scheme} if scheme else {}), **({"touch": True} if touch else {}))
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
        " cards: d.querySelectorAll('.lp-q[data-lpq]').length, chips: [...d.querySelectorAll('.lp-chips .btn:not(.lp-lead)')].map((x) => x.textContent),"
        " ids: [...d.querySelectorAll('.lp [id]')].map((x) => x.id).filter((x) => !x.startsWith('lp-int-larkspur-supply-')),"
        " bar: d.querySelector('.lp-bar').getAttribute('aria-label'), drafts: (d.querySelector('.lp-drafts') || {}).textContent || '',"
        " wide: Math.round(d.__drawnRect().width), vw: innerWidth};"))], vp)
    seen = got["after"][0]["eval"]
    assert seen["full"] and seen["wide"] == seen["vw"], "the prep is full screen on every screen"
    titles = [p["title"] for p in lv["parts"]]
    assert seen["parts"] == titles
    # A chip to every part, then to the stories and the notes.
    assert seen["cards"] == len(lv["questions"])
    assert seen["chips"] == ["%d %s" % (i + 1, p["short"]) for i, p in enumerate(lv["parts"])] + ["Stories", "Your notes"]
    # Every id carries the interview's, so two interviews' preps never share one.
    assert seen["ids"] == [], seen["ids"]
    text = got["after"][0]["text"]
    # Labels are drawn in small capitals, so they are read without their case.
    low = text.lower()
    assert "known to ask" in low
    assert "your notes, not for saying" in low and "Your stories" in text and "Every word, A to Z" not in text
    # The timing is the bar's name for a screen reader; nothing on the screen is folded to hold it.
    assert seen["bar"].startswith("60 minutes in 5 parts"), seen["bar"]
    assert "One month" in text, "the notice period from the profile is in the notes"
    assert "Draft" in text and "3 answers are drafts" in seen["drafts"], "the drafts are marked where they are, and said once at the top"


def test_every_answer_is_a_script_and_points_at_once_and_one_tap_flips_which_leads(run, tmp_path, vp):
    # The maintainer, 2026-11-11: Simple and Detailed were nearly the same answer, Simple just
    # Detailed in bullets, and a switch was one more thing to find mid-call. Both show, always;
    # which comes first is one tap, kept on this device.
    look = _ev("const d = document.querySelector('dialog.detail'); const a = d.querySelector('%s > .lp-ans');"
               " const top = (s) => Math.round(a.querySelector(s).__drawnRect().top);"
               "return {script: [...d.querySelectorAll('.lp-script')].filter(vis).length, scripts: d.querySelectorAll('.lp-script').length,"
               " points: [...d.querySelectorAll('.lp-cues')].filter(vis).length, all: d.querySelectorAll('.lp-cues').length,"
               " cuesFirst: top('.lp-cues') < top('.lp-script'), lead: d.querySelector('.lp').dataset.lead,"
               " label: d.querySelector('.lp-lead').textContent, radios: d.querySelectorAll('.lp [role=radio], .lp details').length};" % Q1)
    # Points lead by default on a call (the live review, 2026-11-11), and only points written as
    # a list are drawn beside the script, so the sample's questions are given lists here.
    got = _go(run, tmp_path, _listed(_model(_ctx())), [
        dict(OPEN, eval=look),
        {"click": "Script first", "exact": True, "within": "dialog.detail .lp-bar", "eval": look},
        {"click": "Points first", "exact": True, "within": "dialog.detail .lp-bar", "eval": look},
    ], vp)
    before, script, back = (a["eval"] for a in got["after"])
    assert before["scripts"] > 1 and before["script"] == before["scripts"], before
    assert before["all"] > 1 and before["points"] == before["all"], before
    assert before["radios"] == 0, "no switch and no fold in the prep"
    assert before["lead"] == "cues" and before["cuesFirst"] and before["label"] == "Script first", before
    assert script["lead"] == "script" and not script["cuesFirst"] and script["label"] == "Points first", script
    assert script["points"] == script["all"] and script["script"] == script["scripts"], "a flip hides nothing"
    assert back["lead"] == "cues" and back["cuesFirst"], back


def _listed(m):
    """The sample with every question's points written as a list, the way a prep is written now."""
    import re
    def walk(nodes):
        for q in nodes or []:
            if isinstance(q.get("simple"), str):
                q["simple"] = [x for x in re.split(r"(?<=[.!?])\s+", q["simple"]) if x.strip()]
            walk(q.get("follow"))
    for iv in m["interviews"]:
        walk((iv.get("live") or {}).get("questions"))
    return m


def test_points_written_as_one_string_are_drawn_once_not_again_under_the_script(run, tmp_path, vp):
    # An older prep's points are one string: the review found every such answer drawn twice,
    # the script and then its own sentences again as points.
    look = _ev("const a = document.querySelector('dialog.detail %s > .lp-ans');"
               "return {scripts: a.querySelectorAll('.lp-script').length, points: a.querySelectorAll('.lp-cues li').length};" % Q1)
    got = _go(run, tmp_path, _model(_ctx()), [dict(OPEN, eval=look)], vp)
    one = got["after"][0]["eval"]
    assert one == {"scripts": 1, "points": 0}, one


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


def test_a_chip_goes_to_its_part(run, tmp_path, vp):
    look = ("(() => { const a = document.activeElement; const r = a.__drawnRect();"
            " return {cls: a.className, tag: a.tagName, top: Math.round(r.top), vh: innerHeight}; })()")
    got = _go(run, tmp_path, _model(_ctx()), [
        OPEN,
        {"click": "4 Probes", "exact": True, "within": "dialog.detail .lp-chips", "ready": IN_VIEW, "eval": look},
        {"click": "Stories", "exact": True, "within": "dialog.detail .lp-chips", "ready": IN_VIEW, "eval": look},
    ], vp)
    probes, stories = (a["eval"] for a in got["after"][1:])
    assert "lp-part" in probes["cls"] and 0 <= probes["top"] < probes["vh"], probes
    assert "lp-stories" in stories["cls"], stories


# The term's box: open or not, its words, where it is against its word's own line, and who has
# the focus.
# The line being read and the one after it stay clear (the live review, 2026-11-11: the box
# under the word covered the next line, the one about to be read).
POP = _ev("const p = document.querySelector('.lp-pop'); const t = document.querySelector('[aria-describedby]');"
          " const r = p.__drawnRect(); const rs = t ? [...t.getClientRects()] : []; const line = rs[rs.length - 1]; const lh = t ? parseFloat(getComputedStyle(t).lineHeight) : 0;"
          " return {open: vis(p), text: p.textContent, described: t ? t.dataset.term : '', wide: Math.round(r.width), lh,"
          " clear: !line || r.top >= line.bottom + lh - 1 || r.bottom <= rs[0].top + 1,"
          " inside: r.left >= 0 && r.right <= innerWidth + 1 && r.top >= 0 && r.bottom <= innerHeight + 1,"
          " focus: document.activeElement.className, panel: document.querySelectorAll('.lp-panel, .lp-scrim').length, more: vis(p.querySelector('.lp-pop-more'))};")
TERM = "demand forecast: what it means"


def test_a_term_opens_in_a_small_box_beside_its_word_and_a_second_tap_closes_it(run, tmp_path, vp):
    # The maintainer, 2026-11-11: a word explains itself where it is, in a small box, never a
    # panel or a sheet over a dimmed page; it never covers the line it explains.
    got = _go(run, tmp_path, _model(_ctx()), [
        OPEN,
        {"click": TERM, "within": "dialog.detail .lp-part", "eval": POP},
        {"click": TERM, "within": "dialog.detail .lp-part", "eval": POP},
        {"click": TERM, "within": "dialog.detail .lp-part"},
        {"eval": "(() => { document.querySelector('dialog.detail .lp-q-q').click(); return 1; })()"},
        {"eval": POP},
    ], vp)
    first, again, _open, _out, outside = (a.get("eval") for a in got["after"][1:])
    assert first["open"] and first["described"] == "demand-forecast" and first["panel"] == 0, first
    assert first["text"].startswith("Demand forecast") and "Means: A best estimate" in first["text"], first["text"]
    assert "Here: At Fernhill Freight" in first["text"] and "More" in first["text"], first["text"]
    assert not first["more"], "the example and the technical answer wait behind More"
    assert first["clear"] and first["inside"], first
    assert first["lh"] > 0 and first["wide"] <= 272, "a small box, clear of the next line too"
    assert "lp-pop" not in first["focus"], "the box never takes the focus"
    assert not again["open"] and not again["described"], "a second tap closes it"
    assert not outside["open"], "a tap outside closes it"


def test_a_term_opens_at_a_fingers_tap_on_a_touch_screen_and_a_second_tap_closes_it(run, tmp_path):
    # A tap focuses the word before its click comes: the box opened on the focus, the click
    # took it for a second tap and shut it, and on an iPhone no word ever explained itself
    # (Safari's and Firefox's runs, 2026-11-12). A finger's tap, as a phone makes it.
    got = _go(run, tmp_path, _model(_ctx()), [
        dict(OPEN, eval="matchMedia('(pointer: coarse)').matches && !matchMedia('(hover: hover)').matches"),
        {"finger": TERM, "within": "dialog.detail .lp-part", "eval": POP},
        {"wait": 400, "eval": POP},
        {"finger": TERM, "within": "dialog.detail .lp-part", "eval": POP},
    ], PHONE, touch=True)
    touch, tapped, later, again = (a.get("eval") for a in got["after"])
    assert touch is True, "a touch screen, no mouse"
    assert tapped["open"] and tapped["described"] == "demand-forecast", tapped
    assert tapped["text"].startswith("Demand forecast") and tapped["clear"] and tapped["inside"], tapped
    assert "lp-pop" not in tapped["focus"], "the box never takes the focus"
    assert later["open"], "it stays open after the tap"
    assert not again["open"] and not again["described"], "a second tap closes it"


def test_a_term_opens_on_a_deliberate_hover_and_on_focus_never_under_a_resting_mouse(run, tmp_path):
    # The live review, 2026-11-11: a box opened by itself mid-read wherever the text brought a
    # word under a mouse left resting. A mouse moved onto the word and kept there 700ms opens
    # it; the text arriving under a still mouse never does, nor a move cut short by a scroll.
    at = ("const t = document.querySelector('dialog.detail .lp-part .lp-term'); const r = t.getClientRects()[0];"
          " const x = Math.round(r.left + 4), y = Math.round(r.top + r.height / 2);")
    move = lambda on, dx: ("(() => { %s const e = %s; e.dispatchEvent(new PointerEvent('pointermove', {bubbles: true, pointerType: 'mouse', clientX: x + %d, clientY: y}));"  # noqa: E731
                           " return 1; })()" % (at, on, dx))
    # The mouse rests where the word then arrives: its last move was there, over other words.
    rest = ("(() => { %s const h = document.querySelector('dialog.detail .lp-part-h');"
            " h.dispatchEvent(new PointerEvent('pointermove', {bubbles: true, pointerType: 'mouse', clientX: x, clientY: y}));"
            " t.dispatchEvent(new MouseEvent('mouseover', {bubbles: true, clientX: x, clientY: y}));"
            " t.dispatchEvent(new PointerEvent('pointermove', {bubbles: true, pointerType: 'mouse', clientX: x, clientY: y})); return 1; })()" % at)
    cut = ("(() => { %s t.dispatchEvent(new PointerEvent('pointermove', {bubbles: true, pointerType: 'mouse', clientX: x + 9, clientY: y}));"
           " document.querySelector('dialog.detail .detail-body').scrollTop += 3; return 1; })()" % at)
    away = ("(() => { const t = document.querySelector('dialog.detail .lp-part .lp-term');"
            " t.dispatchEvent(new MouseEvent('mouseout', {bubbles: true, relatedTarget: document.querySelector('dialog.detail .lp-q-q')})); return 1; })()")
    focus = ("(() => { const t = document.querySelector('dialog.detail .lp-part .lp-term'); t.focus(); return 1; })()")
    esc = ("(() => { document.activeElement.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true})); return 1; })()")
    shown = "!document.querySelector('.lp-pop').hidden"
    gone = "document.querySelector('.lp-pop').hidden"
    got = _go(run, tmp_path, _model(_ctx()), [
        dict(OPEN, eval="matchMedia('(hover: hover) and (pointer: fine)').matches"),
        {"eval": rest}, {"wait": 1200, "eval": POP},
        {"eval": cut}, {"wait": 1200, "eval": POP},
        {"eval": move("t", 5)}, {"ready": shown, "eval": POP},
        {"eval": away}, {"ready": gone, "eval": POP},
        {"eval": focus}, {"ready": shown, "eval": POP},
        {"eval": esc}, {"eval": POP},
    ], WIDE)
    ev = [a.get("eval") for a in got["after"]]
    assert ev[0] is True, "a screen with a mouse"
    resting, scrolled, moved, left, focused, closed = ev[2], ev[4], ev[6], ev[8], ev[10], ev[12]
    assert not resting["open"], "a word that arrives under a resting mouse stays shut"
    assert not scrolled["open"], "a move cut short by the text scrolling stays shut"
    assert moved["open"] and moved["described"], moved
    assert not left["open"], "leaving the word closes it a moment later"
    assert focused["open"] and "lp-term" in focused["focus"], "focus opens it and keeps the focus on the word"
    assert not closed["open"] and not closed["described"], "Esc closes it"


def test_a_term_in_a_picked_follow_up_opens_and_the_pick_stays(run, tmp_path):
    # A term inside a follow-up that was picked opens beside it, and the pick stays.
    pick = "(() => { const c = document.querySelector('[data-lpq=q13] .lp-choice'); c.click(); return document.querySelector('[data-lpq=q13] .lp-fu-q').textContent; })()"
    got = _go(run, tmp_path, _model(_ctx()), [
        OPEN,
        {"eval": pick},
        {"eval": _ev("const t = document.querySelector('[data-lpq=q13] .lp-fu-node .lp-term'); if (!t) return 'none'; t.click();"
                     " return {open: vis(document.querySelector('.lp-pop')), node: vis(document.querySelector('[data-lpq=q13] .lp-fu-node'))};")},
    ], WIDE)
    picked, at = got["after"][1]["eval"], got["after"][2]["eval"]
    assert picked.startswith("How would you test it?"), picked
    assert at == "none" or (at["open"] and at["node"]), at


def test_find_is_always_there_and_finds_what_to_say_answers_and_follow_ups(run, tmp_path, vp):
    # Find sits in the bar at the top, never behind Tools (the maintainer, 2026-11-11: nothing
    # should need opening). A follow-up two deep is found in the prep itself, not on the screen,
    # and is picked so its answer is in view.
    look = _ev("const d = document.querySelector('dialog.detail');"
               "return {found: d.querySelector('.lp-found').textContent, input: vis(d.querySelector('.lp-bar .lp-search input')),"
               " beats: [...d.querySelectorAll('.lp-beat')].filter(vis).length,"
               " cards: [...d.querySelectorAll('.lp-q')].filter(vis).map((x) => x.dataset.lpq || x.dataset.lpa || 'story'),"
               " once: [...d.querySelectorAll('.lp-part-follow')].filter(vis).map((x) => x.closest('.lp-part').dataset.lpp),"
               " node: [...d.querySelectorAll('.lp-part-follow .lp-fu-node')].filter(vis).map((x) => x.textContent).join(' | '),"
               " parts: [...d.querySelectorAll('.lp-part')].filter(vis).length};")
    fill = lambda q: {"eval": "(() => { const f = document.querySelector('.lp-search input'); f.value = %r; f.dispatchEvent(new Event('input')); return 1; })()" % q}  # noqa: E731
    got = _go(run, tmp_path, _model(_ctx()), [
        dict(OPEN, eval=look),
        dict(fill("error by distribution centre"), read="dialog.detail"), {"eval": look},
        dict(fill("its users can check it themselves")), {"eval": look},
        dict(fill("new lines with little history")), {"eval": look},
        dict(fill("zebra crossings")), {"eval": look},
        dict(fill("")), {"eval": look},
        {"eval": "(() => { const f = document.querySelector('.lp-search input'); f.value = 'zebra'; f.dispatchEvent(new Event('input')); f.focus();"
                 " f.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true})); return {value: f.value, parts: document.querySelectorAll('.lp-part:not([hidden])').length}; })()"},
    ], vp)
    ev = [a.get("eval") for a in got["after"]]
    before, narr, detailed, follow, none, cleared, esc = ev[0], ev[2], ev[4], ev[6], ev[8], ev[10], ev[11]
    assert before["input"], "find is on the screen from the start"
    # What to say first and the answer that says it are found; the rest steps aside.
    assert narr["beats"] == 1 and narr["cards"] and narr["found"].endswith("found"), narr
    # The script of an answer is found as its points are.
    assert detailed["cards"] and detailed["beats"] == 0, detailed
    # A follow-up two deep is found and picked, its answer in view. It is one said once for its
    # part, after any story there (the screen review of 2026-11-11, row 35).
    q1_part = next(q["part"] for q in _live()["questions"] if q["id"] == "q1")
    assert follow["cards"] == [] and follow["once"] == [q1_part], follow
    assert "And where did it not hold?" in follow["node"], follow["node"]
    assert none["found"] == "Nothing found: try fewer words" and none["parts"] == 0
    assert cleared["parts"] == before["parts"] and cleared["beats"] == before["beats"] and not cleared["found"]
    # Esc in find clears it.
    assert esc["value"] == "" and esc["parts"] == before["parts"], esc


def _deep(model):
    """The sample prep with one follow-up chain four deep, to see the page stop at three."""
    lv = next(iv for iv in model["interviews"] if iv["id"] == IV)["live"]
    q = next(x for x in lv["questions"] if x["id"] == "q13")
    second = q["follow"][0].setdefault("follow", [])
    second.insert(0, {"who": "technical", "q": "What if the weeks are missing?", "simple": ["Fill them with zero, then flag them"],
                      "detailed": "I'd fill them with zero, then flag them so nobody reads a gap as a quiet week."})
    second[0]["follow"] = [{"who": "manager", "q": "Who would notice the flag?", "simple": ["The planner who owns that line"],
                            "detailed": "The planner who owns that line would see it first, on the morning list.",
                            "follow": [{"who": "senior", "q": "A fourth level nobody draws?", "simple": ["Never shown"], "detailed": "Never shown."}]}]
    return model


def test_the_follow_ups_are_choices_three_deep_with_the_way_back(run, tmp_path, vp):
    # The maintainer, 2026-11-11: each question shows its follow-ups as choices; picking one
    # shows its answer and its own follow-ups, three deep, with a way back. Nothing folds.
    card = "[data-lpq=q13]"
    look = _ev("const c = document.querySelector('%s'); const n = c.querySelector('.lp-fu-node');"
               "return {choices: [...c.querySelectorAll('.lp-choice')].filter(vis).map((b) => b.textContent),"
               " q: n ? n.querySelector('.lp-fu-q').textContent : '', depth: n ? n.dataset.depth : '0',"
               " crumbs: [...c.querySelectorAll('.lp-trail .lp-crumb')].map((b) => b.textContent),"
               " back: vis(c.querySelector('.lp-fu-back')), script: n ? vis(n.querySelector('.lp-script')) : false,"
               " points: n ? vis(n.querySelector('.lp-cues')) : false, focus: document.activeElement.className};" % card)
    pick = lambda text: {"click": text, "within": "dialog.detail " + card + " .lp-choices", "eval": look}  # noqa: E731
    got = _go(run, tmp_path, _listed(_deep(_model(_ctx()))), [
        dict(OPEN, eval=look),
        pick("How would you test it?"),
        pick("What if the weeks are missing?"),
        pick("Who would notice the flag?"),
        {"click": "Back", "exact": True, "within": "dialog.detail " + card + " .lp-trail", "eval": look},
        {"click": "How would you test it?", "within": "dialog.detail " + card + " .lp-trail", "eval": look},
        {"click": "Back", "exact": True, "within": "dialog.detail " + card + " .lp-trail", "eval": look},
    ], vp)
    top, one, two, three, back2, crumb1, home = (a["eval"] for a in got["after"])
    assert top["depth"] == "0" and any(c.startswith("How would you test it?") for c in top["choices"]), top
    assert not top["back"]
    assert one["depth"] == "1" and one["q"].startswith("How would you test it?") and one["back"], one
    assert one["points"] and two["script"] and two["points"], "a picked follow-up shows both ways of its answer at once"
    assert any(c.startswith("What if the weeks are missing?") for c in one["choices"]), one
    assert two["depth"] == "2" and two["crumbs"] == ["How would you test it?"], two
    assert three["depth"] == "3" and three["choices"] == [], "the third level has no more choices"
    assert three["crumbs"] == ["How would you test it?", "What if the weeks are missing?"], three
    assert "lp-fu-q" in three["focus"], "the picked question takes the focus, so a screen reader hears it"
    assert back2["depth"] == "2" and back2["q"].startswith("What if the weeks are missing?"), back2
    assert crumb1["depth"] == "1" and crumb1["q"].startswith("How would you test it?"), crumb1
    assert home["depth"] == "0" and not home["back"] and len(home["choices"]) == len(top["choices"]), home


def test_practice_is_trying_an_answer_first_then_looking(run, tmp_path, vp):
    # The UX review of 2026-11-10 (U-4): trying an answer and then checking it beats rereading.
    # Practise opens the prep with one "Show the answer" in place of each answer's two ways;
    # the live view itself has no switch to hide them (the maintainer, 2026-11-11).
    look = _ev("const d = document.querySelector('dialog.detail');"
               "return {pills: [...d.querySelectorAll('.lp-head .card-actions .btn')].map((b) => b.textContent.trim()),"
               " shown: [...d.querySelectorAll('.lp-reveal')].filter(vis).length, all: d.querySelectorAll('.lp-ans').length,"
               " simple: [...d.querySelectorAll('.lp-simple')].filter(vis).length, detailed: [...d.querySelectorAll('.lp-detailed')].filter(vis).length,"
               " first: vis(d.querySelector('%s > .lp-ans .lp-simple')) && vis(d.querySelector('%s > .lp-ans .lp-detailed')),"
               " beats: [...d.querySelectorAll('.lp-beat')].filter(vis).length};" % (Q1, Q1))
    got = _go(run, tmp_path, _listed(_model(_ctx())), [dict(OPEN, eval=look)], vp)
    before = got["after"][0]["eval"]
    assert before["pills"] == ["Practise with Claude"] and before["shown"] == 0 and before["simple"] > 0 and before["detailed"] > 0
    drill = _go(run, tmp_path, _listed(_soon(1)), [
        {"hash": "todo"},
        {"click": "Practise 3 questions", "within": "#main", "read": "dialog.detail", "eval": look},
        {"click": "Show the answer", "exact": True, "within": Q1 + " > .lp-ans", "eval": look}], vp)
    hidden, one = drill["after"][1]["eval"], drill["after"][2]["eval"]
    assert hidden["simple"] == 0 and hidden["detailed"] == 0 and hidden["shown"] == hidden["all"] > 1, hidden
    assert hidden["beats"] > 0, "what to say first stays in view"
    assert one["first"] and one["shown"] == hidden["all"] - 1, one


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
        got = _go(run, tmp_path, _listed(_soon(days)), steps, vp)
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
    again = _go(run, tmp_path, _listed(_soon(1)), [
        {"hash": "todo"},
        {"click": "Practise 3 questions", "within": "#main", "read": "dialog.detail"},
        {"eval": "(() => { document.querySelector('[data-k=detail-back]').click(); return 1; })()"},
        {"click": "Read your prep", "within": "#main", "read": "dialog.detail", "eval": opened}], vp)
    assert again["after"][3]["eval"]["simple"] > 0 and again["after"][3]["eval"]["shown"] == 0, again["after"][3]["eval"]


def test_nothing_is_wider_than_a_phone_and_the_dark_look_draws(run, tmp_path):
    wide = ("(() => { const d = document.querySelector('dialog.detail'); const b = d.querySelector('.detail-body');"
            # The chips scroll sideways inside their own row on a phone (the screen review,
            # 2026-11-11): one past its edge is inside the row, never wider than the screen. The
            # lifelines wrap, so none is past it (the live review, 2026-11-11).
            " const over = [...d.querySelectorAll('.lp *')].filter((e) => e.getClientRects().length && !e.closest('[hidden]') && !e.parentElement.closest('.lp-chips') && e.__drawnRect().right > innerWidth + 1).map((e) => e.className).slice(0, 5);"
            " const bg = getComputedStyle(d).backgroundColor.match(/\\d+/g).slice(0, 3).map(Number);"
            " return {sideways: b.scrollWidth > b.clientWidth + 1, over, light: (bg[0] + bg[1] + bg[2]) / 3}; })()")
    # Every first follow-up picked, so each answer under a pick is drawn too.
    pick = "(() => { for (const b of document.querySelectorAll('.lp-fu')) { const c = b.querySelector('.lp-choice'); if (c) c.click(); } return 1; })()"
    steps = [dict(OPEN), {"eval": pick}, {"eval": wide}]
    light = _go(run, tmp_path, _model(_ctx()), steps, PHONE)["after"][2]["eval"]
    assert not light["sideways"] and light["over"] == [], light
    dark = _go(run, tmp_path, _model(_ctx()), steps, PHONE, scheme="dark")["after"][2]["eval"]
    assert not dark["sideways"] and dark["over"] == [], dark
    assert dark["light"] < 100 < light["light"], "the dark look is dark and the light look light"


def test_the_smoke_test_at_phone_width(run, tmp_path):
    # The call-prep page's own smoke test (its smoke-test.cjs), at 390 pixels: no script
    # errors, no sideways scroll, a term's box, and every answer shown both ways.
    phone = {"width": 390, "height": 844}
    probe = _ev("const d = document.querySelector('dialog.detail'); const b = d.querySelector('.detail-body'); const p = d.querySelector('.lp-pop');"
                "return {sideways: b.scrollWidth > b.clientWidth + 1 || document.documentElement.scrollWidth > innerWidth + 1,"
                " panel: vis(p) ? p.querySelector('.lp-pop-name').textContent : '', more: vis(p) && vis(p.querySelector('.lp-pop-more')),"
                " detailed: [...d.querySelectorAll('.lp-detailed')].filter(vis).length, all: d.querySelectorAll('.lp-detailed').length,"
                " terms: d.querySelectorAll('.lp-term').length, cards: d.querySelectorAll('.lp-q').length, follows: d.querySelectorAll('.lp-choice').length};")
    got = _go(run, tmp_path, _model(_ctx()), [
        dict(OPEN, eval=probe),
        {"click": "demand forecast: what it means", "within": "dialog.detail .lp-part", "eval": probe},
        {"click": "More", "exact": True, "within": ".lp-pop", "eval": probe},
    ], phone)
    start, term, more = (a.get("eval") for a in got["after"])
    assert not start["sideways"] and start["terms"] > 0 and start["cards"] > 0 and start["follows"] > 0
    assert start["detailed"] == start["all"] > 0
    assert term["panel"] == "Demand forecast" and not term["sideways"]
    assert not term["more"] and more["more"] and more["panel"] == "Demand forecast" and not more["sideways"], "More opens the rest in the box"


def test_the_top_is_the_head_the_bar_and_what_to_say_first(run, tmp_path, vp):
    look = ("(() => { const lp = document.querySelector('.lp'); const kids = [...lp.children];"
            " const first = kids.findIndex((x) => x.classList.contains('lp-part'));"
            " return {before: kids.slice(0, first).map((x) => x.className),"
            " head: document.querySelector('.lp-head').textContent, notes: document.querySelector('.lp-notes').textContent,"
            " sticky: [...lp.querySelectorAll('*')].filter((x) => ['sticky', 'fixed'].includes(getComputedStyle(x).position) && x.checkVisibility()).map((x) => x.className),"
            " pills: [...lp.querySelectorAll('.lp-head .card-actions .btn')].map((x) => x.textContent.trim()),"
            " search: lp.querySelector('.lp-search input').placeholder, foot: lp.lastElementChild.textContent}; })()")
    got = _go(run, tmp_path, _model(_ctx()), [dict(OPEN, eval=look)], vp)
    at = got["after"][0]["eval"]
    # The head, the bar with find and the parts, what to say at a glance, then part 1; nothing
    # folded on the way (the maintainer, 2026-11-11).
    assert at["before"] == ["lp-head", "lp-bar", "lp-box lp-glance"], at["before"]
    assert "Practise with Claude" in at["head"] and "Open all" not in at["head"]
    # One pill on the prep: Update my prep and the calendar stay on the card in Coming up.
    assert at["pills"] == ["Practise with Claude"], at["pills"]
    assert at["search"] == "They asked..."
    # The bar stays at the top while the prep scrolls, and the lifelines at its foot.
    assert at["sticky"] == ["lp-bar", "lp-life"], at["sticky"]
    # The pay and the notice are the person's own notes, last, never on the head.
    assert "If pay comes up:" in at["notes"] and "Your notice: One month." in at["notes"]
    assert "If pay comes up" not in at["head"]
    assert at["foot"] == "Claude doesn't join, listen or record. This page is just for you to look at."


def test_a_term_opens_and_nothing_moves(run, tmp_path, vp):
    box = ("(() => { const c = document.querySelector('.lp').__drawnRect(); const p = document.querySelector('.lp-pop');"
           " return {left: Math.round(c.left), right: Math.round(c.right), top: Math.round(c.top), open: !p.hidden}; })()")
    got = _go(run, tmp_path, _model(_ctx()), [dict(OPEN, eval=box),
        {"click": TERM, "within": "dialog.detail .lp-part", "eval": box}], vp)
    before, after = (a["eval"] for a in got["after"])
    assert after["open"]
    # The tap may scroll the word into view; the column itself never moves sideways or narrows.
    assert (before["left"], before["right"]) == (after["left"], after["right"]), (before, after)


def test_a_technical_prep_opens_in_its_own_stages(run, tmp_path, vp):
    model, doc = _shaped_model(_ctx(), "live SQL and Python, 45 minutes")
    look = _ev("return {parts: [...document.querySelectorAll('.lp-part[data-lpp] .lp-part-h')].map((x) => x.textContent),"
               " bar: document.querySelector('.lp-bar').getAttribute('aria-label'), sideways: (() => { const b = document.querySelector('dialog.detail .detail-body'); return b.scrollWidth > b.clientWidth + 1; })()};")
    at = _go(run, tmp_path, model, [dict(OPEN, eval=look)], vp)["after"][0]["eval"]
    assert at["parts"] == ["Warm-up, and your background", "A problem, worked aloud", "The follow-up probes and trade-offs",
                           "Your questions for them"]
    assert at["bar"].startswith("45 minutes in 4 parts") and not at["sideways"], at["bar"]


def test_a_personal_story_and_live_coding_open_as_one_sitting(run, tmp_path, vp):
    model, doc = _shaped_model(dict(_ctx(), stage="Second round"), "personal experience, technical coding (HackerRank, Python)")
    assert doc["shape"] == "combined:personal+technical"
    look = _ev("return {parts: [...document.querySelectorAll('.lp-part[data-lpp] .lp-part-h')].map((x) => x.textContent),"
               " chips: [...document.querySelectorAll('.lp-chips .btn')].map((x) => x.textContent),"
               " timing: document.querySelector('.lp-bar').getAttribute('aria-label')};")
    at = _go(run, tmp_path, model, [dict(OPEN, eval=look)], vp)["after"][0]["eval"]
    assert at["parts"] == [p["title"] for p in doc["parts"]]
    assert at["chips"][:5] == ["1 Intro", "2 Your story", "3 The problem", "4 Probes", "5 Your questions"]
    assert "in 5 parts" in at["timing"], at["timing"]


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


def test_it_opens_on_what_to_say_at_a_glance_and_nothing_needs_opening(run, tmp_path, vp):
    # The UX review of 2026-11-10 (U-5): the first phone screen was a 43-word introduction and
    # controls before Part 1. The maintainer, 2026-11-11: nothing should need opening before it
    # can be read. It opens on the line to open with, what they are known to ask and two
    # questions to ask them; find is in view; there is no fold anywhere in the prep.
    look = _ev("const d = document.querySelector('dialog.detail'); const g = d.querySelector('.lp-glance');"
               " const top = (x) => Math.round(x.__drawnRect().top);"
               " return {glance: g && g.textContent, glanceIn: !!g && g.__drawnRect().bottom <= innerHeight + 1, gb: !!g && [Math.round(g.__drawnRect().top), Math.round(g.__drawnRect().bottom), innerHeight],"
               " beforePart: !!g && top(g) < top(d.querySelector('.lp-part')),"
               " search: vis(d.querySelector('.lp-search input')), folds: d.querySelectorAll('.lp details, .lp summary').length,"
               " hiddenAnswers: [...d.querySelectorAll('.lp-ans .lp-layers')].filter((x) => !vis(x)).length,"
               " asks: [...d.querySelectorAll('.lp-ask .lp-ifs li')].filter(vis).length, flags: d.querySelectorAll('.lp-notes .lp-flags li').length,"
               " lines: d.querySelectorAll('%s > .lp-ans .lp-simple > li').length,"
               " detailedLines: d.querySelectorAll('%s > .lp-ans .lp-detailed').length,"
               " left: Math.round(d.querySelector('.detail-title').__drawnRect().left)};" % (Q1, Q1))
    got = _go(run, tmp_path, _listed(_model(_ctx())), [dict(OPEN, eval=look)], vp)
    at = got["after"][0]["eval"]
    assert "Open with" in at["glance"] and "I'm an operations analyst" in at["glance"], at["glance"]
    assert "Known to ask" in at["glance"] and "How do you get depot managers to trust a forecast?" in at["glance"]
    assert "Ask them" in at["glance"] and "cross-dock in Warrington" in at["glance"]
    assert at["beforePart"] and (at["glanceIn"] or vp is not PHONE), ("the glance is on the first screen", at["gb"])
    # On a phone the words start 16px from its edge, as everywhere on the page: the full-screen
    # body's empty side columns once added their gap as more padding (2026-11-11).
    assert vp is not PHONE or at["left"] == 16, at["left"]
    assert at["search"] and at["folds"] == 0 and at["hiddenAnswers"] == 0, at
    # What to ask next to each likely answer of theirs is on the screen, not behind a fold.
    assert at["asks"] > 0, at
    assert at["lines"] >= 2 and at["detailedLines"] == 1


def test_who_asks_comes_after_the_question(run, tmp_path, vp):
    # Who asks is said after the question, small, never ahead of it: the question is what to
    # read first (the maintainer, 2026-11-11).
    look = ("(() => [...document.querySelectorAll('dialog.detail .lp-q[data-lpq] .lp-q-q')].map((h4) => {"
            " const pill = h4.querySelector('.lp-who'); const first = h4.firstChild;"
            " return !!pill && first.nodeType === 3 && !!first.textContent.trim(); }))()")
    got = _go(run, tmp_path, _model(_ctx()), [dict(OPEN, eval=look)], vp)
    at = got["after"][0]["eval"]
    assert at and all(at), at


def test_a_test_taken_alone_reads_as_a_test_and_a_day_in_hours(run, tmp_path, vp):
    # A test with nobody in the room has nothing to say first and no talk to time; a day of
    # interviews is said in hours (2026-11-10).
    model, doc = _shaped_model(dict(_ctx(), stage="Online assessment"), "HackerRank, 90 minutes")
    look = _ev("const d = document.querySelector('dialog.detail');"
               "return {labels: [...d.querySelectorAll('.lp-narr > .lp-lbl')].map((x) => x.textContent),"
               " eyebrows: [...d.querySelectorAll('.lp-eyebrow')].map((x) => x.textContent).join(' | '),"
               " lede: d.querySelector('.lp-bar').getAttribute('aria-label'), glance: d.querySelector('.lp-glance').textContent};")
    at = _go(run, tmp_path, model, [dict(OPEN, eval=look)], vp)["after"][0]["eval"]
    assert at["labels"] and "Say first" not in at["labels"] and set(at["labels"]) == {"Keep in mind"}, at["labels"]
    assert "you talk" not in at["eyebrows"].lower(), at["eyebrows"]
    assert "90 minutes" in at["lede"] and "Before you start" in at["glance"] and "Ask them" not in at["glance"]
    day, _doc = _shaped_model(dict(_ctx(), stage="Superday"), "")
    lede = _go(run, tmp_path, day, [dict(OPEN, eval=_ev("return document.querySelector('.lp-bar').getAttribute('aria-label');"))], vp)["after"][0]["eval"]
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
        {"eval": "(() => { const t = document.querySelector('dialog.detail .lp-part .lp-term'); t.focus(); t.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', bubbles: true})); return !document.querySelector('.lp-pop').hidden; })()"}], vp)
    seen, opened = got["after"][0]["eval"], got["after"][1]["eval"]
    assert seen["n"] > 0 and seen["mark"] not in seen["colours"], seen
    assert seen["display"] == ["inline"] and seen["roles"] == ["button"] and seen["tab"], seen
    assert opened is True, "Enter opens a term, as a button's does"


def test_on_a_phone_the_bar_is_find_and_one_row_of_chips(run, tmp_path):
    # Eight chips over three rows were more than a screen before Part 1 on a phone (the screen
    # review, 2026-11-11). The chips are one row that scrolls sideways inside itself, under find.
    look = _ev("const d = document.querySelector('dialog.detail');"
               " const chips = [...d.querySelectorAll('.lp-chips .btn')].filter(vis).map((b) => { const r = b.__drawnRect(); return Math.round((r.top + r.bottom) / 2); });"
               " const bar = d.querySelector('.lp-bar').__drawnRect();"
               " return {rows: new Set(chips).size, n: chips.length, sideways: document.documentElement.scrollWidth > innerWidth || d.scrollWidth > d.clientWidth,"
               " barH: Math.round(bar.height), vh: innerHeight};")
    got = _go(run, tmp_path, _model(_ctx()), [dict(OPEN, eval=look)], PHONE)
    seen = got["after"][0]["eval"]
    assert seen["n"] >= 6 and seen["rows"] == 1 and not seen["sideways"], seen
    assert seen["barH"] < seen["vh"] / 4, seen


# Scrolled well into the prep, as it is read during the call.
DOWN = "(() => { document.querySelector('dialog.detail .detail-body').scrollTop = 1800; return 1; })()"
SETTLED = "(() => { const b = document.querySelector('.lp-bar'); return !!document.querySelector('.lp-chips [aria-current=true]') && (innerWidth >= 760 || b.classList.contains('lp-tight')); })()"


def test_the_bar_is_one_solid_ground_from_the_header_to_under_the_chips(run, tmp_path, vp):
    # The live review, 2026-11-11: the bar stuck 16px under the header, and words scrolled into
    # view above find and under the chips. Every point from the header's foot to the bar's,
    # across the column, is the bar; and the lifelines sit flush on the screen's foot.
    look = _ev("const d = document.querySelector('dialog.detail'); const top = d.querySelector('.detail-top').__drawnRect();"
               " const bar = d.querySelector('.lp-bar').__drawnRect(); const life = d.querySelector('.lp-life').__drawnRect(); const miss = [];"
               " for (let y = Math.ceil(top.bottom); y < bar.bottom; y += 3) for (const x of [bar.left + 2, (bar.left + bar.right) / 2, bar.right - 2]) {"
               "   const e = document.elementFromPoint(x, y); if (!e || !e.closest('.lp-bar, .detail-top')) miss.push([Math.round(x), y, e ? e.className : '']); }"
               " return {miss: miss.slice(0, 4), gap: Math.round(bar.top - top.bottom), foot: Math.round(innerHeight - life.bottom),"
               " ground: getComputedStyle(d.querySelector('.lp-bar')).backgroundColor, head: getComputedStyle(d.querySelector('.detail-top')).backgroundColor};")
    got = _go(run, tmp_path, _model(_ctx()), [OPEN, {"eval": DOWN}, {"ready": SETTLED, "eval": look}], vp)
    at = got["after"][2]["eval"]
    assert at["gap"] <= 1 and at["miss"] == [] and at["foot"] == 0, at
    assert at["ground"] == at["head"], "one ground with the header"


def test_the_order_switch_sits_beside_find_never_past_the_edge(run, tmp_path, vp):
    # The live review, 2026-11-11: "Points first" was the last of a row of chips that scrolls
    # sideways on a phone, past the screen's edge.
    look = _ev("const d = document.querySelector('dialog.detail'); const l = d.querySelector('.lp-lead'); const f = d.querySelector('.lp-search input');"
               " const a = l.__drawnRect(), b = f.__drawnRect();"
               " return {inChips: !!l.closest('.lp-chips'), beside: a.top < b.bottom && a.bottom > b.top && a.left >= b.right, right: a.right <= innerWidth - 8};")
    got = _go(run, tmp_path, _model(_ctx()), [dict(OPEN, eval=look), {"eval": DOWN}, {"ready": SETTLED, "eval": look}], vp)
    for at in (got["after"][0]["eval"], got["after"][2]["eval"]):
        assert not at["inChips"] and at["beside"] and at["right"], at


def test_on_a_phone_the_bar_is_one_row_once_the_prep_is_read_and_nothing_moves(run, tmp_path):
    # The live review, 2026-11-11: on a phone the parts that stay took about 30% of the screen.
    # Read under the bar, find, the order and the chips are one row; the lifelines' line opens
    # over their own row. The bar keeps its room in the flow, so nothing under it moves when it
    # changes, and it is whole again while find is in use.
    look = _ev("const d = document.querySelector('dialog.detail'); const bar = d.querySelector('.lp-bar');"
               " const mid = (s) => { const r = d.querySelector(s).__drawnRect(); return Math.round((r.top + r.bottom) / 2); };"
               " const fixed = d.querySelector('.detail-top').__drawnRect().height + bar.__drawnRect().height + d.querySelector('.lp-life').__drawnRect().height;"
               " return {tight: bar.classList.contains('lp-tight'), mids: [mid('.lp-search input'), mid('.lp-lead'), mid('.lp-chips')],"
               " share: Math.round(100 * fixed / innerHeight), part: Math.round(d.querySelector('[data-lpp=p3]').getBoundingClientRect().top)};")
    focus = "(() => { document.querySelector('.lp-search input').focus(); return 1; })()"
    got = _go(run, tmp_path, _model(_ctx()), [
        dict(OPEN, eval=look),
        {"eval": DOWN},
        {"ready": SETTLED, "eval": look},
        {"click": "Again?", "exact": True, "within": "dialog.detail .lp-life", "eval": look},
        {"eval": focus},
        {"ready": "!document.querySelector('.lp-bar').classList.contains('lp-tight')", "eval": look},
    ], PHONE)
    top, read, said, whole = (got["after"][i]["eval"] for i in (0, 2, 3, 5))
    assert not top["tight"], "whole at the top"
    assert read["tight"] and max(read["mids"]) - min(read["mids"]) <= 4, read
    assert read["share"] <= 27 and said["share"] == read["share"], (read, said)
    assert not whole["tight"] and whole["part"] == read["part"], ("whole while find is in use, nothing moved", read, whole)


def test_the_part_on_the_screen_is_the_chip_marked_and_a_known_part_wears_a_dot(run, tmp_path, vp):
    # The live review, 2026-11-11: a known question's part, its chip filled gold, read as "you
    # are here". The chip filled is the part whose heading was last scrolled up to the bar, the
    # first part from the top of the prep until the next heading gets there, the one thing that
    # changes by itself; a known question's part wears a gold dot. Nothing else looks filled, a
    # chip under the mouse included (at the top "3 The problem" did, under the pointer).
    look = _ev("const d = document.querySelector('dialog.detail'); const cs = [...d.querySelectorAll('.lp-chips .btn')];"
               " const bg = (c) => getComputedStyle(c).backgroundColor; const plain = cs.find((c) => !c.hasAttribute('aria-current') && !c.matches(':hover'));"
               " return {now: cs.filter((c) => c.getAttribute('aria-current') === 'true').map((c) => c.textContent),"
               " filled: cs.filter((c) => bg(c) !== bg(plain)).map((c) => c.textContent),"
               " hovered: cs.filter((c) => c.matches(':hover')).map((c) => c.textContent),"
               " dots: cs.filter((c) => c.querySelector('.lp-chip-dot')).map((c) => c.textContent)};")
    # A part read part way: its heading scrolled past the bar, the next one's still below. (A
    # wide screen is drawn zoomed, so the scroll is by the part's own place, not by pixels.)
    mid = lambda pid: {"eval": "(() => { const sc = document.querySelector('dialog.detail .detail-body'); const p = document.querySelector('[data-lpp=%s]');"  # noqa: E731
                                " p.scrollIntoView({block: 'start', behavior: 'instant'}); sc.scrollTop += 150;"
                                " return Math.round(p.nextElementSibling.__drawnRect().top - document.querySelector('.lp-bar').__drawnRect().bottom); })()" % pid}
    # Marked, and the chips' colours done changing (a chip's fill eases out).
    now = lambda name: ("(() => { const c = [...document.querySelectorAll('.lp-chips [aria-current=true]')];"  # noqa: E731
                        " const moving = document.getAnimations().some((a) => a.playState === 'running' && a.effect && a.effect.target && a.effect.target.closest && a.effect.target.closest('.lp-chips'));"
                        " return c.length === 1 && c[0].textContent === %r && !moving; })()" % name)
    model = _model(_ctx())
    lv = next(iv for iv in model["interviews"] if iv["id"] == IV)["live"]
    names = ["%d %s" % (i + 1, p["short"]) for i, p in enumerate(lv["parts"])]
    got = _go(run, tmp_path, model, [
        dict(OPEN, ready=now(names[0]), eval=look),
        {"click": "4 Probes", "exact": True, "within": "dialog.detail .lp-chips", "ready": now("4 Probes"), "eval": look},
        # The bar settles (a phone's bar folds to one row once scrolled) before the mouse rests on
        # a chip: hovered while it folded, the chip slid out from under the mouse (CI, 2026-11-12).
        mid("p1"), {"ready": now(names[0]) + " && !document.getAnimations().some((a) => a.playState === 'running')", "eval": "1"},
        {"hover": "dialog.detail .lp-chips [data-k='lpchip:p2']",
         "ready": "document.querySelector(\"dialog.detail .lp-chips [data-k='lpchip:p2']\").matches(':hover')", "eval": look},
        mid("p3"), {"ready": now(names[2]), "eval": look},
    ], vp)
    top, probes, below1, _settled, part1, below3, part3 = (a.get("eval") for a in got["after"])
    assert below1 > 24 and below3 > 24, ("the next part is still below the bar", below1, below3)
    assert top["now"] == [names[0]] and top["filled"] == [names[0]], ("the top of the prep is read before Part 1", top)
    assert top["dots"] == ["2 Your story"], ("a known part wears a dot, not a fill", top)
    assert probes["now"] == probes["filled"] == ["4 Probes"], probes
    assert part1["now"] == part1["filled"] == [names[0]], part1
    assert part1["hovered"] == ["2 Your story"], ("the chip under the resting mouse looks plain", part1)
    assert part3["now"] == part3["filled"] == [names[2]], part3


def test_at_the_end_of_the_prep_the_part_tapped_or_the_last_in_view_is_the_one_marked(run, tmp_path):
    # The last parts can never be scrolled up to the bar: tapping "Your notes" filled "Stories"
    # (the live review, 2026-11-11). At the end of the prep the part tapped is the one marked if
    # it is in view, else the last one in view.
    look = _ev("const sc = document.querySelector('dialog.detail .detail-body');"
               " return {now: [...document.querySelectorAll('.lp-chips [aria-current=true]')].map((c) => c.textContent),"
               " end: sc.scrollTop + sc.clientHeight >= sc.scrollHeight - 2};")
    # Marked, once a tap's scroll has come to rest.
    marked = lambda name: "(%s) && (() => { const c = [...document.querySelectorAll('.lp-chips [aria-current=true]')]; return c.length === 1 && c[0].textContent === %r; })()" % (IN_VIEW, name)  # noqa: E731
    still = "(() => { const c = [...document.querySelectorAll('.lp-chips [aria-current=true]')]; return c.length === 1 && c[0].textContent === 'Your notes'; })()"
    bottom = "(() => { const sc = document.querySelector('dialog.detail .detail-body'); sc.scrollTop = sc.scrollHeight; return 1; })()"
    got = _go(run, tmp_path, _model(_ctx()), [
        OPEN,
        {"click": "Your notes", "exact": True, "within": "dialog.detail .lp-chips", "ready": marked("Your notes"), "eval": look},
        {"click": "Stories", "exact": True, "within": "dialog.detail .lp-chips", "ready": marked("Stories"), "eval": look},
        {"click": "1 Intro", "exact": True, "within": "dialog.detail .lp-chips", "ready": marked("1 Intro")},
        {"eval": bottom}, {"ready": still, "eval": look},
    ], {"width": 700, "height": 900})
    notes, stories, bottom_ = got["after"][1]["eval"], got["after"][2]["eval"], got["after"][5]["eval"]
    assert notes == {"now": ["Your notes"], "end": True}, notes
    assert stories["now"] == ["Stories"], stories
    assert bottom_ == {"now": ["Your notes"], "end": True}, "scrolled to the end by hand, the last part in view"


def test_a_lifeline_says_one_line_over_its_own_row_and_it_goes_by_itself(run, tmp_path, vp):
    # Lines for when the call goes sideways, one tap away at the foot of the screen. The live
    # review, 2026-11-11: the line, said in a strip above the row, pushed over the answers on a
    # phone, and the row scrolled its last lifelines past the screen's edge. The line is said
    # over the row itself, the row never grows, and it fades after a while; a tap on it or Esc
    # closes it at once. The row wraps rather than scroll.
    look = _ev("const l = document.querySelector('.lp-life'); const line = l.querySelector('.lp-life-line');"
               " const r = l.__drawnRect(); const row = l.querySelector('.lp-life-row');"
               " const bs = [...l.querySelectorAll('.lp-life-btn')]; const lr = vis(line) ? line.__drawnRect() : null;"
               " return {buttons: bs.map((b) => b.textContent), open: vis(line), said: line.textContent,"
               " over: !lr || (lr.top >= r.top - 1 && lr.bottom <= r.bottom + 1), top: Math.round(r.top), height: Math.round(r.height),"
               " rows: new Set(bs.map((b) => Math.round(b.__drawnRect().top))).size, inside: bs.every((b) => b.__drawnRect().right <= innerWidth) && row.scrollWidth <= row.clientWidth + 1,"
               " foot: Math.abs(Math.round(r.bottom) - innerHeight) <= 1};")
    esc = "(() => { document.querySelector('.lp-life-btn').dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true})); return 1; })()"
    tap = {"click": "Only for you", "within": "dialog.detail .lp-life", "eval": look}
    got = _go(run, tmp_path, _model(_ctx()), [
        dict(OPEN, eval=look),
        {"click": "Again?", "exact": True, "within": "dialog.detail .lp-life", "eval": look},
        tap,
        {"click": "Notice", "exact": True, "within": "dialog.detail .lp-life", "eval": look},
        {"eval": esc}, {"eval": look},
        {"click": "Moment", "exact": True, "within": "dialog.detail .lp-life", "eval": look},
        {"tick": 9000, "eval": look},
    ], vp)
    before, again, shut, notice, _esc, gone, moment, faded = (a.get("eval") for a in got["after"])
    assert before["buttons"][:3] == ["Moment", "Again?", "Don't know"] and "Notice" in before["buttons"], before
    assert not before["open"] and before["foot"], ("the row sits flush at the foot of the screen, its line shut", before)
    assert before["inside"] and before["rows"] <= 2, "every lifeline is on the screen, the row wrapping, never scrolling"
    assert again["open"] and "Sorry, could you say that again?" in again["said"] and "Only for you" in again["said"], again
    assert again["over"] and (again["top"], again["height"]) == (before["top"], before["height"]), "said over the row, which never grows"
    assert not shut["open"], "a tap on the line closes it"
    assert notice["open"] and "One month" in notice["said"], notice
    assert not gone["open"], "Esc closes it"
    assert moment["open"] and not faded["open"], "it goes by itself after a while"


def test_numbers_are_bold_in_what_to_say(run, tmp_path):
    look = _ev("const d = document.querySelector('dialog.detail');"
               " return [...d.querySelectorAll('.lp-ans .lp-num')].map((x) => x.textContent).slice(0, 40);")
    got = _go(run, tmp_path, _model(_ctx()), [dict(OPEN, eval=look)], WIDE)
    nums = got["after"][0]["eval"]
    assert nums and all(any(c.isdigit() for c in n) for n in nums), nums
    assert not any(n.endswith((".", ",")) for n in nums), nums


def _coding(model):
    """The sample prep with its problem part given a coding cockpit, as the writer fills it."""
    lv = next(iv for iv in model["interviews"] if iv["id"] == IV)["live"]
    p = next(x for x in lv["parts"] if x["id"] == "p3")
    p.update(steps=[{"t": "Say the task back", "say": "So I'm forecasting next week's pallets per site; can I look at the data first?"},
                    {"t": "Look at the data", "say": "I'll check the weeks, the sites and any gaps."},
                    {"t": "Build a baseline", "say": "A four week average per site, to beat."},
                    {"t": "Check the error", "say": "Error by site, so one big site doesn't hide the rest."}],
             stuck=["Can I talk through what I'm seeing?", "I'll get a simple version working first."],
             edges=["Weeks with zero pallets", "Missing weeks", "Sites that opened late"],
             code=[{"c": "df.groupby('site')['pallets'].mean()", "means": "average pallets for each site"}],
             more=["With more time I'd add the promotions calendar."])
    return model


def test_a_coding_part_shows_its_cockpit_with_every_step_in_view(run, tmp_path, vp):
    look = _ev("const c = document.querySelector('[data-lpp=p3] .lp-cockpit'); if (!c) return null;"
               " return {text: c.textContent, steps: [...c.querySelectorAll('.lp-ck-step')].filter(vis).length,"
               " done: [...c.querySelectorAll('.lp-ck-step[aria-pressed=true]')].length,"
               " next: [...c.querySelectorAll('.lp-ck-step')].findIndex((b) => b.classList.contains('lp-ck-next')),"
               " edges: [...c.querySelectorAll('.lp-ck-edge[aria-pressed=true]')].length, code: c.querySelector('code').textContent};")
    got = _go(run, tmp_path, _coding(_model(_ctx())), [
        dict(OPEN, eval=look),
        {"click": "Say the task back", "within": "dialog.detail [data-lpp=p3] .lp-cockpit", "eval": look},
        {"click": "Missing weeks", "exact": True, "within": "dialog.detail [data-lpp=p3] .lp-cockpit", "eval": look},
    ], vp)
    before, ticked, edge = (a["eval"] for a in got["after"])
    assert before and before["steps"] == 4 and before["done"] == 0 and before["next"] == 0, before
    for words in ("Ask before you type", "Stuck? say:", "Name these", "Handy code", "With more time I'd add the promotions calendar."):
        assert words in before["text"], words
    assert before["code"] == "df.groupby('site')['pallets'].mean()"
    assert ticked["done"] == 1 and ticked["next"] == 1, "a tick marks the next step"
    assert edge["edges"] == 1


def test_a_coding_part_says_first_what_to_say_then_a_short_checklist(run, tmp_path):
    # The live review, 2026-11-11: on a phone 1100px of steps, each a box of its own, stood
    # between "Say first" and the problem's answer. What to say comes first, then the problem
    # as they set it and its answer, then the steps as a short checklist, then the rest.
    look = _ev("const p = document.querySelector('[data-lpp=p3]');"
               " const n = p.querySelectorAll('.lp-ck-step').length; const st = p.querySelector('.lp-ck-steps').__drawnRect();"
               " return {order: [...p.querySelectorAll('.lp-narr, .lp-q[data-lpq], .lp-cockpit')].map((x) => x.dataset.lpq || (x.classList.contains('lp-narr') ? 'say' : 'cockpit')),"
               " per: Math.round(st.height / n), heads: [...p.querySelectorAll('.lp-qhead')].map((x) => x.textContent)};")
    model = _coding(_model(_ctx()))
    lv = next(iv for iv in model["interviews"] if iv["id"] == IV)["live"]
    p3 = next(p for p in lv["parts"] if p["id"] == "p3")
    at = _go(run, tmp_path, model, [dict(OPEN, eval=look)], PHONE)["after"][0]["eval"]
    first, *rest = p3["questions"]
    assert at["order"] == ["say", first, "cockpit"] + rest, at["order"]
    assert at["heads"] == ["Questions likely in this part", "Other questions likely in this part"], at["heads"]
    assert at["per"] <= 72, ("a step is a line or two of a checklist, never a box a screen tall", at["per"])


def test_a_part_without_steps_has_no_cockpit(run, tmp_path):
    # The sample's coding part carries its steps, as the writer now fills one: it alone has a
    # cockpit. With its steps taken out, no part has one.
    model = _model(_ctx())
    lv = next(iv for iv in model["interviews"] if iv["id"] == IV)["live"]
    stepped = [p["id"] for p in lv["parts"] if p.get("steps")]
    look = "[...document.querySelectorAll('.lp-cockpit')].map((c) => c.closest('.lp-part').dataset.lpp)"
    got = _go(run, tmp_path, model, [dict(OPEN, eval=look)], WIDE)
    assert stepped == ["p3"] and got["after"][0]["eval"] == stepped, got["after"][0]["eval"]
    for p in lv["parts"]:
        p.pop("steps", None)
    got = _go(run, tmp_path, model, [dict(OPEN, eval=look)], WIDE)
    assert got["after"][0]["eval"] == []


def test_a_jump_lands_below_the_bar_not_behind_it(run, tmp_path, vp):
    # The live review, 2026-11-11: a chip, a link or a find pick scrolled its target to 12px from
    # the top, so the question and its first lines sat behind the sticky bar.
    look = _ev("const d = document.querySelector('dialog.detail'); const bar = d.querySelector('.lp-bar').offsetHeight;"
               "const m = (s) => parseFloat(getComputedStyle(d.querySelector(s)).scrollMarginTop);"
               "return {bar: bar, part: m('.lp-part'), q: m('.lp-q')};")
    at = _go(run, tmp_path, _model(_ctx()), [dict(OPEN, eval=look)], vp)["after"][0]["eval"]
    assert at["bar"] > 0 and at["part"] >= at["bar"] + 12 and at["q"] >= at["bar"] + 12, at
