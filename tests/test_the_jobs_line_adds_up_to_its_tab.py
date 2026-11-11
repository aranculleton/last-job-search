"""The line at the head of Jobs is one sentence whose total is the tab's.

The UX review of 2026-11-10 (U-9): the line read "4 to send, 1 still to make, 1 to look at,
1 strong. 2 need your answer." under a tab saying "To apply 5", and "send" read against the
page's own "nothing is ever sent". It now says the tab's total first and what it is made of.
Every person and employer is the sample's, invented.
"""
from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest  # noqa: E402

import test_the_page_journeys as journeys  # noqa: E402
from test_the_page_journeys import PHONE, WIDE, _go  # noqa: E402

T = "2026-10-25T09:00:00Z"
LOOK = ("(() => ({line: (document.querySelector('#main .summary') || {}).textContent || '',"
        " tab: [...document.querySelectorAll('#main button, #main [role=radio], #main label')].map((b) => b.textContent).find((t) => /^To apply/.test(t.trim())) || ''}))()")


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


@pytest.mark.parametrize("vp", [PHONE, WIDE], ids=["phone", "wide"])
def test_the_line_says_the_tabs_total_and_what_makes_it_up(run, tmp_path, vp):
    got = _go(run, tmp_path, [{"hash": "jobs", "eval": LOOK}], vp, clock=T)
    seen = got["after"][0]["eval"]
    tab = int(re.search(r"(\d+)", seen["tab"]).group(1))
    m = re.match(r"\s*(\d+) to apply to: (.*?)\.", seen["line"])
    assert m and int(m.group(1)) == tab, seen
    parts = [int(x) for x in re.findall(r"(\d+) (?:ready|waiting on you|being made|still to make|to look at)", m.group(2))]
    assert sum(parts) == tab, seen
    assert " to send" not in seen["line"] and "strong" not in seen["line"], seen


def test_ready_is_only_a_draft_nothing_waits_on_and_being_made_only_one_that_is(run, tmp_path):
    """The review of 2026-11-11: "3 ready ... 2 need your answer" counted drafts with a question
    as ready, and "being made" counted drafts nothing was making (never started, or stopped)."""
    got = _go(run, tmp_path, [{"hash": "jobs", "eval": LOOK}], WIDE, clock=T)
    line = got["after"][0]["eval"]["line"]
    # The draft that asks is "1 waiting on you", said once: "One needs your answer." after it
    # counted the same question again (2026-11-11).
    assert "2 ready, 1 waiting on you" in line and "your answer" not in line, line
    from test_the_page_journeys import _sample
    m = _sample()
    for a in m["ready"]:
        a["checks"] = {"passed": False, "line": "Not made yet"}
        a["alerts"] = [x for x in a.get("alerts") or [] if x.get("kind") != "checks"]
    got = _go(run, tmp_path, [{"hash": "jobs", "eval": LOOK}], WIDE, model=m, clock=T)
    line = got["after"][0]["eval"]["line"]
    assert "still to make" in line and " ready" not in line.split(":")[1].split(",")[0], line


BOTH = ("(() => { const line = (document.querySelector('#main .summary') || {}).textContent || '';"
        " return line; })()")
BRIEF = "(document.querySelector('#main [data-k=\"bp-drafts\"]') || {}).textContent || ''"


@pytest.mark.parametrize("vp", [PHONE, WIDE], ids=["phone", "wide"])
def test_the_brief_counts_the_drafts_as_jobs_does(run, tmp_path, vp):
    # The Brief said "3 drafts ready to apply, 1 being made" over Jobs' "2 ready, 1 waiting on
    # you, 1 being made": the draft with a question was ready on one screen and waiting on you
    # on the other (the screen review, 2026-11-11). One tally says both.
    got = _go(run, tmp_path, [{"hash": "jobs", "eval": BOTH}, {"hash": "brief", "eval": BRIEF}], vp, clock=T)
    jobs, brief = got["after"][0]["eval"], got["after"][1]["eval"]
    for word in ("ready", "waiting on you", "being made", "still to make"):
        j = re.search(r"(\d+) " + word, jobs)
        b = re.search(r"(\d+) (?:drafts? )?" + word, brief)
        # What Claude is making is its own work, said in the work pill: the Brief names it only
        # when nothing else is owed, and then in Jobs' number (4.15.0, a small laptop's panel).
        if word == "being made" and b is None and any(re.search(r"\d+ (?:drafts? )?" + w, brief) for w in ("ready", "waiting on you", "still to make")):
            continue
        assert (j and j.group(1)) == (b and b.group(1)), (word, jobs, brief)


CUT = ("(() => { const a = document.querySelector('#main [data-k=\"bp-drafts\"]'); if (!a) return null;"
       " return [a, ...a.querySelectorAll('*')].filter((e) => e.scrollWidth > e.clientWidth + 1 || e.scrollHeight > e.clientHeight + 1)"
       ".map((e) => e.tagName + ' ' + e.textContent); })()")


@pytest.mark.parametrize("vp", [PHONE, WIDE, {"width": 1600, "height": 900}], ids=["phone", "wide", "laptop"])
def test_the_briefs_drafts_line_is_said_whole(run, tmp_path, vp):
    # The README's picture of 4.15.0 showed "2 drafts ready to apply, 1 waiting on you, 1 being..."
    # cut off: the rule that keeps a job's title on one line in the Jobs panel took the panel's
    # lead too, which the Brief says in full, never with "..." (app.css, .bp-lead).
    got = _go(run, tmp_path, [{"hash": "brief", "eval": CUT}], vp, clock=T)
    assert got["after"][0]["eval"] == [], got["after"][0]["eval"]
