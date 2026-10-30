"""The round's line about waiting improvements was worked out afresh on every call, which
is a look at the whole profile (about five seconds), so every round, and every test that ran
one, paid it again. It is kept for the process, and a change to what the checks read
makes it be worked out again."""
from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import person  # noqa: E402
import profile_upgrades as U  # noqa: E402


@pytest.fixture
def looks(tmp_path, monkeypatch):
    """A small profile and state folder, and a look that counts how often it is made."""
    profile = tmp_path / "profile"
    profile.mkdir()
    (profile / "search.py").write_text("SCRAPE_QUERIES = []\n", encoding="utf-8")
    state = tmp_path / "state"
    state.mkdir()
    (state / "job_search_tracker.csv").write_text("id\n", encoding="utf-8")
    monkeypatch.setenv(person.ENV, str(profile))
    monkeypatch.setenv(person.STATE_ENV, str(state))
    seen = []
    row = (U.REGISTRY[0], "missing")

    def counted():
        seen.append(1)
        return [row]

    monkeypatch.setattr(U, "pending", counted)
    U.forget_line()
    yield profile, state, seen
    U.forget_line()


def test_two_calls_make_the_look_once(looks):
    _profile, _state, seen = looks
    first = U.line()
    second = U.line()
    assert first == second and first.startswith("Claude: improvements waiting")
    assert len(seen) == 1


def test_a_profile_file_written_between_calls_makes_the_look_again(looks):
    profile, _state, seen = looks
    U.line()
    (profile / "search.py").write_text("SCRAPE_QUERIES = ['a', 'b']\n", encoding="utf-8")
    U.line()
    assert len(seen) == 2
    (profile / "networking.py").write_text("VOICE = 'plain'\n", encoding="utf-8")
    U.line()
    assert len(seen) == 3


def test_a_state_file_changed_between_calls_makes_the_look_again(looks):
    _profile, state, seen = looks
    U.line()
    (state / "job_search_tracker.csv").write_text("id\n1\n", encoding="utf-8")
    U.line()
    assert len(seen) == 2
    (state / "documents").mkdir()
    (state / "documents" / "note.md").write_text("x", encoding="utf-8")
    U.line()
    assert len(seen) == 3


def test_another_profile_is_looked_at_not_taken_from_the_first(looks, tmp_path, monkeypatch):
    _profile, _state, seen = looks
    U.line()
    other = tmp_path / "other"
    other.mkdir()
    monkeypatch.setenv(person.ENV, str(other))
    U.line()
    assert len(seen) == 2


def test_forgetting_the_line_looks_again(looks):
    _profile, _state, seen = looks
    U.line()
    U.forget_line()
    U.line()
    assert len(seen) == 2


def test_rows_a_caller_passes_are_never_kept(looks):
    _profile, _state, seen = looks
    rows = [(U.REGISTRY[0], "missing")]
    assert U.line(rows).startswith("Claude: improvements waiting")
    assert U.line([]) == ""
    assert seen == []
    U.line()
    assert len(seen) == 1
