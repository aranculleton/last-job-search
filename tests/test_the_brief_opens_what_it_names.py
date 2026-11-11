"""The Brief opens what each line names, and lists what there is to do.

The maintainer, 2026-11-05: a Next step about an application ("Send the thank-you after your
interview at ...") was text with nothing to tap; a person put away with Don't contact was still
a Next step; and the Jobs panel said "36 drafts ready to apply" over empty space. Every person
and employer here is the sample's, invented.
"""
from __future__ import annotations

import copy
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_the_page_journeys import _sample, browser  # noqa: E402
from test_the_page_works_in_a_browser import _write  # noqa: E402

WIDE = {"width": 1600, "height": 1000}


@pytest.fixture(scope="module")
def run():
    yield from browser()


def _brief(m, items):
    sec = next(s for s in m["brief"]["sections"] if s["kind"] == "next")
    sec["items"] = items


def test_a_step_about_an_application_opens_it_and_one_put_away_is_gone(run, tmp_path):
    m = copy.deepcopy(_sample())
    app = m["applications"][0]
    who = m["people"][1]
    _brief(m, [{"text": "Send the thank-you after your interview at " + app["company"] + ".", "item": app["id"], "section": "applications"},
               {"text": "Send your reply to " + who["first_name"] + ": it is drafted for you.", "item": who["id"], "section": "people"}])
    html = _write(tmp_path, "brief_steps", m)
    stop = {"actions/act~" + who["id"] + "~person.stop~x": {"item": who["id"], "action": "person.stop", "value": {}, "at": "2026-10-25T09:00:00Z", "_v": 1}}
    got = run("engine", html=html, viewport=WIDE, seed=stop, steps=[
        {"hash": "brief", "eval": "[...document.querySelectorAll('.bp-next .bp-steps li')].map((li) => { const a = li.querySelector('a'); return [li.textContent.trim(), a ? a.getAttribute('href') : null]; })"}])
    assert not got["errors"], got["errors"]
    rows = got["after"][0]["eval"]
    first = next(r for r in rows if "thank-you" in r[0])
    assert first[1] == "#jobs/" + app["id"], rows
    assert not any(who["first_name"] + ":" in r[0] for r in rows), rows


def test_with_nothing_new_found_the_jobs_panel_lists_the_drafts_ready(run, tmp_path):
    m = copy.deepcopy(_sample())
    for r in m["jobs"]["rows"]:
        if r["status"] == "new":
            r["status"] = "dismissed"
    html = _write(tmp_path, "brief_jobs", m)
    got = run("engine", html=html, viewport=WIDE, steps=[
        {"hash": "brief", "eval": "[...document.querySelectorAll('.bp-jobs .bp-list li a')].map((a) => a.textContent.trim())"}])
    assert not got["errors"], got["errors"]
    assert got["after"][0]["eval"], "the drafts ready to apply are listed"


def test_one_new_job_is_never_all_1_new(run, tmp_path):
    # "All 1 new" under one job (the screen review, 2026-11-11): one says where it opens.
    m = copy.deepcopy(_sample())
    keep = [r for r in m["jobs"]["rows"] if r.get("status") in ("new", None)][:1]
    for r in m["jobs"]["rows"]:
        if r.get("status") in ("new", None) and r not in keep:
            r["status"] = "dismissed"
    html = _write(tmp_path, "one_new", m)
    got = run("engine", html=html, viewport=WIDE, steps=[{"hash": "brief", "eval": "[...document.querySelectorAll('[data-k=\"bp:jobs\"] .bp-foot a, [data-k=\"bp:jobs\"] .bp-foot button')].map((a) => a.textContent.trim())"}])
    assert not got["errors"], got["errors"]
    foot = got["after"][0]["eval"]
    assert not any(t.startswith("All 1 ") for t in foot), foot
    assert "Open Jobs" in foot, foot


def test_a_tip_is_shown_in_one_place_at_a_time(run, tmp_path):
    # The same tip ("Tap the pencil on anything Claude writes...") on the Brief and on Jobs the
    # same day (the screen review, 2026-11-11): the engine's tip shows where it belongs, and the
    # Brief keeps one of its own.
    html = _write(tmp_path, "tips", _sample())
    tip = "(document.querySelector('#main .bp-tip, #main .tip') || {}).textContent || ''"
    got = run("engine", html=html, viewport=WIDE, steps=[{"hash": "brief", "eval": tip}, {"hash": "jobs", "eval": tip}])
    assert not got["errors"], got["errors"]
    brief, jobs = (a["eval"] for a in got["after"])
    assert "pencil on anything Claude writes" in jobs, jobs
    assert brief and "pencil on anything Claude writes" not in brief, brief


def test_a_news_links_brackets_keep_to_it(run, tmp_path):
    # "(" alone at a line's end, the link "a trade report)" on the next (the screen review,
    # 2026-11-11): a bracket keeps to the link it opens.
    html = _write(tmp_path, "news", _sample())
    look = r"""(() => [...document.querySelectorAll('#main .bp-news a')].map((a) => {
      const prev = a.previousSibling, t = prev && prev.nodeType === 3 ? prev : (a.parentElement.previousSibling || null);
      const open = a.parentElement.classList.contains('paren') ? a.parentElement.firstChild : (prev && prev.nodeType === 3 && /\($/.test(prev.data) ? prev : null);
      if (!open) return null;
      const g = document.createRange(); g.setStart(open, open.data.length - 1); g.setEnd(open, open.data.length);
      const b = g.getClientRects()[0], w = (() => { const r = document.createRange(); r.selectNodeContents(a); return r.getClientRects()[0]; })();
      return Math.round(Math.abs(b.top - w.top)); }).filter((x) => x !== null))()"""
    for width in (320, 340, 360, 375, 390):
        got = run("engine", html=html, viewport={"width": width, "height": 800}, steps=[{"hash": "brief", "eval": look}])
        assert not got["errors"], got["errors"]
        tops = got["after"][0]["eval"]
        assert tops and all(t <= 4 for t in tops), (width, tops)
