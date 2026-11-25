"""The interview-prep pipeline holds what the QA audit of issue 369 found broken.

Every person, employer and answer here is invented: the example person, and the made-up
application `tests/test_interview_pack.py` builds.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network"),
                os.path.dirname(os.path.abspath(__file__))]

import app  # noqa: E402
import app_model  # noqa: E402
import interview_live as L  # noqa: E402
import interview_pack as P  # noqa: E402
from test_an_interview_has_a_live_prep import _fill  # noqa: E402
from test_interview_pack import COMPANY, ROLE, _ctx, app as app_fixture  # noqa: E402,F401


def _live(ctx):
    P.write_pack(ctx)
    path, found = L.write(ctx, _fill(L.build(ctx)))
    assert path and not found
    return path


def _restamp(path, checks):
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    doc["checked"]["checks"] = checks
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(doc, fh)


# ---------------------------------------------------------------- 1. checks grow stricter

@pytest.mark.usefixtures("app_fixture")
def test_a_live_prep_that_fails_stricter_checks_is_not_shown_as_ready(monkeypatch):
    ctx = _ctx()
    path = _live(ctx)
    folder, stage = os.path.dirname(path), {"label": ctx["stage"]}
    # Written under these checks: shown, with nothing to check again.
    assert L.recheck(folder) == []
    assert app_model._live_prep(folder, stage, []) is not None
    # The app updates and its checks grow stricter: this prep no longer passes them.
    _restamp(path, "older-checks")
    strict = L.problems

    def stricter(doc, ctx_=None):
        return strict(doc, ctx_) + [("what to say first", "a rule added since")]
    monkeypatch.setattr(L, "problems", stricter)
    assert L.recheck(folder)
    assert app_model._live_prep(folder, stage, []) is None
    assert app_model._live_unfit(folder, stage)
    said = app.live_behind_lines({"interviews": [{"company": COMPANY, "role": ROLE,
                                                  "next_stage": ctx["stage"], "live_unfit": True}]})
    assert said and "live-check" in said[0]


@pytest.mark.usefixtures("app_fixture")
def test_a_live_prep_from_older_checks_that_still_passes_stays_shown():
    ctx = _ctx()
    path = _live(ctx)
    _restamp(path, "older-checks")
    folder = os.path.dirname(path)
    assert L.recheck(folder) == []
    assert app_model._live_prep(folder, {"label": ctx["stage"]}, []) is not None
