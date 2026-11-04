"""A thing said once is kept apart from setup's answers, so a finished setup stays finished.

The re-audit of 4 November: a copy with a profile and no setup mark or answers file is set
up (4.0's rule for old copies). The told records (`app.py told <key>`, and the page's Done on
a report or an outside card) wrote profile/setup_answers.json holding only {"outside": ...},
and that copy read as setup unfinished after its first one: start said "Setup carries on",
and the page's setup went from done to searching. The records are kept in a file of their
own (profile/said_once.json), and an answers file holding only "outside", which a copy may
already have, is read as no answers at all. The person is the example's, invented.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import app_setup  # noqa: E402
import merge_state  # noqa: E402
import save_state  # noqa: E402
from test_set_me_up_is_the_only_thing_said_in_a_chat import Copy  # noqa: E402

ANSWERS = "setup_answers.json"


def test_a_told_record_leaves_a_finished_copy_finished(tmp_path):
    c = Copy(str(tmp_path), profile=True)
    assert c.model()["setup"]["state"] == "done"
    c.run("told", "report-page")
    assert not os.path.exists(os.path.join(c.profile, ANSWERS))
    with open(os.path.join(c.profile, app_setup.SAID), encoding="utf-8") as fh:
        assert "report-page" in json.load(fh)
    assert c.model()["setup"]["state"] == "done"
    said = c.run("start", "--on", "m", "--tools", "none")
    assert "Setup carries on" not in said


def test_the_pages_done_on_an_outside_card_leaves_setup_finished(tmp_path, monkeypatch):
    c = Copy(str(tmp_path), profile=True)
    c.run("published", "https://claude.ai/code/artifact/example-page")
    env = dict(c.env(), CLAUDE_CODE_REMOTE="true")
    monkeypatch.setattr(c, "env", lambda: env)
    aid = c.act("setup.done", "q-setup-auto")
    assert c.apply()["ok"] == [aid]
    assert not os.path.exists(os.path.join(c.profile, ANSWERS))
    m = c.model()
    assert m["setup"]["state"] == "done"
    assert not [q for q in m["needs_you"] if q["id"] == "q-setup-auto"]


def test_a_copy_that_already_wrote_one_heals_by_itself(tmp_path, monkeypatch):
    c = Copy(str(tmp_path), profile=True)
    with open(os.path.join(c.profile, ANSWERS), "w", encoding="utf-8") as fh:
        json.dump({"outside": {"report-page": "2026-11-03", "auto": "2026-11-03"}}, fh)
    assert c.model()["setup"]["state"] == "done"
    assert "Setup carries on" not in c.run("start", "--on", "m", "--tools", "none")
    # What it was told before still counts as told.
    monkeypatch.setenv("LJS_PROFILE", c.profile)
    assert app_setup._finished()
    assert app_setup.told("report-page") == "2026-11-03"


def test_an_answers_file_with_a_real_answer_still_counts(tmp_path, monkeypatch):
    c = Copy(str(tmp_path), profile=True)
    monkeypatch.setenv("LJS_PROFILE", c.profile)
    with open(os.path.join(c.profile, ANSWERS), "w", encoding="utf-8") as fh:
        json.dump({"outside": {"auto": "2026-11-03"}, "work": {"work": "Analyst"}}, fh)
    assert not app_setup._finished()


def test_the_record_is_saved_and_merges_by_its_dates():
    assert "profile" in save_state.PLAIN
    rules = merge_state.json_rules("profile/" + app_setup.SAID)
    assert rules["dated"] == ("*",)
