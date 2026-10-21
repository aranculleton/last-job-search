"""A resume a contact asked for, made in one chat and sent from another, is one record.

From a real repo: a networking chat messaged someone, they asked for the CV, and the
person went to a separate chat to make it. Both chats logged something, at the same time,
and nothing joined them: the reply classifier said "Email the resume today" without
saying which, the message log said "Resume sent as asked" with no file, and the tracker
row the drafting chat wrote named nobody. Now the file that went is named on the message
(`state.py message --attached`), a resume drafted for a contact carries them from staging
to the tracker and its folder (`stage_picks.py --for-contact`), the guidance names both
routes, RECONCILE says where the two still disagree, and the due list says who is owed a
resume. Every person, employer and message here is invented; the candidate is the example
person, whose word for the document is "CV".
"""
from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tools" / "network")]

import docpaths  # noqa: E402
import open_actions  # noqa: E402
import outreach  # noqa: E402
import record_drafts  # noqa: E402
import reply  # noqa: E402
import schema  # noqa: E402
import stage_picks  # noqa: E402
import state  # noqa: E402

TODAY = "2026-10-21"
CID = "oakmere_foods_varga"
CV = "cv/Morgan_Ellis_CV_Oakmere.pdf"
ASK = "Thanks Morgan, good to hear from you. Send me your CV and I'll pass it on to the planning lead."
NOTE = ("Hi Quillon, hope you're well. We were both at Leeds. I work in supply-chain analytics "
        "in Manchester. How is the planning team set up at Oakmere?")
EMAIL = "Hi Quillon, thanks for offering to pass it on. My CV is attached. Best, Morgan"
POSTING = ("Demand Planning Analyst. A permanent role in our Manchester team, hybrid. You will "
           "own the weekly forecast in SQL and Python and work with the planning lead.")

CONTACTS = [
    {"contact_id": CID, "name": "Quillon Varga", "title": "Senior Planner",
     "company": "Oakmere Foods", "route": "alumni_school", "status": "in_conversation",
     "first_contacted": "2026-10-01", "channel": "message", "next_action": "", "notes": ""},
    {"contact_id": "kestrel_mutual_ansgar", "name": "Pell Ansgar", "title": "Talent Partner",
     "company": "Kestrel Mutual", "route": "cold", "status": "awaiting_reply",
     "first_contacted": "2026-10-02", "channel": "message"},
    {"contact_id": "fernhill_freight_venn", "name": "Bo Venn", "title": "Planning Manager",
     "company": "Fernhill Freight", "route": "cold", "status": "awaiting_reply",
     "first_contacted": "2026-10-03", "channel": "message"},
]
THREADS = [
    {"contact_id": CID, "date": "2026-10-01", "direction": "out", "channel": "message",
     "scenario": "first_message", "summary": "First message sent", "full_text": NOTE},
    {"contact_id": CID, "date": "2026-10-14", "direction": "in", "channel": "message",
     "scenario": "", "summary": "replied", "full_text": ASK},
    {"contact_id": "kestrel_mutual_ansgar", "date": "2026-10-02", "direction": "out",
     "channel": "message", "scenario": "first_message", "summary": "First message sent",
     "full_text": "Hi Pell, a quick question about the analytics team at Kestrel."},
    {"contact_id": "fernhill_freight_venn", "date": "2026-10-03", "direction": "out",
     "channel": "message", "scenario": "first_message", "summary": "First message sent",
     "full_text": "Hi Bo, a quick question about the planning team at Fernhill."},
]


def _write(path, rows, columns):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=columns, lineterminator="\n")
        w.writeheader()
        w.writerows({c: r.get(c, "") for c in columns} for r in rows)


