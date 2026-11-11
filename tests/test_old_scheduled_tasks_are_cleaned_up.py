"""Old scheduled tasks are cleaned up by the daily tidy-up, and only those that can no longer run.

A person's account held 10 to 13 turned-off "Job search: morning brief" tasks, each left when
the brief moved to a new chat ("turned off, kept, never deleted"), and test check-ins still on:
one bound to the chat that approved computer access failed every run with ACCESS_DENIED, and
one-off ones never cleaned up (audit BT-9, H-5). Now the tidy-up deletes a brief task the
registry no longer names once it has been off more than a week, turns off a one-off task a day
past its time, and turns off a task bound to the chat that approved computer access whose last
run failed. The registry's own tasks and anything else are left alone. Invented ids.
"""
from __future__ import annotations

import datetime as dt
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import routines  # noqa: E402
import tidy  # noqa: E402

REPO = "example-owner/example-copy"
TODAY = dt.date(2026, 11, 10)
NOW = dt.datetime(2026, 11, 10, 12, 0, tzinfo=dt.timezone.utc)
LIVE = "session_EXAMPLEPAGEHELPER"
OWN = "session_EXAMPLEBRIEFCHAT"
TRUSTED = "session_EXAMPLETRUSTEDCHAT"
CRON = "CRON_TZ=Europe/London 1 8 * * *"


def _reg():
    return {"setup": "chat_per_briefing", "timezone": "Europe/London", "routines": [
        {"key": "morning_brief", "name": routines.BRIEF_NAME, "trigger_id": "trig_EXAMPLELIVEBRIEF",
         "cron": CRON, "prompt_file": routines.BRIEF_FILE, "copy": True,
         "chat": {"session_id": OWN, "own": True}}]}


def _task(tid, name, enabled=True, session=OWN, created="2026-10-20T08:00:00Z", **more):
    # This copy's own app tasks carry its address in their prompt (routines.with_copy): only
    # those are ever cleaned (review of fix/helpers, item 1).
    t = {"id": tid, "name": name, "enabled": enabled, "persistent_session_id": session,
         "created_at": created, "prompt": routines.with_copy(
             "Scheduled run: morning brief. Read automation/prompts/morning_brief.md and do it.",
             REPO)}
    t.update(more)
    return t


def _clean(triggers, monkeypatch, trusted=TRUSTED):
    monkeypatch.setattr(routines, "trusted_chat", lambda: trusted)
    tasks = routines.listing({"data": triggers})[0]
    own = {"id": OWN, "title": routines.BRIEF_NAME, "updated_at": "2026-11-10T08:00:00Z"}
    got = tidy.plan([own], tasks, {}, _reg(), {"chat": LIVE, "helper": True}, LIVE, REPO, TODAY,
                    set(), set(), set(), now=NOW)
    return {(c["tool"], c["args"]["trigger_id"]): c for c in got.get("clean") or []}


def test_old_brief_tasks_off_for_a_week_are_deleted_and_the_live_one_kept(monkeypatch):
    got = _clean([
        _task("trig_EXAMPLELIVEBRIEF", routines.BRIEF_NAME, cron_expression=CRON),
        _task("trig_EXAMPLEOLDBRIEF1", routines.BRIEF_NAME, enabled=False, cron_expression=CRON,
              session="session_EXAMPLEOLDCHAT1"),
        _task("trig_EXAMPLEOLDBRIEF2", routines.BRIEF_NAME, enabled=False, cron_expression=CRON,
              session="session_EXAMPLEOLDCHAT2", created="2026-11-08T08:00:00Z"),
        # A task that starts a fresh chat each run: deleting it deletes its chats, so it stays.
        _task("trig_EXAMPLEOLDBRIEF3", routines.BRIEF_NAME, enabled=False, cron_expression=CRON,
              session=""),
    ], monkeypatch)
    assert ("delete_trigger", "trig_EXAMPLEOLDBRIEF1") in got
    assert ("delete_trigger", "trig_EXAMPLEOLDBRIEF2") not in got          # off only two days
    assert not any(tid in ("trig_EXAMPLELIVEBRIEF", "trig_EXAMPLEOLDBRIEF3") for _tool, tid in got)


