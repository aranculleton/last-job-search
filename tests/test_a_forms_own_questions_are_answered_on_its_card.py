"""A form's own questions, asked on the application's card and answered there.

A form asks more than the resume and the letter answer ("why us?", "why this role?", "a time
you used X"), and the person had nowhere to put them (the maintainer, 2026-11-05). One box,
opened from "Questions on the form" under a Drafts, Applied or drafted Found card's More,
queues `form_answers` for that application; the card says where it stands in the words its
card in Claude's work uses, with Cancel while it waits or runs, why it failed with Try again,
and Done only once the answers are on the card, each with its Copy. The answers are kept in the
application's own screening_answers.md (tools/form_answers.py), never in the resume or the
letter. Every person and employer is invented (tests/fixtures/app_model_sample.json).
"""
from __future__ import annotations

import copy
import datetime as dt
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import test_the_page_journeys as journeys  # noqa: E402
from test_the_page_journeys import PHONE, WIDE, _go, _sample  # noqa: E402

T = "2026-10-25T09:00:00Z"
DRAFT = "app-ellerwick-insight"
CARD = '[data-item="%s"]' % DRAFT
LINE = CARD + " .work-inline"
WID = "form_answers~seeded"
ASKED = "Why do you want to work at Ellerwick Trust?\nTell us about a time you used SQL to answer a question."


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


def _at(minutes: int) -> str:
    t = dt.datetime(2026, 10, 25, 9, 0, tzinfo=dt.timezone.utc) - dt.timedelta(minutes=minutes)
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def _work(status="queued", **more):
    doc = {"kind": "form_answers", "title": "Answers for the form: Ellerwick Trust, Research Analyst", "to": "cloud",
           "args": {"item": DRAFT, "slug": "ellerwick_trust_research_analyst", "company": "Ellerwick Trust",
                    "role": "Research Analyst", "text": ASKED},
           "asked_at": _at(2), "status": status, "stages": [], "stage": 0, "stage_at": None, "steps": [],
           "claimed_by": None, "claimed_at": None, "stop_asked": False, "attempt": 1}
    doc.update(more)
    return doc


RUNNING = dict(status="running", claimed_by="cloud-1", claimed_at=_at(1), stage=1, stage_at=_at(1), lease_until="2026-10-25T09:20:00Z")


def _answered(m):
    m = copy.deepcopy(m)
    a = next(x for x in m["ready"] if x["id"] == DRAFT)
    a["screening"] = list(a.get("screening") or []) + [
        {"q": "Why do you want to work at Ellerwick Trust?", "a": "Its research reaches the people it is written for."}]
    return m


def test_the_box_queues_answers_for_that_application_and_the_card_says_so_at_once(run, tmp_path):
    got = _go(run, tmp_path, [
        {"hash": "drafts", "more": DRAFT, "click": "Questions on the form: Ellerwick Trust, Research Analyst"},
        {"fill": {"Questions on the form": ASKED}, "read": "dialog"},
        {"submit": True, "read": LINE},
    ], WIDE, clock=T)
    assert "Your CV and letter change only where you ask." in got["after"][1]["dialog"], got["after"][1]["dialog"]
    work = [w for w in got["work"] if w.get("kind") == "form_answers"]
    assert len(work) == 1, got["work"]
    assert work[0]["args"]["item"] == DRAFT and work[0]["args"]["text"] == ASKED, work[0]["args"]
    assert got["after"][2]["text"].startswith("Saved."), got["after"][2]["text"]
    assert "Cancel" in got["after"][2]["text"]


def test_each_state_is_said_on_the_card_and_done_only_once_the_answers_are_on_it(run, tmp_path):
    m = _sample()
    seed = {"work/" + WID: _work(**RUNNING)}
    done = _work(**dict(RUNNING, status="done", finished_at=_at(0),
                                result={"summary": "1 answer ready to copy on its card.", "links": [],
                                        "questions": ["Why do you want to work at Ellerwick Trust?"]}))
    failed = _work(**dict(RUNNING, status="failed", finished_at=_at(0), error="The posting was not in its folder"))
    got = _go(run, tmp_path, [
        {"hash": "drafts", "read": LINE, "count": LINE + " .spin"},
        {"write": {"work/" + WID: done}, "read": LINE},
        {"view": {"ready": _answered(m)["ready"]}, "read": LINE},
        # The line itself opens the answer where it is (2026-11-05: it said "under More", and
        # More held only the box to ask again).
        {"click": "Show it", "read": CARD + " .send"},
        {"write": {"work/" + WID: failed}, "read": LINE},
    ], WIDE, model=m, seed=seed, clock=T)
    running, unshown, shown, copy_row, broke = (x for x in got["after"])
    assert running["text"].startswith("Claude is on it: writing your answers"), running["text"]
    assert running["count"] == 1 and "Cancel" in running["text"], "its spinner, and Cancel"
    assert "Finished: putting it on your page." in unshown["text"], unshown["text"]
    assert shown["text"].startswith("Done: 1 answer ready to copy.") and "Show it" in shown["text"], shown["text"]
    assert "Its research reaches the people it is written for." in copy_row["text"], "opened, with its answer"
    assert broke["text"].startswith("Claude could not finish this: The posting was not in its folder."), broke["text"]
    assert "Try again" in broke["text"]


