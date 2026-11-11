"""A draft Claude makes again by itself says what its check found, never that it needs you.

The UX review of 2026-11-10 (U-19): the draft's line read "One check needs you: the CV runs to
a second page by two lines: Claude makes it again next.", saying in one breath that the person
was needed and that they were not. The check's own count is taken off its front, and one not
made yet says it is made next, never made again. Every person and employer is the sample's,
invented (tests/fixtures/app_model_sample.json).
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest  # noqa: E402

import test_the_page_journeys as journeys  # noqa: E402
from test_the_page_journeys import PHONE, WIDE, _go, _sample  # noqa: E402

T = "2026-10-25T09:00:00Z"
APP = "app-quayside-demand"
LINE = ("(() => { const c = document.querySelector('#main [data-item=\"%s\"]');"
        " const p = c && c.querySelector('.work-inline .wi-text'); return p ? p.textContent.trim() : null; })()" % APP)


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


def _with(text, label="Make it again"):
    m = _sample()
    for it in m["ready"]:
        if it["id"] == APP:
            for al in it["alerts"]:
                if al["kind"] == "checks":
                    al["text"] = text
                    al["action"]["label"] = label
    return m


@pytest.mark.parametrize("vp", [PHONE, WIDE], ids=["phone", "wide"])
def test_the_line_is_what_the_check_found(run, tmp_path, vp):
    got = _go(run, tmp_path, [{"hash": "drafts", "eval": LINE}], vp, clock=T)
    line = got["after"][0]["eval"]
    assert line == "The CV runs to a second page by two lines: Claude makes it again next.", line


def test_a_draft_not_made_yet_is_made_next_never_again(run, tmp_path):
    got = _go(run, tmp_path, [{"hash": "drafts", "eval": LINE}], WIDE, clock=T,
              model=_with("Not made yet: the letter.", "Make it"))
    assert got["after"][0]["eval"] == "Not made yet: Claude makes it next.", got["after"][0]["eval"]
