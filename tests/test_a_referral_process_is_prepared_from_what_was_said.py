"""A referral-only process, registered with its recruiter as the lead, is prepared from what
was actually said and decided, not from what a template assumes.

Feedback from a real repo on 3.7.0: the document drafted the person's reasons for leaving
from dates and employers, missed their stock answers (the employer's name sat inside the
heading) so a five-year answer arguing against consulting went unflagged at a consultancy,
said nothing about a referrer's first message logged with no text, told them to "tell them
it is booked" to the recruiter who booked it, left the referrer out, named nobody for the
screen, printed a phrase the person never uses and a move date they never give, quoted the
screen's format for the technical round, asked generic questions, and its folder had no
job_posting.md, which turned the person's own CI red.

Every person, employer and role here is invented; the candidate is the example person.
"""
from __future__ import annotations

import csv
import json
import os
import re
import shutil
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "network"))

import interview_pack as P  # noqa: E402
import outreach  # noqa: E402
import person  # noqa: E402
import schema  # noqa: E402
import state as S  # noqa: E402

TODAY = "2026-10-20"
FIRM, ROLE = "Calder & Rook Consulting", "Operations Analytics Consultant"
REFERRER = {"contact_id": "calder_rook_vance", "name": "Ivo Vance",
            "title": "Associate Partner, Operations Practice", "company": FIRM, "route": "alumni",
            "status": "awaiting_reply", "next_action": ""}
RECRUITER = {"contact_id": "calder_rook_marsh", "name": "Tamsin Marsh",
             "title": "Talent Acquisition Partner", "company": FIRM, "route": "referral",
             "referred_by": "calder_rook_vance", "status": "call_booked",
             "next_action": "Recruiter screen", "next_action_due": "2026-10-21"}
THREADS = [
    # The referrer's first InMail, logged as a summary: its words were never kept.
    {"contact_id": "calder_rook_vance", "date": "2026-09-10", "direction": "out",
     "channel": "inmail", "scenario": "alumni_first_note", "summary": "first note, alumni",
     "full_text": ""},
    # The recruiter booked the call: her last message is inbound.
    {"contact_id": "calder_rook_marsh", "date": "2026-10-13", "direction": "in",
     "channel": "email", "scenario": "reply", "summary": "booked the screen",
     "full_text": "Ivo passed on your details. Does the 21st at 10 work for a 30 minute call?"},
]
LEAVING = ('### "Why are you leaving Brindle & Hart Logistics?" / "Why are you looking?"\n'
           "> I want depth over a rotating client portfolio: one planning problem I own end "
           "to end.\n\nUse for: \"why now\"\nNot for: consulting\n")
FIVE_YEARS = ('### "Where do you see yourself in 5 years?"\n'
              "> Leading planning analytics at a product company rather than more consulting.\n")
NEVER = "I made the move"
LEARNED = {"entries": [{"date": "2026-10-01", "area": "interview", "status": "active",
                        "said": "asked how long I've been here, I say I've just arrived",
                        "rule": "say only \"I've just arrived\", never a date or a month",
                        "never_say": [NEVER]}]}
SEEN = {"seen": {
    "https://jobs.example/calder-rook/101": {"company": FIRM, "title": ROLE,
                                             "location": "Manchester", "status": "new"},
    "https://jobs.example/calder-rook-labs/7": {"company": "Calder & Rook Labs", "title": ROLE,
                                                "location": "Manchester", "status": "skipped",
                                                "skip_reason": "same-employer duplicate"}}}
MONTHS = re.compile(r"\b(?:January|February|March|April|May|June|July|August|September|October|"
                    r"November|December)\b")


def _write(path, rows, cols):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})


