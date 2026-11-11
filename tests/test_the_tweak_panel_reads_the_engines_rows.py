"""The Tweak panel shows the engine's own rows, and its Undo is the engine's.

model.tweaks.rows (tools/tweak.py, through app_model) is the table a tweak is applied from:
its codes, its order, its states and its hints. The panel builds the resume, letter, note
and prep rows from it, so a value the page offers is always one the engine knows, and the
newest change the engine kept on an output can be taken back from its card. Jobs and the
brief keep the page's own rows, which the page applies itself. Every person and employer
here is invented.
"""
from __future__ import annotations

import copy
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

from test_the_page_journeys import _go, _item, _one, _sample, browser  # noqa: E402
from test_the_page_works_in_a_browser import _write  # noqa: E402

EXAMPLE = os.path.join(ROOT, "tests", "fixtures", "app_model_example.json")
ITEM = "app-ellerwick-insight"


@pytest.fixture(scope="module")
def run():
    yield from browser()


@pytest.fixture(params=[375, 1280], ids=["phone", "wide"])
def vp(request):
    return {"width": request.param, "height": 800 if request.param < 600 else 900}


def _engine_rows():
    with open(EXAMPLE, encoding="utf-8") as fh:
        return json.load(fh)["tweaks"]["rows"]


def _model(done=None):
    m = copy.deepcopy(_sample())
    m["tweaks"] = dict(m.get("tweaks") or {}, rows=_engine_rows())
    if done is not None:
        _item(m, ITEM)["tweaks_done"] = done
    return m


def test_the_resume_panel_shows_the_engines_labels_and_sends_its_codes(run, tmp_path, vp):
    path = _write(tmp_path, "tw", _model())
    got = run("tweak", html=path, viewport=vp, hash="drafts-applications", item=ITEM, entry="Edit the CV", exact=False,
              choose=[["R4", "name-centre"], ["R5", "navy"]], apply=True)
    assert not got["errors"], got["errors"]
    resume = [r for r in _engine_rows() if "resume" in r["outputs"] and r["control"] != "per-bullet"]
    # The engine's order and labels: its fourth row is Name and dates, not the page's old "Your name".
    assert "Name and dates" in got["all"] and "Your name" not in got["all"]
    assert got["rows"] == 2 and len(resume) > 5
    work = [d for _, d in got["work"] if d.get("kind") == "tweak"]
    assert work, got["work"]
    sent = work[-1]["args"]["changes"]
    codes = {r["p"]: set(r["values"]) for r in resume}
    assert {c["p"] for c in sent} == {"R4", "R5"}
    for c in sent:
        assert c["v"] in codes[c["p"]], c


def test_a_letter_length_that_needs_a_model_says_so_before_apply(run, tmp_path, vp):
    path = _write(tmp_path, "tl", _model())
    got = run("tweak", html=path, viewport=vp, hash="drafts-applications", item=ITEM, entry="Edit the letter", exact=False, choose=[["L1", "full"]])
    assert not got["errors"], got["errors"]
    short = run("tweak", html=path, viewport=vp, hash="drafts-applications", item=ITEM, entry="Edit the letter", exact=False, choose=[["L1", "short"]])
    # L1 is code for short and standard, and the engine's model_values make full a rewrite.
    assert got["after"]["line"] != short["after"]["line"]
    assert "Addressed to" in got["all"]


def test_without_the_engines_rows_the_page_keeps_its_own(run, tmp_path, vp):
    path = _write(tmp_path, "tp", _sample())
    got = run("tweak", html=path, viewport=vp, hash="drafts-applications", item=ITEM, entry="Edit the CV", exact=False)
    assert not got["errors"], got["errors"]
    assert got["rows"] == 2 and "Summary" in got["all"]


def test_the_newest_kept_change_is_undone_with_the_engines_own_action(run, tmp_path, vp):
    done = [{"key": "tw-k2", "at": "2026-10-24T15:00:00Z", "said": ["Look: classic"], "undo": True},
            {"key": "tw-k1", "at": "2026-10-23T15:00:00Z", "said": ["Spacing: tighter"], "undo": False}]
    m = _model(done)
    got = _go(run, tmp_path, [{"hash": "drafts-applications", "more": ITEM}, {"click": "Undo it"}], vp, model=m)
    assert "Last change: Look: classic, Sat 24 Oct." in got["after"][0]["text"]
    a = _one(got, "tweak.undo")
    assert a["item"] == ITEM and a["value"] == {"key": "tw-k2"} and a["rev_seen"] == _item(m, ITEM)["rev"]


