"""A computer starter a newer one replaced is put on the person's To do once, to archive.

It holds the person's OK to use their computer, so no chat may archive it: archive_session
answers that it "only accepts requests made from one of its owner's trusted devices" (tried on
the maintainer's, 2026-11-16). The tidy-up kept every starter for good, and two "starts chats on
your computer" chats sat in their list. Their page now names the old one, once, with its day,
until they tap Done. Invented ids.
"""
from __future__ import annotations

import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import app_model  # noqa: E402
import app_setup  # noqa: E402
import computer  # noqa: E402
import person  # noqa: E402

OLD, NEW = "session_EXAMPLEOLDSTARTER", "session_EXAMPLENEWSTARTER"


@pytest.fixture
def where(tmp_path, monkeypatch):
    import app_state
    state = tmp_path / "state"
    state.mkdir()
    prof = app_state.profile_copy(str(tmp_path / "profile"))
    monkeypatch.setenv("LJS_STATE", str(state))
    monkeypatch.setenv("LJS_PROFILE", prof)
    person.reset()
    yield prof
    person.reset()


def _ctx(rec):
    return types.SimpleNamespace(_got={"computer": {"old_starter": computer.old_starter(rec)}})


def test_the_replaced_starter_is_named_once_until_they_say_they_archived_it(where):
    rec = {"chat": NEW, "gone": {"chat": OLD, "at": "2026-11-12T15:50:17Z", "why": "silent"}}
    # Named as it is called: made before the app's chats were renamed, never renamed.
    assert computer.old_starter(rec) == {"chat": OLD, "at": "2026-11-12T15:50:17Z",
                                         "title": computer.OLD_STARTER_TITLE}
    targets: dict = {}
    (card,) = app_model._old_starter_card(_ctx(rec), targets)
    assert card["id"] == "q-old-starter" and card["kind"] == "setup"
    assert "“Job search: starts chats on your computer” from Thu 12 Nov" in card["body"]
    assert "Claude can't archive it" in card["body"] and "tap Done" in card["body"]
    assert [o["action"] for o in card["options"]] == ["setup.done"]
    assert targets["q-old-starter"]["key"] == computer.OLD_STARTER_SAID + OLD
    # Done: their word is kept, and it is never asked again for that chat.
    app_setup.save_said(computer.OLD_STARTER_SAID + OLD, "2026-11-16T10:00:00Z")
    assert app_model._old_starter_card(_ctx(rec), {}) == []


def test_no_card_for_the_starter_in_use_or_where_none_was_replaced(where):
    assert computer.old_starter({"chat": NEW}) is None
    assert computer.old_starter({"chat": NEW, "gone": {"chat": NEW, "at": ""}}) is None
    assert computer.old_starter({}) is None
    assert app_model._old_starter_card(_ctx({"chat": NEW}), {}) == []
