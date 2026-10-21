"""Every draft that will be sent gets both audits: code first, then the model auditor.

Renamed and updated 2026-10-21 from test_only_a_flagged_draft_reaches_the_model_auditor.py.
That file pinned the old gate: a draft the code audit found clean was `pass` and went to
the renderer with no model reading at all. The person's brief asks for the model auditor
on every draft that will be sent ("one non-agentic call ... given only the draft, the cited
evidence excerpts and the research facts, under 10k tokens"), with the roles they drop left
out by `--only`. So `tools/stage_picks.py audit` writes `needs_model` for every draft until
the model auditor's verdict is in, and that verdict counts only once code has re-checked
its corrected draft and found every flag it left ruled on. `assemble` renders a pass or a
fixed draft and nothing else: not one still waiting, not one code alone passed, not one
changed since its audit, not one audited against a profile that has changed since.
"""
from __future__ import annotations

import copy
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import draft_audit  # noqa: E402
import draft_pack  # noqa: E402
import stage_picks  # noqa: E402

from test_one_drafting_call_per_posting import (  # noqa: E402
    FIXTURE, SLUG, labels, make_round, run_workflow)
def stretched():
    d = copy.deepcopy(FIXTURE["draft"])
    d["stretches"] = [{"sentence": d["claim_map"][5]["sentence"], "why": "staffing is not stock"}]
    return d


def test_a_clean_draft_waits_for_the_model_audit_and_is_assembled_after_it(tmp_path):
    # Was test_a_clean_draft_passes_on_code_alone_and_is_assembled: code alone no longer
    # sends a draft to the renderer.
    rd = make_round(tmp_path)
    [r] = stage_picks.audit(str(rd))
    assert r["verdict"] == "needs_model" and r["mechanical"]["gate"] == "clean"
    record = json.loads((rd / f"audit_{SLUG}.json").read_text(encoding="utf-8"))
    assert record["verdict"] == "needs_model" and record["model"] is None
    assert record["draft"]["p1"] == FIXTURE["draft"]["p1"]
    drafts, missing, rejected = stage_picks.assemble(str(rd))
    assert drafts == [] and not rejected
    assert missing == [f"{FIXTURE['company']} (waiting on the model audit (the code checks are clean))"]
    d = json.loads((rd / f"draft_{SLUG}.json").read_text(encoding="utf-8"))
    _model(rd, "pass", d)
    [r] = stage_picks.audit(str(rd))
    assert r["verdict"] == "pass"
    drafts, missing, rejected = stage_picks.assemble(str(rd))
    assert [d["company"] for d in drafts] == [FIXTURE["company"]] and not missing and not rejected
    assert drafts[0]["posting"] == FIXTURE["posting"] and "check_output" not in drafts[0]


def test_a_record_code_alone_passed_is_never_assembled(tmp_path):
    # An audit record written before this change: code clean, `pass`, no model audit.
    rd = make_round(tmp_path)
    stage_picks.audit(str(rd))
    path = rd / f"audit_{SLUG}.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    record["verdict"] = "pass"
    path.write_text(json.dumps(record), encoding="utf-8")
    drafts, missing, _ = stage_picks.assemble(str(rd))
    assert drafts == [] and "no model audit yet" in missing[0]


def test_a_flagged_draft_waits_for_the_model_auditor_and_is_not_rendered(tmp_path):
    rd = make_round(tmp_path, stretched())
    [r] = stage_picks.audit(str(rd))
    assert r["verdict"] == "needs_model" and "stretch" in r["mechanical"]["reasons"]
    drafts, missing, rejected = stage_picks.assemble(str(rd))
    assert drafts == [] and not rejected
    assert missing == [f"{FIXTURE['company']} (waiting on the model auditor (stretch))"]


def _model(rd, verdict, draft, rulings=(), base=None):
    base = base if base is not None else json.loads((rd / f"draft_{SLUG}.json").read_text(encoding="utf-8"))
    (rd / f"model_audit_{SLUG}.json").write_text(json.dumps({
        "verdict": verdict, "draft": draft, "changes": [], "residual_risks": ["asked about staffing"],
        "rulings": list(rulings), "audited_md5": draft_audit.md5(base),
        "rules_hash": draft_pack.rules_hash()}), encoding="utf-8")


