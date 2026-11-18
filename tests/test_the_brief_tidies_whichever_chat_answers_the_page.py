"""The brief's run tidies the app's own old chats, whichever chat answers the page, or none.

The day's tidy-up was only ever asked of a cloud chat that answers the page, when a ring woke
it: the brief asked for it only where the brief ran in that same chat. So a quiet page, a page
answered by a chat on the person's computer, or a page nobody answered, was never tidied, and
old chats piled up. Now the brief, in any cloud chat, asks for it whenever it is due: read the
page fresh, `tidy.py due --dump` (so the page's own day mark counts), then the same steps the
page's chat is given. Run from the brief's chat, the tidy-up never puts away the live page chat
or the brief's own. Every chat, page and task here is invented.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import pytest  # noqa: E402

import app  # noqa: E402
import brief  # noqa: E402
import tidy  # noqa: E402
import test_a_day_of_page_chats_is_tidied_in_full as day  # noqa: E402
from test_one_chat_answers_the_page import PAGE, Copy  # noqa: E402

LIVE = "session_EXAMPLEPAGECHAT"
BRIEF = "session_EXAMPLEBRIEFSOWNCHAT"
TODAY = "2026-11-18"


@pytest.fixture
def copy(tmp_path, monkeypatch):
    c = Copy(tmp_path)
    # The tidy-up keeps its day in the copy's git folder, as a person's copy has one.
    subprocess.run(["git", "init", "-q", c.state], check=True, timeout=60)
    c.page()
    for k, v in c.env().items():
        monkeypatch.setenv(k, v)
    yield c
    sys.path.remove(c.root)


def _in_the_briefs_chat(monkeypatch, chat=BRIEF):
    monkeypatch.setenv("CLAUDE_CODE_REMOTE", "true")
    monkeypatch.setenv("LJS_CHAT", chat)


def _due(dump):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        assert tidy.main(["due", "--dump", dump, "--today", TODAY,
                          "--now", TODAY + "T08:05:00Z"]) == 0
    return buf.getvalue()


def test_the_brief_in_its_own_cloud_chat_asks_for_the_days_tidy_up(copy, monkeypatch):
    # Another chat answers the page: the brief's own chat is not it.
    assert copy.send(copy.run("listen", copy.dump(), "--chat", LIVE, "--listen",
                              "--now", TODAY + "T07:00:00Z", CLAUDE_CODE_REMOTE="true"))
    _in_the_briefs_chat(monkeypatch)
    line = brief._tidy_due()
    assert line, "the brief in a chat of its own never asked for the day's tidy-up"
    assert PAGE in line and "tidy.py due --dump" in line and "meta, work and beats" in line
    # The page's records say nothing tidied today: the same steps the page's chat is given.
    said = _due(copy.dump("d1"))
    assert app.TIDY_GIVE in said and "tidy.py plan --dump" in said


def test_a_page_nobody_answers_is_tidied_from_the_brief_too(copy, monkeypatch):
    _in_the_briefs_chat(monkeypatch)
    assert brief._tidy_due()
    assert app.TIDY_GIVE in _due(copy.dump("d1"))


def test_the_pages_own_day_mark_counts(copy, monkeypatch):
    """Another chat, in another container, tidied today: the page holds its mark, and the
    brief's run does nothing more."""
    _in_the_briefs_chat(monkeypatch)
    os.makedirs(os.path.join(copy.db, "meta"), exist_ok=True)
    with open(os.path.join(copy.db, "meta", "tidy.json"), "w", encoding="utf-8") as fh:
        json.dump({"data": {"checked": TODAY, "at": TODAY + "T07:30:00Z", "sweep": tidy.SWEEP},
                   "version": 1}, fh)
    said = _due(copy.dump("d1"))
    assert said.strip() == tidy.NOT_DUE and "list_sessions" not in said


def test_never_in_a_chat_on_the_computer(copy, monkeypatch):
    monkeypatch.setenv("LJS_CHAT", BRIEF)
    monkeypatch.delenv("CLAUDE_CODE_REMOTE", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_CONTAINER_ID", raising=False)
    import place
    monkeypatch.setattr(place, "in_cloud", lambda: False)
    assert brief._tidy_due() == ""


def test_run_from_the_briefs_chat_it_keeps_the_page_chat_and_the_briefs_own(monkeypatch):
    """The maintainer's whole chat list of 2026-11-18 (test_a_day_of_page_chats_is_tidied_in_full),
    tidied from the brief's own chat while it runs: the live page chat and the brief's chat
    stay, the old page chats and the brief's old chat go."""
    real = tidy.plan

    def from_the_brief(chats, triggers, info, reg, listener, _this_chat, *rest, **more):
        chats = [dict(c, session_status="SESSION_STATUS_RUNNING", updated_at=day.NOW.strftime(
            "%Y-%m-%dT%H:%M:%SZ")) if c["id"] == day.BRIEF_NEW else c for c in chats]
        return real(chats, triggers, info, reg, listener, day.BRIEF_NEW, *rest, **more)

    monkeypatch.setattr(tidy, "plan", from_the_brief)
    got = day._plan(monkeypatch)
    gone = {c["id"] for c in got["archive"]}
    assert gone == {day.YESTERDAY, day.DAY_BEFORE, day.BRIEF_OLD}, got["archive"]
    kept = {c["id"]: c["why"] for c in got["keep"]}
    assert kept[day.LIVE] == "it answers the page" and kept[day.BRIEF_NEW] == "it is this chat"
    assert got["brief"] == [] and not got.get("moves")
