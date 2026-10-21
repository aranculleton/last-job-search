"""A draft needs no outreach body; one is written by its own small step only when wanted.

The drafter was made to write `outreach_body` for every posting, wanted or not, and the
auditor checked it again. `tools/outreach.py` has always built the note from the letter
when a draft carries no body, so a draft without one is complete. When the person wants a
written note, the workflow's Outreach step writes `outreach_<slug>.json`, and the code
audit merges it into the draft and checks it whole, opening line included.
"""
from __future__ import annotations

import copy
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import pytest  # noqa: E402

import draft_audit  # noqa: E402
import outreach  # noqa: E402
import stage_picks  # noqa: E402
from test_one_drafting_call_per_posting import (  # noqa: E402
    FIXTURE, SLUG, WORKFLOW, labels, make_round, run_workflow)


def test_a_draft_with_no_body_is_complete_and_its_note_is_built_from_the_letter(tmp_path):
    assert "outreach_body" not in FIXTURE["draft"]
    rd = make_round(tmp_path)
    [r] = stage_picks.audit(str(rd))
    # Updated 2026-10-21: clean for code, and waiting on the model audit like every draft.
    assert r["mechanical"]["gate"] == "clean" and r["verdict"] == "needs_model"
    note = outreach.outreach_note(dict(FIXTURE["draft"]))
    assert note.startswith(outreach.OPENING.format(role=FIXTURE["role"], company="Kestrel Mutual"))
    assert outreach.check_note(note) == []


def test_a_body_the_outreach_step_writes_is_merged_and_checked_whole(tmp_path):
    rd = make_round(tmp_path)
    body = ("Your claims teams staff to a weekly forecast. At Brindle & Hart Logistics I built "
            "the demand models that cut forecast error from 22% to 14%. Happy to answer anything "
            "the application leaves open.")
    cm = [{"field": "outreach_body", "sentence": s, "cites": c} for s, c in (
        ("Your claims teams staff to a weekly forecast.", ["POSTING"]),
        ("At Brindle & Hart Logistics I built the demand models that cut forecast error from 22% "
         "to 14%.", ["BH_FORECAST"]),
        ("Happy to answer anything the application leaves open.", []))]
    # Updated 2026-10-21: the note is saved by draft_audit.write_note (the workflow's
    # `draft_audit.py note`), which stamps it with the draft it was written for; a file
    # written by hand carries no stamp and is left out (test_a_note_for_another_draft...).
    draft_audit.write_note(str(rd), SLUG, {"outreach_body": body, "claim_map": cm})
    [r] = stage_picks.audit(str(rd))
    assert r["mechanical"]["gate"] == "clean", r["mechanical"]
    record = json.loads((rd / f"audit_{SLUG}.json").read_text(encoding="utf-8"))
    assert record["draft"]["outreach_body"] == body
    # A body that fits in 80 words alone and not with the opening line in front of it.
    long = " ".join(["Your claims teams staff to a weekly forecast."] * 9)
    assert len(long.split()) < outreach.MAX_NOTE_WORDS
    draft_audit.write_note(str(rd), SLUG, {"outreach_body": long, "claim_map": []})
    [r] = stage_picks.audit(str(rd))
    assert r["verdict"] == "needs_model"
    assert any(f["rule"] == "outreach" and "words" in f["text"] for f in r["mechanical"]["findings"])


def test_the_drafter_is_not_asked_for_a_body_and_the_step_runs_only_when_wanted():
    node = subprocess.run(["node", "--version"], capture_output=True)
    if node.returncode != 0:
        pytest.skip("node is not installed")
    probe = ("const src = require('fs').readFileSync(process.argv[1], 'utf8')"
             ".replace(/^export const meta/m, 'const meta');"
             "const body = src.split('// ------------------------------------------------------------------ research')[0];"
             "const f = new Function('args', body + '; return {DRAFT_REQ, DRAFT_SCHEMA};');"
             "const r = f({today: 'd', round_dir: '/r', picks: []});"
             "console.log(JSON.stringify({req: r.DRAFT_REQ, schema: r.DRAFT_SCHEMA.required}))")
    got = json.loads(subprocess.run(["node", "-e", probe, WORKFLOW], capture_output=True,
                                    text=True, check=True).stdout)
    assert "outreach_body" not in got["req"] and "outreach_body" not in got["schema"]
    assert {"claim_map", "stretches"} <= set(got["req"])
    assert labels(run_workflow({"A": "clean", "B": "clean"}, pack="P"), "outreach") == []
    got = run_workflow({"A": "clean", "B": "clean"}, pack="P", outreach=["b"])
    assert labels(got, "outreach") == ["outreach:b"]
    assert labels(run_workflow({"A": "clean", "B": "model"}, pack="P", outreach=True),
                  "outreach") == ["outreach:a", "outreach:b"]


def test_a_draft_still_waiting_on_the_model_auditor_gets_no_note():
    got = run_workflow({"A": "model", "B": "clean"}, pack="P", outreach=True, only=["b"])
    assert labels(got, "outreach") == ["outreach:b"]
    # The note is written from the paragraphs the model auditor kept, not the drafter's.
    prompt = next(c["prompt"] for c in got["calls"] if c["label"] == "outreach:b")
    assert "p1: audited p1" in prompt and "drafted p1" not in prompt


def test_old_drafts_that_carry_a_body_are_still_checked_as_before():
    d = dict(copy.deepcopy(FIXTURE["draft"]), outreach_body="x " * 90)
    got = draft_audit.parity(d, FIXTURE["posting"], FIXTURE["research"])
    assert any(check == "outreach" for check, _ in got["old"]) and got["missed"] == []
