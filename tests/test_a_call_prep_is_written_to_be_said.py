"""A call prep says the referrer's name, speaks to its reader, and holds answers to be said.

Seen in one real prep.md: "Referred by <employer>_<surname>" where a name belonged; "name
them in the first minute" to a recruiter who already knew who routed it; the peer's
work-authorization line for a recruiter; the resume summary pasted in as "tell me about
yourself"; the personal narrative copied nearly word for word; a document still saying
"wait" after the call was booked; and "not researched" two days before the call with
nothing asking for research. Every person here is invented.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "network"))

import compose  # noqa: E402
import prep  # noqa: E402

REFERRER = {"contact_id": "calder_rook_vance", "name": "Ivo Vance", "company": "Calder & Rook",
            "title": "Associate Partner", "status": "referral_in_progress"}
RECRUITER = {"contact_id": "calder_rook_marsh", "name": "Tamsin Marsh", "company": "Calder & Rook",
             "title": "Talent Acquisition Partner", "route": "referral",
             "referred_by": "calder_rook_vance", "status": "call_booked",
             "next_action_due": "2026-10-21"}
PEER = {"contact_id": "larkspur_retail_castellan", "name": "Juno Castellan",
        "company": "Larkspur Retail", "title": "Data Analyst", "route": "alumni",
        "referred_by": "calder_rook_vance", "status": "call_booked"}
FACTS = {"summary": "Operations analyst with seven years turning warehouse data into forecasts.",
         "narrative": "An unconventional route: retail floor first, then analytics.",
         "work_authorization": "UK settled status. No sponsorship required."}
SAID = ("I'm an operations analyst, and for seven years I've turned warehouse data into "
        "forecasts that people actually order from.")


def test_the_referrer_is_named_not_their_id():
    assert prep.referrer_name(RECRUITER, [REFERRER, RECRUITER]) == "Ivo Vance"
    # A name written by hand stands as it is.
    assert prep.referrer_name({"referred_by": "Ivo Vance"}, []) == "Ivo Vance"


def test_a_recruiter_hears_the_referrer_when_asked_and_a_peer_hears_it_first():
    assert "when asked" in prep._referrer_advice(RECRUITER)
    assert "first minute" in prep._referrer_advice(PEER)


def test_work_authorization_is_said_in_the_readers_register():
    employer = compose.WORK_AUTH.get("employer") or compose.WORK_AUTH["senior"]
    assert prep.work_auth_for(RECRUITER) == employer
    # A peer's booked coffee chat is not a hiring process.
    assert prep.work_auth_for(PEER) == compose.WORK_AUTH["peer"]


def test_profile_wording_is_marked_and_the_narrative_is_never_pasted():
    qs = {q["question"]: q["answer"] for q in prep.likely_questions(PEER, "", FACTS)}
    assert qs["Tell me about yourself."].startswith(prep.RAW_MARK)
    assert prep.NARRATIVE_POINTER in qs.values()
    assert not any(FACTS["narrative"] in a for a in qs.values())


def test_check_refuses_raw_or_written_answers_and_passes_said_ones():
    doc = ("- **Q.** Tell me about yourself.\n  **A.** %s %s (source: x)\n"
           "- **Q.** How did you get here?\n  **A.** %s (source: y)\n"
           % (prep.RAW_MARK, FACTS["summary"], prep.NARRATIVE_POINTER))
    assert [q for q, _w in prep.check_answers(doc)] == ["Tell me about yourself."]
    written = doc.replace("%s %s" % (prep.RAW_MARK, FACTS["summary"]),
                          "Operations analyst with seven years. Built forecasts.")
    assert prep.check_answers(written)
    said = doc.replace("%s %s" % (prep.RAW_MARK, FACTS["summary"]), SAID)
    assert prep.check_answers(said) == []


def test_a_rewritten_answer_survives_a_rebuild(tmp_path):
    path = prep.write_prep(PEER, profile_facts=FACTS, today="2026-10-19", root=str(tmp_path))
    text = open(path, encoding="utf-8").read()
    raw = "%s %s" % (prep.RAW_MARK, FACTS["summary"])
    assert raw in text
    open(path, "w", encoding="utf-8").write(text.replace(raw, SAID))
    again = prep.write_prep(PEER, profile_facts=FACTS, today="2026-10-20", root=str(tmp_path))
    rebuilt = open(again, encoding="utf-8").read()
    assert SAID in rebuilt and raw not in rebuilt


def test_a_prep_is_stale_once_the_thread_moves(tmp_path):
    waiting = dict(PEER, status="awaiting_reply", next_action="Wait")
    path = prep.write_prep(waiting, profile_facts=FACTS, today="2026-10-17", root=str(tmp_path))
    assert not prep.stale(path, waiting, [])
    assert prep.stale(path, dict(waiting, status="call_booked"), [])
    reply = [{"contact_id": PEER["contact_id"], "date": "2026-10-18", "direction": "in",
              "scenario": "reply", "summary": "yes, Tuesday"}]
    assert prep.stale(path, waiting, reply)


def test_a_booked_call_with_nothing_researched_asks_for_research_first():
    need = prep.research_needed(RECRUITER, {}, today="2026-10-19")
    assert need.startswith("RESEARCH FIRST") and "employer-researcher" in need
    assert prep.research_needed(RECRUITER, {"facts": ["x"]}, today="2026-10-19") == ""
    far = dict(PEER, status="awaiting_reply", next_action_due="2026-12-01")
    assert prep.research_needed(far, {}, today="2026-10-19") == ""


def test_a_recruiter_screen_on_a_live_process_points_at_interview():
    app = {"company": "Calder & Rook", "role": "Operations Analytics Consultant",
           "status": "interview"}
    lines = prep._process_lines(RECRUITER, app)
    assert lines and "/interview Calder & Rook" in lines[0]
    assert prep._process_lines(RECRUITER, dict(app, status="applied")) == []


def test_a_fact_only_a_search_summary_gave_is_labelled():
    fact = prep._fact({"claim": "Opened an office in Leeds.", "url": "https://x.example",
                       "read": False})
    assert fact.value.endswith("[%s]" % prep.UNREAD)
    assert prep.UNREAD not in prep._fact({"claim": "Opened an office.", "url": "u"}).value
