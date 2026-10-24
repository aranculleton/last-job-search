"""A message that needs no answer stops being a reply owed, until they write again.

"I'll get back to you next week" left the contact owed a reply, and setting them to
in conversation did not change it: the log said they wrote last, so the brief asked for an
answer every day (2026-10-24). `state.py no-reply` says why none is needed, dated, and
when to look again; their next message is owed like any other. Invented people.
"""
from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import state  # noqa: E402

CID = "ivo_marsh"


def _t(date, direction, text, scenario=""):
    return {"contact_id": CID, "date": date, "direction": direction, "channel": "message",
            "scenario": scenario, "summary": scenario or "logged", "full_text": text,
            "subject": ""}


def _book():
    contacts = [{"contact_id": CID, "name": "Ivo Marsh", "company": "Quayside Foods",
                 "status": "replied", "first_contacted": "2026-10-10"}]
    threads = [_t("2026-10-10", "out", "Hi Ivo, a first note.", "connection_note"),
               _t("2026-10-24", "in", "Thanks, I'll get back to you next week.")]
    return contacts, threads


def _kinds(contacts, threads, today):
    return [i["kind"] for i in state.owed(contacts, threads, today) if i["contact_id"] == CID]


def test_no_answer_owed_until_the_day_to_look_again():
    contacts, threads = _book()
    assert _kinds(contacts, threads, "2026-10-24") == ["reply"]
    row, said = state.no_reply(contacts, threads, CID, "they said they'll get back to you "
                               "next week", "2026-10-24", look_again="2026-11-03")
    assert row["next_action"].startswith("Nothing owed (2026-10-24). They said")
    assert row["next_action_due"] == "2026-11-03" and "2026-11-03" in said
    assert _kinds(contacts, threads, "2026-10-28") == []
    assert _kinds(contacts, threads, "2026-11-03") == ["reply"]          # the day to look again


def test_words_like_if_or_until_in_the_reason_still_mean_nothing_owed():
    contacts, threads = _book()
    state.no_reply(contacts, threads, CID, "nothing until they are back, if ever", "2026-10-24",
                   look_again="2026-11-03")
    assert _kinds(contacts, threads, "2026-10-28") == []


def test_their_next_message_is_owed_again():
    contacts, threads = _book()
    state.no_reply(contacts, threads, CID, "they will come back", "2026-10-24",
                   look_again="2026-11-03")
    threads.append(_t("2026-10-27", "in", "Hi again, could you send your resume?"))
    assert _kinds(contacts, threads, "2026-10-28") == ["reply"]


def test_the_default_day_is_the_persons_own_follow_up_rule():
    contacts, threads = _book()
    row, _ = state.no_reply(contacts, threads, CID, "they will come back", "2026-10-24")
    assert row["next_action_due"] == state.follow_up_on("2026-10-24").isoformat()


def test_only_where_they_wrote_last():
    contacts, threads = _book()
    threads.append(_t("2026-10-24", "out", "Great, speak then.", "reply"))
    with pytest.raises(ValueError, match="the last word on the thread is ours"):
        state.no_reply(contacts, threads, CID, "they will come back", "2026-10-24")


def test_the_command(tmp_path, capsys):
    contacts, threads = _book()
    cpath, tpath = str(tmp_path / "c.csv"), str(tmp_path / "t.csv")
    state.save_contacts(contacts, cpath)
    state.save_threads(threads, tpath)
    assert state.main(["no-reply", CID, "--why", "they'll get back to you next week",
                       "--look-again", "2026-11-03", "--contacts", cpath, "--threads", tpath,
                       "--today", "2026-10-24"]) == 0
    assert "no answer owed; looked at again on 2026-11-03" in capsys.readouterr().out
    assert state.load_contacts(cpath)[0]["next_action_due"] == "2026-11-03"
