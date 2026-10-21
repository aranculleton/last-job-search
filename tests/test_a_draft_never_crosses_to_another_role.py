"""Nothing written for one application is read as another's.

Every round file is named by the company's slug, and nothing compared a file with the pick
it sat under:

- A draft left from an earlier pick at the same employer (its claims role) was audited
  against the next pick's posting (its pricing role) and assembled under the new file name.
- An outreach note body left from an earlier draft was merged into whatever was drafted
  next for the slug.
- A draft edited after its audit was assembled as the audited copy, silently.
- A model audit carrying no md5 was applied to any later draft.
- Recording a re-application (a role applied to before, drafted again under new file
  names) overwrote the sent application's row: its documents pointed at files the employer
  never saw.
- A draft for "Data Analyst" was still read as the "Senior Data Analyst" staged after it at
  the same employer, because one title's words sat inside the other's, and when another
  employer had been staged in between (picks.json no longer named the first pick) nothing
  was set aside at all.

Every employer, role and posting here is invented.
"""
from __future__ import annotations

import copy
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import csv_store  # noqa: E402
import docpaths  # noqa: E402
import draft_audit  # noqa: E402
import draft_pack  # noqa: E402
import record_drafts  # noqa: E402
import stage_picks  # noqa: E402
from test_one_drafting_call_per_posting import FIXTURE, SLUG, make_round, store_pages  # noqa: E402

PRICING = ("Kestrel Mutual is hiring a Pricing Analyst in Manchester to set motor premiums. "
           "You will build price elasticity models in Python and SQL and report in Power BI. "
           "This is a permanent, full-time role. Hybrid, two days a week in our Manchester office.")
SHORTLIST = [{"company": "Kestrel Mutual", "title": "Claims Forecasting Analyst",
              "location": "Manchester, UK", "url": "https://jobs.example/1",
              "desc": FIXTURE["posting"], "fit": 80},
             {"company": "Kestrel Mutual", "title": "Pricing Analyst", "location": "Manchester, UK",
              "url": "https://jobs.example/2", "desc": PRICING, "fit": 78}]


def _model_pass(rd, slug=SLUG):
    d = json.loads((rd / f"draft_{slug}.json").read_text(encoding="utf-8"))
    (rd / f"model_audit_{slug}.json").write_text(json.dumps({
        "verdict": "pass", "draft": d, "changes": [], "residual_risks": [], "rulings": [],
        "audited_md5": draft_audit.md5(d), "rules_hash": draft_pack.rules_hash()}),
        encoding="utf-8")


def test_a_draft_left_by_another_role_at_the_employer_is_never_assembled_for_this_one(tmp_path):
    store_pages()
    rd = tmp_path / "r1"
    [p] = stage_picks.stage(str(rd), ["1"], rows=[], shortlist=SHORTLIST, fetch=lambda r: {},
                            root=str(tmp_path))
    stage_picks.consent(str(rd), p["slug"], no=list(p["ask_first"]))
    (rd / f"research_{p['slug']}.json").write_text(json.dumps(FIXTURE["research"]), encoding="utf-8")
    d = dict(copy.deepcopy(FIXTURE["draft"]), pack_hash=draft_pack.rules_hash())
    (rd / f"draft_{p['slug']}.json").write_text(json.dumps(d), encoding="utf-8")
    _model_pass(rd, p["slug"])
    assert [r["verdict"] for r in stage_picks.audit(str(rd))] == ["pass"]
    # Later the pricing role is staged in the same directory, under the same slug.
    [q] = stage_picks.stage(str(rd), ["2"], rows=[], shortlist=SHORTLIST, fetch=lambda r: {},
                            root=str(tmp_path))
    assert q["slug"] == p["slug"]
    # The claims role's files were set aside, not read as the pricing role's.
    assert not (rd / f"draft_{q['slug']}.json").exists()
    assert (rd / "old" / f"{q['slug']}-1" / f"draft_{q['slug']}.json").exists()
    stage_picks.consent(str(rd), q["slug"], no=list(q["ask_first"]))
    assert [r["verdict"] for r in stage_picks.audit(str(rd))] == ["missing"]
    # Even a stale draft put back by hand is refused, and never assembled.
    (rd / f"draft_{q['slug']}.json").write_text(json.dumps(d), encoding="utf-8")
    [r] = stage_picks.audit(str(rd))
    assert r["verdict"] == "stale" and "Claims Forecasting Analyst" in r["why"]
    drafts, missing, _ = stage_picks.assemble(str(rd))
    assert drafts == [] and "draft this pick again" in missing[0]


