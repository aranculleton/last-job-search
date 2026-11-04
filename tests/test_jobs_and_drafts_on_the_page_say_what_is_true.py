"""Jobs, Drafts, Applied and the Brief on the page say what is true, once, in plain words.

The 3 November audit drove a real page: no card said when a job was posted or why it scored
what it did; a closed posting offered a referral ask and "I have applied"; "Also at" listed
the note to someone and then them again, and a draft's own role as somewhere else; "Apply
on their site" opened LinkedIn; "[check the tracker row]" sat behind a Copy button; the
resume the person must never send was one tap away; Applied said "66 applied" beside the
Brief's 54 and Drafts' 52, and "with an interview booked" of interviews with no day; a
follow-up two days late said "on Sun 1 Nov"; "usually 0" sat under a week of 51; Progress
said "Applied Applied"; a stage name led a heading in lower case; and news five days old
said only "Gathered". Each test taps the page as the person did. Every person and employer
is invented (tests/fixtures/app_model_sample.json).
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import test_the_page_journeys as journeys  # noqa: E402
from test_the_page_journeys import PHONE, WIDE, _go, _sample  # noqa: E402


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


T = "2026-10-25T09:00:00Z"


def _row(m, rid):
    return next(r for r in m["jobs"]["rows"] if r["id"] == rid)


def test_a_job_card_says_when_it_was_posted_and_why_it_scored_what_it_did(run, tmp_path):
    m = _sample()
    _row(m, "r12-1")["why"] = ["Matches your skills: SQL, Python", "Asks for 5 years in banking"]
    card = '[data-item="r12-1"]'
    got = _go(run, tmp_path, [
        {"hash": "jobs", "read": card + " .facts"},
        {"more": "r12-1", "read": card},
    ], PHONE, model=m, clock=T)
    assert "Posted 5 days ago" in got["after"][0]["text"], got["after"][0]["text"]
    assert "Why 84: Matches your skills: SQL, Python. Asks for 5 years in banking." in got["after"][1]["text"]


def test_a_closed_posting_offers_only_setting_it_aside(run, tmp_path):
    m = _sample()
    r = _row(m, "r12-5")
    r["warm"] = "Noor at Brackenridge Advisory has replied to you: ask them first."
    r["warm_contact"] = "brackenridge_advisory_noor"
    card = '[data-item="r12-5"]'
    got = _go(run, tmp_path, [{"hash": "jobs", "more": "r12-5", "read": card}], PHONE, model=m, clock=T)
    text = got["after"][0]["text"]
    assert "Set it aside" in text
    for gone in ("for a referral", "I have applied", "Find people at", "ask them first"):
        assert gone not in text, (gone, text)


def test_also_at_names_each_person_once_and_never_the_cards_own_role(run, tmp_path):
    m = _sample()
    r = _row(m, "r12-5")
    r["apply"] = dict(r["apply"], status="open")
    r["alerts"] = []
    got = _go(run, tmp_path, [{"hash": "jobs", "more": "r12-5", "read": '[data-item="r12-5"] .related'}],
              PHONE, model=m, clock=T)
    text = got["after"][0]["text"]
    assert "the note to Noor" in text and text.count("Noor") == 1, text
    d = _sample()
    a = next(x for x in d["ready"] if x["id"] == "app-ellerwick-insight")
    got = _go(run, tmp_path, [{"hash": "drafts", "more": a["id"], "read": '[data-item="app-ellerwick-insight"]'}],
              PHONE, model=d, clock=T)
    assert "the role: Research Analyst" not in got["after"][0]["text"], "a draft's own role is not elsewhere"


def test_a_draft_says_where_its_apply_link_goes_and_leaves_a_gap_to_the_person(run, tmp_path):
    m = _sample()
    a = next(x for x in m["ready"] if x["id"] == "app-ellerwick-insight")
    a["apply"] = {"url": "https://www.linkedin.com/jobs/view/4000000999/", "status": "not_checked", "kind": "linkedin"}
    a["screening"].append({"q": "How did you hear about this role?", "a": "", "fill": True})
    card = '[data-item="app-ellerwick-insight"]'
    got = _go(run, tmp_path, [
        {"hash": "drafts", "read": card},
        {"more": "app-ellerwick-insight",
         "eval": "document.querySelector('[data-k=\"det:copy:app-ellerwick-insight\"]').open = true"},
        {"read": card, "count": card + ' [data-k^="copy:qa-"]'},
    ], PHONE, model=m, clock=T)
    assert "Apply on LinkedIn" in got["after"][0]["text"] and "Apply on their site" not in got["after"][0]["text"]
    opened = got["after"][2]
    assert "How did you hear about this role?" in opened["text"]
    assert "Yours to answer" in opened["text"]
    assert opened["count"] == 3, "a Copy for each answer Claude wrote, none for the gap"


def test_the_resume_that_breaks_the_persons_rules_offers_only_a_fresh_one(run, tmp_path):
    m = _sample()
    m["resume"]["breaks"] = ["it has dashes your documents never use"]
    m["resume"]["asset"] = None
    card = '[data-item="resume-current"], [data-item="resume-general"]'
    got = _go(run, tmp_path, [{"hash": "drafts", "read": card}], PHONE, model=m, clock=T)
    text = got["after"][0]["text"]
    assert "Not to send" in text and "Make a fresh one" in text and "dashes your documents never use" in text
    assert "Get it" not in text and "Get this one anyway" not in text


def test_applied_says_what_it_counts_and_flags_a_late_follow_up(run, tmp_path):
    m = _sample()
    for a in m["applications"]:
        if a["id"] == "app-fernhill-ops":
            a["next"] = {"kind": "follow_up", "label": "Follow up", "date": "2026-10-23"}
    for i in m["interviews"]:
        if i["id"] == "int-harbourline-risk":
            i["when"] = None
    got = _go(run, tmp_path, [
        {"hash": "jobs", "click": "Applied", "read": "#main"},
    ], PHONE, model=m, clock=T, seed={"pref:jobs:tab": "applied"})
    text = got["after"][0]["text"]
    assert " still open" in text and " applied," not in text.split("\n")[0], text[:300]
    assert "1 interview with no day yet" in text, text[:300]
    assert "Next: follow up, 2 days late" in text and "Follow-up due" in text


def test_the_weeks_say_their_average_and_progress_says_applied_once(run, tmp_path):
    m = _sample()
    m["done"]["weeks"] = [{"week": "2026-W%02d" % w, "applied": n, "replies": 0}
                          for w, n in zip(range(36, 44), (10, 0, 0, 0, 0, 51, 3, 0))]
    got = _go(run, tmp_path, [
        {"hash": "brief", "read": '[data-k="spark-cap"]'},
        {"hash2": "progress", "read": "#main"},
    ], PHONE, model=m, clock=T)
    cap = got["after"][0]["text"]
    assert "about 8 a week on average" in cap and "usually" not in cap, cap
    assert "Applied Applied" not in got["after"][1]["text"]


def test_a_stage_name_leads_its_heading_with_a_capital(run, tmp_path):
    m = _sample()
    for i in m["interviews"]:
        if i["id"] == "int-copperleaf-payments":
            i["next_stage"] = "initial round"
    got = _go(run, tmp_path, [{"hash": "interviews", "click": "Interviews", "exact": True, "read": "#main"}],
              WIDE, model=m, clock=T)
    assert "Initial round with Copperleaf Pay" in got["after"][0]["text"]
    assert "initial round with Copperleaf Pay" not in got["after"][0]["text"]


def test_news_from_an_earlier_brief_says_todays_search_found_nothing_newer(run, tmp_path):
    m = _sample()
    m["brief"]["news_date"] = "2026-10-20"
    m["brief"]["news_searched"] = "2026-10-25"
    got = _go(run, tmp_path, [{"hash": "brief", "read": '[data-k="news-asof"]'}], WIDE, model=m, clock=T)
    assert got["after"][0]["text"].startswith("Searched this morning: nothing newer than these, from"), got["after"][0]["text"]


def test_a_job_put_in_the_bin_leaves_and_set_aside_counts_it(run, tmp_path):
    """After "Not this one" the card stayed in place, Found dropped and "set aside" did not
    rise (audit 20)."""
    got = _go(run, tmp_path, [
        {"hash": "jobs", "read": "#main"},
        {"click": "Not for me: Harbourline Bank, Pricing Analyst"},
        {"click": "Not this one", "within": "dialog", "read": "#main", "count": '#main [data-item="r12-1"]'},
    ], PHONE, clock=T)
    before, after = got["after"][0]["text"], got["after"][2]
    assert "1 set aside" in before and after["count"] == 0
    assert "2 set aside" in after["text"], after["text"][:400]


def test_one_way_to_each_thing_on_jobs_and_the_brief(run, tmp_path):
    """The audit's "too many buttons": a warm route asked about twice on one card, "Find jobs"
    and "Search again" for one search, and "I have applied" on a drafted role's Found card
    as well as on its draft."""
    m = _sample()
    r = _row(m, "r12-1")
    r["warm"] = "Bea at Harbourline Bank has replied to you: ask them first."
    r["warm_contact"] = "harbourline_bank_bea"
    r["related"] = dict(r.get("related") or {}, people=["harbourline_bank_bea"])
    r["suggest"] = {"level": 2, "id": "sg-warm-r12-1-a1", "kind": "warm",
                    "text": "Bea at Harbourline Bank replied to you: ask Bea about this role before applying.",
                    "why": "A reply is what makes a route warm.",
                    "action": {"type": "work", "label": "Write to Bea", "kind": "reply", "id": "reply~harbourline_bank_bea",
                               "title": "Write to Bea at Harbourline Bank", "args": {"contact": "harbourline_bank_bea"}},
                    "cost": {"state": 2, "label": "Some Claude"}, "since": "2026-10-25", "rev": "s9"}
    got = _go(run, tmp_path, [
        {"hash": "jobs", "more": "r12-1", "read": '[data-item="r12-1"]'},
        {"more": "r12-4", "read": '[data-item="r12-4"]'},
        {"hash": "brief", "read": "#main .bp-jobs"},
    ], WIDE, model=m, clock=T)
    card = got["after"][0]
    assert "Write to Bea" in card["text"] and "for a referral" not in card["text"], card["text"]
    drafted = got["after"][1]["text"]
    assert "See the draft" in drafted and "I have applied" not in drafted, "one I have applied: on the draft"
    assert "Search again" not in got["after"][2]["text"] and "Find jobs" in got["after"][2]["text"]
