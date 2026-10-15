"""It learns what works from what happened, with nobody having to say so.

Every result that matters was already on record: the tracker knew which
applications reached an interview, the message log knew which messages drew a
reply. Nothing read it back, so a person kept having to ask for "a message like the
one that got an answer" and "a resume like the one that got the interview".
`tools/what_works.py` reads it back by counting, with no model call and no state of
its own. These pin what it counts, what it refuses to conclude from too little,
and the one thing it changes by itself: the lift a winning resume's bullets get.
"""
from __future__ import annotations

import csv
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "network"))

import allocate  # noqa: E402
import what_works as W  # noqa: E402

TODAY = "2026-10-15"
CONTACTS = [
    {"contact_id": "larkspur_retail_castellan", "name": "Juno Castellan",
     "company": "Larkspur Retail", "route": "alumni_school", "tier": "1"},
    {"contact_id": "fernhill_freight_halloway", "name": "Wren Halloway",
     "company": "Fernhill Freight", "route": "cold", "tier": "2"},
    {"contact_id": "quayside_foods_reed", "name": "Sasha Reed",
     "company": "Quayside Foods", "route": "cold", "tier": "2"},
]
NOTE = "Hi Juno, we were both at Leeds. How is the analytics team set up at Larkspur?"


def _row(cid, date, direction, text="", channel="linkedin", scenario=""):
    return {"contact_id": cid, "date": date, "direction": direction, "channel": channel,
            "scenario": scenario, "summary": "", "full_text": text}


def test_the_reply_is_credited_to_the_message_it_answered():
    threads = [
        _row("larkspur_retail_castellan", "2026-09-01", "out", NOTE),
        _row("larkspur_retail_castellan", "2026-09-09", "out", "Hi Juno, a quick nudge?"),
        _row("larkspur_retail_castellan", "2026-09-10", "in", "Happy to talk."),
    ]
    cases = W.message_cases(CONTACTS, threads, TODAY)
    assert [(c["attempt"], c["won"]) for c in cases] == [("opener", False), ("follow-up", True)]
    assert cases[1]["days_to_reply"] == 1


def test_a_bare_connection_request_is_not_the_opener():
    threads = [
        _row("fernhill_freight_halloway", "2026-09-01", "out", channel="connection_request"),
        _row("fernhill_freight_halloway", "2026-09-03", "in", scenario="accepted_no_reply"),
        _row("fernhill_freight_halloway", "2026-09-04", "out", "Hi Wren, thanks for connecting."),
        _row("fernhill_freight_halloway", "2026-09-05", "in", "Glad to."),
    ]
    cases = W.message_cases(CONTACTS, threads, TODAY)
    assert len(cases) == 1 and cases[0]["attempt"] == "opener" and cases[0]["won"]


def test_a_message_still_inside_its_wait_is_not_counted_as_a_failure():
    recent = [_row("quayside_foods_reed", "2026-10-10", "out", "Hi Sasha, a question?")]
    assert W.message_cases(CONTACTS, recent, TODAY) == []
    old = [_row("quayside_foods_reed", "2026-09-10", "out", "Hi Sasha, a question?")]
    assert [c["won"] for c in W.message_cases(CONTACTS, old, TODAY)] == [False]


def test_nothing_is_concluded_from_a_handful():
    assert not W.clear(2, 7, 0, 7)                  # groups under MIN_GROUP
    assert not W.clear(3, 10, 2, 10)                # a gap that could be chance
    assert W.clear(6, 8, 1, 8)                      # a gap that is unlikely to be


def test_the_brief_shows_the_closest_winning_message_and_its_shape():
    threads = [_row("larkspur_retail_castellan", "2026-09-01", "out", NOTE),
               _row("larkspur_retail_castellan", "2026-09-01", "in", "Sure."),
               _row("fernhill_freight_halloway", "2026-09-02", "out", "Hi Wren, a long note " * 20),
               _row("fernhill_freight_halloway", "2026-09-04", "in", "Thanks.")]
    out = W.brief_messages(CONTACTS, threads, TODAY, route="alumni_school", channel="connection")
    first = [ln for ln in out.splitlines() if ln.startswith("  ")][0]
    assert "alumni route" in first and "answered the same day" in first and NOTE in first
    assert "No difference is clear yet" in out
    assert all(len(ln) < 700 for ln in out.splitlines())    # exemplars are clipped


def test_a_clear_difference_is_reported_with_both_counts():
    contacts, threads = [], []
    for i in range(10):
        for route, replied in (("alumni_school", i < 7), ("cold", i < 1)):
            cid = "%s_%d" % (route, i)
            contacts.append({"contact_id": cid, "name": cid, "route": route})
            threads.append(_row(cid, "2026-08-01", "out", "Hi, a question?"))
            if replied:
                threads.append(_row(cid, "2026-08-03", "in", "Yes."))
    out = W.brief_messages(contacts, threads, TODAY)
    assert "By route: alumni answered 7 of 10 (70%); cold answered 1 of 10 (10%)." in out


