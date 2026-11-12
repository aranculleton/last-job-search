"""Read your prep and Practise 3 questions open the interview's prep on every device.

The incident (the maintainer, 2026-11-11, the night before an interview): on a phone, in a
browser and in the Claude app on a Mac, both buttons on the interview's card in Coming up
looked pressed and opened nothing. The page throws "Cannot define property __iv, object is
not extensible" before the sheet exists: it set a hidden property on the interview's live
prep, and the claude.ai store hands the page every record frozen (db.d.ts 0.2.91, "Delivered
snapshots and their data() are frozen"). The tests' stand-in for the store handed out copies
anyone could change, and the page's model was drawn from the copy built into it, so every
test passed while every real page failed.

Here the interview, its live prep included, reaches the page the way it reaches a real one:
as a screen in the store, frozen as the runtime freezes it. Each test taps the card as a
person would on the invented sample search (the live prep is the engine's own, built for the
example person's invented application). A last test pins the stand-in itself: every record
it hands out is frozen all the way down, so a page that writes onto one fails here first.
Every person and employer is invented.
"""
from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import app_page  # noqa: E402
from test_interview_pack import app  # noqa: E402,F401
from test_the_live_prep_on_the_page import IV, _soon  # noqa: E402
from test_the_page_journeys import PHONE, WIDE, browser  # noqa: E402

# The live prep is built from the example person's invented application, on disk for each test.
pytestmark = pytest.mark.usefixtures("app")

# Later than the sample's own model, so the page takes the store's screen over the copy built
# into it, as a real page does.
DRAWN = "2026-10-25T09:30:00Z"


@pytest.fixture(scope="module")
def run():
    yield from browser()


def _go(run, tmp_path, steps, vp):
    """The sample a day before its interview, the interviews screen in the store as a chat
    writes it (`app.py view`)."""
    model = _soon(1)
    path = os.path.join(str(tmp_path), "page.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(app_page.standalone(app_page.render(model)))
    seed = {"view/interviews": {"made_at": DRAWN, "data": model["interviews"]}}
    return run("engine", html=path, viewport=vp, steps=steps, seed=seed, fake={"canSend": "available"}), model


SHEET = ("(() => { const d = document.querySelector('dialog.detail'); const lp = d && d.querySelector('.lp');"
         " return {open: !!(d && d.open), title: d ? d.querySelector('.detail-title').textContent : '',"
         " parts: lp ? lp.querySelectorAll('.lp-part[data-lpp]').length : 0, mode: lp ? lp.dataset.mode : ''}; })()")


# The day before, the By day row leads with practice; the Interviews card has both.
TAPS = [("By day", "Practise 3 questions"), ("Interviews", "Practise 3 questions"), ("Interviews", "Read your prep")]


@pytest.mark.parametrize("vp", [PHONE, WIDE], ids=["phone", "wide"])
@pytest.mark.parametrize("view,tap", TAPS)
def test_the_prep_opens_from_the_store_on_coming_up(run, tmp_path, vp, view, tap):
    got, model = _go(run, tmp_path, [
        {"hash": "interviews"},
        {"click": view, "exact": True},
        {"click": tap, "within": "#main", "eval": SHEET},
    ], vp)
    assert not got["errors"], got["errors"]
    seen = got["after"][2]["eval"]
    iv = next(i for i in model["interviews"] if i["id"] == IV)
    assert seen["open"] and iv["company"] in seen["title"], seen
    assert seen["parts"] == len(iv["live"]["parts"]), seen
    assert seen["mode"] == ("hidden" if tap.startswith("Practise") else "both"), seen


def test_the_brief_and_to_do_draw_the_prep_from_the_store(run, tmp_path):
    # The prep's questions are read for To do and the Brief too (ivQuestions): a property set
    # on the store's record there would stop the screen drawing.
    got, _ = _go(run, tmp_path, [{"hash": "todo", "read": "#main"}, {"hash": "brief", "read": "#main"},
                                 {"hash": "interviews", "read": "#main"}], PHONE)
    assert not got["errors"], got["errors"]
    for a in got["after"]:
        assert "could not be shown" not in a["text"], a["text"][:400]


def test_the_stand_in_store_hands_out_frozen_records_as_the_real_one_does(run, tmp_path):
    got, _ = _go(run, tmp_path, [{"eval": (
        "(async () => { const db = await window.claude.use('db'); const d = await db.doc('screen/interviews').get();"
        " const x = d.data(); const iv = x.data.find((i) => i.live);"
        " return [Object.isFrozen(x), Object.isFrozen(x.data), Object.isFrozen(iv), Object.isFrozen(iv.live),"
        " Object.isFrozen(iv.live.parts[0])]; })()")}], PHONE)
    assert got["after"][0]["eval"] == [True, True, True, True, True], got["after"][0]["eval"]
