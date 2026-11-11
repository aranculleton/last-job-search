"""A contact with no employer recorded is shown, never passed by in silence.

The 2026-11-10 audit (NW-6): a third of one person's contact book had no employer, and every
view grouped by employer skipped those rows without a word: someone owed a reply, with no
employer on their row, never reached the employer view at all. Now they are grouped under
"Employer not recorded", with a line saying the checks made per employer cannot count them
and how their employer gets filled. Every name here is invented.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tools" / "network")]

import open_actions  # noqa: E402

TODAY = "2026-11-10"


def test_someone_owed_a_reply_with_no_employer_is_in_the_employer_view():
    contacts = [{"contact_id": "halloway", "name": "Wren Halloway", "company": "",
                 "status": "replied_needs_response", "next_action": "Reply to her question"},
                {"contact_id": "okafor", "name": "Dayo Okafor", "company": "",
                 "status": "awaiting_reply"},
                {"contact_id": "lindqvist", "name": "Petra Lindqvist", "company": "Ashgrove Ledger",
                 "status": "awaiting_reply"}]
    threads = [{"contact_id": "halloway", "date": "2026-11-08", "direction": "in",
                "channel": "message", "scenario": "", "summary": "Asked a question",
                "full_text": "Which team are you looking at?"}]
    entries = open_actions.build(contacts, threads, [], TODAY)
    unknown = next(e for e in entries if e["key"] == open_actions.NO_EMPLOYER)
    assert {c["contact_id"] for c in unknown["contacts"]} == {"halloway", "okafor"}
    text = open_actions.render(entries, TODAY)
    assert "## Employer not recorded" in text and "Wren Halloway" in text
    assert "2 people here have no employer recorded" in text