TRACKER = [
    {"date": "2026-08-01", "company": "Larkspur Retail", "role": "Senior Supply Chain Analyst",
     "status": "interview", "fit_rating": "81", "channel": "referral",
     "cv_file": "cv/Morgan_Ellis_CV_Larkspur.tex"},
    {"date": "2026-08-02", "company": "Quayside Foods", "role": "Demand Planning Analyst",
     "status": "rejected", "fit_rating": "64", "channel": "company site"},
    {"date": "2026-08-03", "company": "Fernhill Freight", "role": "Operations Analyst",
     "status": "applied", "fit_rating": "70"},                       # 73 days quiet
    {"date": "2026-10-10", "company": "Acme", "role": "Analyst", "status": "applied"},
    {"date": "2026-10-11", "company": "Acme", "role": "Planner", "status": "drafted"},
]


def test_applications_count_as_won_lost_or_not_yet():
    cases = {c["company"]: c["won"] for c in W.application_cases(TRACKER, TODAY)}
    assert cases == {"Larkspur Retail": True, "Quayside Foods": False, "Fernhill Freight": False}


def _state(tmp_path, bullets=("BH_FORECAST", "BH_ROUTING")):
    with open(tmp_path / "job_search_tracker.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=sorted({k for r in TRACKER for k in r}))
        w.writeheader()
        w.writerows(TRACKER)
    d = tmp_path / "documents" / "applications" / "larkspur_senior_supply_chain_analyst_larkspur"
    d.mkdir(parents=True)
    draft = {"company": "Larkspur Retail", "role": "Senior Supply Chain Analyst",
             "summary": "Supply-chain analyst who turns forecasts into decisions.",
             "jobs": [{"employer": "Brindle & Hart Logistics", "bullets": list(bullets)}]}
    (d / "draft.json").write_text(json.dumps([draft]), encoding="utf-8")
    return str(tmp_path)


def test_the_documents_brief_names_what_the_winning_resume_used(tmp_path):
    root = _state(tmp_path)
    out = W.brief_documents(TRACKER, W.drafts(root), TODAY)
    assert "Reached an interview: 1 of 3 (33%)" in out
    assert "Supply-chain analyst who turns forecasts into decisions." in out
    assert "bullets: BH_FORECAST, BH_ROUTING" in out


def test_a_winning_resume_lifts_its_bullets_by_a_bounded_amount(tmp_path, monkeypatch):
    plain = allocate.bullet_scores("forecasting and routing")
    monkeypatch.setenv("LJS_STATE", _state(tmp_path))
    W._bullet_wins.cache_clear()
    try:
        assert W.bullet_wins() == {"BH_FORECAST": 1, "BH_ROUTING": 1}
        lifted = allocate.bullet_scores("forecasting and routing")
    finally:
        W._bullet_wins.cache_clear()
    assert lifted["BH_FORECAST"] - plain["BH_FORECAST"] == allocate.WIN_BONUS
    assert lifted["BH_FORECAST_SHORT"] == plain["BH_FORECAST_SHORT"]
    assert allocate.WIN_BONUS * allocate.WIN_CAP < allocate.THEME_BONUS


def test_no_results_changes_nothing_the_allocator_does():
    W._bullet_wins.cache_clear()
    assert W.bullet_wins() == {}                       # the example person has no wins
    assert allocate.bullet_scores("forecasting")["BH_FORECAST"] == (
        allocate.WEIGHT["BH_FORECAST"]
        + allocate.THEME_BONUS * sum(allocate.theme_scores("forecasting").get(t, 0.0)
                                     for t in allocate.THEMES["BH_FORECAST"]))


def test_the_event_line_says_what_this_result_had(tmp_path):
    root = _state(tmp_path)
    line = W.event_company(TRACKER, W.drafts(root), "Larkspur Retail Ltd", TODAY)
    assert line.startswith("Interview at Larkspur Retail (Senior Supply Chain Analyst), "
                           "from a fit 75+, referral application.")
    assert "2 bullets it used get a small lift" in line
    assert W.event_company(TRACKER, [], "Quayside Foods", TODAY) == "Interviews so far: 1 of 3 (33%)."
    threads = [_row("larkspur_retail_castellan", "2026-09-01", "out", NOTE),
               _row("larkspur_retail_castellan", "2026-09-03", "in", "Sure.")]
    said = W.event_contact(CONTACTS, threads, "larkspur_retail_castellan", TODAY)
    assert said.startswith("Juno Castellan answered your first message of 2026-09-01 after 2 days")


def test_it_runs_on_the_example_person(capsys):
    for area in ("messages", "documents", "search"):
        assert W.main(["brief", area, "--today", TODAY]) == 0
    assert "First messages answered" in capsys.readouterr().out
