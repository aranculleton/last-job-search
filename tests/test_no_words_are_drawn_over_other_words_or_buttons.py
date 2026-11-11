"""No words are drawn over other words or over a button, on any screen, at a phone's, a
tablet's or a laptop's width, light or dark.

On Coming up, By day, an interview's time read from another zone ("15:00 Toronto time (20:00
here)") ran out of its column under the title, over the row's line of facts and into its pill,
on a laptop in dark (the maintainer, 2026-11-11). The layout checks found only what spilled past
the width. The harness's overlap probe (tests/app_page/harness.js, overlapProbe) now measures
every line of visible text and every drawn control on every screen and each of its views, and
names each pair that meet. It runs over the sample and over the sample at its extremes: a
person whose zone is not the device's, so every time says both; a long employer, a long role
and a long interview title; and an interview tomorrow with a live prep, so the practice day's
pills are drawn. Every person and employer is invented.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

from test_interview_pack import app  # noqa: E402,F401
from test_the_live_prep_on_the_page import _model as _live_model  # noqa: E402
from test_the_page_journeys import _sample, browser  # noqa: E402
from test_the_page_works_in_a_browser import _write  # noqa: E402

# The day before the interview with the live prep: its practice is on its card's face.
CLOCK = "2026-10-27T09:00:00Z"
SIZES = {"phone": {"width": 375, "height": 812}, "tablet": {"width": 820, "height": 1180},
         "laptop": {"width": 1280, "height": 800}, "desktop": {"width": 1440, "height": 900}}

LONG_EMPLOYER = "Copperleaf Payments and Merchant Services Group"
LONG_ROLE = "Senior Data Analyst, Payments Risk and Merchant Onboarding Analytics"
LONG_STAGE = "Final round: technical case study with the hiring panel"

# Overlaps meant to be there, each with why. A string lets an element pass whole; a pair lets
# only those two meet; `drawn` measures a control as the part of it that is drawn.
ALLOW = [
    # The "?" is a 22px circle drawn inside a 44px target on a phone (DESIGN.md, "Buttons,
    # links and taps": a full-size tap area): the target reaches past its line, the circle
    # does not. Measured as the circle.
    {"sel": ".q, .sum .help-q", "drawn": 23},
    # A draft's heading row is its fold's whole-width toggle, and Copy and the pencil sit at
    # its right end by design (DESIGN.md, "Contacts": "the draft with Copy and the pencil at
    # the right end of its heading line"): the row is drawn under them, its words beside them.
    ["summary.pdraft-sum", ".bubble-copy, .bubble-pen"],
]


def extremes():
    """The sample with a live prep, at its extremes, as an engine would write them: the person in
    Toronto on a device in London, so every time says both zones; one employer's name, one role
    and one interview's title at full length, wherever the sample names them."""
    m = _live_model()
    m["person"] = dict(m["person"], time_zone="America/Toronto")
    text = json.dumps(m).replace("Copperleaf Pay", LONG_EMPLOYER).replace("Data Analyst, Payments", LONG_ROLE)
    m = json.loads(text)
    for iv in m["interviews"]:
        if iv["id"] == "int-copperleaf-payments":
            iv["next_stage"] = LONG_STAGE
    for u in m["upcoming"]:
        if u["id"].startswith("up-app-copperleaf-payments"):
            u["title"] = LONG_STAGE + ": " + LONG_EMPLOYER
    return m


_PAGES: dict = {}


@pytest.fixture
def pages(app, tmp_path_factory):  # noqa: F811
    if not _PAGES:
        tmp = tmp_path_factory.mktemp("overlaps")
        _PAGES.update(sample=_write(tmp, "sample", _sample()), extremes=_write(tmp, "extremes", extremes()))
    return _PAGES


@pytest.fixture(scope="module")
def run():
    yield from browser()


def _overlaps(run, html, size, scheme):
    got = run("layout", html=html, viewport=SIZES[size], scheme=scheme, fake={"canSend": "available"}, clock=CLOCK,
              overlaps=True, allow=ALLOW)
    assert not got["errors"], got["errors"]
    assert set(got["overlaps"]) >= {"brief", "todo", "jobs", "contacts", "interviews", "progress", "chat", "settings", "profile"}, got["overlaps"].keys()
    return {screen: found for screen, found in got["overlaps"].items() if found}


@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("size", ["phone", "tablet", "laptop", "desktop"])
@pytest.mark.parametrize("model", ["sample", "extremes"])
def test_no_words_are_drawn_over_other_words_or_buttons_on_any_screen(run, pages, model, size, scheme):
    found = _overlaps(run, pages[model], size, scheme)
    assert not found, "\n".join(screen + ": " + o["a"] + " and " + o["b"] + " meet, %(w)sx%(h)spx at %(at)s" % o
                                 for screen, overlaps in found.items() for o in overlaps)


def test_the_check_sees_words_drawn_over_words(run, pages):
    """The probe itself: a line of words laid over a row's title is named."""
    got = run("overlap_selftest", html=pages["sample"], viewport=SIZES["desktop"], clock=CLOCK, allow=ALLOW)
    assert not got["errors"], got["errors"]
    assert any("Drawn over the title" in o["a"] + o["b"] for o in got["found"]), got["found"]


def test_the_extremes_are_drawn(run, pages):
    """The extremes reach the page: both zones in a time, the long names, the practice day."""
    got = run("engine", html=pages["extremes"], viewport=SIZES["desktop"], fake={"canSend": "available"}, clock=CLOCK,
              hashes=["interviews", "jobs"])
    assert not got["errors"], got["errors"]
    up = got["texts"]["interviews"]
    assert "Toronto time (" in up and " here)" in up, up
    assert LONG_STAGE + ": " + LONG_EMPLOYER in up and "Practise 3 questions" in up, up
    assert LONG_ROLE in got["texts"]["jobs"], got["texts"]["jobs"]
