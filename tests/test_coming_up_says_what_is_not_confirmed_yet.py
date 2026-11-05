"""Coming up says what is asked for and not confirmed yet, and a call called off goes at once.

The maintainer, 2026-11-05: (12) a day asked for and not confirmed showed as if it were fixed;
now a booking the engine marks `tentative` says "Not confirmed yet" on Coming up and on the
Brief, and the box is there whenever the day is given (a new day on its row, a call booked).
(15) A booked call stayed in Coming up after it was called off, until the page was drawn
again: the page reads its own taps (`effective`) and takes it off at once. Every person and
employer is the invented sample's (tests/fixtures/app_model_sample.json).
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_the_page_journeys import _sample, browser  # noqa: E402
from test_the_page_works_in_a_browser import _write  # noqa: E402

WIDE = {"width": 1280, "height": 900}
CLOCK = "2026-10-25T09:00:00Z"
CALL = "up-call-harbourline-bank-bea-2026-10-29"
SCREEN = "up-app-larkspur-supply-phone-screen-2026-10-28"


@pytest.fixture(scope="module")
def run():
    yield from browser()


def _model():
    m = _sample()
    for u in m["upcoming"]:
        if u["id"] == CALL:
            u["tentative"] = True
    return m


def _row(uid):
    return '#main [data-item="%s"]' % uid


def test_a_booking_not_confirmed_says_so_and_a_call_called_off_goes_at_once(run, tmp_path):
    page = _write(tmp_path, "page", _model())
    got = run("engine", html=page, viewport=WIDE, clock=CLOCK, fake={"canSend": "available"}, steps=[
        {"hash": "interviews", "read": _row(CALL)},
        {"hash": "interviews", "read": _row(SCREEN)},
        {"hash": "brief", "eval": "[...document.querySelectorAll('#main .bp-up-row')].map((r) => r.innerText)"},
        {"hash": "interviews", "click": "The call is off: Call with Bea (Harbourline Bank)",
         "eval": "!!document.querySelector('#main [data-item=\"%s\"]')" % CALL},
    ])
    assert not got["errors"], got["errors"]
    assert "Not confirmed yet" in got["after"][0]["text"], got["after"][0]["text"]
    assert "Not confirmed yet" not in got["after"][1]["text"], got["after"][1]["text"]
    brief = got["after"][2]["eval"]
    assert any("Bea" in r and "Not confirmed yet" in r for r in brief), brief
    # Called off: gone from Coming up at once, before Claude has caught up.
    assert got["after"][3]["eval"] is False
    (a,) = [x for x in got["actions"] if x["action"] == "person.status"]
    assert a["item"] == "harbourline_bank_bea" and a["value"]["status"] == "in_conversation", a


SUBMIT_DAY = ("(() => { const f = document.querySelector('#main [data-k=\"fix-in:up-day:%s\"]').form;"
              " f.querySelector('input[type=date]').value = '2026-10-30';"
              " f.querySelector('input[type=checkbox]').click(); f.requestSubmit(); return true; })()" % SCREEN)


def test_a_new_day_and_a_call_can_each_be_marked_not_confirmed_yet(run, tmp_path):
    page = _write(tmp_path, "page", _model())
    got = run("engine", html=page, viewport=WIDE, clock=CLOCK, fake={"canSend": "available"}, steps=[
        {"hash": "interviews", "click": "Change the day: Phone screen: Larkspur Retail", "eval": SUBMIT_DAY},
        {"hash": "contacts", "click": "Change the call with Bea",
         "eval": "(() => { const d = document.querySelector('dialog[open]'); const c = [...d.querySelectorAll('label')].find((l) => l.textContent === 'Not confirmed yet');"
                 " const box = document.getElementById(c.htmlFor); const was = box.checked; box.click(); return was; })()"},
        {"submit": True},
    ])
    assert not got["errors"], got["errors"]
    moved = [x for x in got["actions"] if x["action"] == "outcome.interview"]
    assert moved and moved[-1]["value"]["on"] == "2026-10-30" and moved[-1]["value"]["tentative"] is True, moved
    # The call's box is shown as it stands, and ticked here.
    assert got["after"][1]["eval"] is False
    (call,) = [x for x in got["actions"] if x["action"] == "person.call_booked"]
    assert call["value"]["tentative"] is True and call["value"]["on"] == "2026-10-29", call
