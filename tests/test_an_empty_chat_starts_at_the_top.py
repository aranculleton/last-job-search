"""An empty Chat puts its starters and its box just under the header.

The screen review of 2026-11-11 (row 33): with no messages yet, 200 to 460px of blank stood
above the starters and the box, pushed to the foot of the screen as if a conversation sat
above them, and "Ask anything" was said three ways (the subtitle, the starters' line and the
box's hint). With no messages the starters and the box sit under the header and the subtitle is
not drawn; once there are messages the box stays at the foot, as in any chat. On a phone and a
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
        " return {gap: Math.round(form.top - head.bottom), low: form.bottom / innerHeight, starters: box.querySelectorAll('.talk-examples button').length,"
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
def test_with_no_messages_the_starters_and_box_sit_under_the_header(run, tmp_path, vp, scheme):
    seen = _look(run, tmp_path, vp, scheme, {})
    assert seen["msgs"] == 0 and seen["starters"] >= 2, seen
    # Under the header, never at the foot of a blank screen (it stood 200 to 460px down).
    assert 0 <= seen["gap"] <= 48, seen
    # Said once, by the starters' own line and the box's hint: no subtitle saying it again.
    assert seen["sum"] == "", seen


@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("vp", [PHONE, WIDE], ids=["phone", "wide"])
def test_with_messages_the_box_stays_at_the_foot(run, tmp_path, vp, scheme):
    seen = _look(run, tmp_path, vp, scheme, THREAD)
    assert seen["msgs"] == 2 and seen["starters"] == 0, seen
    assert seen["low"] >= 0.8 and seen["gap"] > 200, seen
    assert seen["sum"] == "Ask anything about your search.", seen
