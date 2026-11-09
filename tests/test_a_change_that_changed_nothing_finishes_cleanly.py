"""A change that changed nothing finishes cleanly: no spinner, never "Reply written" (T10).

A person's copy, 2026-11-09: changes asked with the pencil that Claude held, set aside or could
not make finished with nothing new on the page. The draft's row said "Finished · putting the
new version on your page" with its spinner for good, since it waited for a new version that
would never come; and on a person whose draft the change had set aside, the card said "Reply
written · Finished · Putting it on your page" for two hours. Now the finish says how it ended
(`app.py done --outcome held|set_aside|unchanged`), the card says it at once, and work that
changed nothing never waits for a version. A finished change whose new version has not
reached the page in a few minutes stops spinning and says it finished.

Every person and employer is invented (the page journeys' sample).
"""
from __future__ import annotations

import copy
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import test_the_page_journeys as journeys  # noqa: E402
from test_cards_say_claudes_work_once_and_keep_every_answer_in_reach import JUNO, PEN, T, _tweak  # noqa: E402
from test_the_page_journeys import WIDE, _go  # noqa: E402

HELD = "Held until she answers the earlier message."


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


def _held(outcome="held", rev="m1", finished="2026-10-25T08:58:00.000Z", answer=None):
    seed = _tweak("done", rev=rev, summary=HELD, finished_at=finished)
    w = seed["work/tweak~msg-juno-1~x"]
    w["result"]["outcome"] = outcome
    if answer:
        w["result"]["answer"] = answer
    return seed


def test_a_held_change_says_held_at_once_with_no_spinner(run, tmp_path):
    got = _go(run, tmp_path, [{"hash": "contacts", "eval": PEN}], WIDE, seed=_held(), clock=T)
    done = got["after"][0]["eval"]["done"]
    # In the person's words, then what happens next; never the engine's "Held" (the screen
    # review, 2026-11-09).
    assert done == "Not sent for now · Nothing to send until they reply.", done
    assert "putting" not in done and "New version" not in done, done
    spin = got["after"][0]["eval"]
    assert spin["stop"] == 0, spin


def test_a_change_set_aside_or_not_possible_says_so(run, tmp_path):
    for outcome, words in (("set_aside", "Not sent for now"), ("unchanged", "Kept as it was")):
        got = _go(run, tmp_path, [{"hash": "contacts", "eval": PEN}], WIDE, seed=_held(outcome), clock=T)
        done = got["after"][0]["eval"]["done"]
        assert done.startswith(words), (outcome, done)
        assert "putting" not in done and "Held" not in done, done


def test_a_written_answer_to_a_change_shows_on_its_card(run, tmp_path):
    said = "Her last message asked for a call, so a shorter note would drop the one thing she wanted."
    got = _go(run, tmp_path, [{"hash": "contacts", "eval": PEN}], WIDE,
              seed=_held("unchanged", answer=said), clock=T)
    done = got["after"][0]["eval"]["done"]
    assert done.startswith("Kept as it was") and said in done, done


def test_a_finished_change_stops_spinning_once_a_page_update_is_overdue(run, tmp_path):
    """No outcome said, and the version never came: after a few minutes it says it finished."""
    seed = _tweak("done", rev="m1", summary="Her message now asks straight for the call.",
                  finished_at="2026-10-25T08:30:00.000Z")
    got = _go(run, tmp_path, [{"hash": "contacts", "eval": PEN}], WIDE, seed=seed, clock=T)
    done = got["after"][0]["eval"]["done"]
    assert done.startswith("Finished: her message now asks"), done
    assert "putting" not in done, done


GOING = ("(() => { const c = document.querySelector('[data-item=\"%s\"]'); if (!c) return null;"
         " const g = c.querySelector('.going'); return {going: g ? g.innerText.replace(/\\s+/g, ' ').trim() : '',"
         " spin: !!(g && g.querySelector('.spin')), text: c.innerText}; })()" % JUNO)


def test_a_change_that_left_no_draft_never_says_reply_written(run, tmp_path):
    """The change set her draft aside: her card has no draft, and the finished change is not a
    reply about to arrive."""
    model = copy.deepcopy(journeys._sample())
    model["messages"] = [m for m in model.get("messages") or [] if m.get("contact") != JUNO]
    for outcome in ("set_aside", None):
        seed = _held(outcome) if outcome else _tweak("done", rev="m1", summary=HELD,
                                                     finished_at="2026-10-25T08:58:00.000Z")
        got = _go(run, tmp_path, [{"hash": "contacts", "eval": GOING}], WIDE, model=model,
                  seed=seed, clock=T)
        r = got["after"][0]["eval"]
        assert r is not None, "her card is on Contacts"
        assert "Reply written" not in r["text"] and "Putting it on your page" not in r["text"], r
        assert not r["spin"], r
        if outcome:
            assert r["going"].startswith("Not sent for now"), r


