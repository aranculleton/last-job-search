"""/gmail-sync reads an employer's email the way it reads.

Step 5 listed phrases with no order and no exceptions. "If your application is a good
fit, we will contact you to schedule a call" sits in ordinary acknowledgements and holds
"schedule a call", which the table read as an interview invite; "we will not be
extending an offer" holds offer words; a hiring freeze had nowhere to go but `rejected`;
an employer asking the person for their availability had no row at all, so the nudge
clock carried on at someone who was waiting on them; and nothing recorded which sentence
a proposal was read from.
"""
from __future__ import annotations

import re
from pathlib import Path

TEXT = (Path(__file__).resolve().parent.parent / ".claude" / "commands"
        / "gmail-sync.md").read_text(encoding="utf-8")
STEP5 = TEXT.split("## Step 5", 1)[1].split("## Step 6", 1)[0]
TABLE = [ln for ln in STEP5.splitlines() if ln.startswith("| ") and not ln.startswith("| Signal")]


def _signals():
    return [ln.split("|")[1].strip() for ln in TABLE if not ln.startswith("|---")]


def test_rejection_is_read_before_offer_and_the_table_is_in_that_order():
    assert re.search(r"Precedence.*rejection first, then offer", STEP5)
    order = _signals()
    assert order.index("Rejection") < order.index("Offer extended")
    assert order[-1] == "Application ack"


def test_what_is_not_a_signal_is_named():
    noise = STEP5.split("**Not a signal", 1)[1].split("**Precedence", 1)[0]
    for kind in ("newsletters", "job alerts", "receipts", "out-of-office", "layoff"):
        assert kind in noise, kind
    assert "if your application is a good fit" in noise


def test_a_freeze_holds_the_nudges_and_is_never_a_rejection():
    row = next(ln for ln in TABLE if ln.startswith("| Hiring freeze"))
    assert "DO NOT CHASE until" in row and "Never `rejected`" in row


def test_an_employer_asking_for_something_is_a_reply_owed():
    row = next(ln for ln in TABLE if ln.startswith("| Reply owed"))
    assert "availability" in row and "Replies to Send" in row
    assert "### Replies to Send" in TEXT.split("## Step 10", 1)[1]


def test_every_proposal_carries_its_evidence_into_the_table_and_the_record():
    assert "**Evidence for every proposal.**" in STEP5
    step6 = TEXT.split("## Step 6", 1)[1].split("## Step 7", 1)[0]
    assert "| Evidence |" in step6
    step7a = TEXT.split("### Step 7a", 1)[1]
    assert 'gmail-sync: <signal> ("<email subject>"): "<evidence>"' in step7a
    assert 'Evidence: "<the quoted sentence>". Source:' in step7a
