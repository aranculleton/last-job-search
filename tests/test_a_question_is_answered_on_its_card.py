"""A question is answered on its card, with the control its answer needs (2026-11-05).

The maintainer's To do held an interview card with two bins side by side, "Not done" in a
pill and again in its line ("Not done: Which day is it? Give it as 28 Oct.") and one button,
"Say it in Chat"; and "Show 1 more" under a group still said so after it had shown the card.
Their ask: "the less things that can be done in chat the better, surely that one we could
just have a date picker". Each test taps the page as a person would and checks what reaches
the engine: a date picker (and the time) on the card, chips or a Yes and a No for a question
Claude asked with its kind of answer, a time picker on a Coming up row, and a fold whose
count goes once it has shown what it held. Every person and employer is invented
(tests/fixtures/app_model_sample.json).
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

T = "2026-10-25T09:00:00.000Z"
HEARD = {"chats/cloud-1": {"kind": "cloud", "seen_at": "2026-10-25T08:58:30.000Z", "watching": True},
         "meta/listener": {"chat": "cloud-1", "kind": "cloud", "answered_at": "2026-10-25T08:56:00.000Z", "since": "2026-10-24T08:00:00.000Z"}}


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


@pytest.fixture(params=[PHONE, WIDE], ids=["phone", "wide"])
def vp(request):
    return request.param


# ------------------------------------------------------------------ the fold says what it still holds


FOLD = ("(() => { const d = document.querySelector('#main details.band-more:not(.soon-more)'); if (!d) return null;"
        " d.open = false; const s = d.querySelector('summary'); const before = {text: s.textContent, shown: getComputedStyle(s).display !== 'none'};"
        " s.click(); return {before, open: d.open, after: getComputedStyle(s).display !== 'none' ? s.textContent : ''}; })()")
FOCUS = ("(() => { const d = document.querySelector('#main details.band-more:not(.soon-more)'); const a = document.activeElement;"
         " return !!d && !!a && d.contains(a) && a.hasAttribute('data-card'); })()")


def test_show_n_more_goes_once_it_has_shown_them_and_its_first_card_takes_the_focus(run, tmp_path, vp):
    got = _go(run, tmp_path, [{"hash": "todo", "eval": FOLD}, {"eval": FOCUS}], vp, clock=T)
    r = got["after"][0]["eval"]
    assert r, "To do folds the rest of today behind one line"
    assert r["before"]["shown"] and r["before"]["text"].startswith("Show "), r
    assert r["open"], r
    assert r["after"] == "", ("once it has shown them, nothing is left folded: the line goes", r)
    assert got["after"][1]["eval"], "the first card it showed takes the focus, not the page"


# ------------------------------------------------------------------ a refusal's question, on its card


def _refused(app_id):
    aid = "act~" + app_id + "~outcome.interview~old"
    return aid, dict(HEARD, **{
        "actions/" + aid: {"item": app_id, "action": "outcome.interview", "value": {"stage": "Phone screen"},
                           "at": "2026-10-25T08:50:00.000Z", "rev_seen": "r", "tab": "t0"},
        # The receipt an engine before 4.10 wrote: its question, and nothing saying what kind.
        "receipts/" + aid: {"result": "conflict", "note": "Which day is it? Give it as 2026-10-28.",
                            "applied_at": "2026-10-25T08:51:00Z", "by": "cloud-1"}})


def _card(aid):
    return ("(() => { const c = document.querySelector('[data-item=\"refused:" + aid + "\"]'); if (!c) return null;"
            " return {kind: c.querySelector('.kind').textContent, text: c.textContent, bins: c.querySelectorAll('[data-bin]').length,"
            " date: !!c.querySelector('input[type=date]'), time: !!c.querySelector('input[type=time]'),"
            " chat: [...c.querySelectorAll('button')].some((b) => /in Chat/.test(b.textContent)),"
            " notDone: (c.textContent.match(/Not done/g) || []).length}; })()")


def _fill(aid, day, time):
    return ("(() => { const c = document.querySelector('[data-item=\"refused:" + aid + "\"]');"
            " const set = (el, v) => { el.value = v; el.dispatchEvent(new Event('input', {bubbles: true})); };"
            " set(c.querySelector('input[type=date]'), '" + day + "'); set(c.querySelector('input[type=time]'), '" + time + "'); return true; })()")


def test_a_refused_day_is_given_with_a_date_picker_on_its_one_card_and_books_it(run, tmp_path, vp):
    m = copy.deepcopy(_sample())
    app = m["applications"][0]
    aid, seed = _refused(app["id"])
    within = '[data-item="refused:' + aid + '"]'
    got = _go(run, tmp_path, [
        {"hash": "todo", "eval": _card(aid)},
        {"eval": _fill(aid, "2026-10-30", "14:30")},
        {"click": "Send", "exact": True, "within": within, "eval": _card(aid)},
        {"receipts": True, "eval": _card(aid)},
    ], vp, model=m, seed=seed, clock=T)
    card = got["after"][0]["eval"]
    assert card, "the refused tap is a card in To do"
    assert card["kind"] == "Interview" and "28 Oct" in card["text"] and "2026-10-28" not in card["text"], card
    assert card["bins"] == 1, ("one bin a card, never two side by side", card)
    assert card["notDone"] == 1, ("Not done said once", card)
    assert card["date"] and card["time"], ("a date picker, with the time beside it", card)
    assert not card["chat"], ("never Say it in Chat for a question a control answers", card)
    sent = [a for a in got["actions"] if a["action"] == "outcome.interview" and a["item"] == app["id"] and a.get("at", "") > "2026-10-25T08:50:00.000Z"]
    assert sent, got["actions"]
    v = sent[-1]["value"]
    assert v["on"] == "2026-10-30" and v["time"] == "14:30" and v["stage"] == "Phone screen", v
    assert sent[-1]["rev_seen"] == app["rev"], ("pinned to the item as the page shows it", sent[-1])
    assert got["after"][3]["eval"] is None, "once Claude has booked it, the card has gone from To do"


def test_a_refusal_whose_reason_is_not_a_question_has_no_control_and_one_bin(run, tmp_path):
    m = copy.deepcopy(_sample())
    app = m["applications"][0]
    aid, seed = _refused(app["id"])
    seed["receipts/" + aid] = dict(seed["receipts/" + aid], note="Answered differently on your phone.")
    got = _go(run, tmp_path, [{"hash": "todo", "eval": _card(aid)}], WIDE, model=m, seed=seed, clock=T)
    card = got["after"][0]["eval"]
    assert card and card["bins"] == 1 and not card["date"] and not card["chat"], card


def test_a_refusal_naming_a_choice_is_answered_in_one_tap(run, tmp_path):
    """The engine's own `ask` (4.10): its kind and choices, drawn as chips, each sending the
    same tap again with that answer."""
    m = copy.deepcopy(_sample())
    app = m["applications"][0]
    aid, seed = _refused(app["id"])
    seed["receipts/" + aid] = dict(seed["receipts/" + aid], note="Which stage is it?",
                                   ask={"key": "stage", "label": "Which stage?", "kind": "choice", "type": "text",
                                        "choices": [{"value": "Phone screen", "label": "Phone screen"}, {"value": "Final round", "label": "Final round"}]})
    got = _go(run, tmp_path, [{"hash": "todo", "click": "Final round", "exact": True, "within": '[data-item="refused:' + aid + '"]'}], WIDE, model=m, seed=seed, clock=T)
    sent = [a for a in got["actions"] if a["action"] == "outcome.interview" and a.get("at", "") > "2026-10-25T08:50:00.000Z"]
    assert sent and sent[-1]["value"]["stage"] == "Final round", got["actions"]


# ------------------------------------------------------------------ a question Claude asked, with its kind


def _asking(answer, question="Which day did they offer?", about=""):
    w = {"kind": "follow_up", "title": "Follow up with Wren", "to": "cloud", "args": {}, "asked_at": "2026-10-25T08:40:00.000Z",
         "status": "needs_you", "note": question, "asked_you_at": "2026-10-25T08:45:00.000Z",
         "needs": {"question": question, "about": about, "work": "follow_up~wren", "answer": answer}, "_v": 3}
    return dict(HEARD, **{"work/follow_up~wren": w})


ASK_CARD = ("(() => { const c = document.querySelector('#main [data-item=\"work:follow_up~wren\"]'); if (!c) return null;"
            " return {text: c.textContent, quote: (c.querySelector('.ask-about') || {}).textContent || '', chips: [...c.querySelectorAll('.ask-choices button')].map((b) => b.textContent),"
            " date: !!c.querySelector('input[type=date]'), range: !!c.querySelector('input[type=range]'), answerBtn: [...c.querySelectorAll('button')].some((b) => b.textContent === 'Answer')}; })()")


def test_a_question_with_choices_is_chips_on_its_card_and_resumes_the_work(run, tmp_path, vp):
    seed = _asking({"key": "answer", "kind": "choice", "choices": [{"value": "keep", "label": "Keep it"}, {"value": "cut", "label": "Take it out"}]},
                   question="This line says you led the team. Keep it?", about="I led the pricing team at Harbourline")
    got = _go(run, tmp_path, [
        {"hash": "todo", "eval": ASK_CARD},
        {"click": "Take it out", "exact": True, "within": '#main [data-item="work:follow_up~wren"]',
         "eval": "[...document.querySelectorAll('[data-toast]')].map((t) => t.textContent).join(' | ')"},
    ], vp, seed=seed, clock=T)
    card = got["after"][0]["eval"]
    assert card and card["chips"] == ["Keep it", "Take it out"], card
    assert "I led the pricing team at Harbourline" in card["quote"], ("the words it is about, quoted", card)
    assert not card["answerBtn"], ("the control is on the card: no sheet, no chat", card)
    w = [x for x in got["work"] if x.get("title") == "Follow up with Wren"][-1]
    assert w["status"] == "queued", w
    assert w["args"]["answers"] == {"This line says you led the team. Keep it?": "cut"}, w["args"]
    assert "Sent: Take it out" in got["after"][1]["eval"] and "See it" in got["after"][1]["eval"], got["after"][1]["eval"]


def test_a_question_asking_for_a_day_is_a_date_picker_and_a_scale_a_slider(run, tmp_path):
    seed = _asking({"key": "answer", "kind": "date", "time": "time"})
    got = _go(run, tmp_path, [
        {"hash": "todo", "eval": ASK_CARD},
        {"eval": "(() => { const c = document.querySelector('#main [data-item=\"work:follow_up~wren\"]');"
                 " const set = (el, v) => { el.value = v; el.dispatchEvent(new Event('input', {bubbles: true})); };"
                 " set(c.querySelector('input[type=date]'), '2026-10-29'); set(c.querySelector('input[type=time]'), '09:15'); return true; })()"},
        {"click": "Send", "exact": True, "within": '#main [data-item="work:follow_up~wren"]'},
    ], WIDE, seed=seed, clock=T)
    assert got["after"][0]["eval"]["date"], got["after"][0]["eval"]
    w = [x for x in got["work"] if x.get("title") == "Follow up with Wren"][-1]
    assert w["args"]["answers"] == {"Which day did they offer?": "2026-10-29 at 09:15"}, w["args"]
    scale = _go(run, tmp_path, [{"hash": "todo", "eval": ASK_CARD}], WIDE, seed=_asking({"key": "answer", "kind": "scale", "min": 1, "max": 5}, question="How sure are you?"), clock=T)
    assert scale["after"][0]["eval"]["range"], scale["after"][0]["eval"]


def test_the_same_question_in_claudes_work_has_its_control_too(run, tmp_path):
    seed = _asking({"key": "answer", "kind": "yesno"}, question="Did the call go ahead?")
    look = ("(() => { const c = document.querySelector('[data-work=\"follow_up~wren\"]'); if (!c) return null;"
            " return [...c.querySelectorAll('.ask-choices button')].map((b) => b.textContent); })()")
    got = _go(run, tmp_path, [{"hash": "todo", "open": "pill", "eval": look}], WIDE, seed=seed, clock=T)
    assert got["after"][0]["eval"] == ["Yes", "No"], got["after"][0]["eval"]


# ------------------------------------------------------------------ Coming up: the time on its row


def test_add_the_time_on_a_coming_up_row_is_a_time_picker_that_books_it(run, tmp_path, vp):
    row = "up-app-harbourline-risk-second-interview-2026-11-04"
    within = '[data-item="' + row + '"]'
    got = _go(run, tmp_path, [
        {"hash": "interviews", "click": "Add the time: Second interview: Harbourline Bank", "exact": True,
         "eval": "!!document.querySelector('" + within + " input[type=time]')"},
        {"eval": "(() => { const i = document.querySelector('" + within + " input[type=time]'); i.value = '10:30'; i.dispatchEvent(new Event('input', {bubbles: true})); return true; })()"},
        {"click": "Send", "exact": True, "within": within, "eval": "[...document.querySelectorAll('[data-toast]')].map((t) => t.textContent).join(' | ')"},
    ], vp, seed=HEARD, clock=T)
    assert got["after"][0]["eval"], "the row opens a time picker in place, never a line begun in Chat"
    sent = [a for a in got["actions"] if a["action"] == "outcome.interview"]
    assert sent, got["actions"]
    v = sent[-1]["value"]
    assert sent[-1]["item"] == "int-harbourline-risk" and v["on"] == "2026-11-04" and v["time"] == "10:30" and v["stage"] == "Second interview", sent[-1]
    # Said at once in its toast, which carries the Undo while it is up (DESIGN.md, the bin).
    assert "Time added" in got["after"][2]["eval"] and "10:30" in got["after"][2]["eval"], got["after"][2]["eval"]


def test_a_booked_interview_is_moved_from_its_coming_up_row_with_its_pencil(run, tmp_path, vp):
    """To do could move an interview and Coming up could not (the UX review, 2026-11-05)."""
    row = "up-app-larkspur-supply-phone-screen-2026-10-28"
    within = '[data-item="' + row + '"]'
    got = _go(run, tmp_path, [
        {"hash": "interviews", "click": "Change the day: Phone screen: Larkspur Retail", "exact": True,
         "eval": "!!document.querySelector('" + within + " input[type=date]')"},
        {"eval": "(() => { const c = document.querySelector('" + within + "'); const set = (el, v) => { el.value = v; el.dispatchEvent(new Event('input', {bubbles: true})); };"
                 " set(c.querySelector('input[type=date]'), '2026-10-30'); set(c.querySelector('input[type=time]'), '15:00'); return true; })()"},
        {"click": "Send", "exact": True, "within": within},
    ], vp, seed=HEARD, clock=T)
    assert got["after"][0]["eval"], "the pencil opens the day and time in place"
    sent = [a for a in got["actions"] if a["action"] == "outcome.interview"][-1]
    assert sent["item"] == "int-larkspur-supply" and sent["value"]["on"] == "2026-10-30" and sent["value"]["time"] == "15:00" \
        and sent["value"]["stage"] == "Phone screen", sent


def test_finished_work_says_it_is_being_put_on_the_page_until_the_page_has_it(run, tmp_path):
    """DESIGN.md, "Moving parts" (2): "Done" only once the result is on the page; finished a
    minute ago with the page's model made before it, it says so instead, with no reload."""
    w = {"kind": "follow_up", "title": "Follow up with Wren", "to": "cloud", "args": {}, "asked_at": "2026-10-25T08:40:00.000Z",
         "status": "done", "finished_at": "2026-10-25T08:59:00.000Z", "result": {"summary": "Your follow-up is drafted.", "links": []}, "_v": 4}
    label = "(document.querySelector('[data-work=\"follow_up~wren\"] .state-word') || {}).textContent || ''"
    m = copy.deepcopy(_sample())
    before = _go(run, tmp_path, [{"hash": "todo", "eval": label}], WIDE, model=m, seed=dict(HEARD, **{"work/follow_up~wren": w}), clock=T)
    assert before["after"][0]["eval"] == "Finished: putting it on your page", before["after"][0]["eval"]
    m["made_at"] = "2026-10-25T08:59:30Z"
    after = _go(run, tmp_path, [{"hash": "todo", "eval": label}], WIDE, model=m, seed=dict(HEARD, **{"work/follow_up~wren": w}), clock=T)
    assert after["after"][0]["eval"] == "Done", after["after"][0]["eval"]


