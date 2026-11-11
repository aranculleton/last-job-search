"""The daily clean-up of scheduled tasks touches only this copy's own app tasks.

list_triggers covers the whole account: the person's own reminders, tasks of other projects,
and the app's tasks of another copy of theirs (a cloud copy and one on a Mac). The clean-up
turned off a one-off of theirs a day past its time, would delete another copy's paused brief
after a week, and judged the computer-trust and "Job search"-named cases by name alone
(review of fix/helpers, item 1; the reviewer's probes). It now acts only on a task whose prompt
is the app's and names this copy (routines.with_copy puts it in every prompt). And the daily
sweep asks for tasks that have fired only once a week. Invented ids.
"""
from __future__ import annotations

import datetime as dt
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import routines  # noqa: E402

NOW = dt.datetime(2026, 11, 10, 12, 0, tzinfo=dt.timezone.utc)
REPO = "example-owner/my-job-search"
OTHER = "example-owner/another-copy"
CRON = "CRON_TZ=Europe/London 1 8 * * *"
STUB = "Scheduled run: morning brief. Read automation/prompts/morning_brief.md and do it."
TRUSTED = "session_EXAMPLETRUSTED"


def _reg():
    return {"setup": "chat_per_briefing", "timezone": "Europe/London", "routines": [
        {"key": "morning_brief", "name": routines.BRIEF_NAME, "trigger_id": "trig_EXAMPLELIVE",
         "cron": CRON, "prompt_file": routines.BRIEF_FILE, "copy": True,
         "chat": {"session_id": "session_EXAMPLEBRIEFCHAT", "own": True}}]}


def _clean(tasks):
    rows = routines.listing({"data": tasks})[0]
    return {c["args"]["trigger_id"]: c for c in routines.cleanup(_reg(), rows, NOW, TRUSTED,
                                                                 repo=REPO)}


def test_only_this_copys_app_tasks_are_touched():
    ours = routines.with_copy(STUB, REPO)
    theirs = routines.with_copy(STUB, OTHER)
    got = _clean([
        {"id": "trig_EXAMPLEDENTIST", "name": "Call the dentist", "enabled": True,
         "persistent_session_id": "session_EXAMPLEPERSON", "run_once_at": "2026-11-08T09:00:00Z",
         "prompt": "Remind me to call the dentist."},
        {"id": "trig_EXAMPLEOTHERBRIEF", "name": routines.BRIEF_NAME, "enabled": False,
         "persistent_session_id": "session_EXAMPLEOTHERCHAT", "cron_expression": CRON,
         "created_at": "2026-10-01T09:00:00Z", "prompt": theirs},
        {"id": "trig_EXAMPLENAMEONLY", "name": "Job search: check", "enabled": False,
         "persistent_session_id": "session_EXAMPLEX", "run_once_at": "2026-10-01T09:00:00Z",
         "created_at": "2026-10-01T08:00:00Z", "prompt": "Check something of mine."},
        {"id": "trig_EXAMPLETRUSTEDTHEIRS", "name": "A reminder", "enabled": True,
         "persistent_session_id": TRUSTED, "cron_expression": "0 23 * * *",
         "prompt": "Remind me.", "last_run": {"status": "FAILED"}},
        {"id": "trig_EXAMPLEOURBRIEF", "name": routines.BRIEF_NAME, "enabled": False,
         "persistent_session_id": "session_EXAMPLEOLDCHAT", "cron_expression": CRON,
         "created_at": "2026-10-01T09:00:00Z", "prompt": ours},
        {"id": "trig_EXAMPLEOURCHECK", "name": "Check the test brief", "enabled": True,
         "persistent_session_id": "session_EXAMPLEBRIEFCHAT",
         "run_once_at": "2026-11-08T09:00:00Z", "prompt": ours},
    ])
    assert set(got) == {"trig_EXAMPLEOURBRIEF", "trig_EXAMPLEOURCHECK"}, got


def test_tasks_that_fired_are_asked_for_once_a_week():
    import app
    import tidy
    assert "include_completed" not in app.TIDY_GIVE
    assert tidy.completed_due("2026-11-10", last="")
    assert not tidy.completed_due("2026-11-10", last="2026-11-06")
    assert tidy.completed_due("2026-11-14", last="2026-11-06")
