"""An empty Chat keeps its box at the foot, its starters as chips just above it.

The screen review of 2026-11-11 (row 33): with no messages yet, 200 to 460px of blank stood
above the starters and the box, and "Ask anything" was said three ways (the subtitle, the
starters' line and the box's hint), so the starters and the box moved under the header. Then
the redesign of 2026-11-16: under the header, the box sat mid-screen on a phone and jumped to
the foot with the first message. Now the box keeps to the foot from the first look, where it
stays once there are messages, as in any chat; with no messages its starters are chips just
above it, the intro is in the room above them, and the subtitle is not drawn. On a phone and a
wide screen, in the light look and the dark. Every person and employer is invented.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest  # noqa: E402

import app_page  # noqa: E402
import test_the_page_journeys as journeys  # noqa: E402
from test_the_page_journeys import PHONE, WIDE, _sample  # noqa: E402

CLOCK = "2026-10-25T18:30:00Z"
LOOK = ("(() => { const box = document.querySelector('#talk-box'); const head = box.querySelector('.sec-head').getBoundingClientRect();"
        " const form = box.querySelector('.talk-form').getBoundingClientRect(); const sum = box.querySelector('.sec-head .sum');"
        " const row = box.querySelector('.talk-row').getBoundingClientRect(); const chips = [...box.querySelectorAll('.talk-examples button')].map((b) => b.getBoundingClientRect());"
        " const intro = box.querySelector('.talk-intro'); const ir = intro && intro.getClientRects().length ? intro.getBoundingClientRect() : null;"
        " return {gap: Math.round(form.top - head.bottom), low: form.bottom / innerHeight, starters: chips.length, rowBottom: Math.round(row.bottom),"
        " chipsToBox: chips.length ? Math.round(row.top - Math.max(...chips.map((c) => c.bottom))) : null,"
        " introAbove: ir && chips.length ? ir.bottom <= Math.min(...chips.map((c) => c.top)) && ir.top >= head.bottom : null,"
        " sum: sum && sum.offsetParent !== null && !sum.hidden ? sum.textContent : '', msgs: box.querySelectorAll('.talk-msg').length}; })()")
THREAD = {"talk/cloud-1": {"to": "cloud", "conv": "1", "title": "Questions", "created_at": "2026-10-25T09:00:00Z", "_v": 1},
          "talk/cloud-1/messages/q1": {"from": "you", "text": "When is the Harbourline second interview?", "at": "2026-10-25T18:00:00Z", "_v": 1},
          "talk/cloud-1/messages/a1": {"from": "cloud", "text": "Wednesday 4 November; no time yet.", "at": "2026-10-25T18:01:00Z", "_v": 1}}


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


def _look(run, tmp_path, vp, scheme, seed):
    path = os.path.join(str(tmp_path), "page.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(app_page.standalone(app_page.render(_sample())))
    got = run("engine", html=path, viewport=vp, scheme=scheme, steps=[{"hash": "chat", "wait": 200, "eval": LOOK}],
              seed=seed, fake={"canSend": "available"}, clock=CLOCK)
    assert not got["errors"], got["errors"]
    return got["after"][0]["eval"]


@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("vp", [PHONE, WIDE], ids=["phone", "wide"])
def test_with_no_messages_the_box_is_at_the_foot_with_its_starters_just_above_it(run, tmp_path, vp, scheme):
    seen = _look(run, tmp_path, vp, scheme, {})
    assert seen["msgs"] == 0 and seen["starters"] >= 2, seen
    # At the foot, where it stays once there are messages: never under the header, where it
    # sat mid-screen on a phone and jumped with the first message (the redesign, 2026-11-16).
    assert seen["low"] >= 0.8, seen
    # The starters are chips just over the box, the intro in the room above them.
    assert 0 <= seen["chipsToBox"] <= 24 and seen["introAbove"], seen
    # Said once, by the starters' own line and the box's hint: no subtitle saying it again.
    assert seen["sum"] == "", seen


@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("vp", [PHONE, WIDE], ids=["phone", "wide"])
def test_with_messages_the_box_stays_at_the_foot(run, tmp_path, vp, scheme):
    seen = _look(run, tmp_path, vp, scheme, THREAD)
    assert seen["msgs"] == 2 and seen["starters"] == 0, seen
    assert seen["low"] >= 0.8 and seen["gap"] > 200, seen
    assert seen["sum"] == "Ask anything about your search.", seen
    # The first message never moves the box: it is where it was on the empty Chat.
    empty = _look(run, tmp_path, vp, scheme, {})
    assert abs(seen["rowBottom"] - empty["rowBottom"]) <= 2, (empty["rowBottom"], seen["rowBottom"])