def test_staging_the_same_role_again_keeps_its_files(tmp_path):
    rd = tmp_path / "r1"
    [p] = stage_picks.stage(str(rd), ["1"], rows=[], shortlist=SHORTLIST, fetch=lambda r: {},
                            root=str(tmp_path))
    (rd / f"draft_{p['slug']}.json").write_text(json.dumps(FIXTURE["draft"]), encoding="utf-8")
    stage_picks.stage(str(rd), ["1"], rows=[], shortlist=SHORTLIST, fetch=lambda r: {},
                      root=str(tmp_path))
    assert (rd / f"draft_{p['slug']}.json").exists() and not (rd / "old").exists()


def test_a_note_written_for_another_version_of_the_draft_is_left_out(tmp_path):
    rd = make_round(tmp_path)
    body = ("At Brindle & Hart Logistics I built the weekly demand-forecasting models in Python "
            "and SQL that cut forecast error from 22% to 14% across 2,400 SKUs. Could I send you "
            "a short note on how I would start?")
    draft_audit.write_note(str(rd), SLUG, {"outreach_body": body, "claim_map": []})
    # Run 2 redrafts the letter and asks for no note.
    d = json.loads((rd / f"draft_{SLUG}.json").read_text(encoding="utf-8"))
    old, new = "Your claims handling teams staff ahead", "Claims handlers at Kestrel Mutual staff ahead"
    d["p1"] = d["p1"].replace(old, new)
    for c in d["claim_map"]:
        c["sentence"] = c["sentence"].replace(old, new)
    (rd / f"draft_{SLUG}.json").write_text(json.dumps(d), encoding="utf-8")
    _model_pass(rd)
    [r] = stage_picks.audit(str(rd))
    assert "outreach-note" in {n["rule"] for n in r["mechanical"]["notes"]}
    drafts, _, _ = stage_picks.assemble(str(rd))
    assert "outreach_body" not in drafts[0]
    # A note file written by hand, with no stamp, is no note either.
    (rd / f"outreach_{SLUG}.json").write_text(json.dumps({"outreach_body": body, "claim_map": []}),
                                              encoding="utf-8")
    stage_picks.audit(str(rd))
    drafts, _, _ = stage_picks.assemble(str(rd))
    assert "outreach_body" not in drafts[0]


def test_a_draft_edited_after_its_audit_is_held_back(tmp_path):
    rd = make_round(tmp_path)
    _model_pass(rd)
    stage_picks.audit(str(rd))
    d = json.loads((rd / f"draft_{SLUG}.json").read_text(encoding="utf-8"))
    d["p4"] = d["p4"] + " One more line nobody audited."
    (rd / f"draft_{SLUG}.json").write_text(json.dumps(d), encoding="utf-8")
    drafts, missing, _ = stage_picks.assemble(str(rd))
    assert drafts == [] and "changed since it was audited" in missing[0]


def test_a_model_audit_with_no_md5_says_nothing_about_any_draft(tmp_path):
    rd = make_round(tmp_path)
    d = json.loads((rd / f"draft_{SLUG}.json").read_text(encoding="utf-8"))
    (rd / f"model_audit_{SLUG}.json").write_text(json.dumps({
        "verdict": "fixed", "draft": dict(d, p4="An older close."), "changes": [],
        "residual_risks": [], "rulings": [], "rules_hash": draft_pack.rules_hash()}),
        encoding="utf-8")
    [r] = stage_picks.audit(str(rd))
    assert r["verdict"] == "needs_model"
    record = json.loads((rd / f"audit_{SLUG}.json").read_text(encoding="utf-8"))
    assert record["model"] is None and record["draft"]["p4"] == d["p4"]


def test_a_re_application_gets_its_own_row_and_the_sent_one_is_kept(tmp_path):
    path = str(tmp_path / "tracker.csv")
    sent = {"date": "2026-09-30", "company": "Kestrel Mutual", "role": "Claims Forecasting Analyst",
            "status": "applied", "fit_rating": "80", "notes": "r3.",
            "cv_file": docpaths.resume_rel("KestrelMutual"),
            "cover_letter_file": docpaths.letter_rel("KestrelMutual"),
            "source": "https://jobs.example/1"}
    csv_store.write_rows(path, [dict(sent)], record_drafts.HEADER)
    d = {"company": "Kestrel Mutual", "role": "Claims Forecasting Analyst",
         "abbr": "KestrelMutual_ClaimsForecasting", "notes_for_tracker": "Reposted; applying again."}
    done = record_drafts.record([d], {"KESTRELMUTUAL_CLAIMSFORECASTING": {"fit": 82,
                                                                          "url": "https://jobs.example/9"}},
                                "2026-10-21", "r9", path=path)
    assert [a for a, _ in done] == ["added"]
    rows = csv_store.read_rows(path, record_drafts.HEADER)
    assert len(rows) == 2
    assert rows[0]["cv_file"] == sent["cv_file"] and rows[0]["status"] == "applied"
    assert rows[0]["source"] == sent["source"] and rows[0]["date"] == sent["date"]
    assert rows[1]["status"] == "drafted" and "ClaimsForecasting" in rows[1]["cv_file"]
    # An unsent draft of the same role is still refreshed in place, as before.
    again = record_drafts.record([d], {"KESTRELMUTUAL_CLAIMSFORECASTING": {"fit": 83}},
                                 "2026-10-22", "r9", path=path)
    assert [a for a, _ in again] == ["updated"]
    assert len(csv_store.read_rows(path, record_drafts.HEADER)) == 2


