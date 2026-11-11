"""The morning brief runs in a chat of its own, and nothing the app says sets a reminder in
the chat that answers the page.

Approving computer access (confirm_repository_trust) ties the chat that asks to the person's
own devices for good, and a scheduled task bound to it then fails. The brief was bound to the
chat that answers the page, and carried from helper to helper as that chat renewed; a fresh
chat each run, tried next, has no copy of the files and failed on its first run (the
maintainer, 2026-11-10). The brief now gets a chat of its own, "Job search: morning brief",
made with create_session and the person's copy, and the daily tidy-up makes it again where it
is gone, archived or approved computer access. A reminder a helper sets for itself
(send_later) cannot run there either, so no app instruction asks for one.
"""
from __future__ import annotations

import datetime as dt
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import pytest  # noqa: E402

import routines  # noqa: E402
import tidy  # noqa: E402

REPO = "example-owner/my-job-search"
HELPER = "session_EXAMPLEPAGEHELPER"
NEWHELPER = "session_EXAMPLENEXTHELPER"
OWN = "session_EXAMPLEBRIEFCHAT"
TODAY = dt.date(2026, 11, 10)
CRON = "CRON_TZ=America/Vancouver 38 7 * * *"


def _reg(chat=None):
    brief = {"key": "morning_brief", "name": routines.BRIEF_NAME, "trigger_id": "trig_EXAMPLEB",
             "cron": CRON, "prompt_file": routines.BRIEF_FILE, "copy": True}
    if chat is not None:
        brief["chat"] = chat
    return {"setup": "chat_per_briefing", "timezone": "America/Vancouver", "routines": [brief]}


def _chat(sid, title, **more):
    return dict({"id": sid, "title": title, "updated_at": "2026-11-10T08:00:00Z",
                 "created_at": "2026-11-01T08:00:00Z", "origin": "claude_code_mcp_seed"}, **more)


def _info(chats):
    return {c["id"]: {"id": c["id"], "session_context": {"sources": [{"git_repository": {
        "url": f"https://github.com/{REPO}"}}]}} for c in chats}


def _plan(reg, chats, fires=OWN, helper=HELPER, monkeypatch=None, trusted="", info=None):
    if monkeypatch is not None:
        monkeypatch.setattr(routines, "trusted_chat", lambda: trusted)
    triggers = [{"id": "trig_EXAMPLEB", "session": fires, "enabled": True,
                 "prompt": routines.with_copy(routines.stub(reg, "morning_brief"), REPO)}]
    return tidy.plan(chats, triggers, dict(_info(chats), **(info or {})), reg,
                     {"chat": helper, "helper": True},
                     helper, REPO, TODAY, set(), set(), set(),
                     now=dt.datetime(2026, 11, 10, 16, 0, tzinfo=dt.timezone.utc))


def _moved_to_its_own_chat(calls, old="trig_EXAMPLEB"):
    assert [c.get("tool") or "run" for c in calls] == [
        "create_session", "create_trigger", "run", "update_trigger"], calls
    assert calls[0]["args"] == routines.brief_chat_call(REPO)
    assert calls[0]["args"]["title"] == "Job search: morning brief"
    assert calls[0]["args"]["source_url"] == f"https://github.com/{REPO}"
    assert calls[1]["args"]["persistent_session_id"] == routines.NEW_CHAT
    assert calls[1]["args"]["cron_expression"] == CRON          # its days and time kept
    assert "create_new_session_on_fire" not in calls[1]["args"]
    assert "--own-chat" in calls[2]["run"] and f"--session {routines.NEW_CHAT}" in calls[2]["run"]
    assert calls[3]["args"] == {"trigger_id": old, "enabled": False}     # kept, never deleted
    for c in calls:
        assert HELPER not in str(c) and NEWHELPER not in str(c)


# ------------------------------------------------------------------ (a) every new install


