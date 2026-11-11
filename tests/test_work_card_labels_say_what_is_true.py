"""A finished job has no Stop, and a job waiting for the computer has no running clock.

The audit of 2026-11-10 (DW-1): a finished computer job's only button was "Stop Claude", which
read as cancelling work already done, and a computer job nobody had picked up said "Waking
Claude" with a clock that read as stuck work. Checked here at phone and desktop width. Every
person and employer is invented.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest  # noqa: E402

import test_the_page_journeys as journeys  # noqa: E402
from test_the_page_journeys import PHONE, WIDE, _go  # noqa: E402

T = "2026-10-25T09:00:00.000Z"
SEED = {
    "work/network~done": {"kind": "network", "title": "Reading 4 profiles", "to": "computer",
                          "args": {"read_on_computer": True}, "asked_at": "2026-10-25T08:00:00.000Z",
                          "status": "done", "finished_at": "2026-10-25T08:50:00.000Z",
                          "claimed_by": "local-mac1", "result": {"summary": "Read 4 profiles.", "links": []},
                          "_v": 4},
    "work/network~waits": {"kind": "network", "title": "Reading 3 profiles", "to": "computer",
                           "args": {"read_on_computer": True}, "asked_at": "2026-10-25T08:40:00.000Z",
                           "status": "queued", "stage": 0, "steps": [], "_v": 1},
}
LOOK = ("(() => { const card = (id) => document.querySelector('[data-work=\"' + id + '\"]');"
        " const done = card('network~done'), waits = card('network~waits');"
        " const btns = (c) => c ? [...c.querySelectorAll('button')].map((b) => b.textContent) : null;"
        " return {doneButtons: btns(done), waitsText: waits ? waits.textContent : null,"
        " waitsClock: waits ? !!waits.querySelector('.wi-clock') : null}; })()")


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


@pytest.mark.parametrize("vp", [PHONE, WIDE], ids=["phone", "wide"])
def test_a_done_job_has_no_stop_and_a_computer_job_waiting_has_no_clock(run, tmp_path, vp):
    first = dict({"hash": "contacts", "wait": 200, "eval": LOOK}, **({"open": "pill"} if vp == PHONE else {}))
    got = _go(run, tmp_path, [first], vp, seed=SEED, clock=T)
    seen = got["after"][0]["eval"]
    assert seen["doneButtons"] is not None and not [b for b in seen["doneButtons"] if "Stop" in b], seen
    assert seen["waitsText"] and "Waiting for your computer" in seen["waitsText"], seen
    assert "Waking Claude" not in seen["waitsText"] and seen["waitsClock"] is False, seen
