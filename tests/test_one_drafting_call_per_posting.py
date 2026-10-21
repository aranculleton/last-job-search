"""One drafting call per posting, from the pack, checked by code before anything else.

Each drafter in the `draft-applications` workflow was an agent that read the profile, the
guides, the bridges, the renderer and two letters for itself, wrote the draft, then ran
voice_check and the outreach check by hand: forty-odd tool calls each. Now the drafter is
given the drafting pack (tools/draft_pack.py) as its first bytes, the same for every
posting, and this posting after it; it reads no file, returns the draft with a claim map,
and runs one command, `tools/stage_picks.py audit --only <slug> --json`, which runs every
existing check in code and prints only what fails.
"""
from __future__ import annotations

import copy
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import pytest  # noqa: E402

import draft_pack  # noqa: E402
import stage_picks  # noqa: E402
import untrusted  # noqa: E402

FIXTURE = json.load(open(os.path.join(ROOT, "tests", "fixtures", "drafting_round.json"),
                         encoding="utf-8"))
SLUG = FIXTURE["slug"]
WORKFLOW = os.path.join(ROOT, ".claude", "workflows", "draft-applications.js")


def store_pages(research=None):
    """Keep each research fact's page where tools/company_research.py fetch keeps the
    pages it read, so the audit's quote check finds the quote on it (as a real research
    run leaves it). The tests' own pages folder (conftest.py), never the machine's."""
    import company_research
    for f in (research or FIXTURE["research"]).get("facts") or []:
        if f.get("url") and f.get("quote"):
            company_research._store_page(f["url"], "About us", "About us. " + f["quote"]
                                         + ". Read more about the group.", "page")


def make_round(tmp_path, draft=None, slugs=(SLUG,)):
    store_pages()
    rd = tmp_path / "r1"
    (rd / "picks").mkdir(parents=True, exist_ok=True)
    picks = []
    for n, slug in enumerate(slugs, 1):
        f = rd / "picks" / f"{n:02d}_{slug}.md"
        f.write_text(f"# {FIXTURE['company']} | {FIXTURE['role']}\n\n"
                     + untrusted.fence(FIXTURE["posting"]) + "\n", encoding="utf-8")
        picks.append({"file": str(f), "company": FIXTURE["company"], "role": FIXTURE["role"],
                      "slug": slug, "abbr": FIXTURE["abbr"] + ("" if n == 1 else str(n)),
                      "ask_first": ["SAP"], "skills_no": ["SAP"]})
        (rd / f"research_{slug}.json").write_text(json.dumps(FIXTURE["research"]), encoding="utf-8")
        d = dict(copy.deepcopy(draft or FIXTURE["draft"]), pack_hash=draft_pack.rules_hash())
        (rd / f"draft_{slug}.json").write_text(json.dumps(d), encoding="utf-8")
    (rd / "picks.json").write_text(json.dumps(picks), encoding="utf-8")
    return rd


def test_a_draft_that_meets_every_rule_passes_the_code_checks(tmp_path):
    # Updated 2026-10-21: a draft code passes was `pass` and went to the renderer. Every
    # draft that will be sent is now read by the model auditor after the code audit, so a
    # clean code audit leaves it `needs_model`, waiting on that reading.
    rd = make_round(tmp_path)
    [r] = stage_picks.audit(str(rd))
    assert r["mechanical"]["gate"] == "clean" and r["mechanical"]["findings"] == []
    assert r["mechanical"]["flags"] == [] and r["verdict"] == "needs_model"
    record = json.loads((rd / f"audit_{SLUG}.json").read_text(encoding="utf-8"))
    assert record["verdict"] == "needs_model" and record["draft"]["p1"] == FIXTURE["draft"]["p1"]


def test_the_drafter_is_shown_only_what_fails(tmp_path):
    d = copy.deepcopy(FIXTURE["draft"])
    d["p1"] = d["p1"].replace("demand, so", "demand \u2014 so")
    rd = make_round(tmp_path, d)
    out = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "stage_picks.py"), "audit",
                          str(rd), "--only", SLUG, "--json"], capture_output=True, text=True)
    assert out.returncode == 1
    [got] = json.loads(out.stdout)
    assert got["gate"] == "model"
    # voice_check reads the draft as written; the renderer would turn the dash into a
    # comma, so check_claims on the rendered words has nothing to say about it.
    assert [f["rule"] for f in got["fix"]] == ["voice:em-dash"]


