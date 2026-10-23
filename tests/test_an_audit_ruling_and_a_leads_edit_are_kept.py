"""An audit ruling matches its flag however the sentence was quoted, the auditor's packet
holds the draft it returns, and a lead's edit to the corrected draft is kept.

Three findings from one round (2026-10-23): a p2-uncited flag showed the paragraph cut to
120 characters, so a ruling quoting the whole paragraph never settled it; the packet gave
the draft as plain lines, not the object the verdict returns, so auditors opened the draft
file for the company and role and tried again; and a re-audit wrote over a lead's edit to
the corrected draft. The draft and employer are the invented fixture's.
"""
from __future__ import annotations

import copy
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import draft_audit  # noqa: E402
import draft_pack  # noqa: E402
import stage_picks  # noqa: E402

from test_one_drafting_call_per_posting import FIXTURE, SLUG, make_round  # noqa: E402


def _base(rd):
    return json.loads((rd / f"draft_{SLUG}.json").read_text(encoding="utf-8"))


def test_a_ruling_quoting_the_whole_sentence_or_its_cut_settles_the_flag():
    para = ("Your team rebuilt its demand forecasting around store-level signals last year, "
            "and the planning work that came out of it is the kind I have done for four years.")
    flag = {"flag": "p2-uncited", "field": "p2", "sentence": para}
    for quoted in (para, para[:120]):
        assert draft_audit._ruled(flag, [{"sentence": quoted, "flag": "p2-uncited",
                                          "ruling": "supported"}]), quoted
    # Too little of it says nothing about which sentence it is.
    assert not draft_audit._ruled(flag, [{"sentence": para[:20], "ruling": "supported"}])
    # Another flag on the same sentence is not settled by it.
    assert not draft_audit._ruled(flag, [{"sentence": para, "flag": "stretch",
                                          "ruling": "supported"}])


def test_the_packet_holds_the_draft_it_returns_and_a_verdict_keeps_what_it_left_out(tmp_path):
    rd = make_round(tmp_path)
    text = draft_audit.packet(str(rd), SLUG)
    assert "== THE DRAFT AS THE OBJECT YOU RETURN" in text
    assert f'"company": "{FIXTURE["company"]}"' in text
    base = _base(rd)
    lean = {k: v for k, v in base.items() if k not in ("company", "role")}
    draft_audit.write_verdict(str(rd), SLUG, {"verdict": "pass", "draft": lean,
                                              "audited_md5": draft_audit.md5(base),
                                              "rules_hash": draft_pack.rules_hash()})
    saved = json.loads((rd / f"model_audit_{SLUG}.json").read_text(encoding="utf-8"))
    assert saved["draft"]["company"] == base["company"]
    assert saved["draft"]["role"] == base["role"]


def test_a_leads_edit_to_the_corrected_draft_survives_a_re_audit(tmp_path):
    rd = make_round(tmp_path)
    base = _base(rd)
    (rd / f"model_audit_{SLUG}.json").write_text(json.dumps({
        "verdict": "pass", "draft": copy.deepcopy(base), "changes": [], "residual_risks": [],
        "rulings": [], "audited_md5": draft_audit.md5(base),
        "rules_hash": draft_pack.rules_hash()}), encoding="utf-8")
    stage_picks.audit(str(rd))
    path = rd / f"audit_{SLUG}.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    edited = record["draft"]["p4"] + " "
    record["draft"]["p4"] = edited
    path.write_text(json.dumps(record), encoding="utf-8")
    stage_picks.audit(str(rd))
    again = json.loads(path.read_text(encoding="utf-8"))
    assert again["draft"]["p4"] == edited
    model = json.loads((rd / f"model_audit_{SLUG}.json").read_text(encoding="utf-8"))
    assert model["draft"]["p4"] == edited
    assert any("edited after the audit" in str(c.get("reason")) for c in again["changes"])
    # Audited once more with nothing edited, it changes nothing.
    stage_picks.audit(str(rd))
    assert json.loads(path.read_text(encoding="utf-8"))["draft"]["p4"] == edited