@pytest.fixture
def case(tmp_path, monkeypatch):
    prof = tmp_path / "profile"
    shutil.copytree(os.path.join(ROOT, "profile.example"), prof,
                    ignore=shutil.ignore_patterns("__pycache__", "state"))
    stock = prof / P.STORIES_FILE
    text = stock.read_text(encoding="utf-8")
    text = re.sub(r'### "Why are you looking\?"\n> [^\n]*\n', LEAVING, text)
    stock.write_text(text.rstrip() + "\n\n" + FIVE_YEARS, encoding="utf-8")
    (prof / "learned.json").write_text(json.dumps(LEARNED), encoding="utf-8")
    st = tmp_path / "state"
    (st / "job_scraper").mkdir(parents=True)
    (st / "job_scraper" / "seen_jobs.json").write_text(json.dumps(SEEN), encoding="utf-8")
    _write(st / "network_contacts.csv", [REFERRER, RECRUITER], schema.CONTACT_COLUMNS)
    _write(st / "network_threads.csv", THREADS, schema.THREAD_COLUMNS)
    monkeypatch.setenv(person.ENV, str(prof))
    monkeypatch.setenv(person.STATE_ENV, str(st))
    person.reset()
    who = {"identity.moved": "just arrived", "identity.area": "Ancoats, Manchester"}
    real = P._person
    monkeypatch.setattr(P, "_person", lambda dotted: who.get(dotted) or real(dotted))
    yield st
    monkeypatch.undo()
    person.reset()


def _process(*extra):
    # Registered with the recruiter as the lead, and nobody named for the screen.
    return P.main(["process", FIRM, "--contact", "calder_rook_marsh", "--role", ROLE,
                   "--stage", "Recruiter screen", "--date", "2026-10-21", "--today", TODAY,
                   *extra])


def _doc():
    with open(os.path.join(outreach.app_folder(FIRM, ROLE), P.LIVING), encoding="utf-8") as fh:
        return fh.read()


def _section(text, title):
    return text.split("## %s\n" % title, 1)[1].split("\n## ", 1)[0]


def _block(text, question):
    return _section(text, "Your answers").split("### %s\n" % question, 1)[1].split("\n### ")[0]


def test_every_process_folder_holds_a_posting_so_the_folder_check_stays_green(case):
    assert _process() == 0
    applications = case / "documents" / "applications"
    for name in os.listdir(applications):
        assert (applications / name / "job_posting.md").is_file(), name
    text = (applications / os.listdir(applications)[0] / "job_posting.md").read_text("utf-8")
    assert P.POSTING_NOT_HELD in text
    # The placeholder is never read as the posting.
    assert P.gather(FIRM, ROLE, today=TODAY)["posting"] == ""
    # A posting found later replaces it; one held is kept.
    posting = case / "posting.txt"
    posting.write_text("Operations Analytics Consultant. You will build demand models.",
                       encoding="utf-8")
    assert _process("--posting", str(posting)) == 0
    assert "build demand models" in P.gather(FIRM, ROLE, today=TODAY)["posting"]


def test_motivation_answers_are_asked_and_stock_answers_are_matched_and_flagged(case, capsys):
    _process()
    text = _doc()
    # The moves and "why this employer" are theirs: asked once, in one plain question.
    moves = _block(text, "Walk me through your career, and the moves between jobs.")
    assert P.ASK_MARK in moves and "What made you take each move (Saltmarsh Analytics, then " \
        "Oakmere Foods, then Brindle & Hart Logistics)?" in moves
    assert P.ASK_MARK in _block(text, "Why %s?" % FIRM)
    assert "facts only" not in text
    # The stock answer is found through the employer's name in its heading, and, being
    # marked Not for consulting, left out with the reason: never printed as the thing to say.
    leaving = _block(text, "Why are you leaving your current role?")
    assert "depth over a rotating client portfolio" not in leaving
    assert "left out for %s: its Not for: line names consulting employers" % FIRM in leaving
    assert "depth over a rotating client portfolio" not in _section(text, "Likely questions")
    # A five-year answer this stage does not ask is still flagged, on one screen.
    screen = _section(text, "On one screen")
    assert 'Not as it stands: your answer to "Where do you see yourself in 5 years?"' in screen
    assert '("rather than more consulting")' in screen
    capsys.readouterr()
    assert P.main(["check", FIRM]) == 1
    assert "- Ask: Walk me through your career, and the moves between jobs." in \
        capsys.readouterr().out
    # Their answer is kept for every later employer, and the next build uses it.
    assert P.main(["motive", "Walk me through your career, and the moves between jobs.",
                   "--answer", "Each move was for a bigger planning problem than the last one "
                   "gave me.", "--suits", "consulting,product"]) == 0
    kept = (person.path(P.STORIES_FILE))
    body = open(kept, encoding="utf-8").read()
    assert '### "Walk me through your career, and the moves between jobs."' in body
    assert "Suits: consulting, product" in body and "Use for: " in body
    P.main(["pack", FIRM, "--today", TODAY, "--write"])
    moves = _block(_doc(), "Walk me through your career, and the moves between jobs.")
    assert P.ASK_MARK not in moves and "bigger planning problem" in moves
    # A kind of employer the pack cannot tell apart is refused, never kept as a dead tag.
    assert P.main(["motive", "Why now?", "--answer", "x", "--suits", "agency"]) == 1


