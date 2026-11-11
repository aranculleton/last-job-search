"""Work with no word from Claude for a while has one banner over Claude's work, with Stop.

The audit of 2026-11-10 (PE-4, and its improvements list: "One page banner for any lapsed,
ownerless or refused state, with a Stop or Try again"): each job whose chat went quiet said
"May have stopped" on its own card, and work nobody took up said "No answer yet", so a person
found them one card at a time. One banner now counts them, says they are tried again by
themselves, and stops them in one tap. Work waiting on the person is never counted. Every
employer here is invented.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest  # noqa: E402

import test_the_page_journeys as journeys  # noqa: E402
from test_the_page_journeys import PHONE, WIDE, _go  # noqa: E402

T = "2026-10-25T09:00:00.000Z"
QUIET = {"kind": "draft", "title": "Draft: Kestrel Mutual", "to": "cloud", "args": {},
         "asked_at": "2026-10-25T07:30:00.000Z", "status": "running", "stage": 1,
         "stage_at": "2026-10-25T07:40:00.000Z", "claimed_by": "session_gone1",
         "claimed_at": "2026-10-25T07:35:00.000Z", "lease_until": "2026-10-25T08:10:00.000Z",
         "steps": [], "_v": 2}
BANNER = ("(() => { const b = document.querySelector('[data-k=\"quiet-banner\"]');"
          " return b ? {text: b.textContent, buttons: [...b.querySelectorAll('button')].map((x) => x.textContent)} : null; })()")


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


@pytest.mark.parametrize("vp", [PHONE, WIDE], ids=["phone", "wide"])
def test_one_banner_counts_the_quiet_jobs_and_stops_them(run, tmp_path, vp):
    seed = {"work/draft~kestrel": QUIET, "work/draft~oakmere": dict(QUIET, title="Draft: Oakmere Foods"),
            "work/follow_up~wren": {"kind": "follow_up", "title": "Follow up with Wren", "to": "cloud",
                                    "status": "needs_you", "note": "Did the call go ahead?", "args": {},
                                    "asked_at": "2026-10-25T07:00:00.000Z", "_v": 1}}
    # The work rail is open beside Jobs on a wide screen; a phone opens it from the pill.
    first = dict({"hash": "jobs", "wait": 200, "eval": BANNER}, **({"open": "pill"} if vp == PHONE else {}))
    got = _go(run, tmp_path, [first, {"click": "Stop them", "exact": True, "wait": 200}],
              vp, seed=seed, clock=T)
    banner = got["after"][0]["eval"]
    assert banner and banner["text"].startswith("2 jobs have had no word from Claude"), banner
    # What really happens to them, said for each (the review of 2026-11-11): each stopped once,
    # so each is started again by Claude.
    assert "2 are started again by Claude" in banner["text"] and "by itself" not in banner["text"], banner
    assert banner["buttons"] == ["Stop them"], banner
    stopped = {w["id"]: w for w in got["after"][-1]["work"]}
    assert stopped["draft~kestrel"].get("stop_asked") and stopped["draft~oakmere"].get("stop_asked")
    assert not stopped["follow_up~wren"].get("stop_asked")


def test_no_banner_while_work_is_going(run, tmp_path):
    going = dict(QUIET, lease_until="2026-10-25T09:20:00.000Z", stage_at="2026-10-25T08:55:00.000Z")
    got = _go(run, tmp_path, [{"hash": "jobs", "wait": 200, "eval": BANNER}], WIDE,
              seed={"work/draft~kestrel": going}, clock=T)
    assert got["after"][0]["eval"] is None


def test_its_first_half_hour_without_a_word_it_waits_for_its_chat(run, tmp_path):
    """The audit of 2026-11-10 (PE-12): the engine waits a lease after a claim's lease runs out
    before it starts the job again or ends it, and the card said "May have stopped" at once."""
    card = ("(() => { const c = document.querySelector('[data-work=\"draft~kestrel\"]');"
            " return c ? c.textContent : null; })()")
    # Run by a job chat of its own (run_by), which the engine waits for a lease more; any other
    # job is taken up again at once, so it has no such wait (the review of 2026-11-11).
    lately = dict(QUIET, lease_until="2026-10-25T08:50:00.000Z", run_by="session_EXAMPLEchild1")       # ten minutes ago
    got = _go(run, tmp_path, [{"hash": "jobs", "wait": 200, "eval": card},
                              {"eval": BANNER}], WIDE, seed={"work/draft~kestrel": lately}, clock=T)
    text = got["after"][0]["eval"]
    assert "Waiting for its chat" in text and "may have stopped" not in text.lower(), text
    assert got["after"][1]["eval"] is None
    long_ago = _go(run, tmp_path, [{"hash": "jobs", "wait": 200, "eval": card}], WIDE,
                   seed={"work/draft~kestrel": QUIET}, clock=T)["after"][0]["eval"]
    assert "May have stopped" in long_ago, long_ago
    plain = _go(run, tmp_path, [{"hash": "jobs", "wait": 200, "eval": card}], WIDE,
                seed={"work/draft~kestrel": dict(QUIET, lease_until="2026-10-25T08:50:00.000Z")}, clock=T)["after"][0]["eval"]
    assert "May have stopped" in plain and "Waiting for its chat" not in plain, plain


def test_one_job_tried_twice_is_said_to_end_with_try_again(run, tmp_path):
    twice = dict(QUIET, attempt=2)
    got = _go(run, tmp_path, [{"hash": "jobs", "wait": 200, "eval": BANNER}], WIDE,
              seed={"work/draft~kestrel": twice}, clock=T)
    text = got["after"][0]["eval"]["text"]
    assert text.startswith("1 job has had no word from Claude for a while. It is ended, with Try again on its card."), text
