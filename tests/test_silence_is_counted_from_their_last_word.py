"""Silence is counted from the employer's last word, not from the application.

`followups.review()` put the quiet day at the application date plus SILENCE_DAYS, and
`close_quiet` then closed the row as `no_response` whatever the notes recorded since: a
recruiter writing on day 40 to ask for availability left the row to close as "no reply in
45 days" five days later. The nudge timing in CLAUDE.md is unchanged (seven days after
applying, seven after the first actually went, at most two); what moves is where the
silence starts, and a nudge drafted after their word no longer asks whether the
application reached anyone.
"""
from __future__ import annotations

import datetime
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "network"))

import followups as F  # noqa: E402

D = datetime.date
ASKED = '2026-09-10 gmail-sync: Reply owed ("Your application"): "Could you share your availability?"'


def _row(notes=""):
    return {"company": "Larkspur Retail", "role": "Planning Analyst", "date": "2026-08-01",
            "status": "applied", "contact_person": "Wren Halloway", "notes": notes}


def test_a_word_from_them_moves_the_quiet_day():
    plain = F.review([_row()], D(2026, 9, 16))[0]
    assert plain["state"] == "quiet" and plain["quiet_on"] == "2026-09-15"
    it = F.review([_row(ASKED)], D(2026, 9, 16))[0]
    assert it["state"] == "due" and it["heard"] == "2026-09-10"
    assert it["quiet_on"] == "2026-10-25"


def test_an_acknowledgement_is_not_a_word():
    for note in ('2026-08-02 gmail-sync: Application ack ("Thanks for applying")',
                 "2026-08-02: automated reply, received your application"):
        assert F.review([_row(note)], D(2026, 9, 16))[0]["state"] == "quiet", note


def test_the_nudge_dates_are_the_ones_claude_md_states():
    # Seven days after applying, whatever they said: the rule is unchanged.
    it = F.review([_row("2026-08-03: recruiter emailed, reviewing this week")], D(2026, 8, 8))[0]
    assert (it["state"], it["nudge"], it["due_on"]) == ("due", 1, "2026-08-08")


def test_a_nudge_after_their_word_says_so():
    it = F.review([_row(ASKED)], D(2026, 9, 14))[0]
    assert it["message"].startswith("Hi Wren, thank you for your note on 2026-09-10.")
    assert "reached the right person" not in it["message"]


def test_a_reply_after_the_second_nudge_is_not_two_nudges_met_with_silence():
    notes = "followed up 2026-08-08 | followed up 2026-08-15 | 2026-08-20: recruiter replied, " \
            "shortlist next month"
    it = F.review([_row(notes)], D(2026, 8, 30))[0]
    assert it["state"] != "quiet" and it["quiet_on"] == "2026-10-04"
    silent = F.review([_row("followed up 2026-08-08 | followed up 2026-08-15")], D(2026, 8, 30))[0]
    assert silent["state"] == "quiet"


def test_the_close_says_how_long_since_they_last_wrote(tmp_path):
    path = tmp_path / "job_search_tracker.csv"
    path.write_text("company,role,date,status,notes,cv_file\n"
                    'Larkspur Retail,Planning Analyst,2026-08-01,applied,"%s",\n'
                    % ASKED.replace('"', '""'), encoding="utf-8")
    assert F.close_quiet(str(path), today=D(2026, 10, 20), holds={}) == []
    closed = F.close_quiet(str(path), today=D(2026, 10, 26), holds={})
    assert len(closed) == 1
    assert "no word since they last wrote, 2026-09-10" in F._rows(str(path))[0]["notes"]