def test_what_was_read_and_what_was_not_logged_are_both_said(case):
    _process()
    told = _section(_doc(), "What they have been told")
    assert "- Read: Ivo Vance, Associate Partner, Operations Practice [awaiting_reply]: 1 " \
           "message(s) from you, 2026-09-10" in told
    assert "- Read: Tamsin Marsh, Talent Acquisition Partner [call_booked]: nothing from you " \
           "logged" in told
    assert "2026-09-10, to Ivo Vance: text not logged (logged as \"first note, alumni\"): check " \
           "what this said about where you are, notice and pay" in told
    assert "state.py text calder_rook_vance --date 2026-09-10" in told
    # The words, once added, are read: and what to say about them is never put in their mouth.
    msg = case / "msg.txt"
    msg.write_text("Hi Ivo, I'm moving to Manchester from Leeds next month.", encoding="utf-8")
    assert S.main(["text", "calder_rook_vance", "--date", "2026-09-10", "--text-file",
                   str(msg)]) == 0
    assert S.main(["text", "calder_rook_vance", "--date", "2026-09-10", "--text-file",
                   str(msg)]) == 1                      # already has its text
    P.main(["pack", FIRM, "--today", TODAY, "--write"])
    told = _section(_doc(), "What they have been told")
    assert "to Ivo Vance, on where you are" in told and "DIFFERS" in told
    assert "text not logged" not in told


def test_the_warm_route_and_the_interviewer_are_right(case):
    _process()
    text = _doc()
    assert "with Tamsin Marsh, Talent Acquisition Partner (assumed: the recruiter who leads " \
           "it)" in text.splitlines()[2]
    meeting = _section(text, "Who you are meeting")
    assert "- Assumed: Tamsin Marsh, Talent Acquisition Partner leads this process" in meeting
    assert "**Tamsin Marsh**" in meeting
    warm = _section(text, "Warm route")
    # Her stored status wins over the inbound message, and nothing is owed to her.
    assert "Tamsin Marsh" in warm and "[call_booked]" in warm
    assert "replied_needs_response" not in warm and "tell them it is booked" not in warm
    # The referrer, named only in her row's referred_by, is listed with the referrer's rule.
    assert "- Ivo Vance, Associate Partner, Operations Practice put you forward" in warm
    assert "no update until there is an outcome, unless they ask" in warm


def test_just_arrived_switches_the_small_talk_on_with_no_date(case):
    _process()
    text = _doc()
    talk = _section(text, "Small talk")
    assert "Ancoats, Manchester, and have just arrived" in talk
    assert "How are you finding Ancoats?" in _section(text, "Your answers")
    where = _block(text, "Where are you based?")
    assert "You have just arrived" in where
    for part in (talk, where):
        assert not MONTHS.search(part) and "few weeks" not in part