def test_a_ruling_settles_the_flag_it_names_and_nothing_else(tmp_path):
    rd = make_round(tmp_path, stretched())
    d = json.loads((rd / f"draft_{SLUG}.json").read_text(encoding="utf-8"))
    sentence = d["stretches"][0]["sentence"]
    _model(rd, "pass", d, [{"sentence": sentence, "flag": "tense", "ruling": "supported"}])
    [r] = stage_picks.audit(str(rd))
    assert r["verdict"] == "needs_model"
    assert [f["flag"] for f in r["mechanical"]["open_after_model"]] == ["stretch"]
    _model(rd, "pass", d, [{"sentence": sentence, "flag": "stretch", "ruling": "supported"}])
    [r] = stage_picks.audit(str(rd))
    assert r["verdict"] == "pass"
    drafts, missing, _ = stage_picks.assemble(str(rd))
    assert len(drafts) == 1 and not missing
    assert drafts[0]["residual_risks"] == ["asked about staffing"]


def test_the_model_auditors_fix_is_checked_again_by_code_before_it_counts(tmp_path):
    rd = make_round(tmp_path, stretched())
    fixed = json.loads((rd / f"draft_{SLUG}.json").read_text(encoding="utf-8"))
    fixed["stretches"] = []
    # A fix that breaks a rule (a dash) is not accepted, whatever the verdict says.
    broken = copy.deepcopy(fixed)
    broken["p1"] = broken["p1"].replace("demand, so", "demand — so")
    broken["claim_map"][2]["sentence"] = broken["claim_map"][2]["sentence"].replace(
        "demand, so", "demand — so")
    _model(rd, "fixed", broken)
    [r] = stage_picks.audit(str(rd))
    assert r["verdict"] == "needs_model"
    _model(rd, "fixed", fixed)
    [r] = stage_picks.audit(str(rd))
    assert r["verdict"] == "fixed"
    drafts, _, _ = stage_picks.assemble(str(rd))
    assert drafts[0]["stretches"] == []


def test_an_audit_of_another_version_says_nothing_and_a_reject_is_never_rendered(tmp_path):
    rd = make_round(tmp_path, stretched())
    d = json.loads((rd / f"draft_{SLUG}.json").read_text(encoding="utf-8"))
    _model(rd, "pass", d, base={"another": "version"})
    [r] = stage_picks.audit(str(rd))
    assert r["verdict"] == "needs_model"
    _model(rd, "reject", d)
    [r] = stage_picks.audit(str(rd))
    assert r["verdict"] == "reject"
    drafts, _, rejected = stage_picks.assemble(str(rd))
    assert drafts == [] and rejected == [f"{FIXTURE['company']} | {FIXTURE['role']}: asked about staffing"]


def test_a_draft_changed_after_its_audit_or_a_profile_changed_since_is_not_rendered(tmp_path, monkeypatch):
    rd = make_round(tmp_path)
    _model(rd, "pass", json.loads((rd / f"draft_{SLUG}.json").read_text(encoding="utf-8")))
    stage_picks.audit(str(rd))
    path = rd / f"audit_{SLUG}.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    edited = copy.deepcopy(record)
    edited["draft"]["p4"] += " One more line nobody audited."
    path.write_text(json.dumps(edited), encoding="utf-8")
    _, missing, _ = stage_picks.assemble(str(rd))
    assert missing and "changed since it was audited" in missing[0]
    path.write_text(json.dumps(record), encoding="utf-8")
    monkeypatch.setattr(draft_pack, "rules_hash", lambda: "f" * 16)
    _, missing, _ = stage_picks.assemble(str(rd))
    assert missing and "the profile changed since it was audited" in missing[0]


