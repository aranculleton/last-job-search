"""A task listing cut down by hand is read as it is: a missing field is unknown, never "on".

The tidy-up's listings are typed back by hand, and a list without `enabled` read every
turned-off brief task as on, so their chats were kept and old prompts mended (second audit A6;
review of fix/helpers, item 18). A missing `enabled` is unknown: nothing is changed on a task
whose state is unknown, and the step says which fields the plan needs, so nothing more is typed.
Invented ids.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import routines  # noqa: E402

REPO = "example-owner/my-job-search"


def test_a_missing_enabled_is_unknown_and_nothing_is_changed_on_it():
    rows = routines.listing({"data": [
        {"id": "trig_EXAMPLEUNKNOWN", "name": routines.BRIEF_NAME,
         "prompt": "Scheduled run: morning brief. Read automation/prompts/morning_brief.md."},
        {"id": "trig_EXAMPLEON", "name": routines.BRIEF_NAME, "enabled": True,
         "prompt": "Scheduled run: morning brief. Read automation/prompts/morning_brief.md."}]})[0]
    assert rows[0]["enabled"] is None and rows[1]["enabled"] is True
    mended = {c["args"]["trigger_id"] for c in routines.mend(rows, REPO, named={
        "trig_EXAMPLEUNKNOWN", "trig_EXAMPLEON"})}
    assert mended == {"trig_EXAMPLEON"}


def test_the_step_names_the_fields_the_plan_needs():
    import app
    for field in ("id", "title", "origin", "session_status", "updated_at", "enabled",
                  "persistent_session_id", "prompt"):
        assert field in app.TIDY_GIVE, field
