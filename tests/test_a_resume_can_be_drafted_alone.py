"""A resume can be drafted alone, and the tracker names only the documents that were made.

The maintainer, 4 November: "There's no way to draft resumes only. A resume-only run still
named cover letter files in the tracker that were never made, which broke your own check and
blocked saving until I cleared them." The resume alone is now a choice the page passes (a
draft's `resume_only`) and a chat stages (stage_picks.py --resume-only): the drafter is told
to write no letter, the code audit holds the draft to the resume's rules, the render and the
checks make and read no letter, and the tracker row names no letter. And record_drafts.py
names a document only when it is on disk, and reads the tracker back after writing to check.
Every person and employer is invented.
"""
from __future__ import annotations

import copy
import json
import os
import shutil
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import docpaths  # noqa: E402
import draft_pack  # noqa: E402
import record_drafts  # noqa: E402
import stage_picks  # noqa: E402
from tests.test_one_drafting_call_per_posting import FIXTURE, make_round, run_workflow  # noqa: E402

TODAY = "2026-11-04"
POSTING = ("Pricing Analyst. A permanent role in our Leeds team, hybrid. You will build pricing "
           "models in SQL and Python and report to the commercial director. We want three years "
           "of analytics experience.")
LETTER = ("p1", "p2", "lead", "cl_bullets", "p4")


@pytest.fixture
def state(tmp_path, monkeypatch):
    """The example person's state, copied: a tracker and documents of the test's own."""
    st = tmp_path / "state"
    shutil.copytree(os.path.join(ROOT, "profile.example", "state"), st)
    monkeypatch.setenv("LJS_STATE", str(st))
    return st


def _row():
    return {"company": "Ottergate Foods", "title": "Pricing Analyst", "portal": "pasted",
            "url": "https://jobs.example/ottergate/4", "location": "Leeds", "desc": POSTING,
            "fit": 78}


# ------------------------------------------------------------------ asked for, and staged


def test_a_pick_staged_for_the_resume_alone_says_so_to_every_step(state):
    staged = stage_picks.stage(str(state / "r1"), ["1"], rows=[], root=str(state),
                               shortlist=[_row()], resume_only=True, today=TODAY)
    assert staged[0][docpaths.RESUME_ONLY] is True
    apps_in = json.loads((state / "r1" / "apps_in.json").read_text(encoding="utf-8"))
    assert apps_in[0][docpaths.RESUME_ONLY] is True
    assert not docpaths.has_letter(staged[0]) and not docpaths.has_letter(apps_in[0])
    # The drafter is told, in the part of its prompt that is this posting's.
    assert draft_pack.RESUME_ONLY_LINE in draft_pack.posting_brief(staged[0])
    # Asked for both, nothing changes.
    both = stage_picks.stage(str(state / "r2"), ["1"], rows=[], root=str(state),
                             shortlist=[_row()], today=TODAY)
    assert docpaths.RESUME_ONLY not in both[0] and docpaths.has_letter(both[0])
    assert draft_pack.RESUME_ONLY_LINE not in draft_pack.posting_brief(both[0])


def test_the_command_takes_the_choice(state, monkeypatch, capsys):
    posting = state / "posting.txt"
    posting.write_text(POSTING, encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["stage_picks.py", "single", str(state / "apply"),
                                      "--company", "Ottergate Foods", "--role", "Pricing Analyst",
                                      "--posting-file", str(posting), "--resume-only"])
    assert stage_picks.main() == 0
    assert "the resume alone, as asked: no letter is drafted or made" in capsys.readouterr().out
    staged = json.loads((state / "apply" / "picks.json").read_text(encoding="utf-8")) or \
        json.loads((state / "apply" / "held.json").read_text(encoding="utf-8"))
    assert staged[0][docpaths.RESUME_ONLY] is True


