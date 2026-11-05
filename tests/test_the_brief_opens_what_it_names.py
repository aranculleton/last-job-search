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
