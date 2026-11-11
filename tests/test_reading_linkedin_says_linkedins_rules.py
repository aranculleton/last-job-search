"""Where the person lets Claude read LinkedIn profiles, the page says LinkedIn's own rules.

The UX review of 2026-11-10 (U-1): the page asked the person to let Claude read LinkedIn
profiles, and later said only "LinkedIn asked Claude to slow down", never that LinkedIn's
rules do not allow automated tools and that it can limit an account it thinks uses one.
Reading through Claude's browser stays on by default (the maintainer); the line informs the
choice, in plain words, in Settings beside it and on the card that asks for it. Every person
and employer here is the sample's, invented.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest  # noqa: E402

import test_the_page_journeys as journeys  # noqa: E402
from test_the_page_journeys import PHONE, WIDE, _go, _sample  # noqa: E402

T = "2026-10-25T09:00:00Z"
RULES = "LinkedIn's rules do not allow automated tools"


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


@pytest.fixture(params=[PHONE, WIDE], ids=["phone", "wide"])
def vp(request):
    return request.param


def test_the_reading_setting_says_linkedins_rules(run, tmp_path, vp):
    m = _sample()
    m["settings"] = m["settings"] + [{"id": "setting-profile_reads", "key": "profile_reads",
                                      "label": "Reading LinkedIn profiles", "kind": "choice",
                                      "value": "browser", "rev": "pr1",
                                      "choices": [["browser", "Claude reads them"], ["paste", "I paste them"]]}]
    got = _go(run, tmp_path, [{"hash": "settings", "eval": "document.querySelector('#main').textContent"}],
              vp, model=m, clock=T)
    text = got["after"][0]["eval"]
    assert RULES in text and "Claude reads them" in text, text[:2000]


def test_the_reading_row_says_them_too_where_the_engine_names_no_setting(run, tmp_path):
    rows = ("(() => { for (const d of document.querySelectorAll('#main details')) d.open = true;"
            " return [...document.querySelectorAll('#main [data-k=\"linkedin-rules\"]')].map((p) => p.textContent); })()")
    got = _go(run, tmp_path, [{"hash": "settings", "wait": 200, "eval": rows}], WIDE, clock=T)
    said = got["after"][0]["eval"]
    assert said and all(s.startswith(RULES) for s in said), said
    # Plain words: nothing a person would have to look up.
    from test_a_beginner_is_told_in_plain_words import _plain
    _plain(said[0])
