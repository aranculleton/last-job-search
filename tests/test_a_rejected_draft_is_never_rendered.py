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


def test_the_workflow_writes_the_verdict_with_the_draft():
    with open(os.path.join(ROOT, ".claude", "workflows", "draft-applications.js"),
              encoding="utf-8") as fh:
        text = fh.read()
    audit = text.split("phase: 'Audit'", 1)[0].rsplit("agent(", 1)[1]
    assert "the whole audit you return (verdict, draft" in audit
    assert "delete ${scratch}/audit_" not in audit