def test_a_new_brief_is_made_in_a_chat_of_its_own_whichever_chat_asks(monkeypatch):
    for asker in (HELPER, "session_EXAMPLESETUPCHAT", ""):
        monkeypatch.setenv("LJS_CHAT", asker)
        got = routines.plan("example-owner", "my-job-search", "America/Vancouver",
                            chat=asker, now=dt.datetime(2026, 11, 10, 16, 0, tzinfo=dt.timezone.utc))
        assert got["create_session"] == routines.brief_chat_call(REPO)
        for key in ("create_trigger", "first_brief"):
            assert got[key]["persistent_session_id"] == routines.NEW_CHAT
            assert "create_new_session_on_fire" not in got[key]
        assert "--own-chat" in got["record"]
        assert not asker or asker not in str(got)


def test_recorded_with_its_own_chat_the_registry_says_so(tmp_path):
    path = str(tmp_path / "routines.json")
    routines.record(OWN, "trig_EXAMPLEB", CRON, path=path, own_chat=True)
    reg = routines.load(path)
    assert routines.owns_chat(reg["routines"][0]) and routines.check(reg) == []
    assert routines.needs_own_chat(reg, reg["routines"][0], {"session": OWN}) == ""


# ------------------------------------------------------------------ (b) the daily check mends it


def test_a_working_brief_in_its_own_chat_is_left_alone_and_never_follows_the_helper(monkeypatch):
    """(d) The daily renewal carried the brief from helper to helper. In its own chat, a new
    helper taking the page moves nothing, and the brief's chat is kept for its task."""
    chats = [_chat(OWN, "Job search: morning brief"), _chat(HELPER, "Job search page"),
             _chat(NEWHELPER, "Job search page")]
    reg = _reg({"session_id": OWN, "own": True})
    for helper in (HELPER, NEWHELPER):
        got = _plan(reg, chats, helper=helper, monkeypatch=monkeypatch)
        assert got["brief"] == [], got["brief"]
        assert OWN not in {a["id"] for a in got["archive"]}
        assert got["brief_own"] == OWN and got["brief_fires"] == OWN


@pytest.mark.parametrize("how", ["deleted", "archived", "approved computer access"])
def test_a_brief_whose_own_chat_stopped_working_gets_a_new_one_said_to_nobody(monkeypatch, how):
    reg = _reg({"session_id": OWN, "own": True})
    chats = [_chat(HELPER, "Job search page")]
    trusted = ""
    info = {}
    if how == "deleted":
        # Deleted by get_session's word, never by a listing that lacks it (second audit B1).
        info = {OWN: {"id": OWN, "gone": True}}
    if how == "archived":
        chats.append(_chat(OWN, "Job search: morning brief", session_status="archived"))
    elif how == "approved computer access":
        chats.append(_chat(OWN, "Job search: morning brief"))
        trusted = OWN
    got = _plan(reg, chats, monkeypatch=monkeypatch, trusted=trusted, info=info)
    _moved_to_its_own_chat(got["brief"])
    assert got["brief_why"]


def test_a_brief_bound_to_a_helper_that_approved_computer_access_moves_out(monkeypatch):
    """The live helper approved computer access: the brief bound to it fails from then on, so
    the tidy-up gives it a chat of its own, never another helper."""
    chats = [_chat(HELPER, "Job search page")]
    got = _plan(_reg({"session_id": HELPER}), chats, fires=HELPER, monkeypatch=monkeypatch,
                trusted=HELPER)
    _moved_to_its_own_chat(got["brief"])
    assert HELPER not in {a["id"] for a in got["archive"]}         # the live helper stays


def test_a_brief_in_the_helper_a_renewal_replaced_moves_to_its_own_chat_not_the_new_helper(
        monkeypatch):
    chats = [_chat(HELPER, "Job search page (finishing up)"), _chat(NEWHELPER, "Job search page")]
    got = _plan(_reg({"session_id": HELPER}), chats, fires=HELPER, helper=NEWHELPER,
                monkeypatch=monkeypatch)
    _moved_to_its_own_chat(got["brief"])
    assert {a["id"]: a["why"] for a in got["archive"]}.get(HELPER) == \
        "the brief moved into a chat of its own"