def test_no_phrase_on_the_never_say_list_is_in_the_document(case):
    msg = case / "msg.txt"
    msg.write_text("Hi Ivo, I'm moving to Manchester next month.", encoding="utf-8")
    S.main(["text", "calder_rook_vance", "--date", "2026-09-10", "--text-file", str(msg)])
    _process()
    text = _doc()
    assert NEVER.lower() not in text.lower().replace('"%s"' % NEVER.lower(), "")
    assert "wording you have said never to use" not in text


def test_the_format_told_for_one_round_is_not_quoted_for_another(case):
    _process()
    folder = outreach.app_folder(FIRM, ROLE)
    out = os.path.join(folder, "outcome.md")
    with open(out, "a", encoding="utf-8") as fh:
        fh.write("- 2026-10-13: Recruiter screen booked: virtual, 30 minutes.\n"
                 "- 2026-10-13: The technical interview is a 60 minute case with two partners.\n")
    screen = P.format_lines(P.gather(FIRM, ROLE, stage="Recruiter screen", today=TODAY))
    tech = P.format_lines(P.gather(FIRM, ROLE, stage="Technical interview", today=TODAY))
    assert any("virtual, 30 minutes" in ln for ln in screen)
    assert not any("virtual, 30 minutes" in ln for ln in tech)
    assert any("60 minute case" in ln for ln in tech)


def test_ask_them_starts_with_which_team_and_a_screen_asks_about_the_process(case):
    _process()
    ask = [ln for ln in _section(_doc(), "Ask them").splitlines() if ln.startswith("- ")]
    assert ask[0].startswith("- Which team is this recruiter screen for?")
    assert "Calder & Rook Labs" in ask[0]
    assert any("What are the stages from here" in ln for ln in ask)
    assert any("How much travel does the role involve" in ln for ln in ask)


@pytest.mark.parametrize("moved,today,said", [
    ("by 2026-09-16", "2026-10-20", "for a few weeks"),
    ("by 2026-05-02", "2026-10-20", "since May 2026"),
    ("2026-09", "2026-10-20", "for a few weeks"),
    ("none", "2026-10-20", ""),
    ("[CONFIRM: when did you move?]", "2026-10-20", ""),
])
def test_a_confirmed_by_date_switches_the_newcomer_lines_on(monkeypatch, moved, today, said):
    monkeypatch.setattr(P, "_person", lambda dotted: moved if dotted == "identity.moved" else "")
    monkeypatch.setattr(P, "_just_arrived_rule", lambda: False)
    assert P.newcomer({"today": today}) == said


@pytest.mark.parametrize("question,heading,hit", [
    ("Why are you leaving your current role?",
     '"Why are you leaving Brindle & Hart Logistics?" / "Why are you looking?"', True),
    ("Why are you looking?", '"Why are you leaving Brindle & Hart Logistics?"', True),
    ("Where do you see yourself in five years?", '"Where do you see yourself in 5 years?"', True),
    ("Why Fernhill Freight?", '"Why Calder & Rook Consulting?"', False),
    ("Tell me about yourself.", '"Why are you looking?"', False),
])
def test_a_stock_answer_is_matched_whatever_employer_its_heading_names(question, heading, hit):
    answer = {"question": heading.strip('"'), "answer": "x", "alternatives":
              re.findall(r'"([^"]+)"', heading), "use_for": [], "suits": (), "not_for": ()}
    names = ["Fernhill Freight", "Brindle & Hart Logistics", "Oakmere Foods"]
    got = P._answer_for(question, [answer], names, "Fernhill Freight")
    assert (got is not None) == hit


def test_use_for_tags_reach_a_stock_answer_and_one_that_fits_is_taken_first():
    fits = {"question": "Why now?", "answer": "a", "alternatives": ["Why now?"],
            "use_for": ["why are you leaving"], "suits": ("consulting",), "not_for": ()}
    not_here = dict(fits, answer="b", suits=(), not_for=("consulting",))
    got = P._answer_for("Why are you leaving your current role?", [not_here, fits], (), "X",
                        fits=lambda a: "consulting" not in a["not_for"])
    assert got is fits
