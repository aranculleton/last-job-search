"""What two independent bug hunts found in the interview pipeline, pinned so none comes back.

A rebuild that deleted answers the person wrote for questions not on this stage's list;
"careful" flags saved as their answer and doubling on every rebuild; "pay" read inside
"payments"; a referral process counted as an application that reached interview and
credited with a draft nobody sent; a campaign chat invisible when nothing was due; call
preps losing rewritten answers; a sync that said "nothing was lost" when nothing moved.
Every person, employer and role here is invented.
"""
from __future__ import annotations

import csv
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "network"))

import interview_pack as P  # noqa: E402
import open_actions  # noqa: E402
import outreach  # noqa: E402
import prep  # noqa: E402
import record_drafts  # noqa: E402
import schema  # noqa: E402
import throttle  # noqa: E402
import what_works  # noqa: E402

TODAY = "2026-10-19"
FIRM, ROLE = "Calder & Rook Consulting", "Operations Analytics Consultant"
REFERRER = {"contact_id": "calder_rook_vance", "name": "Ivo Vance", "company": FIRM,
            "title": "Associate Partner", "route": "alumni", "status": "referral_in_progress"}
RECRUITER = {"contact_id": "calder_rook_marsh", "name": "Tamsin Marsh", "company": FIRM,
             "title": "Talent Acquisition Partner", "route": "referral",
             "referred_by": "calder_rook_vance", "status": "call_booked",
             "next_action_due": "2026-10-21"}
SAID = ("I'm an operations analyst, and for seven years I've turned warehouse data into "
        "forecasts that people actually order from, which is the work I want more of.")


def _write(path, rows, cols):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setenv("LJS_STATE", str(tmp_path))
    _write(tmp_path / "network_contacts.csv", [REFERRER, RECRUITER], schema.CONTACT_COLUMNS)
    _write(tmp_path / "network_threads.csv", [], schema.THREAD_COLUMNS)
    return tmp_path