HARNESS = r"""
const src = require('fs').readFileSync(process.argv[1], 'utf8').replace(/^export const meta/m, 'const meta');
const gates = JSON.parse(process.argv[2]); const extra = JSON.parse(process.argv[3]);
const calls = [];
const picks = [{file: 'f1', company: 'A', role: 'R', slug: 'a', ask_first: [], brief: 'POSTING A'},
               {file: 'f2', company: 'B', role: 'R', slug: 'b', ask_first: [], brief: 'POSTING B'}];
// Agents are labelled by the pick's slug (two roles at one employer are two labels); the
// stand-in answers by the company that slug is staged for.
const company = (slug) => (picks.find(p => p.slug === slug) || {}).company || slug;
const agent = async (prompt, opts) => {
  calls.push({label: opts.label, model: opts.model || null, prompt});
  const [stage, slug] = opts.label.split(':');
  const co = company(slug);
  if (stage === 'research') return {facts: [{claim: 'c', quote: 'q', url: 'u'}], team_context: '', do_not_claim: [], salary: '', work_model: '', location: ''};
  if (stage === 'draft') return {company: co, p1: 'drafted p1', p2: 'drafted p2', claim_map: [], check_output: '[{"gate": "' + gates[co] + '"}]'};
  if (stage === 'audit') return {verdict: 'fixed', p1: 'audited p1', p2: 'audited p2', claim_map: [], check_output: '[{"slug": "' + slug + '", "verdict": "fixed", "gate": "clean"}]'};
  return {outreach_body: 'b', claim_map: [], check_output: ''};
};
const pipeline = async (items, ...stages) => {
  const out = [];
  for (let i = 0; i < items.length; i++) {
    let v; for (let s = 0; s < stages.length; s++) v = await (s ? stages[s](v, items[i], i) : stages[s](items[i], items[i], i));
    out.push(v);
  }
  return out;
};
const f = new Function('args', 'agent', 'pipeline', 'phase', 'log', 'return (async()=>{' + src + '})()');
f(Object.assign({today: 'd', round_dir: '/r', picks}, extra), agent, pipeline, () => {}, () => {})
  .then(r => console.log(JSON.stringify({calls, out: r})));
"""


def run_workflow(gates, **extra):
    node = subprocess.run(["node", "--version"], capture_output=True)
    if node.returncode != 0:
        pytest.skip("node is not installed")
    out = subprocess.run(["node", "-e", HARNESS, WORKFLOW, json.dumps(gates), json.dumps(extra)],
                         capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def labels(got, stage):
    return [c["label"] for c in got["calls"] if c["label"].startswith(stage + ":")]


def test_every_draft_prompt_opens_on_the_pack_and_sends_the_drafter_to_no_file():
    got = run_workflow({"A": "clean", "B": "clean"}, pack="THE PACK\n", pack_hash="h")
    drafts = [c["prompt"] for c in got["calls"] if c["label"].startswith("draft:")]
    assert len(drafts) == 2
    # The same first bytes for every posting: the prompt-cache prefix.
    assert all(p.startswith("THE PACK\n") for p in drafts)
    assert "POSTING A" in drafts[0] and "POSTING B" in drafts[1]
    assert "Read in full" not in drafts[0] and "01-candidate-profile.md" not in drafts[0]
    # The one command it runs is the code audit of its own draft.
    assert "python3 tools/stage_picks.py audit /r --only a --json" in drafts[0]
    assert '"pack_hash": "h"' in drafts[0]
    models = {c["label"]: c["model"] for c in got["calls"]}
    assert models["draft:a"] is None and models["research:a"] == "sonnet"


def test_without_a_pack_the_drafter_builds_it_itself():
    got = run_workflow({"A": "clean", "B": "clean"})
    draft = next(c["prompt"] for c in got["calls"] if c["label"] == "draft:a")
    assert draft.startswith("First run: python3 tools/draft_pack.py build /r")


def test_the_drafter_returns_its_claim_map_and_the_checks_last_word():
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
    assert {"claim_map", "stretches"} <= set(got["req"])
    assert "check_output" in got["schema"]
