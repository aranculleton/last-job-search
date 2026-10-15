"""What a reproduced, line-by-line audit of a real repo found. Example person and invented
names only; each test is the smallest case of one finding.
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "network"))

import ats_boards  # noqa: E402
import bridges  # noqa: E402
import check_numbers  # noqa: E402
import company_key  # noqa: E402
import compose  # noqa: E402
import doc_name  # noqa: E402
import fit_to_page  # noqa: E402
import opportunity  # noqa: E402
import prefilter  # noqa: E402
import render_application  # noqa: E402
import state  # noqa: E402
import text_screen  # noqa: E402
import throttle  # noqa: E402
import what_works as W  # noqa: E402

TODAY = "2026-10-15"


# ------------------------------------------------------------------ what it learns from

def test_an_interview_stays_an_interview_after_a_rejection():
    row = {"company": "Larkspur Retail", "role": "Planner", "status": "rejected",
           "date": "2026-08-01", "notes": "2026-08-20: phone screen with the hiring manager."}
    assert W.application_cases([row], TODAY)[0]["won"]
    advice = dict(row, notes="If this progresses, do not claim dbt in interview. Two days onsite.")
    assert not W.application_cases([advice], TODAY)[0]["won"]


def test_a_draft_is_never_credited_to_another_role():
    row = {"company": "Larkspur Retail", "role": "Senior Planner", "status": "interview"}
    other = {"company": "Larkspur Retail", "role": "Data Analyst", "abbr": "LarkspurData"}
    assert W.draft_for(row, [other]) is None
    same = dict(other, role="Senior Planner")
    assert W.draft_for(row, [other, same]) is same


def test_the_event_line_is_about_the_row_that_won():
    rows = [{"company": "Larkspur Retail", "role": "Planner", "status": "interview",
             "date": "2026-09-01"},
            {"company": "Larkspur Retail", "role": "Analyst", "status": "applied",
             "date": "2026-09-20"}]
    assert W.event_company(rows, [], "Larkspur Retail", TODAY).startswith("Interview at Larkspur")


# ------------------------------------------------------------------ the contact book

def _row(date, direction, text="x", scenario="", channel="linkedin"):
    return {"contact_id": "acme_reed", "date": date, "direction": direction,
            "channel": channel, "scenario": scenario, "summary": "", "full_text": text}


def test_a_close_dated_after_the_last_reply_is_not_reopened():
    rows = [_row("2026-09-01", "out"), _row("2026-09-09", "in")]
    c = {"contact_id": "acme_reed", "name": "Sasha Reed", "status": "closed",
         "outcome": "not answered: deprioritised by the candidate 2026-10-13"}
    assert not any(p["reason"] == "reopened" for p in state.reconcile([c], rows))
    later = rows + [_row("2026-10-14", "in")]
    assert any(p["reason"] == "reopened" for p in state.reconcile([c], later))


def test_no_action_unless_they_reply_means_exactly_that():
    c = {"contact_id": "acme_reed", "name": "Sasha Reed", "status": "",
         "next_action": "No action unless they reply."}
    waiting = [_row("2026-09-01", "out", "Hi Sasha")]
    assert [i["kind"] for i in state.owed([c], waiting, TODAY)] == []
    replied = waiting + [_row("2026-10-14", "in", "Happy to chat")]
    assert [i["kind"] for i in state.owed([c], replied, TODAY)] == ["reply"]


def test_a_catch_up_message_is_not_a_connection_request():
    rows = [_row("2026-10-15", "out", "Sorry for the slow follow-up", scenario="reply")]
    assert state.connection_requests([], rows) == set()


def test_a_hiring_manager_is_not_a_recruiter_and_plain_job_asks_are_caught():
    assert not compose.is_recruiter("Head of Planning (recruiting Senior Analysts)")
    assert compose.is_recruiter("VP, Connecting Data & AI Talent")
    for t in ("Is the Senior Analyst role still open? I'd love to apply.",
              "Would you consider me for the role?",
              "I'm interested in the Planner opening on your team."):
        assert compose.first_note_findings(t), t


# ------------------------------------------------------------------ the search

def test_a_country_code_beside_a_home_region_is_the_country(monkeypatch):
    monkeypatch.setattr(prefilter, "REGIONS", {"on": "ON", "ontario": "ON"})
    monkeypatch.setattr(prefilter, "_HOME_REGION", "ON")
    monkeypatch.setattr(prefilter, "METRO", ["northgate"])
    monkeypatch.setattr(prefilter, "NEIGHBOUR_STATES", {"ca", "tx"})
    monkeypatch.setattr(prefilter, "_CC", "ca")
    assert prefilter.location_verdict("Northgate, ON, CA")[0] == "PASS"
    assert prefilter.location_verdict("Austin, TX")[0] == "FAIL"
    assert prefilter.location_verdict("Ontario, ON")[0] == "PASS"


def test_a_refused_permit_and_private_equity_still_cut(monkeypatch):
    monkeypatch.setattr(text_screen, "PERMIT_ACCEPTED", re.compile(r"work permit|work visa", re.I))
    monkeypatch.setattr(text_screen, "ELIGIBILITY",
                        re.compile(r"citizen\w*|permanent resident\w*", re.I))
    body = " You will build planning models in SQL and Python."
    assert text_screen.eligibility_cut(
        "Open to citizens and permanent residents only, and not open to work permit holders." + body)
    assert text_screen.eligibility_cut(
        "Due to our private equity mandates, this role requires citizenship." + body)


def test_a_requirement_to_live_abroad_is_cut_and_home_is_not():
    body = " You will build planning models in SQL and Python."
    assert text_screen.residence_cut("Candidates must be based in the US or Spain." + body)
    assert not text_screen.residence_cut("You must be based in the UK or Ireland." + body)


def test_asset_and_bonus_are_preference_only_in_their_preference_sense():
    assert not text_screen.PREFERRED.search("The CFA is required for our asset management team.")
    assert not text_screen.PREFERRED.search("A degree is required for this bonus-eligible role.")
    assert text_screen.PREFERRED.search("Tableau is an asset.")


def test_old_exclusions_the_rules_now_only_rank_are_released():
    for reason in ("knockout at triage, blocker 2 (years bar above 5): 8+ years",
                   "free text screen: stated range tops out at 52,000",
                   "blocker 1: Master's degree is explicitly required"):
        assert throttle.is_stale_exclusion(reason), reason
    assert not throttle.is_stale_exclusion("eligibility gate: citizenship stated as a condition")


def test_a_live_interview_keeps_holding_its_employer():
    old = {"company": "Acme", "role": "Planner", "status": "interview", "date": "2026-06-01"}
    assert not throttle.is_silent(old)
    assert throttle.is_silent(dict(old, status="applied"))


def test_a_role_already_applied_to_does_not_come_back_once_closed():
    row = {"title": "Senior Planner", "company": "Acme", "url": "https://example.com/j/1",
           "priority": 80, "fit": 80}
    closed = {"acme": [{"company": "Acme", "role": "Senior Planner", "status": "no_response",
                        "date": "2026-08-01"}]}
    kept, skipped = throttle.throttle([row], {}, {}, {}, TODAY, closed=closed)
    assert not kept and skipped[0]["skip_reason"].startswith("already applied to this role")


def test_a_loan_size_is_not_the_pay_band():
    body = ("You will price unsecured personal loans of up to 50,000 for customers. " * 3
            + "You will build credit risk models in SQL and Python, work with the risk team, "
              "present to senior stakeholders and own the monitoring of model performance. " * 4)
    why = " ".join(opportunity.score({"title": "Senior Analyst, Credit Risk", "company": "Acme",
                                      "desc": body})["why"])
    assert "top of band" not in why


def test_a_short_name_in_brackets_joins_the_long_name():
    company_key.learn(["Northgate Pension Investment Board (NPIB)"])
    assert company_key.key("NPIB") == company_key.key("Northgate Pension Investment Board")
    assert company_key.key("Fernhill Freight (UK)") == company_key.key("Fernhill Freight")


def test_a_gap_asked_as_a_preference_is_never_do_not_apply():
    pref = bridges.assess("Preferred: CIPS or a degree in procurement, logistics or economics.")
    assert "never a reason not to apply" in pref[0].note
    req = bridges.assess("Required: MCIPS membership.")
    assert "never a reason not to apply" not in req[0].note


def test_lever_rows_carry_their_created_date():
    assert ats_boards._epoch_ms_date(1760000000000) == "2025-10-09"
    assert ats_boards._epoch_ms_date(None) == ""


# ------------------------------------------------------------------ the documents

def test_years_with_a_plus_and_per_cent_are_claims():
    found = [check_numbers.claim_key(m.group(1), m.group(2) or "")
             for m in check_numbers._NUM.finditer("8+ years of data; up 9 per cent")]
    assert (8.0, "year") in found and (9.0, "%") in found


def test_a_prose_field_the_letter_cannot_place_is_refused_and_not_counted():
    a = {"company": "Acme", "role": "Planner", "p1": "one two", "p2": "three",
         "lead": "four", "p4": "five", "p3": "six seven eight", "cl_bullets": []}
    assert fit_to_page.body_words(a) == 5
    try:
        render_application.check_batch([a], rows=[])
    except SystemExit as e:
        assert "p3" in str(e)
    else:
        raise AssertionError("a draft carrying p3 was rendered and p3 dropped")


def test_a_letter_that_fits_keeps_its_opening_paragraph():
    p1 = " ".join(["word"] * 50) + ". I want to bring forecasting to your planning team."
    a = {"p1": p1, "p2": "x", "p4": "y", "cl_bullets": []}
    assert not fit_to_page.trim_letter(a, 20, page_over=False)
    assert a["p1"] == p1


def test_a_filename_never_ends_on_a_minor_word():
    assert not re.search(r"(?:of|and|the)$", doc_name.suffix("Northgate Bank of Larkspur Holdings"),
                         re.I)
