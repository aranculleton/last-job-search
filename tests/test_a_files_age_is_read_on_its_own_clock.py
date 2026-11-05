"""A file's age is read on the clock that stamped it, never on Python's (tools/file_clock.py).

With the suite's clock moved 400 days on (tools/everywhere.sh suite 400-days), every file
written that moment read as 400 days old: a landing called today's notes "over a week old",
the spare copies of another chat's files were cleared at once, and a search's shortlist saved
a minute ago read as saved before the search began (2026-11-05). Here Python's clock is moved
in the test itself, so the real clock shows it too. Invented names."""
# ruff: noqa: F811  (the landing tests' `copy` fixture, imported and taken as a parameter)
import datetime as dt
import os
import sys
import time
import types

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

import file_clock  # noqa: E402
import merge_state  # noqa: E402
import save_state  # noqa: E402
from tests.test_a_chat_lands_its_work_in_one_command import copy, write  # noqa: E402,F401

AHEAD = 400 * 86400


def _ahead(monkeypatch):
    real = time.time
    monkeypatch.setattr(time, "time", lambda: real() + AHEAD)


def test_a_file_written_now_is_not_old_whatever_pythons_clock_says(copy, monkeypatch):
    _origin, chat, _other = copy
    write(chat, "profile/notes.md", "first\na note from today\n")
    _ahead(monkeypatch)
    assert save_state.old_unsaved(str(chat)) == []
    assert file_clock.age(os.path.join(str(chat), "profile", "notes.md")) < 60


def test_a_spare_copy_made_now_is_kept_whatever_pythons_clock_says(tmp_path, monkeypatch):
    d = tmp_path / merge_state.SPARE_DIR
    d.mkdir()
    (d / "new").write_text("y")
    _ahead(monkeypatch)
    merge_state.tidy_spares(str(tmp_path))
    assert os.listdir(d) == ["new"]


def test_a_shortlist_saved_a_minute_ago_is_saved_whatever_pythons_clock_says(tmp_path,
                                                                             monkeypatch):
    import app_model
    import page_db
    saved = tmp_path / "r10.json"
    saved.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(app_model, "newest_round", lambda: str(saved))
    ahead = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=AHEAD)

    class Moved(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return ahead if tz else ahead.replace(tzinfo=None)
    monkeypatch.setattr(page_db, "dt", types.SimpleNamespace(
        datetime=Moved, timezone=dt.timezone, timedelta=dt.timedelta, date=dt.date))
    claimed = (ahead - dt.timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert page_db.search_unsaved({"claimed_at": claimed}) == ""
    # And one saved before the search was taken on is still not saved.
    old = os.path.getmtime(saved) - 3600
    os.utime(saved, (old, old))
    assert "not saved yet" in page_db.search_unsaved({"claimed_at": claimed})
