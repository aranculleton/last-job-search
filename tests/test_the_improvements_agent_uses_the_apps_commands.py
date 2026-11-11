"""The agent that applies the improvements moves its page item by the app's own commands, works
in a worktree of its own, and its end is handled.

The second audit of 2026-11-10 (C5): .claude/commands/upgrade.md had the agent write its
`update~upgrades-<date>` item by hand, against the rule that every move of a work item is an
app.py command; its report said its question card would show on the next refresh; nothing told
the chat that started it what to do when it ended, so the page was left as it was; and it ran
in the same folder as that chat, whose save could sweep in half an upgrade. Every chat id here
is invented.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import app_setup  # noqa: E402

UPGRADE = os.path.join(ROOT, ".claude", "commands", "upgrade.md")
APP = os.path.join(ROOT, "tools", "app.py")
NOW = "2026-11-10T09:00:00Z"
WID = "update~upgrades-20261110"


def _upgrade() -> str:
    with open(UPGRADE, encoding="utf-8") as fh:
        return " ".join(fh.read().split())


def test_the_page_item_is_made_moved_and_finished_by_commands():
    text = _upgrade()
    step = text.split("6. **On the page.**", 1)[1].split("Stop at the budget", 1)[0]
    for said in ("app.py ask", "--kind update", "--here", "app.py pin", "app.py done"):
        assert said in step, (said, step)
    assert "`status: running`" not in step and "result.summary" not in step, step


def test_its_report_ends_on_the_line_the_starting_chat_acts_on():
    text = _upgrade()
    report = text.split("## Step 5: Report", 1)[1]
    assert "Finished the improvements: bring the page up to date." in report
    assert "isolation worktree" in app_setup.UPGRADE_AGENT
    assert "Finished the improvements" in app_setup.UPGRADE_AGENT
    assert "app.py view" in app_setup.UPGRADE_AGENT


def test_the_commands_it_names_work_for_an_update(tmp_path):
    dump = tmp_path / "dump"
    (dump / "work").mkdir(parents=True)
    run = lambda *a: subprocess.run([sys.executable, APP, *a, "--now", NOW],  # noqa: E731
                                    capture_output=True, text=True, encoding="utf-8")
    r = run("ask", str(dump), "--kind", "update", "--title", "Improvements to your search",
            "--id", WID, "--here", "--chat", "session_EXAMPLEagent1", "--out", str(tmp_path / "a"))
    assert r.returncode == 0, r.stderr
    batch = json.loads(r.stdout)["batches"][0]
    with open(batch, encoding="utf-8") as fh:
        entry = json.load(fh)[0]
    with open(entry["file_path"], encoding="utf-8") as fh:
        item = json.load(fh)
    assert entry["doc_id"] == WID and item["status"] == "running" and item["in_chat"]
    assert item["claimed_by"] == "session_EXAMPLEagent1"


def test_the_agent_that_mends_their_own_tests_works_in_a_worktree_too():
    """The same agent, started for the person's own tests after an update (sync_app
    OWN_TESTS_STEP), ran in the chat's own folder too, where a save could take half of it."""
    import sync_app
    assert "isolation worktree" in sync_app.OWN_TESTS_STEP
    assert "Finished the improvements" in sync_app.OWN_TESTS_STEP
