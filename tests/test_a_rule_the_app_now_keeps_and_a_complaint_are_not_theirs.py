"""What the person taught it stays theirs, and only theirs.

Two things that are not theirs had been kept as their rules (the maintainer, 2026-11-06):

- a rule the app has since built in for everyone (how resume files are named, follow-ups
  written the moment the page rings): it only repeated the app and nothing ever put it away.
  Now, after the update that built it in, the copy's Claude is told once (the profile upgrade
  `built-in-rules`) to judge each rule that may repeat it, put away the ones truly covered as
  "Now part of the app", and say one line; it is never proposed again for that behaviour;
- a complaint about how the app behaves ("why is it so slow"): never a rule. In the app
  maker's own copy it is kept as an app bug; for anyone else it is worked around. Either way
  it leaves the turn's list of reactions, so the turn is not held for it.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import app_model  # noqa: E402
import learned  # noqa: E402
import person  # noqa: E402
import profile_upgrades as U  # noqa: E402

FILE_NAMES = {"date": "2026-10-20", "area": "documents",
              "said": "call the file after me and the company",
              "rule": "name each resume file Firstname_Lastname_Resume_Company.pdf",
              "applied_to": [], "never_say": [], "status": "active"}
VOICE = {"date": "2026-10-21", "area": "voice", "said": "too formal",
         "rule": "plain and direct; no stock pleasantries", "applied_to": [], "never_say": [],
         "status": "active"}


@pytest.fixture
def profile(tmp_path, monkeypatch):
    d = tmp_path / "profile"
    shutil.copytree(os.path.join(ROOT, "profile.example"), d)
    monkeypatch.setenv(person.ENV, str(d))
    monkeypatch.setenv("LJS_STATE", str(tmp_path / "state"))   # the chat's list of reactions
    (tmp_path / "state").mkdir()
    person._modules.clear()
    person._data.clear()
    yield d
    person._modules.clear()
    person._data.clear()


def _older_copy(profile, *rows):
    """A rules file kept before the app listed what it does by itself: no `built_in` mark."""
    (profile / "learned.json").write_text(json.dumps({"entries": [dict(r) for r in rows]}),
                                          encoding="utf-8")


# ------------------------------------------------------------------ now part of the app


def test_a_rule_the_app_now_does_is_put_away_once_and_never_proposed_again(profile, monkeypatch):
    _older_copy(profile, FILE_NAMES, VOICE)
    got = learned.built_in_candidates()
    assert [(n, b["id"]) for n, _e, b in got] == [(1, "document-file-names")]

    learned.retire_built_in(1, "document-file-names", today="2026-11-06")
    n, line = learned.built_in_done(today="2026-11-06")
    assert (n, line) == (1, "1 of your rules is now part of the app, so it's off your list.")
    rows = learned.load()
    assert rows[0]["status"] == "retired" and rows[0]["retired_why"] == learned.NOW_PART
    assert rows[1]["status"] == "active"                   # their own voice rule stays
    assert [e["rule"] for e in learned.entries()] == [VOICE["rule"]]

    # Once: the same behaviour never proposes a rule again, even one said again later.
    learned.record("documents", "name the file after me", FILE_NAMES["rule"] + " always",
                   today="2026-11-07", answers=False)
    assert learned.built_in_candidates() == []
    assert learned.built_in_done(today="2026-11-07") == (0, "")

    # A behaviour a later update adds is judged once, against the rules still in force only.
    later = {"id": "voice-plain", "version": "9.9.9", "since": "2026-12-01",
             "does": "Every note is plain and direct.", "areas": ("voice",),
             "match": (r"\bplain\b",)}
    monkeypatch.setattr(learned, "BUILT_IN", learned.BUILT_IN + (later,))
    assert [(n, b["id"]) for n, _e, b in learned.built_in_candidates()] == [(2, "voice-plain")]

    # The page keeps the put-away rule, folded, saying why; the rest as before.
    shown = app_model._learned(None, {})
    away = [x for x in shown if x.get("retired")]
    assert [x["n"] for x in away] == [1] and away[0]["why"] == "Now part of the app"
    assert away[0]["app_does"].startswith("Your resume and cover letter files are named")


def test_a_new_copy_never_has_a_rule_put_away_for_what_the_app_did_before(profile):
    # Set up today: the file is made with every behaviour already checked.
    learned.record("documents", "call the file after me", FILE_NAMES["rule"],
                   today="2026-11-06", answers=False)
    assert learned.file_data()["built_in"]["checked"] == [b["id"] for b in learned.BUILT_IN]
    assert learned.built_in_candidates() == []
    assert U.by_id("built-in-rules").pending() == ""


def test_an_existing_copy_is_told_by_the_update_check_with_nobody_asked(profile, tmp_path):
    u = U.by_id("built-in-rules")
    assert u.needs == "nobody" and u.cost != "instant"     # Claude judges; nobody is asked
    assert u.pending() == ""                                # no rules file: nothing to do
    _older_copy(profile, FILE_NAMES, VOICE)
    assert u.pending() == "1 of the rules you taught may now be done by the app itself"
    assert "built-in-rules" in [p["id"] for p in U.plan()]
    assert "learned.py built-in" in u.run and "--done" in u.run
    # What the day's update check runs after every sync lists it for the background /upgrade.
    env = dict(os.environ, LJS_PROFILE=str(profile), LJS_STATE=str(tmp_path / "state"))
    out = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "profile_upgrades.py"),
                          "--plan"], env=env, capture_output=True, text=True, encoding="utf-8",
                         cwd=ROOT, timeout=300).stdout
    assert any(p["id"] == "built-in-rules" for p in json.loads(out))
    learned.built_in_done(today="2026-11-06")              # judged, none put away
    assert u.pending() == ""


# ------------------------------------------------------------------ a complaint about the app


def _cli(*argv):
    return learned.main(list(argv))


def test_a_complaint_about_the_app_is_refused_as_a_rule(profile, capsys):
    for said in ("why is it so slow", "the page is broken again", "this button does nothing",
                 "it keeps crashing", "I hate how slow it is"):
        assert learned.about_app(said), said
    for said in ("too formal", "why does the app say passionate", "name my resume after me",
                 "that opener is not working for me"):
        assert not learned.about_app(said), said
    with pytest.raises(SystemExit) as e:
        _cli("record", "--area", "other", "--said", "why is it so slow", "--rule", "be quicker")
    assert "about how the app behaves" in str(e.value) and "--about-app" in str(e.value)
    assert learned.load() == []
    # Claude may say it is truly theirs: then it is kept.
    _cli("record", "--area", "other", "--said", "the page takes too long to read, keep notes "
         "short", "--rule", "keep notes short", "--not-about-app")
    assert [e["rule"] for e in learned.entries()] == ["keep notes short"]


def test_a_complaint_goes_to_the_maker_in_their_copy_and_is_worked_round_elsewhere(
        profile, monkeypatch, capsys):
    monkeypatch.setattr(learned, "_maintainers", lambda: False)
    learned.note_reaction("I hate how slow it is", "I hate how")
    assert len(learned.pending()) == 1
    _cli("record", "--about-app", "--said", "I hate how slow it is")
    said = capsys.readouterr().out
    assert "not kept as a rule" in said and "Work round it" in said
    assert learned.pending() == []                         # the turn is not held for it
    data = learned.file_data()
    assert learned.load() == [] and not data.get("app_bugs")
    assert data["skipped"][-1]["why"] == learned.ABOUT_APP_WHY

    monkeypatch.setattr(learned, "_maintainers", lambda: True)
    learned.note_reaction("the page is broken again", "broken")
    _cli("record", "--about-app", "--said", "the page is broken again")
    said = capsys.readouterr().out
    assert "kept as an app bug" in said and "github.com" in said
    assert learned.pending() == [] and learned.load() == []
    bugs = learned.app_bugs()
    assert [b["said"] for b in bugs] == ["the page is broken again"]
    assert "the page is broken" not in bugs[0]["link"]    # the public link carries nothing of theirs
    assert [b["said"] for b in app_model._app_bugs()] == ["the page is broken again"]
    learned.close_app_bug(1)
    assert learned.app_bugs() == [] and app_model._app_bugs() == []
    # Anyone else's page never shows one.
    monkeypatch.setattr(learned, "_maintainers", lambda: False)
    learned.route_about_app("stuck loading again", maintainer=True)
    assert app_model._app_bugs() == []


def test_the_hook_says_a_complaint_is_routed_not_recorded(profile):
    got = learned.hook({"hook_event_name": "UserPromptSubmit", "prompt": "I hate how slow it is"})
    said = got["hookSpecificOutput"]["additionalContext"]
    assert "--about-app" in said and "never a rule" in said
    plain = learned.hook({"hook_event_name": "UserPromptSubmit", "prompt": "too formal"})
    assert "--about-app" not in plain["hookSpecificOutput"]["additionalContext"]
