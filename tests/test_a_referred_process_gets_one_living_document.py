"""A referral-only process with a booked recruiter screen and no tracker row gets, from one
command, one living document.

A senior insider referred the candidate, a recruiter booked a screen, and nobody applied
through the portal (a second, worse record of the same person). /interview refused it, so
the session hand-wrote everything: answers in four places, the recruiter's questions missing,
and a referrer who had been told "moving" weeks before the profile said "moved". This pins
the whole path, from the contact book to a document that is kept, rebuilt and checked.

Every person, employer and role here is invented; the candidate is the example person.
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "network"))

import interview_pack as P  # noqa: E402
import open_actions  # noqa: E402
import outreach  # noqa: E402
import schema  # noqa: E402

TODAY = "2026-10-19"
FIRM, ROLE = "Calder & Rook Consulting", "Operations Analytics Consultant"
CONTACTS = [
    {"contact_id": "calder_rook_vance", "name": "Ivo Vance",
     "title": "Associate Partner, Operations Practice", "company": FIRM, "route": "alumni",
     "route_detail": "we were both at Oakmere Foods", "status": "referral_in_progress",
     "next_action": "Tell him the screen is booked", "outcome": "referred 2026-10-08"},
    {"contact_id": "calder_rook_marsh", "name": "Tamsin Marsh",
     "title": "Talent Acquisition Partner", "company": FIRM, "route": "referral",
     "referred_by": "calder_rook_vance", "status": "call_booked",
     "next_action": "Recruiter screen", "next_action_due": "2026-10-21"},
]
THREADS = [
    {"contact_id": "calder_rook_vance", "date": "2026-09-10", "direction": "out",
     "channel": "linkedin", "scenario": "alumni_first_note", "summary": "first note",
     "full_text": "Hi Ivo, we were both at Oakmere Foods. I'm currently at Brindle & Hart and "
                  "moving to Manchester from Leeds next month. Would you have 15 minutes?"},
    {"contact_id": "calder_rook_marsh", "date": "2026-10-13", "direction": "out",
     "channel": "email", "scenario": "reply", "summary": "confirmed",
     "full_text": "Thanks Tamsin, the 21st at 10 works well. I'm based in Manchester."},
]
RESEARCH = {"company": FIRM, "fetched_date": "2026-10-18",
            "facts": [{"claim": "Calder & Rook runs an operations practice for retailers.",
                       "source_url": "https://calder-rook.example/operations"}]}
PERSON = {"identity.moved": "2026-05", "identity.area": "Ancoats, Manchester"}
SPOKEN = ("I'm an operations analyst, and for seven years I've turned warehouse and transport "
          "data into forecasts people actually order from. Most recently I cut forecast error "
          "from 22% to 14%, and I'd like to do that kind of work across many clients.")


def _write(path, rows, cols):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setenv("LJS_STATE", str(tmp_path))
    _write(tmp_path / "network_contacts.csv", CONTACTS, schema.CONTACT_COLUMNS)
    _write(tmp_path / "network_threads.csv", THREADS, schema.THREAD_COLUMNS)
    real = P._person
    monkeypatch.setattr(P, "_person", lambda dotted: PERSON.get(dotted) or real(dotted))
    return tmp_path


def _process(*extra):
    return P.main(["process", FIRM, "--contact", "calder_rook_vance", "--role", ROLE,
                   "--stage", "Recruiter screen", "--date", "2026-10-21",
                   "--with", "Tamsin Marsh, Talent Acquisition Partner", "--today", TODAY,
                   *extra])


def _doc():
    with open(os.path.join(outreach.app_folder(FIRM, ROLE), P.LIVING), encoding="utf-8") as fh:
        return fh.read()


def _section(text, title):
    body = text.split("## %s\n" % title, 1)[1]
    return "\n".join(body.split("\n## ", 1)[0].splitlines())


def _tracker(state):
    with open(state / "job_search_tracker.csv", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def test_with_no_application_it_names_the_one_command(state):
    with pytest.raises(LookupError) as exc:
        P.gather(FIRM, today=TODAY)
    assert "interview_pack.py process" in str(exc.value)
    assert "calder_rook_vance" in str(exc.value)


def test_one_command_registers_the_process_and_writes_the_document(state, capsys):
    assert _process() == 0
    out = capsys.readouterr().out
    rows = _tracker(state)
    assert len(rows) == 1
    row = rows[0]
    assert row["status"] == "interview" and row["channel"] == "referral"
    assert row["source"] == "contact:calder_rook_vance" and P.PROCESS_NOTE in row["notes"]
    assert not row["cv_file"] and not row["cover_letter_file"]
    folder = outreach.app_folder(FIRM, ROLE)
    outcome = open(os.path.join(folder, "outcome.md"), encoding="utf-8").read()
    assert "- [ ] Recruiter screen (scheduled 2026-10-21, with Tamsin Marsh" in outcome
    assert "written: " in out and os.path.exists(os.path.join(folder, P.LIVING))
    # Offered once, optionally.
    assert out.count("Want a separate chat just for %s?" % FIRM) == 1
    # Run again, it changes nothing in the tracker.
    assert _process() == 0
    assert "already registered" in capsys.readouterr().out
    assert len(_tracker(state)) == 1


def test_the_document_holds_what_the_acceptance_asks_for(state):
    _process()
    text = _doc()
    # The call at a glance.
    assert text.startswith("# Interview prep: %s at %s\n\nLast updated %s. Next: Recruiter "
                           "screen, 2026-10-21, with Tamsin Marsh" % (ROLE, FIRM, TODAY))
    screen = _section(text, "On one screen")
    assert "**What they are assessing:**" in screen and "**What they want to hear:**" in screen
    # What this employer's people have been told, conflicts flagged.
    told = _section(text, "What they have been told")
    assert "to Ivo Vance, on where you are" in told and "DIFFERS" in told
    assert "CHECK: your profile's current employer" not in told    # "Brindle & Hart" is it
    # Every likely screen question, to be answered aloud, with what it is checking.
    answers = _section(text, "Your answers")
    for q in ("Tell me about yourself.", "Why are you leaving your current role?",
              "Where are you based?", "How do you know Ivo Vance?",
              "Are you willing to travel?", "Are you interviewing anywhere else?",
              "What is your notice period, and when could you start?"):
        assert "### " + q in answers
    assert answers.count(P.INTENT_MARK) == answers.count("### ")
    assert P.TO_WRITE in answers
    # Honest newcomer small talk, with no invented memories.
    where = _section(text, "Small talk")
    assert "Ancoats, Manchester" in where and "Never say you have done" in where
    # The person's questions, and a close.
    ask = _section(text, "Ask them")
    assert ask.strip().splitlines()[-1].startswith("- Is there anything about my background")
    # A process has no letter, and nothing tells the person to read one.
    assert "read the letter" not in text and "Nothing went in through a portal" in text
    # The recruiter: asked about the process, never researched for their own posts.
    meeting = _section(text, "Who you are meeting")
    assert "Tamsin Marsh" in meeting and "Wants to hear:" in meeting
    assert "Nothing about their own posts" in meeting
    assert "RESEARCH FIRST (Claude, not you): Tamsin Marsh" not in meeting
    # The referral: how it started changes what to say.
    assert "Through Ivo Vance's referral" in _section(text, "The format")
    assert "—" not in text


def test_rebuilt_in_place_it_keeps_what_the_person_wrote(state):
    _process()
    path = os.path.join(outreach.app_folder(FIRM, ROLE), P.LIVING)
    text = _doc()
    text = text.replace("### Tell me about yourself.\n", "### Tell me about yourself.\n" + SPOKEN
                        + "\n", 1)
    text = text.replace("## Notes\n\n" + P.NOTES_EMPTY, "## Notes\n\n- Tamsin prefers a call "
                        "to email.")
    text = text.replace("### What you found out\n\n" + P.FOUND_EMPTY, "### What you found "
                        "out\n\n- The tram stop is two minutes away (source: my own walk).")
    open(path, "w", encoding="utf-8").write(text)
    assert P.main(["pack", FIRM, "--today", "2026-10-20", "--write"]) == 0
    again = _doc()
    assert "Last updated 2026-10-20." in again
    block = again.split("### Tell me about yourself.\n", 1)[1].split("\n### ", 1)[0]
    assert SPOKEN in block
    # Their words replace the generated lines; nothing generated is kept as theirs.
    assert P.TO_WRITE not in block and "- From:" not in block
    assert again.count(SPOKEN) == 1
    assert "- Tamsin prefers a call to email." in _section(again, "Notes")
    assert "tram stop" in _section(again, "Small talk")
    # A question nobody has written yet is built afresh, once.
    leaving = again.split("### Why are you leaving your current role?\n", 1)[1].split("\n### ")[0]
    assert leaving.count(P.TO_WRITE) == 1 and leaving.count(P.INTENT_MARK) == 1


def test_check_holds_it_until_the_answers_are_said_and_the_research_is_done(state, capsys):
    _process()
    capsys.readouterr()
    assert P.main(["check", FIRM]) == 1
    out = capsys.readouterr().out
    assert "not written yet" in out and "research still to do" in out
    # Research arrives (Claude's job), and the first five answers are written as said.
    os.makedirs(state / "company_research", exist_ok=True)
    (state / "company_research" / "calder-rook-consulting.json").write_text(
        json.dumps(RESEARCH), encoding="utf-8")
    P.main(["pack", FIRM, "--today", TODAY, "--write"])
    path = os.path.join(outreach.app_folder(FIRM, ROLE), P.LIVING)
    text = _doc()
    questions = re.findall(r"^### (.+)$", _section(text, "Your answers"), re.M)[:P.ONE_SCREEN_QUESTIONS]
    for q in questions:
        text = text.replace("### %s\n" % q, "### %s\n%s\n" % (q, SPOKEN), 1)
    open(path, "w", encoding="utf-8").write(text)
    capsys.readouterr()
    assert P.main(["check", FIRM]) == 0, capsys.readouterr().out
    # Resume prose in their place is refused.
    bad = text.replace(SPOKEN, "Operations analyst with seven years turning data into "
                                "forecasts. Cut forecast error from 22% to 14%.", 1)
    open(path, "w", encoding="utf-8").write(bad)
    assert P.main(["check", FIRM]) == 1


def test_the_answer_to_the_campaign_offer_is_kept_and_the_search_leaves_it_alone(state, capsys):
    _process()
    capsys.readouterr()
    assert P.main(["campaign", FIRM, "--yes", "Job search: Calder & Rook campaign"]) == 0
    P.main(["pack", FIRM, "--today", TODAY, "--write"])
    assert "Want a separate chat" not in capsys.readouterr().out
    held = open_actions.campaigns(_tracker(state))
    assert any("Calder" in str(k) or "calder" in str(k) for k in held)


@pytest.mark.parametrize("stage,want", [
    ("First round: case + PEI", {"case", "behavioural"}),
    ("Coding pairing session", {"coding"}),
    ("Take-home presentation", {"presentation"}),
    ("Technical interview (SQL)", {"technical"}),
    ("Values interview", {"behavioural"}),
    ("Recruiter screen", {"screen"}),
])
def test_the_format_is_read_from_the_stage(stage, want):
    ctx = {"stage": stage, "format": "", "step": "technical", "role": "Analyst", "row": {},
           "company": "Fernhill Freight", "research": {}}
    got, assumed = P.interview_formats(ctx)
    assert set(got) == want and not assumed


def test_an_unnamed_round_at_a_consultancy_is_assumed_and_said_to_be():
    ctx = {"stage": "Second round", "format": "", "step": "technical", "role": ROLE,
           "row": {}, "company": FIRM, "research": {}}
    got, assumed = P.interview_formats(ctx)
    assert got == ["case", "behavioural"] and "consulting" in assumed


@pytest.mark.parametrize("question,checking", [
    ("Why are you leaving your current role?", "running from something"),
    ("Walk me through your career, and the moves between jobs.", "leave them soon"),
    ("Walk me through a project in sixty seconds.", "did the work yourself"),
    ("Why %s?" % FIRM, "chose them"),
    ("What are your salary expectations?", "budget"),
    ("Is there anything about my background you'd like me to go into more?", "doubt"),
])
def test_every_common_question_says_what_it_is_checking(question, checking):
    got, hear = P.intent(question)
    assert checking in got and hear


@pytest.mark.parametrize("title,kind", [
    ("Talent Acquisition Partner", "screener"), ("Associate Partner", "senior"),
    ("Engagement Manager", "manager"), ("Senior Data Scientist", "practitioner"),
    ("VP Engineering", "senior"), ("HR Business Partner", "screener"),
])
def test_each_interviewer_is_read_by_their_title(title, kind):
    assert P._kind(title) == kind
