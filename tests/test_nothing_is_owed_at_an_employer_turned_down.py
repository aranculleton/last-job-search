"""Nothing is owed to anyone at an employer the person turned down.

The maintainer, 2026-11-05: the Brief's Next ("Send your reply to Juno: it is drafted for
you.") and To do still listed a drafted reply to someone at an employer put in the trash with
"No more from <employer>". The engine holds everyone there from its next read (surface.held
reads BAR_DECLINED, replies included); the page must agree at once: what is owed to people
at that employer leaves Next, Waiting on you and To do, and their thread stays in Contacts.
Every person and employer is invented (the sample's own).
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import test_the_page_journeys as journeys  # noqa: E402
from test_the_page_journeys import WIDE, _go, _one  # noqa: E402

T = "2026-10-25T09:00:00.000Z"
JUNO = "larkspur_retail_castellan"


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


BRIEF = ("[...document.querySelectorAll('#main .bp-next, #main .bp-people, #main .bp-today')]"
         ".map((p) => p.innerText).join(' | ')")
TODO = "[...document.querySelectorAll('#main [data-card]')].map((c) => c.innerText).join(' | ')"
CONTACT = "!!document.querySelector('#main [data-item=\"%s\"]')" % JUNO


@pytest.mark.parametrize("how", ["job", "person"])
def test_an_employer_turned_down_takes_its_live_reply_off_next_and_to_do(run, tmp_path, how):
    steps = [{"hash": "brief", "eval": BRIEF}]
    if how == "job":
        # The job's trash: "No more from Larkspur Retail".
        steps += [{"hash": "jobs", "open": "bin:r12-2"},
                  {"click": "No more from Larkspur Retail", "exact": True, "within": "dialog", "wait": 300}]
    else:
        # Another way to the same: Juno's own trash in Contacts, "Not interested in ... any more".
        steps += [{"hash": "contacts", "open": "pbin:" + JUNO},
                  {"click": "Not interested in Larkspur Retail any more", "exact": True, "within": "dialog", "wait": 300}]
    steps += [{"hash": "brief", "eval": BRIEF}, {"hash": "todo", "eval": TODO}, {"hash": "contacts", "eval": CONTACT}]
    got = _go(run, tmp_path, steps, WIDE, clock=T)
    before, brief, todo, contact = (got["after"][0]["eval"], got["after"][-3]["eval"], got["after"][-2]["eval"],
                                    got["after"][-1]["eval"])
    assert "Juno" in before, before                    # owed before: the reply is drafted
    assert "Juno" not in brief, brief
    assert "Reply to Juno" not in todo and "Juno" not in todo, todo
    if how == "job":
        assert contact, "their thread stays in Contacts"
    action = _one(got, "job.dismiss" if how == "job" else "person.stop")
    assert action["value"].get("scope") == "employer" or action["value"].get("why") == "employer", action
