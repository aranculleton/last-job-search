"""Work waiting for Claude says when it starts and what starts it now.

The UX review of 2026-11-10 (U-15): a card said "Claude starts it when it next looks at this
page" and the pill "1 waiting", and neither said when that would be or what the person could
do. The card now says Claude's helper for the page starts it when it next answers, or the next
brief starts one, and the one thing that starts it now; on a wide screen the pill says what it waits for. Every
person and employer here is the sample's, invented.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest  # noqa: E402

import test_the_page_journeys as journeys  # noqa: E402
from test_the_page_journeys import PHONE, WIDE, _go  # noqa: E402

T = "2026-10-25T09:00:00.000Z"
SEED = {"work/evaluate~k1": {"kind": "evaluate", "title": "Look at the Kestrel Mutual posting",
                             "to": "cloud", "args": {}, "asked_at": "2026-10-25T08:58:00.000Z",
                             "status": "queued", "stage": 0, "steps": [], "_v": 1}}
CARD = ("(() => { const c = document.querySelector('[data-work=\"evaluate~k1\"]');"
        " const p = document.querySelector('#pill');"
        " return {card: c ? c.textContent : '', pill: p ? p.textContent : ''}; })()")


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


@pytest.mark.parametrize("vp", [PHONE, WIDE], ids=["phone", "wide"])
def test_a_waiting_card_says_when_it_starts_and_how_to_start_it_now(run, tmp_path, vp):
    got = _go(run, tmp_path, [{"hash": "jobs", "open": "pill", "wait": 200, "eval": CARD}], vp,
              seed=SEED, clock=T)
    seen = got["after"][0]["eval"]
    # What really starts it (the review of 2026-11-11): the chat that answers this page, or the
    # next brief; any other chat open takes no queued work.
    assert "helper for this page starts it when it next answers" in seen["card"], seen
    assert "next time one of your Claude chats is open" not in seen["card"], seen
    assert "when it next looks at this page" not in seen["card"], seen
    # Asked two minutes ago, Claude not yet past its quiet time: nothing on the page starts it
    # sooner, so no control is named (the screen review, 2026-11-11).
    assert "to start it now" not in seen["card"], seen
    if vp == WIDE:
        assert "1 waiting for Claude" in seen["pill"], seen


# The README's picture: a search running in a chat of its own and a draft asked after it.
_RUN = "2026-10-25T08:56:40.000Z"
BUSY = {"work/search~1": {"kind": "search", "title": "Finding jobs", "to": "cloud", "args": {}, "asked_at": _RUN, "status": "running",
                          "claimed_by": "cloud-1", "claimed_at": _RUN, "stage": 1, "stage_at": "2026-10-25T08:58:30.000Z",
                          "stages": [{"name": "Getting started", "est_s": 60}, {"name": "Searching job sites", "est_s": 300}, {"name": "Scoring", "est_s": 120}],
                          "steps": [{"at": _RUN, "text": "Searching 4 job sites and 12 employers"}], "_v": 1},
        "work/draft~r12-2": {"kind": "draft", "title": "CV and letter: Larkspur Retail, Senior Supply Chain Analyst", "to": "cloud", "args": {},
                             "asked_at": "2026-10-25T08:59:20.000Z", "status": "queued", "stage": 0, "steps": [], "_v": 1}}
DRAFT = ("(() => { const c = document.querySelector('[data-work=\"draft~r12-2\"]');"
         " const wake = [...document.querySelectorAll('#main button, #main a')].filter((b) => /^(Wake|Open) Claude$/.test(b.textContent.trim()));"
         " return {card: c ? c.textContent : '', wake: wake.length}; })()")


@pytest.mark.parametrize("vp", [PHONE, WIDE], ids=["phone", "wide"])
def test_work_waiting_while_claude_is_at_work_names_no_button_that_is_not_there(run, tmp_path, vp):
    # "Wake Claude in To do to start it now" while the header said Claude was running, and To
    # do had no Wake Claude: it shows only while Claude is not answering. Nor "if none is
    # answering" beside a running search (the screen review, 2026-11-11).
    got = _go(run, tmp_path, [{"hash": "todo", "open": "pill", "wait": 200, "eval": DRAFT}], vp, seed=BUSY, clock=T)
    seen = got["after"][0]["eval"]
    assert "helper for this page starts it when it next answers" in seen["card"], seen
    assert "if none is answering" not in seen["card"] and "Claude to start it now" not in seen["card"], seen
    assert seen["wake"] == 0, seen


QUIET = {"work/evaluate~k1": dict(SEED["work/evaluate~k1"], asked_at="2026-10-25T08:40:00.000Z")}


@pytest.mark.parametrize("vp", [PHONE, WIDE], ids=["phone", "wide"])
def test_work_waiting_past_claudes_quiet_time_names_to_dos_wake_claude_which_is_there(run, tmp_path, vp):
    got = _go(run, tmp_path, [{"hash": "todo", "open": "pill", "wait": 200, "eval": CARD},
                              {"eval": "[...document.querySelectorAll('#main [data-k=\"wake\"]')].map((b) => b.textContent.trim())"}],
              vp, seed=QUIET, clock=T)
    seen, wake = got["after"][0]["eval"], got["after"][1]["eval"]
    assert "Wake Claude in To do to start it now." in seen["card"], seen
    assert wake == ["Wake Claude"], wake


INLINE = """(() => { const i = document.querySelector('#main [data-work-inline="draft~r12-2"]');
  const r = document.querySelector('#rail [data-work="draft~r12-2"]');
  return {card: i ? i.textContent : null, rail: r ? r.textContent : null}; })()"""


@pytest.mark.parametrize("vp", [PHONE, WIDE], ids=["phone", "wide"])
def test_beside_claudes_work_a_cards_line_says_its_state_and_the_panel_the_rest(run, tmp_path, vp):
    # With Claude's work open beside Jobs, the queued draft said its whole sentence twice on one
    # screen, on its card and in the panel (the screen review, 2026-11-11). Beside the panel the
    # card says its state in a line; on a phone, with no panel beside it, it says it all.
    got = _go(run, tmp_path, [{"hash": "jobs", "eval": INLINE}], vp, seed=BUSY, clock=T)
    seen = got["after"][0]["eval"]
    assert seen["card"], seen
    if vp == WIDE:
        assert "helper for this page" in seen["rail"] and "helper for this page" not in seen["card"], seen
        assert "Waiting for Claude" in seen["card"] or "waiting for Claude" in seen["card"], seen
    else:
        assert "helper for this page" in seen["card"], seen