def test_the_page_asks_for_it_and_the_work_says_so():
    import datetime as dt

    import app_actions

    class Run:
        target = {"round": "r9", "rank": 3, "url": "https://jobs.example/ottergate/4",
                  "company": "Ottergate Foods", "title": "Pricing Analyst"}
        value = {"resume_only": True}
        db: dict = {}
        act: dict = {}
        at = dt.datetime(2026, 11, 4, 9, 0, tzinfo=dt.timezone.utc)
        written: list = []

        class w:
            @staticmethod
            def add(op, coll, wid, doc, if_version=None):
                Run.written.append(doc)
    app_actions._job_draft(Run)
    doc = Run.written[-1]
    assert doc["args"]["resume_only"] is True
    assert doc["title"].endswith("only: Ottergate Foods, Pricing Analyst")
    Run.value = {}
    app_actions._job_draft(Run)
    assert "resume_only" not in Run.written[-1]["args"]
    assert "and letter: Ottergate Foods" in Run.written[-1]["title"]


# ------------------------------------------------------------------ drafted and audited


def _alone(tmp_path, draft):
    rd = make_round(tmp_path, draft)
    picks = json.loads((rd / "picks.json").read_text(encoding="utf-8"))
    for p in picks:
        p[docpaths.RESUME_ONLY] = True
    (rd / "picks.json").write_text(json.dumps(picks), encoding="utf-8")
    return rd


def test_the_code_audit_holds_a_resume_alone_to_the_resume_rules(tmp_path):
    d = copy.deepcopy(FIXTURE["draft"])
    d.update(p1="", p2="", lead="", cl_bullets=[], p4="")
    d["claim_map"] = [c for c in d["claim_map"] if c["field"] not in LETTER]
    [r] = stage_picks.audit(str(_alone(tmp_path, d)))
    assert r["mechanical"]["findings"] == [], r["mechanical"]["findings"]
    # A letter written anyway is a finding: it would be checked and never made.
    [r] = stage_picks.audit(str(_alone(tmp_path / "again", FIXTURE["draft"])))
    assert {f["field"] for f in r["mechanical"]["findings"] if f["rule"] == "resume-only"} \
        == set(LETTER)


def test_the_workflow_spends_no_research_and_no_note_on_a_resume_alone():
    picks = [{"file": "f1", "company": "A", "role": "R", "slug": "a", "ask_first": [],
              "brief": "POSTING A", "resume_only": True},
             {"file": "f2", "company": "B", "role": "R", "slug": "b", "ask_first": [],
              "brief": "POSTING B"}]
    got = run_workflow({"A": "clean", "B": "clean"}, picks=picks, outreach=True)
    labels = [c["label"] for c in got["calls"]]
    assert "research:a" not in labels and "research:b" in labels
    audit_a = next(c["prompt"] for c in got["calls"] if c["label"] == "audit:a")
    assert "draft_audit.py note" not in audit_a


def test_the_render_makes_no_letter_for_a_resume_alone(monkeypatch):
    """fit_to_page as RUNBOOK step 3 runs it, the compiler stood in: the resume is fitted and
    no letter is rendered."""
    import fit_to_page as F
    made = []
    monkeypatch.setattr(F, "_render_resume", lambda a: made.append("resume") or 1)
    monkeypatch.setattr(F, "compile_resume", lambda abbr, passes=1: 1)
    monkeypatch.setattr(F, "_too_close", lambda abbr: False)
    monkeypatch.setattr(F, "grow_resume", lambda a, caps, skip=(): False)
    monkeypatch.setattr(F, "font_problems", lambda pdf: [])
    monkeypatch.setattr(F, "_lines", lambda pdf: 40)
    monkeypatch.setattr(F, "_render_letter", lambda a: made.append("letter") or 1)
    d = dict(copy.deepcopy(FIXTURE["draft"]), abbr=FIXTURE["abbr"], posting=FIXTURE["posting"],
             p1="", p2="", lead="", cl_bullets=[], p4="", resume_only=True)
    assert F.fit(d) == ((1, 40), 0)
    assert "resume" in made and "letter" not in made
    made.clear()
    F.fit(dict(copy.deepcopy(FIXTURE["draft"]), abbr=FIXTURE["abbr"], posting=FIXTURE["posting"]))
    assert "letter" in made


# ------------------------------------------------------------------ recorded


def _draft(abbr, **more):
    return dict({"company": "Ottergate Foods", "role": "Pricing Analyst", "abbr": abbr}, **more)


