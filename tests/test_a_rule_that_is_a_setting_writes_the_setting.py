"""A rule the person gives that is a setting is that setting, written in the same command.

Engine audit 30 (2026-11-03): "Never take the app's update unless he says to update" was
recorded in learned.json against `sync_app.py`, an app file the next update puts back, and
`"app_updates": "when_asked"` never reached person.json, so ten updates came in by
themselves. `learned.py record` now writes the settings it knows (how updates arrive, how old
a posting may be), names them in `applied_to`, and refuses an app file as a rule's home.
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

import learned  # noqa: E402
import person  # noqa: E402

LEARNED = os.path.join(ROOT, "tools", "learned.py")


@pytest.fixture
def profile(tmp_path, monkeypatch):
    d = tmp_path / "profile"
    shutil.copytree(os.path.join(ROOT, "profile.example"), d,
                    ignore=shutil.ignore_patterns("state", "tests", "__pycache__"))
    monkeypatch.setenv(person.ENV, str(d))
    person._modules.clear()
    person._data.clear()
    yield d
    person._modules.clear()
    person._data.clear()


def _person_json(profile):
    with open(profile / "person.json", encoding="utf-8") as fh:
        return json.load(fh)


def test_update_only_when_i_say_is_written_into_person_json(profile):
    """The audit's own steps: the rule as it was recorded, in its own words, and the file it
    was filed under. The record is refused for the app file; recorded with no file, it writes
    the setting itself."""
    said = "only update when I say"
    rule = ("Never take the app's update (sync_app.py in any form that merges) unless he says "
            "to update.")
    with pytest.raises(SystemExit) as no:
        learned.record("other", said, rule, applied_to=["sync_app.py"], today="2026-10-25")
    assert "app's own file" in str(no.value) and "app_updates" not in _person_json(profile)
    got = learned.record("other", said, rule, today="2026-10-25")
    assert _person_json(profile)["app_updates"] == "when_asked"
    assert "profile/person.json app_updates" in got["applied_to"]
    person._data.clear()
    assert "profile/person.json app_updates" in learned.locked()
    # And back: by themselves again.
    learned.record("other", "updates can come by themselves again",
                   "App updates arrive automatically again.", today="2026-11-03")
    assert _person_json(profile)["app_updates"] == "auto"


def test_a_search_window_said_in_words_is_the_window(profile):
    """The person's "I TOLD U TO GET RECENT ONES" became "only jobs from the last 10 days" in
    learned.json while profile/search.py stayed at the window it had."""
    got = learned.record("search", "I TOLD U TO GET RECENT ONES",
                         "Only jobs posted in the last 10 days.", today="2026-11-03")
    assert "profile/search.py JOB_AGE_DAYS" in got["applied_to"]
    person._modules.clear()
    assert person.module("search").JOB_AGE_DAYS == 10
    # And the round searches with it: a 10 was read as 14, silently (engine audit 25).
    r = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, 'tools'); "
                        "import run_round; print(run_round._job_age_days())"], cwd=ROOT,
                       env=dict(os.environ, **{person.ENV: str(profile)}),
                       capture_output=True, text=True, encoding="utf-8")
    assert r.stdout.strip() == "10", r.stdout + r.stderr
    # A follow-up rule in days is no search window.
    assert learned.known_settings("messages", "chase after two weeks",
                                  "Follow up within 14 days of no reply.") == []
    assert learned.known_settings("documents", "only update my resume when I say",
                                  "Update the resume only when asked.") == []


def test_the_command_says_what_it_set(profile):
    r = subprocess.run([sys.executable, LEARNED, "record", "--area", "other", "--said",
                        "no more automatic updates", "--rule",
                        "The app updates only when he asks."],
                       env=dict(os.environ, **{person.ENV: str(profile)}),
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    assert "set: profile/person.json app_updates = \"when_asked\"" in r.stdout
    assert _person_json(profile)["app_updates"] == "when_asked"
