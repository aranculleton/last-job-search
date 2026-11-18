"""The chat that starts Claude on the person's computer is named like the app's other chats, and
the page calls it by the name it actually has.

Issue #289 named the app's chats "Last Job Search · <what it is for>", and the daily tidy-up
renamed the ones an install already had, once each. The chat that starts chats on the computer
was missed: it was still made and kept as "Job search: starts chats on your computer", beside
the renamed ones in the person's list of chats. Now it is made as "Last Job Search · Starts
chats on your computer", the tidy-up renames one made before, by its exact old name, once, and
its To do card and the work's line name it as it is called in their list: the old name for one
made before and not renamed (not yet, or the rename was refused), the new one once it is renamed
or made new. Every id, title and employer here is invented.
"""
from __future__ import annotations

import contextlib
import io
import os
import sys
from datetime import timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network"),
                os.path.join(ROOT, "tests")]

import app_model  # noqa: E402
import computer  # noqa: E402
import tidy  # noqa: E402
from test_a_computer_chat_is_seen_to_its_end import BELL, T, _apply  # noqa: E402
from test_a_finished_chat_closes_at_once_and_one_page_helper_stays import (  # noqa: E402
    LIVE, _chat, copy)
from test_a_tick_on_the_page_is_applied_once import _db, _w  # noqa: E402
from test_the_apps_chats_have_short_plain_names import (  # noqa: E402
    BRIEF_CHAT, COMPUTER_CHAT, RUNS_CHAT, _plan)
from test_the_computer_side_just_works import BRIDGE  # noqa: E402

assert copy  # the fixture, imported

NEW = "Last Job Search · Starts chats on your computer"
OLD = "Job search: starts chats on your computer"
STARTER = "session_EXAMPLESTARTERCHAT"
WID = "network~read~1"
WORK = (WID, _w("network", "Harbourline Bank", to="computer", title="People at Harbourline Bank",
                asked="2026-10-25T17:00:00Z"))
# A starter as one made before this change keeps it on the page: no title of its own.
MADE_BEFORE = {"chat": STARTER, "bell": BELL, "made_at": "2026-10-20T08:00:00Z",
               "ready_at": "2026-10-20T08:02:00Z"}
APP = "Last Job Search \u00b7 "


def _listed(*more) -> list[dict]:
    """The person's list of chats: the app's others under their new names, and `more`."""
    return [_chat(LIVE, APP + "Page"), _chat(BRIEF_CHAT, APP + "Brief"),
            _chat(COMPUTER_CHAT, APP + "Your computer"), _chat(RUNS_CHAT, APP + "Scheduled runs"),
            *more]


def _made_before(on: str, tmp_path) -> dict:
    db = dict(_db(WORK), meta={"computer_starter": {"data": dict(MADE_BEFORE), "version": 3}})
    return _apply(db, computer.starter_waits(db, on, T, str(tmp_path / f"before-{on}")))


def _made_now(on: str, tmp_path) -> dict:
    db = _db(WORK)
    db = _apply(db, computer.starter_made(db, STARTER, T - timedelta(minutes=5),
                                          str(tmp_path / "made")))
    db = _apply(db, computer.starter_ready(db, STARTER, BELL, T - timedelta(minutes=4),
                                           str(tmp_path / "ready")))
    return _apply(db, computer.starter_waits(db, on, T, str(tmp_path / f"now-{on}")))


def _said(db: dict) -> tuple[str, str, str]:
    """(the work's line, the To do card's words, the chat the card names), as the page has them."""
    st = computer.state(db, T, envs=BRIDGE)
    assert st["state"] == "starter_waits" and st["card"], st
    card = computer.card(st)
    assert card["open"]["url"].endswith(STARTER)
    return st["line"], card["body"], st["starter"]["title"]


def _named(db: dict, name: str) -> None:
    line, body, title = _said(db)
    other = OLD if name == NEW else NEW
    assert title == name
    assert f"“{name}”" in line and other not in line, line
    assert f"“{name}”" in body and other not in body, body


def _done(*more: str) -> None:
    with contextlib.redirect_stdout(io.StringIO()):
        assert tidy.main(["done", "--today", "2026-11-16", *more]) == 0


# ------------------------------------------------------------------ its name, and both known


def test_the_starter_is_made_under_the_new_name_and_known_by_either():
    assert computer.STARTER_TITLE == NEW and computer.OLD_STARTER_TITLE == OLD
    for name in (NEW, OLD):
        # The app's own chat, kept for good by the tidy-up whichever name it has.
        assert tidy.APP_TITLE.match(name) and tidy.STARTER_NAME.match(name), name
        assert not tidy.HELPER_NAME.match(name) and not tidy.LISTENER_NAME.match(name), name
    assert not tidy.STARTER_NAME.match("Last Job Search · Your computer")
    assert not tidy.STARTER_NAME.match("Last Job Search · People search, 16 Nov")
    # Never put away on the computer either, under the new name as under the old one: it holds
    # the person's OK to use their computer, and a new one would ask for it again.
    old = (T - timedelta(hours=5)).isoformat()
    listing = [{"title": t, "id": f"local-{i}", "status": "idle", "updated_at": old}
               for i, t in enumerate((NEW, OLD, "Last Job Search · People at Harbourline Bank"))]
    got = [r["title"] for r in computer.archivable(listing, True, now=T)]
    assert got == ["Last Job Search · People at Harbourline Bank"], got