def test_the_panel_leads_with_your_own_words_and_has_one_button(run, tmp_path, vp):
    """The maintainer, 2026-11-04: "u seem to have to scroll down to get the text box", "a lot of
    options its slightly overwhelming", and of Start now, With your next chat and Apply, "wtf
    is the difference". The text box comes first, two choices show with the rest one tap below,
    the person's rules fold to one line, and Apply is the one button."""
    path = _write(tmp_path, "tw", _model())
    got = run("tweak", html=path, viewport=vp, hash="drafts-applications", item=ITEM, entry="Edit the CV", exact=False)
    assert not got["errors"], got["errors"]
    text = got["text"]
    assert text.index("What should change?") < text.index("More choices"), text
    assert got["rows"] == 2
    assert "Start now" not in got["all"] and "With your next chat" not in got["all"]
    assert "Your usual:" not in got["all"]


def test_the_general_resumes_pencil_opens_its_bullets_and_sends_the_ones_ticked(run, tmp_path, vp):
    """The maintainer, 2026-11-06: "You can't choose which bullets go on a general resume."
    Its card carries its bullets where its draft is kept, and its pencil opens the Tweak panel
    with Bullets first: each one a choice, the ones ticked sent as the engine's R6 for the
    general resume, never kept as a usual (its Keep box is off for it). One made before its draft was kept has no pencil."""
    m = _model()
    m["resume"].update(id="resume-current", rev="r-general")
    m["resume"]["bullets"] = [
        {"id": "EX_ONE", "employer": "Brindle & Hart Logistics",
         "text": "Built weekly demand-forecasting models across 2,400 SKUs and six distribution "
                 "centres, cutting forecast error from 22% to 14%."},
        {"id": "EX_TWO", "employer": "Oakmere Foods", "text": "Cut waste by reading the shelf data."}]
    path = _write(tmp_path, "gr", m)
    got = run("tweak", html=path, viewport=vp, hash="drafts", entry=": your CV",
              exact=False, choose=[["R6", "EX_TWO"]], apply=True)
    assert not got["errors"], got["errors"]
    assert got["text"].split("\n").count("Bullets") >= 1 and "Cut waste by reading the shelf data." in got["all"]
    assert "centres, cutting forecast error from 22% to 14%." not in got["all"]   # a long one is clipped
    work = [d for _, d in got["work"] if d.get("kind") == "tweak"]
    assert work, got["work"]
    args = work[-1]["args"]
    assert args["target"]["id"] == "resume-current" and args["target"]["output"] == "resume"
    assert args["changes"] == [{"p": "R6", "v": ["EX_TWO"]}], args
    assert args.get("keep") is None, args        # never a usual: its Keep box stays off
    m["resume"]["bullets"] = []
    got = _go(run, tmp_path, [{"hash": "drafts", "count": '[data-k^="tweak:resume:resume-current"]'}], vp, model=m)
    assert got["after"][0]["count"] == 0, got


def test_a_change_made_today_says_its_time(run, tmp_path, vp):
    """The maintainer, 2026-11-11, of "Last change: the message rewritten, Wed 11 Nov.": "if its
    the same day can we have the time ... like the time it was rewritten"."""
    done = [{"key": "tw-k3", "at": "2026-10-24T15:05:00Z", "said": ["Look: classic"], "undo": True}]
    got = _go(run, tmp_path, [{"hash": "drafts-applications", "more": ITEM}], vp, model=_model(done),
              clock="2026-10-24T18:00:00Z", zone="UTC")
    line = got["after"][0]["text"]
    line = line[line.find("Last change"):].split("Undo it")[0]
    # Said on the person's own clock, the device's beside it where they differ.
    assert line.startswith("Last change: Look: classic, today at ") and "15:05" in line, line