def test_cancel_while_it_waits_takes_it_off_at_once_and_keeps_the_words(run, tmp_path):
    seed = {"work/" + WID: _work("queued")}
    got = _go(run, tmp_path, [
        {"hash": "drafts", "read": LINE},
        {"click": "Cancel: Answers for the form: Ellerwick Trust, Research Analyst", "count": "#main " + LINE},
        {"more": DRAFT, "click": "Questions on the form: Ellerwick Trust, Research Analyst",
         "eval": "document.querySelector('dialog textarea').value"},
    ], PHONE, seed=seed, clock=T)
    assert got["after"][0]["text"].startswith("Saved."), got["after"][0]["text"]
    assert got["after"][1]["count"] == 0, "called off before Claude began: gone at once"
    w = next(x for x in got["work"] if x.get("kind") == "form_answers")
    assert w["status"] == "stopped" and w["stop_asked"], w
    assert got["after"][2]["eval"] == ASKED, "their words wait in the box"


def test_cancel_while_it_runs_says_stopping_then_stopped(run, tmp_path):
    seed = {"work/" + WID: _work(**RUNNING)}
    stopped = _work(**dict(RUNNING, status="stopped", stop_asked=True, finished_at=_at(0)))
    got = _go(run, tmp_path, [
        {"hash": "drafts", "click": "Cancel: Answers for the form: Ellerwick Trust, Research Analyst", "read": LINE},
        {"write": {"work/" + WID: stopped}, "read": LINE},
    ], WIDE, seed=seed, clock=T)
    assert got["after"][0]["text"] == "Stopping after this step.", got["after"][0]["text"]
    assert got["after"][1]["text"] == "Stopped. Nothing more is done on it.", got["after"][1]["text"]


def test_an_applied_card_and_a_drafted_found_card_take_the_form_too(run, tmp_path):
    m = _sample()
    sent = next(a for a in m["applications"] if a["id"] == "app-harbourline-risk")
    sent["screening"] = [{"q": "Why Harbourline Bank?", "a": "Its credit risk team works on the questions I have."}]
    seed = {"work/" + WID: _work(**RUNNING)}
    got = _go(run, tmp_path, [
        {"hash": "jobs", "click": "Applied"},
        {"more": "app-harbourline-risk", "click": "Details: Harbourline Bank, Credit Risk Analyst", "read": '[data-item="app-harbourline-risk"]'},
        {"click": "To apply", "exact": False},
        {"more": DRAFT, "read": CARD},
    ], WIDE, model=m, seed=seed, clock=T)
    applied, found = got["after"][1]["text"], got["after"][3]["text"]
    assert "Questions on the form" in applied and "Show it" in applied, applied
    assert "Claude is on it: writing your answers" in found and "Questions on the form" in found, found


def test_an_answer_is_kept_with_the_application_and_read_back_on_its_card(tmp_path):
    """tools/form_answers.py writes the answer the card's parser reads, a draft example marked
    for the person to confirm, and the same question answered again replaces its answer."""
    import app_model
    import form_answers
    import screening_answers  # noqa: F401  the file it writes beside
    folder = str(tmp_path / "app")
    os.makedirs(folder)
    with open(os.path.join(folder, "screening_answers.md"), "w", encoding="utf-8") as fh:
        fh.write("# Screening answers\n\n### Do you need sponsorship?\n\n**No**\n\nA note.\n\n---\n\nAnswers given on a portal.\n")
    form_answers.add(folder, "Why Ellerwick Trust?", "Its research reaches\nthe people it is for.")
    form_answers.add(folder, "A time you used SQL?", "I built the weekly stock report in SQL.", draft=True)
    form_answers.add(folder, "Why Ellerwick Trust?", "Its research is read by the people it is for.")
    got = app_model._screening(folder)
    assert [x["q"] for x in got] == ["Do you need sponsorship?", "Why Ellerwick Trust?", "A time you used SQL?"]
    assert got[1]["a"] == "Its research is read by the people it is for."
    assert got[2]["why"].startswith("A draft for you to confirm"), got[2]
    with open(os.path.join(folder, "screening_answers.md"), encoding="utf-8") as fh:
        assert fh.read().rstrip().endswith("Answers given on a portal."), "its closing note stays last"
