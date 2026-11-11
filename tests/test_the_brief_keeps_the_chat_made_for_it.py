"""The brief keeps the chat made for it: recorded as its own, never moved for a short listing.

A person's registry named the brief's chat only in a field the app does not read, kept the
older `ops_relay` set-up, and had no `chat` with `own`, so every check said the brief ran in a
chat not made for it, and the tidy-up gave it a new chat about once a day: ten turned-off brief
tasks in a week. A listing that lacked the brief's chat moved it the same way, and `routines.py
check` said "clean" (audit BT-1; second audit B1, B8, root R6). Now `record --own-chat` writes
the chat as the brief's own in every set-up and leaves the old relay behind where nothing else
uses it, a later record never drops it, the tidy-up adopts a chat made for the brief that its
task already fires in rather than making another, a chat missing from a listing is asked about
before it is called gone, and `check` given the task listing fails the old shape. Invented ids.
"""
from __future__ import annotations

import datetime as dt
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import routines  # noqa: E402
import tidy  # noqa: E402

REPO = "example-owner/my-job-search"
HELPER = "session_EXAMPLEPAGEHELPER"
OWN = "session_EXAMPLEBRIEFCHAT"
OPS = "session_EXAMPLEOLDOPS"
CRON = "CRON_TZ=Europe/London 1 8 * * *"
TODAY = dt.date(2026, 11, 10)


def _old_shape():
    """The registry as one person's chat left it: ops_relay, a dead ops chat, a relay, and a
    brief whose chat is named only in a field the app does not read."""
    return {"setup": "ops_relay", "timezone": "Europe/London",
            "ops_session": {"id": OPS, "title": "Job search ops"},
            "routines": [
                {"key": "morning_brief", "name": routines.BRIEF_NAME,
                 "trigger_id": "trig_EXAMPLEB", "cron": CRON, "copy": True,
                 "prompt_file": routines.BRIEF_FILE, "fires_into": OWN + " (its own chat)"},
                {"key": "relay", "name": "Job search: relay", "mode": "fresh_session",
                 "trigger_id": "trig_EXAMPLERELAY", "cron": None,
                 "notifications": {"push": True}}]}


def _live(fires=OWN):
    return {"id": "trig_EXAMPLEB", "session": fires, "enabled": True,
            "prompt": "Scheduled run: morning brief. automation/prompts/morning_brief.md"}


def test_record_own_chat_names_it_in_every_set_up_and_leaves_the_relay(tmp_path):
    path = str(tmp_path / "routines.json")
    import json
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(_old_shape(), fh)
    routines.record(OWN, "trig_EXAMPLEB", CRON, path=path, own_chat=True)
    reg = routines.load(path)
    brief = next(r for r in reg["routines"] if routines._is_brief(r))
    assert brief["chat"] == {"session_id": OWN, "title": routines.BRIEF_NAME, "own": True}
    assert reg["setup"] == "chat_per_briefing"
    assert "ops_session" not in reg and not any(r.get("mode") == "fresh_session"
                                                for r in reg["routines"])
    assert routines.check(reg) == []
    assert routines.needs_own_chat(reg, brief, _live()) == ""
    assert routines.brief_pushes_itself(reg) is False
    # A later record of the same task without --own-chat never drops it.
    routines.record(OWN, "trig_EXAMPLEB", CRON, path=path)
    brief = next(r for r in routines.load(path)["routines"] if routines._is_brief(r))
    assert routines.owns_chat(brief)


def test_an_own_chat_in_the_routines_set_up_is_not_a_fresh_chat_each_run():
    reg = {"setup": "routines_screen", "timezone": "Europe/London", "routines": [
        {"key": "morning_brief", "name": routines.BRIEF_NAME, "trigger_id": "trig_EXAMPLEB",
         "cron": CRON, "prompt_file": routines.BRIEF_FILE,
         "chat": {"session_id": OWN, "own": True}}]}
    assert routines.needs_own_chat(reg, reg["routines"][0], _live()) == ""


def test_check_given_the_listing_fails_the_old_shape():
    reg = _old_shape()
    assert routines.check(reg) == []                       # without the listing it cannot tell
    got = routines.check(reg, triggers=[_live()])
    assert any("morning_brief" in p and OWN in p for p in got), got
    assert routines.check(reg, triggers=[_live(fires=OPS)]) == []      # a working relay


def _info(*sids):
    return {s: {"id": s, "title": routines.BRIEF_NAME if s == OWN else "Job search page",
                "session_context": {"sources": [{"git_repository": {
                    "url": f"https://github.com/{REPO}"}}]}} for s in sids}


def _plan(reg, chats, info, monkeypatch, fires=OWN):
    monkeypatch.setattr(routines, "trusted_chat", lambda: "")
    monkeypatch.setattr(tidy, "archived", lambda: [])
    triggers = [dict(_live(fires), cron=CRON)]
    return tidy.plan(chats, triggers, info, reg, {"chat": HELPER, "helper": True}, HELPER, REPO,
                     TODAY, set(), set(), set(),
                     now=dt.datetime(2026, 11, 10, 16, 0, tzinfo=dt.timezone.utc))


def _chat(sid, title):
    return {"id": sid, "title": title, "updated_at": "2026-11-10T08:00:00Z",
            "created_at": "2026-11-01T08:00:00Z", "origin": "claude_code_mcp_seed"}


def test_the_tidy_up_adopts_the_chat_made_for_the_brief_rather_than_making_another(monkeypatch):
    chats = [_chat(HELPER, "Job search page"), _chat(OWN, routines.BRIEF_NAME)]
    got = _plan(_old_shape(), chats, _info(HELPER, OWN), monkeypatch)
    calls = got["brief"]
    assert [c.get("tool") or "run" for c in calls] == ["run"], calls
    assert f"--session {OWN}" in calls[0]["run"] and "--own-chat" in calls[0]["run"]
    assert OWN not in {a["id"] for a in got["archive"]}


def test_a_brief_chat_missing_from_the_listing_is_asked_about_never_moved(monkeypatch):
    reg = {"setup": "chat_per_briefing", "timezone": "Europe/London", "routines": [
        {"key": "morning_brief", "name": routines.BRIEF_NAME, "trigger_id": "trig_EXAMPLEB",
         "cron": CRON, "prompt_file": routines.BRIEF_FILE, "copy": True,
         "chat": {"session_id": OWN, "own": True}}]}
    chats = [_chat(HELPER, "Job search page")]

    def moved(got):
        return any(c.get("tool") == "create_session" for c in got["brief"])
    got = _plan(reg, chats, _info(HELPER), monkeypatch)
    assert OWN in got["ask"] and not moved(got)
    got = _plan(reg, chats, _info(HELPER, OWN), monkeypatch)          # get_session: it is there
    assert not moved(got) and OWN not in got["ask"]
    gone = dict(_info(HELPER), **{OWN: {"id": OWN, "gone": True}})   # get_session: not found
    got = _plan(reg, chats, gone, monkeypatch)
    assert [c.get("tool") for c in got["brief"]][:2] == ["create_session", "create_trigger"]
