"""Every trash sheet whose card has a box ends with "Something else", which opens that box.

The maintainer, 2026-11-05: the trash on a person ("Not Juno?": Don't contact, Already in
touch another way, Cancel) had nothing for anything else, so there was no way to say in words
what was going on. Its last choice is now Something else: the sheet closes and the card's own
box opens under the card, its field focused, as the card's Something else under More does. A
job's, a draft's and an interview's trash end the same way; a person's trash opened from To do
takes the person to their card in Contacts, where their box is. Every person and employer is
the invented sample's (tests/fixtures/app_model_sample.json).
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_the_page_journeys import _sample, browser  # noqa: E402
from test_the_page_works_in_a_browser import _write  # noqa: E402

WIDE = {"width": 1280, "height": 900}
PHONE = {"width": 390, "height": 844}
CLOCK = "2026-10-25T09:00:00Z"


@pytest.fixture(scope="module")
def run():
    yield from browser()


def _click(sel):
    return "(() => { const b = document.querySelector('%s'); if (b) b.click(); return !!b; })()" % sel


FOCUS = ("(() => { const a = document.activeElement; const d = document.querySelector('dialog[open]');"
         " return {focus: a ? a.getAttribute('data-k') : null, sheet: !!d, hash: location.hash}; })()")


def _choices():
    return "[...document.querySelectorAll('dialog[open] .choice-btn')].map((b) => b.textContent.trim())"


@pytest.mark.parametrize("vp", [PHONE, WIDE], ids=["phone", "wide"])
@pytest.mark.parametrize("where,kind,item,bin_sel", [
    ("contacts", "person", "fernhill_freight_halloway", '[data-k="pbin:fernhill_freight_halloway"]'),
    ("jobs", "job", "r12-1", '[data-k="bin:r12-1"]'),
    ("drafts", "application", "app-quayside-demand", '[data-k="dbin:app-quayside-demand"]'),
    ("interviews/int-harbourline-risk", "interview", "int-harbourline-risk", '#main [data-k^="ivbin:"][data-k$=":int-harbourline-risk"]'),
], ids=["person", "job", "draft", "interview"])
def test_the_trash_ends_with_something_else_which_opens_the_cards_box(run, tmp_path, vp, where, kind, item, bin_sel):
    page = _write(tmp_path, "page", _sample())
    got = run("engine", html=page, viewport=vp, fake={"canSend": "available"}, clock=CLOCK, steps=[
        {"hash": where, "eval": _click(bin_sel)},
        {"eval": _choices()},
        {"click": "Something else", "within": "dialog[open]", "exact": True, "eval": FOCUS},
    ])
    assert not got["errors"], got["errors"]
    assert got["after"][0]["eval"], "the trash is on the card"
    choices = got["after"][1]["eval"]
    assert choices and choices[-1] == "Something else", choices
    after = got["after"][2]["eval"]
    # The sheet is shut and the card's own box has the focus, ready to type into.
    assert not after["sheet"], after
    assert after["focus"] == "ct-text:card-%s-%s" % (kind, item), after
    # Opening the box sends nothing: only its Ask Claude does.
    assert not got["actions"] and not got["work"], (got["actions"], got["work"])


def test_a_persons_trash_in_to_do_opens_their_box_in_contacts(run, tmp_path):
    page = _write(tmp_path, "page", _sample())
    bins = ("(() => { const b = [...document.querySelectorAll('#main [data-k]')].find((x) => /bin/.test(x.getAttribute('data-k'))"
            " && /^Not Juno/.test(x.getAttribute('aria-label') || '')); if (b) b.click(); return b ? b.getAttribute('data-k') : null; })()")
    got = run("engine", html=page, viewport=WIDE, fake={"canSend": "available"}, clock=CLOCK, steps=[
        {"hash": "todo", "eval": bins},
        {"click": "Something else", "within": "dialog[open]", "exact": True, "eval": FOCUS},
    ])
    assert not got["errors"], got["errors"]
    assert got["after"][0]["eval"], "Juno's row in To do has the trash"
    after = got["after"][1]["eval"]
    assert after["focus"] == "ct-text:card-person-larkspur_retail_castellan", after
    assert after["hash"].startswith("#contacts"), after