def test_a_change_that_changed_nothing_folds_away_after_two_hours(run, tmp_path):
    """"Not changed." stayed under a draft for good; after the two hours the person's card says
    it, it folds to "Claude answered <day> · Show" (the screen review, 2026-11-09)."""
    said = "Her last message asked for a call, so a shorter note would drop the one thing she wanted."
    later = "2026-10-25T11:30:00.000Z"
    got = _go(run, tmp_path, [{"hash": "contacts", "eval": PEN},
                              {"open": "tw-show:tweak~msg-juno-1~x", "eval": PEN}], WIDE,
              seed=_held("unchanged", answer=said), clock=later)
    folded, shown = got["after"][0]["eval"]["done"], got["after"][1]["eval"]["done"]
    assert folded.startswith("Claude answered") and "25 Oct" in folded and said not in folded, folded
    assert shown.startswith("Kept as it was") and said in shown, shown
    got = _go(run, tmp_path, [{"hash": "contacts", "eval": PEN}], WIDE, seed=_held(), clock=later)
    assert got["after"][0]["eval"]["done"] == "", got["after"][0]["eval"]


LINE = ("(() => { const g = document.querySelector('[data-going=\"%s\"]'); if (!g) return null;"
        " const kids = [...g.children].filter((e) => e.getClientRects().length);"
        " const lines = []; for (const e of kids) { for (const b of e.getClientRects()) {"
        " const top = Math.round(b.top); let l = lines.find((x) => Math.abs(x.top - top) < 4);"
        " if (!l) lines.push(l = {top, first: e.textContent}); } }"
        " return {text: g.textContent.replace(/\\s+/g, ' ').trim(),"
        " starts: lines.sort((a, b) => a.top - b.top).map((l) => l.first.trim())}; })()" % JUNO)


@pytest.mark.parametrize("vp", [WIDE, journeys.PHONE], ids=["wide", "phone"])
def test_her_cards_line_says_it_once_and_no_line_starts_with_a_dot(run, tmp_path, vp):
    """"Held · Held until she answers ..." said its word twice, and on a phone the wrapped line
    began "· Set her draft aside" (the screen review, 2026-11-09)."""
    model = copy.deepcopy(journeys._sample())
    model["messages"] = [m for m in model.get("messages") or [] if m.get("contact") != JUNO]
    seed = _held("set_aside")
    seed["work/tweak~msg-juno-1~x"]["result"]["summary"] = \
        "Set aside: she has two unanswered messages already."
    got = _go(run, tmp_path, [{"hash": "contacts", "eval": LINE}], vp, model=model, seed=seed,
              clock=T)
    r = got["after"][0]["eval"]
    assert r["text"] == "Not sent for now · She has two unanswered messages already.", r
    assert not any(x.startswith("·") for x in r["starts"]), r


WORK = ("[...document.querySelectorAll('[data-work]')].filter((e) => e.getClientRects().length)"
        ".map((e) => ({id: e.getAttribute('data-work'), phase: e.getAttribute('data-phase'),"
        " text: e.textContent.replace(/\\s+/g, ' ').trim()}))")
SHOW = ("(() => { const b = [...document.querySelectorAll('button')].filter((e) =>"
        " e.textContent.trim() === 'Show' && e.getClientRects().length).pop(); if (b) b.click();"
        " return !!b; })()")


def test_claudes_work_finishes_a_change_that_changed_nothing_at_once_with_its_result(run, tmp_path):
    """Claude's work said "Putting on page" with "Open in Contacts" for three minutes over a
    change that changed nothing, and the finished row lost Claude's answer (the screen
    review, 2026-11-09)."""
    answer = "Her last message asked for a call, so a shorter note would drop the one thing she wanted."
    seed = _held("unchanged", answer=answer, finished="2026-10-25T08:59:00.000Z")
    seed["work/tweak~msg-juno-1~x"]["result"]["summary"] = ""
    w2 = copy.deepcopy(seed["work/tweak~msg-juno-1~x"])
    w2["title"] = "Edit message: Kit at Harbourline"
    w2["finished_at"] = "2026-10-25T08:40:00.000Z"
    w2["result"] = {"links": [], "summary": "",
                    "answer": "Yes: the team is in the office three days a week."}
    seed["work/tweak~msg-kit-1~y"] = w2
    got = _go(run, tmp_path, [{"hash": "contacts", "wait": 300},
                              {"eval": SHOW}, {"wait": 300, "eval": WORK}], WIDE, seed=seed, clock=T)
    rows = {x["id"]: x for x in got["after"][-1]["eval"]}
    juno, kit = rows.get("tweak~msg-juno-1~x"), rows.get("tweak~msg-kit-1~y")
    assert juno and juno["phase"] == "done", rows
    assert "Putting on page" not in juno["text"] and "Open in" not in juno["text"], juno
    assert "Kept as it was · Her last message asked for a call" in juno["text"], juno
    assert kit and "Yes: the team is in the office three days a week." in kit["text"], kit