def _kestrel(title, n):
    return {"company": "Kestrel Mutual", "title": title, "location": "Manchester, UK",
            "url": f"https://jobs.example/{n}", "portal": "pasted", "desc": PRICING, "fit": 78}


def test_a_role_is_this_picks_only_when_its_words_are_the_same():
    km = {"company": "Kestrel Mutual"}
    for drafted, pick in [("Data Analyst", "Senior Data Analyst"),
                          ("Senior Data Analyst", "Data Analyst"),
                          ("Data Analyst", "Data Analyst, Fraud Strategy"),
                          ("Pricing Analyst", "Lead Pricing Analyst")]:
        assert draft_audit.other_role(dict(km, role=drafted), dict(km, role=pick)), (drafted, pick)
    # The same role, written without its requisition noise, in another order or spelling.
    for drafted, pick in [("Data Analyst", "Data Analyst (m/w/d)"),
                          ("Senior Data Analyst", "Senior Data Analyst - REQ-2026-0412"),
                          ("Data Analyst", "Data Analyst (Fixed Term, 12 months) - REQ1234"),
                          ("Supply Chain Data Analyst", "Data Analyst - Supply Chain"),
                          ("Pricing and Underwriting Analyst", "Analyst, Pricing & Underwriting"),
                          ("Senior Data Analyst", "Sr. Data Analyst"),
                          ("Data Analyst, maternity cover", "Data Analyst (Maternity Cover)")]:
        assert draft_audit.other_role(dict(km, role=drafted), dict(km, role=pick)) == "", \
            (drafted, pick)


def test_an_earlier_role_is_set_aside_after_another_employer_was_staged(tmp_path):
    rd = tmp_path / "r1"
    [p] = stage_picks.stage(str(rd), ["1"], rows=[], shortlist=[_kestrel("Data Analyst", 1)],
                            fetch=lambda r: {}, root=str(tmp_path))
    (rd / f"research_{p['slug']}.json").write_text(json.dumps(FIXTURE["research"]),
                                                   encoding="utf-8")
    d = dict(copy.deepcopy(FIXTURE["draft"]), role="Data Analyst")
    (rd / f"draft_{p['slug']}.json").write_text(json.dumps(d), encoding="utf-8")
    # Another employer on its own: picks.json now names only that one.
    other = dict(_kestrel("Planning Analyst", 2), company="Fernhill Freight")
    stage_picks.stage(str(rd), ["1"], rows=[], shortlist=[other], fetch=lambda r: {},
                      root=str(tmp_path))
    assert [x["slug"] for x in json.loads((rd / "picks.json").read_text())] == ["fernhill_freight"]
    [q] = stage_picks.stage(str(rd), ["1"], rows=[], shortlist=[_kestrel("Senior Data Analyst", 3)],
                            fetch=lambda r: {}, root=str(tmp_path))
    assert q["slug"] == p["slug"]
    for name in (f"draft_{q['slug']}.json", f"research_{q['slug']}.json"):
        assert not (rd / name).exists(), name
        assert (rd / "old" / f"{q['slug']}-1" / name).exists(), name
    # A stale draft put back by hand is refused, never audited or assembled as this role's.
    (rd / f"draft_{q['slug']}.json").write_text(json.dumps(d), encoding="utf-8")
    stage_picks.consent(str(rd), q["slug"], no=list(q["ask_first"]))
    [r] = stage_picks.audit(str(rd))
    assert r["verdict"] == "stale" and "'Data Analyst'" in r["why"]
    drafts, missing, _ = stage_picks.assemble(str(rd))
    assert drafts == [] and missing
    # Staging the senior role again keeps what is now its own.
    (rd / f"draft_{q['slug']}.json").write_text(json.dumps(dict(d, role="Senior Data Analyst")),
                                                encoding="utf-8")
    stage_picks.stage(str(rd), ["1"], rows=[], shortlist=[_kestrel("Senior Data Analyst", 3)],
                      fetch=lambda r: {}, root=str(tmp_path))
    assert (rd / f"draft_{q['slug']}.json").exists() and not (rd / "old" / f"{q['slug']}-2").exists()