def test_a_starter_made_now_keeps_the_name_it_was_made_with(tmp_path):
    db = _made_now("allow", tmp_path)
    assert computer.starter(db)["title"] == NEW
    # Replaced by a newer one, the old one's name goes with it, for the card that asks the
    # person to archive it.
    gone = _apply(db, computer.starter_seen(db, "archived", T, str(tmp_path / "gone")))
    assert computer.starter(gone)["gone"]["title"] == NEW


# ------------------------------------------------------------------ the daily tidy-up


def test_the_daily_tidy_up_renames_a_starter_made_before_once_and_keeps_it(copy, tmp_path,
                                                                              monkeypatch):
    mine = "session_EXAMPLEMINE"
    # Not the app's exact old name: the person's own words, never renamed.
    chats = _listed(_chat(STARTER, OLD), _chat(mine, OLD + " (my notes)"))
    out = _plan(copy, tmp_path, monkeypatch, chats)
    renames = [ln for ln in out.splitlines() if ln.startswith("rename ")]
    want = '{"session_id": "' + STARTER + '", "title": "' + NEW + '"}'
    assert [ln for ln in renames if want in ln and "set_session_title" in ln], out
    assert not [ln for ln in renames if mine in ln], out
    assert f"archive {STARTER}" not in out and f"archive {mine}" not in out, out
    # Once: asked for again on no later day, made or refused.
    _done()
    assert tidy.renamed() == {STARTER: NEW}
    out = _plan(copy, tmp_path, monkeypatch, chats)
    assert not [ln for ln in out.splitlines() if ln.startswith("rename ")], out
    # Under its new name it is kept, and left alone.
    out = _plan(copy, tmp_path, monkeypatch, _listed(_chat(STARTER, NEW)), renamed_before={})
    assert not [ln for ln in out.splitlines() if ln.startswith("rename ")], out
    assert f"archive {STARTER}" not in out, out


# ------------------------------------------------------------------ the page names it as it is


def test_the_page_names_a_starter_made_before_by_the_name_it_has(copy, tmp_path, monkeypatch):
    """Not renamed yet: the old name. Renamed by the tidy-up: the new one. The rename refused
    (it holds the person's OK, so another chat may be refused it): the old one still."""
    for on in ("allow", "mode"):
        _named(_made_before(on, tmp_path), OLD)
    allow = _made_before("allow", tmp_path)
    line, _, _ = _said(allow)
    assert line == ("Claude needs your OK once: open the chat “Job search: starts chats on your "
                    "computer”, tap Allow, then switch it to Accept edits and back to Auto.")
    # The tidy-up renames it.
    _plan(copy, tmp_path, monkeypatch, _listed(_chat(STARTER, OLD)))
    _named(allow, OLD)                    # asked for, not made yet: never said ahead of it
    _done()
    for on in ("allow", "mode"):
        _named(_made_before(on, tmp_path), NEW)
    line, _, _ = _said(_made_before("mode", tmp_path))
    assert line == ("Waiting for you to switch the chat “Last Job Search · Starts chats on your "
                    "computer” back to Auto: a setting in that chat, so nothing pops up there.")
    # What the brief and the day's update check say to the person names it the same way.
    assert any(f"“{NEW}”" in ln for ln in computer.check(allow, T, envs=BRIDGE))


def test_a_refused_rename_leaves_the_old_name_on_the_page(copy, tmp_path, monkeypatch):
    _plan(copy, tmp_path, monkeypatch, _listed(_chat(STARTER, OLD)))
    out = _plan(copy, tmp_path, monkeypatch, _listed(_chat(STARTER, OLD)))
    # The plan says how a refusal is told back.
    assert "--refused" in out, out
    _done("--refused", STARTER)
    assert tidy.renamed() == {STARTER: NEW}           # never asked for again
    assert tidy.renamed(made=True) == {}
    for on in ("allow", "mode"):
        _named(_made_before(on, tmp_path), OLD)
    out = _plan(copy, tmp_path, monkeypatch, _listed(_chat(STARTER, OLD)))
    assert not [ln for ln in out.splitlines() if ln.startswith("rename ")], out


def test_a_starter_made_now_is_named_by_its_new_name(copy, tmp_path):
    for on in ("allow", "mode"):
        _named(_made_now(on, tmp_path), NEW)


def test_the_old_starter_card_names_the_replaced_chat_as_it_is_called(copy, tmp_path,
                                                                       monkeypatch):
    def body(gone: dict) -> str:
        import types
        old = computer.old_starter({"chat": "session_EXAMPLENEWER", "gone": gone})
        ctx = types.SimpleNamespace(_got={"computer": {"old_starter": old}})
        (card,) = app_model._old_starter_card(ctx, {})
        return card["body"]

    at = "2026-11-12T15:50:17Z"
    assert f"“{OLD}” from Thu 12 Nov" in body({"chat": STARTER, "at": at})
    assert f"“{NEW}” from Thu 12 Nov" in body({"chat": STARTER, "at": at, "title": NEW})
    # One made before that the tidy-up renamed: its new name.
    _plan(copy, tmp_path, monkeypatch, _listed(_chat(STARTER, OLD)))
    _done()
    assert f"“{NEW}” from Thu 12 Nov" in body({"chat": STARTER, "at": at})