def test_the_tidy_up_says_it_has_moved_only_once_the_listing_shows_its_own_chat(
        monkeypatch, tmp_path, capsys):
    import json
    monkeypatch.setattr(routines, "trusted_chat", lambda: "")
    monkeypatch.setattr(tidy, "_listener", lambda d: {"chat": HELPER, "kind": "cloud", "helper": True})
    monkeypatch.setattr(tidy, "_repo", lambda: REPO)
    monkeypatch.setattr(tidy, "_campaign_chats", lambda: set())
    monkeypatch.setattr(tidy, "unmerged", lambda: set())
    monkeypatch.setattr(tidy, "on_github", lambda: set(), raising=False)
    monkeypatch.setattr(routines, "load", lambda *a, **k: _reg({"session_id": OWN, "own": True}))
    sessions = tmp_path / "s.json"
    sessions.write_text(json.dumps({"data": [_chat(HELPER, "Job search page")]}))
    tasks = tmp_path / "t.json"
    tasks.write_text(json.dumps({"data": [{"id": "trig_EXAMPLEB", "persistent_session_id": OWN,
                                           "enabled": True}]}))
    # get_session could not find it: gone by its word, not by the listing (second audit B1).
    gone = tmp_path / "d.json"
    gone.write_text(json.dumps({"id": OWN, "gone": True}))
    assert tidy.main(["plan", "--chat", HELPER, "--today", TODAY.isoformat(),
                      "--sessions", str(sessions), "--triggers", str(tasks),
                      "--details", str(gone)]) == 0
    said = capsys.readouterr().out
    assert "brief 1: create_session" in said and "brief 2: create_trigger" in said
    assert "it has not moved, so never say it has" in said
    assert "saying nothing to the person" in said


# ------------------------------------------------------------------ (c) existing copies


def test_existing_copies_bound_to_the_helper_or_a_fresh_chat_each_run_are_moved_by_an_upgrade(
        monkeypatch):
    import profile_upgrades
    u = profile_upgrades.by_id("brief-own-chat")
    assert u.needs == "nobody" and "routines.py brief --triggers" in u.run
    monkeypatch.setattr(routines, "trusted_chat", lambda: "")
    for reg, pending in ((_reg({"session_id": HELPER}), True),
                         (dict(_reg(), setup="routines_screen"), True),       # fresh chat a run
                         (_reg({"session_id": OWN, "own": True}), False),
                         # The older ops shape, never read against a listing: due, so a
                         # listing says where it runs (PD-7; review of fix/helpers, item 19)...
                         ({"setup": "ops_relay", "timezone": "America/Vancouver",
                           "ops_session": {"id": "session_EXAMPLEOPS"},
                           "routines": _reg()["routines"]}, True),
                         # ...and once one showed it relays from the ops chat, it stays.
                         ({"setup": "ops_relay", "timezone": "America/Vancouver",
                           "ops_session": {"id": "session_EXAMPLEOPS"},
                           "ops_checked": "2026-11-10", "routines": _reg()["routines"]}, False)):
        monkeypatch.setattr(routines, "load", lambda *a, reg=reg, **k: reg)
        assert bool(u.pending()) is pending, reg
    # A routine the person made themself, notifications on, works and stays.
    theirs = dict(_reg(), setup="routines_screen")
    theirs["routines"][0]["notifications"] = {"push": True}
    monkeypatch.setattr(routines, "load", lambda *a, **k: theirs)
    assert u.pending() == ""


def test_the_computer_trust_check_moves_the_brief_into_its_own_chat_recorded_as_such():
    import computer
    lines = computer.trust_check(HELPER, {"data": [
        {"id": "trig_EXAMPLEB", "name": routines.BRIEF_NAME, "persistent_session_id": HELPER,
         "cron_expression": CRON, "enabled": True, "prompt": "Scheduled run: morning brief."}]})
    assert '"title": "Job search: morning brief"' in lines[0]
    assert "--own-chat" in lines[1] and "routines_screen" not in lines[1]
    assert "create_new_session_on_fire" not in "".join(lines)