def test_only_audits_the_roles_named(tmp_path):
    rd = make_round(tmp_path, slugs=(SLUG, "kestrel_two"))
    got = stage_picks.audit(str(rd), only=["kestrel_two"])
    assert [r["slug"] for r in got] == ["kestrel_two"]
    assert not (rd / f"audit_{SLUG}.json").exists()
    with pytest.raises(SystemExit):
        stage_picks.audit(str(rd), only=["nobody"])


def test_two_drafts_in_one_batch_may_not_share_an_opening(tmp_path):
    rd = make_round(tmp_path, slugs=(SLUG, "kestrel_two"))
    first, second = stage_picks.audit(str(rd))
    assert first["mechanical"]["gate"] == "clean"
    assert [f["rule"] for f in second["mechanical"]["findings"]] == ["rule-9", "rule-9"]


def test_the_cli_prints_only_what_fails_for_the_drafter(tmp_path):
    rd = make_round(tmp_path, stretched())
    out = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "stage_picks.py"), "audit",
                          str(rd), "--only", SLUG, "--json"], capture_output=True, text=True)
    assert out.returncode == 1
    got = json.loads(out.stdout)
    assert got[0]["gate"] == "model" and got[0]["fix"] == []
    assert [f["flag"] for f in got[0]["flags"]] == ["stretch"]


def test_the_packet_is_small_and_carries_the_auditors_own_checks(tmp_path):
    rd = make_round(tmp_path, stretched())
    text = draft_audit.packet(str(rd), SLUG)
    base = json.loads((rd / f"draft_{SLUG}.json").read_text(encoding="utf-8"))
    assert f"audited_md5 {draft_audit.md5(base)}" in text
    # The grounding-auditor's list, from its own file: one copy of the rules.
    for rule in ("Reserve Experience", "rule 9", "certification"):
        assert rule in text
    assert "[stretch]" in text and "BH_FORECAST: Built weekly demand-forecasting models" in text
    assert "F1: Kestrel Mutual looks after 1.2 million policyholders" in text
    assert "No (a defect wherever named): SAP" in text
    assert draft_pack.approx_tokens(text)["by_chars"] < 10000


# ------------------------------------------------------------------ the workflow itself

def test_the_workflow_sends_every_draft_to_the_model_auditor():
    # Was test_the_workflow_sends_only_a_flagged_draft_to_the_model_auditor, which pinned
    # audit labels ["audit:B"]: the clean draft A was passed by code alone.
    got = run_workflow({"A": "clean", "B": "model"}, pack="THE PACK\n", pack_hash="h")
    assert labels(got, "research") == ["research:a", "research:b"]
    assert labels(got, "draft") == ["draft:a", "draft:b"]
    assert labels(got, "audit") == ["audit:a", "audit:b"]
    by = {r["pick"]["slug"]: r["audit"] for r in got["out"]}
    assert by["a"]["by"] == "model" and by["a"]["code_gate"] == "clean"
    assert by["b"]["by"] == "model" and by["b"]["code_gate"] == "model"
    # The model auditor inherits the strongest model: it is never downgraded.
    models = {c["label"]: c["model"] for c in got["calls"]}
    assert models["audit:a"] is None and models["audit:b"] is None
    # It reads one packet and runs nothing else to read: the packet and the verdict commands.
    prompt = next(c["prompt"] for c in got["calls"] if c["label"] == "audit:a")
    assert "python3 tools/draft_audit.py packet /r a" in prompt
    assert "python3 tools/draft_audit.py verdict /r a" in prompt


def test_the_person_can_skip_the_roles_they_drop():
    got = run_workflow({"A": "model", "B": "model"}, pack="P", only=["b"])
    assert labels(got, "audit") == ["audit:b"]
    assert {r["pick"]["slug"]: r["audit"]["verdict"] for r in got["out"]}["a"] == "needs_model"
    # The older "every draft" switch is the default now and changes nothing.
    got = run_workflow({"A": "clean", "B": "model"}, pack="P", model_audit="all")
    assert labels(got, "audit") == ["audit:a", "audit:b"]
    got = run_workflow({"A": "unreadable", "B": "clean"}, pack="P")
    assert labels(got, "audit") == ["audit:a", "audit:b"]
