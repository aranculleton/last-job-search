"""A draft the grounding audit rejected never reaches the renderer.

`stage_picks.assemble` rendered any `audit_<slug>.json` it found, and a reject
was kept out only by the auditor deleting its own file. One it left behind went
on to be rendered, verified and recorded like a draft that had passed. The audit
file now holds the whole audit, verdict included, and assemble reads it.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import stage_picks  # noqa: E402
import untrusted  # noqa: E402

DRAFT = {"company": "Kestrel Mutual", "role": "Operations Analyst", "summary": "s",
         "p1": "a.", "p2": "b.", "lead": "c", "cl_bullets": [], "p4": "d."}


def _round(tmp_path, audits):
    picks = []
    for i, (slug, audit) in enumerate(audits.items(), 1):
        f = tmp_path / f"{i:02d}_{slug}.md"
        f.write_text("# head\n\n" + untrusted.fence("The posting body.") + "\n", encoding="utf-8")
        picks.append({"file": str(f), "company": slug.title(), "role": "Operations Analyst",
                      "slug": slug, "abbr": slug.title()})
        if audit is not None:
            (tmp_path / f"audit_{slug}.json").write_text(json.dumps(audit), encoding="utf-8")
    (tmp_path / "picks.json").write_text(json.dumps(picks), encoding="utf-8")
    return str(tmp_path)


def test_a_reject_is_reported_and_not_assembled(tmp_path):
    rd = _round(tmp_path, {
        "kestrel": {"verdict": "fixed", "draft": DRAFT, "changes": [], "residual_risks": []},
        "fernhill": {"verdict": "reject", "draft": dict(DRAFT, company="Fernhill"),
                     "changes": [], "residual_risks": ["the posting needs a licence"]},
        "larkspur": None,
    })
    drafts, missing, rejected = stage_picks.assemble(rd)
    assert [d["company"] for d in drafts] == ["Kestrel Mutual"]
    assert drafts[0]["posting"] == "The posting body." and drafts[0]["abbr"] == "Kestrel"
    assert missing == ["Larkspur"]
    assert rejected == ["Fernhill | Operations Analyst: the posting needs a licence"]
    on_disk = json.loads((tmp_path / "drafts.json").read_text(encoding="utf-8"))
    assert [d["company"] for d in on_disk] == ["Kestrel Mutual"]


def test_an_audit_file_holding_the_draft_alone_is_still_read(tmp_path):
    rd = _round(tmp_path, {"kestrel": [DRAFT]})
    drafts, missing, rejected = stage_picks.assemble(rd)
    assert len(drafts) == 1 and not missing and not rejected


def test_the_audit_file_holds_the_verdict_with_the_draft(tmp_path):
    # Updated 2026-10-21: this read the workflow's auditor prompt for the instruction to
    # write the whole audit. The audit file is now written by code (stage_picks.py audit,
    # tools/draft_audit.py), with the model auditor's verdict merged into it, so the
    # verdict and the draft it judged are always kept together.
    from test_one_drafting_call_per_posting import SLUG, make_round
    rd = make_round(tmp_path)
    stage_picks.audit(str(rd))
    record = json.loads((rd / f"audit_{SLUG}.json").read_text(encoding="utf-8"))
    assert {"verdict", "draft", "changes", "residual_risks"} <= set(record)
    # 2026-10-21: needs_model until the model auditor has read it, as every draft is.
    assert record["verdict"] == "needs_model" and record["draft"]["company"] == "Kestrel Mutual"


def test_the_model_audit_is_the_grounding_auditor_and_keeps_all_its_checks(tmp_path):
    # Updated 2026-10-21: this read the workflow's auditor prompt for "Read
    # .claude/agents/grounding-auditor.md first", "voice_check.py --corpus" and
    # "check_numbers.py --drafts". The model auditor no longer reads files: its packet
    # (tools/draft_audit.py packet) carries the agent file's own list of checks, and the
    # code audit runs rule 9 against every letter and check_numbers on the draft itself.
    import copy
    import draft_audit
    from test_one_drafting_call_per_posting import FIXTURE, SLUG, make_round
    with open(os.path.join(ROOT, ".claude", "agents", "grounding-auditor.md"),
              encoding="utf-8") as fh:
        agent = fh.read()
    for rule in ("Reserve Experience", "rule 9", "Audit a fixed version"):
        assert rule in agent
    d = copy.deepcopy(FIXTURE["draft"])
    d["stretches"] = [{"sentence": d["claim_map"][5]["sentence"], "why": "a stretch"}]
    rd = make_round(tmp_path, d)
    packet = draft_audit.packet(str(rd), SLUG)
    checks = agent.split("## What you check, in order", 1)[1].split("\n## ", 1)[0].strip()
    assert checks in packet and "audited_md5" in packet
    opening, _ = draft_audit.ends(FIXTURE["draft"])
    m = draft_audit.mechanical(dict(FIXTURE["draft"], pack_hash="x"), {}, FIXTURE["posting"],
                               FIXTURE["research"], corpus={"openings": {opening},
                                                            "closings": set()})
    assert "rule-9" in {f["rule"] for f in m["findings"]}
    bad = dict(copy.deepcopy(FIXTURE["draft"]), lead="Where my 45 years of work meets the role:")
    m = draft_audit.mechanical(bad, {}, FIXTURE["posting"], FIXTURE["research"],
                               corpus={"openings": set(), "closings": set()})
    assert "number" in {f["rule"] for f in m["findings"]}


def test_what_the_audit_left_open_rides_with_the_draft(tmp_path):
    # The interview pack reads what an interviewer could still probe from the kept draft;
    # nothing kept it before.
    rd = _round(tmp_path, {"kestrel": {"verdict": "pass", "draft": DRAFT, "changes": [],
                                       "residual_risks": ["no direct pricing ownership"]}})
    drafts, _, _ = stage_picks.assemble(rd)
    assert drafts[0]["residual_risks"] == ["no direct pricing ownership"]
