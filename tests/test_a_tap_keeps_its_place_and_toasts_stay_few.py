"""A job tapped keeps its place on Jobs, and toasts stay few and say how long they have.

The maintainer, 2026-11-06: "the position of meta in this list changed when i pressed draft
... i had to scroll to find it again": a job tapped Draft this jumped to the top among the
drafts. And, on the toasts: "a circle that fills up ... make me less incentivised to close it.
also when a bunch get completed at the same time, is there a limit so it doesnt fill the screen
with stacking?" Every person and employer is invented (the sample's own).
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import test_the_page_journeys as journeys  # noqa: E402
from test_the_page_journeys import _go, _sample  # noqa: E402

T = "2026-10-25T09:00:00Z"
WIDE = {"width": 1400, "height": 900}
ORDER = "[...document.querySelectorAll('#main [data-k^=\"card:\"]')].map((c) => c.getAttribute('data-k'))"
DRAFTS = "[...document.querySelectorAll('#main button')].filter((b) => (b.getAttribute('aria-label') || '').startsWith('Draft this:'))"


def _finds():
    m = _sample()
    base = next(r for r in m["jobs"]["rows"] if r.get("status") in ("new", None) and not r.get("draft"))
    for i, co in enumerate(("Wrenfield Freight", "Saltmarsh Analytics", "Dovecote Systems", "Oakmere Foods")):
        m["jobs"]["rows"].append(dict(base, id="find-%d" % i, rank=90 + i, status="new", draft=None, company=co,
                                      title="Planning Analyst", score=70 - i))
    return m


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


def test_a_job_tapped_draft_this_keeps_its_place(run, tmp_path):
    got = _go(run, tmp_path, [
        {"hash": "jobs", "eval": ORDER},
        {"eval": "(() => { const b = " + DRAFTS + "; b[b.length - 1].click(); return b.length; })()", "wait": 400},
        {"eval": ORDER},
        {"hash": "brief", "wait": 100},
        {"hash": "jobs", "wait": 200, "eval": ORDER},
    ], WIDE, model=_finds(), clock=T)
    before, n, after = got["after"][0]["eval"], got["after"][1]["eval"], got["after"][2]["eval"]
    assert n >= 2, "the sample has finds to draft"
    assert [k for k in after if k in before] == [k for k in before if k in after], ("a tapped card moved", before, after)
    assert any(w.get("kind") == "draft" for w in got["work"]), got["work"]


TOASTS = ("(() => { const ts = [...document.querySelectorAll('#toasts [data-toast]')];"
          " return {n: ts.length, more: (document.querySelector('[data-k=\"toast-more\"]') || {}).textContent || '',"
          " ring: ts.every((t) => t.querySelector('.toast-x .toast-ring circle'))}; })()")


def test_a_burst_of_toasts_shows_two_and_counts_the_rest(run, tmp_path):
    got = _go(run, tmp_path, [
        {"hash": "jobs", "eval": "(() => { const b = " + DRAFTS + "; b.forEach((x) => x.click()); return b.length; })()", "wait": 300},
        {"eval": TOASTS},
    ], WIDE, model=_finds(), clock=T)
    n, t = got["after"][0]["eval"], got["after"][1]["eval"]
    assert n >= 3, ("the sample has three or more finds", n)
    assert t["n"] == 2 and t["more"] == "+%d more" % (n - 2), t
    assert t["ring"], ("each toast shows its time left round its close", t)


def _left(summary_only):
    result = {"summary": "Not drafted: the posting asks for a doctorate.", "links": []}
    if not summary_only:
        result["left_out"] = "the posting asks for a doctorate"
    return {"chats/cloud-1": {"kind": "cloud", "seen_at": "2026-10-25T08:59:30Z", "watching": True},
            "meta/listener": {"chat": "cloud-1", "kind": "cloud", "answered_at": "2026-10-25T08:58:00Z", "since": "2026-10-24T08:00:00.000Z"},
            "work/draft~find-0": {"kind": "draft", "status": "stopped", "to": "cloud", "attempt": 1, "stages": [], "stage": 0, "steps": [], "title": "Resume and letter: Wrenfield Freight, Planning Analyst",
                                  "asked_at": "2026-10-25T08:00:00Z", "claimed_at": "2026-10-25T08:01:00Z", "stage_at": "2026-10-25T08:02:00Z",
                                  "finished_at": "2026-10-25T08:05:00Z", "args": {"job": "find-0", "company": "Wrenfield Freight"}, "result": result, "_v": 1}}


@pytest.mark.parametrize("summary_only", [False, True], ids=["kept", "older"])
def test_a_job_left_out_says_why_and_offers_no_try_again(run, tmp_path, summary_only):
    look = ("(() => { const t = [...document.querySelectorAll('button')].filter((b) => b.textContent.trim() === 'Try again'"
            " && b.getClientRects().length).length; return {again: t, said: document.body.textContent.includes('Not drafted: the posting asks for a doctorate')}; })()")
    got = _go(run, tmp_path, [{"hash": "jobs", "wait": 200}, {"open": "fold:work", "wait": 200, "eval": look}], WIDE, model=_finds(), seed=_left(summary_only), clock=T)
    r = got["after"][1]["eval"]
    assert r["said"] and r["again"] == 0, ("Try again offered on a job ruled out", r)
    assert not [w for w in got["work"] if w.get("kind") == "draft" and w.get("status") == "queued"], got["work"]


FOLDS = ("(() => ({one: [...document.querySelectorAll('#main summary')].some((s) => /^Show 1 more$/.test(s.textContent.trim())),"
         " away: /more in To do/.test(document.querySelector('#main').textContent),"
         " bars: [...document.querySelectorAll('#main .band-more > summary')].map((s) => Math.round(s.getBoundingClientRect().width))}))()")


@pytest.mark.parametrize("where", ["todo", "jobs"])
def test_one_more_is_shown_never_folded_and_folds_are_quiet_lines(run, tmp_path, where):
    # The maintainer, 2026-11-06: "+1 more in to do? why would to do have it but not the jobs
    # page?", and of To do's foot: "show 1 more etc those 3 options at the end ... needs better
    # design". One card left over is shown in place, nothing sends the person to To do from
    # Jobs, and a fold is a short line, never a bar the width of the page.
    got = _go(run, tmp_path, [{"hash": where, "wait": 200, "eval": FOLDS}], WIDE, model=_finds(), clock=T)
    r = got["after"][0]["eval"]
    assert not r["one"] and not r["away"], r
    assert all(w < WIDE["width"] / 2 for w in r["bars"]), r
