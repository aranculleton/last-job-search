"""Another copy's scheduled task is never given this copy's address.

mend added the line that gets the files, naming this copy, to every app task whose prompt
lacked it, whichever copy it belonged to: list_triggers covers the whole account, and a person
with a cloud copy and a Mac copy had the other copy's task pointed at this one (review of
fix/helpers, item 20). Only the tasks this copy's registry names are mended now. Invented ids.
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
LIVE = "session_EXAMPLEHELPER"
STUB = "Scheduled run: job round. Read automation/prompts/job_round.md and do it."


def test_only_the_tasks_this_registry_names_are_mended(monkeypatch):
    monkeypatch.setattr(routines, "trusted_chat", lambda: "")
    monkeypatch.setattr(tidy, "archived", lambda: [])
    reg = {"setup": "chat_per_briefing", "timezone": "Europe/London", "routines": [
        {"key": "job_round", "name": "Job search: shortlist", "trigger_id": "trig_EXAMPLEOURS",
         "cron": "CRON_TZ=Europe/London 52 6 * * 1", "prompt_file": "automation/prompts/job_round.md",
         "chat": {"session_id": LIVE}, "paused": "off"}]}
    tasks = routines.listing({"data": [
        {"id": "trig_EXAMPLEOURS", "name": "Job search: shortlist", "enabled": True,
         "persistent_session_id": LIVE, "prompt": STUB},
        {"id": "trig_EXAMPLEOTHERCOPY", "name": "Job search: shortlist", "enabled": True,
         "persistent_session_id": "session_EXAMPLEMAC", "prompt": STUB}]})[0]
    got = tidy.plan([{"id": LIVE, "title": "Job search page"}], tasks, {}, reg,
                    {"chat": LIVE, "helper": True}, LIVE, REPO, dt.date(2026, 11, 10), set(),
                    set(), set(), now=dt.datetime(2026, 11, 10, 12, 0, tzinfo=dt.timezone.utc))
    assert [c["args"]["trigger_id"] for c in got["mend"]] == ["trig_EXAMPLEOURS"]