# ------------------------------------------------------------------ 31: no reminder in a helper


SCANNED = [os.path.join("tools", f) for f in os.listdir(os.path.join(ROOT, "tools"))
           if f.endswith(".py")] + [
    "RUNBOOK.md", "CLAUDE.md", "SETUP.md", "automation/README.md",
    *[os.path.join("automation", "prompts", f)
      for f in os.listdir(os.path.join(ROOT, "automation", "prompts")) if f.endswith(".md")],
    *[os.path.join(dp, f).replace(ROOT + os.sep, "")
      for dp, _d, fs in os.walk(os.path.join(ROOT, ".claude")) for f in fs if f.endswith(".md")]]
NEVER = re.compile(r"\b(?:never|no|not|nor|none|cannot|can't)\b", re.I)


def test_no_app_instruction_asks_a_chat_to_set_itself_a_reminder():
    """A send_later reminder the helper set for itself could not run once it had approved
    computer access (the maintainer, 2026-11-10). Every line that names send_later, or asks
    for a check-in to be set or scheduled, says never; what waits is taken by the brief's next
    run or the page's next check-in."""
    found = []
    for rel in SCANNED:
        path = os.path.join(ROOT, rel)
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as fh:
            for n, line in enumerate(fh, 1):
                asks = ("send_later" in line or re.search(
                    r"\b(?:set|schedule|ask for)s?\b[^.]{0,30}\bcheck-in\b", line, re.I))
                if asks and not NEVER.search(line):
                    found.append(f"{rel}:{n}: {line.strip()}")
    assert found == []


def test_the_tidy_up_prints_no_reminder_when_an_old_helper_is_kept(monkeypatch, tmp_path, capsys):
    """The live helper kept the helper it took over from (still finishing) and asked for a
    check-in half an hour on: that reminder could not run once the helper had approved
    computer access. The tidy-up is due again by itself (tidy.due), so none is set."""
    import json
    monkeypatch.setattr(routines, "trusted_chat", lambda: "")
    monkeypatch.setenv("LJS_STATE", str(tmp_path))
    monkeypatch.setattr(tidy, "_checked_path", lambda: str(tmp_path / "checked.json"))
    old = "session_EXAMPLEOLDHELPER"
    listener = {"chat": HELPER, "kind": "cloud", "helper": True, "since": "2026-11-10T15:50:00Z",
                "took_from": old, "took_from_helper": True}
    monkeypatch.setattr(tidy, "_listener", lambda d: listener)
    monkeypatch.setattr(tidy, "_repo", lambda: REPO)
    monkeypatch.setattr(tidy, "_campaign_chats", lambda: set())
    monkeypatch.setattr(tidy, "unmerged", lambda: set())
    monkeypatch.setattr(tidy, "on_github", lambda: set(), raising=False)
    monkeypatch.setattr(routines, "load", lambda *a, **k: _reg({"session_id": OWN, "own": True}))
    sessions = tmp_path / "s.json"
    sessions.write_text(json.dumps({"data": [
        _chat(HELPER, "Job search page"), _chat(OWN, "Job search: morning brief"),
        _chat(old, "Job search page (finishing up)", status="running")]}))
    tasks = tmp_path / "t.json"
    tasks.write_text(json.dumps({"data": [{"id": "trig_EXAMPLEB", "persistent_session_id": OWN,
                                           "enabled": True}]}))
    details = tmp_path / "d.json"
    details.write_text(json.dumps(dict(_info([_chat(old, "x")])[old], status="running")))
    assert tidy.main(["plan", "--chat", HELPER, "--now", "2026-11-10T16:00:00Z",
                      "--sessions", str(sessions), "--triggers", str(tasks),
                      "--details", str(details), "--verbose"]) == 0
    said = capsys.readouterr().out
    assert f"keep {old}" in said, said
    assert "send_later" not in said and "check-in: " not in said