def test_a_one_off_past_its_time_and_a_task_that_cannot_open_its_chat_are_turned_off(
        monkeypatch):
    got = _clean([
        _task("trig_EXAMPLEONEOFFOLD", "Check the test brief", run_once_at="2026-11-08T23:00:00Z"),
        _task("trig_EXAMPLEONEOFFSOON", "Check the test brief", run_once_at="2026-11-10T11:30:00Z"),
        _task("trig_EXAMPLETRUSTED", "Check the computer test", session=TRUSTED,
              cron_expression="0 23 * * *",
              last_run={"status": "FAILED", "fired_at": "2026-11-09T23:00:00Z"}),
        _task("trig_EXAMPLETHEIRS", "Water the plants", session="session_EXAMPLETHEIRS",
              cron_expression="0 18 * * *", prompt="Remind me to water the plants."),
    ], monkeypatch)
    assert got[("update_trigger", "trig_EXAMPLEONEOFFOLD")]["args"] == {"trigger_id": "trig_EXAMPLEONEOFFOLD",
                                                                 "enabled": False}
    assert ("update_trigger", "trig_EXAMPLETRUSTED") in got
    assert not any(tid in ("trig_EXAMPLEONEOFFSOON", "trig_EXAMPLETHEIRS") for _tool, tid in got)


def test_the_plan_prints_them_to_make_saying_nothing(monkeypatch, tmp_path, capsys):
    import argparse
    import json
    import app_listen
    import app_setup
    monkeypatch.setattr(tidy, "_git_dir", lambda: str(tmp_path))
    monkeypatch.setattr(tidy, "archived", lambda: [])
    monkeypatch.setattr(tidy, "_listener", lambda dump: {"chat": LIVE, "helper": True})
    monkeypatch.setattr(tidy, "_repo", lambda: REPO)
    monkeypatch.setattr(tidy, "unmerged", lambda: set())
    monkeypatch.setattr(tidy, "on_github", lambda: set())
    monkeypatch.setattr(tidy, "_campaign_chats", lambda: set())
    monkeypatch.setattr(app_listen, "this_chat", lambda chat="": LIVE)
    monkeypatch.setattr(app_listen, "nested", lambda chat: False)
    monkeypatch.setattr(app_setup, "doorbells_due", lambda today: False)
    monkeypatch.setattr(routines, "load", lambda *a, **k: _reg())
    monkeypatch.setattr(routines, "saw", lambda tasks: None)
    monkeypatch.setattr(routines, "trusted_chat", lambda: TRUSTED)
    triggers = tmp_path / "t.json"
    triggers.write_text(json.dumps({"data": [
        _task("trig_EXAMPLELIVEBRIEF", routines.BRIEF_NAME, cron_expression=CRON),
        _task("trig_EXAMPLEOLDBRIEF1", routines.BRIEF_NAME, enabled=False, cron_expression=CRON,
              session="session_EXAMPLEOLDCHAT1")]}), encoding="utf-8")
    sessions = tmp_path / "s.json"
    sessions.write_text(json.dumps({"data": [
        {"id": OWN, "title": routines.BRIEF_NAME, "updated_at": "2026-11-10T08:00:00Z"}]}),
        encoding="utf-8")
    a = argparse.Namespace(today="", now="2026-11-10T12:00:00Z", stdin=False,
                           triggers=[str(triggers)], sessions=[str(sessions)], details=[],
                           dump="", chat=LIVE,
                           verbose=False)
    assert tidy.run_plan(a) == 0
    out = capsys.readouterr().out
    assert 'clean 1: delete_trigger {"trigger_id": "trig_EXAMPLEOLDBRIEF1"}' in out
    assert "nothing to tidy" not in out


def test_fired_one_offs_of_the_apps_are_found_and_taken_away(monkeypatch):
    """list_triggers hides a one-off that has fired unless asked (include_completed), so the
    test check-ins piled up unseen (second audit B9). The tidy-up asks for them, and deletes
    one of the app's, bound to a chat, a week after it fired; anything else stays."""
    got = _clean([
        _task("trig_EXAMPLEFIRED", "Check the test brief", enabled=False,
              run_once_at="2026-11-01T08:00:00Z", ended_reason="run_once_fired",
              last_run={"status": "SUCCEEDED", "fired_at": "2026-11-01T08:00:00Z"}),
        _task("trig_EXAMPLEFIREDLATE", "Check the test brief", enabled=False,
              run_once_at="2026-11-09T08:00:00Z", ended_reason="run_once_fired",
              last_run={"status": "SUCCEEDED", "fired_at": "2026-11-09T08:00:00Z"},
              created="2026-11-09T07:00:00Z"),
        dict(_task("trig_EXAMPLEFIREDTHEIRS", "Water the plants", enabled=False,
                   session="session_EXAMPLETHEIRS", run_once_at="2026-11-01T08:00:00Z",
                   ended_reason="run_once_fired"), prompt="Remind me to water the plants."),
    ], monkeypatch)
    assert ("delete_trigger", "trig_EXAMPLEFIRED") in got
    assert not any(tid in ("trig_EXAMPLEFIREDLATE", "trig_EXAMPLEFIREDTHEIRS") for _t, tid in got)
    import app
    assert "include_completed" in app.TIDY_COMPLETED          # asked for once a week
