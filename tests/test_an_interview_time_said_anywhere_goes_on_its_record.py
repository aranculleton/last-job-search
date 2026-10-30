"""An interview's time, wherever it is said, goes on the interview's own record, and the page
shows it.

From a person's copy (2026-10-29): the recruiter's message gave the panel's day and time, the
chat kept it in the contact's note, and the interview's record (its outcome.md stage line) had
the day alone. To do said "time not set", and the chat told the person to add the time
themselves. The page reads an interview's `when` alone, so a time on record that the model sent
as a day alone read "time not set" too.

Here the time reaches the record from a message recorded with someone at that employer, from a
note written into the contact book, and from the chat's own command; each time the model's
`when` is the moment, which the page shows with its time. Every person and employer is
invented: the search is tests/app_state.py's, with the panel at Thornbury Bank booked for
2026-10-28 and no time, and the person in London (GMT that day).
"""
from __future__ import annotations

import csv
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import pytest  # noqa: E402

from company_key import key as company_key  # noqa: E402
from test_a_tick_on_the_page_is_applied_once import Search  # noqa: E402

INTERVIEW = "int-thornbury_bank_risk_analyst"
OUTCOME = ("documents", "applications", "thornbury_bank_risk_analyst_thornbury", "outcome.md")
JUNO = "thornbury_bank_castellan"


@pytest.fixture
def search(tmp_path):
    s = Search(str(tmp_path))
    path = os.path.join(s.state, "network_contacts.csv")
    with open(path, encoding="utf-8") as fh:
        head = next(csv.reader(fh))
    with open(path, "a", encoding="utf-8", newline="") as fh:
        csv.DictWriter(fh, fieldnames=head, extrasaction="ignore").writerow(dict.fromkeys(head, "") | {
            "contact_id": JUNO, "name": "Juno Castellan", "title": "Talent Partner",
            "company": "Thornbury Bank", "company_key": company_key("Thornbury Bank"),
            "tier": "2", "route": "hiring_team", "first_contacted": "2026-10-10",
            "channel": "email", "status": "in_conversation"})
    return s


def tool(search, *args):
    env = dict(os.environ, LJS_PROFILE=search.profile, LJS_STATE=search.state,
               LJS_COPY="private")
    env.pop("LJS_TODAY", None)
    r = subprocess.run([sys.executable, *args], env=env, capture_output=True, encoding="utf-8",
                       errors="replace", timeout=120, cwd=ROOT)
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout


def outcome(search):
    with open(os.path.join(search.state, *OUTCOME), encoding="utf-8") as fh:
        return fh.read()


def interview(search):
    return next(i for i in search.model()["interviews"] if i["id"] == INTERVIEW)


def test_a_message_giving_the_day_and_time_puts_the_time_on_the_interview(search, tmp_path):
    assert interview(search)["when"] == "2026-10-28", "booked with its day alone"
    said = tmp_path / "invite.txt"
    said.write_text("Hi Morgan, confirming your panel interview on Wednesday 28 October at "
                    "2.30pm. It runs for an hour. Best, Juno", encoding="utf-8")
    out = tool(search, "tools/network/state.py", "received", JUNO, "--text-file", str(said),
               "--date", "2026-10-25", "--channel", "email", "--today", "2026-10-25")
    assert "Saved on the interview: Panel interview with Thornbury Bank on 2026-10-28 at " \
           "14:30." in out, out
    assert "- [ ] Panel interview (scheduled 2026-10-28 14:30, with the head of risk)" \
        in outcome(search)
    i = interview(search)
    # The moment, which the page shows with its time; never a day alone, "time not set".
    assert (i["when"], i["time"], i["all_day"]) == ("2026-10-28T14:30:00Z", "14:30", False)


def test_a_note_in_the_contact_book_is_taken_and_the_newest_message_wins(search):
    # Written into the book by hand, with no tool: the next sweep (every wake of the chat
    # that answers the page runs it) takes it.
    path = os.path.join(search.state, "network_contacts.csv")
    with open(path, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
        head = list(rows[0])
    for r in rows:
        if r["contact_id"] == JUNO:
            r["notes"] = "2026-10-24: panel is 28 Oct at 10am, an hour, three people"
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=head)
        w.writeheader()
        w.writerows(rows)
    threads = os.path.join(search.state, "network_threads.csv")
    with open(threads, encoding="utf-8") as fh:
        thead = next(csv.reader(fh))
    with open(threads, "a", encoding="utf-8", newline="") as fh:
        csv.DictWriter(fh, fieldnames=thead, extrasaction="ignore").writerow(
            dict.fromkeys(thead, "") | {
                "contact_id": JUNO, "date": "2026-10-25", "direction": "in",
                "channel": "email", "summary": "moved the panel",
                "full_text": "Small change: the panel on 28 October is now at 11:15 GMT."})
    out = tool(search, "tools/interview_pack.py", "times", "--today", "2026-10-25")
    assert "Panel interview with Thornbury Bank on 2026-10-28 at 11:15 GMT" in out, out
    assert "(scheduled 2026-10-28 11:15 GMT, with the head of risk)" in outcome(search)
    assert interview(search)["when"] == "2026-10-28T11:15:00Z"
    # Once the time is on the record, nothing is taken twice.
    again = tool(search, "tools/interview_pack.py", "times", "--today", "2026-10-25")
    assert "Saved on the interview" not in again


def test_the_chat_saves_a_time_it_was_told_with_one_command(search):
    out = tool(search, "tools/interview_pack.py", "book", "Thornbury Bank", "--time", "9am",
               "--zone", "EST", "--today", "2026-10-25")
    assert "(scheduled 2026-10-28 09:00 EST, with the head of risk)" in out, out
    assert "(scheduled 2026-10-28 09:00 EST, with the head of risk)" in outcome(search)
    i = interview(search)
    # 09:00 in New York on 28 October 2026 (still summer time there) is 13:00 UTC.
    assert (i["when"], i["time"], i["zone"]) == ("2026-10-28T13:00:00Z", "09:00", "EST")


def _said(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return " ".join(fh.read().split())


def test_every_chat_is_told_to_save_the_time_itself_and_never_to_hand_it_back():
    # The chat told the person to add the time themselves: /interview wrote a booked stage
    # with its day alone, and no instruction said the chat fixes a record it knows better.
    core = _said("CLAUDE.md")
    assert "**Records are yours to fix.**" in core and "never them" in core
    interview, outcome, app = (_said(".claude/commands/interview.md"),
                               _said(".claude/commands/outcome.md"),
                               _said(".claude/skills/app/SKILL.md"))
    for text in (interview, outcome, app):
        assert "interview_pack.py book" in text and "--time" in text
    assert "(scheduled YYYY-MM-DD HH:MM, with <title or name>)" in interview
    assert "(scheduled YYYY-MM-DD HH:MM, with <title or name>)" in outcome
    assert "interview_pack.py times" in interview and "interview_pack.py times" in outcome
    assert "never tell the person to add a time, or fix any record, themselves" in app
