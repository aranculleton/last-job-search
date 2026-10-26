"""An application, a contact, an interview and a job each go on being recorded from the page.

FUNCTIONS_SPEC.md (2026-10-25) section 4: every application that went is one record with
its draft's id, from every round and from outside the app, and "I heard back" writes what
/outcome writes (the tracker's status and a dated note, outcome.md's booked stage line or
its resolution), once; a referral is a person, a role and a process; a call booked is the
contact's, and its prep is the networking call's, never an interview pack; an interview's
due row is a prep, a thank-you or a status note, each its own work, the prep one id with
the card's; due rows and brief lines name the item they are about; a job from an earlier
search stays for two weeks, or for as long as it is kept, with why it scored; the checks a
draft got are said in plain words. Every person and employer here is invented.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import app_model  # noqa: E402
import app_state  # noqa: E402
from test_a_tick_on_the_page_is_applied_once import KESTREL, Search  # noqa: E402

THORNBURY = "app-thornbury_bank_risk_analyst"
LARKSPUR = "app-larkspur_retail_senior_supply_chain_analyst"
JUNO = "larkspur_retail_castellan"
FOLDER = ("documents", "applications", "thornbury_bank_risk_analyst_thornbury")


@pytest.fixture
def search(tmp_path):
    return Search(str(tmp_path))


def _app(search, aid):
    return next(a for a in search.model()["applications"] if a["id"] == aid)


def _outcome_md(search):
    with open(os.path.join(search.state, *FOLDER, "outcome.md"), encoding="utf-8") as fh:
        return fh.read()


# ------------------------------------------------------------------ applications


def test_every_application_that_went_is_a_record_with_its_drafts_id(search):
    apps = {a["id"]: a for a in search.model()["applications"]}
    assert set(apps) >= {THORNBURY, LARKSPUR}
    t = apps[THORNBURY]
    assert (t["status_word"], t["applied_on"]) == ("Interviewing", "2026-10-02")
    assert t["next"] == {"kind": "interview", "label": "Panel interview", "date": "2026-10-28"}
    assert [s["label"] for s in t["stages"]] == ["Phone screen", "Panel interview"]
    assert t["sent_files"] == ["Morgan_Ellis_CV_Thornbury.pdf",
                               "Morgan_Ellis_Cover_Letter_Thornbury.pdf"]
    assert "outcome.rejected" in t["heard"] and "outcome.no_response" not in t["heard"]
    # A draft never sent is not an application yet.
    assert KESTREL not in apps


def test_an_interview_booked_on_the_page_is_the_stage_line_outcome_writes(search):
    a = _app(search, LARKSPUR)
    aid = search.act("outcome.interview", LARKSPUR, rev=a["rev"],
                     value={"stage": "Phone screen", "on": "2026-10-30", "time": "14:00",
                            "with": "the recruiter"})
    got = search.apply()
    assert got["ok"] == [aid], search.receipt(aid)
    row = search.tracker_row("Larkspur Retail")
    assert row["status"] == "interview"
    assert "phone screen booked for 2026-10-30 at 14:00" in row["notes"].lower()
    folder = os.path.join(search.state, "documents", "applications")
    md = next(os.path.join(folder, d, "outcome.md") for d in os.listdir(folder)
              if d.startswith("larkspur_retail_senior"))
    # The time goes on the stage line too, where the pack, the brief and the page read it.
    assert "- [ ] Phone screen (scheduled 2026-10-30 14:00, with the recruiter)" in open(
        md, encoding="utf-8").read()
    assert _app(search, LARKSPUR)["next"] == {"kind": "interview", "label": "Phone screen",
                                              "date": "2026-10-30"}
    # The same booking again, from another device: nothing changes.
    a = _app(search, LARKSPUR)
    again = search.act("outcome.interview", LARKSPUR, rev=a["rev"],
                       value={"stage": "Phone screen", "on": "2026-10-30"})
    search.written_back()
    assert search.apply()["ok"] == [again]
    assert search.receipt(again)["note"] == "Already recorded."
    assert open(md, encoding="utf-8").read().count("- [ ] Phone screen") == 1


def test_a_rejection_closes_it_and_undo_puts_back_the_row_and_its_outcome(search):
    before_md = _outcome_md(search)
    before = search.tracker_row("Thornbury Bank")
    a = _app(search, THORNBURY)
    aid = search.act("outcome.rejected", THORNBURY, value="not taken forward", rev=a["rev"])
    assert search.apply()["ok"] == [aid], search.receipt(aid)
    row = search.tracker_row("Thornbury Bank")
    assert row["status"] == "rejected" and "rejected, not taken forward (page)" in row["notes"]
    md = _outcome_md(search)
    assert "**Status:** rejected" in md and "**Date resolved:** 2026-10-25" in md
    assert "- [x] Phone screen (2026-10-15, with the recruiter)" in md   # history kept
    assert not _app(search, THORNBURY)["live"]
    search.written_back()
    back = search.act("undo", None, value={"undoes": aid})
    assert search.apply()["ok"] == [back]
    assert search.tracker_row("Thornbury Bank")["status"] == before["status"]
    assert search.tracker_row("Thornbury Bank")["notes"] == before["notes"]
    assert _outcome_md(search) == before_md


def test_an_offer_ticks_its_line_and_an_unsent_draft_has_no_outcome(search):
    a = _app(search, THORNBURY)
    aid = search.act("outcome.offer", THORNBURY, rev=a["rev"])
    assert search.apply()["ok"] == [aid]
    assert "- [x] Offer received (2026-10-25)" in _outcome_md(search)
    assert search.tracker_row("Thornbury Bank")["status"] == "offer"
    item = search.item(KESTREL)
    bad = search.act("outcome.rejected", KESTREL, rev=item["rev"])
    search.written_back()
    assert search.apply()["conflict"] == [bad]


# ------------------------------------------------------------------ contacts, calls, referrals


WREN = "fernhill_freight_halloway"


def test_a_call_booked_is_the_contacts_and_its_prep_is_the_calls(search):
    person = next(p for p in search.model()["people"] if p["id"] == WREN)
    aid = search.act("person.call_booked", WREN, value={"on": "2026-10-30", "time": "12:30"},
                     rev=person["rev"])
    assert search.apply()["ok"] == [aid], search.receipt(aid)
    after = next(p for p in search.model()["people"] if p["id"] == WREN)
    assert after["status"] == "call_booked" and after["status_word"] == "Call booked"
    assert after["call"] == {"day": "2026-10-30", "prep": None}
    assert after["owed"] == {"label": "Prepare for the call", "kind": "prep",
                             "id": f"prep~call~{WREN}", "args": {"contact": WREN, "call": True}}
    # A call booked with someone whose reply is owed is still booked on their row.
    juno = next(p for p in search.model()["people"] if p["id"] == JUNO)
    search.written_back()
    aid = search.act("person.call_booked", JUNO, value="2026-10-31", rev=juno["rev"])
    assert search.apply()["ok"] == [aid]
    juno = next(p for p in search.model()["people"] if p["id"] == JUNO)
    assert juno["status"] == "replied_needs_response" and juno["call"]["day"] == "2026-10-31"


def _held(model, company):
    return [a for item in model["ready"] if item["company"] == company
            for a in item["alerts"] if "forward" in a["text"] + a["why"]]


def test_a_referral_agreed_links_a_person_and_a_role_and_its_end_lifts_the_hold(search):
    person = next(p for p in search.model()["people"] if p["id"] == WREN)
    aid = search.act("referral.agreed", WREN, value="Operations Analyst", rev=person["rev"])
    assert search.apply()["ok"] == [aid], search.receipt(aid)
    m = search.model()
    (ref,) = m["referrals"]
    assert (ref["contact"], ref["first_name"], ref["company"]) == (WREN, "Wren",
                                                                  "Fernhill Freight")
    assert ref["stage"] in ("agreed", "put_forward")
    assert _held(m, "Fernhill Freight"), [i["alerts"] for i in m["ready"]]
    search.written_back()
    end = search.act("referral.ended", ref["id"], value="rejected", rev=ref["rev"])
    assert search.apply()["ok"] == [end], search.receipt(end)
    m = search.model()
    assert m["referrals"] == [] and not _held(m, "Fernhill Freight")


# ------------------------------------------------------------------ due rows


def test_an_interviews_due_row_is_a_prep_with_the_cards_own_work_id(search):
    path = os.path.join(search.state, *FOLDER, "interview_prep.md")
    os.remove(path)
    md = os.path.join(search.state, *FOLDER, "outcome.md")
    with open(md, "w", encoding="utf-8") as fh:
        fh.write("# Outcome\n\n## Interview stages reached\n\n"
                 "- [x] Phone screen (2026-10-15, with the recruiter)\n"
                 "- [ ] Panel interview (scheduled 2026-10-27, with the head of risk)\n")
    m = search.model()
    row = next(d for d in m["due"] if d["kind"] == "interview")
    assert row["sub"] == "prep" and row["item"] == "int-thornbury_bank_risk_analyst"
    assert row["work"] == {"kind": "prep", "id": "prep~int-thornbury_bank_risk_analyst",
                           "args": {"interview": "int-thornbury_bank_risk_analyst"}}


def test_a_thank_you_owed_is_a_follow_up_never_a_prep(search):
    md = os.path.join(search.state, *FOLDER, "outcome.md")
    with open(md, "w", encoding="utf-8") as fh:
        fh.write("# Outcome\n\n## Interview stages reached\n\n"
                 "- [x] Phone screen (2026-10-24, with the recruiter)\n")
    rows = [d for d in search.model()["due"] if d["kind"] == "interview"]
    if rows:
        (row,) = rows
        assert row["sub"] in ("thank_you", "status_note")
        assert row["work"]["kind"] == "follow_up"
        assert row["work"]["args"]["kind"] == row["sub"]


def test_every_due_row_names_its_item_and_the_work_it_queues(search):
    for d in search.model()["due"]:
        assert d["item"], d
        assert d["work"]["kind"] in ("reply", "follow_up", "prep", "resume_for_contact"), d
        assert d["work"]["id"].startswith(d["work"]["kind"] + "~")


def test_not_today_moves_a_contacts_due_day(search):
    row = next(d for d in search.model()["due"] if d["item"] == "fernhill_freight_halloway")
    assert row["snooze"] == {"action": "due.snooze", "label": "Not today"}
    aid = search.act("due.snooze", row["id"], value="2026-10-28", rev=row["rev"])
    assert search.apply()["ok"] == [aid], search.receipt(aid)
    with open(os.path.join(search.state, "network_contacts.csv"), encoding="utf-8") as fh:
        import csv
        c = next(r for r in csv.DictReader(fh) if r["contact_id"] == "fernhill_freight_halloway")
    assert c["next_action_due"] == "2026-10-28"


def test_a_brief_line_opens_what_it_is_about(search):
    items = search.model()["brief"]["items"]
    assert items[0] == {"text": "2 replies owed", "item": None, "section": "due"}
    assert items[1] == {"text": "Kestrel Mutual is hiring analysts", "item": KESTREL,
                        "section": "ready"}


# ------------------------------------------------------------------ jobs from earlier searches


def _round(search, name, rows):
    path = os.path.join(search.state, "documents", "rounds", f"{name}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(rows, fh)
    return path


def test_a_job_from_an_earlier_search_stays_two_weeks_or_while_kept(search):
    rounds = os.path.join(search.state, "documents", "rounds")
    os.rename(os.path.join(rounds, "r9.json"), os.path.join(rounds, "r8.json"))
    # The earlier round was made the day before the sample's clock (2026-10-25), whatever
    # day the test runs: its age is read from the file's time.
    import datetime as dt
    made = dt.datetime(2026, 10, 24, 12, 0, tzinfo=dt.timezone.utc).timestamp()
    os.utime(os.path.join(rounds, "r8.json"), (made, made))
    _round(search, "r9", [{"fit": 70, "title": "Planner", "company": "Wren Health",
                           "url": "https://jobs.example/wren/planner",
                           "fit_why": ["+12 SQL and Python asked and held",
                                       "-6 stated 5+ years against 4 held"]}])
    m = search.model()
    rows = m["jobs"]["rows"]
    assert rows[0]["why"] == ["SQL and Python asked and held", "Stated 5+ years against 4 held"]
    earlier = [r for r in rows if r["from_round"] == "r8"]
    assert earlier and all("From an earlier search." in r["notes"] for r in earlier)
    assert "more from earlier searches" in m["jobs"]["summary"]
    # Two weeks on, only a kept one stays.
    brindle = next(r for r in earlier if r["company"] == "Brindle Hart Logistics")
    aid = search.act("job.keep", brindle["id"], rev=brindle["rev"])
    assert search.apply()["ok"] == [aid], search.receipt(aid)
    old = os.path.join(rounds, "r8.json")
    os.utime(old, (1700000000, 1700000000))
    rows = search.model()["jobs"]["rows"]
    assert [r["company"] for r in rows if r["from_round"]] == ["Brindle Hart Logistics"]
    assert next(r for r in rows if r["from_round"])["kept"] is True


# ------------------------------------------------------------------ the checks a draft got


def test_the_checks_a_draft_got_are_said_in_plain_words(search):
    folder = os.path.join(search.state, "documents", "applications",
                          "kestrel_mutual_claims_forecasting_analyst_kestrel")
    with open(os.path.join(folder, "verify.json"), "w", encoding="utf-8") as fh:
        json.dump({"at": "2026-10-25T09:00:00Z", "flags": [], "pages": {"resume": 1,
                                                                         "letter": 1}}, fh)
    checks = search.item(KESTREL)["checks"]
    assert checks["verify"]["passed"] and checks["verify"]["items"][0]["ok"]
    with open(os.path.join(folder, "verify.json"), "w", encoding="utf-8") as fh:
        json.dump({"at": "2026-10-25T09:00:00Z", "flags": ["CHRONO", "SHARED_PHRASE(2)"],
                   "pages": {"resume": 1, "letter": 1}}, fh)
    checks = search.item(KESTREL)["checks"]
    assert not checks["passed"]
    assert [i["said"] for i in checks["verify"]["items"]] == ["the jobs are not in date order",
                                                               "two bullets share a phrase"]
    assert checks["line"] == "A check found something: the jobs are not in date order"


def test_the_model_still_keeps_the_contract(search):
    assert app_model.check(search.model()) == []
    _ = app_state
