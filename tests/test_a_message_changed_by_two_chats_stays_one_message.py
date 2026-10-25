"""A message two chats changed at once merges into one message, never two.

The message log was merged with the whole row as its key, so one chat naming the file that
went with a message and another adding its words were two new rows and a removed one: the
merge kept both copies, said nothing, and the copy counted as a second message sent, which
spent the one nudge. Every name and message here is invented.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tools" / "network")]

import csv_store  # noqa: E402
import merge_state  # noqa: E402
import state  # noqa: E402

LOG = "contact_id,date,direction,channel,scenario,summary,full_text\n"
FIRST = "acme_halloway,2026-10-01,out,message,first_message,First message sent,\n"
OTHER = "brindle_rook,2026-10-01,out,message,first_message,First message sent,Hi Ana\n"


def _merge(base, ours, theirs, tmp_path):
    text, problems = merge_state.merge(LOG + base, LOG + ours, LOG + theirs,
                                       "network_threads.csv")
    p = tmp_path / "network_threads.csv"
    p.write_text(text, encoding="utf-8")
    return csv_store.read_rows(str(p)), problems


def test_a_file_named_on_one_side_and_words_added_on_the_other_is_one_message(tmp_path):
    ours = ("acme_halloway,2026-10-01,out,message,send_resume,First message sent; "
            "attached Acme_Resume.pdf,\n" + OTHER)
    theirs = ("acme_halloway,2026-10-01,out,message,first_message,First message sent,Hi Wren\n"
              + OTHER)
    rows, problems = _merge(FIRST + OTHER, ours, theirs, tmp_path)
    assert problems == []
    mine = [r for r in rows if r["contact_id"] == "acme_halloway"]
    assert len(mine) == 1 and len(rows) == 2
    assert mine[0]["scenario"] == "send_resume" and "Acme_Resume.pdf" in mine[0]["summary"]
    assert mine[0]["full_text"] == "Hi Wren"
    due = state.follow_up_due({"contact_id": "acme_halloway"}, mine)
    assert due[2] == 0 and due[1] is not None          # no nudge counted, one still due


def test_two_messages_each_side_added_on_one_day_are_both_kept(tmp_path):
    ours = FIRST + "acme_halloway,2026-10-03,in,message,,They replied,Happy to chat\n"
    theirs = FIRST + "acme_halloway,2026-10-03,in,message,,They replied,Thursday works too\n"
    rows, problems = _merge(FIRST, ours, theirs, tmp_path)
    assert problems == [] and len(rows) == 3


def test_the_same_words_changed_two_ways_is_a_conflict_for_a_person(tmp_path):
    ours = "acme_halloway,2026-10-01,out,message,first_message,First message sent,Hi Wren\n"
    theirs = ("acme_halloway,2026-10-01,out,message,first_message,First message sent,"
              "Hello Wren\n")
    text, problems = merge_state.merge(LOG + FIRST, LOG + ours, LOG + theirs,
                                       "network_threads.csv")
    assert problems and "full_text" in problems[0]
    assert "<<<<<<< ours" in text
