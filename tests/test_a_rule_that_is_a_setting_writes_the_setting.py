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


# ------------------------------------------- SV-1, SV-2: the words are read the way they mean
#
# The person's copy, 2026-11-10 (audit SV-1, critical): the rule "App updates come by
# themselves; never ask him again" wrote `"app_updates": "when_asked"`, the opposite of what it
# says. Its words were read as one run with the restated rule after them, so "never ask him
# again App updates" read as "never ... update". The same reader decides which notes in a chat's
# memory disagree with the setting (computer.memory_conflicts), and the start step removes those,
# so a correct note was removed with it.

BY_THEMSELVES = [
    "App updates come by themselves; never ask him again",
    "updates should just happen, dont ask me",
    "stop asking me about updates, just do them",
    "never ask about app updates again, they come by themselves",
    "No, updates come by themselves",
    "Take the app's updates without asking me",
    # A "not" that belongs to waiting is about waiting: each of these wrote when_asked, from a
    # person asking for full automatic updates (2026-11-11).
    "stop waiting for my word on updates",
    "Never wait for his word on app updates",
    "dont hold updates back",
]
WAIT_FOR_ME = [
    "only update when I say. never take the app's update by itself",
    "Never take the app's update (sync_app.py in any form that merges) unless he says to update.",
    "no more automatic updates",
    "The app updates only when he asks.",
    "don't ask me, only take the app's update when I say",
    "Don't take updates without asking me",
    # The app's own words for the choice (CLAUDE.md), naming no app: missed until 2026-11-11.
    "Only update when I say",
    "only update when i say so",
    "don't update without waiting for my word",
]


@pytest.mark.parametrize("words", ["Don't update my resume until I say", "Update my CV only when I say",
                                   # The review of 2026-11-11: an update with no object of its
                                   # own was taken for the app's, and each of these wrote the
                                   # setting one way or the other.
                                   "Don't ask recruiters for an update",
                                   "Stop asking hiring managers for an update",
                                   "Don't chase for an update until two weeks have passed",
                                   "No status update emails",
                                   "Don't update LinkedIn without checking with me",
                                   "only follow up when there is an update to share",
                                   "Never ask recruiters for updates",
                                   "Send him status updates only when he asks",
                                   # Bare and loud, but no choice said: never the opposite.
                                   "STOP WAITING FOR ME TO SAY UPDATE"])
def test_an_update_to_something_of_theirs_is_never_the_apps_updates(words):
    assert learned.known_settings("other", words, words) == [], words


@pytest.mark.parametrize("words", BY_THEMSELVES)
def test_words_that_say_updates_come_by_themselves_are_read_as_auto(words):
    assert learned.known_settings("other", words, words) == [
        ("profile/person.json app_updates", "auto")], words


@pytest.mark.parametrize("words", WAIT_FOR_ME)
def test_words_that_say_updates_wait_are_read_as_when_asked(words):
    assert learned.known_settings("other", words, words) == [
        ("profile/person.json app_updates", "when_asked")], words


def test_the_rule_that_was_written_inverted_now_writes_auto_and_reads_it_back(profile):
    person.put(["app_updates"], "when_asked")
    person._data.clear()
    said = "App updates come by themselves; never ask him again"
    got = learned.record("other", said, said, today="2026-11-10")
    assert _person_json(profile)["app_updates"] == "auto"
    assert got["set"] == [("profile/person.json app_updates", "auto")]


def test_a_setting_that_does_not_read_back_as_written_stops_the_record(profile, monkeypatch):
    """Whatever writes the file, what is on disk afterwards is what counts: a write that leaves
    another value there is said at once, never recorded as done."""
    real = person.put
    monkeypatch.setattr(person, "put", lambda key, value: real(key, "when asked"))
    with pytest.raises(SystemExit) as no:
        learned.record("other", "updates come by themselves", "Updates arrive automatically.",
                       today="2026-11-10")
    assert "app_updates" in str(no.value) and "auto" in str(no.value)
    assert not [e for e in learned.load() if e.get("said") == "updates come by themselves"]


def test_a_memory_note_that_agrees_with_the_setting_is_kept(tmp_path):
    """The note says what the setting says: nothing disagrees, so the start step removes
    nothing. Read the old way it was a when_asked note, and with the setting auto it was
    taken out of the chat's memory."""
    import re as _re
    import computer
    home = tmp_path / "home"
    copy = tmp_path / "search"
    copy.mkdir()
    mem = home / ".claude" / "projects" / _re.sub(r"[^A-Za-z0-9]", "-", str(copy)) / "memory"
    mem.mkdir(parents=True)
    note = mem / "feedback_updates.md"
    note.write_text("Stop asking me about updates, just take them.\n", encoding="utf-8")
    os.environ.pop("CLAUDE_CONFIG_DIR", None)
    auto = {"profile/person.json app_updates": "auto"}
    assert computer.memory_conflicts(str(copy), home=str(home), settings=auto) == []
    wait = {"profile/person.json app_updates": "when_asked"}
    got = computer.memory_conflicts(str(copy), home=str(home), settings=wait)
    assert [(c["memory_says"], c["setting_says"]) for c in got] == [("auto", "when_asked")]


# The review of SV-1 (2026-11-11): the "don't ask" reading counted in any sentence, "no more
# asking" and "don't bother asking" still read as waiting, and a value that did not read back
# was left on disk while the command said nothing was recorded.

@pytest.mark.parametrize("words,meant", [
    ("Don't ask me again about LinkedIn. App updates: I'll say when.", "when_asked"),
    ("Never ask me which jobs to apply to. I decide on app updates.", "when_asked"),
    ("No more asking about updates", "auto"),
    ("Don't bother asking about updates, just take them", "auto"),
])
def test_not_asking_counts_only_where_it_is_about_updates(words, meant):
    assert learned.known_settings("other", words, words) == [
        ("profile/person.json app_updates", meant)], words


def test_a_value_that_does_not_read_back_is_put_back_as_it_was(profile, monkeypatch):
    person.put(["app_updates"], "when_asked")
    person._data.clear()
    real = person.put
    calls = []

    def wrong_once(key, value):
        calls.append(value)
        return real(key, "when asked" if len(calls) == 1 else value)
    monkeypatch.setattr(person, "put", wrong_once)
    with pytest.raises(SystemExit):
        learned.record("other", "updates come by themselves", "Updates arrive automatically.",
                       today="2026-11-11")
    assert _person_json(profile)["app_updates"] == "when_asked"