def _tracker(state):
    with open(state / "job_search_tracker.csv", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _process(*extra):
    return P.main(["process", FIRM, "--contact", "calder_rook_vance", "--role", ROLE,
                   "--stage", "Recruiter screen", "--date", "2026-10-21", "--today", TODAY,
                   *extra])


def _path():
    return os.path.join(outreach.app_folder(FIRM, ROLE), P.LIVING)


def _doc():
    return open(_path(), encoding="utf-8").read()


def _answer(text, question):
    return text.split("### %s\n" % question, 1)[1].split("\n### ", 1)[0].split("\n## ", 1)[0]


# ------------------------------------------------------------ the living document

def test_an_answer_for_a_question_this_stage_does_not_list_is_never_dropped(state):
    _process()
    text = _doc().replace("### Why are you looking?\n", "### Why are you looking?\n%s\n" % SAID, 1)
    open(_path(), "w", encoding="utf-8").write(text)
    P.main(["pack", FIRM, "--stage", "Technical interview", "--today", TODAY, "--write"])
    P.main(["pack", FIRM, "--stage", "Offer received", "--today", TODAY, "--write"])
    assert _doc().count(SAID) == 1


def test_a_careful_flag_is_never_kept_as_the_answer(state, monkeypatch):
    _process()
    import learned
    monkeypatch.setattr(learned, "dislikes", lambda text: ["moves"] if "moves" in text else [])
    q = "Walk me through your career, and the moves between jobs."
    P.main(["pack", FIRM, "--today", TODAY, "--write"])
    once = _answer(_doc(), q).count("careful:")
    for _ in range(2):
        P.main(["pack", FIRM, "--today", TODAY, "--write"])
    block = _answer(_doc(), q)
    assert once and block.count("careful:") == once and P.TO_WRITE in block


def test_what_you_found_out_stays_after_the_move_is_a_year_old(state, monkeypatch):
    monkeypatch.setattr(P, "_person", lambda d: {"identity.moved": "2026-05",
                                                 "identity.area": "Ancoats"}.get(d, ""))
    _process()
    text = _doc().replace(P.FOUND_EMPTY, "- Tram stop two minutes away (source: my walk).\n"
                                         "#### Food\n- A bakery on the corner (source: my walk).")
    open(_path(), "w", encoding="utf-8").write(text)
    P.main(["pack", FIRM, "--today", "2027-09-01", "--write"])
    again = _doc()
    assert "Tram stop" in again and "#### Food" in again and "bakery" in again


def test_placeholders_are_not_kept_and_notes_keep_their_paragraphs(state):
    _process()
    text = _doc().replace("## Notes\n\n" + P.NOTES_EMPTY,
                          "## Notes\n\n" + P.NOTES_EMPTY + "\n- First.\n\nSecond paragraph.")
    text = text.replace("## To rework\n\n- " + P.REWORK_EMPTY,
                        "## To rework\n\nSay the number before the method.")
    open(_path(), "w", encoding="utf-8").write(text)
    P.main(["pack", FIRM, "--today", TODAY, "--write"])
    again = _doc()
    notes = again.split("## Notes\n", 1)[1]
    assert P.NOTES_EMPTY not in notes and "- First.\n\nSecond paragraph." in notes
    assert "Say the number before the method." in again


def test_check_hears_short_answers_and_refuses_bullets_and_pastes(state, capsys):
    _process()
    text = _doc()
    for q in ("Tell me about yourself.", "Why are you looking?"):
        text = text.replace("### %s\n" % q, "### %s\n%s\n" % (q, SAID), 1)
    text = text.replace("### Why %s?\n" % FIRM, "### Why %s?\n%s\n" % (FIRM, SAID), 1)
    text = text.replace("### What are your salary expectations?\n",
                        "### What are your salary expectations?\nBetween 48 and 58, base.\n", 1)
    text = text.replace("### Do you need sponsorship?\n",
                        "### Do you need sponsorship?\n- Settled status\n- No sponsorship\n", 1)
    open(_path(), "w", encoding="utf-8").write(text)
    found = dict(P.check(_path()))
    assert "What are your salary expectations?" not in found
    assert "bullet" in found["Do you need sponsorship?"]
    pasted = text.replace("Between 48 and 58, base.", "Prepared: One month. (source: profile)")
    open(_path(), "w", encoding="utf-8").write(pasted)
    assert "pasted" in dict(P.check(_path()))["What are your salary expectations?"]


# ------------------------------------------------------------ registering a process

def test_a_drafted_row_becomes_the_process_and_an_applied_one_is_refused(state, capsys):
    row = {k: "" for k in record_drafts.HEADER}
    row.update(date="2026-10-01", company=FIRM, role=ROLE, status="drafted",
               cv_file="cv/Morgan_Ellis_CV_CalderRook.tex")
    _write(state / "job_search_tracker.csv", [row], record_drafts.HEADER)
    assert _process() == 0
    rows = _tracker(state)
    assert len(rows) == 1 and throttle.is_process(rows[0]) and rows[0]["status"] == "interview"
    assert "never sent" in rows[0]["notes"]
    assert "Drafted for this role and never sent" in _doc() and "Sent: cv/" not in _doc()
    rows[0].update(status="applied", notes="")
    _write(state / "job_search_tracker.csv", rows, record_drafts.HEADER)
    capsys.readouterr()
    assert _process() == 1
    assert "already on record" in capsys.readouterr().err


def test_a_rebooked_stage_replaces_its_line_and_no_second_screen_appears(state):
    _process()
    P.main(["process", FIRM, "--contact", "calder_rook_vance", "--role", ROLE,
            "--stage", "Recruiter screen", "--date", "2026-10-23", "--today", TODAY])
    outcome = open(os.path.join(outreach.app_folder(FIRM, ROLE), "outcome.md"),
                   encoding="utf-8").read()
    assert outcome.count("Recruiter screen") == 1 and "2026-10-23" in outcome
    assert "Phone screen" not in outcome


@pytest.mark.parametrize("argv", [["pack", FIRM, "--today", "2026-13-45"],
                                  ["pack", FIRM, "--date", "2026-10-3"],
                                  ["process", FIRM, "--contact", "x", "--role", "r",
                                   "--today", "13/10/2026"]])
def test_a_bad_date_is_refused_before_anything_is_written(state, argv):
    with pytest.raises(SystemExit) as exc:
        P.main(argv)
    assert exc.value.code == 2
    assert not os.path.exists(state / "job_search_tracker.csv")


def test_a_missing_map_is_an_error_not_a_traceback(state, capsys):
    _process()
    assert P.main(["pack", FIRM, "--map", str(state / "nope.json")]) == 1
    assert "interview_pack:" in capsys.readouterr().err


def test_rework_finds_the_process_without_a_role(state):
    _process()
    P.main(["rework", "--company", FIRM, "--stage", "Recruiter screen",
            "--question", "Why consulting?", "--note", "Lead with the clients."])
    assert "Lead with the clients." in _doc()


# ------------------------------------------------------------ reading the world

def test_pay_is_a_whole_word():
    ctx = {"form": [("Have you worked with payment systems before?", "Yes"),
                    ("What are your salary expectations?", "GBP 50,000 to 55,000")]}
    assert P._form_value(ctx, P._PAY_Q)[1] == "GBP 50,000 to 55,000"


def test_what_they_were_told_reads_amounts_moves_and_employers_as_they_are():
    said = dict((t, s) for t, s in P._said("I'm keen on moving into pricing work. "
                                          "We serve 250k customers a week."))
    assert "where you are" not in said and "pay" not in said
    assert P._differs_from_band("I'm looking for around £40,000 base.")
    assert not P._differs_from_band("Somewhere between 48,000 and 58,000.")
    assert "current employer" in dict(P._said("I’m at Brindle & Hart at the moment."))


def test_a_sponsorship_sentence_is_not_a_temporary_status():
    ctx = {"facts": {"work_authorization": "British citizen. No visa sponsorship required."}}
    assert not P.temporary_status(ctx)
    ctx = {"facts": {"work_authorization": "Working holiday permit until 2027."}}
    assert P.temporary_status(ctx)


def test_someone_introduced_to_you_is_not_your_referrer():
    ctx = {"company": FIRM, "contacts": [RECRUITER], "row": {}, "outcome": ""}
    assert P.referrer_of(ctx) == ""
    assert P.referrer_of(dict(ctx, contacts=[RECRUITER, REFERRER])) == "Ivo Vance"


@pytest.mark.parametrize("sector,company,summary,want", [
    ("Banking", "Northvale Bank", "A retail bank with a wealth advisory arm.", "bank"),
    ("", "Northlight Creative Agency", "Brand work for retailers.", ""),
    ("", "Bankside Freight", "Pallets across the North.", ""),
    ("", FIRM, "A management consultancy.", "consulting"),
])
def test_the_employer_type_comes_from_the_most_direct_source(sector, company, summary, want):
    ctx = {"row": {"sector": sector}, "company": company, "research": {"summary": summary}}
    assert P.employer_type(ctx) == want


@pytest.mark.parametrize("with_,want", [
    ("Priya A. Shah", [("Priya A. Shah", "")]),
    ("two partners", [("", "two partners")]),
    ("Tom Head", [("Tom Head", "")]),
    ("Dana Okafor, Head of Data", [("Dana Okafor", "Head of Data")]),
    ("Engagement Manager and Sam Lee", [("", "Engagement Manager"), ("Sam Lee", "")]),
])
def test_who_you_are_meeting_is_read_as_names_and_titles(with_, want):
    got = [(w["name"], w["title"]) for w in P._interviewers({"with": with_})]
    assert got == want


def test_a_buyer_is_not_a_recruiter():
    assert P._kind("Sourcing Manager") == "manager"


@pytest.mark.parametrize("question,company,checking", [
    ("Why Dovecote Freight?", "Dovecote Freight", "chose them"),
    ("Why Now Analytics?", "Now Analytics", "chose them"),
    ("Why data science?", "Now Analytics", "this work on purpose"),
    ("Why did you leave Oakmere Foods?", "", "running from something"),
    ("Tell me about a project that failed.", "", "whether you learn"),
    ("I noticed you moved recently?", "", ""),
    ("Tell me about a career highlight project.", "", "did the work yourself"),
    ("Tell me about your experience with SQL.", "", "as your papers say"),
    ("What is your experience with SAP?", "", "a gap"),
])
def test_question_patterns_read_whole_words(question, company, checking):
    got = P.intent(question, company)[0]
    assert (checking in got) if checking else got == ""


def test_a_team_is_matched_by_its_name_not_by_likeness():
    research = {"not_found": ["Supply Chain Analytics"],
                "teams": {"Data Platform": [{"claim": "Runs the warehouse.", "url": "u"}]}}
    assert P._researched(research, "Supply Chain Engineering")[0] == "todo"
    assert P._researched(research, "Supply Chain Analytics")[0] == "none"
    assert P._researched(research, "Data Platform")[0] == "found"


# ------------------------------------------------------------ the rest of the app

def test_a_process_is_not_an_application_and_is_never_credited_with_a_draft(state):
    _process()
    rows = _tracker(state)
    assert what_works.application_cases(rows, TODAY) == []
    draft = {"company": FIRM, "role": ROLE, "abbr": "CalderRook", "jobs": [{"bullets": ["b1"]}]}
    assert what_works.draft_for(rows[0], [draft]) is None
    line = what_works.event_company(rows, [draft], FIRM, TODAY)
    assert "a process with no application" in line and "referral application" not in line


def test_a_campaign_chat_shows_on_its_employer_when_nothing_is_due(state):
    _process()
    P.main(["campaign", FIRM, "--yes", "Job search: Calder & Rook campaign"])
    rows = _tracker(state)
    entries = open_actions.build([], [], rows, TODAY)
    text = "\n".join(open_actions.render(entries, TODAY)) if isinstance(
        open_actions.render(entries, TODAY), list) else open_actions.render(entries, TODAY)
    assert "handled by its campaign chat (Job search: Calder & Rook campaign)" in text
    assert "process, no application" in text


# ------------------------------------------------------------ call preps

FACTS = {"summary": "Operations analyst with seven years turning warehouse data into forecasts.",
         "narrative": "An unconventional route.", "strengths": ["Built forecasts."],
         "work_authorization": "No sponsorship required."}


def test_a_rewritten_answer_beats_the_pointer_and_survives_a_new_role(tmp_path):
    peer = {"contact_id": "larkspur_retail_castellan", "name": "Juno Castellan",
            "company": "Larkspur Retail", "title": "Data Analyst", "status": "call_booked"}
    path = prep.write_prep(peer, profile_facts=FACTS, today=TODAY, root=str(tmp_path))
    text = open(path, encoding="utf-8").read()
    route_q = prep._ROUTE_QUESTION
    said_route = "I came to it sideways, from the shop floor, and I've stayed for the puzzles."
    text = text.replace("  **A.** %s" % prep.NARRATIVE_POINTER, "  **A.** " + said_route, 1)
    open(path, "w", encoding="utf-8").write(text)
    again = prep.write_prep(peer, profile_facts=FACTS, today=TODAY, root=str(tmp_path),
                            application={"role": "Pricing Analyst", "status": "interview"})
    rebuilt = open(again, encoding="utf-8").read()
    assert said_route in rebuilt and route_q in rebuilt


def test_a_multi_line_answer_is_read_whole():
    doc = ("- **Q.** Tell me about yourself.\n  **A.** I'm an analyst.\n    I like forecasts.\n"
           "  - careful: x\n- **Q.** Next?\n  **A.** Yes. (source: y)\n")
    got = prep.answers_in(doc)
    assert got[0][1] == "I'm an analyst.\nI like forecasts." and got[1] == ("Next?", "Yes.", "y")


def test_a_peer_coffee_chat_is_not_called_an_interview_stage():
    peer = {"contact_id": "calder_rook_reed", "name": "Ola Reed", "company": FIRM,
            "title": "Data Engineer", "route": "alumni", "status": "call_booked"}
    app = {"company": FIRM, "role": ROLE, "status": "interview"}
    assert not any("stage of a live hiring process" in ln for ln in prep._process_lines(peer, app))
    assert any("stage of a live hiring process" in ln for ln in prep._process_lines(RECRUITER, app))


def test_a_prep_is_stale_once_research_arrives(tmp_path):
    path = prep.write_prep(RECRUITER, profile_facts=FACTS, today=TODAY, root=str(tmp_path))
    assert not prep.stale(path, RECRUITER, [], {}, None, TODAY)
    assert prep.stale(path, RECRUITER, [], {"fetched_date": "2026-10-19", "facts": ["x"]},
                      None, TODAY)


def test_the_introduction_is_answered_with_a_name(state):
    qs = {q["question"]: q["answer"] for q in prep.likely_questions(RECRUITER, "", FACTS)}
    assert qs.get("How did the introduction come about?") == "Ivo Vance"
    assert json.dumps(qs)


def test_a_rebuild_never_freezes_the_tools_own_words(tmp_path):
    peer = {"contact_id": "larkspur_retail_castellan", "name": "Juno Castellan",
            "company": "Larkspur Retail", "title": "Data Analyst", "status": "call_booked"}
    # The profile's summary, which the document places as it stands. (It once varied the
    # work-authorization line; that answer is now the person's stock answer or their words
    # for this reader, never the profile's raw line, so the line no longer reaches it.)
    old = dict(FACTS, summary="Operations analyst with seven years of warehouse forecasts.")
    prep.write_prep(peer, profile_facts=old, today=TODAY, root=str(tmp_path))
    new = dict(FACTS, summary="Planning analyst who builds the forecasts a network orders from.")
    path = prep.write_prep(peer, profile_facts=new, today=TODAY, root=str(tmp_path))
    text = open(path, encoding="utf-8").read()
    assert "a network orders from" in text and "seven years of warehouse" not in text


def test_an_old_document_keeps_only_answers_said_in_the_first_person():
    doc = ("- **Q.** How did the introduction come about?\n  **A.** larkspur_retail_castellan "
           "(source: c)\n- **Q.** Why are you looking?\n  **A.** I want a bigger planning "
           "problem to own, honestly. (source: p)\n")
    kept = prep.said_answers(doc)
    assert list(kept) == [prep._qkey("Why are you looking?")]


def test_an_answer_written_in_two_paragraphs_is_kept_whole():
    doc = ("- **Q.** Tell me about yourself.\n  **A.** I'm an analyst.\nI like forecasts.\n\n"
           "    And I like the people who use them.\n- **Q.** Next?\n  **A.** Yes.\n")
    got = prep.answers_in(doc)[0][1]
    assert got == "I'm an analyst.\nI like forecasts.\n\nAnd I like the people who use them."


def test_a_next_step_due_soon_is_a_call_only_when_it_says_so():
    contact = {"company": FIRM, "status": "in_conversation", "next_action": "Send the CV",
               "next_action_due": "2026-10-20"}
    assert prep.research_needed(contact, {}, today=TODAY) == ""
    contact["next_action"] = "Coffee chat at 10"
    assert prep.research_needed(contact, {}, today=TODAY).startswith("RESEARCH NEXT")


def test_a_process_never_hides_an_earlier_rejection(state):
    import followups
    old = {k: "" for k in record_drafts.HEADER}
    old.update(date="2026-09-01", company=FIRM, role=ROLE, status="rejected")
    _write(state / "job_search_tracker.csv", [old], record_drafts.HEADER)
    _process()
    rows = _tracker(state)
    assert not followups.superseded(rows)
    assert len(what_works.application_cases(rows, TODAY)) == 1


def test_a_closed_process_is_not_called_an_application(state):
    _process()
    row = dict(_tracker(state)[0], status="rejected")
    from company_key import key
    posting = [{"title": ROLE, "company": FIRM, "url": "https://example.com/j/1",
                "priority": 70, "fit": 80}]
    _kept, skipped = throttle.throttle(posting, {}, {}, {}, TODAY,
                                       closed={key(FIRM): [row]})
    assert skipped and "hiring process for this role" in skipped[0]["skip_reason"]
    assert "already applied" not in skipped[0]["skip_reason"]


def test_a_draft_nobody_sent_is_not_an_application_there():
    import why
    contact = {"contact_id": "calder_rook_vance", "name": "Ivo Vance", "company": FIRM,
               "title": "Associate Partner", "status": "not_contacted"}
    drafted = {"company": FIRM, "role": ROLE, "status": "drafted"}
    got = why.why_them(contact, {}, applied=[drafted])
    assert not any("applied there" in r for _p, r in got["reasons"])


# ------------------------------------------------------------ the verification pass

def test_a_declined_referral_is_never_a_referral():
    no = {"contact_id": "larkspur_okoro", "name": "Ben Okoro", "company": FIRM,
          "status": "closed", "outcome": "declined: no referral, hiring freeze"}
    ctx = {"company": FIRM, "contacts": [no], "row": {"notes": ""}, "outcome": ""}
    assert P.referrer_of(ctx) == ""
    assert P._said_referral("referral_converted_to_interview")


def test_never_moved_means_no_move_is_claimed(monkeypatch):
    monkeypatch.setattr(P, "_person", lambda d: {"identity.moved": "none"}.get(d, ""))
    assert P._moved_on() == ""
    monkeypatch.setattr(P, "_person", lambda d: {"identity.moved": "2026-05"}.get(d, ""))
    assert P._moved_on() == "2026-05"


def test_a_visa_with_no_sponsorship_needed_is_still_a_temporary_status():
    ctx = {"facts": {"work_authorization": "Graduate visa, valid until 2027, no sponsorship "
                                           "required until then."}}
    assert P.temporary_status(ctx)


@pytest.mark.parametrize("with_,want", [
    ("Ama Reyes, Data Science; Ola Berg, Supply Chain Analytics",
     [("Ama Reyes", "Data Science"), ("Ola Berg", "Supply Chain Analytics")]),
    ("Lee Marsh, Data & Analytics Manager", [("Lee Marsh", "Data & Analytics Manager")]),
    ("Dana Okafor (Head of Data)", [("Dana Okafor", "Head of Data")]),
    ("Dana Okafor - Head of Data", [("Dana Okafor", "Head of Data")]),
    ("Dr. Ruth Abara", [("Dr. Ruth Abara", "")]),
    ("Ana de la Cruz", [("Ana de la Cruz", "")]),
    ("Pat", [("Pat", "")]),
])
def test_more_ways_of_writing_who_you_are_meeting(with_, want):
    assert [(w["name"], w["title"]) for w in P._interviewers({"with": with_})] == want


@pytest.mark.parametrize("title,team", [("Head of Data", "Data"),
                                        ("Data Science Manager", "Data Science"),
                                        ("Associate Partner, Operations Practice",
                                         "Operations Practice"),
                                        ("Engagement Manager", ""), ("Partner", "")])
def test_a_team_is_the_field_in_a_title(title, team):
    assert P._team_of(title) == team


def test_what_a_software_company_sells_to_is_not_what_it_is():
    ctx = {"row": {"sector": "Technology"}, "company": "Dovecote Systems",
           "research": {"summary": "software used by retailers, banks and consulting firms"}}
    assert P.employer_type(ctx) == "product"


def test_a_new_stage_goes_after_the_last_one_held_and_keeps_its_interviewer(state):
    _process()
    path = os.path.join(outreach.app_folder(FIRM, ROLE), "outcome.md")
    text = open(path, encoding="utf-8").read().replace(
        "- [ ] Recruiter screen (scheduled 2026-10-21)", "- [x] Recruiter screen (2026-10-21)")
    open(path, "w", encoding="utf-8").write(text)
    P.main(["process", FIRM, "--contact", "calder_rook_vance", "--role", ROLE,
            "--stage", "Partner interview", "--date", "2026-11-02", "--with", "Ivo Vance",
            "--today", TODAY])
    P.main(["process", FIRM, "--contact", "calder_rook_vance", "--role", ROLE,
            "--stage", "Partner interview", "--date", "2026-11-04", "--today", TODAY])
    lines = [ln for ln in open(path, encoding="utf-8").read().splitlines() if ln.startswith("- [")]
    assert lines[0].startswith("- [x] Recruiter screen")
    assert lines[1] == "- [ ] Partner interview (scheduled 2026-11-04, with Ivo Vance)"


def test_savings_are_not_pay_and_a_band_inside_the_target_is_not_flagged():
    assert "pay" not in dict(P._said("My forecast released £1.1M of safety stock."))
    assert not P._differs_from_band("I'm looking for between £52k and £56k base.")


def test_an_unsent_form_placeholder_is_never_quoted():
    ctx = {"form": [("What are your salary expectations?", "[decide: per application]")]}
    assert P._form_value(ctx, P._PAY_Q) == ("", "")


def test_a_strength_on_paper_is_not_framed_as_a_gap():
    assert "gap" not in P.intent("Tell me about your experience with dbt.")[1]
    assert "close the gap" in P.intent("What is your experience with SAP?")[1]
