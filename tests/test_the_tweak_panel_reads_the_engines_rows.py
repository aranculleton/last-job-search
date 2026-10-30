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
    assert "Name and dates" in got["text"] and "Your name" not in got["text"]
    assert got["rows"] == 5 and len(resume) > 5
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
    assert "Addressed to" in got["text"]


def test_without_the_engines_rows_the_page_keeps_its_own(run, tmp_path, vp):
    path = _write(tmp_path, "tp", _sample())
    got = run("tweak", html=path, viewport=vp, hash="drafts-applications", item=ITEM, entry="Edit the CV", exact=False)
    assert not got["errors"], got["errors"]
    assert got["rows"] == 5 and "Summary" in got["text"]


def test_the_newest_kept_change_is_undone_with_the_engines_own_action(run, tmp_path, vp):
    done = [{"key": "tw-k2", "at": "2026-10-24T15:00:00Z", "said": ["Look: classic"], "undo": True},
            {"key": "tw-k1", "at": "2026-10-23T15:00:00Z", "said": ["Spacing: tighter"], "undo": False}]
    m = _model(done)
    got = _go(run, tmp_path, [{"hash": "drafts-applications", "more": ITEM}, {"click": "Undo it"}], vp, model=m)
    assert "Last change: Look: classic" in got["after"][0]["text"]
    a = _one(got, "tweak.undo")
    assert a["item"] == ITEM and a["value"] == {"key": "tw-k2"} and a["rev_seen"] == _item(m, ITEM)["rev"]