def _make(rel):
    path = docpaths.person.state(rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("% made\n")


def test_the_tracker_names_no_letter_for_a_resume_alone(state):
    row = record_drafts._row_for(_draft("Ottergate", resume_only=True), {"fit": 78}, TODAY, "r9")
    assert row["cv_file"] == docpaths.resume_rel("Ottergate") and row["cover_letter_file"] == ""
    row = record_drafts._row_for(_draft("Ottergate"), {"fit": 78, "resume_only": True}, TODAY, "")
    assert row["cover_letter_file"] == ""
    assert record_drafts._row_for(_draft("Ottergate"), {"fit": 78}, TODAY, "")[
        "cover_letter_file"] == docpaths.letter_rel("Ottergate")


def test_the_tracker_records_only_what_was_made_and_checks_after_writing(state, monkeypatch,
                                                                         capsys):
    """Through the command, as RUNBOOK step 4 runs it: a draft rendered without its letter
    names no letter, and a row an earlier run left naming a letter never made is cleared."""
    tracker = state / "job_search_tracker.csv"
    # The names the render writes under (fit_to_page settles each draft's abbr).
    otter, wex = "OttergateFoods", "WexmoorLending"
    with open(tracker, "a", encoding="utf-8", newline="") as fh:
        fh.write("2026-11-01,Wexmoor Lending,,Data Analyst,,,drafted,,70,an earlier run,"
                 f"{docpaths.resume_rel(wex)},{docpaths.letter_rel(wex)},,\n")
    for abbr in (otter, wex):
        _make(docpaths.resume_rel(abbr))
    drafts = [_draft(otter), dict(_draft(wex), company="Wexmoor Lending", role="Data Analyst"),
              dict(_draft("Quillfield"), company="Quillfield Retail")]
    assert [record_drafts.outreach.R.final_abbr(d) for d in drafts] == [d["abbr"] for d in drafts]
    metas = [{"abbr": d["abbr"], "fit": 70, "url": f"https://jobs.example/{d['abbr']}"}
             for d in drafts]
    (state / "drafts.json").write_text(json.dumps(drafts), encoding="utf-8")
    (state / "apps_in.json").write_text(json.dumps(metas), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["record_drafts.py", str(state / "drafts.json"),
                                      str(state / "apps_in.json"), "--today", TODAY,
                                      "--no-screening"])
    assert record_drafts.main() == 1, "one draft was never rendered"
    out = capsys.readouterr().out
    assert "not recorded: Quillfield Retail | Pricing Analyst: its resume was never made" in out
    rows = {r["company"]: r for r in record_drafts.csv_store.read_rows(str(tracker))}
    assert "Quillfield Retail" not in rows
    assert rows["Ottergate Foods"]["cv_file"] == docpaths.resume_rel(otter)
    assert rows["Ottergate Foods"]["cover_letter_file"] == ""
    assert rows["Wexmoor Lending"]["cover_letter_file"] == ""
    assert rows["Wexmoor Lending"]["cv_file"] == docpaths.resume_rel(wex)
    # The check after writing reads the tracker back: every file it names is on disk.
    for r in rows.values():
        for col in record_drafts.FILE_COLUMNS:
            assert not r.get(col) or docpaths.made(r[col]) or r["company"] in (
                "Larkspur Retail", "Fernhill Freight"), (r["company"], col)
    assert "the tracker names a file that was not made" not in out


def test_the_check_after_writing_names_a_file_the_tracker_holds_and_nobody_made(state):
    tracker = str(state / "job_search_tracker.csv")
    done = record_drafts.record([_draft("Ottergate")], {"OTTERGATE": {"fit": 70}}, TODAY,
                                path=tracker)
    assert record_drafts.unmade(done, tracker) == [
        f"Ottergate Foods | Pricing Analyst: {docpaths.resume_rel('Ottergate')}",
        f"Ottergate Foods | Pricing Analyst: {docpaths.letter_rel('Ottergate')}"]
    _make(docpaths.resume_rel("Ottergate"))
    _make(docpaths.letter_rel("Ottergate"))
    assert record_drafts.unmade(done, tracker) == []


# ------------------------------------------------------------------ checked whole, assembled

# The maintainer, 2026-11-05: the code audit stopped at the letter's fields, so voice_check,
# check_claims and the grounding flags never read the summary of a draft with no letter, and
# the tracker still named a letter for one. A summary with an em dash (voice_check), the word
# the example person never uses for the document (check_claims) and a sentence no claim-map
# entry covers (the grounding flags).
SUMMARY_FAULTS = ("Operations analyst with seven years — and a resume — turning "
                  "warehouse data into forecasts operations teams plan against. "
                  + FIXTURE["draft"]["summary"].split(". ", 1)[1])


def _summary_checked(r):
    rules = {f["rule"] for f in r["mechanical"]["findings"]}
    flags = {(f["flag"], f["field"]) for f in r["mechanical"]["flags"]}
    assert "voice:em-dash" in rules, r["mechanical"]["findings"]
    assert any(x.startswith("claims:the-word-resume") for x in rules), rules
    assert ("unmapped", "summary") in flags, flags


def test_a_resume_alone_with_a_letter_written_anyway_still_has_its_summary_checked(tmp_path):
    d = dict(copy.deepcopy(FIXTURE["draft"]), summary=SUMMARY_FAULTS)
    [r] = stage_picks.audit(str(_alone(tmp_path, d)))
    assert {f["field"] for f in r["mechanical"]["findings"] if f["rule"] == "resume-only"} \
        == set(LETTER)
    _summary_checked(r)


def test_a_letter_left_out_of_a_full_application_still_has_its_summary_checked(tmp_path):
    d = {k: v for k, v in copy.deepcopy(FIXTURE["draft"]).items() if k not in LETTER}
    d["summary"] = SUMMARY_FAULTS
    [r] = stage_picks.audit(str(make_round(tmp_path, d)))
    # The letter is still required where one was asked for, and nothing else is skipped.
    assert {f["field"] for f in r["mechanical"]["findings"] if f["rule"] == "missing-field"} \
        == set(LETTER)
    _summary_checked(r)


def _model_pass(rd, slug):
    import draft_audit
    base = json.loads((rd / f"draft_{slug}.json").read_text(encoding="utf-8"))
    (rd / f"model_audit_{slug}.json").write_text(json.dumps({
        "verdict": "pass", "draft": base, "changes": [], "residual_risks": [], "rulings": [],
        "audited_md5": draft_audit.md5(base), "rules_hash": draft_pack.rules_hash()}),
        encoding="utf-8")


def test_a_resume_alone_that_passes_both_audits_is_assembled_and_names_no_letter(tmp_path, state):
    # The drafter left the letter's fields out altogether.
    d = {k: v for k, v in copy.deepcopy(FIXTURE["draft"]).items() if k not in LETTER}
    d["claim_map"] = [c for c in d["claim_map"] if c["field"] not in LETTER]
    rd = _alone(tmp_path, d)
    [r] = stage_picks.audit(str(rd))
    assert r["mechanical"]["findings"] == [] and r["mechanical"]["flags"] == []
    _model_pass(rd, FIXTURE["slug"])
    [r] = stage_picks.audit(str(rd))
    assert r["verdict"] == "pass", r["mechanical"]
    [got], missing, rejected = stage_picks.assemble(str(rd))
    assert not missing and not rejected and got[docpaths.RESUME_ONLY] is True
    # The tracker names the resume alone, even with a letter an earlier render left on disk
    # under the same name.
    abbr = record_drafts.outreach.R.final_abbr(got)
    _make(docpaths.resume_rel(abbr))
    _make(docpaths.letter_rel(abbr))
    done = record_drafts.record([dict(got, abbr=abbr)], {abbr.upper(): {"fit": 70}}, TODAY,
                                path=str(state / "job_search_tracker.csv"), exists=docpaths.made)
    [(_action, row)] = done
    assert row["cv_file"] == docpaths.resume_rel(abbr) and row["cover_letter_file"] == ""


def test_a_draft_with_no_letter_in_it_never_has_one_named():
    # Not marked resume-only, and no letter written: the tracker names none.
    bare = {k: v for k, v in copy.deepcopy(FIXTURE["draft"]).items() if k not in LETTER}
    for d in (dict(bare, abbr="Kestrel"),
              dict(bare, abbr="Kestrel", p1="", p2="", lead="", cl_bullets=[], p4="")):
        assert record_drafts._row_for(d, {"fit": 70}, TODAY, "")["cover_letter_file"] == ""
    # A draft with its letter names it, as before.
    full = dict(copy.deepcopy(FIXTURE["draft"]), abbr="Kestrel")
    assert record_drafts._row_for(full, {"fit": 70}, TODAY, "")["cover_letter_file"] \
        == docpaths.letter_rel("Kestrel")
