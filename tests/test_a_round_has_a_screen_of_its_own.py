"""An interview's round has a screen of its own that prepares the person for it (issue 367).

Reading a prep was not preparing: the person had the questions and their answers, but nothing
said how ready they were, who they would meet and what each would probe, how to get there and
what to bring for an interview in person, or how to practise. The prep's own screen is now the
round's: the day, how ready they are as a sentence with the one next step, who they meet with
what each is likely to ask about, the format and the cheat sheet, then the questions; in person,
the day's plan, a fact not known yet said so and never guessed, with Confirm the plan asking
Claude; flashcards that keep each mark and when the card is next due (1, 3, 7 and 14 days); the
stories against the questions they answer (a grid on a wide screen, a list a story on a phone);
the numbers with a drill that hides them; and the cases, each kept as done.

On the sample page (an invented search, every person and employer invented), on a phone and on
a wide screen. The round is the one the engine will put on each upcoming interview (`round`).
"""
from __future__ import annotations

import copy
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))

from test_the_page_journeys import PHONE, WIDE, _go, _sample, browser  # noqa: E402

IV = "int-larkspur-supply"
ADDR = "interviews/prep~" + IV + "/open"
CLOCK = "2026-10-27T09:00:00Z"


@pytest.fixture(scope="module")
def run():
    yield from browser()


@pytest.fixture(params=[PHONE, WIDE], ids=["phone", "wide"])
def vp(request):
    return request.param


def _with(model, change):
    m = copy.deepcopy(model)
    for iv in m["interviews"]:
        if iv["id"] == IV:
            change(iv)
    return m


DUMP = "(() => { const d = document.querySelector('dialog.detail'); return d ? d.innerText : ''; })()"


def test_dump(run, tmp_path, vp):
    got = _go(run, tmp_path, [{"hash": ADDR, "read": "dialog.detail", "eval": DUMP}], vp, clock=CLOCK)
    print(got["after"][0]["eval"])
    assert 0
