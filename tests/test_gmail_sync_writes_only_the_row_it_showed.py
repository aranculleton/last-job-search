"""An approved /gmail-sync write goes only to the row as it was shown.

Approval is for a batch shown at one moment, and several chats run against one tracker.
Step 7a wrote `status` straight from the proposal, so "approve all" after another chat
had moved a row (an offer recorded, a rejection logged) overwrote the newer status with
an older reading of an email. It now re-reads each row and writes only where the status
is still the one the person approved against.
"""
from __future__ import annotations

from pathlib import Path

TEXT = (Path(__file__).resolve().parent.parent / ".claude" / "commands"
        / "gmail-sync.md").read_text(encoding="utf-8")
STEP7A = TEXT.split("### Step 7a", 1)[1].split("## Step 8", 1)[0]


def test_step_7a_re_reads_the_row_and_skips_one_that_moved():
    first = STEP7A.split("1. **Tracker", 1)[0]
    assert "re-read each row" in first
    assert "Read `job_search_tracker.csv` again" in first
    assert "write nothing for that row" in first
    assert "Approval was for the row as shown" in first


def test_the_closing_summary_names_a_row_that_was_not_written():
    done = TEXT.split("## Step 10", 1)[1]
    assert "not written (Step 7a)" in done


def test_the_rule_is_in_the_important_rules():
    rules = TEXT.split("## Important Rules", 1)[1]
    assert "status has changed since it was shown" in rules
