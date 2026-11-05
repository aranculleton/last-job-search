"""Every filter chip on says what it is, and a surname finds the person it belongs to.

A person's notes (2026-11-05): Jobs showed "Filter 1" and a chip with no words beside "Clear
all", and Clear all made it come back. Clearing the sort set it to nothing, and the list read
that as a sort called "", which it showed as a chip. And Contacts' search read first names,
employers and titles only, so a surname found nobody: the page keeps first names only, but a
person's id carries the rest of their name. Every person and employer is the sample's own.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import test_the_page_journeys as journeys  # noqa: E402
from test_the_page_journeys import WIDE, _go  # noqa: E402

CHIPS = r"""(() => ({n: ((document.querySelector('#main .filter-btn .fl-n') || {textContent: ''}).textContent.match(/\d+/) || [''])[0],
  chips: [...document.querySelectorAll('#main .active-filters .af-chip')].map((c) => c.textContent.replace('×', '').replace(': take off', '').trim())}))()"""


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


def test_clearing_a_sort_leaves_no_chip_without_words(run, tmp_path):
    got = _go(run, tmp_path, [
        {"hash": "jobs", "eval": "(localStorage.setItem('ljs:p:jobs:sort', JSON.stringify('closing')), 1)"},
        {"reload": True, "hash": "jobs", "eval": CHIPS},
        {"click": "Clear all", "eval": CHIPS},
        # One kept by an older page, which this list does not offer, is the default.
        {"eval": "(localStorage.setItem('ljs:p:jobs:sort', JSON.stringify('salary')), 1)"},
        {"reload": True, "hash": "jobs", "eval": CHIPS},
    ], WIDE)
    _, chosen, cleared, _, old = (x["eval"] for x in got["after"])
    assert chosen == {"n": "1", "chips": ["Closing soonest"]}, chosen
    assert cleared == {"n": "", "chips": []}, cleared
    assert old == {"n": "", "chips": []}, old


SEARCH = r"""(() => { const i = document.querySelector('#main input[data-k="q:contacts"]');
  i.value = %r; i.dispatchEvent(new Event('input', {bubbles: true})); return !!i; })()"""
SHOWN = r"""[...document.querySelectorAll('#main ul.people > [data-item]')].map((e) => e.getAttribute('data-item')).filter((x) => x && !x.startsWith('msg-'))"""


def test_a_surname_finds_the_person_whose_name_it_is(run, tmp_path):
    got = _go(run, tmp_path, [
        {"hash": "contacts", "eval": SHOWN},
        {"eval": SEARCH % "Castellan"},
        {"tick": 400},
        {"eval": SHOWN},
    ], WIDE)
    every, shown = got["after"][0]["eval"], got["after"][3]["eval"]
    assert len(every) > 8, every
    assert shown == ["larkspur_retail_castellan"], shown


def test_a_resume_made_for_someone_is_on_their_card(run, tmp_path):
    """A resume made for Juno when she asked for one says so on her card, with Get it
    (tests/test_a_resume_made_for_someone_is_theirs.py has the engine's half)."""
    m = journeys._sample()
    juno = next(p for p in m["people"] if p["id"] == "larkspur_retail_castellan")
    juno["resume_for_them"] = {"name": "Morgan_Ellis_Resume_For_Juno.pdf", "made_on": "2026-10-24",
                               "path": "documents/network/larkspur_retail_castellan/Morgan_Ellis_Resume_For_Juno.pdf",
                               "asset": None, "get": {"kind": "files", "id": "files~resume-larkspur_retail_castellan",
                                                      "args": {"paths": ["documents/network/larkspur_retail_castellan/Morgan_Ellis_Resume_For_Juno.pdf"]}}}
    got = _go(run, tmp_path, [
        {"hash": "contacts", "eval": "[...document.querySelectorAll('#main [data-resume-for]')].map((e) => [e.getAttribute('data-resume-for'), e.textContent])"},
    ], WIDE, model=m)
    lines = got["after"][0]["eval"]
    assert len(lines) == 1 and lines[0][0] == "larkspur_retail_castellan", lines
    assert lines[0][1].startswith("CV made for Juno") and "Get it" in lines[0][1], lines
