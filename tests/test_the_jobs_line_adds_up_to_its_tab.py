"""The line at the head of Jobs is one sentence whose total is the tab's.

The UX review of 2026-11-10 (U-9): the line read "4 to send, 1 still to make, 1 to look at,
1 strong. 2 need your answer." under a tab saying "To apply 5", and "send" read against the
page's own "nothing is ever sent". It now says the tab's total first and what it is made of.
Since the redesign's second round (2026-11-17) what it is made of is the list's own headings,
in their words and order, then the fold's "Did you apply?" count: "2 ready, 1 waiting on you,
1 being made, 1 to look at" matched none of the headings. Every person and employer is the
sample's, invented.
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
        " tab: [...document.querySelectorAll('#main button, #main [role=radio], #main label')].map((b) => b.textContent).find((t) => /^To apply/.test(t.trim())) || '',"
        " heads: [...document.querySelectorAll('#main .job-group > .list-head')].map((x) => x.textContent.trim()),"
        " stages: [...document.querySelectorAll('#main .job-groups .card[data-stage], #main .stack.jobs > .card[data-stage]')].filter((c) => !c.closest('details')).map((c) => c.getAttribute('data-stage')),"
        " fold: [...document.querySelectorAll('#main details.confirm-fold .card')].map((c) => c.getAttribute('data-item')),"
        " foldSays: ((document.querySelector('#main details.confirm-fold > summary') || {}).textContent || '').trim()}))()")
WORDS = {"0": "needs your answer", "1": "ready to send", "2": "ready to send", "3": "being written", "4": "new"}


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


@pytest.mark.parametrize("vp", [PHONE, WIDE], ids=["phone", "wide"])
def test_the_line_says_the_tabs_total_and_what_makes_it_up(run, tmp_path, vp):
    got = _go(run, tmp_path, [{"hash": "jobs", "eval": LOOK}], vp, clock=T)
    seen = got["after"][0]["eval"]
    tab = int(re.search(r"(\d+)", seen["tab"]).group(1))
    m = re.match(r"\s*(\d+) to apply for: (.*?)\.(?: (\d+) to confirm\.)?", seen["line"])
    assert m and int(m.group(1)) == tab, seen
    parts = re.findall(r"(\d+) (needs? your answer|ready to send|being written|new)", m.group(2))
    # The parts are the headings' own words, in the headings' order, and count the cards under
    # each; the drafts asking whether they went are counted in the tab and wait in the fold.
    said = [w.replace("need your", "needs your") for _, w in parts]
    assert said == [h.lower() for h in seen["heads"]], (said, seen["heads"])
    for n, w in parts:
        assert int(n) == sum(1 for st in seen["stages"] if WORDS[st] == w.replace("need your", "needs your")), (n, w, seen)
    asked_drafts = sum(1 for x in seen["fold"] if x.startswith("app-"))
    assert sum(int(n) for n, _ in parts) + asked_drafts == tab, seen
    assert int(m.group(3) or 0) == len(seen["fold"]) and seen["foldSays"].startswith("%d jobs to confirm" % len(seen["fold"])), seen
    # "4 to send" read against "nothing is ever sent"; "ready to send" is the heading's own word.
    assert not re.search(r"\d+ to send", seen["line"]), seen
    for gone in ("strong", "waiting on you", "being made", "still to make", "to look at"):
        assert gone not in seen["line"], (gone, seen)
    assert m.group(0).strip() == "5 to apply for: 2 ready to send, 1 being written, 1 new. 2 to confirm.", seen


def test_ready_is_only_a_draft_nothing_waits_on_and_one_not_made_is_being_written(run, tmp_path):
    """The review of 2026-11-11: "3 ready ... 2 need your answer" counted drafts with a question
    as ready. A draft whose files are still to come is being written, never ready, under that
    heading and in the line, as Claude makes it next by itself (the redesign's second round,
    2026-11-17)."""
    got = _go(run, tmp_path, [{"hash": "jobs", "eval": LOOK}], WIDE, clock=T)
    line = got["after"][0]["eval"]["line"]
    # The draft that asks whether it went is in the fold's count alone, said once.
    assert "2 ready to send, 1 being written" in line and "your answer" not in line and line.count("confirm") == 1, line
    from test_the_page_journeys import _sample
    m = _sample()
    for a in m["ready"]:
        a["checks"] = {"passed": False, "line": "Not made yet"}
        a["alerts"] = [x for x in a.get("alerts") or [] if x.get("kind") != "checks"]
    got = _go(run, tmp_path, [{"hash": "jobs", "eval": LOOK}], WIDE, model=m, clock=T)
    seen = got["after"][0]["eval"]
    assert "ready to send" not in seen["line"] and "being written" in seen["line"], seen
    assert "Ready to send" not in seen["heads"] and "Being written" in seen["heads"], seen


BOTH = ("(() => { const line = (document.querySelector('#main .summary') || {}).textContent || '';"
        " return line; })()")
BRIEF = "(document.querySelector('#main [data-k=\"bp-drafts\"]') || {}).textContent || ''"


@pytest.mark.parametrize("vp", [PHONE, WIDE], ids=["phone", "wide"])
def test_the_brief_counts_the_drafts_as_jobs_does(run, tmp_path, vp):
    # The Brief said "3 drafts ready to apply, 1 being made" over Jobs' "2 ready, 1 waiting on
    # you, 1 being made": the draft with a question was ready on one screen and waiting on you
    # on the other (the screen review, 2026-11-11). One tally says both, in the same words (the
    # redesign's second round, 2026-11-17).
    got = _go(run, tmp_path, [{"hash": "jobs", "eval": BOTH}, {"hash": "brief", "eval": BRIEF}], vp, clock=T)
    jobs, brief = got["after"][0]["eval"], got["after"][1]["eval"]
    assert brief.startswith("2 applications ready to send"), brief
    for word in ("ready to send", "needs your answer", "being written"):
        j = re.search(r"(\d+) " + word, jobs)
        b = re.search(r"(\d+) (?:applications? )?" + word, brief)
        # What Claude is writing is its own work, said in the work pill: the Brief names it only
        # when nothing else is owed, and then in Jobs' number (4.15.0, a small laptop's panel).
        # Only drafts are the Brief's: a new job is no draft.
        if word == "being written" and b is None and any(re.search(r"\d+ (?:applications? )?" + w, brief) for w in ("ready to send", "needs? your answer", "to confirm")):
            continue
        assert (j and j.group(1)) == (b and b.group(1)), (word, jobs, brief)
    for gone in ("waiting on you", "being made", "still to make", "drafts"):
        assert gone not in brief, (gone, brief)


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