def test_an_answer_shows_its_work_going_at_once_and_can_be_called_off_with_the_answer_kept(run, tmp_path):
    """DESIGN.md, "Moving parts": the tap shows at once where the work is drawn (Claude's work
    card, the one drawing of work), with one plain way to call it off while it waits, and
    what the person gave is kept."""
    seed = _asking({"key": "answer", "kind": "yesno"}, question="Did the call go ahead?")
    card = ("(() => { const c = document.querySelector('[data-work=\"follow_up~wren\"]'); if (!c) return null;"
            " return {text: c.textContent, off: [...c.querySelectorAll('button')].map((b) => b.textContent).filter((t) => /Don.t do it|^Stop$/.test(t))}; })()")
    got = _go(run, tmp_path, [
        {"hash": "todo", "click": "Yes", "exact": True, "within": '#main [data-item="work:follow_up~wren"]', "eval": card},
        {"click": "Don't do it: Follow up with Wren", "exact": True, "within": '[data-work="follow_up~wren"]', "eval": card},
    ], WIDE, seed=seed, clock=T)
    first = got["after"][0]["eval"]
    assert first and "Needs your answer" not in first["text"], first
    assert first["off"] == ["Don't do it"], ("one way to call it off while it waits", first)
    queued = [x for x in got["after"][0]["work"] if x.get("title") == "Follow up with Wren"][-1]
    assert queued["status"] == "queued", queued
    w = [x for x in got["work"] if x.get("title") == "Follow up with Wren"][-1]
    assert w.get("stop_asked") or w["status"] == "stopped", w
    assert w["args"]["answers"] == {"Did the call go ahead?": "yes"}, ("the answer is kept", w["args"])