def _repo(root, contacts=CONTACTS, threads=THREADS, tracker=(), files=(CV,)):
    """A person's state at `root`: the contact book, the message log, the tracker, and the
    documents named in `files`."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    _write(root / "network_contacts.csv", contacts, schema.CONTACT_COLUMNS)
    _write(root / "network_threads.csv", threads, schema.THREAD_COLUMNS)
    _write(root / "job_search_tracker.csv", list(tracker), record_drafts.HEADER)
    for f in files:
        (root / f).parent.mkdir(parents=True, exist_ok=True)
        (root / f).write_bytes(b"%PDF-1.4 an invented CV\n")
    return root


@pytest.fixture
def repo(tmp_path, monkeypatch):
    root = _repo(tmp_path / "repo")
    monkeypatch.setenv("LJS_STATE", str(root))
    return root


def _args(root):
    return ["--contacts", str(root / "network_contacts.csv"),
            "--threads", str(root / "network_threads.csv"), "--today", TODAY]


def _email(root, text=EMAIL):
    """The message as sent, kept beside the repo, never in it."""
    words = Path(str(root) + "_words")
    words.mkdir(exist_ok=True)
    f = words / ("message_%d.txt" % len(list(words.iterdir())))
    f.write_text(text, encoding="utf-8")
    return str(f)


def _load(root):
    return (state.load_contacts(str(root / "network_contacts.csv")),
            state.load_threads(str(root / "network_threads.csv")),
            state.load_tracker(str(root / "job_search_tracker.csv")))


def _reasons(root):
    contacts, threads, tracker = _load(root)
    return {(p["contact_id"], p["reason"]): p["detail"]
            for p in state.reconcile(contacts, threads, tracker)
            if p["reason"].startswith("resume_")}


def _made_row(status="drafted", role="Demand Planning Analyst", date="2026-10-15"):
    return {"date": date, "company": "Oakmere Foods", "role": role, "channel": "contact",
            "status": status, "contact_person": "Quillon Varga", "fit_rating": "74",
            "notes": f"Made for Quillon Varga ({CID}), who asked for it: it goes to them, not "
                     "through the portal.",
            "cv_file": "cv/Morgan_Ellis_CV_Oakmere.tex",
            "cover_letter_file": "cover_letters/Morgan_Ellis_Cover_Letter_Oakmere.tex",
            "source": "https://jobs.example/oakmere/7"}


# ------------------------------------------------------------------ 1. logging the file

def test_the_message_that_carried_a_resume_names_the_file(repo, capsys):
    assert state.main(["message", CID, "--text-file", _email(repo), "--attached", CV,
                       "--channel", "email", *_args(repo)]) == 0
    contacts, threads, _ = _load(repo)
    row = threads[-1]
    assert "a resume attached (cv/Morgan_Ellis_CV_Oakmere.pdf)" in row["summary"]
    assert state.attached(row) == [CV] and state.says_resume_went(row)
    assert row["scenario"] == "send_resume" and row["full_text"] == EMAIL
    # The row stops asking for it, and nothing is owed any more.
    quillon = next(c for c in contacts if c["contact_id"] == CID)
    assert quillon["next_action"].startswith("CV sent 2026-10-21 (" + CV)
    assert state.resumes_owed(contacts, threads) == []
    assert _reasons(repo) == {}


def test_the_file_must_be_one_every_chat_can_find(repo, tmp_path, capsys):
    before = (repo / "network_threads.csv").read_text(encoding="utf-8")
    outside = tmp_path / "Downloads" / "Morgan_Ellis_CV.pdf"
    outside.parent.mkdir()
    outside.write_bytes(b"%PDF")
    for bad, said in (("cv/Nobody_CV.pdf", "no file cv/Nobody_CV.pdf"),
                      (str(outside), "outside this repo")):
        assert state.main(["message", CID, "--text-file", _email(repo), "--attached", bad,
                           *_args(repo)]) == 1
        assert said in capsys.readouterr().out
    assert (repo / "network_threads.csv").read_text(encoding="utf-8") == before
    # An absolute path inside the repo is kept as the repo's own path.
    assert state.resolve_attachment(str(repo / CV)) == CV
    # One a kept application names, whose PDF this copy does not hold yet.
    folder = repo / "documents" / "applications" / "fernhill_freight_analyst_fernhill"
    folder.mkdir(parents=True)
    (folder / "draft.json").write_text(json.dumps([{"abbr": "Fernhill"}]), encoding="utf-8")
    assert state.resolve_attachment("cv/Morgan_Ellis_CV_Fernhill.pdf") == \
        "cv/Morgan_Ellis_CV_Fernhill.pdf"
    # One with the name the app gives this person's resume: a drafting chat at the same
    # time made it, and it arrives with the merge.
    assert state.resolve_attachment("cv/Morgan_Ellis_CV_Kestrel.pdf") == \
        "cv/Morgan_Ellis_CV_Kestrel.pdf"
    # A letter is an attachment, never a resume.
    assert state.attachment_note("cover_letters/Morgan_Ellis_Cover_Letter_Oakmere.pdf") == \
        "an attachment attached (cover_letters/Morgan_Ellis_Cover_Letter_Oakmere.pdf)"


def test_a_first_message_and_a_nudge_take_the_file_too(repo):
    (repo / "documents" / "cv").mkdir(parents=True)
    (repo / "documents" / "cv" / "Morgan_Ellis_CV_current.pdf").write_bytes(b"%PDF")
    general = "documents/cv/Morgan_Ellis_CV_current.pdf"
    contacts = CONTACTS + [{"contact_id": "quayside_foods_orrin", "name": "Tamsin Orrin",
                            "company": "Quayside Foods", "status": "not_contacted"}]
    _repo(repo, contacts=contacts)
    assert state.main(["sent", "quayside_foods_orrin", "--channel", "email", "--text-file",
                       _email(repo, "Hi Tamsin, my CV is attached in case a planning role opens."),
                       "--attached", general, *_args(repo)]) == 0
    assert state.main(["nudge", "kestrel_mutual_ansgar", "--text-file",
                       _email(repo, "Hi Pell, I have attached my CV in case it helps."),
                       "--attached", general, *_args(repo)]) == 0
    _, threads, _ = _load(repo)
    first, nudge = [r for r in threads if r["date"] == TODAY]
    assert state.attached(first) == [general] and first["scenario"] == "first_message"
    assert state.attached(nudge) == [general] and nudge["scenario"] == "nudge"


# ------------------------------------------------------------------ 2. drafting for a contact

def _pick():
    return {"company": "Oakmere Foods", "title": "Demand Planning Analyst", "portal": "pasted",
            "url": "https://jobs.example/oakmere/7", "location": "Manchester", "desc": POSTING,
            "fit": 74}


def test_a_resume_drafted_for_a_contact_is_filed_under_them(repo):
    staged = stage_picks.stage(str(repo / "r1"), ["1"], rows=[], root=str(repo),
                               shortlist=[_pick()], for_contact=CID, today=TODAY)
    assert staged[0]["for_contact"] == CID and staged[0]["for_contact_name"] == "Quillon Varga"
    apps_in = json.loads((repo / "r1" / "apps_in.json").read_text(encoding="utf-8"))
    assert apps_in[0]["for_contact"] == CID
    picks = json.loads((repo / "r1" / "picks.json").read_text(encoding="utf-8"))
    assert picks[0]["for_contact"] == CID
    assert f"- for contact: Quillon Varga ({CID})" in Path(picks[0]["file"]).read_text("utf-8")
    # The tracker row: who it goes to, by which route, and the words RECONCILE reads.
    meta = dict(apps_in[0])
    draft = {"company": "Oakmere Foods", "role": "Demand Planning Analyst",
             "abbr": meta["abbr"], "for_contact": CID}
    [(action, row)] = record_drafts.record([draft], {meta["abbr"].upper(): meta}, TODAY,
                                           path=str(repo / "job_search_tracker.csv"))
    assert action == "added" and row["contact_person"] == "Quillon Varga"
    assert row["channel"] == "contact" and row["source"] == "https://jobs.example/oakmere/7"
    assert f"Made for Quillon Varga ({CID})" in row["notes"]
    contacts, _, tracker = _load(repo)
    assert state.made_for(tracker[0], contacts)["contact_id"] == CID
    # The folder: the thread heads outreach.md, and no cold note is written.
    a = dict(draft, posting=POSTING, p1="x.", p2="y.", lead="", cl_bullets=[], p4="",
             summary="", tools="")
    d = Path(outreach.write(a, meta, TODAY))
    md = (d / "outreach.md").read_text(encoding="utf-8")
    assert "## This goes to Quillon Varga, who asked for it" in md
    assert "They asked on 2026-10-14" in md and "pass it on to the planning lead" in md
    assert f"state.py message {CID} --attached cv/Morgan_Ellis_CV_" in md
    assert "I've just applied" not in md and "hiring manager or the recruiter" not in md
    assert json.loads((d / "draft.json").read_text(encoding="utf-8"))[0]["for_contact"] == CID


def test_single_takes_the_contact_on_its_command_line(repo, monkeypatch, capsys):
    posting = repo / "posting.txt"
    posting.write_text(POSTING, encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["stage_picks.py", "single", str(repo / "apply"),
                                      "--company", "Oakmere Foods", "--role",
                                      "Demand Planning Analyst", "--posting-file", str(posting),
                                      "--for-contact", CID])
    assert stage_picks.main() == 0
    assert f"for Quillon Varga ({CID}), who asked for it" in capsys.readouterr().out
    picks = json.loads((repo / "apply" / "picks.json").read_text(encoding="utf-8"))
    assert picks[0]["for_contact"] == CID


def test_a_referral_through_the_same_contact_does_not_hold_the_draft(repo, monkeypatch):
    referring = [dict(CONTACTS[0], status="referral_in_progress")] + CONTACTS[1:]
    answered = THREADS + [{"contact_id": CID, "date": "2026-10-15", "direction": "out",
                           "channel": "message", "scenario": "reply", "summary": "Reply sent",
                           "full_text": "Thank you, that is kind. I'll put it together today."}]
    _repo(repo, contacts=referring, threads=answered)
    held = stage_picks.stage(str(repo / "r1"), ["1"], rows=[], root=str(repo),
                             shortlist=[_pick()], today=TODAY)
    assert "referral" in {q["id"] for q in held[0]["hold"]}          # cold, it would collide
    mine = stage_picks.stage(str(repo / "r2"), ["1"], rows=[], root=str(repo),
                             shortlist=[_pick()], for_contact=CID, today=TODAY)
    assert "referral" not in {q["id"] for q in mine[0]["hold"]}      # it goes through them
    # A contact at another employer is refused, unless a recruiter placing the role.
    with pytest.raises(SystemExit, match="works at Fernhill Freight, not Oakmere Foods"):
        stage_picks.stage(str(repo / "r3"), ["1"], rows=[], root=str(repo),
                          shortlist=[_pick()], for_contact="fernhill_freight_venn", today=TODAY)
    assert stage_picks.stage(str(repo / "r4"), ["1"], rows=[], root=str(repo), shortlist=[_pick()],
                             for_contact="kestrel_mutual_ansgar", today=TODAY)[0]["for_contact"]


def test_with_no_role_named_the_current_resume_goes_and_is_recorded(repo, capsys, monkeypatch):
    run = ["stage_picks.py", "single", str(repo / "r1"), "--for-contact", CID]
    monkeypatch.setattr(sys, "argv", run)
    assert stage_picks.main() == 1
    assert "no current CV on file: put the one you send" in capsys.readouterr().out
    cvs = repo / "documents" / "cv"
    cvs.mkdir(parents=True)
    for name in ("Morgan_Ellis_CV_2025-03.pdf", "Morgan_Ellis_CV_2026-09.pdf",
                 "Morgan_Ellis_CV_2026-09.docx"):
        (cvs / name).write_bytes(b"x")
    assert docpaths.current_resume() == "documents/cv/Morgan_Ellis_CV_2026-09.pdf"
    (cvs / "Morgan_Ellis_CV_current.pdf").write_bytes(b"x")
    assert docpaths.current_resume() == "documents/cv/Morgan_Ellis_CV_current.pdf"
    assert stage_picks.main() == 0
    out = capsys.readouterr().out
    assert "No role named, so nothing is drafted: send Quillon Varga your current CV, " \
           "documents/cv/Morgan_Ellis_CV_current.pdf, never one tailored" in out
    assert f"state.py message {CID} --attached documents/cv/Morgan_Ellis_CV_current.pdf" in out
    assert not (repo / "r1" / "picks.json").exists()                  # nothing drafted
    contacts, threads, _ = _load(repo)
    quillon = next(c for c in contacts if c["contact_id"] == CID)
    assert "CV to send: documents/cv/Morgan_Ellis_CV_current.pdf" in quillon["notes"]
    [owed] = state.resumes_owed(contacts, threads)
    assert owed["file"] == "documents/cv/Morgan_Ellis_CV_current.pdf" and owed["recorded"]
    assert stage_picks.main() == 0                                    # run twice, noted once
    capsys.readouterr()
    assert _load(repo)[0][0]["notes"].count("CV to send") == 1
    # Two undated files and nothing saying which: asked, never guessed.
    for f in cvs.iterdir():
        f.unlink()
    (cvs / "long.pdf").write_bytes(b"x")
    (cvs / "short.pdf").write_bytes(b"x")
    assert docpaths.current_resume() == ""


def test_a_resume_drafted_for_a_contact_is_owed_until_it_is_logged(repo):
    # Nobody logged an ask (they asked on a call); the drafting chat made one for them.
    made = dict(_made_row(status="drafted"), company="Fernhill Freight",
                notes="Made for Bo Venn (fernhill_freight_venn), who asked for it.",
                contact_person="Bo Venn", cv_file="cv/Morgan_Ellis_CV_Fernhill.tex")
    _repo(repo, tracker=[made], files=(CV, "cv/Morgan_Ellis_CV_Fernhill.pdf"))
    contacts, threads, tracker = _load(repo)
    [owed] = [o for o in state.resumes_owed(contacts, threads, tracker)
              if o["contact_id"] == "fernhill_freight_venn"]
    assert owed["made"] == "2026-10-15" and owed["file"] == "cv/Morgan_Ellis_CV_Fernhill.pdf"
    line = state.resume_owed_line(owed)
    assert line.startswith("a CV owed to Bo Venn (made 2026-10-15 for Demand Planning Analyst)")
    assert "--attached cv/Morgan_Ellis_CV_Fernhill.pdf" in line
    assert ("fernhill_freight_venn", "resume_owed") not in _reasons(repo)   # the tracker says so
    assert state.main(["message", "fernhill_freight_venn", "--text-file", _email(repo),
                       "--attached", "cv/Morgan_Ellis_CV_Fernhill.pdf", *_args(repo)]) == 0
    contacts, threads, tracker = _load(repo)
    assert not [o for o in state.resumes_owed(contacts, threads, tracker)
                if o["contact_id"] == "fernhill_freight_venn"]


# ------------------------------------------------------------------ 3. the guidance

def test_the_guidance_says_which_resume_and_how_to_log_it(repo):
    for text in ("Sure, send your CV to quillon@example.com", ASK):
        read = reply.classify(text)
        advice = reply.guidance(read, contact_id=CID)
        assert read["scenario"] in reply.RESUME_ROUTE_SCENARIOS, (text, read)
        which = advice["which_resume"]
        assert f"--for-contact {CID}" in which and "With no role named, your current CV" in which
        assert f"state.py message {CID} --attached <the file>" in which
    referral = reply.guidance("referral_offered")["which_resume"]
    assert "--for-contact <contact_id>" in referral and "--attached" in referral
    # Beside the next action, which stays what it was: with no address, ask for one.
    assert reply.guidance("send_resume", "Can you send me your CV?")["next_action"] == \
        reply.NO_ADDRESS_ACTION
    # Told to apply and name them: it goes in through the portal, and nothing is attached.
    told = reply.guidance(reply.classify("Apply online and put me in the referral field, "
                                         "quillon@example.com"), contact_id=CID)
    assert "--for-contact" in told["which_resume"]
    assert "attach" not in " ".join(str(v) for v in told.values()).lower()
    (repo / "documents" / "cv").mkdir(parents=True)
    (repo / "documents" / "cv" / "Morgan_Ellis_CV_current.pdf").write_bytes(b"x")
    assert "(documents/cv/Morgan_Ellis_CV_current.pdf)" in reply.guidance(
        "send_resume", "send it to quillon@example.com")["which_resume"]
    assert "which_resume" not in reply.guidance("calendar_link", "https://calendly.com/x/30")


def test_passing_a_cv_on_is_not_a_no():
    # "I'll pass it on" read as "I'll pass", a decline: the resume ask beside it was
    # blocked, and two such messages ended the thread.
    assert reply.classify(ASK)["scenario"] == "send_resume"
    assert reply.declines_in([{"direction": "in", "full_text": ASK}]) == []
    assert reply.asks_for_resume(ASK)
    for no in ("Thanks, but I'll pass.", "I'll pass on this one, sorry.",
               "I will have to pass on this.", "Thanks but I will pass on this one."):
        assert len(reply.declines_in([{"direction": "in", "full_text": no}])) == 1, no
        # A bare "pass" offers nothing: read as an introduction, "Thanks, but I'll pass."
        # came back as a referral offer.
        assert reply.classify(no)["scenario"] == "rejection", no
    for on in ("I'll pass it on to the team.", "I'll pass this on to the hiring manager.",
               "I will pass it along."):
        assert reply.classify(on)["scenario"] == "referral_offered", on
    for not_an_ask in ("Best, Quillon | quillon@example.com", "Send me your details",
                       "I've passed your CV on to the team.", "We're not hiring, so no CV needed."):
        assert not reply.asks_for_resume(not_an_ask), not_an_ask


# ------------------------------------------------------------------ 4. RECONCILE

def test_a_resume_sent_with_no_file_named_is_found_and_settled_once(repo, capsys):
    threads = THREADS + [{"contact_id": CID, "date": "2026-10-16", "direction": "out",
                          "channel": "email", "scenario": "", "summary": "CV sent as asked.",
                          "full_text": ""}]
    _repo(repo, threads=threads)
    found = _reasons(repo)
    assert list(found) == [(CID, "resume_file_not_named")]
    assert f"state.py attach {CID} --date 2026-10-16 --file <the file that went>" in \
        found[(CID, "resume_file_not_named")]
    # Not one that went before, or one only offered.
    assert not state.says_resume_went({"direction": "out", "summary": "Following up on the CV "
                                       "I sent in September."})
    assert not state.says_resume_went({"direction": "out", "full_text": "Happy to send my CV."})
    assert state.main(["attach", CID, "--date", "2026-10-16", "--file", CV,
                       "--threads", str(repo / "network_threads.csv")]) == 0
    assert "CV sent as asked.; a resume attached (cv/Morgan_Ellis_CV_Oakmere.pdf)" in \
        capsys.readouterr().out
    assert _reasons(repo) == {} and _reasons(repo) == {}             # settled, and stays so
    _repo(repo, threads=threads)
    assert state.main(["attach", CID, "--date", "2026-10-16", "--file", "unknown",
                       "--threads", str(repo / "network_threads.csv")]) == 0
    assert _reasons(repo) == {}
    assert state.main(["attach", CID, "--date", "2026-10-17", "--file", CV,
                       "--threads", str(repo / "network_threads.csv")]) == 1


def test_a_resume_the_tracker_says_went_with_nothing_in_the_thread(repo, capsys):
    _repo(repo, tracker=[_made_row(status="drafted")])
    assert (CID, "resume_not_logged") not in _reasons(repo)          # not sent yet: owed
    _repo(repo, tracker=[_made_row(status="applied")])
    detail = _reasons(repo)[(CID, "resume_not_logged")]
    capsys.readouterr()
    assert state.main(_args(repo) + ["--tracker", str(repo / "job_search_tracker.csv")]) == 0
    assert f"Quillon Varga ({CID}): resume_not_logged - the CV for" in capsys.readouterr().out
    assert "the CV for Demand Planning Analyst at Oakmere Foods was made for them" in detail
    assert f"state.py message {CID} --attached cv/Morgan_Ellis_CV_Oakmere.pdf" in detail
    assert state.main(["message", CID, "--text-file", _email(repo), "--attached", CV,
                       "--date", "2026-10-16", *_args(repo)]) == 0
    assert _reasons(repo) == {}
    # Or the person says it did not go to them.
    _repo(repo, tracker=[_made_row(status="applied")])
    assert state.main(["set", CID, "--note", "CV not sent: applied through the portal",
                       *_args(repo)]) == 0
    assert (CID, "resume_not_logged") not in _reasons(repo)
    # A row filed under somebody it was not made for is not read as one.
    other = dict(_made_row(status="applied"), channel="portal", notes="", contact_person="")
    _repo(repo, tracker=[other])
    assert (CID, "resume_not_logged") not in _reasons(repo)


def test_a_resume_asked_for_and_never_sent(repo):
    detail = _reasons(repo)[(CID, "resume_owed")]
    assert detail.startswith("they asked for your CV on 2026-10-14 and none has gone since")
    assert f"state.py message {CID} --attached <the file that went>" in detail
    # Their row saying it is owed puts it on the due list, and RECONCILE is quiet.
    owing = [dict(CONTACTS[0], next_action="Send the CV")] + CONTACTS[1:]
    _repo(repo, contacts=owing)
    assert _reasons(repo) == {}
    # A "not sent" note from before they asked settles nothing; one after it does.
    for when, quiet in (("2026-10-10", False), ("2026-10-15", True)):
        noted = [dict(CONTACTS[0], notes=f"{when}: CV not sent: they found someone")] + CONTACTS[1:]
        _repo(repo, contacts=noted)
        assert ((CID, "resume_owed") not in _reasons(repo)) is quiet, when
    # Words that only promise it do not settle it; the CV going does.
    _repo(repo)
    assert state.main(["message", CID, "--text-file", _email(repo, "Thanks! I'll send it tonight."),
                       *_args(repo)]) == 0
    assert (CID, "resume_owed") in _reasons(repo)


def test_the_example_person_is_quiet():
    root = ROOT / "profile.example" / "state"
    contacts = state.load_contacts(str(root / "network_contacts.csv"))
    threads = state.load_threads(str(root / "network_threads.csv"))
    tracker = state.load_tracker(str(root / "job_search_tracker.csv"))
    assert not [p for p in state.reconcile(contacts, threads, tracker)
                if p["reason"].startswith("resume_")]
    # Their one ask is on the due list, because the row already says it is owed.
    [owed] = state.resumes_owed(contacts, threads, tracker)
    assert owed["contact_id"] == "larkspur_retail_castellan" and owed["recorded"]


# ------------------------------------------------------------------ 5. two chats at once

def _git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), "-c", "user.name=t",
                           "-c", "user.email=t@example.com", *args],
                          capture_output=True, text=True)


def test_two_chats_at_once_leave_one_linked_record(tmp_path, monkeypatch, capsys):
    """A networking chat logs the CV going, a drafting chat makes it, neither has merged;
    the state files merge row by row, and RECONCILE then has nothing to say."""
    origin = tmp_path / "origin"
    _repo(origin, files=())
    (origin / "tools").mkdir()
    (origin / "tools" / "merge_state.py").write_text(
        (ROOT / "tools" / "merge_state.py").read_text(encoding="utf-8"), encoding="utf-8")
    (origin / ".gitattributes").write_text((ROOT / ".gitattributes").read_text("utf-8"),
                                           encoding="utf-8")
    _git(origin, "init", "-q", "-b", "master")
    _git(origin, "add", "-A")
    _git(origin, "commit", "-qm", "base")
    net, drafting = tmp_path / "net", tmp_path / "drafting"
    for clone in (net, drafting):
        assert subprocess.run(["git", "clone", "-q", str(origin), str(clone)],
                              capture_output=True).returncode == 0

    # The drafting chat: the CV made for Quillon, its tracker row, and a thank-you it logged.
    monkeypatch.setenv("LJS_STATE", str(drafting))
    (drafting / "cv").mkdir()
    (drafting / CV).write_bytes(b"%PDF-1.4 an invented CV\n")
    meta = {"abbr": "Oakmere", "company": "Oakmere Foods", "title": "Demand Planning Analyst",
            "url": "https://jobs.example/oakmere/7", "portal": "pasted", "fit": 74,
            "for_contact": CID, "for_contact_name": "Quillon Varga"}
    record_drafts.record([{"company": "Oakmere Foods", "role": "Demand Planning Analyst",
                           "abbr": "Oakmere", "for_contact": CID}], {"OAKMERE": meta},
                         "2026-10-20", path=str(drafting / "job_search_tracker.csv"))
    assert state.main(["nudge", "fernhill_freight_venn", "--text-file",
                       _email(drafting, "Hi Bo, a short follow-up on the planning team."),
                       *_args(drafting)]) == 0
    _git(drafting, "add", "-A")
    _git(drafting, "commit", "-qm", "drafting chat")

    # The networking chat, at the same time: the CV went, named, though this copy has no
    # file yet; and a nudge to somebody else.
    monkeypatch.setenv("LJS_STATE", str(net))
    assert state.main(["message", CID, "--text-file", _email(net), "--attached", CV,
                       "--channel", "email", *_args(net)]) == 0
    assert state.main(["nudge", "kestrel_mutual_ansgar", "--text-file",
                       _email(net, "Hi Pell, a short follow-up on the analytics team."),
                       *_args(net)]) == 0
    _git(net, "add", "-A")
    _git(net, "commit", "-qm", "networking chat")

    # Merged: both chats' rows, no conflict, the driver doing the work. Git's own line
    # merge would stop on both files: each chat added its rows at the same place.
    _git(net, "remote", "add", "drafting", str(drafting))
    _git(net, "fetch", "-q", "drafting")
    for name in ("network_threads.csv", "network_contacts.csv"):
        sides = []
        for ref in ("master~1", "master", "drafting/master"):
            side = tmp_path / ("%s_%d" % (name, len(sides)))
            side.write_text(_git(net, "show", "%s:%s" % (ref, name)).stdout, encoding="utf-8")
            sides.append(str(side))
        line_merge = subprocess.run(["git", "merge-file", "-p", sides[1], sides[0], sides[2]],
                                    capture_output=True, text=True)
        assert line_merge.returncode > 0, name
    sys.path.insert(0, str(ROOT / "tools"))
    import merge_state
    merge_state.install(str(net))
    r = _git(net, "merge", "-q", "--no-edit", "drafting/master")
    assert r.returncode == 0, r.stdout + r.stderr
    for name in ("network_threads.csv", "job_search_tracker.csv", "network_contacts.csv"):
        assert "<<<<<<<" not in (net / name).read_text(encoding="utf-8"), name
    contacts, threads, tracker = _load(net)
    assert len([t for t in threads if t["date"] == TODAY]) == 3
    [row] = tracker
    assert row["contact_person"] == "Quillon Varga" and state.made_for(row, contacts)
    sent = [s for s in state.resumes_sent(threads, CID)]
    assert [s["files"] for s in sent] == [[CV]]
    assert os.path.splitext(sent[0]["files"][0])[0] == os.path.splitext(row["cv_file"])[0]
    assert not [p for p in state.reconcile(contacts, threads, tracker)
                if p["reason"].startswith("resume_")]
    # RECONCILE and LINKED, as the person reads them.
    capsys.readouterr()
    assert state.main(_args(net) + ["--tracker", str(net / "job_search_tracker.csv")]) == 0
    out = capsys.readouterr().out
    assert f"Quillon Varga -> Demand Planning Analyst; CV sent {TODAY} ({CV})" in out
    assert "resume_" not in out


def test_two_chats_on_one_contact_row_merge_field_by_field(tmp_path, monkeypatch):
    """The drafting chat records which CV goes (no role named: a note on their row) while
    the networking chat logs it going (their next action, a message row): one row, two
    fields, merged."""
    origin = tmp_path / "origin"
    _repo(origin, files=("documents/cv/Morgan_Ellis_CV_current.pdf",))
    (origin / "tools").mkdir()
    (origin / "tools" / "merge_state.py").write_text(
        (ROOT / "tools" / "merge_state.py").read_text(encoding="utf-8"), encoding="utf-8")
    (origin / ".gitattributes").write_text((ROOT / ".gitattributes").read_text("utf-8"),
                                           encoding="utf-8")
    _git(origin, "init", "-q", "-b", "master")
    _git(origin, "add", "-A")
    _git(origin, "commit", "-qm", "base")
    net, drafting = tmp_path / "net", tmp_path / "drafting"
    for clone in (net, drafting):
        subprocess.run(["git", "clone", "-q", str(origin), str(clone)], capture_output=True)
    general = "documents/cv/Morgan_Ellis_CV_current.pdf"
    monkeypatch.setenv("LJS_STATE", str(drafting))
    got = stage_picks.general_resume_for(CID, today=TODAY)
    assert got["file"] == general and got["noted"]
    _git(drafting, "commit", "-qam", "drafting chat")
    monkeypatch.setenv("LJS_STATE", str(net))
    assert state.main(["message", CID, "--text-file", _email(net), "--attached", general,
                       *_args(net)]) == 0
    _git(net, "commit", "-qam", "networking chat")
    _git(net, "remote", "add", "drafting", str(drafting))
    _git(net, "fetch", "-q", "drafting")
    sys.path.insert(0, str(ROOT / "tools"))
    import merge_state
    merge_state.install(str(net))
    r = _git(net, "merge", "-q", "--no-edit", "drafting/master")
    assert r.returncode == 0, r.stdout + r.stderr
    contacts, threads, tracker = _load(net)
    quillon = next(c for c in contacts if c["contact_id"] == CID)
    assert f"CV to send: {general}" in quillon["notes"]                      # drafting's field
    assert quillon["next_action"].startswith(f"CV sent {TODAY} ({general})")  # networking's
    assert state.resumes_owed(contacts, threads, tracker) == []
    assert not [p for p in state.reconcile(contacts, threads, tracker)
                if p["reason"].startswith("resume_")]


# ------------------------------------------------------------------ 6. the due list

def test_the_due_list_says_who_is_owed_a_resume_and_the_employer_line_what_went(repo):
    contacts, threads, tracker = _load(repo)
    text = open_actions.render(open_actions.build(contacts, threads, tracker, TODAY), TODAY)
    assert "**a CV owed to Quillon Varga** (asked 2026-10-14): send it, then log it" in text
    due = open_actions.due_items(contacts, threads, tracker, TODAY)
    [mine] = [i for i in due if i.get("contact_id") == CID]
    assert mine["what"].startswith("a CV owed to Quillon Varga (asked 2026-10-14)")
    # Answered with a promise: no reply is owed now, and the CV still is.
    assert state.main(["message", CID, "--text-file", _email(repo, "Thanks! I'll send it tonight."),
                       *_args(repo)]) == 0
    contacts, threads, tracker = _load(repo)
    [mine] = [i for i in open_actions.due_items(contacts, threads, tracker, TODAY)
              if i.get("contact_id") == CID]
    assert mine["kind"] == "resume" and mine["what"].startswith("a CV owed to Quillon Varga")
    # A later day the person put on it holds it off the due list until then.
    later = [dict(c, next_action_due="2026-10-30") if c["contact_id"] == CID else c
             for c in contacts]
    assert not [i for i in open_actions.due_items(later, threads, tracker, TODAY)
                if i.get("contact_id") == CID]
    # Sent: the owed line goes, and the employer's line says which went and when.
    assert state.main(["message", CID, "--text-file", _email(repo), "--attached", CV,
                       *_args(repo)]) == 0
    contacts, threads, tracker = _load(repo)
    text = open_actions.render(open_actions.build(contacts, threads, tracker, TODAY), TODAY,
                               only_live=False)
    oakmere = text.split("## Oakmere Foods", 1)[1].split("\n## ", 1)[0]
    assert "owed to Quillon" not in oakmere
    assert f"- CV sent to Quillon Varga {TODAY}: {CV}" in oakmere
    assert not [i for i in open_actions.due_items(contacts, threads, tracker, TODAY)
                if i.get("kind") == "resume"]


# ------------------------------------------------------------------ 7. the interview pack

def test_the_interview_pack_says_which_resume_a_contact_holds(repo):
    # The referrer who asked holds the file that went to them, which may not be the one the
    # tracker row names: the pack says it beside what was sent, by name and date.
    import interview_pack
    sent = {"contact_id": CID, "date": "2026-10-15", "direction": "out", "channel": "email",
            "scenario": "send_resume", "full_text": EMAIL,
            "summary": "CV sent as asked; " + state.attachment_note(CV)}
    unnamed = dict(sent, date="2026-10-16", summary="CV sent again.")
    ctx = {"company": "Oakmere Foods", "contacts": CONTACTS, "threads": THREADS + [sent, unnamed]}
    lines = interview_pack._held_by_contacts(ctx)
    assert lines[0] == f"- Sent to Quillon Varga on 2026-10-15: {CV}"
    assert "file not named (state.py attach %s)" % CID in lines[1]
    # Someone at another employer, and a message that only offered one, add nothing.
    assert interview_pack._held_by_contacts(dict(ctx, company="Kestrel Mutual")) == []
