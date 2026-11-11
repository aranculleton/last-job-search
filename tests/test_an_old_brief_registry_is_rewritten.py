"""An old brief registry is rewritten: the chat made for the brief is adopted as its own.

A registry left in the older shape (setup ops_relay, the brief with no chat of its own, the ops
chat long gone) was never rewritten: the upgrade brief-own-chat read it with no listing and
said nothing was due, and the tidy-up adopted the brief's chat only under the exact title "Job
search: morning brief", so one called "Job search: brief (daily)" was given yet another chat
(audit PD-7, review of fix/helpers, item 19). Now the upgrade is due for that shape until a
listing has been read, a chat titled for the brief with this copy is adopted whatever its exact
words, and routines.py adopt records it from one get_session. Invented ids.
"""
from __future__ import annotations

import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import routines  # noqa: E402

REPO = "example-owner/my-job-search"
OWN = "session_EXAMPLEBRIEFCHAT"
OPS = "session_EXAMPLEOLDOPS"
CRON = "CRON_TZ=Europe/London 1 8 * * *"


def _old_shape():
    return {"setup": "ops_relay", "timezone": "Europe/London",
            "ops_session": {"id": OPS, "title": "Job search ops"},
            "routines": [
                {"key": "morning_brief", "name": "Job search: brief (daily)",
                 "trigger_id": "trig_EXAMPLEB", "cron": CRON, "copy": True,
                 "prompt_file": routines.BRIEF_FILE},
                {"key": "relay", "name": "Job search: relay", "mode": "fresh_session",
                 "trigger_id": "trig_EXAMPLERELAY", "cron": None,
                 "notifications": {"push": True}}]}


def _detail(title, repo=REPO):
    return {"id": OWN, "title": title, "session_context": {"sources": [{"git_repository": {
        "url": f"https://github.com/{repo}"}}]}}


def test_a_chat_titled_for_the_brief_with_this_copy_is_adoptable():
    assert routines.adoptable(_detail("Job search: brief (daily)"), REPO)
    assert routines.adoptable(_detail("⚡ Job search: morning brief"), REPO)
    assert not routines.adoptable(_detail("Job search page"), REPO)
    assert not routines.adoptable(_detail("Job search: brief (daily)", "example-owner/other"),
                                  REPO)
    assert not routines.adoptable(_detail("My notes"), REPO)


def test_the_upgrade_is_due_for_the_old_shape_until_a_listing_was_read(monkeypatch):
    import profile_upgrades
    u = profile_upgrades.by_id("brief-own-chat")
    monkeypatch.setattr(routines, "trusted_chat", lambda: "")
    reg = _old_shape()
    monkeypatch.setattr(routines, "load", lambda *a, **k: reg)
    assert u.pending()
    monkeypatch.setattr(routines, "load", lambda *a, **k: dict(reg, ops_checked="2026-11-10"))
    assert u.pending() == ""


def test_adopt_records_the_chat_made_for_the_brief(tmp_path, monkeypatch, capsys):
    path = tmp_path / "routines.json"
    path.write_text(json.dumps(_old_shape()), encoding="utf-8")
    monkeypatch.setattr(routines, "_repo", lambda: REPO)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(
        {"details": _detail("Job search: brief (daily)")})))
    assert routines.main(["adopt", "--session", OWN, "--trigger", "trig_EXAMPLEB", "--cron", CRON,
                          "--path", str(path), "--stdin"]) == 0
    reg = routines.load(str(path))
    brief = next(r for r in reg["routines"] if routines._is_brief(r))
    assert routines.owns_chat(brief) and brief["chat"]["session_id"] == OWN
    assert reg["setup"] == "chat_per_briefing" and "ops_session" not in reg
    # One that is not the brief's: the move instead, nothing recorded.
    path.write_text(json.dumps(_old_shape()), encoding="utf-8")
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"details": _detail("Job search page")})))
    capsys.readouterr()
    assert routines.main(["adopt", "--session", OWN, "--trigger", "trig_EXAMPLEB", "--cron", CRON,
                          "--path", str(path), "--stdin"]) == 0
    out = capsys.readouterr().out
    assert "create_session" in out
    assert not routines.owns_chat(next(r for r in routines.load(str(path))["routines"]
                                       if routines._is_brief(r)))


def test_the_tidy_up_adopts_a_brief_chat_whatever_its_exact_words(monkeypatch):
    import datetime as dt
    import tidy
    monkeypatch.setattr(routines, "trusted_chat", lambda: "")
    monkeypatch.setattr(tidy, "archived", lambda: [])
    live = "session_EXAMPLEHELPER"
    chats = [{"id": live, "title": "Job search page"},
             {"id": OWN, "title": "Job search: brief (daily)", "updated_at": "2026-11-10T08:00:00Z"}]
    triggers = [{"id": "trig_EXAMPLEB", "session": OWN, "enabled": True, "cron": CRON,
                 "prompt": routines.with_copy("Scheduled run: morning brief. Read "
                                              "automation/prompts/morning_brief.md.", REPO)}]
    got = tidy.plan(chats, triggers, {OWN: _detail("Job search: brief (daily)")}, _old_shape(),
                    {"chat": live, "helper": True}, live, REPO, dt.date(2026, 11, 10), set(),
                    set(), set(), now=dt.datetime(2026, 11, 10, 12, 0, tzinfo=dt.timezone.utc))
    assert [c.get("run", "") for c in got["brief"]] == [
        f"python3 tools/routines.py record --session {OWN} --trigger trig_EXAMPLEB --cron "
        f"\"{CRON}\" --own-chat"]


def test_a_listing_showing_it_relays_from_the_ops_chat_is_noted(tmp_path, monkeypatch, capsys):
    import shutil
    prof = tmp_path / "profile"
    shutil.copytree(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                 "profile.example"), prof, ignore=shutil.ignore_patterns("state"))
    (prof / "routines.json").write_text(json.dumps(_old_shape()), encoding="utf-8")
    monkeypatch.setenv("LJS_PROFILE", str(prof))
    monkeypatch.setattr(routines, "trusted_chat", lambda: "")
    import person
    person.reset()
    listing = tmp_path / "t.json"
    listing.write_text(json.dumps({"data": [
        {"id": "trig_EXAMPLEB", "name": "Job search: brief (daily)", "enabled": True,
         "persistent_session_id": OPS, "cron_expression": CRON,
         "prompt": "Scheduled run: morning brief. Read automation/prompts/morning_brief.md."}]}),
        encoding="utf-8")
    assert routines.main(["brief", "--triggers", str(listing), "--chat",
                          "session_EXAMPLEHELPER"]) == 0
    assert routines.load(str(prof / "routines.json")).get("ops_checked")
